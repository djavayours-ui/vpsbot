"""Bot: fayl menejeri — filesvc yadrosi ustida (ko'rish, yuklab olish, almashtirish, savat, nusxa)."""
import asyncio, os, shutil, time, uuid
from pathlib import Path

from aiogram import F, Router
from aiogram.filters import BaseFilter, Command, CommandObject
from aiogram.types import CallbackQuery, FSInputFile, Message

import filesvc as fm
from common import APPS, K, TMP, B, edit, esc, pre, q, sh

router = Router()
PAGE, MAX_SEND, MAX_DL = 10, 49 * 1024 * 1024, 20 * 1024 * 1024
FSTATE: dict[int, dict] = {}
CLIP: dict[int, tuple[str, str]] = {}


def short(s: str, n: int = 30) -> str:
    return s if len(s) <= n else s[:n - 1] + "…"


def render_roots():
    items = [("📦 Ilovalar", APPS), ("🏠 /root", Path("/root")), ("📜 /var/log", Path("/var/log")),
             ("⚙️ /etc", Path("/etc")), ("🌐 /var/www", Path("/var/www")), ("📁 /", Path("/")), ("🗑 Savat", fm.TRASH)]
    rows, row = [], []
    for t, p in items:
        if p.exists():
            row.append(B(t, f"f:d:{fm.tid(p)}:0"))
            if len(row) == 2: rows.append(row); row = []
    if row: rows.append(row)
    rows.append([B("⬅️ Menyu", "menu"), B("❌ Yopish", "x")])
    return "📁 <b>Fayl menejeri</b>\nPapkani tanlang:", K(rows)


def render_dir(uid: int, p: Path, page: int = 0, note: str = ""):
    pk = fm.tid(p)
    up = [B("⬆️ Yuqoriga", f"f:d:{fm.tid(p.parent)}:0")] if str(p) != "/" else []
    sc = fm.scan(p)
    if sc is None:
        return f"{note}⛔ Ochib bo'lmadi: <code>{esc(str(p))}</code>", K([up + [B("🏠 Ildizlar", "f:r")]])
    dirs, files = sc
    allx = dirs + files
    pages = max(1, -(-len(allx) // PAGE))
    page = min(max(page, 0), pages - 1)
    rows = []
    for e in allx[page * PAGE:(page + 1) * PAGE]:
        k = fm.tid(e.path)
        try: isd = e.is_dir()
        except OSError: isd = False
        if isd:
            rows.append([B(f"📁 {short(e.name)}", f"f:d:{k}:0")])
        else:
            try: sz = fm.hsize(e.stat().st_size)
            except OSError: sz = "?"
            rows.append([B(f"📄 {short(e.name, 24)} · {sz}", f"f:v:{k}")])
    if pages > 1:
        rows.append([B("◀️", f"f:d:{pk}:{page - 1}") if page > 0 else B("·", f"f:d:{pk}:{page}"),
                     B(f"{page + 1}/{pages}", f"f:d:{pk}:{page}"),
                     B("▶️", f"f:d:{pk}:{page + 1}") if page < pages - 1 else B("·", f"f:d:{pk}:{page}")])
    rows.append([B("⬆️ Yuklash", f"f:up:{pk}"), B("📁 Yangi papka", f"f:mk:{pk}")])
    rows.append([B("⚙️ Papka amallari", f"f:v:{pk}"), B("🔄 Yangilash", f"f:d:{pk}:{page}")])
    if uid in CLIP:
        mode, src = CLIP[uid]
        rows.append([B(f"📥 Qo'yish: {short(Path(src).name, 18)}", f"f:ps:{pk}"), B("🧹 Bufer", f"f:cc:{pk}")])
    rows.append(up + [B("🏠 Ildizlar", "f:r"), B("❌ Yopish", "x")])
    text = (f"{note}📂 <code>{esc(str(p))}</code>\n{len(dirs)} papka · {len(files)} fayl"
            + (f" · sahifa {page + 1}/{pages}" if pages > 1 else "") + ("\n(bo'sh)" if not allx else ""))
    return text, K(rows)


def render_item(uid: int, p: Path, note: str = "", preview: bool = True):
    k, pk = fm.tid(p), fm.tid(p.parent)
    try: st = p.lstat()
    except OSError as e:
        return f"❌ {esc(str(e))}", K([[B("⬆️ Papkaga", f"f:d:{pk}:0")]])
    isd = p.is_dir()
    try:
        import pwd
        owner = pwd.getpwuid(st.st_uid).pw_name
    except Exception:
        owner = str(st.st_uid)
    text = (f"{note}{'📁' if isd else '📄'} <b>{esc(p.name or '/')}</b>\n<code>{esc(str(p))}</code>\n"
            f"{oct(st.st_mode & 0o777)[2:]} · {owner} · {time.strftime('%Y-%m-%d %H:%M', time.localtime(st.st_mtime))}")
    rows = []
    if isd:
        rows += [[B("📂 Ochish", f"f:d:{k}:0"), B("📦 ZIP yuklab olish", f"f:get:{k}")],
                 [B("✏️ Nomi", f"f:rn:{k}"), B("📏 Hajm", f"f:du:{k}")]]
    else:
        text += f" · {fm.hsize(st.st_size)}"
        if preview and st.st_size <= 2_000_000 and fm.is_text(p):
            try: text += "\n" + pre(p.read_text(errors="replace")[:2500], 2500)
            except OSError: pass
        rows += [[B("⬇️ Yuklab olish", f"f:get:{k}"), B("🔁 Almashtirish", f"f:rp:{k}")],
                 [B("✏️ Nomi", f"f:rn:{k}"), B("⏬ Oxiri (tail)", f"f:tl:{k}")]]
        a = fm.app_of(p)
        if a: rows.append([B(f"🔄 Restart {short(a, 16)}", f"do:{a}:restart")])
    rows += [[B("📋 Nusxa", f"f:cp:{k}"), B("✂️ Ko'chirish", f"f:mv:{k}"), B("🗑 O'chirish", f"f:rm:{k}")],
             [B("⬅️ Papkaga", f"f:d:{pk}:0"), B("❌ Yopish", "x")]]
    return text, K(rows)


def show(uid, p: Path, note=""):
    return render_dir(uid, p, 0, note) if p.is_dir() else render_item(uid, p, note)


def replace_file(p: Path, new: Path):
    fm.copy_to_trash(p, suffix=".replaced")
    shutil.copyfile(new, p)   # joyida yoziladi — egasi va ruxsatlari saqlanadi


# ───────── buyruqlar ─────────
@router.message(Command("files"))
async def cmd_files(m: Message, command: CommandObject):
    FSTATE.pop(m.from_user.id, None)
    arg = (command.args or "").strip()
    if not arg:
        text, k = render_roots()
    else:
        p = Path(arg)
        if not p.exists(): return await m.answer("❌ Topilmadi")
        text, k = show(m.from_user.id, p)
    await m.answer(text, reply_markup=k)


@router.callback_query(F.data == "fm")
async def cb_fm(c: CallbackQuery):
    FSTATE.pop(c.from_user.id, None)
    text, k = render_roots()
    await edit(c.message, text, k)


@router.callback_query(F.data.startswith("f:"), ~F.data.startswith("f:undo:"))
async def cb_f(c: CallbackQuery):
    uid = c.from_user.id
    parts = c.data.split(":")
    op, k = parts[1], (parts[2] if len(parts) > 2 else "")
    if op == "r":
        text, kb = render_roots(); return await edit(c.message, text, kb)
    p = fm.P(k)
    if p is None:
        text, kb = render_roots()
        return await edit(c.message, "⌛ Ro'yxat eskirgan, qaytadan oching.\n\n" + text, kb)

    if op == "d":
        page = int(parts[3]) if len(parts) > 3 else 0
        text, kb = render_dir(uid, p, page)
        return await edit(c.message, text, kb)
    if op == "v":
        text, kb = show(uid, p); return await edit(c.message, text, kb)
    if op == "cx":
        FSTATE.pop(uid, None)
        text, kb = show(uid, p) if p.exists() else render_roots()
        return await edit(c.message, "❌ Bekor qilindi\n\n" + text, kb)

    if op == "tl":
        try: t = await asyncio.to_thread(fm.tail, p)
        except OSError as e: t = f"❌ {e}"
        return await edit(c.message, f"⏬ <b>{esc(p.name)}</b> (oxiri)\n{pre(t)}",
                          K([[B("🔄", f"f:tl:{k}"), B("⬅️ Orqaga", f"f:v:{k}")]]))
    if op == "du":
        _, out = await sh(f"du -sh -- {q(str(p))} 2>/dev/null | cut -f1", timeout=60)
        text, kb = render_item(uid, p, f"📏 Hajm: <b>{esc(out.strip() or '?')}</b>\n")
        return await edit(c.message, text, kb)
    if op == "get":
        wait = await c.message.answer("⏳ Tayyorlanmoqda…")
        try:
            if p.is_dir():
                out = TMP / f"{uuid.uuid4().hex[:8]}-{p.name}.zip"
                await asyncio.to_thread(fm.zip_dir, p, out)
                src, rm = out, True
            else: src, rm = p, False
            sz = src.stat().st_size
            if sz == 0: await c.message.answer("Fayl bo'sh — Telegram bo'sh faylni yubormaydi.")
            elif sz > MAX_SEND: await c.message.answer(f"⚠️ {fm.hsize(sz)} — Telegram limiti 50MB dan katta.")
            else: await c.message.answer_document(FSInputFile(src, filename=src.name))
            if rm: src.unlink(missing_ok=True)
        except Exception as e:
            await c.message.answer(f"❌ {esc(str(e))}")
        finally:
            await wait.delete()
        return

    if op in ("rn", "rp", "mk", "up"):
        if op == "rn":
            g = fm.guard(p)
            if g: return await edit(c.message, f"⛔ {g}", K([[B("⬅️ Orqaga", f"f:v:{k}")]]))
            msg, back = f"✏️ <b>{esc(p.name)}</b> uchun yangi nomni yozing:", k
        elif op == "rp":
            msg, back = f"🔁 <b>{esc(p.name)}</b> o'rniga yangi faylni <b>hujjat</b> sifatida yuboring.\nEski fayl savatga zaxiralanadi.", k
        elif op == "mk":
            msg, back = f"📁 <code>{esc(str(p))}</code> ichida yangi papka nomini yozing:", k
        else:
            msg, back = f"⬆️ <code>{esc(str(p))}</code> ga fayl(lar)ni hujjat sifatida yuboring (limit 20MB).", k
        FSTATE[uid] = {"kind": {"rn": "ren", "rp": "rep"}.get(op, op), "path": str(p)}
        return await edit(c.message, msg, K([[B("❌ Bekor", f"f:cx:{back}")]]))

    if op == "rm":
        g = fm.guard(p)
        if g: return await edit(c.message, f"⛔ {g}", K([[B("⬅️ Orqaga", f"f:v:{k}")]]))
        extra = "\n⚠️ Papka ichidagi hamma narsa bilan." if p.is_dir() else ""
        return await edit(c.message, f"🗑 <b>{esc(p.name)}</b> o'chirilsinmi?{extra}\n(Savatga o'tadi, 7 kun saqlanadi)",
                          K([[B("✅ Ha, o'chirish", f"f:rmy:{k}"), B("❌ Bekor", f"f:v:{k}")]]))
    if op == "rmy":
        g = fm.guard(p)
        if g or not (p.exists() or p.is_symlink()):
            return await edit(c.message, f"⛔ {g or 'Topilmadi'}", K([[B("⬅️ Orqaga", f"f:d:{fm.tid(p.parent)}:0")]]))
        try: dst = await asyncio.to_thread(fm.to_trash, p)
        except Exception as e: return await edit(c.message, f"❌ {esc(str(e))}", K([[B("⬅️ Orqaga", f"f:v:{k}")]]))
        key = uuid.uuid4().hex[:8]; fm.TRASHED[key] = (str(p), str(dst))
        return await edit(c.message, f"🗑 <b>{esc(p.name)}</b> savatga o'tdi.",
                          K([[B("↩️ Qaytarish", f"f:undo:{key}"), B("📂 Papkaga", f"f:d:{fm.tid(p.parent)}:0")]]))
    if op in ("cp", "mv"):
        if op == "mv":
            g = fm.guard(p)
            if g: return await edit(c.message, f"⛔ {g}", K([[B("⬅️ Orqaga", f"f:v:{k}")]]))
        CLIP[uid] = ("copy" if op == "cp" else "move", str(p))
        text, kb = render_dir(uid, p.parent, 0, f"{'📋 Nusxa' if op == 'cp' else '✂️ Ko‘chirish'} buferga olindi: <b>{esc(p.name)}</b>\n"
                                                  "Papkani oching va «📥 Qo'yish» ni bosing.\n\n")
        return await edit(c.message, text, kb)
    if op == "cc":
        CLIP.pop(uid, None)
        text, kb = render_dir(uid, p, 0, "🧹 Bufer tozalandi\n"); return await edit(c.message, text, kb)
    if op == "ps":
        if uid not in CLIP: return await edit(c.message, "Bufer bo'sh", K([[B("⬅️", f"f:d:{k}:0")]]))
        mode, src = CLIP[uid]
        try:
            dst = await asyncio.to_thread(fm.paste, mode, Path(src), p)
            if mode == "move": CLIP.pop(uid, None)
            note = f"✅ {'Nusxalandi' if mode == 'copy' else 'Ko‘chirildi'}: <b>{esc(dst.name)}</b>\n"
        except Exception as e:
            note = f"❌ {esc(str(e))}\n"
        text, kb = render_dir(uid, p, 0, note); return await edit(c.message, text, kb)


@router.callback_query(F.data.startswith("f:undo:"))
async def cb_undo(c: CallbackQuery):
    key = c.data.split(":")[2]
    orig, dst = fm.TRASHED.get(key, (None, None))
    if not orig or not Path(dst).exists():
        return await edit(c.message, "Qaytarib bo'lmadi (muddati o'tgan).", K([[B("🏠", "f:r")]]))
    if Path(orig).exists():
        return await edit(c.message, "❌ Asl joyda shu nomli narsa bor.", K([[B("🏠", "f:r")]]))
    try:
        await asyncio.to_thread(shutil.move, dst, orig)
        fm.TRASHED.pop(key, None)
        text, kb = show(c.from_user.id, Path(orig), "↩️ Qaytarildi\n")
    except Exception as e:
        text, kb = f"❌ {esc(str(e))}", K([[B("🏠", "f:r")]])
    await edit(c.message, text, kb)


# ───────── matn / hujjat kutish ─────────
class HasState(BaseFilter):
    def __init__(self, kinds): self.kinds = set(kinds)
    async def __call__(self, m: Message) -> bool:
        s = FSTATE.get(m.from_user.id)
        return bool(s and s["kind"] in self.kinds)


@router.message(F.text & ~F.text.startswith("/"), HasState({"ren", "mk"}))
async def on_text(m: Message):
    uid = m.from_user.id
    s = FSTATE[uid]; p = Path(s["path"]); name = m.text.strip()
    cancel = K([[B("❌ Bekor", f"f:cx:{fm.tid(p)}")]])
    if not name or "/" in name or name in (".", "..") or len(name) > 200 or "\0" in name:
        return await m.answer("❌ Nom yaroqsiz (/ bo'lmasin). Qayta yozing:", reply_markup=cancel)
    try:
        if s["kind"] == "ren":
            g = fm.guard(p)
            if g: raise ValueError(g)
            dst = p.with_name(name)
            if dst.exists(): raise ValueError("Bunday nom allaqachon bor")
            await asyncio.to_thread(os.rename, p, dst)
            FSTATE.pop(uid, None)
            text, kb = show(uid, dst, "✅ Nomi o'zgartirildi\n")
        else:
            dst = p / name
            if dst.exists(): raise ValueError("Bunday nom allaqachon bor")
            await asyncio.to_thread(dst.mkdir)
            FSTATE.pop(uid, None)
            text, kb = render_dir(uid, p, 0, f"✅ Papka yaratildi: <b>{esc(name)}</b>\n")
    except Exception as e:
        return await m.answer(f"❌ {esc(str(e))}\nBoshqa nom yozing:", reply_markup=cancel)
    await m.answer(text, reply_markup=kb)


@router.message(F.document, HasState({"up", "rep"}))
async def on_doc(m: Message):
    uid = m.from_user.id
    s = FSTATE[uid]; p = Path(s["path"]); doc = m.document
    cancel = K([[B("✅ Tugatish" if s["kind"] == "up" else "❌ Bekor", f"f:cx:{fm.tid(p)}")]])
    if doc.file_size and doc.file_size > MAX_DL:
        return await m.answer("⚠️ Bot API 20MB dan katta faylni bermaydi.", reply_markup=cancel)
    tmp = TMP / f"up-{uuid.uuid4().hex[:8]}"
    try:
        await m.bot.download(doc, destination=tmp)
        if s["kind"] == "rep":
            if not p.is_file(): raise ValueError("Asl fayl topilmadi")
            await asyncio.to_thread(replace_file, p, tmp)
            FSTATE.pop(uid, None)
            text, kb = render_item(uid, p, "✅ Fayl almashtirildi (eskisi savatda)\n", preview=False)
            return await m.answer(text, reply_markup=kb)
        name = os.path.basename((doc.file_name or "file").replace("\0", "")) or "file"
        dst = fm.unique(p / name)
        await asyncio.to_thread(shutil.move, str(tmp), str(dst))
        await m.answer(f"✅ Saqlandi: <code>{esc(str(dst))}</code>\nYana yuborishingiz mumkin.", reply_markup=cancel)
    except Exception as e:
        await m.answer(f"❌ {esc(str(e))}", reply_markup=cancel)
    finally:
        tmp.unlink(missing_ok=True)
