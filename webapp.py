"""Telegram Mini App server: to'liq API + statik panel.
Xavfsizlik: /api/* faqat Telegram initData imzosi to'g'ri va ADMIN_IDS ichida bo'lsa ishlaydi.
Brauzerda initData bo'lmasa, panel o'zi demo (mock) rejimda ochiladi — API chaqirilmaydi."""
import asyncio, hashlib, hmac, json, os, re, shutil, time, uuid
from pathlib import Path
from urllib.parse import parse_qsl

from aiohttp import web

import appctl, core, filesvc as fm, jobs
from config import ADMINS, APPS, NAME_RE, SVC_RE, TRASH, TMP, sh

WEB = Path(__file__).resolve().parent / "webapp"
TOKEN = os.environ.get("BOT_TOKEN", "")
MAX_UP = 64 * 1024 * 1024   # 64MB
ok = lambda **k: web.json_response({"ok": True, **k})
fail = lambda msg, s=400: web.json_response({"error": msg}, status=s)


# ───────── auth ─────────
def verify(init: str) -> dict | None:
    """initData imzosini tekshiradi; foydalanuvchi ma'lumotini qaytaradi (yoki None)."""
    if not init:
        return None
    try:
        d = dict(parse_qsl(init, keep_blank_values=True))
        h = d.pop("hash", "")
        chk = "\n".join(f"{k}={v}" for k, v in sorted(d.items()))
        key = hmac.new(b"WebAppData", TOKEN.encode(), hashlib.sha256).digest()
        good = hmac.compare_digest(hmac.new(key, chk.encode(), hashlib.sha256).hexdigest(), h)
        if not good or time.time() - int(d.get("auth_date", 0)) > 86400:
            return None
        u = json.loads(d.get("user", "{}"))
        return u if u.get("id") in ADMINS else None
    except Exception:
        return None


@web.middleware
async def auth(req, handler):
    if req.path.startswith("/api/") and req.method != "OPTIONS":
        u = verify(req.headers.get("X-Init", ""))
        if not u:
            return fail("Ruxsat yo'q. Panelni bot orqali oching.", 403)
        req["user"] = u
    return await handler(req)


@web.middleware
async def errors(req, handler):
    try:
        return await handler(req)
    except ValueError as e:
        return fail(str(e), 400)
    except web.HTTPException:
        raise
    except Exception as e:
        return fail(f"{type(e).__name__}: {e}", 500)


# ───────── yordamchi ─────────
def jid(req) -> str:
    return req.match_info["id"]


def app_or_404(n: str) -> str:
    if not NAME_RE.match(n) or not (APPS / n).is_dir():
        raise web.HTTPNotFound(text=json.dumps({"error": "Ilova topilmadi."}),
                               content_type="application/json")
    return n


def token_path(tok: str) -> Path:
    p = fm.P(tok)
    if not p:
        raise ValueError("Havola eskirgan — papkani qaytadan oching.")
    return p


# ───────── asosiy ─────────
async def me(req):
    u = req["user"]
    return ok(id=u.get("id"), name=" ".join(x for x in (u.get("first_name"), u.get("last_name")) if x),
              username=u.get("username", ""), photo=u.get("photo_url", ""),
              admins=sorted(ADMINS), version=2)


async def status(req) -> web.Response:
    return web.json_response(await asyncio.to_thread(core.status))


async def apps_list(req):
    names = appctl.app_names()
    sts = await appctl.states(names) if names else []
    out = []
    for n, s in zip(names, sts):
        out.append({"name": n, "state": s, "mode": appctl.mode(n), "kind": appctl.detect(APPS / n)[0],
                    "avg": appctl.avg_time(n), "backups": len(appctl.backups(n))})
    return web.json_response(out)


async def app_detail(req):
    d = await appctl.detail(app_or_404(req.match_info["n"]))
    return web.json_response(d)


async def app_act(req):
    n, a = app_or_404(req.match_info["n"]), req.match_info["a"]
    if a not in {"start", "stop", "restart"}:
        return fail("Amal noma'lum.")
    code, out = await appctl.ctl(n, a)
    await asyncio.sleep(1)
    st = await appctl.state(n)
    return ok(done=code == 0, state=st, out=out[-1500:])


async def app_logs(req):
    n = app_or_404(req.match_info["n"])
    lines = min(int(req.query.get("lines", 120)), 400)
    return ok(text=await appctl.logs(n, lines, req.query.get("since", "")))


async def app_env_get(req):
    n = app_or_404(req.match_info["n"])
    env = appctl.env_read(n)
    return ok(keys=[{"key": k, "value": v, "masked": appctl.mask(v)} for k, v in env.items()], count=len(env))


async def app_env_set(req):
    n = app_or_404(req.match_info["n"])
    b = await req.json()
    text = (b.get("text") or "").strip()
    if b.get("key"):
        k, v = str(b["key"]).strip(), str(b.get("value", ""))
        if not appctl.KEY_RE.fullmatch(k):
            return fail("Kalit nomi yaroqsiz (harf/raqam/_, raqam bilan boshlanmasin).")
        appctl.env_write(n, {k: v})
        return ok(saved=[k], bad=[])
    if not text:
        return fail("Bo'sh matn.")
    upd, bad = appctl.env_parse_lines(text)
    if not upd:
        return fail("Format: KALIT=qiymat")
    appctl.env_write(n, upd)
    return ok(saved=list(upd), bad=bad)


async def app_env_del(req):
    n = app_or_404(req.match_info["n"])
    k = req.query.get("key", "")
    appctl.env_write(n, drop={k})
    return ok(deleted=k)


async def app_backups(req):
    n = app_or_404(req.match_info["n"])
    return ok(backups=[b.name for b in appctl.backups(n)])


async def app_rollback(req):
    n = app_or_404(req.match_info["n"])
    j = appctl.start_rollback(n)
    return ok(job=j.snap())


async def app_delete(req):
    n = app_or_404(req.match_info["n"])
    if req.query.get("confirm") != "1":
        return fail("Tasdiqlash kerak.")
    await appctl.wipe(n)
    return ok(deleted=n)


async def app_deploy(req):
    """ZIP yuklash: yangi deploy yoki mavjud ilovani yangilash (target)."""
    reader = await req.multipart()
    blob, filename, target = None, "", (req.query.get("target") or "").strip()
    while True:
        part = await reader.next()
        if part is None:
            break
        if part.name == "file":
            filename = part.filename or ""
            blob = await part.read(decode=False)
        elif part.name == "target":
            target = (await part.text()).strip()
    if not blob:
        return fail("Fayl yuborilmadi.")
    if not filename.lower().endswith(".zip"):
        return fail("Faqat .zip fayl qabul qilinadi.")
    name = re.sub(r"[^a-zA-Z0-9_.-]", "-", Path(filename).stem).lstrip(".-")[:50] or "app"
    if target and not NAME_RE.match(target):
        return fail("Ilova nomi yaroqsiz.")
    zpath = TMP / f"{uuid.uuid4().hex}.zip"
    zpath.write_bytes(blob)
    j = appctl.start_deploy(zpath, name, target or None)
    return ok(job=j.snap(), name=target or name, update=bool(target))


async def job_get(req):
    j = jobs.get(jid(req))
    return web.json_response(j.snap()) if j else fail("Jarayon topilmadi.", 404)


async def job_cancel(req):
    return ok(cancelled=jobs.cancel(jid(req)))


# ───────── tizim ─────────
async def procs(req):
    return web.json_response(await asyncio.to_thread(core.procs_list, req.query.get("sort", "cpu"),
                                                      int(req.query.get("limit", 40))))


async def proc_one(req):
    d = await asyncio.to_thread(core.proc_detail, int(req.match_info["pid"]))
    return web.json_response(d) if d else fail("Jarayon topilmadi.", 404)


async def proc_kill(req):
    pid = int(req.match_info["pid"])
    sig = int(req.query.get("sig", 15))
    err = await asyncio.to_thread(core.proc_kill, pid, sig)
    return fail(err) if err else ok(pid=pid)


async def ports(req):
    try:
        return web.json_response(await asyncio.to_thread(core.ports))
    except Exception as e:
        return web.json_response([], headers={"X-Warn": str(e)})


async def services(req):
    return web.json_response(await core.services())


async def service_one(req):
    return web.json_response(await core.service_info(req.match_info["n"]))


async def service_act(req):
    r = await core.service_act(req.match_info["n"], req.match_info["a"])
    if "blocked" in r:
        return fail(r["blocked"], 409)
    return ok(**r)


async def service_journal(req):
    return ok(text=await core.journal(req.match_info["n"], int(req.query.get("lines", 80))))


async def disk(req):
    return web.json_response(await core.disk())


async def clean(req):
    return ok(**await core.clean())


async def docker(req):
    return ok(**await core.docker())


async def shell(req):
    b = await req.json()
    return ok(**(await core.shell(b.get("cmd", ""), min(int(b.get("timeout", 60)), 300))))


async def reboot(req):
    asyncio.get_running_loop().call_later(1, lambda: asyncio.create_task(core.reboot()))
    return ok(reboot=True)


# ───────── fayllar ─────────
async def f_roots(req):
    return ok(roots=fm.roots(), trash=str(TRASH))


async def f_list(req):
    p = token_path(req.query.get("token", ""))
    if not p.is_dir():
        return fail("Bu papka emas.")
    return web.json_response(await asyncio.to_thread(fm.listdir, p, int(req.query.get("page", 0))))


async def f_resolve(req):
    """Absolyut yo'lni tokenga aylantiradi (ilovaning papkasini ochish uchun)."""
    raw = req.query.get("path", "")
    if not raw.startswith("/"):
        return fail("Yo'l absolyut bo'lishi kerak.")
    p = Path(raw)
    if not p.exists():
        return fail("Topilmadi (ilova papkasi bormi?).", 404)
    return ok(token=fm.tid(p), path=str(p), dir=p.is_dir())


async def f_stat(req):
    p = token_path(req.query.get("token", ""))
    return web.json_response(await asyncio.to_thread(fm.stat, p))


async def f_read(req):
    p = token_path(req.query.get("token", ""))
    if p.is_dir():
        return fail("Bu papka.")
    return web.json_response(await asyncio.to_thread(fm.read_text, p))


async def f_write(req):
    b = await req.json()
    p = token_path(b.get("token", ""))
    if p.is_dir():
        return fail("Papka ustiga yozib bo'lmaydi.")
    if fm.guard(p):
        return fail(fm.guard(p))
    await asyncio.to_thread(fm.write_text, p, b.get("text", ""))
    return ok(size=len(b.get("text", "")))


async def f_download(req):
    p = token_path(req.query.get("token", ""))
    if not p.exists():
        return fail("Topilmadi.", 404)
    if p.is_dir():
        out = TMP / f"{uuid.uuid4().hex[:8]}-{p.name}.zip"
        await asyncio.to_thread(fm.zip_dir, p, out)
        return web.FileResponse(out, headers={"Content-Disposition": f'attachment; filename="{p.name}.zip"'})
    return web.FileResponse(p, headers={"Content-Disposition": f'attachment; filename="{p.name}"'})


async def f_tail(req):
    p = token_path(req.query.get("token", ""))
    if p.is_dir():
        return fail("Bu papka.")
    return ok(text=await asyncio.to_thread(fm.tail, p, int(req.query.get("bytes", 8000))))


async def f_upload(req):
    reader = await req.multipart()
    d = token_path(req.query.get("token", ""))
    if not d.is_dir():
        return fail("Papka topilmadi.")
    saved = []
    while True:
        part = await reader.next()
        if part is None:
            break
        if part.name == "file":
            blob = await part.read(decode=False)
            if len(blob) > MAX_UP:
                return fail("Fayl juda katta (64MB).")
            dst = await asyncio.to_thread(fm.save_upload, d, part.filename or "file", blob)
            saved.append({"name": dst.name, "token": fm.tid(dst), "size": dst.stat().st_size})
    return ok(saved=saved)


async def f_mkdir(req):
    b = await req.json()
    d = token_path(b.get("token", ""))
    name = str(b.get("name", "")).strip()
    if not name or "/" in name or name in (".", "..") or "\0" in name or len(name) > 200:
        return fail("Nom yaroqsiz.")
    dst = d / name
    if dst.exists():
        return fail("Bunday nom allaqachon bor.")
    dst.mkdir()
    return ok(token=fm.tid(dst), name=name)


async def f_rename(req):
    b = await req.json()
    p = token_path(b.get("token", ""))
    g = fm.guard(p)
    if g:
        return fail(g)
    name = str(b.get("name", "")).strip()
    if not name or "/" in name or name in (".", "..") or "\0" in name or len(name) > 200:
        return fail("Nom yaroqsiz.")
    dst = p.with_name(name)
    if dst.exists():
        return fail("Bunday nom allaqachon bor.")
    p.rename(dst)
    return ok(token=fm.tid(dst), name=name)


async def f_remove(req):
    b = await req.json()
    p = token_path(b.get("token", ""))
    g = fm.guard(p)
    if g:
        return fail(g)
    if not (p.exists() or p.is_symlink()):
        return fail("Topilmadi.", 404)
    dst = await asyncio.to_thread(fm.to_trash, p)
    key = uuid.uuid4().hex[:8]
    fm.TRASHED[key] = (str(p), str(dst))
    return ok(undo=key, trash=fm.tid(dst), orig=str(p))


async def f_restore(req):
    b = await req.json()
    key = b.get("undo", "")
    orig, dst = fm.TRASHED.get(key, (None, None))
    if not orig:
        return fail("Qaytarib bo'lmaydi (muddati o'tgan).")
    if Path(orig).exists():
        return fail("Asl joyda shu nomli narsa bor.")
    await asyncio.to_thread(shutil.move, dst, orig)
    fm.TRASHED.pop(key, None)
    return ok(token=fm.tid(Path(orig)), path=orig)


async def f_paste(req):
    b = await req.json()
    src, dst = token_path(b.get("src", "")), token_path(b.get("dst", ""))
    mode = "move" if b.get("mode") == "move" else "copy"
    if mode == "move" and fm.guard(src):
        return fail(fm.guard(src))
    if not dst.is_dir():
        return fail("Manzil papka emas.")
    out = await asyncio.to_thread(fm.paste, mode, src, dst)
    return ok(token=fm.tid(out), name=out.name)


# ───────── AI ─────────
async def ai_fix(req):
    n = app_or_404(req.match_info["n"])
    j = appctl.start_fix(n)
    return ok(job=j.snap())


async def ai_apply(req):
    n = app_or_404(req.match_info["n"])
    b = await req.json()
    pid = str(b.get("pid", ""))
    if not pid:
        return fail("Taklif ID kerak.")
    j = appctl.start_apply(n, pid)
    return ok(job=j.snap())


async def ai_pending(req):
    n = req.match_info["n"]
    out = [{"pid": k, "explanation": v.get("explanation", ""), "files": [f["path"] for f in v.get("files", [])]}
           for k, v in appctl.PENDING.items() if v.get("name") == n]
    return ok(pending=out)


# ───────── statik ─────────
async def index(req):
    return web.FileResponse(WEB / "index.html", headers={"Cache-Control": "no-store"})


async def static(req):
    f = req.match_info["f"]
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,40}", f):
        raise web.HTTPNotFound()
    return web.FileResponse(WEB / f, headers={"Cache-Control": "no-store"})


def make_app() -> web.Application:
    app = web.Application(middlewares=[errors, auth], client_max_size=MAX_UP + 1024 * 1024)
    R = app.router
    R.add_get("/", index)
    R.add_get("/static/{f}", static)
    R.add_get("/api/me", me)
    R.add_get("/api/status", status)
    R.add_get("/api/apps", apps_list)
    R.add_post("/api/apps/deploy", app_deploy)
    R.add_get("/api/apps/{n}", app_detail)
    R.add_post("/api/apps/{n}/{a:start|stop|restart}", app_act)
    R.add_get("/api/apps/{n}/logs", app_logs)
    R.add_get("/api/apps/{n}/env", app_env_get)
    R.add_post("/api/apps/{n}/env", app_env_set)
    R.add_delete("/api/apps/{n}/env", app_env_del)
    R.add_get("/api/apps/{n}/backups", app_backups)
    R.add_post("/api/apps/{n}/rollback", app_rollback)
    R.add_delete("/api/apps/{n}", app_delete)
    R.add_get("/api/jobs/{id}", job_get)
    R.add_post("/api/jobs/{id}/cancel", job_cancel)
    R.add_get("/api/procs", procs)
    R.add_get("/api/procs/{pid:\\d+}", proc_one)
    R.add_post("/api/procs/{pid:\\d+}/kill", proc_kill)
    R.add_get("/api/ports", ports)
    R.add_get("/api/services", services)
    R.add_get("/api/services/{n}", service_one)
    R.add_post("/api/services/{n}/{a:start|stop|restart|enable|disable}", service_act)
    R.add_get("/api/services/{n}/journal", service_journal)
    R.add_get("/api/disk", disk)
    R.add_post("/api/disk/clean", clean)
    R.add_get("/api/docker", docker)
    R.add_post("/api/sh", shell)
    R.add_post("/api/reboot", reboot)
    R.add_get("/api/files/roots", f_roots)
    R.add_get("/api/files/list", f_list)
    R.add_get("/api/files/stat", f_stat)
    R.add_get("/api/files/resolve", f_resolve)
    R.add_get("/api/files/read", f_read)
    R.add_post("/api/files/write", f_write)
    R.add_get("/api/files/download", f_download)
    R.add_get("/api/files/tail", f_tail)
    R.add_post("/api/files/upload", f_upload)
    R.add_post("/api/files/mkdir", f_mkdir)
    R.add_post("/api/files/rename", f_rename)
    R.add_post("/api/files/remove", f_remove)
    R.add_post("/api/files/restore", f_restore)
    R.add_post("/api/files/paste", f_paste)
    R.add_post("/api/ai/{n}/fix", ai_fix)
    R.add_post("/api/ai/{n}/apply", ai_apply)
    R.add_get("/api/ai/{n}/pending", ai_pending)
    return app


async def serve(host: str | None = None, port: int | None = None):
    runner = web.AppRunner(make_app())
    await runner.setup()
    await web.TCPSite(runner, host or os.getenv("WEBAPP_HOST", "127.0.0.1"),
                      port or int(os.getenv("WEBAPP_PORT", "8080"))).start()
    return runner


_TUN = []


async def tunnel(port: int) -> str:
    """cloudflared quick tunnel — domen shart emas. Topilmasa bo'sh satr."""
    exe = shutil.which("cloudflared") or ("/usr/local/bin/cloudflared" if Path("/usr/local/bin/cloudflared").exists() else "")
    if not exe:
        return ""
    p = await asyncio.create_subprocess_exec(exe, "tunnel", "--no-autoupdate", "--protocol", os.getenv("CF_PROTOCOL", "http2"), "--url", f"http://127.0.0.1:{port}",
                                             stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
    fut = asyncio.get_running_loop().create_future()

    async def pump():
        url = ""
        async for line in p.stdout:
            t = line.decode(errors="replace")
            m = re.search(r"https://[a-z0-9-]+\.trycloudflare\.com", t)
            if m and not url:
                url = m[0]
            # URL logda tunnel ulanishidan OLDIN chiqadi — ulanish ro'yxatdan o'tgach qaytaramiz (1033 xatosini oldini oladi)
            if url and "Registered tunnel connection" in t and not fut.done():
                fut.set_result(url)
    _TUN.extend([p, asyncio.create_task(pump())])
    try:
        return await asyncio.wait_for(fut, 45)
    except asyncio.TimeoutError:
        return ""


if __name__ == "__main__":
    async def _run():
        await core.sampler_once() if hasattr(core, "sampler_once") else None
        asyncio.create_task(core.sampler())
        runner = await serve(os.getenv("WEBAPP_HOST", "0.0.0.0"))
        url = await tunnel(int(os.getenv("WEBAPP_PORT", "8080")))
        print("Panel:", url or "http://0.0.0.0:%s" % os.getenv("WEBAPP_PORT", "8080"), flush=True)
        await asyncio.Event().wait()
    asyncio.run(_run())
