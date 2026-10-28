"""Bot: ilovalar, ZIP deploy, .env kalitlar, AI tuzatish — appctl yadrosi ustida."""
import asyncio, time
from pathlib import Path

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

import appctl, filesvc as fm, jobs
from common import APPS, NAME_RE, TMP, B, K, edit, esc, pre

router = Router()
FSTATE: dict[int, dict] = {}   # uid -> {"kind": "upd"|"envadd"|"envset", "path": n, "key": k}
ICON = {"active": "🟢", "activating": "🟡", "failed": "🔴"}


def cancel_all():
    for j in list(jobs.JOBS.values()):
        if j.state == "run" and j.task and not j.task.done():
            j.task.cancel()


# ───────── ro'yxat / karta ─────────
async def apps_view() -> tuple[str, object]:
    names = appctl.app_names()
    if not names:
        return "Hali ilova yo'q. ZIP yuboring 📦", K([[B("⬅️ Menyu", "menu"), B("❌ Yopish", "x")]])
    sts = await appctl.states(names)
    rows, row = [], []
    for n, st in zip(names, sts):
        row.append(B(f"{ICON.get(st, '⚪')} {n}", f"app:{n}"))
        if len(row) == 2: rows.append(row); row = []
    if row: rows.append(row)
    rows.append([B("🔄", "apps"), B("⬅️ Menyu", "menu"), B("❌ Yopish", "x")])
    return "📦 <b>Ilovalar</b>", K(rows)


async def show_app(msg: Message, n: str, note: str = ""):
    d = await appctl.detail(n)
    if not d:
        return await edit(msg, "Bunday ilova yo'q.", K([[B("⬅️ Ilovalar", "apps")]]))
    extra = ""
    if d["mode"] == "systemd":
        extra = f" · restart {d.get('restarts', 0)}"
    await edit(msg, f"{ICON.get(d['state'], '⚪')} <b>{esc(n)}</b> — {d['state']} ({d['mode'] or 'boshqarilmaydi'}, {d['kind']}){extra}\n"
                    f"📦 {d['size'] / 1024**2:.1f}MB · Zaxira: {len(d['backups'])} ta{note}", K([
        [B("▶️ Start", f"do:{n}:start"), B("⏹ Stop", f"do:{n}:stop"), B("🔄 Restart", f"do:{n}:restart")],
        [B("📜 Log", f"do:{n}:logs"), B("🤖 AI fix", f"do:{n}:fix"), B("⬆️ ZIP yangilash", f"do:{n}:upd")],
        [B("↩️ Oldingi versiya", f"do:{n}:rollback"), B("📁 Fayllar", f"f:d:{fm.tid(APPS / n)}:0"), B("🗑 O'chirish", f"do:{n}:delete")],
        [B("🔑 Kalitlar (.env)", f"ev:{n}:0")],
        [B("⬅️ Ilovalar", "apps"), B("❌ Yopish", "x")]]))


@router.message(Command("apps"))
async def cmd_apps(m: Message):
    text, kb = await apps_view()
    await m.answer(text, reply_markup=kb)


@router.callback_query(F.data == "apps")
async def cb_apps(c: CallbackQuery):
    text, kb = await apps_view()
    await edit(c.message, text, kb)


@router.callback_query(F.data.startswith("app:"))
async def cb_app(c: CallbackQuery):
    n = c.data[4:]
    st = FSTATE.get(c.from_user.id)
    if st and st["kind"] in ("upd", "envadd", "envset"):
        FSTATE.pop(c.from_user.id, None)
    await show_app(c.message, n)


@router.callback_query(F.data.startswith("do:"))
async def cb_do(c: CallbackQuery):
    _, n, a = c.data.split(":")
    if not (APPS / n).is_dir():
        return await edit(c.message, "Bunday ilova yo'q.", K([[B("⬅️ Ilovalar", "apps")]]))
    if a in {"start", "stop", "restart"}:
        code, out = await appctl.ctl(n, a)
        await asyncio.sleep(1)
        await show_app(c.message, n, f"\n{'✅' if not code else '⚠️'} {a}" + (pre(out, 400) if code else ""))
    elif a == "logs":
        await edit(c.message, f"📜 <b>{esc(n)}</b>\n{pre(await appctl.logs(n, 80))}",
                   K([[B("🔄", f"do:{n}:logs"), B("⬅️ Ilova", f"app:{n}"), B("❌ Yopish", "x")]]))
    elif a == "fix":
        await run_job(c.message, appctl.start_fix(n))
    elif a == "upd":
        FSTATE[c.from_user.id] = {"kind": "upd", "path": n}
        await edit(c.message, f"📦 <b>{esc(n)}</b> uchun yangi ZIP faylni yuboring.", K([[B("❌ Bekor", f"app:{n}")]]))
    elif a == "rollback":
        bs = appctl.backups(n)
        if not bs:
            return await edit(c.message, "Zaxira versiya yo'q.", K([[B("⬅️ Ilova", f"app:{n}")]]))
        await edit(c.message, f"↩️ <b>{esc(n)}</b> → <code>{bs[-1].name}</code> versiyasiga qaytarilsinmi?\n"
                              "(Hozirgi kod almashtiriladi; baza va .env tegilmaydi.)",
                   K([[B("✅ Ha, qaytarish", f"rbky:{n}"), B("❌ Bekor", f"app:{n}")]]))
    elif a == "delete":
        await edit(c.message, f"🗑 <b>{esc(n)}</b> butunlay o'chirilsinmi? (xizmat/konteyner + fayllar + zaxiralar)",
                   K([[B("✅ Ha, o'chirish", f"dely:{n}"), B("❌ Bekor", f"app:{n}")]]))


@router.callback_query(F.data.startswith("dely:"))
async def cb_dely(c: CallbackQuery):
    n = c.data[5:]
    if not NAME_RE.match(n) or not (APPS / n).is_dir(): return
    await appctl.wipe(n)
    await edit(c.message, f"🗑 {esc(n)} o'chirildi", K([[B("⬅️ Ilovalar", "apps")]]))


@router.callback_query(F.data.startswith("rbky:"))
async def cb_rbky(c: CallbackQuery):
    n = c.data[5:]
    if not NAME_RE.match(n) or not (APPS / n).is_dir(): return
    if not appctl.backups(n):
        return await edit(c.message, "Zaxira versiya yo'q.", K([[B("⬅️ Ilova", f"app:{n}")]]))
    await run_job(c.message, appctl.start_rollback(n))


# ───────── job progressini xabarda ko'rsatish ─────────
def render_job(j: jobs.Job) -> str:
    s = j.snap()
    done = "\n".join(f"✅ {esc(x['text'])} <i>({x['secs']}s)</i>" for x in s["steps"])
    cur = f"\n⏳ {esc(s['cur'])}…" if s["cur"] else ""
    if s["state"] == "run":
        tail = f"\n\n{_bar(s['pct'])}\n⏱ {s['elapsed']:.0f}s o'tdi · " + (f"~{s['remain']}s qoldi" if s["remain"] > 1 else "tez orada tugaydi…")
    else:
        tail = f"\n\n⏱ Jami: <b>{s['elapsed']:.0f}s</b>"
    return f"<b>{esc(s['title'])}</b>\n{done}{cur}{tail}"


def _bar(p: float) -> str:
    from config import bar
    return bar(p)


async def run_job(msg: Message, j: jobs.Job) -> jobs.Job:
    """Job tugaguncha xabarni yangilab turadi (bekor qilish tugmasi bilan)."""
    stop = asyncio.Event()

    async def pump():
        while not stop.is_set():
            try:
                if j.state != "run":
                    break
                await msg.edit_text(render_job(j), reply_markup=K([[B("❌ Bekor qilish", f"cn:{j.id}")]]))
            except Exception:
                pass
            await asyncio.sleep(2)

    t = asyncio.create_task(pump())
    await jobs.wait(j.id, 1800)
    stop.set()
    try: await t
    except Exception: pass
    await final_msg(msg, j)
    return j


async def final_msg(msg: Message, j: jobs.Job):
    s, r = j.snap(), j.snap()["result"]
    n = s["meta"].get("name", "")
    if s["kind"] == "deploy":
        if s["state"] == "ok":
            return await edit(msg, f"✅ {'Yangilandi' if s['meta'].get('update') else 'Ishlayapti'}: <b>{esc(n)}</b>"
                                   + (f" — {r['up']:.1f}s" if r.get("up") else "")
                                   + (f"\n⏱ Jami: {r['total']}s · Barqarorlik: o'tdi" if r.get("total") else "")
                                   + f"\n{pre(s['log'], 1500)}",
                              K([[B("📜 Log", f"do:{n}:logs"), B("📦 Ilova", f"app:{n}")], [B("❌ Yopish", "x")]]))
        rolled = "↩️ Eski kod tiklandi va ishlayapti" if r.get("rolled") else ""
        return await edit(msg, f"{'⏹ Bekor qilindi' if s['state'] == 'cancel' else '❌ Ishlamadi'}: <b>{esc(n)}</b>\n"
                               f"Sabab: {esc(s['error'][:500])}\n{rolled}\n{pre(s['log'], 1800)}",
                          K([[B("🤖 AI fix", f"do:{n}:fix"), B("📜 Log", f"do:{n}:logs")], [B("📦 Ilova", f"app:{n}")]]))
    if s["kind"] == "rollback":
        return await edit(msg, f"{'✅ Qaytarildi' if s['state'] == 'ok' else '❌ ' + esc(s['error'])} — {esc(r.get('backup', ''))}\n"
                               f"{pre(s['log'], 1800)}", K([[B("📜 Log", f"do:{n}:logs"), B("📦 Ilova", f"app:{n}")]]))
    if s["kind"] == "fix":
        if s["state"] != "ok":
            return await edit(msg, f"AI xatosi: {esc(s['error'])}", K([[B("⬅️ Ilova", f"app:{n}")]]))
        txt = f"🤖 <b>Tahlil</b>\n{esc(r.get('explanation', ''))}"
        if not r.get("files") and not r.get("pip") and not r.get("npm"):
            return await edit(msg, txt + "\n\nKodni o'zgartirish kerak emas.", K([[B("⬅️ Ilova", f"app:{n}")]]))
        return await edit(msg, f"{txt}\n\nFayllar: <code>{esc(', '.join(r['files']) or '—')}</code>\n"
                               f"Paketlar: {esc(str(r.get('pip') or r.get('npm') or '—'))}",
                          K([[B("✅ Qo'llash", f"ai:{r['pid']}:yes"), B("❌ Bekor", f"app:{n}")]]))
    if s["kind"] == "apply":
        note = f"\n⚠️ O'tkazib yuborildi: <code>{esc(', '.join(r.get('skipped', [])))}</code>" if r.get("skipped") else ""
        return await edit(msg, f"{'✅ Ishlayapti' if s['state'] == 'ok' else '❌ ' + esc(s['error'])}: <b>{esc(n)}</b>{note}\n"
                               f"(zaxira: <code>{esc(r.get('backup', ''))}</code>)\n{pre(s['log'], 1500)}",
                          K([[B("📜 Log", f"do:{n}:logs"), B("↩️ Oldingi versiya", f"do:{n}:rollback")], [B("📦 Ilova", f"app:{n}")]]))
    await edit(msg, render_job(j))


@router.callback_query(F.data.startswith("cn:"))
async def cb_cn(c: CallbackQuery):
    jobs.cancel(c.data[3:])


# ───────── ZIP qabul qilish ─────────
@router.message(F.document)
async def on_zip(m: Message):
    doc, uid = m.document, m.from_user.id
    if not (doc.file_name or "").lower().endswith(".zip"):
        return await m.answer("Faqat .zip fayl qabul qilinadi.")
    if doc.file_size and doc.file_size > 20 * 1024 * 1024:
        return await m.answer("⚠️ Telegram Bot API 20MB dan katta faylni bermaydi. Kichraytiring yoki local Bot API server ishlating.")
    import re
    name = re.sub(r"[^a-zA-Z0-9_.-]", "-", Path(doc.file_name).stem).lstrip(".-")[:50] or "app"
    cap = (m.caption or "").split()
    st = FSTATE.get(uid)
    target = st["path"] if st and st["kind"] == "upd" else None
    if target: FSTATE.pop(uid, None)
    if len(cap) == 2 and cap[0] == "/update" and NAME_RE.match(cap[1]):
        target = cap[1]
    elif not target and appctl.mode(name):
        target = name
    if target and not appctl.mode(target):
        return await m.answer("Bunday ilova yo'q yoki u boshqarilmaydi.")
    msg = await m.answer(f"⬇️ <b>{esc(target or name)}</b> yuklanmoqda...")
    zpath = TMP / f"{__import__('uuid').uuid4().hex}.zip"
    await m.bot.download(doc, destination=zpath)
    j = appctl.start_deploy(zpath, name, target)
    await run_job(msg, j)


@router.message(Command("update"))
async def cmd_update(m: Message):
    a = (m.text or "").split()
    if len(a) != 2 or not NAME_RE.match(a[1]) or not appctl.mode(a[1]):
        return await m.answer("Format: <code>/update nom</code> (nom — /apps dagi ilova)")
    FSTATE[m.from_user.id] = {"kind": "upd", "path": a[1]}
    await m.answer(f"📦 <b>{esc(a[1])}</b> uchun yangi ZIP faylni yuboring.")


@router.message(Command("rollback"))
async def cmd_rollback(m: Message):
    a = (m.text or "").split()
    if len(a) != 2 or not NAME_RE.match(a[1]) or not appctl.mode(a[1]):
        return await m.answer("Format: <code>/rollback nom</code>")
    await run_job(await m.answer("↩️ …"), appctl.start_rollback(a[1]))


@router.message(Command("fix"))
async def cmd_fix(m: Message):
    a = (m.text or "").split()
    if len(a) != 2 or not NAME_RE.match(a[1]): return await m.answer("Format: <code>/fix nom</code>")
    await run_job(await m.answer("🤖 …"), appctl.start_fix(a[1]))


@router.callback_query(F.data.startswith("ai:"))
async def cb_ai(c: CallbackQuery):
    _, pid, ans = c.data.split(":")
    n = appctl.PENDING.get(pid, {}).get("name", "")
    if ans == "no" or not n:
        return await edit(c.message, "Bekor qilindi.")
    await run_job(c.message, appctl.start_apply(n, pid))


# ───────── .env kalitlar ─────────
ENV_PAGE = 8


def env_list_view(n: str, page: int = 0, note: str = ""):
    env = appctl.env_read(n)
    keys = list(env)
    pages = max(1, -(-len(keys) // ENV_PAGE))
    page = min(max(page, 0), pages - 1)
    rows = [[B(f"{k} = {appctl.mask(env[k])}"[:60], f"ek:{n}:{k}")] for k in keys[page * ENV_PAGE:(page + 1) * ENV_PAGE]]
    if pages > 1:
        rows.append([B("◀️", f"ev:{n}:{page - 1}") if page else B("·", f"ev:{n}:{page}"), B(f"{page + 1}/{pages}", f"ev:{n}:{page}"),
                     B("▶️", f"ev:{n}:{page + 1}") if page < pages - 1 else B("·", f"ev:{n}:{page}")])
    rows.append([B("➕ Qo'shish", f"ea:{n}"), B("🔄 Restart (qo'llash)", f"er:{n}")])
    rows.append([B("⬅️ Ilova", f"app:{n}"), B("❌ Yopish", "x")])
    text = (f"{note}🔑 <b>{esc(n)}</b> — kalitlar ({len(keys)})\nIlovaning <code>.env</code> fayli. "
            "O'zgarish ilova qayta ishga tushgach kuchga kiradi." + ("\n\n(hozircha bo'sh)" if not keys else ""))
    return text, K(rows)


def env_key_view(n: str, k: str, show: bool = False, note: str = ""):
    v = appctl.env_read(n).get(k, "")
    from urllib.parse import quote
    h = quote(k, safe="")
    text = f"{note}🔑 <b>{esc(n)}</b> · <code>{esc(k)}</code>\nQiymat: <code>{esc(v if show else appctl.mask(v))}</code>"
    return text, K([[B("🙈 Yashirish" if show else "👁 Ko'rsatish", f"ek:{n}:{h}" + ("" if show else ":1")),
                     B("✏️ Tahrirlash", f"ee:{n}:{h}"), B("🗑 O'chirish", f"ed:{n}:{h}")],
                    [B("⬅️ Kalitlar", f"ev:{n}:0"), B("❌ Yopish", "x")]])


def _k(c: CallbackQuery) -> tuple[str, str]:
    """callback_data: <op>:<app>:<urlencoded key>[:flag]"""
    from urllib.parse import unquote
    p = c.data.split(":")
    return p[1], (unquote(p[2]) if len(p) > 2 else "")


@router.callback_query(F.data.startswith("ev:"))
async def cb_ev(c: CallbackQuery):
    n, page = _k(c)
    st = FSTATE.get(c.from_user.id)
    if st and st["kind"] in ("envadd", "envset"):
        FSTATE.pop(c.from_user.id, None)
    if not (APPS / n).is_dir():
        return await edit(c.message, "Bunday ilova yo'q.", K([[B("⬅️ Ilovalar", "apps")]]))
    text, kb = env_list_view(n, int(page) if page.lstrip("-").isdigit() else 0)
    await edit(c.message, text, kb)


@router.callback_query(F.data.startswith("ek:"))
async def cb_ek(c: CallbackQuery):
    n, k = _k(c)
    if not (APPS / n).is_dir(): return await edit(c.message, "Bunday ilova yo'q.")
    if not k or k not in appctl.env_read(n):
        text, kb = env_list_view(n, note="Bu kalit endi yo'q.\n\n")
    else:
        FSTATE.pop(c.from_user.id, None)
        text, kb = env_key_view(n, k, show=c.data.endswith(":1"))
    await edit(c.message, text, kb)


@router.callback_query(F.data.startswith("ea:"))
async def cb_ea(c: CallbackQuery):
    n = c.data[3:]
    if not (APPS / n).is_dir(): return await edit(c.message, "Bunday ilova yo'q.")
    FSTATE[c.from_user.id] = {"kind": "envadd", "path": n}
    await edit(c.message, f"➕ <b>{esc(n)}</b> uchun yangi kalit yozing:\n<code>KALIT=qiymat</code>\n"
                          "Bir nechta qatorni birdaniga yuborish mumkin (mavjud kalit yangilanadi).\n"
                          "Xabaringiz o'qilgach chatdan o'chiriladi.", K([[B("❌ Bekor", f"ev:{n}:0")]]))


@router.callback_query(F.data.startswith("ee:"))
async def cb_ee(c: CallbackQuery):
    from urllib.parse import quote
    n, k = _k(c)
    if not (APPS / n).is_dir() or k not in appctl.env_read(n):
        return await edit(c.message, "Bu kalit endi yo'q.", K([[B("⬅️ Kalitlar", f"ev:{n}:0")]]))
    FSTATE[c.from_user.id] = {"kind": "envset", "path": n, "key": k}
    await edit(c.message, f"✏️ <code>{esc(k)}</code> uchun yangi qiymatni yozing.\nXabaringiz o'qilgach chatdan o'chiriladi.",
               K([[B("❌ Bekor", f"ek:{n}:{quote(k, safe='')}")]]))


@router.callback_query(F.data.startswith("ed:"))
async def cb_ed(c: CallbackQuery):
    from urllib.parse import quote
    n, k = _k(c)
    if not (APPS / n).is_dir() or k not in appctl.env_read(n):
        return await edit(c.message, "Bu kalit endi yo'q.", K([[B("⬅️ Kalitlar", f"ev:{n}:0")]]))
    q = quote(k, safe="")
    await edit(c.message, f"🗑 <code>{esc(k)}</code> o'chirilsinmi?",
               K([[B("✅ Ha, o'chirish", f"edy:{n}:{q}"), B("❌ Bekor", f"ek:{n}:{q}")]]))


@router.callback_query(F.data.startswith("edy:"))
async def cb_edy(c: CallbackQuery):
    n, k = _k(c)
    if (APPS / n).is_dir() and k:
        appctl.env_write(n, drop={k})
    text, kb = env_list_view(n, note=f"🗑 <code>{esc(k)}</code> o'chirildi\n\n")
    await edit(c.message, text, kb)


@router.callback_query(F.data.startswith("er:"))
async def cb_er(c: CallbackQuery):
    n = c.data[3:]
    if not (APPS / n).is_dir(): return await edit(c.message, "Bunday ilova yo'q.")
    if not appctl.mode(n):
        text, kb = env_list_view(n, note="⚠️ Bu ilova boshqarilmaydi (systemd/docker yo'q).\n\n")
        return await edit(c.message, text, kb)
    await edit(c.message, f"⏳ <b>{esc(n)}</b> qayta ishga tushirilmoqda…")
    if appctl.mode(n) == "docker": await appctl.dc(n, "up -d", 300)
    else: await appctl.ctl(n, "restart")
    ok, _, why = await appctl.wait_healthy(n)
    text, kb = env_list_view(n, note=("✅ Qayta ishga tushdi, yangi qiymatlar ishlayapti\n\n" if ok else f"❌ {esc(why)} — /fix {n}\n\n"))
    await edit(c.message, text, kb)


@router.message(F.text & ~F.text.startswith("/"))
async def on_env_text(m: Message):
    uid = m.from_user.id
    s = FSTATE.get(uid)
    if not s or s["kind"] not in ("envadd", "envset"):
        return
    n = s["path"]
    try: await m.delete()
    except Exception: pass
    if s["kind"] == "envset":
        if "\n" in m.text.strip():
            return await m.answer("❌ Qiymat bitta qatorda bo'lishi kerak. Qayta yozing:")
        upd, bad = {s["key"]: m.text.strip()}, []
    else:
        upd, bad = appctl.env_parse_lines(m.text)
        if not upd:
            return await m.answer("❌ Format: <code>KALIT=qiymat</code> (kalit harf/raqam/_ dan iborat, raqam bilan boshlanmasin). Qayta yozing:")
    old = appctl.env_read(n)
    appctl.env_write(n, upd)
    FSTATE.pop(uid, None)
    names = ", ".join(f"<code>{esc(k)}</code>" for k in upd)
    note = (f"✅ {'Yangilandi' if all(k in old for k in upd) else 'Saqlandi'}: {names}\n"
            + (f"⚠️ O'qib bo'lmadi: {esc(', '.join(bad))}\n" if bad else "") + "\n")
    text, kb = env_list_view(n, note=note)
    await m.answer(text, reply_markup=kb)
