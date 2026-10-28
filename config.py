"""Sozlamalar va sof yordamchilar (aiogram'siz — bot ham, web ham import qiladi)."""
import asyncio, html, os, re, shlex, signal
from asyncio.subprocess import PIPE, STDOUT
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()
ADMINS = {int(x) for x in os.environ.get("ADMIN_IDS", "").split(",") if x.strip().isdigit()}
if not ADMINS or not os.getenv("BOT_TOKEN", "").count(":"):
    raise SystemExit(".env xato: ADMIN_IDS (Telegram ID raqami) va BOT_TOKEN (123:ABC... ko'rinishida) to'g'ri to'ldirilishi kerak.")
APPS = Path(os.getenv("APPS_DIR", "/opt/apps"))
TMP = Path("/tmp/vpsbot")
TRASH = Path(os.getenv("TRASH_DIR", "/var/tmp/vpsbot-trash"))
for _d in (APPS, TMP, TRASH):
    _d.mkdir(parents=True, exist_ok=True)

# Nom nuqta bilan boshlanmaydi (".." va yashirin papkalardan himoya); 50 belgi — callback_data 64 baytga sig'ishi uchun
NAME_RE = re.compile(r"^[A-Za-z0-9_@][A-Za-z0-9_.@-]{0,49}$")
SVC_RE = re.compile(r"^[A-Za-z0-9_@][A-Za-z0-9_.@-]{0,39}$")
RISKY = {"ssh", "sshd", "networking", "systemd-networkd", "NetworkManager", "dbus", "systemd-logind"}

esc = html.escape
q = shlex.quote


def bar(p: float) -> str:
    n = max(0, min(10, int(p / 10)))
    return "█" * n + "░" * (10 - n) + f" {p:.0f}%"


def pre(text: str, limit: int = 3500) -> str:
    text = (text or "").strip() or "(bo'sh)"
    if len(text) > limit:
        text = "…" + text[-limit:]
    return f"<pre>{esc(text)}</pre>"


def _kill(p):
    try:
        os.killpg(p.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass


async def sh(cmd: str, cwd=None, timeout: int = 300, env: dict | None = None) -> tuple[int, str]:
    """Buyruqni alohida sessiyada bajaradi; (exit_code, chiqish) qaytaradi. Timeout — 124."""
    p = await asyncio.create_subprocess_shell(
        cmd, cwd=cwd, stdout=PIPE, stderr=STDOUT, start_new_session=True, env=env)
    try:
        out, _ = await asyncio.wait_for(p.communicate(), timeout)
    except asyncio.TimeoutError:
        _kill(p)
        return 124, "⏱ Vaqt tugadi (timeout)"
    except asyncio.CancelledError:
        _kill(p)
        raise
    return p.returncode or 0, out.decode(errors="replace")
