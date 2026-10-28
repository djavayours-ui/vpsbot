"""Tizim yadrosi: monitoring, jarayonlar, portlar, xizmatlar, docker, disk, terminal.
Aiogram'siz — bot ham, web API ham shu funksiyalarni ishlatadi."""
import asyncio, os, signal, time
from collections import deque

import psutil

from config import APPS, RISKY, SVC_RE, TRASH, TMP, q, sh

SNAP = {"t": 0.0, "cpu": [], "procs": []}
HIST = deque(maxlen=60)      # oxirgi ~3 daqiqa CPU (sparkline + alert o'rtachasi)
NET_H = deque(maxlen=60)     # (t, recv, sent) — tezlikni hisoblash uchun
ALERT_THRESHOLD = int(os.getenv("ALERT_THRESHOLD", "90"))


# ───────── fon sampler ─────────
def sample():
    cpu = psutil.cpu_percent(None, percpu=True)
    rows = []
    for p in psutil.process_iter(["pid", "name", "username", "cpu_percent", "memory_percent", "memory_info"]):
        i = p.info
        mi = i.get("memory_info")
        rows.append((i["pid"], i.get("name") or "?", i.get("username") or "?",
                     i.get("cpu_percent") or 0.0, i.get("memory_percent") or 0.0, mi.rss if mi else 0))
    if cpu:
        avg = sum(cpu) / len(cpu)
        HIST.append(round(avg, 1))
    net = psutil.net_io_counters()
    NET_H.append((time.time(), net.bytes_recv, net.bytes_sent))
    SNAP.update(t=time.time(), cpu=cpu, procs=rows)


def get():
    if time.time() - SNAP["t"] > 15:  # sampler o'chib qolgan bo'lsa — o'zimiz o'lchaymiz
        sample()
    return SNAP


def cpu_avg() -> float:
    get()
    return sum(HIST) / len(HIST) if HIST else 0.0


async def sampler():
    await asyncio.to_thread(sample)
    while True:
        await asyncio.sleep(3)
        try:
            await asyncio.to_thread(sample)
        except Exception:
            pass


# ───────── holat ─────────
def status() -> dict:
    snap = get()
    cpu = snap["cpu"] or [0.0]
    vm, sw, du = psutil.virtual_memory(), psutil.swap_memory(), psutil.disk_usage("/")
    net = psutil.net_io_counters()
    try:
        t = psutil.sensors_temperatures()
        temp = list(t.values())[0][0].current if t else None
    except Exception:
        temp = None
    m = lambda o: {"p": round(o.percent, 1), "u": o.used, "t": o.total}
    # net tezligi (oxirgi namunalar orasidagi farq)
    rx = tx = 0.0
    if len(NET_H) >= 2:
        (t0, r0, s0), (t1, r1, s1) = NET_H[0], NET_H[-1]
        dt = max(t1 - t0, 1e-6)
        rx, tx = max(r1 - r0, 0) / dt, max(s1 - s0, 0) / dt
    top = sorted(((c, mm, n, pid) for pid, n, _u, c, mm, _r in snap["procs"]), reverse=True)[:6]
    try:
        la = list(os.getloadavg())
    except OSError:
        la = [0.0, 0.0, 0.0]
    return {"cpu": round(sum(cpu) / len(cpu), 1), "cores": len(cpu), "percpu": cpu,
            "load": [round(x, 2) for x in la], "ram": m(vm), "swap": m(sw), "disk": m(du),
            "net": {"r": net.bytes_recv, "s": net.bytes_sent, "rx": round(rx), "tx": round(tx)},
            "temp": temp, "up": time.time() - psutil.boot_time(), "hist": list(HIST),
            "top": [{"name": n, "pid": pid, "cpu": round(c, 1), "mem": round(mm, 1)} for c, mm, n, pid in top],
            "procs": len(snap["procs"]), "alert": ALERT_THRESHOLD}


def procs_list(sort: str = "cpu", limit: int = 40) -> list[dict]:
    s = get()
    idx = 3 if sort == "cpu" else 4
    rows = sorted(s["procs"], key=lambda r: r[idx], reverse=True)[:limit]
    return [{"pid": p, "name": n, "user": u, "cpu": round(c, 1), "mem": round(mm, 1), "rss": r}
            for p, n, u, c, mm, r in rows]


def proc_detail(pid: int) -> dict | None:
    try:
        p = psutil.Process(pid)
        with p.oneshot():
            return {"pid": pid, "name": p.name(), "user": p.username(),
                    "rss": p.memory_info().rss, "cmd": " ".join(p.cmdline())[:400],
                    "status": p.status(), "created": p.create_time(),
                    "risky": p.name() in RISKY}
    except psutil.Error:
        return None


def proc_kill(pid: int, sig: int = signal.SIGTERM) -> str:
    """'' — muvaffaqiyat, aks holda xabar."""
    if pid in (1, os.getpid()) or sig not in (signal.SIGTERM, signal.SIGKILL, 9, 15):
        return "Bu jarayonni to'xtatib bo'lmaydi (tizim yoki panelning o'zi)."
    try:
        p = psutil.Process(pid)
        if p.name() in RISKY:
            return "Bu jarayon xavfli: serverga kira olmay qolishingiz mumkin."
        p.send_signal(sig)
        return ""
    except psutil.NoSuchProcess:
        return ""
    except psutil.Error as e:
        return str(e)


# ───────── portlar ─────────
def ports() -> list[dict]:
    out = {}
    for cn in psutil.net_connections(kind="inet"):
        if cn.status == psutil.CONN_LISTEN and cn.laddr:
            name = "?"
            if cn.pid:
                try: name = psutil.Process(cn.pid).name()
                except Exception: pass
            out[(cn.laddr.port, cn.pid)] = (cn.laddr.ip, name)
    return [{"port": port, "pid": pid, "ip": ip, "name": name} for (port, pid), (ip, name) in sorted(out.items())]


# ───────── disk / docker ─────────
async def disk() -> dict:
    _, df = await sh("df -h -x tmpfs -x devtmpfs -x squashfs -x overlay | head -15")
    _, du = await sh(f"du -sh {q(str(APPS))} {q(str(TRASH))} {q(str(TMP))} /var/log/journal 2>/dev/null", timeout=60)
    u = psutil.disk_usage("/")
    return {"df": df.strip(), "du": du.strip(), "p": u.percent, "u": u.used, "t": u.total}


async def clean() -> dict:
    before = psutil.disk_usage("/").used
    await sh("journalctl --vacuum-size=200M; apt-get clean; docker image prune -f", timeout=300)
    freed = (before - psutil.disk_usage("/").used) / 1024**2
    return {"freed": round(max(freed, 0)), "p": psutil.disk_usage("/").percent}


async def docker() -> dict:
    code, out = await sh("docker ps -a --format 'table {{.Names}}\\t{{.Status}}\\t{{.Ports}}'", timeout=30)
    return {"text": out.strip() or ("docker topilmadi" if code else ""), "ok": code == 0}


# ───────── systemd xizmatlari ─────────
async def services() -> list[dict]:
    _, out = await sh("systemctl list-units --type=service --state=running --no-pager --plain --no-legend "
                      "| awk '{print $1}'", timeout=30)
    names = sorted(n[:-8] for n in out.split() if n.endswith(".service") and len(n) - 8 <= 40)
    return [{"name": n} for n in names]


async def service_info(n: str) -> dict:
    if not SVC_RE.match(n):
        raise ValueError("Xizmat nomi yaroqsiz.")
    _, out = await sh(f"systemctl is-active {n}; systemctl show {n} -p MainPID,NRestarts,ActiveEnterTimestamp,LoadState --no-pager",
                      timeout=30)
    first, _, rest = out.partition("\n")
    kv = dict(l.split("=", 1) for l in rest.splitlines() if "=" in l)
    return {"name": n, "state": first.strip(), "pid": kv.get("MainPID", ""), "restarts": kv.get("NRestarts", "0"),
            "since": kv.get("ActiveEnterTimestamp", "").strip(), "load": kv.get("LoadState", ""), "risky": n in RISKY}


async def service_act(n: str, a: str) -> dict:
    if a not in {"start", "stop", "restart", "enable", "disable"} or not SVC_RE.match(n):
        raise ValueError("Amal yaroqsiz.")
    if a in ("stop", "disable") and n in RISKY:
        return {"blocked": "Bu xizmatni to'xtatish xavfli (serverga kira olmay qolishingiz mumkin)."}
    code, out = await sh(f"systemctl {a} {n} --no-pager; sleep 1", timeout=90)
    return {"done": code == 0, "out": out[-1200:]}


async def journal(n: str, lines: int = 60) -> str:
    if not SVC_RE.match(n):
        raise ValueError("Xizmat nomi yaroqsiz.")
    _, out = await sh(f"journalctl -u {n} -n {min(lines, 300)} --no-pager -o cat", timeout=30)
    return out.strip() or "(bo'sh)"


# ───────── terminal / reboot ─────────
async def shell(cmd: str, timeout: int = 60) -> dict:
    if not cmd.strip():
        raise ValueError("Buyruq bo'sh.")
    code, out = await sh(cmd, timeout=timeout)
    return {"code": code, "out": out[-12000:]}


async def reboot():
    await sh("systemctl reboot", timeout=10)
