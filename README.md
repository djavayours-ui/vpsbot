# VPS Manager v5 — Telegram Mini App

Botning **barcha** bo'limlari endi bitta yadro (`core` / `appctl` / `filesvc`) ustida ishlaydi.
Bot ham, Mini App ham **bir xil** funksiyalarni chaqiradi — mantiq ikki marta yozilmagan.

## Tuzilma

```
config.py      sozlamalar + sof yordamchilar (aiogram'siz)
core.py        monitoring, jarayonlar, portlar, xizmatlar, docker, disk, terminal
appctl.py      ZIP deploy, update+rollback, .env kalitlar, AI tuzatish
filesvc.py     fayl menejeri yadrosi
jobs.py        fon vazifalari + progress (bot ham, web ham o'qiydi)
webapp.py      aiohttp API + statik panel + cloudflared tunnel
webapp/        index.html, styles.css, app.js  (premium gray glassmorphism)
bot.py         bot kirish nuqtasi, monitoring, alert
bot_apps.py    bot: ilovalar, ZIP, kalitlar, AI
bot_files.py   bot: fayl menejeri
bot_sys.py     bot: jarayonlar, portlar, xizmatlar
```

## O'rnatish

```bash
sudo apt update && sudo apt install -y python3-venv python3-pip curl
# cloudflared apt'da yo'q — binar fayl yuklanadi:
sudo curl -fL -o /usr/local/bin/cloudflared https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-$(dpkg --print-architecture)
sudo chmod +x /usr/local/bin/cloudflared
unzip vpsbot-v5-webapp.zip -d /opt/vpsbot && cd /opt/vpsbot
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

cp .env.example .env && nano .env     # BOT_TOKEN, ADMIN_IDS
sudo .venv/bin/python bot.py
```

`WEBAPP_URL` **bo'sh** qoldirilsa bot o'zi cloudflared bilan bepul HTTPS manzil oladi va
shu manzilni «Panel» tugmasiga qo'yadi (trycloudflare manzili har ishga tushishda o'zgaradi).

### Doimiy domen bilan (tavsiya etiladi)

```bash
# 1) systemd xizmati
sudo tee /etc/systemd/system/vpsbot.service >/dev/null <<'EOF'
[Unit]
Description=VPS Manager bot + panel
After=network.target

[Service]
WorkingDirectory=/opt/vpsbot
Environment=WEBAPP_URL=https://panel.example.com
ExecStart=/opt/vpsbot/.venv/bin/python bot.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload && sudo systemctl enable --now vpsbot

# 2) cloudflared nomlangan tunnel
cloudflared tunnel login
cloudflared tunnel create vpspanel
sudo mkdir -p /etc/cloudflared
sudo tee /etc/cloudflared/config.yml >/dev/null <<'EOF'
tunnel: <TUNNEL_UUID>
credentials-file: /root/.cloudflared/<TUNNEL_UUID>.json
ingress:
  - hostname: panel.example.com
    service: http://127.0.0.1:8080
  - service: http_status:404
EOF
cloudflared tunnel route dns vpspanel panel.example.com
sudo cloudflared service install && sudo systemctl enable --now cloudflared
```

### Telegram menyu tugmasi (BotFather)

1. @BotFather → `/mybots` → botni tanlang
2. **Bot Settings → Menu Button → Configure menu button**
3. Matn: `Panel`
4. URL: `https://panel.example.com` (yoki `WEBAPP_URL`)

Yoki kod o'zi qiladi: `WEBAPP_URL` berilgan bo'lsa `set_chat_menu_button` chaqiriladi.

## Xavfsizlik

- `/api/*` faqat **Telegram initData** imzosi to'g'ri bo'lsa ishlaydi (HMAC-SHA256, `auth_date` 24 soat).
- Foydalanuvchi ID `ADMIN_IDS` da bo'lishi shart.
- Brauzerda `initData` bo'lmasa — panel **demo rejimda** ochiladi va API'ga umuman murojaat qilmaydi.
- Fayl amallari `DENY`/`guard()` bilan himoyalangan; o'chirilgan narsa 7 kun savatda turadi.
- `RISKY` xizmat/jarayonlarni (ssh, networking, ...) to'xtatib bo'lmaydi.

## API (qisqacha)

`GET /api/status · /api/apps · /api/procs · /api/ports · /api/services · /api/disk · /api/docker`
`POST /api/apps/deploy · /api/apps/{n}/{start|stop|restart} · /api/apps/{n}/rollback · /api/ai/{n}/fix`
`GET /api/jobs/{id}` — har qanday uzoq jarayonning bosqichlari/progressi
`GET|POST|DELETE /api/apps/{n}/env` — .env kalitlari
`GET /api/files/{roots,list,stat,read,download,tail,resolve} · POST /api/files/{upload,write,mkdir,rename,remove,paste,restore}`

## Demo

`vps-panel-demo.html` — bitta fayl, internet kerak emas: ochsangiz barcha ekranlar namuna ma'lumot bilan ishlaydi.
