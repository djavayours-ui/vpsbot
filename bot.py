"""VPS Manager bot — barcha bo'limlar yadro (core/appctl/filesvc) ustida ishlaydi.
Mini App bir xil yadroni ishlatadi, shuning uchun mantiq ikki marta yozilmaydi."""
import asyncio, os, time

import psutil
from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardButton as IB, MenuButtonWebApp, Message, WebAppInfo

import appctl, bot_apps, bot_files, bot_sys, core, filesvc as fm, webapp
from common import ADMINS, APPS, K, TMP, TRASH, B, AdminOnly, edit, esc, pre, sh

WEBAPP_URL = os.getenv("WEBAPP_URL", "").strip()
ALERT_THRESHOLD = int(os.getenv("ALERT_THRESHOLD", "90"))
r = Router()


def gb(x): return f"{x / 1024**3:.1f}G"


# ───────── monitoring ─────────
def _status_text() -> str:
    s = core.status()
    lines = [
        f"CPU  {core.__dict__ and ''}".rstrip(),
    ]
    from config import bar
    lines = [
        f"CPU  {bar(s['cpu'])}  ({s['cores']} yadro)",
        f"RAM  {bar(s['ram']['p'])}  {gb(s['ram']['u'])}/{gb(s['ram']['t'])}",
        f"SWAP {bar(s['swap']['p'])}  {gb(s['swap']['u'])}/{gb(s['swap']['t'])}",
        f"DISK {bar(s['disk']['p'])}  {gb(s['disk']['u'])}/{gb(s['disk']['t'])}",
        f"Load {s['load'][0]:.2f} {s['load'][1]:.2f} {s['load'][2]:.2f}",
        f"Net  ↓{gb(s['net']['r'])} ↑{gb(s['net']['s'])}",
        f"Up   {int(s['up'] // 86400)}k {int(s['up'] % 86400 // 3600)}s {int(s['up'] % 3600 // 60)}d",
    ]
    if s["temp"]:
        lines.append(f"Temp {s['temp']:.0f}°C")
    lines.append("\nTOP jarayonlar (CPU% MEM% nom):")
    for t in s["top"][:5]:
        lines.append(f"{t['cpu']:5.1f} {t['mem']:5.1f}  {t['name']} ({t['pid']})")
    return "\n".join(lines)


async def status_text() -> str:
    return "📊 <b>Server holati</b>\n" + pre(await asyncio.to_thread(_status_text))


async def alert_loop(bot: Bot):
    last: dict[str, float] = {}
    bad: dict[str, int] = {}
    down: set[str] = set()

    async def notify(msg):
        for a in ADMINS:
            try: await bot.send_message(a, msg)
            except Exception: pass

    async def alert(key, msg):
        if time.time() - last.get(key, 0) > 900:
            last[key] = time.time()
            await notify(msg)

    cpu_hi = 0
    while True:
        try:
            cpu = core.cpu_avg()
            cpu_hi = cpu_hi + 1 if cpu > ALERT_THRESHOLD else 0
            if cpu_hi >= 2: await alert("cpu", f"🚨 CPU {cpu:.0f}% (uzoq vaqtdan beri)")
            if psutil.virtual_memory().percent > ALERT_THRESHOLD: await alert("ram", "🚨 RAM to'lib qoldi")
            if psutil.disk_usage("/").percent > ALERT_THRESHOLD: await alert("disk", "🚨 Disk to'lib qoldi (💾 Disk → 🧹 Tozalash)")
            names = appctl.app_names()
            for n, st in zip(names, await appctl.states(names) if names else []):
                if st in ("failed", "activating"):
                    bad[n] = bad.get(n, 0) + 1
                    if st == "failed" or bad[n] >= 2:
                        down.add(n)
                        await alert(f"app-{n}", f"❌ <b>{esc(n)}</b> {'ishdan chiqdi' if st == 'failed' else 'qayta-qayta qulayapti'}. /fix {n}")
                else:
                    bad.pop(n, None)
                    if st == "active" and n in down:
                        down.discard(n)
                        await notify(f"✅ <b>{esc(n)}</b> qayta ishlayapti")
        except Exception as e:
            print("alert error", e)
        await asyncio.sleep(55)


async def janitor():
    while True:
        await asyncio.to_thread(fm.purge_trash)
        await asyncio.to_thread(fm.purge_tmp)
        await asyncio.to_thread(appctl.prune_all_backups)
        await asyncio.sleep(6 * 3600)


# ───────── menyu ─────────
def _panel():
    return [[IB(text="🖥 Panel (Mini App)", web_app=WebAppInfo(url=WEBAPP_URL))]] if WEBAPP_URL.startswith("https") else []


def main_kb():
    return K(_panel() + [[B("📊 Holat", "st"), B("📦 Ilovalar", "apps")],
                         [B("⚙️ Xizmatlar", "svcs"), B("🐳 Docker", "docker")],
                         [B("💾 Disk", "disk"), B("🔥 Jarayonlar", "pr:cpu")],
                         [B("📁 Fayllar", "fm"), B("🌐 Portlar", "ports")]])


START_TEXT = (
    "🖥 <b>VPS Manager</b>\n\n• ZIP fayl yuboring — avtomatik deploy (shu nomli ilova bor bo'lsa — yangilash)\n"
    "• 🖥 <b>Panel</b> — barcha bo'limlar Mini App ko'rinishida (tezroq va qulay)\n"
    "• /status — monitoring\n• /apps — ilovalar\n• /svc &lt;start|stop|restart&gt; &lt;nom&gt;\n"
    "• /logs &lt;nom&gt; [qator] — loglar\n• /fix &lt;nom&gt; — AI bilan tuzatish\n"
    "• /update &lt;nom&gt; — ZIP bilan yangilash (xatoda avtomatik rollback)\n• /rollback &lt;nom&gt; — oldingi versiya\n"
    "• /sh &lt;buyruq&gt; — terminal\n• /reboot — serverni qayta yuklash\n• /files — fayl menejeri\n• /cancel — amalni bekor qilish")


@r.message(CommandStart())
@r.message(Command("help"))
async def start(m: Message):
    await m.answer(START_TEXT, reply_markup=main_kb())


@r.callback_query(F.data == "menu")
async def cb_menu(c: CallbackQuery):
    await edit(c.message, START_TEXT, main_kb())


@r.message(Command("status"))
async def cmd_status(m: Message): await m.answer(await status_text(), reply_markup=main_kb())


@r.callback_query(F.data == "st")
async def cb_status(c: CallbackQuery):
    await edit(c.message, await status_text(), main_kb())


@r.callback_query(F.data == "disk")
async def cb_disk(c: CallbackQuery):
    d = await core.disk()
    await edit(c.message, f"💾 <b>Disk</b> — {d['p']:.0f}% band\n{pre(d['df'] + chr(10) + d['du'])}",
               K([[B("🧹 Tozalash", "clean"), B("🔄", "disk")], [B("⬅️ Menyu", "menu"), B("❌ Yopish", "x")]]))


@r.callback_query(F.data == "clean")
async def cb_clean(c: CallbackQuery):
    res = await core.clean()
    await asyncio.to_thread(fm.purge_tmp, 1)
    await edit(c.message, f"🧹 Tozalandi: <b>{res['freed']}MB</b> bo'shadi\n(Savat tegilmadi — Fayllar → 🗑 Savat)",
               K([[B("💾 Disk", "disk"), B("❌ Yopish", "x")]]))


@r.callback_query(F.data == "docker")
async def cb_docker(c: CallbackQuery):
    d = await core.docker()
    await edit(c.message, f"🐳 <b>Docker</b>\n{pre(d['text'])}", K([[B("🔄", "docker"), B("⬅️ Menyu", "menu"), B("❌ Yopish", "x")]]))


# ───────── tizim buyruqlari ─────────
@r.message(Command("svc"))
async def cmd_svc(m: Message):
    from config import NAME_RE
    a = (m.text or "").split()
    if len(a) != 3 or a[1] not in {"start", "stop", "restart", "status", "enable", "disable"} or not NAME_RE.match(a[2]):
        return await m.answer("Format: <code>/svc restart nginx</code>")
    _, out = await sh(f"systemctl {a[1]} {a[2]} --no-pager | head -30; systemctl is-active {a[2]}")
    await m.answer(pre(out))


@r.message(Command("logs"))
async def cmd_logs(m: Message):
    from config import NAME_RE
    a = (m.text or "").split()
    if len(a) < 2 or not NAME_RE.match(a[1]): return await m.answer("Format: <code>/logs nom [qator]</code>")
    n = min(int(a[2]), 300) if len(a) > 2 and a[2].isdigit() else 60
    if (APPS / a[1]).is_dir():
        out = await appctl.logs(a[1], n)
    else:
        _, out = await sh(f"journalctl -u {a[1]} -n {n} --no-pager -o cat")
    await m.answer(pre(out))


@r.message(Command("sh"))
async def cmd_sh(m: Message):
    cmd = (m.text or "").partition(" ")[2].strip()
    if not cmd: return await m.answer("Format: <code>/sh ls -la</code>")
    res = await core.shell(cmd, 60)
    await m.answer(f"exit={res['code']}\n" + pre(res["out"]))


@r.message(Command("reboot"))
async def cmd_reboot(m: Message):
    await m.answer("Server qayta yuklansinmi?", reply_markup=K([[B("✅ Ha, reboot", "reboot_yes"), B("Bekor", "x")]]))


@r.callback_query(F.data == "reboot_yes")
async def cb_reboot(c: CallbackQuery):
    await edit(c.message, "♻️ Reboot...")
    await core.reboot()


@r.callback_query(F.data == "x")
async def cb_cancel(c: CallbackQuery):
    fm.FSTATE.pop(c.from_user.id, None) if hasattr(fm, "FSTATE") else None
    try: await c.message.delete()
    except Exception: pass


@r.message(Command("panel"))
async def cmd_panel(m: Message):
    kb = K(_panel()) if _panel() else None
    await m.answer(f"🖥 Panel: {esc(WEBAPP_URL)}" if WEBAPP_URL.startswith("https") else "Panel o'chiq yoki cloudflared topilmadi.",
                   reply_markup=kb)


@r.message(Command("cancel"))
async def cmd_cancel(m: Message):
    uid = m.from_user.id
    bot_files.FSTATE.pop(uid, None)
    bot_files.CLIP.pop(uid, None)
    bot_apps.cancel_all()
    await m.answer("❌ Bekor qilindi.", reply_markup=main_kb())


async def main():
    bot = Bot(os.environ["BOT_TOKEN"], default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    global WEBAPP_URL
    runner = None
    if WEBAPP_URL != "off":
        runner = await webapp.serve()
        if not WEBAPP_URL:
            WEBAPP_URL = await webapp.tunnel(int(os.getenv("WEBAPP_PORT", "8080")))
            print("Mini App manzili:", WEBAPP_URL or "cloudflared topilmadi")
            if not WEBAPP_URL:
                for a in ADMINS:
                    try: await bot.send_message(a, "⚠️ cloudflared topilmadi. O'rnating: <code>sudo apt install cloudflared</code> yoki README'dagi ko'rsatma.")
                    except Exception: pass
        if WEBAPP_URL.startswith("https"):
            try:
                await bot.set_chat_menu_button(menu_button=MenuButtonWebApp(text="Panel", web_app=WebAppInfo(url=WEBAPP_URL)))
            except Exception as e:
                print("menu button:", e)
    if WEBAPP_URL.startswith("https"):
        for a in ADMINS:
            try: await bot.send_message(a, f"🖥 <b>Panel manzili:</b>\n{esc(WEBAPP_URL)}\n\n<i>Telegram ichida «Panel» tugmasi orqali oching.</i>")
            except Exception: pass
    dp.include_routers(bot_apps.router, bot_files.router, bot_sys.router, r)
    dp.update.outer_middleware(AdminOnly())
    bg = [asyncio.create_task(core.sampler()), asyncio.create_task(alert_loop(bot)), asyncio.create_task(janitor())]
    for a in ADMINS:
        try:
            up = time.time() - psutil.boot_time()
            await bot.send_message(a, f"🟢 Bot ishga tushdi · server {int(up // 3600)}s {int(up % 3600 // 60)}d ishlayapti",
                                   reply_markup=main_kb())
        except Exception:
            pass
    try:
        await dp.start_polling(bot)
    finally:
        for t in bg: t.cancel()
        if runner: await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
