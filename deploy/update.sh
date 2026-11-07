#!/usr/bin/env bash
# Kodni yangilash. Yangi fayllarni serverga joylagandan so'ng (yoki git ishlatilsa — avtomatik git pull):
#     sudo bash deploy/update.sh
# Tartib: baza nusxasi -> kutubxonalar -> kodni tekshirish -> qayta ishga tushirish.
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE_NAME="${SERVICE_NAME:-murojaat-bot}"
say() { printf '\033[1;32m==>\033[0m %s\n' "$*"; }
die() { printf '\033[1;31mXATO:\033[0m %s\n' "$*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || die "root huquqi kerak: sudo bash deploy/update.sh"
[ -f "/etc/systemd/system/${SERVICE_NAME}.service" ] || die "Xizmat o'rnatilmagan. Avval: sudo bash deploy/install.sh"
SERVICE_USER="$(systemctl show -p User --value "$SERVICE_NAME")"
SERVICE_USER="${SERVICE_USER:-root}"
run() { (cd "$APP_DIR" && runuser -u "$SERVICE_USER" -- "$@"); }

if [ -d "$APP_DIR/.git" ] && [ "${NO_GIT:-0}" != 1 ]; then
    say "git pull..."
    git -C "$APP_DIR" pull --ff-only
fi

say "Baza nusxasi olinmoqda..."
run "$APP_DIR/.venv/bin/python" scripts/backup.py || die "Nusxa olinmadi — yangilash to'xtatildi"

say "Kutubxonalar..."
"$APP_DIR/.venv/bin/pip" install -q -r "$APP_DIR/requirements.txt"

say "Kod tekshirilmoqda..."
run "$APP_DIR/.venv/bin/python" -c "import main" \
    || die "Kodda xato — bot qayta ishga tushirilmadi (eski versiya ishlashda davom etyapti)"

say "Qayta ishga tushirilmoqda..."
systemctl restart "$SERVICE_NAME"
sleep 5
if systemctl is-active --quiet "$SERVICE_NAME"; then
    say "Tayyor."
else
    journalctl -u "$SERVICE_NAME" -n 30 --no-pager || true
    die "Ishga tushmadi — yuqoridagi logni ko'ring. Eski nusxa: python scripts/backup.py --list"
fi
