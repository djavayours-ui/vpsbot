"""Ilovalar yadrosi: ZIP deploy, systemd/docker boshqaruv, yangilash, rollback, o'chirish, .env kalitlar.
Aiogram'siz — jobs.Progress orqali holat beriladi, bot ham web ham shundan foydalanadi."""
import asyncio, hashlib, json, os, re, shutil, time, uuid, zipfile
from pathlib import Path

import filesvc as fm
import jobs
from config import APPS, NAME_RE, TMP, q, sh

AI_MODEL = os.getenv("AI_MODEL", "claude-sonnet-4-5")
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY", "")
STABLE_SECS = int(os.getenv("STABLE_SECS", "10"))
BACKUPS = APPS / ".backups"
UNIT_DIR = Path(os.getenv("SYSTEMD_DIR", "/etc/systemd/system"))  # test uchun o'zgartirsa bo'ladi
TIMINGS = APPS / ".timings.json"
COMPOSE = ("docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml")
ENTRY = ("main.py", "bot.py", "app.py", "run.py", "server.py")
KEEP = {".venv", "venv", "node_modules", ".env", "data", "uploads", "sessions"}
DB_RE = re.compile(r"\.(db|sqlite3?|session)(-\w+)?$")
PKG_RE = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.\-\[\]=<>!~,]*")
NPM_RE = re.compile(r"[@A-Za-z0-9_][@A-Za-z0-9_./\-^~]*")
PENDING: dict[str, dict] = {}   # AI takliflari


# ───────── asosiy yordamchilar ─────────
def unit(n: str) -> str:
    return f"app-{n}.service"


def unit_file(n: str) -> Path:
    return UNIT_DIR / unit(n)


def app_names() -> list[str]:
    try:
        return sorted(p.name for p in APPS.iterdir() if p.is_dir() and not p.name.startswith("."))
    except OSError:
        return []


def mode(n: str) -> str:
    """'systemd' | 'docker' | '' (boshqarilmaydi)."""
    if unit_file(n).exists():
        return "systemd"
    return "docker" if any((APPS / n / f).exists() for f in COMPOSE) else ""


def dc(n: str, args: str, timeout: int = 300):
    return sh(f"docker compose {args}", cwd=APPS / n, timeout=timeout)


async def ctl(n: str, a: str) -> tuple[int, str]:
    if mode(n) == "docker":
        return await dc(n, {"start": "up -d", "stop": "stop", "restart": "restart"}[a])
    return await sh(f"systemctl {a} {unit(n)}")


async def states(names: list[str]) -> list[str]:
    res = {}
    sysd = [n for n in names if mode(n) != "docker"]
    if sysd:
        _, out = await sh("systemctl is-active " + " ".join(unit(n) for n in sysd), timeout=30)
        res.update(zip(sysd, out.split()))
    for n in names:
        if mode(n) == "docker":
            _, run = await dc(n, "ps --status running -q 2>/dev/null", 60)
            _, allc = await dc(n, "ps -a -q 2>/dev/null", 60)
            r, a = len(run.split()), len(allc.split())
            res[n] = "inactive" if not r else "active" if r == a else "failed"
    return [res.get(n, "inactive") for n in names]


async def state(n: str) -> str:
    return (await states([n]))[0]


async def probe(n: str) -> tuple[str, int]:
    if mode(n) == "docker":
        return await state(n), 0
    _, o = await sh(f"systemctl show {unit(n)} -p ActiveState,NRestarts", timeout=30)
    kv = dict(l.split("=", 1) for l in o.splitlines() if "=" in l)
    return kv.get("ActiveState", "inactive"), int(kv.get("NRestarts") or 0)


async def logs(n: str, lines: int = 60, since: str = "") -> str:
    if not NAME_RE.match(n):
        raise ValueError("Nom yaroqsiz.")
    if mode(n) == "docker":
        return (await dc(n, f"logs --no-color --tail {lines} 2>&1", 90))[1]
    cmd = f"journalctl -u {unit(n)} -n {lines} --no-pager -o cat" + (f" --since {q(since)}" if since else "")
    return (await sh(cmd, timeout=60))[1]


async def wait_healthy(n: str, boot_timeout: int = 30) -> tuple[bool, float | None, str]:
    t0, up, n0 = time.time(), None, 0
    while time.time() - t0 < boot_timeout:
        st, nr = await probe(n)
        if st == "active":
            up, n0 = time.time() - t0, nr
            break
        if st == "failed":
            return False, None, "xizmat 'failed' holatiga tushdi"
        await asyncio.sleep(0.5)
    if up is None:
        return False, None, f"{boot_timeout}s ichida ishga tushmadi"
    end = time.time() + STABLE_SECS
    while time.time() < end:
        await asyncio.sleep(1)
        st, nr = await probe(n)
        if st != "active" or nr > n0:
            return False, up, "ishga tushdi, lekin qulab tushdi (crash/restart loop)"
    return True, up, "ok"


# ───────── ZIP, aniqlash, unit ─────────
def safe_extract(zpath: Path, dest: Path):
    dest.mkdir(parents=True, exist_ok=True)
    root = dest.resolve()
    with zipfile.ZipFile(zpath) as z:
        for i in z.infolist():
            t = (dest / i.filename).resolve()
            if root not in t.parents and t != root:
                raise ValueError(f"Xavfli yo'l: {i.filename}")
        z.extractall(dest)
    shutil.rmtree(dest / "__MACOSX", ignore_errors=True)
    for _ in range(5):  # work/v5/... kabi ichma-ich papkalarni ham ochadi
        items = [p for p in dest.iterdir() if p.name != ".unwrap"]
        if len(items) != 1 or not items[0].is_dir():
            break
        inner = items[0].rename(dest / ".unwrap")
        for p in inner.iterdir(): shutil.move(str(p), dest / p.name)
        inner.rmdir()


def detect(d: Path) -> tuple[str, str, str]:
    custom = (d / "start.cmd").read_text().strip() if (d / "start.cmd").exists() else ""
    if not custom and any((d / f).exists() for f in COMPOSE):
        return "docker", "docker compose up -d --build", ""
    if (d / "package.json").exists():
        run = "npm start" if '"start"' in (d / "package.json").read_text() else "node index.js"
        return "node", "npm install --omit=dev", custom or run
    if (d / "requirements.txt").exists() or any(d.glob("*.py")):
        ins = "python3 -m venv .venv" + (" && .venv/bin/pip install -q -r requirements.txt" if (d / "requirements.txt").exists() else "")
        run = custom or next((f".venv/bin/python {e}" for e in ENTRY if (d / e).exists()), "")
        return "python", ins, run
    if (d / "start.sh").exists():
        return "shell", "chmod +x start.sh", custom or "./start.sh"
    return ("custom" if custom else "unknown"), "", custom


def write_unit(n: str, d: Path, run: str):
    cmd = ("exec " + run).replace("\\", "\\\\").replace('"', '\\"').replace("%", "%%").replace("$", "$$")
    unit_file(n).write_text(
        f"[Unit]\nDescription=App {n}\nAfter=network.target\n\n[Service]\nWorkingDirectory={d}\n"
        f"Environment=PYTHONUNBUFFERED=1\n"
        f'ExecStart=/bin/bash -lc "{cmd}"\nRestart=always\nRestartSec=3\n\n'
        f"[Install]\nWantedBy=multi-user.target\n")


def deps_changed(old: Path, d: Path, kind: str) -> bool:
    for f in ("requirements.txt", "package.json", "package-lock.json"):
        a, b = old / f, d / f
        if a.exists() != b.exists() or (a.exists() and a.read_bytes() != b.read_bytes()):
            return True
    return (kind == "python" and not (d / ".venv").exists()) or (kind == "node" and not (d / "node_modules").exists())


async def launch(n: str, d: Path, install: bool):
    kind, ins, run = detect(d)
    if ins and (install or kind == "docker"):
        code, out = await sh(ins, cwd=d, timeout=900)
        if code: raise RuntimeError("O'rnatishda xato:\n" + out[-1500:])
    if kind == "docker":
        return
    if not run:
        raise RuntimeError("Ishga tushirish fayli topilmadi. ZIP ichiga start.cmd "
                           "(masalan: .venv/bin/python app.py) qo'shing.")
    write_unit(n, d, run)
    await sh(f"systemctl daemon-reload && systemctl enable {unit(n)} && systemctl restart {unit(n)}", timeout=120)


async def wipe(n: str):
    if mode(n) == "docker":
        await dc(n, "down --remove-orphans", 120)
    elif unit_file(n).exists():
        await sh(f"systemctl disable --now {unit(n)}", timeout=120)
        unit_file(n).unlink(missing_ok=True)
        await sh("systemctl daemon-reload", timeout=60)
    await asyncio.to_thread(shutil.rmtree, APPS / n, True)
    await asyncio.to_thread(shutil.rmtree, BACKUPS / n, True)
    try:
        data = json.loads(TIMINGS.read_text()); data.pop(n, None); TIMINGS.write_text(json.dumps(data))
    except Exception:
        pass


# ───────── zaxira ─────────
def load_keep(d: Path) -> set[str]:
    try:
        extra = {l.strip() for l in (d / ".keep").read_text().splitlines() if l.strip() and not l.startswith("#")}
    except OSError:
        extra = set()
    return KEEP | extra


def kept(p: Path, keep: set[str]) -> bool:
    return p.name in keep or bool(DB_RE.search(p.name))


def mirror(src: Path, dst: Path, keep: set[str]):
    for p in list(dst.iterdir()):
        if kept(p, keep): continue
        shutil.rmtree(p) if p.is_dir() and not p.is_symlink() else p.unlink()
    for p in src.iterdir():
        if kept(p, keep) and (dst / p.name).exists(): continue
        if p.is_dir() and not p.is_symlink(): shutil.copytree(p, dst / p.name, symlinks=True)
        else: shutil.copy2(p, dst / p.name, follow_symlinks=False)


def make_backup(d: Path, bak: Path, keep: set[str]):
    def ignore(cur, names):
        top = Path(cur) == d
        return [x for x in names if x in (".git", "__pycache__") or (top and (x in keep or DB_RE.search(x)))]
    bak.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copytree(d, bak, symlinks=True, ignore=ignore)
    except Exception:
        shutil.rmtree(bak, ignore_errors=True)   # yarim nusxa qolmasin
        raise
    prune_backups(bak.parent, bak)


def prune_backups(folder: Path, keep_one: Path | None = None):
    """Har bir ilova uchun FAQAT 1 ta zaxira: eng yangisi qoladi, qolganlari o'chadi."""
    if not folder.is_dir(): return
    items = sorted(p for p in folder.iterdir() if p.is_dir())
    last = keep_one if keep_one and keep_one.exists() else (items[-1] if items else None)
    for old in items:
        if old != last:
            shutil.rmtree(old, ignore_errors=True)


def prune_all_backups():
    """Eski versiyalardan qolgan ortiqcha zaxiralarni tozalaydi (bot ishga tushganda va har 6 soatda)."""
    if not BACKUPS.is_dir(): return
    names = set(app_names())
    for d in BACKUPS.iterdir():
        if not d.is_dir(): continue
        if d.name not in names:               # ilova o'chirilgan — zaxirasi ham kerak emas
            shutil.rmtree(d, ignore_errors=True)
        else:
            prune_backups(d)


def backups(n: str) -> list[Path]:
    return sorted((BACKUPS / n).glob("*")) if (BACKUPS / n).exists() else []


def avg_time(n: str) -> float | None:
    try:
        v = json.loads(TIMINGS.read_text()).get(n, [])
        return sum(v) / len(v) if v else None
    except Exception:
        return None


def save_time(n: str, secs: float):
    try: data = json.loads(TIMINGS.read_text())
    except Exception: data = {}
    data[n] = (data.get(n, []) + [round(secs, 1)])[-5:]
    TIMINGS.write_text(json.dumps(data))


async def restore(n: str, bak: Path) -> tuple[bool, float | None, str]:
    d = APPS / n
    try:
        install = deps_changed(bak, d, detect(d)[0])
        if mode(n) != "docker": await ctl(n, "stop")
        await asyncio.to_thread(mirror, bak, d, load_keep(d))
        await launch(n, d, install)
        return await wait_healthy(n)
    except Exception as e:
        return False, None, str(e)


# ───────── ko'rinish ─────────
async def detail(n: str) -> dict | None:
    if not NAME_RE.match(n) or not (APPS / n).is_dir():
        return None
    st, kind = await state(n), mode(n)
    info = {"name": n, "state": st, "mode": kind or "", "backups": [b.name for b in backups(n)],
            "avg": avg_time(n), "kind": detect(APPS / n)[0], "size": fm.dir_size(APPS / n)}
    if kind == "systemd":
        _, o = await sh(f"systemctl show {unit(n)} -p NRestarts,ActiveEnterTimestamp,MainPID --no-pager", timeout=30)
        kv = dict(l.split("=", 1) for l in o.splitlines() if "=" in l)
        info.update(restarts=kv.get("NRestarts", "0"), pid=kv.get("MainPID", ""),
                    since=kv.get("ActiveEnterTimestamp", "").strip())
    return info


# ───────── job: deploy / update / rollback ─────────
async def deploy_job(j: jobs.Job, zpath: Path, name: str, target: str | None):
    """Yangi deploy yoki mavjud ilovani yangilash (rollback himoyasi bilan)."""
    if target:
        return await update_job(j, zpath, target)
    dest, started = APPS / name, False
    try:
        await asyncio.to_thread(shutil.rmtree, BACKUPS / name, True)
        if dest.exists():
            await wipe(name)
        j.step("ZIP ochilmoqda")
        await asyncio.to_thread(safe_extract, zpath, dest)
        kind = detect(dest)[0]
        j.meta["kind"] = kind
        j.step(f"Kutubxonalar o'rnatilmoqda ({kind})")
        await launch(name, dest, True)
        started = True
        j.step(f"Tekshirilmoqda (~{STABLE_SECS}s)")
        ok, up, why = await wait_healthy(name)
        j.log = await logs(name, 40)
        if not ok:
            return j.finish("bad", why, done=False, up=up, log=j.log, name=name)
        j.finish("ok", done=True, up=up, log=j.log, name=name, kind=kind)
    except asyncio.CancelledError:
        await wipe(name)
        raise
    except Exception as e:
        if not started:
            await wipe(name)
        raise RuntimeError(str(e))


async def update_job(j: jobs.Job, zpath: Path, n: str):
    d = APPS / n
    stage = TMP / f"stage-{uuid.uuid4().hex}"
    bak = BACKUPS / n / time.strftime("%Y%m%d-%H%M%S")
    t_all, phase, up, err, since = time.time(), 0, None, "", ""
    try:
        j.step("ZIP ochilmoqda")
        await asyncio.to_thread(safe_extract, zpath, stage)
        if not any(stage.iterdir()): raise RuntimeError("ZIP bo'sh")
        keep = load_keep(d) | load_keep(stage)
        j.step("Eski kod zaxiralanmoqda")
        await asyncio.to_thread(make_backup, d, bak, keep)
        phase = 1
        if mode(n) != "docker":
            j.step("Xizmat to'xtatilmoqda")
            await ctl(n, "stop")
        j.step("Fayllar almashtirilmoqda")
        await asyncio.to_thread(mirror, stage, d, keep)
        j.step("Kutubxonalar o'rnatilmoqda va ishga tushirilmoqda")
        since = time.strftime("%Y-%m-%d %H:%M:%S")
        await launch(n, d, deps_changed(bak, d, detect(d)[0]))
        j.step(f"Barqarorlik tekshiruvi (~{STABLE_SECS}s)")
        ok, up, why = await wait_healthy(n)
        if not ok: raise RuntimeError(why)
    except Exception as e:
        err = str(e)
    finally:
        shutil.rmtree(stage, ignore_errors=True)
    total = time.time() - t_all
    j.log = await logs(n, 60, since)

    if not err:
        save_time(n, total)
        return j.finish("ok", done=True, up=up, total=round(total, 1), log=j.log,
                        rolled=False, backup=bak.name, since=since)

    head = f"Sabab: {err[:600]}"
    if phase == 0 or not bak.exists():
        return j.finish("bad", err, done=False, log=j.log, rolled=False, reason=head)

    j.step("Eski kodga qaytarilmoqda")
    t1 = time.time()
    ok, _, why2 = await restore(n, bak)
    if ok:
        shutil.rmtree(bak, ignore_errors=True)
        return j.finish("bad", err, done=False, log=j.log, rolled=True, restore_secs=round(time.time() - t1, 1))
    return j.finish("bad", err + " | rollback: " + why2, done=False, log=j.log, rolled=False, reason=why2)


async def rollback_job(j: jobs.Job, n: str):
    baks = backups(n)
    if not baks:
        raise RuntimeError("Zaxira versiya yo'q.")
    bak = baks[-1]
    j.meta["backup"] = bak.name
    j.step(f"{bak.name} tiklanmoqda")
    ok, up, why = await restore(n, bak)
    if ok:
        shutil.rmtree(bak, ignore_errors=True)
    j.log = await logs(n, 30)
    j.finish("ok" if ok else "bad", "" if ok else why, done=ok, up=up, log=j.log, backup=bak.name)


def start_deploy(zpath: Path, name: str, target: str | None = None) -> jobs.Job:
    title = f"{'Yangilanmoqda' if target else 'O‘rnatilmoqda'}: {target or name}"
    return jobs.spawn("deploy", title, lambda j: deploy_job(j, zpath, name, target),
                      est=(avg_time(target) if target else None) or 45,
                      name=target or name, update=bool(target))


def start_rollback(n: str) -> jobs.Job:
    return jobs.spawn("rollback", f"Qaytarilmoqda: {n}", lambda j: rollback_job(j, n), est=40, name=n)


def start_fix(n: str) -> jobs.Job:
    return jobs.spawn("fix", f"AI tahlil: {n}", lambda j: ai_fix_job(j, n), est=25, name=n)


def start_apply(n: str, pid: str) -> jobs.Job:
    return jobs.spawn("apply", f"Tuzatish qo'llanmoqda: {n}", lambda j: apply_fix_job(j, n, pid), est=45, name=n)


# ───────── .env kalitlar ─────────
ENV_LINE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=(.*)$")
KEY_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def env_path(n: str) -> Path:
    return APPS / n / ".env"


def unq(v: str) -> str:
    v = v.strip()
    m = re.match(r'^"((?:[^"\\]|\\.)*)"', v)
    if m: return m[1].replace('\\"', '"').replace("\\\\", "\\")
    m = re.match(r"^'([^']*)'", v)
    if m: return m[1]
    return re.split(r"\s+#", v)[0].strip()


def enq(v: str) -> str:
    if not re.search(r"[\s#\"'\\]", v): return v
    if "'" not in v: return f"'{v}'"
    return '"' + v.replace("\\", "\\\\").replace('"', '\\"') + '"'


def env_read(n: str) -> dict[str, str]:
    try: lines = env_path(n).read_text().splitlines()
    except OSError: return {}
    out = {}
    for l in lines:
        m = ENV_LINE.match(l)
        if m: out[m[1]] = unq(m[2])
    return out


def env_write(n: str, upd: dict[str, str] | None = None, drop: set[str] | frozenset = frozenset()):
    try: lines = env_path(n).read_text().splitlines()
    except OSError: lines = []
    upd, seen, out = dict(upd or {}), set(), []
    for l in lines:
        m = ENV_LINE.match(l)
        k = m[1] if m else None
        if k in drop: continue
        if k in upd:
            if k not in seen: out.append(f"{k}={enq(upd[k])}"); seen.add(k)
            continue
        out.append(l)
    out += [f"{k}={enq(v)}" for k, v in upd.items() if k not in seen]
    env_path(n).write_text("\n".join(out) + "\n")


def env_parse_lines(text: str) -> tuple[dict[str, str], list[str]]:
    """«KALIT=qiymat» matnini ajratadi; (yaroqli, yaroqsiz qatorlar)."""
    upd, bad = {}, []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"): continue
        k, sep, v = re.sub(r"^export\s+", "", line).partition("=")
        if sep and KEY_RE.fullmatch(k.strip()): upd[k.strip()] = unq(v)
        else: bad.append(line.split("=")[0][:30])
    return upd, bad


def mask(v: str) -> str:
    if not v: return ""
    return "•" * len(v) if len(v) <= 4 else v[:2] + "•" * min(len(v) - 4, 8) + v[-2:]


# ───────── AI tuzatish ─────────
FIX_TOOL = {
    "name": "propose_fix",
    "description": "Ilovadagi xatoni tuzatish taklifi: faqat o'zgarishi kerak bo'lgan fayllar (TO'LIQ yangi matn bilan).",
    "input_schema": {"type": "object", "required": ["explanation", "files"], "properties": {
        "explanation": {"type": "string", "description": "O'zbek tilida qisqa izoh: sabab va nima o'zgartirildi"},
        "files": {"type": "array", "items": {"type": "object", "required": ["path", "content"], "properties": {
            "path": {"type": "string", "description": "ilova papkasiga nisbiy yo'l"},
            "content": {"type": "string", "description": "faylning TO'LIQ yangi matni"}}}},
        "pip": {"type": "array", "items": {"type": "string"}},
        "npm": {"type": "array", "items": {"type": "string"}}}},
}
_ai = None


def client():
    global _ai
    if _ai is None:
        from anthropic import AsyncAnthropic
        _ai = AsyncAnthropic(api_key=ANTHROPIC_KEY)
    return _ai


def project_context(d: Path, keep: set[str], log: str) -> str:
    files = []
    for dp, dns, fns in os.walk(d):
        top = Path(dp) == d
        dns[:] = [x for x in dns if x not in (".git", "__pycache__") and not (top and x in keep)]
        files += [p for p in (Path(dp) / f for f in fns)
                  if not (top and p.name in keep) and not DB_RE.search(p.name) and p.is_file()]
    tree = "\n".join(str(p.relative_to(d)) for p in files[:120])
    pri = [p for p in files if p.suffix in {".py", ".js", ".ts", ".json", ".txt", ".sh", ".cmd", ".yml", ".yaml"}]
    pri.sort(key=lambda p: (p.name not in log, p.stat().st_size))
    pick, total = [], 0
    for p in pri:
        left = 45000 - total
        if left < 500: break
        s = p.read_text(errors="replace")[:min(12000, left)]
        pick.append(f"=== {p.relative_to(d)} ===\n{s}"); total += len(s)
    return f"FAYL DARAXTI:\n{tree}\n\nFAYLLAR:\n" + "\n\n".join(pick)


async def ai_fix_job(j: jobs.Job, n: str):
    if not ANTHROPIC_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY .env da yo'q.")
    d = APPS / n
    if not d.is_dir(): raise RuntimeError("Bunday ilova yo'q.")
    j.step("Loglar o'qilmoqda")
    lg = await logs(n, 120)
    j.step("Kod tahlil qilinmoqda")
    ctx = await asyncio.to_thread(project_context, d, load_keep(d), lg)
    prompt = (f"Ilova '{n}' Ubuntu serverda {mode(n) or 'systemd'} orqali ishlamoqda va muammo bor.\n\nLOG:\n{lg[-8000:]}\n\n{ctx}\n\n"
              "Xatoning sababini toping va minimal tuzatish bering (propose_fix). Faqat o'zgarishi shart bo'lgan fayllarni yuboring.")
    resp = await client().messages.create(
        model=AI_MODEL, max_tokens=8000, tools=[FIX_TOOL], tool_choice={"type": "tool", "name": "propose_fix"},
        messages=[{"role": "user", "content": prompt}])
    if resp.stop_reason == "max_tokens":
        raise RuntimeError("javob juda uzun bo'ldi, tuzatish kesilib qoldi")
    data = next((b.input for b in resp.content if b.type == "tool_use"), None)
    if data is None:
        raise RuntimeError("AI tuzatish taklif qilmadi")
    for k in [k for k, v in PENDING.items() if time.time() - v["t"] > 3600]:
        PENDING.pop(k, None)
    pid = uuid.uuid4().hex[:8]
    PENDING[pid] = {"name": n, "t": time.time(), **data}
    j.finish("ok", explanation=data.get("explanation", ""), files=[f["path"] for f in data.get("files", [])],
             pip=data.get("pip") or [], npm=data.get("npm") or [], pid=pid, log=lg[-2000:])


async def apply_fix_job(j: jobs.Job, n: str, pid: str):
    p = PENDING.pop(pid, None)
    if not p:
        raise RuntimeError("Taklif eskirgan — AI tahlilni qaytadan boshlang.")
    d = (APPS / n).resolve()
    keep = load_keep(d)
    j.step("Zaxira yaratilmoqda")
    bak = BACKUPS / n / time.strftime("%Y%m%d-%H%M%S")
    await asyncio.to_thread(make_backup, d, bak, keep)
    j.step("Fayllar yozilmoqda")
    skipped = []
    for f in p.get("files", []):
        t = (d / f["path"]).resolve()
        if d not in t.parents or t.relative_to(d).parts[0] in keep or DB_RE.search(t.name):
            skipped.append(f["path"]); continue
        t.parent.mkdir(parents=True, exist_ok=True); t.write_text(f["content"])
    out = ""
    pk = [x for x in p.get("pip", []) if PKG_RE.fullmatch(x)]
    nk = [x for x in p.get("npm", []) if NPM_RE.fullmatch(x)]
    if pk and (d / ".venv").exists():
        out += (await sh(f".venv/bin/pip install -q {' '.join(map(q, pk))}", cwd=d, timeout=600))[1][-800:]
    if nk and (d / "package.json").exists():
        out += (await sh(f"npm install {' '.join(map(q, nk))}", cwd=d, timeout=600))[1][-800:]
    j.step("Qayta ishga tushirilmoqda")
    if mode(n) == "docker": await dc(n, "up -d --build", 900)
    else: await ctl(n, "restart")
    ok, _, why = await wait_healthy(n)
    j.log = out + await logs(n, 20)
    j.finish("ok" if ok else "bad", "" if ok else why, done=ok, skipped=skipped, backup=bak.name, log=j.log)
