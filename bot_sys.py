"""Bot: jarayonlar, portlar, xizmatlar — core yadrosi ustida."""
import asyncio, os

from aiogram import F, Router
from aiogram.types import CallbackQuery

import core
from common import B, K, SVC_RE, edit, esc, pre

router = Router()


# ───────── jarayonlar ─────────
def render(sort: str):
    s = core.status()
    rows = core.procs_list(sort, 12)
    lines = [f"{'PID':>6} {'USER':<8} {'CPU%':>5} {'MEM%':>5} {'RSS':>6}  NAME"]
    for p in rows:
        lines.append(f"{p['pid']:>6} {p['user'][:8]:<8} {p['cpu']:5.1f} {p['mem']:5.1f} {p['rss'] / 1048576:5.0f}M  {p['name'][:18]}")
    text = (f"🔥 <b>Jarayonlar</b> — jami {s['procs']}, CPU {s['cpu']:.0f}%\n"
            f"Saralash: <b>{'CPU' if sort == 'cpu' else 'RAM'}</b>\n<pre>{esc(chr(10).join(lines))}</pre>"
            "To'xtatish uchun tanlang 👇")
    kb, row = [], []
    for p in rows[:8]:
        row.append(B(f"❌ {p['name'][:12]} {p['pid']}", f"pk:{p['pid']}"))
        if len(row) == 2:
            kb.append(row); row = []
    if row: kb.append(row)
    kb.append([B("CPU ⇅", "pr:cpu"), B("RAM ⇅", "pr:mem"), B("🔄", f"pr:{sort}")])
    kb.append([B("🌐 Portlar", "ports"), B("⬅️ Menyu", "menu"), B("❌ Yopish", "x")])
    return text, K(kb)


@router.callback_query(F.data.startswith("pr:"))
async def cb_pr(c: CallbackQuery):
    sort = c.data[3:] if c.data[3:] in ("cpu", "mem") else "cpu"
    text, kb = render(sort)
    await edit(c.message, text, reply_markup=kb)


@router.callback_query(F.data.startswith("pk:"))
async def cb_pk(c: CallbackQuery):
    pid = int(c.data[3:])
    back = K([[B("⬅️ Ro'yxat", "pr:cpu")]])
    d = await asyncio.to_thread(core.proc_detail, pid)
    if not d:
        return await edit(c.message, "Bu jarayon allaqachon yo'q.", reply_markup=back)
    if d["risky"] or pid == 1:
        return await edit(c.message, f"⛔ {esc(d['name'])} ni to'xtatish xavfli (serverga kira olmay qolishingiz mumkin).",
                          reply_markup=back)
    await edit(c.message,
               f"⚠️ <b>{esc(d['name'])}</b> (harakat <code>{pid}</code>) to'xtatilsinmi?\n"
               f"Egasi: {esc(d['user'])} • RAM {d['rss'] / 1048576:.0f}MB\n<code>{esc(d['cmd'])}</code>\n\n"
               "ℹ️ Agar bu systemd xizmati bo'lsa, u o'zi qayta ishga tushishi mumkin — xizmatni "
               "«Xizmatlar» yoki «Ilovalar» orqali to'xtating.",
               reply_markup=K([[B("🛑 To'xtatish", f"pks:{pid}:15"), B("💀 Majburan", f"pks:{pid}:9")],
                               [B("❌ Bekor", "pr:cpu")]]))


@router.callback_query(F.data.startswith("pks:"))
async def cb_pks(c: CallbackQuery):
    _, pid, sig = c.data.split(":")
    pid, sig = int(pid), int(sig)
    back = K([[B("⬅️ Ro'yxat", "pr:cpu")]])
    err = await asyncio.to_thread(core.proc_kill, pid, sig)
    if err:
        return await edit(c.message, f"⛔ {esc(err)}", reply_markup=back)
    await asyncio.sleep(1)
    d = await asyncio.to_thread(core.proc_detail, pid)
    await edit(c.message, f"{pid}: {'hali ishlayapti (kuting yoki «Majburan»)' if d else 'to‘xtadi ✅'}",
               reply_markup=back)


# ───────── portlar ─────────
@router.callback_query(F.data == "ports")
async def cb_ports(c: CallbackQuery):
    try:
        rows = await asyncio.to_thread(core.ports)
        note = ""
    except Exception as e:
        rows, note = [], f"Ruxsat yo'q: {e}"
    lines = [f"{'PORT':>6} {'MANZIL':<15} {'PID':>6}  JARAYON"]
    for r in rows[:45]:
        lines.append(f"{r['port']:>6} {r['ip'][:15]:<15} {r['pid'] or '-':>6}  {r['name'][:20]}")
    await edit(c.message, f"🌐 <b>Ochiq portlar</b> ({len(rows)})\n{pre(chr(10).join(lines))}{note}",
               reply_markup=K([[B("🔄", "ports"), B("🔥 Jarayonlar", "pr:cpu")],
                               [B("⬅️ Menyu", "menu"), B("❌ Yopish", "x")]]))


# ───────── xizmatlar ─────────
@router.callback_query(F.data == "svcs")
async def cb_svcs(c: CallbackQuery):
    names = [x["name"] for x in await core.services()]
    kb, row = [], []
    for n in names[:40]:
        row.append(B(f"🟢 {n[:22]}", f"sc:{n}"))
        if len(row) == 2:
            kb.append(row); row = []
    if row: kb.append(row)
    kb.append([B("🔄", "svcs"), B("⬅️ Menyu", "menu"), B("❌ Yopish", "x")])
    await edit(c.message, f"⚙️ <b>Ishlayotgan xizmatlar</b> ({len(names)})\nBoshqasi: <code>/svc status nom</code>",
               reply_markup=K(kb))


async def svc_card(c: CallbackQuery, n: str, note: str = ""):
    if not SVC_RE.match(n): return
    d = await core.service_info(n)
    body = f"MainPID={d['pid']}  NRestarts={d['restarts']}\nActiveEnter={d['since']}"
    await edit(c.message, f"⚙️ <b>{esc(n)}</b> — {esc(d['state'])}\n{pre(body, 600)}{note}",
               reply_markup=K([[B("▶️ Start", f"sa:start:{n}"), B("⏹ Stop", f"sa:stop:{n}"), B("🔄 Restart", f"sa:restart:{n}")],
                               [B("📜 Log", f"sl:{n}"), B("✅ Enable", f"sa:enable:{n}"), B("🚫 Disable", f"sa:disable:{n}")],
                               [B("⬅️ Xizmatlar", "svcs"), B("❌ Yopish", "x")]]))


@router.callback_query(F.data.startswith("sc:"))
async def cb_sc(c: CallbackQuery):
    await svc_card(c, c.data[3:])


@router.callback_query(F.data.startswith("sa:"))
async def cb_sa(c: CallbackQuery):
    _, a, n = c.data.split(":", 2)
    if a not in {"start", "stop", "restart", "enable", "disable"} or not SVC_RE.match(n):
        return
    r = await core.service_act(n, a)
    if "blocked" in r:
        return await svc_card(c, n, f"\n⛔ {esc(r['blocked'])}")
    await svc_card(c, n, f"\n{'✅' if r['done'] else '⚠️'} {a}" + (f"\n{pre(r['out'], 400)}" if not r["done"] else ""))


@router.callback_query(F.data.startswith("sl:"))
async def cb_sl(c: CallbackQuery):
    n = c.data[3:]
    if SVC_RE.match(n):
        await c.message.answer(f"📜 <b>{esc(n)}</b>\n{pre(await core.journal(n, 50))}")
