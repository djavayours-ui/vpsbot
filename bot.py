#!/usr/bin/env python3
"""VPS Manager Telegram Bot — ZIP deploy, systemd, monitoring, AI fix."""
import asyncio, html, json, os, re, shutil, time, uuid, zipfile
from pathlib import Path

import psutil
from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.environ["BOT_TOKEN"]
ADMINS = {int(x) for x in os.environ["ADMIN_IDS"].split(",") if x.strip()}
APPS = Path(os.getenv("APPS_DIR", "/opt/apps"))
TMP = Path("/tmp/vpsbot")
AI_MODEL = os.getenv("AI_MODEL", "claude-sonnet-5-5")
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ALERT_THRESHOLD = int(os.getenv("ALERT_THRESHOLD", "90"))
APPS.mkdir(parents=True, exist_ok=True)
TMP.mkdir(parents=True, exist_ok=True)
BACKUPS = APPS / ".backups"
TIMINGS = APPS / ".timings.json"
STABLE_SECS = int(os.getenv("STABLE_SECS", "10"))  # yangilangandan keyin barqarorlik tekshiruvi

bot = Bot(TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
r = Router()
r.message.filter(F.from_user.id.in_(ADMINS))
r.callback_query.filter(F.from_user.id.in_(ADMINS))
dp.include_router(r)

NAME_RE = re.compile(r"^[a-zA-Z0-9_.@-]{1,60}$")
PENDING: dict[str, dict] = {}  # AI takliflari


# ───────────── yordamchilar ─────────────
async def sh(cmd: str, cwd=None, timeout=300) -> tuple[int, str]:
    p = await asyncio.create_subprocess_shell(
        cmd, cwd=cwd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
    try:
        out, _ = await asyncio.wait_for(p.communicate(), timeout)
    except asyncio.TimeoutError:
        p.kill()
        return 124, "⏱ Vaqt tugadi (timeout)"
    return p.returncode, out.decode(errors="replace")


def pre(text: str, limit=3500) -> str:
    text = text.strip() or "(bo'sh)"
    if len(text) > limit:
        text = "…" + text[-limit:]
    return f"<pre>{html.escape(text)}</pre>"


def unit(name: str) -> str:
    return f"app-{name}.service"


def app_names() -> list[str]:
    return sorted(p.name for p in APPS.iterdir() if p.is_dir() and not p.name.startswith("."))


def bar(p: float) -> str:
    n = int(p / 10)
    return "█" * n + "░" * (10 - n) + f" {p:.0f}%"


def gb(x): return f"{x / 1024**3:.1f}G"


# ───────────── monitoring ─────────────
def _status_sync() -> str:
    procs = list(psutil.process_iter(["pid", "name"]))
    for p in procs:
        try: p.cpu_percent(None)
        except Exception: pass
    cpu = psutil.cpu_percent(interval=1, percpu=True)
    top = []
    for p in procs:
        try: top.append((p.cpu_percent(None), p.memory_percent(), p.info["name"], p.pid))
        except Exception: pass
    top.sort(reverse=True)
    vm, sw, du = psutil.virtual_memory(), psutil.swap_memory(), psutil.disk_usage("/")
    net = psutil.net_io_counters()
    la = os.getloadavg()
    up = time.time() - psutil.boot_time()
    lines = [
        f"CPU  {bar(sum(cpu)/len(cpu))}  ({len(cpu)} yadro)",
        f"RAM  {bar(vm.percent)}  {gb(vm.used)}/{gb(vm.total)}",
        f"SWAP {bar(sw.percent)}  {gb(sw.used)}/{gb(sw.total)}",
        f"DISK {bar(du.percent)}  {gb(du.used)}/{gb(du.total)}",
        f"Load {la[0]:.2f} {la[1]:.2f} {la[2]:.2f}",
        f"Net  ↓{gb(net.bytes_recv)} ↑{gb(net.bytes_sent)}",
        f"Up   {int(up//86400)}k {int(up%86400//3600)}s {int(up%3600//60)}d",
    ]
    try:
        t = psutil.sensors_temperatures()
        if t: lines.append(f"Temp {list(t.values())[0][0].current:.0f}°C")
    except Exception: pass
    lines.append("\nTOP jarayonlar (CPU% MEM% nom):")
    for c, m, n, pid in top[:5]:
        lines.append(f"{c:5.1f} {m:5.1f}  {n} ({pid})")
    return "\n".join(lines)


async def status_text() -> str:
    return "📊 <b>Server holati</b>\n" + pre(await asyncio.to_thread(_status_sync))


async def alert_loop():
    last: dict[str, float] = {}
    async def alert(key, msg):
        if time.time() - last.get(key, 0) > 900:
            last[key] = time.time()
            for a in ADMINS:
                try: await bot.send_message(a, msg)
                except Exception: pass
    while True:
        try:
            cpu = await asyncio.to_thread(psutil.cpu_percent, 5)
            if cpu > ALERT_THRESHOLD: await alert("cpu", f"🚨 CPU {cpu:.0f}%")
            if psutil.virtual_memory().percent > ALERT_THRESHOLD: await alert("ram", "🚨 RAM to'lib qoldi")
            if psutil.disk_usage("/").percent > ALERT_THRESHOLD: await alert("disk", "🚨 Disk to'lib qoldi")
            for n in app_names():
                c, out = await sh(f"systemctl is-failed {unit(n)}")
                if out.strip() == "failed":
                    await alert(f"app-{n}", f"❌ <b>{n}</b> ishdan chiqdi. /fix {n}")
        except Exception as e:
            print("alert error", e)
        await asyncio.sleep(55)


# ───────────── menyu ─────────────
def main_kb():
    b = InlineKeyboardBuilder()
    b.button(text="📊 Holat", callback_data="st")
    b.button(text="📦 Ilovalar", callback_data="apps")
    b.button(text="⚙️ Xizmatlar", callback_data="svcs")
    b.button(text="🐳 Docker", callback_data="docker")
    b.button(text="💾 Disk/Port", callback_data="disk")
    b.adjust(2)
    return b.as_markup()


@r.message(CommandStart())
async def start(m: Message):
    await m.answer(
        "🖥 <b>VPS Manager</b>\n\n• ZIP fayl yuboring — avtomatik deploy\n"
        "• /status — monitoring\n• /apps — ilovalar\n• /svc &lt;start|stop|restart|status&gt; &lt;nom&gt;\n"
        "• /logs &lt;nom&gt; — loglar\n• /fix &lt;nom&gt; — AI bilan tuzatish\n• /update &lt;nom&gt; — ZIP bilan yangilash (xatoda avtomatik rollback)\n• /rollback &lt;nom&gt; — oldingi versiya\n• /sh &lt;buyruq&gt; — terminal\n"
        "• /reboot — serverni qayta yuklash", reply_markup=main_kb())


@r.message(Command("status"))
async def cmd_status(m: Message): await m.answer(await status_text(), reply_markup=main_kb())


@r.callback_query(F.data == "st")
async def cb_status(c: CallbackQuery):
    await c.message.edit_text(await status_text(), reply_markup=main_kb()); await c.answer()


@r.callback_query(F.data == "disk")
async def cb_disk(c: CallbackQuery):
    _, d = await sh("df -h -x tmpfs -x devtmpfs | head -15; echo; ss -tlnp | head -25")
    await c.message.answer(pre(d)); await c.answer()


@r.callback_query(F.data == "docker")
async def cb_docker(c: CallbackQuery):
    _, d = await sh("docker ps -a --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'")
    await c.message.answer(pre(d)); await c.answer()


@r.callback_query(F.data == "svcs")
async def cb_svcs(c: CallbackQuery):
    _, d = await sh("systemctl list-units --type=service --state=running --no-pager --plain --no-legend | awk '{print $1}' | head -40")
    await c.message.answer("⚙️ <b>Ishlayotgan xizmatlar</b>\n" + pre(d) +
                           "\nBoshqarish: <code>/svc restart nginx</code>"); await c.answer()


# ───────────── systemd ─────────────
@r.message(Command("svc"))
async def cmd_svc(m: Message):
    a = (m.text or "").split()
    if len(a) != 3 or a[1] not in {"start", "stop", "restart", "status", "enable", "disable"} or not NAME_RE.match(a[2]):
        return await m.answer("Format: <code>/svc restart nginx</code>")
    _, out = await sh(f"systemctl {a[1]} {a[2]} --no-pager | head -30; systemctl is-active {a[2]}")
    await m.answer(pre(out))


@r.message(Command("logs"))
async def cmd_logs(m: Message):
    a = (m.text or "").split()
    if len(a) < 2 or not NAME_RE.match(a[1]): return await m.answer("Format: <code>/logs nom [qator]</code>")
    n = int(a[2]) if len(a) > 2 and a[2].isdigit() else 60
    u = unit(a[1]) if (APPS / a[1]).is_dir() else a[1]
    _, out = await sh(f"journalctl -u {u} -n {min(n, 300)} --no-pager -o cat")
    await m.answer(pre(out))


@r.message(Command("sh"))
async def cmd_sh(m: Message):
    cmd = (m.text or "").partition(" ")[2].strip()
    if not cmd: return await m.answer("Format: <code>/sh ls -la</code>")
    code, out = await sh(cmd, timeout=60)
    await m.answer(f"exit={code}\n" + pre(out))


@r.message(Command("reboot"))
async def cmd_reboot(m: Message):
    b = InlineKeyboardBuilder(); b.button(text="✅ Ha, reboot", callback_data="reboot_yes"); b.button(text="Bekor", callback_data="x")
    await m.answer("Server qayta yuklansinmi?", reply_markup=b.as_markup())


@r.callback_query(F.data == "reboot_yes")
async def cb_reboot(c: CallbackQuery):
    await c.message.edit_text("♻️ Reboot..."); await sh("systemctl reboot")


@r.callback_query(F.data == "x")
async def cb_cancel(c: CallbackQuery): await c.message.delete()


# ───────────── ilovalar ─────────────
@r.message(Command("apps"))
async def cmd_apps(m: Message): await show_apps(m)


@r.callback_query(F.data == "apps")
async def cb_apps(c: CallbackQuery): await show_apps(c.message); await c.answer()


async def show_apps(m: Message):
    names = app_names()
    if not names: return await m.answer("Hali ilova yo'q. ZIP yuboring 📦")
    b = InlineKeyboardBuilder()
    for n in names:
        _, st = await sh(f"systemctl is-active {unit(n)}")
        b.button(text=f"{'🟢' if st.strip()=='active' else '🔴'} {n}", callback_data=f"app:{n}")
    b.adjust(2)
    await m.answer("📦 <b>Ilovalar</b>", reply_markup=b.as_markup())


@r.callback_query(F.data.startswith("app:"))
async def cb_app(c: CallbackQuery):
    n = c.data.split(":")[1]
    b = InlineKeyboardBuilder()
    for t, a in [("▶️ Start", "start"), ("⏹ Stop", "stop"), ("🔄 Restart", "restart"),
                 ("📜 Log", "logs"), ("🤖 AI fix", "fix"), ("🗑 O'chirish", "delete"),
                 ("⬆️ ZIP yangilash", "upd"), ("↩️ Oldingi versiya", "rollback")]:
        b.button(text=t, callback_data=f"do:{n}:{a}")
    b.adjust(3)
    _, st = await sh(f"systemctl is-active {unit(n)}")
    await c.message.answer(f"<b>{n}</b> — {st.strip()}", reply_markup=b.as_markup()); await c.answer()


@r.callback_query(F.data.startswith("do:"))
async def cb_do(c: CallbackQuery):
    _, n, a = c.data.split(":")
    if a in {"start", "stop", "restart"}:
        _, out = await sh(f"systemctl {a} {unit(n)}; sleep 1; systemctl is-active {unit(n)}")
        await c.message.answer(f"{n}: {a} → {pre(out)}")
    elif a == "logs":
        _, out = await sh(f"journalctl -u {unit(n)} -n 60 --no-pager -o cat")
        await c.message.answer(pre(out))
    elif a == "fix":
        await ai_fix(c.message, n)
    elif a == "upd":
        WAITING[c.from_user.id] = n
        await c.message.answer(f"📦 <b>{n}</b> uchun yangi ZIP faylni yuboring.")
    elif a == "rollback":
        await do_rollback(c.message, n)
    elif a == "delete":
        await sh(f"systemctl disable --now {unit(n)}; rm -f /etc/systemd/system/{unit(n)}; systemctl daemon-reload")
        shutil.rmtree(APPS / n, ignore_errors=True)
        await c.message.answer(f"🗑 {n} o'chirildi")
    await c.answer()


# ───────────── ZIP deploy ─────────────
def safe_extract(zpath: Path, dest: Path):
    dest.mkdir(parents=True, exist_ok=True)
    root = dest.resolve()
    with zipfile.ZipFile(zpath) as z:
        for i in z.infolist():
            t = (dest / i.filename).resolve()
            if root not in t.parents and t != root:
                raise ValueError(f"Xavfli yo'l: {i.filename}")
        z.extractall(dest)
    items = [p for p in dest.iterdir() if p.name != "__MACOSX"]
    if len(items) == 1 and items[0].is_dir():  # bitta papka ichida bo'lsa — ochib yuboramiz
        inner = items[0]
        for p in inner.iterdir(): shutil.move(str(p), dest / p.name)
        inner.rmdir()


def detect(d: Path) -> tuple[str, str, str]:
    """(tur, o'rnatish buyrug'i, ishga tushirish buyrug'i)"""
    if (d / "start.cmd").exists():
        return "custom", "", (d / "start.cmd").read_text().strip()
    if (d / "docker-compose.yml").exists() or (d / "compose.yaml").exists():
        return "docker", "docker compose up -d --build", ""
    if (d / "package.json").exists():
        run = "npm start" if '"start"' in (d / "package.json").read_text() else "node index.js"
        return "node", "npm install --omit=dev", run
    if (d / "requirements.txt").exists() or list(d.glob("*.py")):
        ins = "python3 -m venv .venv && .venv/bin/pip install -q -r requirements.txt" \
            if (d / "requirements.txt").exists() else "python3 -m venv .venv"
        for e in ("main.py", "bot.py", "app.py", "run.py", "server.py"):
            if (d / e).exists(): return "python", ins, f".venv/bin/python {e}"
        return "python", ins, ""
    if (d / "start.sh").exists(): return "shell", "chmod +x start.sh", "./start.sh"
    return "unknown", "", ""


@r.message(F.document)
async def on_zip(m: Message):
    doc = m.document
    if not (doc.file_name or "").lower().endswith(".zip"):
        return await m.answer("Faqat .zip fayl qabul qilinadi.")
    if doc.file_size and doc.file_size > 20 * 1024 * 1024:
        return await m.answer("⚠️ Telegram Bot API 20MB dan katta faylni bermaydi. Kichraytiring yoki local Bot API server ishlating.")
    name = re.sub(r"[^a-zA-Z0-9_.-]", "-", Path(doc.file_name).stem)[:50]
    cap = (m.caption or "").split()
    target = WAITING.pop(m.from_user.id, None)
    if len(cap) == 2 and cap[0] == "/update" and NAME_RE.match(cap[1]):
        target = cap[1]
    elif not target and (APPS / name).is_dir():
        target = name  # shu nomli ilova bor — yangilash rejimi (rollback himoyasi bilan)
    if target and not (APPS / target).is_dir():
        return await m.answer("Bunday ilova yo'q.")
    msg = await m.answer(f"⬇️ <b>{target or name}</b> yuklanmoqda...")
    zpath = TMP / f"{uuid.uuid4().hex}.zip"
    await bot.download(doc, destination=zpath)
    if target:
        try:
            await do_update(msg, zpath, target)
        finally:
            zpath.unlink(missing_ok=True)
        return
    dest = APPS / name
    log = []
    try:
        if dest.exists():
            await sh(f"systemctl stop {unit(name)}")
            shutil.rmtree(dest)
        await msg.edit_text("📂 Ochilmoqda...")
        safe_extract(zpath, dest)
        kind, ins, run = detect(dest)
        log.append(f"Tur: {kind}")
        if ins:
            await msg.edit_text(f"📦 O'rnatilmoqda ({kind})...")
            code, out = await sh(ins, cwd=dest, timeout=900)
            log.append(out[-1200:])
            if code: raise RuntimeError("O'rnatishda xato")
        if kind == "docker":
            return await msg.edit_text(f"✅ Docker Compose ishga tushdi\n{pre(chr(10).join(log))}")
        if not run:
            return await msg.edit_text("⚠️ Ishga tushirish fayli topilmadi. ZIP ichiga <code>start.cmd</code> "
                                       "(masalan: <code>.venv/bin/python app.py</code>) qo'shing.")
        Path(f"/etc/systemd/system/{unit(name)}").write_text(
            f"[Unit]\nDescription=App {name}\nAfter=network.target\n\n[Service]\nWorkingDirectory={dest}\n"
            f"ExecStart=/bin/bash -lc 'exec {run}'\nRestart=always\nRestartSec=3\n\n"
            f"[Install]\nWantedBy=multi-user.target\n")
        await sh(f"systemctl daemon-reload && systemctl enable --now {unit(name)}")
        await asyncio.sleep(4)
        _, st = await sh(f"systemctl is-active {unit(name)}")
        _, lg = await sh(f"journalctl -u {unit(name)} -n 15 --no-pager -o cat")
        ok = st.strip() == "active"
        b = InlineKeyboardBuilder()
        b.button(text="📜 Log", callback_data=f"do:{name}:logs")
        if not ok: b.button(text="🤖 AI fix", callback_data=f"do:{name}:fix")
        await msg.edit_text(f"{'✅ Ishlayapti' if ok else '❌ Ishga tushmadi'}: <b>{name}</b>\n"
                            f"<code>{html.escape(run)}</code>\n{pre(lg)}", reply_markup=b.as_markup())
    except Exception as e:
        await msg.edit_text(f"❌ Xato: {html.escape(str(e))}\n{pre(chr(10).join(log))}")
    finally:
        zpath.unlink(missing_ok=True)


# ───────────── ZIP bilan yangilash + rollback ─────────────
WAITING: dict[int, str] = {}  # user_id -> ilova (keyingi ZIP shu ilovani yangilaydi)
KEEP = {".venv", "venv", "node_modules", ".env", "data", "uploads"}  # yangilashda tegilmaydi
DBSUF = {".db", ".sqlite", ".sqlite3"}


def kept(p: Path) -> bool:
    return p.name in KEEP or p.suffix in DBSUF


def mirror(src: Path, dst: Path):
    """dst ni src ga aylantiradi (KEEP dagilar saqlanadi)."""
    for p in list(dst.iterdir()):
        if kept(p): continue
        shutil.rmtree(p) if p.is_dir() and not p.is_symlink() else p.unlink()
    for p in src.iterdir():
        if kept(p) and (dst / p.name).exists(): continue
        if p.is_dir(): shutil.copytree(p, dst / p.name, symlinks=True)
        else: shutil.copy2(p, dst / p.name)


def make_backup(d: Path, bak: Path):
    bak.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(d, bak, symlinks=True, ignore=shutil.ignore_patterns(
        *KEEP, "*.db", "*.sqlite", "*.sqlite3", ".git", "__pycache__"))
    for old in sorted(bak.parent.glob("*"))[:-3]:  # oxirgi 3 ta zaxira saqlanadi
        shutil.rmtree(old, ignore_errors=True)


def deps_changed(bak: Path, d: Path, kind: str) -> bool:
    for f in ("requirements.txt", "package.json", "package-lock.json"):
        a, b = bak / f, d / f
        if a.exists() != b.exists() or (a.exists() and a.read_bytes() != b.read_bytes()):
            return True
    return (kind == "python" and not (d / ".venv").exists()) or (kind == "node" and not (d / "node_modules").exists())


def write_unit(name: str, d: Path, run: str):
    Path(f"/etc/systemd/system/{unit(name)}").write_text(
        f"[Unit]\nDescription=App {name}\nAfter=network.target\n\n[Service]\nWorkingDirectory={d}\n"
        f"ExecStart=/bin/bash -lc 'exec {run}'\nRestart=always\nRestartSec=3\n\n"
        f"[Install]\nWantedBy=multi-user.target\n")


def avg_time(name: str) -> float | None:
    try:
        v = json.loads(TIMINGS.read_text()).get(name, [])
        return sum(v) / len(v) if v else None
    except Exception:
        return None


def save_time(name: str, secs: float):
    try: data = json.loads(TIMINGS.read_text())
    except Exception: data = {}
    data[name] = (data.get(name, []) + [round(secs, 1)])[-5:]
    TIMINGS.write_text(json.dumps(data))


class Progress:
    """Xabarni har 2 soniyada yangilab, o'tgan va taxminiy qolgan vaqtni ko'rsatadi."""
    def __init__(self, msg: Message, title: str, est: float):
        self.msg, self.title, self.est = msg, title, est
        self.t0 = time.time(); self.done: list[tuple[str, float]] = []
        self.cur = ""; self.cur_t = self.t0; self.task = None

    def step(self, text: str):
        now = time.time()
        if self.cur: self.done.append((self.cur, now - self.cur_t))
        self.cur, self.cur_t = text, now

    def render(self) -> str:
        el = time.time() - self.t0
        rem = max(self.est - el, 0)
        pct = min(el / self.est * 100, 95) if self.est else 0
        lines = [f"<b>{self.title}</b>"] + [f"✅ {t} <i>({d:.1f}s)</i>" for t, d in self.done]
        if self.cur: lines.append(f"⏳ {self.cur}…")
        eta = f"~{rem:.0f}s qoldi" if rem > 1 else "tez orada tugaydi…"
        return "\n".join(lines) + f"\n\n{bar(pct)}\n⏱ {el:.0f}s o'tdi · {eta}"

    async def _loop(self):
        while True:
            try: await self.msg.edit_text(self.render())
            except TelegramBadRequest: pass
            except Exception: pass
            await asyncio.sleep(2)

    async def start(self): self.task = asyncio.create_task(self._loop())

    async def stop(self):
        if self.task:
            self.task.cancel()
            try: await self.task
            except BaseException: pass


async def wait_healthy(name: str, boot_timeout=30) -> tuple[bool, float | None, str]:
    """(ok, ishga_tushish_vaqti, sabab). Jarayon 'running' bo'lguncha, so'ng STABLE_SECS barqarorlik."""
    u, t0 = unit(name), time.time()

    async def show():
        _, o = await sh(f"systemctl show {u} -p ActiveState,SubState,NRestarts")
        return dict(l.split("=", 1) for l in o.splitlines() if "=" in l)

    up = n0 = None
    while time.time() - t0 < boot_timeout:
        s = await show()
        if s.get("ActiveState") == "active" and s.get("SubState") == "running":
            up, n0 = time.time() - t0, int(s.get("NRestarts", 0)); break
        if s.get("ActiveState") == "failed": return False, None, "xizmat 'failed' holatiga tushdi"
        await asyncio.sleep(0.5)
    if up is None: return False, None, f"{boot_timeout}s ichida ishga tushmadi"
    end = time.time() + STABLE_SECS
    while time.time() < end:
        await asyncio.sleep(1)
        s = await show()
        if s.get("ActiveState") != "active" or s.get("SubState") != "running" or int(s.get("NRestarts", 0)) > n0:
            return False, up, "ishga tushdi, lekin qulab tushdi (crash/restart loop)"
    return True, up, "ok"


async def do_update(msg: Message, zpath: Path, name: str):
    d = APPS / name
    if not Path(f"/etc/systemd/system/{unit(name)}").exists():
        return await msg.edit_text("⚠️ Bu ilova systemd orqali ishlamaydi (masalan Docker). Hozircha qo'llab-quvvatlanmaydi.")
    pg = Progress(msg, f"⬆️ Yangilanmoqda: {name}", avg_time(name) or 30)
    await pg.start()
    stage = TMP / f"stage-{uuid.uuid4().hex}"
    bak = BACKUPS / name / time.strftime("%Y%m%d-%H%M%S")
    t_all, phase, up, err, since = time.time(), 0, None, "", ""
    try:
        pg.step("ZIP ochilmoqda")
        await asyncio.to_thread(safe_extract, zpath, stage)
        if not any(stage.iterdir()): raise RuntimeError("ZIP bo'sh")
        pg.step("Eski kod zaxiralanmoqda")
        await asyncio.to_thread(make_backup, d, bak)
        pg.step("Xizmat to'xtatilmoqda")
        phase = 1
        await sh(f"systemctl stop {unit(name)}")
        pg.step("Fayllar almashtirilmoqda")
        await asyncio.to_thread(mirror, stage, d)
        kind, ins, run = detect(d)
        if ins and deps_changed(bak, d, kind):
            pg.step("Kutubxonalar o'rnatilmoqda")
            code, out = await sh(ins, cwd=d, timeout=900)
            if code: raise RuntimeError("Kutubxona o'rnatishda xato:\n" + out[-1500:])
        if run:
            write_unit(name, d, run)
            await sh("systemctl daemon-reload")
        pg.step(f"Ishga tushirilmoqda va tekshirilmoqda (~{STABLE_SECS}s)")
        since = time.strftime("%Y-%m-%d %H:%M:%S")
        await sh(f"systemctl restart {unit(name)}")
        ok, up, why = await wait_healthy(name)
        if not ok: raise RuntimeError(why)
    except Exception as e:
        err = str(e)
    pg.step("Yakunlanmoqda")
    await pg.stop()
    shutil.rmtree(stage, ignore_errors=True)
    total = time.time() - t_all
    _, lg = await sh(f'journalctl -u {unit(name)} --since "{since or "-5min"}" -n 60 --no-pager -o cat')

    b = InlineKeyboardBuilder()
    if not err:
        save_time(name, total)
        b.button(text="📜 Log", callback_data=f"do:{name}:logs")
        b.button(text="↩️ Oldingi versiya", callback_data=f"do:{name}:rollback")
        return await msg.edit_text(
            f"✅ <b>{name}</b> yangilandi\n⏱ Jami: <b>{total:.1f}s</b>\n"
            f"🚀 Jarayon ishga tushdi: <b>{up:.1f}s</b>\n🛡 Barqarorlik ({STABLE_SECS}s) tekshiruvi: o'tdi\n"
            f"{pre(lg, 1500)}", reply_markup=b.as_markup())

    # ── xato: log yuboramiz va eski kodga qaytamiz ──
    head = f"❌ <b>{name}</b> yangilanmadi\nSabab: {html.escape(err[:600])}\n\nXato logi:{pre(lg, 1800)}"
    if phase == 0 or not bak.exists():
        return await msg.edit_text(head + "\nEski kod tegilmagan.")
    await msg.edit_text(head + "\n↩️ Eski kodga qaytarilmoqda…")
    t1 = time.time()
    await sh(f"systemctl stop {unit(name)}")
    await asyncio.to_thread(mirror, bak, d)
    kind, ins, run = detect(d)
    if run:
        write_unit(name, d, run)
        await sh("systemctl daemon-reload")
    await sh(f"systemctl restart {unit(name)}")
    ok, up2, why2 = await wait_healthy(name)
    if ok:
        shutil.rmtree(bak, ignore_errors=True)
        res = f"\n✅ Eski kod tiklandi va ishlayapti ({time.time()-t1:.1f}s)"
    else:
        b.button(text="🤖 AI fix", callback_data=f"do:{name}:fix")
        res = f"\n🚨 Eski kod ham ishga tushmadi: {html.escape(why2)}"
    b.button(text="📜 Log", callback_data=f"do:{name}:logs")
    await msg.edit_text(head + res + f"\n⏱ Jami: {time.time()-t_all:.1f}s", reply_markup=b.as_markup())


async def do_rollback(m: Message, name: str):
    d = APPS / name
    baks = sorted((BACKUPS / name).glob("*")) if (BACKUPS / name).exists() else []
    if not baks: return await m.answer("Zaxira versiya yo'q.")
    bak, t0 = baks[-1], time.time()
    msg = await m.answer(f"↩️ <b>{name}</b> → {bak.name} versiyasiga qaytarilmoqda…")
    await sh(f"systemctl stop {unit(name)}")
    await asyncio.to_thread(mirror, bak, d)
    kind, ins, run = detect(d)
    if run:
        write_unit(name, d, run)
        await sh("systemctl daemon-reload")
    await sh(f"systemctl restart {unit(name)}")
    ok, up, why = await wait_healthy(name)
    if ok: shutil.rmtree(bak, ignore_errors=True)
    _, lg = await sh(f"journalctl -u {unit(name)} -n 20 --no-pager -o cat")
    await msg.edit_text(f"{'✅ Qaytarildi' if ok else '❌ Ishlamadi: ' + html.escape(why)} — {time.time()-t0:.1f}s\n{pre(lg, 1800)}")


@r.message(Command("update"))
async def cmd_update(m: Message):
    a = (m.text or "").split()
    if len(a) != 2 or not NAME_RE.match(a[1]) or not (APPS / a[1]).is_dir():
        return await m.answer("Format: <code>/update nom</code> (nom — /apps dagi ilova)")
    WAITING[m.from_user.id] = a[1]
    await m.answer(f"📦 <b>{a[1]}</b> uchun yangi ZIP faylni yuboring.")


@r.message(Command("rollback"))
async def cmd_rollback(m: Message):
    a = (m.text or "").split()
    if len(a) != 2 or not NAME_RE.match(a[1]) or not (APPS / a[1]).is_dir():
        return await m.answer("Format: <code>/rollback nom</code>")
    await do_rollback(m, a[1])


# ───────────── AI tuzatish ─────────────
SKIP = {".venv", "node_modules", ".git", "__pycache__", "venv"}


def project_context(d: Path) -> str:
    files = [p for p in d.rglob("*") if p.is_file() and not (set(p.relative_to(d).parts) & SKIP)]
    tree = "\n".join(str(p.relative_to(d)) for p in files[:120])
    pick, total = [], 0
    pri = [p for p in files if p.suffix in {".py", ".js", ".ts", ".json", ".txt", ".env", ".sh", ".cmd", ".yml", ".yaml"}]
    pri.sort(key=lambda p: p.stat().st_size)
    for p in pri:
        s = p.read_text(errors="replace")[:12000]
        if total + len(s) > 45000: break
        pick.append(f"=== {p.relative_to(d)} ===\n{s}"); total += len(s)
    return f"FAYL DARAXTI:\n{tree}\n\nFAYLLAR:\n" + "\n\n".join(pick)


async def ai_fix(m: Message, name: str):
    if not ANTHROPIC_KEY: return await m.answer("ANTHROPIC_API_KEY .env da yo'q.")
    d = APPS / name
    if not d.is_dir(): return await m.answer("Bunday ilova yo'q.")
    msg = await m.answer("🤖 Loglar va kod tahlil qilinmoqda...")
    _, logs = await sh(f"journalctl -u {unit(name)} -n 120 --no-pager -o cat")
    from anthropic import AsyncAnthropic
    prompt = (f"Ilova '{name}' Ubuntu serverda systemd orqali ishlamoqda va muammo bor.\n\nLOG:\n{logs[-8000:]}\n\n"
              f"{project_context(d)}\n\nXatoning sababini toping va minimal tuzatish bering. "
              'FAQAT JSON qaytaring: {"explanation":"o\'zbek tilida qisqa izoh",'
              '"files":[{"path":"nisbiy/yo\'l","content":"TO\'LIQ yangi fayl matni"}],'
              '"pip":["o\'rnatilishi kerak paketlar"],"npm":[]}')
    try:
        resp = await AsyncAnthropic(api_key=ANTHROPIC_KEY).messages.create(
            model=AI_MODEL, max_tokens=8000, messages=[{"role": "user", "content": prompt}])
        txt = resp.content[0].text
        data = json.loads(txt[txt.index("{"): txt.rindex("}") + 1])
    except Exception as e:
        return await msg.edit_text(f"AI xatosi: {html.escape(str(e))}")
    pid = uuid.uuid4().hex[:8]
    PENDING[pid] = {"name": name, **data}
    files = ", ".join(f["path"] for f in data.get("files", [])) or "—"
    b = InlineKeyboardBuilder()
    b.button(text="✅ Qo'llash", callback_data=f"ai:{pid}:yes"); b.button(text="❌ Bekor", callback_data=f"ai:{pid}:no")
    await msg.edit_text(f"🤖 <b>Tahlil</b>\n{html.escape(data.get('explanation',''))}\n\n"
                        f"Fayllar: <code>{html.escape(files)}</code>\nPaketlar: {data.get('pip') or data.get('npm') or '—'}",
                        reply_markup=b.as_markup())


@r.message(Command("fix"))
async def cmd_fix(m: Message):
    a = (m.text or "").split()
    if len(a) != 2 or not NAME_RE.match(a[1]): return await m.answer("Format: <code>/fix nom</code>")
    await ai_fix(m, a[1])


@r.callback_query(F.data.startswith("ai:"))
async def cb_ai(c: CallbackQuery):
    _, pid, ans = c.data.split(":")
    p = PENDING.pop(pid, None)
    if not p or ans == "no": return await c.message.edit_text("Bekor qilindi.")
    name, d = p["name"], (APPS / p["name"]).resolve()
    bak = d / f".bak-{int(time.time())}"
    for f in p.get("files", []):
        t = (d / f["path"]).resolve()
        if d not in t.parents: continue  # papkadan tashqariga yozishni bloklash
        if t.exists():
            (bak / f["path"]).parent.mkdir(parents=True, exist_ok=True); shutil.copy2(t, bak / f["path"])
        t.parent.mkdir(parents=True, exist_ok=True); t.write_text(f["content"])
    out = ""
    pk = [x for x in p.get("pip", []) if re.fullmatch(r"[A-Za-z0-9_.\-\[\]=<>!~,]+", x)]
    nk = [x for x in p.get("npm", []) if re.fullmatch(r"[@A-Za-z0-9_./\-]+", x)]
    if pk: out += (await sh(f".venv/bin/pip install -q {' '.join(pk)}", cwd=d))[1]
    if nk: out += (await sh(f"npm install {' '.join(nk)}", cwd=d))[1]
    await sh(f"systemctl restart {unit(name)}"); await asyncio.sleep(4)
    _, st = await sh(f"systemctl is-active {unit(name)}")
    _, lg = await sh(f"journalctl -u {unit(name)} -n 15 --no-pager -o cat")
    await c.message.edit_text(f"{'✅' if st.strip()=='active' else '❌'} {name}: {st.strip()}\n"
                              f"(zaxira: <code>{bak.name}</code>)\n{pre(out + lg)}")


async def main():
    asyncio.create_task(alert_loop())
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
