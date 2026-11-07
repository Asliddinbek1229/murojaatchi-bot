#!/usr/bin/env bash
# Birinchi o'rnatish (Ubuntu/Debian). Loyiha papkasida ishga tushiring:
#     sudo bash deploy/install.sh
# Ixtiyoriy: SERVICE_NAME=murojaat-bot SERVICE_USER=murojaat PYTHON=python3.12 sudo -E bash deploy/install.sh
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE_NAME="${SERVICE_NAME:-murojaat-bot}"
PYTHON="${PYTHON:-python3}"
UNIT="/etc/systemd/system/${SERVICE_NAME}.service"

say()  { printf '\033[1;32m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m!!\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31mXATO:\033[0m %s\n' "$*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || die "root huquqi kerak: sudo bash deploy/install.sh"
[ -f "$APP_DIR/main.py" ] || die "main.py topilmadi ($APP_DIR)"

# ---------- 1. Python ----------
if ! command -v "$PYTHON" >/dev/null 2>&1; then
    say "Python o'rnatilmoqda..."
    apt-get update -qq && apt-get install -y -qq python3 python3-venv python3-pip
fi
"$PYTHON" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' \
    || die "Python 3.10+ kerak (hozir: $("$PYTHON" -V 2>&1)). Masalan: apt install python3.12 python3.12-venv, so'ng PYTHON=python3.12"
if ! "$PYTHON" -c 'import ensurepip, venv' >/dev/null 2>&1; then
    PYV="$("$PYTHON" -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
    say "python${PYV}-venv o'rnatilmoqda..."
    apt-get update -qq
    apt-get install -y -qq "python${PYV}-venv" || apt-get install -y -qq python3-venv
fi
say "Python: $("$PYTHON" -V 2>&1)"

# ---------- 2. Xizmat foydalanuvchisi ----------
PROTECT_HOME="ProtectHome=true"
case "$APP_DIR" in
    /root/*|/home/*) PROTECT_HOME="# ProtectHome yoq: loyiha uy papkasida joylashgan" ;;
esac
if [ -z "${SERVICE_USER:-}" ]; then
    case "$APP_DIR" in
        /root/*) SERVICE_USER=root ;;
        *)  OWNER="$(stat -c %U "$APP_DIR")"
            if [ "$OWNER" = root ]; then SERVICE_USER=murojaat; else SERVICE_USER="$OWNER"; fi ;;
    esac
fi
if ! id "$SERVICE_USER" >/dev/null 2>&1; then
    say "Tizim foydalanuvchisi yaratilmoqda: $SERVICE_USER"
    useradd --system --no-create-home --shell /usr/sbin/nologin "$SERVICE_USER"
fi
if [ "$SERVICE_USER" = root ]; then
    warn "Bot root nomidan ishlaydi (loyiha /root ichida). Xavfsizroq variant: loyihani /opt ga ko'chirish."
fi
SERVICE_GROUP="$(id -gn "$SERVICE_USER")"
say "Bot foydalanuvchisi: $SERVICE_USER"

# ---------- 3. .env ----------
if [ ! -f "$APP_DIR/.env" ]; then
    cp "$APP_DIR/.env.example" "$APP_DIR/.env"
    chown "$SERVICE_USER:$SERVICE_GROUP" "$APP_DIR/.env"
    chmod 600 "$APP_DIR/.env"
    warn ".env yaratildi. BOT_TOKEN va SUPERADMIN_IDS ni yozing:  nano $APP_DIR/.env"
    warn "So'ng qayta ishga tushiring:  sudo bash deploy/install.sh"
    exit 1
fi
sed -i 's/\r$//' "$APP_DIR/.env"   # Windows'da tahrirlangan bo'lsa — CRLF ni tozalash

# ---------- 4. Virtual muhit va kutubxonalar ----------
if [ ! -x "$APP_DIR/.venv/bin/python" ]; then
    say "Virtual muhit yaratilmoqda (.venv)..."
    rm -rf "$APP_DIR/.venv"   # Windows'dan ko'chirilgan .venv Linux'da ishlamaydi
    "$PYTHON" -m venv "$APP_DIR/.venv"
fi
say "Kutubxonalar o'rnatilmoqda..."
"$APP_DIR/.venv/bin/pip" install -q --upgrade pip
"$APP_DIR/.venv/bin/pip" install -q -r "$APP_DIR/requirements.txt"

# ---------- 5. Huquqlar ----------
mkdir -p "$APP_DIR/data" "$APP_DIR/logs"
chown -R "$SERVICE_USER:$SERVICE_GROUP" "$APP_DIR/data" "$APP_DIR/logs"
chown "$SERVICE_USER:$SERVICE_GROUP" "$APP_DIR/.env"
chmod 600 "$APP_DIR/.env"
chmod 700 "$APP_DIR/data"
if [ "$SERVICE_USER" != root ] && ! runuser -u "$SERVICE_USER" -- test -r "$APP_DIR/main.py"; then
    die "$SERVICE_USER foydalanuvchisi $APP_DIR ni o'qiy olmaydi. Loyihani /opt ga ko'chiring yoki SERVICE_USER ni ko'rsating."
fi

# ---------- 6. Sozlamalarni tekshirish ----------
say "Sozlamalar tekshirilmoqda..."
(cd "$APP_DIR" && runuser -u "$SERVICE_USER" -- "$APP_DIR/.venv/bin/python" -c \
    "from bot.config import config; print('   superadminlar:', sorted(config.superadmin_ids)); print('   baza:', config.db_path)") \
    || die ".env da xato bor (yuqoridagi xabarni o'qing): nano $APP_DIR/.env"

# ---------- 7. systemd ----------
say "systemd xizmati: $UNIT"
sed -e "s|@APP_DIR@|$APP_DIR|g" -e "s|@USER@|$SERVICE_USER|g" -e "s|@GROUP@|$SERVICE_GROUP|g" \
    -e "s|@PROTECT_HOME@|$PROTECT_HOME|" "$APP_DIR/deploy/murojaat-bot.service" > "$UNIT"
systemctl daemon-reload
systemctl enable "$SERVICE_NAME" >/dev/null 2>&1
systemctl restart "$SERVICE_NAME"
sleep 5

if systemctl is-active --quiet "$SERVICE_NAME"; then
    say "Tayyor! Bot ishlayapti va server qayta yonganda o'zi ishga tushadi."
    echo "   Holat:      systemctl status $SERVICE_NAME"
    echo "   Loglar:     journalctl -u $SERVICE_NAME -f"
    echo "   Yangilash:  sudo bash deploy/update.sh"
else
    journalctl -u "$SERVICE_NAME" -n 30 --no-pager || true
    die "Xizmat ishga tushmadi — yuqoridagi logni ko'ring."
fi
