/* ═══════════ VPS Panel · Mini App ═══════════ */
const tg = window.Telegram?.WebApp;
tg?.ready(); tg?.expand?.(); tg?.disableVerticalSwipes?.();
try { tg?.setHeaderColor('#171A1E'); tg?.setBackgroundColor('#171A1E'); } catch (e) {}

const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];
const hap = (t) => { try { tg?.HapticFeedback?.impactOccurred(t || 'light'); } catch (e) {} };
const notify = (t) => { try { tg?.HapticFeedback?.notificationOccurred(t); } catch (e) {} };
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const GB = 1073741824, MB = 1048576;
const gb = x => (x / GB).toFixed(1);
const sz = n => { const u = ['B', 'KB', 'MB', 'GB', 'TB']; let i = 0; while (n >= 1024 && i < 4) { n /= 1024; i++; } return (i ? n.toFixed(1) : n.toFixed(0)) + u[i]; };
const spd = b => b >= MB ? (b / MB).toFixed(1) + ' MB/s' : (b / 1024).toFixed(0) + ' KB/s';
const dur = s => { s = Math.max(0, Math.floor(s)); const d = Math.floor(s / 86400), h = Math.floor(s % 86400 / 3600), m = Math.floor(s % 3600 / 60);
  return (d ? d + ' kun ' : '') + (d || h ? h + ' soat ' : '') + m + ' daq'; };
const ago = t => { const s = Math.floor(Date.now() / 1000 - t); if (s < 60) return 'hozir'; if (s < 3600) return Math.floor(s / 60) + ' daq oldin';
  if (s < 86400) return Math.floor(s / 3600) + ' soat oldin'; return Math.floor(s / 86400) + ' kun oldin'; };
const ICON = {
  play: '<path d="M7 4l12 8-12 8V4z"/>', stop: '<rect x="6" y="6" width="12" height="12" rx="2"/>',
  restart: '<path d="M20 11a8 8 0 1 0-2.3 5.7"/><path d="M20 4v7h-7"/>',
  log: '<path d="M4 6h16M4 12h16M4 18h10"/>', ai: '<path d="M12 3l1.9 4.6L18.5 9.5 13.9 11.4 12 16l-1.9-4.6L5.5 9.5l4.6-1.9L12 3z"/><path d="M18 16l.9 2.1L21 19l-2.1.9L18 22l-.9-2.1L15 19l2.1-.9L18 16z"/>',
  zip: '<path d="M12 16V4"/><path d="M7 9l5-5 5 5"/><path d="M4 16v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2"/>',
  back: '<path d="M15 18l-6-6 6-6"/>', trash: '<path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13"/>',
  key: '<circle cx="8" cy="12" r="4"/><path d="M12 12h9M17 12v3M20 12v2"/>',
  folder: '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7z"/>',
  file: '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8l-5-5z"/><path d="M14 3v5h5"/>',
  undo: '<path d="M9 14L4 9l5-5"/><path d="M4 9h11a5 5 0 0 1 0 10h-3"/>',
  dl: '<path d="M12 4v12"/><path d="M7 11l5 5 5-5"/><path d="M4 20h16"/>',
  edit: '<path d="M4 20h4L20 8l-4-4L4 16v4z"/>', save: '<path d="M5 12l5 5L20 6"/>',
  close: '<path d="M6 6l12 12M18 6L6 18"/>', refresh: '<path d="M20 11a8 8 0 1 0-2.3 5.7"/><path d="M20 4v7h-7"/>',
  term: '<rect x="3" y="4" width="18" height="16" rx="3"/><path d="M7 9l3 3-3 3M13 15h4"/>',
  power: '<path d="M12 3v8"/><path d="M6.4 6.4a8 8 0 1 0 11.2 0"/>',
  plus: '<path d="M12 5v14M5 12h14"/>', chart: '<path d="M4 19V5M4 19h16"/><path d="M8 16v-5M12 16V8M16 16v-3"/>',
  code: '<path d="M8 6l-5 6 5 6M16 6l5 6-5 6"/>', server: '<rect x="3" y="4" width="18" height="7" rx="2"/><rect x="3" y="13" width="18" height="7" rx="2"/><path d="M7 7.5h.01M7 16.5h.01"/>'
};
const svg = (k, cls) => `<svg class="i ${cls || ''}" viewBox="0 0 24 24">${ICON[k] || ''}</svg>`;

/* ───────── API ───────── */
const DEMO = !tg?.initData;
const R = (a, b) => a + Math.random() * (b - a);
const state = { tab: 'st', sort: 'cpu', apps: [], files: [], path: {}, clip: null, demoApps: null };

function mock(p, post, body) {
  const G = GB;
  if (/^status$/.test(p)) return { cpu: R(19, 44), cores: 4, percpu: [R(10, 40), R(20, 55), R(15, 45), R(12, 38)],
    load: [R(.4, 1.4), R(.5, 1.2), R(.6, 1.1)], ram: { p: R(52, 66), u: 2.4 * G, t: 4 * G }, swap: { p: R(4, 14), u: .2 * G, t: 2 * G },
    disk: { p: R(42, 51), u: 23.4 * G, t: 50 * G }, net: { r: 41.6 * G, s: 12.3 * G, rx: R(2e5, 2e6), tx: R(4e4, 4e5) },
    temp: R(41, 56), up: 3 * 86400 + 4 * 3600 + 900, hist: Array.from({ length: 40 }, () => R(15, 55)), alert: 90,
    top: [['python3', 1214, 18.4, 9.1], ['node', 980, 11.2, 6.4], ['dockerd', 764, 4.1, 3.2], ['nginx', 640, 1.4, .8], ['postgres', 812, 2.7, 12.4]]
      .map(([name, pid, cpu, mem]) => ({ name, pid, cpu, mem })), procs: 168 };
  if (/^apps$/.test(p)) return state.demoApps || (state.demoApps = [
    { name: 'savdo-bot', state: 'active', mode: 'systemd', kind: 'python', avg: 24.3, backups: 2 },
    { name: 'api-server', state: 'active', mode: 'docker', kind: 'docker', avg: 41.7, backups: 1 },
    { name: 'parser', state: 'activating', mode: 'systemd', kind: 'python', avg: null, backups: 0 },
    { name: 'eski-bot', state: 'inactive', mode: 'systemd', kind: 'python', avg: 18.9, backups: 3 }]);
  if (/^apps\/[\w.-]+$/.test(p)) { const n = p.split('/')[1];
    return { name: n, state: 'active', mode: 'systemd', kind: 'python', backups: ['20261026-101500', '20261025-183000'],
      avg: 24.3, kind2: '', size: 12 * MB, restarts: 0, pid: 1214, since: 'Sun 2026-10-25 18:31:04 UTC' }; }
  if (/ping|^me$/.test(p)) return { id: 0, name: 'Demo', username: 'demo', admins: [], version: 2 };
  if (/^apps\/[\w.-]+\/logs/.test(p)) return { text: 'INFO  bot ishga tushdi (v4.2)\nINFO  polling boshlandi\nINFO  12 ta yangi xabar qabul qilindi\nINFO  webhook javob 200 (42ms)\nWARN  baza ulanishi 1 marta qayta tiklandi\nINFO  navbat: 0 ta kutilayotgan vazifa' };
  if (/^apps\/[\w.-]+\/env/.test(p)) return post ? { saved: ['BOT_TOKEN'], bad: [] } :
    { count: 4, keys: [{ key: 'BOT_TOKEN', value: '1234567:AA••H8xQ', masked: '12••••••••Q' }, { key: 'ADMIN_IDS', value: '654321', masked: '65••21' },
      { key: 'DB_URL', value: 'postgres://bot:pw@127.0.0.1:5432/savdo', masked: 'po••••••••••do' }, { key: 'TZ', value: 'Asia/Tashkent', masked: 'As••••••••nt' }] };
  if (/^procs$/.test(p)) return [['python3', 1214, 18.4, 9.1, 372 * MB], ['node', 980, 11.2, 6.4, 261 * MB], ['dockerd', 764, 4.1, 3.2, 131 * MB],
    ['postgres', 812, 2.7, 12.4, 507 * MB], ['nginx', 640, 1.4, .8, 32 * MB], ['cloudflared', 1502, .8, 1.2, 49 * MB],
    ['systemd-journald', 402, .5, 1.9, 78 * MB], ['cron', 710, .1, .3, 12 * MB]]
    .map(([name, pid, cpu, mem, rss]) => ({ name, pid, user: 'root', cpu, mem, rss }));
  if (/^procs\/\d+/.test(p)) return { pid: +p.split('/')[1], name: 'python3', user: 'root', rss: 372 * MB, status: 'sleeping',
    created: Date.now() / 1000 - 7200, risky: false, cmd: '/opt/apps/savdo-bot/.venv/bin/python bot.py' };
  if (/^ports$/.test(p)) return [{ port: 22, pid: 640, ip: '0.0.0.0', name: 'sshd' }, { port: 80, pid: 640, ip: '0.0.0.0', name: 'nginx' },
    { port: 443, pid: 640, ip: '0.0.0.0', name: 'nginx' }, { port: 5432, pid: 812, ip: '127.0.0.1', name: 'postgres' },
    { port: 8080, pid: 1214, ip: '127.0.0.1', name: 'python3' }];
  if (/^services$/.test(p)) return ['ssh', 'nginx', 'docker', 'postgresql', 'cron', 'systemd-journald'].map(name => ({ name }));
  if (/^services\/[\w.-]+$/.test(p)) { const n = p.split('/')[1]; return { name: n, state: 'active', pid: '640', restarts: '0', since: 'Sun 2026-10-25 18:30:11 UTC', load: 'loaded', risky: n === 'ssh' }; }
  if (/^services\/[\w.-]+\/journal/.test(p)) return { text: 'Oct 28 09:12:04 host nginx[640]: 127.0.0.1 - GET /api/status 200\nOct 28 09:12:31 host nginx[640]: 127.0.0.1 - GET / 200 4ms' };
  if (/^disk$/.test(p)) return { p: 46.8, u: 23.4 * GB, t: 50 * GB, df: 'Filesystem Size Used Avail Use% Mounted on\n/dev/vda1 50G 23G 25G 47% /\n/dev/vda15 105M 6.1M 99M 6% /boot/efi', du: '12G /opt/apps\n48M /var/tmp/vpsbot-trash\n2.1M /tmp/vpsbot' };
  if (/^docker$/.test(p)) return { ok: true, text: 'NAMES STATUS PORTS\napi-server Up 3 days 0.0.0.0:3000->3000/tcp\nredis Up 3 days 6379/tcp' };
  if (/^files\/roots$/.test(p)) return { roots: [{ key: 'apps', label: 'Ilovalar', path: '/opt/apps', token: 'apps', exists: true },
    { key: 'root', label: '/root', path: '/root', token: 'root', exists: true }, { key: 'log', label: '/var/log', path: '/var/log', token: 'log', exists: true },
    { key: 'etc', label: '/etc', path: '/etc', token: 'etc', exists: true }, { key: 'www', label: '/var/www', path: '/var/www', token: 'www', exists: false },
    { key: 'slash', label: '/', path: '/', token: 'slash', exists: true }, { key: 'trash', label: 'Savat', path: '/var/tmp/vpsbot-trash', token: 'trash', exists: true }], trash: '/var/tmp/vpsbot-trash' };
  if (/^files\/list/.test(p)) return { path: '/opt/apps/savdo-bot', token: 'apps', name: 'savdo-bot', page: 0, pages: 1, parent: 'apps', dirs: 2, files: 4, error: '',
    items: [{ name: '.venv', dir: true, token: 'd1' }, { name: 'data', dir: true, token: 'd2' },
      { name: 'bot.py', dir: false, token: 'f1', size: 8412, size_h: '8.2KB', mode: '644', mtime: Date.now() / 1000 - 3600 },
      { name: 'requirements.txt', dir: false, token: 'f2', size: 74, size_h: '74B', mode: '644', mtime: Date.now() / 1000 - 86000 },
      { name: '.env', dir: false, token: 'f3', size: 210, size_h: '210B', mode: '600', mtime: Date.now() / 1000 - 4000 },
      { name: 'savdo.db', dir: false, token: 'f4', size: 1.2 * MB, size_h: '1.2MB', mode: '644', mtime: Date.now() / 1000 - 7200 }] };
  if (/^files\/stat/.test(p)) return { path: '/opt/apps/savdo-bot/bot.py', token: 'f1', parent: 'apps', name: 'bot.py', dir: false, size: 8412, size_h: '8.2KB', mode: '644', owner: 'root', mtime: Date.now() / 1000 - 3600, app: 'savdo-bot' };
  if (/^files\/read/.test(p)) return { text: 'import asyncio\nfrom aiogram import Bot, Dispatcher\n\nTOKEN = "***"\n\nasync def main():\n    bot = Bot(TOKEN)\n    dp = Dispatcher()\n    await dp.start_polling(bot)\n\nif __name__ == "__main__":\n    asyncio.run(main())\n', truncated: false };
  if (/^jobs/.test(p)) return { id: 'demo', kind: 'deploy', title: 'O‘rnatilmoqda: yangi-bot', state: 'ok', pct: 100, elapsed: 27.4, remain: 0,
    steps: [{ text: 'ZIP ochilmoqda', secs: 3.1 }, { text: 'Kutubxonalar o‘rnatilmoqda (python)', secs: 18.2 }, { text: 'Tekshirilmoqda (~10s)', secs: 6.1 }],
    cur: '', error: '', log: 'INFO  bot ishga tushdi\nINFO  polling boshlandi', result: { up: 1.8, done: true }, meta: { name: 'yangi-bot' } };
  return { ok: true, done: true, out: 'Bajarildi ✓', text: 'Bajarildi ✓', freed: 412, cancelled: true, saved: [], bad: [] };
}

async function api(path, { post, body, form, method } = {}) {
  if (DEMO) { await new Promise(r => setTimeout(r, 90)); return mock(path, post, body); }
  const opt = { method: method || (post ? 'POST' : 'GET'), headers: { 'X-Init': tg?.initData || '' } };
  if (form) opt.body = form;
  else if (body !== undefined) { opt.headers['Content-Type'] = 'application/json'; opt.body = JSON.stringify(body); }
  const r = await fetch('/api/' + path, opt);
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.error || 'Xato ' + r.status);
  return j;
}

/* ───────── toast / error ───────── */
let tmr;
function toast(msg, bad) {
  const t = $('#toast'); t.textContent = msg; t.className = 'toast on' + (bad ? ' bad' : '');
  clearTimeout(tmr); tmr = setTimeout(() => t.className = 'toast', 2400);
  notify(bad ? 'error' : 'success');
}
function err(m) {
  const e = $('#er'); e.textContent = m || ''; e.classList.toggle('on', !!m);
  $('#ld').className = 'dot' + (m ? ' bad' : '');
}

/* ───────── sheet ───────── */
let sheetOnClose = null;
function sheet(html, onClose) {
  $('#sheetBody').innerHTML = html;
  sheetOnClose = onClose || null;
  $('#scrim').classList.add('on'); $('#sheet').classList.add('on');
  try { tg?.BackButton?.show?.(); } catch (e) {}
}
function closeSheet() {
  $('#scrim').classList.remove('on'); $('#sheet').classList.remove('on');
  try { tg?.BackButton?.hide?.(); } catch (e) {}
  if (sheetOnClose) { const f = sheetOnClose; sheetOnClose = null; f(); }
  setTimeout(() => { if (!$('#sheet').classList.contains('on')) $('#sheetBody').innerHTML = ''; }, 380);
}
$('#scrim').onclick = closeSheet;
try { tg?.BackButton?.onClick?.(closeSheet); } catch (e) {}

/* ───────── Holat ───────── */
const C = 2 * Math.PI * 86;
const MET = [['ram', 'Xotira (RAM)'], ['swap', 'Swap'], ['disk', 'Disk']];
$('#mt').innerHTML = MET.map(([k, l]) => `<div><div class="r"><span>${l}</span><span class="d" id="d-${k}"></span></div><div class="bar"><i id="b-${k}"></i></div></div>`).join('');

async function loadStatus() {
  const d = await api('status');
  $('#cpu').textContent = Math.round(d.cpu);
  const rg = $('#rg');
  rg.style.strokeDasharray = `${Math.max(d.cpu, .5) / 100 * C} 600`;
  rg.classList.toggle('hot', d.cpu > 85);
  $('#cn').textContent = `${d.cores} yadro · ${d.procs} jarayon · yuklama ${d.load.map(x => x.toFixed(2)).join(' · ')}`;
  MET.forEach(([k]) => { const o = d[k]; if (!o) return;
    $('#d-' + k).textContent = `${gb(o.u)} / ${gb(o.t)} GB · ${Math.round(o.p)}%`;
    const b = $('#b-' + k); b.style.width = Math.min(o.p, 100) + '%'; b.classList.toggle('hi', o.p > 85); });
  $('#rx').textContent = spd(d.net.rx || 0); $('#tx').textContent = spd(d.net.tx || 0);
  $('#nett').textContent = 'jami ↓' + gb(d.net.r) + ' GB'; $('#nett2').textContent = 'jami ↑' + gb(d.net.s) + ' GB';
  $('#tp').textContent = d.temp == null ? '—' : Math.round(d.temp) + '°C';
  $('#la').textContent = d.load[0].toFixed(2);
  const h = d.hist || []; const mx = Math.max(...h, 30);
  $('#spark').innerHTML = (h.slice(-34).length ? h.slice(-34) : Array(20).fill(0))
    .map(v => `<i style="height:${Math.max(3, v / mx * 32)}px;opacity:${.35 + v / mx * .65}"></i>`).join('');
  $('#up').textContent = (DEMO ? 'Demo rejim · ' : 'Server ishlayapti · ') + dur(d.up);
  $('#toplist').innerHTML = (d.top || []).map(p => `<button class="row tight" data-pid="${p.pid}" data-name="${esc(p.name)}">
    <span class="av">${svg('code', 'sm')}</span>
    <span class="n"><b>${esc(p.name)}</b><small>PID ${p.pid}</small></span>
    <span class="e">${p.cpu.toFixed(1)}% · ${p.mem.toFixed(1)}%</span></button>`).join('');
}
$('#toplist').onclick = e => { const r = e.target.closest('[data-pid]'); if (r) { hap(); procSheet(+r.dataset.pid, r.dataset.name); } };

/* ───────── Ilovalar ───────── */
const ST = { active: ['Ishlayapti', ''], activating: ['Ishga tushmoqda', 'warn'], failed: ['Xatolik', 'bad'], inactive: ['To‘xtagan', 'off'] };

async function loadApps() {
  state.apps = await api('apps');
  $('#appsList').innerHTML = state.apps.length ? state.apps.map((a, i) => {
    const [t, c] = ST[a.state] || ST.inactive;
    return `<button class="row" data-i="${i}"><span class="dot ${c}"></span>
      <span class="n"><b>${esc(a.name)}</b><small>${t}${a.kind ? ' · ' + esc(a.kind) : ''}</small></span>
      <span class="e">${a.mode ? esc(a.mode) : '—'}${a.backups ? `<br><span style="opacity:.7">${a.backups} zaxira</span>` : ''}</span></button>`;
  }).join('') : `<div class="g empty"><b>Hali ilova yo'q</b>ZIP fayl yuboring — avtomatik o'rnatiladi.</div>`;
}
$('#appsList').onclick = e => { const r = e.target.closest('[data-i]'); if (r) { hap(); appSheet(state.apps[+r.dataset.i].name); } };
$('#deployBtn').onclick = () => { hap(); $('#zipInput').click(); };
$('#zipInput').onchange = e => { const f = e.target.files[0]; if (f) deploy(f); e.target.value = ''; };

async function deploy(file, target) {
  const fd = new FormData(); fd.append('file', file); if (target) fd.append('target', target);
  let j;
  try { j = (await api('apps/deploy?target=' + encodeURIComponent(target || ''), { post: 1, form: fd })).job; }
  catch (x) { return toast(x.message, 1); }
  jobSheet(j, () => loadApps());
}

function jobSheet(j, after) {
  j = j || {};
  let closed = false;
  const fire = (s) => { if (closed) return; closed = true; if (after) after(s); };
  const render = s => {
    const steps = (s.steps || []).map(x => `<div>✅ <span>${esc(x.text)}</span><em>${x.secs}s</em></div>`).join('');
    const cur = s.cur ? `<div class="cur">⏳ <span>${esc(s.cur)}…</span></div>` : '';
    const meta = s.state === 'run'
      ? `${s.elapsed}s o'tdi · ${s.remain > 1 ? '~' + s.remain + 's qoldi' : 'tez orada tugaydi…'}`
      : `Jami ${s.elapsed}s`;
    const st = { run: ['Jarayon ketmoqda', 'warn'], ok: ['Bajarildi', ''], bad: ['Xatolik', 'bad'], cancel: ['Bekor qilindi', 'off'] }[s.state] || ['', ''];
    const log = s.log ? `<pre>${esc(s.log)}</pre>` : '';
    const btns = s.state === 'run'
      ? `<button class="btn w ghost" id="jobCancel">Bekor qilish</button>`
      : `<button class="btn w primary" id="jobClose">Yopish</button>`;
    return `<div class="grab"></div><h2>${esc(s.title || 'Jarayon')}</h2>
      <div class="sh-sub"><span class="dot ${st[1]}"></span>${st[0]} · ${meta}</div>
      <div class="prog"><i style="width:${s.pct || 0}%"></i></div>
      <div class="steps">${steps}${cur}</div>
      ${s.error ? `<div class="sect"><h4>Sabab</h4><pre>${esc(s.error)}</pre></div>` : ''}
      ${log}
      <div class="fields" style="margin-top:16px">${btns}</div>`;
  };
  sheet(render(j));
  const bind = () => {
    const c = $('#jobCancel'), x = $('#jobClose');
    if (c) c.onclick = async () => { try { await api('jobs/' + j.id + '/cancel', { post: 1 }); toast('Bekor qilindi'); } catch (e) { toast(e.message, 1); } };
    if (x) x.onclick = () => closeSheet();
  };
  bind();
  const poll = async () => {
    if (!$('#sheet').classList.contains('on')) return;
    try {
      const s = await api('jobs/' + j.id);
      $('#sheetBody').innerHTML = render(s); bind();
      if (s.state === 'run') setTimeout(poll, 1400);
      else { notify(s.state === 'ok' ? 'success' : 'error'); fire(s); }
    } catch (e) { setTimeout(poll, 2500); }
  };
  if (j.state === 'run') setTimeout(poll, 1400);
  else fire(j);
}

async function appSheet(name) {
  let d;
  try { d = await api('apps/' + encodeURIComponent(name)); } catch (e) { return toast(e.message, 1); }
  const [t, c] = ST[d.state] || ST.inactive;
  const act = (a, ic, label) => `<button class="btn" data-a="${a}">${svg(ic)}${label}</button>`;
  sheet(`<div class="grab"></div>
    <h2>${esc(d.name)}</h2>
    <div class="sh-sub"><span class="dot ${c}"></span>${t} · ${esc(d.mode || 'boshqarilmaydi')}${d.kind ? ' · ' + esc(d.kind) : ''}${d.size ? ' · ' + sz(d.size) : ''}</div>
    <div class="acts">
      ${act('start', 'play', 'Start')}${act('stop', 'stop', 'Stop')}${act('restart', 'restart', 'Restart')}
    </div>
    <div class="acts">
      ${act('logs', 'log', 'Log')}${act('fix', 'ai', 'AI fix')}${act('zip', 'zip', 'Yangilash')}
    </div>
    <div class="acts two">
      ${act('env', 'key', 'Kalitlar')}${act('rollback', 'undo', 'Oldingi versiya')}
    </div>
    <div class="sect"><h4>Boshqaruv</h4>
      <button class="btn w ghost" data-a="open-files">${svg('folder')}Fayllarini ochish</button>
      <button class="btn w danger" style="margin-top:9px" data-a="delete">${svg('trash')}Ilovani o'chirish</button>
    </div>
    <div id="aout"></div>`);

  $('#sheetBody').onclick = async e => {
    const b = e.target.closest('[data-a]'); if (!b) return;
    const a = b.dataset.a; hap('medium');
    if (a === 'open-files') { closeSheet(); return openFiles({ key: 'apps', token: null, label: d.name, appPath: name }); }
    if (a === 'zip') { closeSheet(); const inp = document.createElement('input'); inp.type = 'file'; inp.accept = '.zip';
      inp.onchange = () => { if (inp.files[0]) deploy(inp.files[0], name); }; inp.click(); return; }
    if (a === 'logs') {
      $('#aout').innerHTML = `<div class="sect"><h4>Loglar</h4><pre id="lg">Yuklanmoqda…</pre></div>`;
      try { const r = await api(`apps/${encodeURIComponent(name)}/logs`); $('#lg').textContent = (r.text || '').trim() || '(bo\'sh)'; }
      catch (x) { $('#lg').textContent = x.message; }
      return;
    }
    if (a === 'env') { closeSheet(); return envSheet(name); }
    if (a === 'fix') { closeSheet(); return aiFlow(name); }
    if (a === 'rollback') {
      if (!confirm(`${d.name} oldingi versiyaga (${(d.backups || [])[0] || 'zaxira'}) qaytarilsinmi?\n\nBaza va .env tegilmaydi.`)) return;
      closeSheet();
      const r = await api(`apps/${encodeURIComponent(name)}/rollback`, { post: 1 }).catch(x => ({ err: x.message }));
      if (r.err) return toast(r.err, 1);
      return jobSheet(r.job, () => loadApps());
    }
    if (a === 'delete') {
      if (!confirm(`${d.name} butunlay o'chirilsinmi?\n\nXizmat + fayllar + zaxiralar. Qaytarib bo'lmaydi.`)) return;
      try { await api(`apps/${encodeURIComponent(name)}?confirm=1`, { method: 'DELETE' }); toast('O‘chirildi'); closeSheet(); loadApps(); }
      catch (x) { toast(x.message, 1); }
      return;
    }
    b.disabled = true;
    $('#aout').innerHTML = `<div class="sect"><pre>⏳ ${a}…</pre></div>`;
    try {
      const r = await api(`apps/${encodeURIComponent(name)}/${a}`, { post: 1, body: {} });
      $('#aout').innerHTML = `<div class="sect"><pre>${esc(r.done ? 'Bajarildi ✓' : (r.out || 'Xatolik'))}</pre></div>`;
      notify(r.done ? 'success' : 'error'); loadApps();
    } catch (x) { $('#aout').innerHTML = `<div class="sect"><pre>${esc(x.message)}</pre></div>`; notify('error'); }
    b.disabled = false;
  };
}

/* ───────── .env ───────── */
async function envSheet(name) {
  let d;
  try { d = await api(`apps/${encodeURIComponent(name)}/env`); } catch (e) { return toast(e.message, 1); }
  state.envKeys = d.keys || [];
  const rows = state.envKeys.map(k => `<button class="row tight" data-k="${esc(k.key)}">
      <span class="av">${svg('key', 'sm')}</span><span class="n"><b>${esc(k.key)}</b><small>${esc(k.masked || '')}</small></span>
      <span class="e">›</span></button>`).join('');
  sheet(`<div class="grab"></div><h2>Kalitlar</h2>
    <div class="sh-sub">${esc(name)} · .env · ${d.count || 0} ta</div>
    <div class="lst" style="margin-top:16px">${rows || '<div class="g empty">Kalit yo‘q</div>'}</div>
    <div class="fields" style="margin-top:16px">
      <button class="btn w primary" id="envAdd">${svg('plus')}Kalit qo'shish</button>
      <button class="btn w ghost" id="envApply">${svg('restart')}Restart — qiymatlarni qo'llash</button>
    </div>`);
  $('#sheetBody').onclick = async e => {
    const r = e.target.closest('[data-k]');
    if (r) { hap(); return envKey(name, r.dataset.k); }
    if (e.target.closest('#envAdd')) { hap(); return envAdd(name); }
    if (e.target.closest('#envApply')) {
      try { const res = await api(`apps/${encodeURIComponent(name)}/restart`, { post: 1, body: {} });
        toast(res.done ? 'Qayta ishga tushdi' : 'Xatolik', !res.done); }
      catch (x) { toast(x.message, 1); }
    }
  };
}

function envKey(name, key) {
  const k = (state.envKeys || []).find(x => x.key === key) || { key, value: '', masked: '' };
  sheet(`<div class="grab"></div><h2>${esc(key)}</h2><div class="sh-sub">${esc(name)} · .env</div>
    <div class="fields">
      <input class="f" id="envVal" value="${esc(k.value)}" placeholder="qiymat" autocomplete="off" spellcheck="false">
      <div class="chips"><span class="chip" id="envShow">Ko'rsatish / yashirish</span><span class="chip" id="envDel">O'chirish</span></div>
      <button class="btn w primary" id="envSave">${svg('save')}Saqlash</button>
      <button class="btn w ghost" id="envBack">Orqaga</button>
    </div>`);
  const inp = $('#envVal');
  $('#envShow').onclick = () => { inp.type = inp.type === 'password' ? 'text' : 'password'; };
  inp.type = 'text';
  $('#envBack').onclick = () => envSheet(name);
  $('#envDel').onclick = async () => {
    if (!confirm(`${key} o'chirilsinmi?`)) return;
    try {
      await api(`apps/${encodeURIComponent(name)}/env?key=${encodeURIComponent(key)}`, { method: 'DELETE' });
      toast('O‘chirildi'); envSheet(name);
    } catch (x) { toast(x.message, 1); }
  };
  $('#envSave').onclick = async () => {
    try { await api(`apps/${encodeURIComponent(name)}/env`, { post: 1, body: { key, value: inp.value } }); toast('Saqlandi'); envSheet(name); }
    catch (x) { toast(x.message, 1); }
  };
}

function envAdd(name) {
  sheet(`<div class="grab"></div><h2>Kalit qo'shish</h2><div class="sh-sub">${esc(name)} · .env</div>
    <div class="fields">
      <textarea class="f" id="envTxt" placeholder="KALIT=qiymat&#10;IKKINCHI_KALIT=qiymat"></textarea>
      <button class="btn w primary" id="envSave2">${svg('save')}Saqlash</button>
      <button class="btn w ghost" id="envBack2">Bekor</button>
    </div>
    <div class="hint">Har qatorda bitta <code>KALIT=qiymat</code>. Mavjud kalit yangilanadi.</div>`);
  $('#envBack2').onclick = () => envSheet(name);
  $('#envSave2').onclick = async () => {
    try { const r = await api(`apps/${encodeURIComponent(name)}/env`, { post: 1, body: { text: $('#envTxt').value } });
      toast(r.bad && r.bad.length ? `Saqlandi, ${r.bad.length} qator o'qilmadi` : 'Saqlandi', r.bad && r.bad.length); envSheet(name); }
    catch (x) { toast(x.message, 1); }
  };
}

async function aiFlow(name) {
  let j;
  try { j = (await api(`ai/${encodeURIComponent(name)}/fix`, { post: 1 })).job; }
  catch (x) { return toast(x.message, 1); }
  jobSheet(j, s => {
    if (!s || s.state !== 'ok' || !s.result || !s.result.pid) return;
    setTimeout(() => proposal(name, s.result), 420);
  });
}

function proposal(name, r) {
  sheet(`<div class="grab"></div><h2>AI tahlil</h2><div class="sh-sub">${esc(name)}</div>
    <div class="sect"><h4>Sabab va yechim</h4><pre>${esc(r.explanation || '')}</pre></div>
    <div class="sect"><h4>O'zgaradigan fayllar</h4><pre>${esc((r.files || []).join('\n') || '—')}</pre></div>
    ${(r.pip || r.npm) ? `<div class="hint">Paketlar: ${esc([].concat(r.pip || [], r.npm || []).join(', '))}</div>` : ''}
    <div class="fields"><button class="btn w primary" id="aiApply">${svg('save')}Tuzatishni qo'llash</button>
    <button class="btn w ghost" id="aiNo">Bekor</button></div>`);
  $('#aiNo').onclick = closeSheet;
  $('#aiApply').onclick = async () => {
    try {
      const x = await api(`ai/${encodeURIComponent(name)}/apply`, { post: 1, body: { pid: r.pid } });
      jobSheet(x.job, () => loadApps());
    } catch (e) { toast(e.message, 1); }
  };
}

/* ───────── Jarayonlar ───────── */
async function loadProcs() {
  const list = await api('procs?sort=' + state.sort);
  $('#procList').innerHTML = list.map(p => `<button class="row" data-pid="${p.pid}" data-name="${esc(p.name)}">
    <span class="av">${svg('code', 'sm')}</span>
    <span class="n"><b>${esc(p.name)}</b><small>PID ${p.pid} · ${esc(p.user || '')}</small></span>
    <span class="e">${p.cpu.toFixed(1)}%<br><span style="opacity:.7">${(p.rss / MB).toFixed(0)} MB</span></span></button>`).join('');
}
$('#procList').onclick = e => { const r = e.target.closest('[data-pid]'); if (r) { hap(); procSheet(+r.dataset.pid, r.dataset.name); } };
$('#prSeg').onclick = e => { const b = e.target.closest('button'); if (!b) return; hap();
  $$('#prSeg button').forEach(x => x.classList.toggle('on', x === b)); state.sort = b.dataset.sort; loadProcs().catch(x => err(x.message)); };

async function procSheet(pid, name) {
  let d = null;
  try { d = await api('procs/' + pid); } catch (e) {}
  if (!d) d = { pid, name, cmd: '', user: '', rss: 0, risky: false };
  sheet(`<div class="grab"></div><h2>${esc(d.name || name)}</h2>
    <div class="sh-sub">PID ${pid}${d.user ? ' · ' + esc(d.user) : ''}${d.rss ? ' · ' + (d.rss / MB).toFixed(0) + ' MB' : ''}</div>
    ${d.cmd ? `<div class="sect"><h4>Buyruq</h4><pre>${esc(d.cmd)}</pre></div>` : ''}
    <div class="fields">
      <button class="btn w danger" id="k15">${svg('stop')}To'xtatish (SIGTERM)</button>
      <button class="btn w danger" id="k9">${svg('power')}Majburan (SIGKILL)</button>
      <button class="btn w ghost" id="kNo">Bekor</button>
    </div>
    <div class="hint">Systemd xizmati bo'lsa, u o'zi qayta ishga tushishi mumkin — «Xizmatlar» orqali to'xtating.</div>`);
  $('#kNo').onclick = closeSheet;
  const kill = async sig => {
    if (!confirm(`${d.name} (PID ${pid}) to'xtatilsinmi?`)) return;
    try { await api(`procs/${pid}/kill?sig=${sig}`, { post: 1, body: {} }); toast('To‘xtatildi'); closeSheet(); loadProcs(); }
    catch (x) { toast(x.message, 1); }
  };
  $('#k15').onclick = () => kill(15); $('#k9').onclick = () => kill(9);
}

/* ───────── Fayllar ───────── */
async function openFiles(opt = {}) {
  tab('fl');
  try {
    if (!state.roots) state.roots = (await api('files/roots')).roots;
    let token = opt.token;
    if (!token && opt.appPath) {
      const base = (state.roots.find(r => r.key === 'apps') || {}).path || '/opt/apps';
      const r = await api('files/resolve?path=' + encodeURIComponent(base.replace(/\/$/, '') + '/' + opt.appPath));
      token = r.token;
    }
    if (!token && opt.key) token = (state.roots.find(r => r.key === opt.key) || {}).token;
    if (token) return fileList(token);
  } catch (e) { return toast(e.message, 1); }
  sheet(`<div class="grab"></div><h2>Fayllar</h2><div class="sh-sub">Papkani tanlang</div>
    <div class="lst" style="margin-top:16px">${state.roots.filter(r => r.exists).map(r => `
      <button class="row" data-t="${r.token}"><span class="av">${svg('folder', 'sm')}</span>
      <span class="n"><b>${esc(r.label)}</b><small>${esc(r.path)}</small></span><span class="e">›</span></button>`).join('')}</div>`);
  $('#sheetBody').onclick = e => { const b = e.target.closest('[data-t]'); if (b) { closeSheet(); fileList(b.dataset.t); } };
}

async function fileList(token, page = 0, note = '') {
  let d;
  try { d = await api(`files/list?token=${encodeURIComponent(token)}&page=${page}`); } catch (e) { return toast(e.message, 1); }
  state.files = d.items || [];
  state.cur = d;
  const crumbs = (d.path || '').split('/').filter(Boolean);
  $('#crumb').innerHTML = `<button data-crumb="-1">⌂</button>` +
    crumbs.map((c, i) => `<button data-crumb="${i}"${i === crumbs.length - 1 ? ' class="cur"' : ''}>${esc(c)}</button>`).join('');
  $('#crumb').onclick = async e => {
    const b = e.target.closest('[data-crumb]'); if (!b) return; hap();
    const i = +b.dataset.crumb;
    if (i < 0) return openFiles({});
    const to = '/' + crumbs.slice(0, i + 1).join('/');
    try { const r = await api('files/resolve?path=' + encodeURIComponent(to)); fileList(r.token); }
    catch (x) { toast(x.message, 1); }
  };
  const items = state.files.map((f, i) => `<button class="row${f.dir ? '' : ' tight'}" data-i="${i}">
    <span class="av">${svg(f.dir ? 'folder' : 'file', 'sm')}</span>
    <span class="n"><b>${esc(f.name)}</b><small>${f.dir ? 'papka' : (f.size_h || '')} ${f.mtime ? '· ' + ago(f.mtime) : ''}</small></span>
    <span class="e">${f.dir ? '›' : ''}</span></button>`).join('');
  $('#fileList').innerHTML = (note ? `<div class="g empty" style="padding:12px">${note}</div>` : '') +
    (items || `<div class="g empty"><b>Papka bo'sh</b>${esc(d.path || '')}</div>`);
  $('#fileList').onclick = e => {
    const r = e.target.closest('[data-i]'); if (!r) return; hap();
    const f = state.files[+r.dataset.i];
    if (f.dir) return fileList(f.token);
    itemSheet(f);
  };
  $('#upBtn').onclick = () => { state.upToken = d.token; $('#fileInput').click(); };
  $('#mkdirBtn').onclick = async () => {
    const name = prompt('Yangi papka nomi:'); if (!name) return;
    try { await api('files/mkdir', { post: 1, body: { token: d.token, name } }); toast('Yaratildi'); fileList(d.token); }
    catch (x) { toast(x.message, 1); }
  };
}

$('#fileInput').onchange = async e => {
  const files = [...e.target.files]; e.target.value = '';
  if (!files.length || !state.upToken) return;
  const fd = new FormData(); files.forEach(f => fd.append('file', f, f.name));
  toast('Yuklanmoqda…');
  try { const r = await api('files/upload?token=' + encodeURIComponent(state.upToken), { post: 1, form: fd });
    toast(`${r.saved.length} fayl yuklandi`); fileList(state.upToken); }
  catch (x) { toast(x.message, 1); }
};

async function itemSheet(f) {
  let d = f;
  try { d = await api('files/stat?token=' + encodeURIComponent(f.token)); } catch (e) {}
  sheet(`<div class="grab"></div><h2>${esc(d.name)}</h2>
    <div class="sh-sub">${esc(d.path || '')} · ${d.size_h || ''} · ${d.mode || ''} ${d.owner ? '· ' + esc(d.owner) : ''}</div>
    <div class="acts two">
      <button class="btn" data-fa="read">${svg('edit')}Ko'rish</button>
      <button class="btn" data-fa="dl">${svg('dl')}Yuklab olish</button>
    </div>
    <div class="acts">
      <button class="btn" data-fa="rename">${svg('edit')}Nom</button>
      <button class="btn" data-fa="copy">${svg('file')}Nusxa</button>
      <button class="btn" data-fa="move">${svg('folder')}Ko'chirish</button>
    </div>
    <button class="btn w danger" data-fa="rm" style="margin-top:9px">${svg('trash')}O'chirish (savatga)</button>
    <div id="fout"></div>`);
  $('#sheetBody').onclick = async e => {
    const b = e.target.closest('[data-fa]'); if (!b) return;
    const a = b.dataset.fa; hap();
    if (a === 'dl') { if (DEMO) return toast('Demo rejim — yuklab bo\'lmaydi', 1);
      window.open('/api/files/download?token=' + encodeURIComponent(d.token), '_blank'); return; }
    if (a === 'read') {
      try { const r = await api('files/read?token=' + encodeURIComponent(d.token));
        $('#fout').innerHTML = `<div class="sect"><h4>Mazmun</h4><pre>${esc(r.text)}</pre>
          <button class="btn w ghost" id="fEdit" style="margin-top:10px">${svg('edit')}Tahrirlash</button></div>`;
        $('#fEdit').onclick = () => fileEdit(d, r.text);
      } catch (x) { toast(x.message, 1); }
      return;
    }
    if (a === 'rename') {
      const name = prompt('Yangi nom:', d.name); if (!name || name === d.name) return;
      try { await api('files/rename', { post: 1, body: { token: d.token, name } }); toast('Saqlandi'); closeSheet(); fileList(state.cur.token); }
      catch (x) { toast(x.message, 1); }
      return;
    }
    if (a === 'copy' || a === 'move') {
      state.clip = { mode: a, token: d.token, name: d.name };
      toast(`${a === 'copy' ? 'Nusxa' : 'Ko‘chirish'} buferda: ${d.name}. Manzil papkani oching.`);
      closeSheet();
      if (state.cur) fileList(state.cur.token, 0, `📥 Bufer: ${esc(d.name)} — <button class="chip" id="pasteHere">Shu yerga qo'yish</button>`);
      setTimeout(() => { const p = $('#pasteHere'); if (p) p.onclick = () => paste(d.token); }, 60);
      return;
    }
    if (a === 'rm') {
      if (!confirm(`${d.name} o'chirilsinmi?\n(Savatga o'tadi, 7 kun saqlanadi)`)) return;
      try { const r = await api('files/remove', { post: 1, body: { token: d.token } });
        toast('Savatga o‘tdi'); closeSheet(); fileList(state.cur.token);
        setTimeout(() => toast('Qaytarish: Savat papkasidan'), 800); }
      catch (x) { toast(x.message, 1); }
    }
  };
}

async function paste(dstToken) {
  if (!state.clip) return;
  try { await api('files/paste', { post: 1, body: { src: state.clip.token, dst: dstToken, mode: state.clip.mode } });
    toast('Bajarildi'); state.clip = null; fileList(dstToken); }
  catch (x) { toast(x.message, 1); }
}

function fileEdit(d, text) {
  sheet(`<div class="grab"></div><h2>${esc(d.name)}</h2><div class="sh-sub">Tahrirlash</div>
    <textarea class="f" id="fTxt" style="min-height:44vh">${esc(text)}</textarea>
    <div class="fields"><button class="btn w primary" id="fSave">${svg('save')}Saqlash</button>
    <button class="btn w ghost" id="fBack">Bekor</button></div>
    <div class="hint">Saqlashdan oldin eski nusxa savatga zaxiralanadi.</div>`);
  $('#fBack').onclick = () => itemSheet(d);
  $('#fSave').onclick = async () => {
    try { await api('files/write', { post: 1, body: { token: d.token, text: $('#fTxt').value } });
      toast('Saqlandi'); if (state.cur) fileList(state.cur.token); }
    catch (x) { toast(x.message, 1); }
  };
}

/* ───────── Ko'proq ───────── */
$('#v-mo').onclick = e => {
  const b = e.target.closest('[data-more]'); if (!b) return; hap();
  const k = b.dataset.more;
  if (k === 'svc') svcSheet();
  if (k === 'docker') dockerSheet();
  if (k === 'disk') diskSheet();
  if (k === 'ports') portsSheet();
  if (k === 'term') termSheet();
  if (k === 'reboot') {
    if (!confirm('Server qayta yuklansinmi?')) return;
    api('reboot', { post: 1, body: {} }).then(() => toast('Reboot yuborildi')).catch(x => toast(x.message, 1));
  }
};

async function svcSheet() {
  const list = await api('services').catch(() => []);
  sheet(`<div class="grab"></div><h2>Xizmatlar</h2><div class="sh-sub">${list.length} ta ishlayapti</div>
    <div class="lst" style="margin-top:16px">${list.map(s => `<button class="row tight" data-svc="${esc(s.name)}">
      <span class="dot"></span><span class="n"><b>${esc(s.name)}</b></span><span class="e">›</span></button>`).join('')}</div>`);
  $('#sheetBody').onclick = e => { const b = e.target.closest('[data-svc]'); if (b) { hap(); svcCard(b.dataset.svc); } };
}

async function svcCard(n) {
  let d = { name: n, state: 'active', pid: '', restarts: '0', since: '', risky: false };
  try { d = await api('services/' + encodeURIComponent(n)); } catch (e) {}
  sheet(`<div class="grab"></div><h2>${esc(n)}</h2>
    <div class="sh-sub"><span class="dot${d.state === 'active' ? '' : ' off'}"></span>${esc(d.state)} · restart ${esc(d.restarts || 0)}</div>
    <div class="acts">${['start', 'stop', 'restart'].map(a => `<button class="btn" data-sa="${a}">${svg(a === 'start' ? 'play' : a === 'stop' ? 'stop' : 'restart')}${a[0].toUpperCase() + a.slice(1)}</button>`).join('')}</div>
    <div class="acts two"><button class="btn" data-sa="enable">Enable</button><button class="btn" data-sa="disable">Disable</button></div>
    <button class="btn w ghost" id="svcLog">${svg('log')}Journal ko'rish</button>
    <div id="sout"></div>`);
  $('#svcLog').onclick = async () => { try { const r = await api(`services/${encodeURIComponent(n)}/journal`);
    $('#sout').innerHTML = `<div class="sect"><pre>${esc(r.text)}</pre></div>`; } catch (e) { toast(e.message, 1); } };
  $('#sheetBody').onclick = async e => {
    const b = e.target.closest('[data-sa]'); if (!b) return;
    try { const r = await api(`services/${encodeURIComponent(n)}/${b.dataset.sa}`, { post: 1, body: {} });
      toast(r.done ? 'Bajarildi' : 'Xatolik', !r.done); svcCard(n); }
    catch (x) { toast(x.message, 1); }
  };
}

async function portsSheet() {
  const list = await api('ports').catch(() => []);
  sheet(`<div class="grab"></div><h2>Portlar</h2><div class="sh-sub">${list.length} ta listen</div>
    <pre>${esc(list.map(p => `${String(p.port).padStart(5)}  ${(p.ip || '').padEnd(15).slice(0, 15)}  ${p.name}`).join('\n') || '(bo\'sh)')}</pre>`);
}

async function diskSheet() {
  const d = await api('disk').catch(() => ({ df: '', du: '', p: 0 }));
  sheet(`<div class="grab"></div><h2>Disk</h2><div class="sh-sub">${d.p ? Math.round(d.p) + '% band' : ''}</div>
    <div class="prog"><i style="width:${d.p || 0}%"></i></div>
    <pre>${esc((d.df || '') + '\n' + (d.du || ''))}</pre>
    <button class="btn w primary" id="clean">🧹 Xavfsiz tozalash</button>
    <div class="hint">journalctl 200MB gacha, apt keshi, docker dangling image. Savatga tegmaydi.</div>`);
  $('#clean').onclick = async () => { try { const r = await api('disk/clean', { post: 1, body: {} });
    toast(`${r.freed}MB bo'shadi`); diskSheet(); } catch (e) { toast(e.message, 1); } };
}

async function dockerSheet() {
  const d = await api('docker').catch(() => ({ text: '' }));
  sheet(`<div class="grab"></div><h2>Docker</h2><div class="sh-sub">konteynerlar</div><pre>${esc(d.text || '(bo\'sh)')}</pre>`);
}

function termSheet() {
  sheet(`<div class="grab"></div><h2>Terminal</h2><div class="sh-sub">root · diqqat bilan</div>
    <div class="fields"><input class="f" id="cmd" placeholder="ls -la /opt/apps" autocapitalize="off" autocorrect="off" spellcheck="false">
    <button class="btn w primary" id="run">${svg('play')}Bajarish</button></div><div id="tout"></div>`);
  const run = async () => {
    const c = $('#cmd').value.trim(); if (!c) return;
    $('#tout').innerHTML = `<pre>⏳…</pre>`;
    try { const r = await api('sh', { post: 1, body: { cmd: c, timeout: 120 } });
      $('#tout').innerHTML = `<pre>exit=${r.code}\n${esc(r.out)}</pre>`; }
    catch (x) { $('#tout').innerHTML = `<pre>${esc(x.message)}</pre>`; }
  };
  $('#run').onclick = run;
  $('#cmd').onkeydown = e => { if (e.key === 'Enter') run(); };
}

async function loadMe() {
  try {
    const d = await api('me');
    $('#meInfo').innerHTML = `<div class="kv"><span>Foydalanuvchi</span><b>${esc(d.name || '—')}</b></div>
      <div class="kv"><span>ID</span><b>${esc(d.id || '—')}</b></div>
      <div class="kv"><span>Rejim</span><b>${DEMO ? 'Demo (statik)' : 'Mini App'}</b></div>
      <div class="kv"><span>Versiya</span><b>v${d.version || 2}.0</b></div>
      <div class="kv"><span>Manzil</span><b>${esc(location.host || '—')}</b></div>`;
  } catch (e) {}
}

/* ───────── tablar ───────── */
const LOAD = { st: loadStatus, ap: loadApps, pr: loadProcs, fl: () => (state.cur ? fileList(state.cur.token) : openFiles({})), mo: () => { loadMe(); } };
const TTL = { st: 'Holat', ap: 'Ilovalar', pr: 'Jarayonlar', fl: 'Fayllar', mo: "Ko'proq" };

function tab(t) {
  state.tab = t;
  $$('#nav button').forEach(b => b.classList.toggle('on', b.dataset.tab === t));
  $$('.v').forEach(s => s.classList.toggle('on', s.id === 'v-' + t));
  $('#ttl').textContent = TTL[t];
  tick();
}
$('#nav').onclick = e => { const b = e.target.closest('button'); if (!b) return; hap(); tab(b.dataset.tab); };
$('#v-st').addEventListener('click', e => { const b = e.target.closest('[data-tab]'); if (b) tab(b.dataset.tab); });

let busy = false;
async function tick() {
  if (busy || document.hidden) return;
  busy = true;
  try { await LOAD[state.tab](); err(''); }
  catch (e) { err(e.message); }
  finally { busy = false; }
}
$('#rf').onclick = () => { hap(); $('#rf').classList.add('spin'); tick().finally(() => setTimeout(() => $('#rf').classList.remove('spin'), 500)); };

setInterval(() => { if (state.tab === 'st' || state.tab === 'pr') tick(); }, 4000);
document.addEventListener('visibilitychange', () => { if (!document.hidden) tick(); });

/* start */
(async () => {
  if (DEMO) { err(''); }
  await tick();
  if (DEMO) $('#up').textContent = 'Demo rejim · namuna ma’lumotlar';
})();
