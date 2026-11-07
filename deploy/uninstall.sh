#!/usr/bin/env bash
# systemd xizmatini olib tashlash (loyiha fayllari va baza o'chirilmaydi).
set -euo pipefail
SERVICE_NAME="${SERVICE_NAME:-murojaat-bot}"
[ "$(id -u)" -eq 0 ] || { echo "sudo bilan ishga tushiring"; exit 1; }
systemctl disable --now "$SERVICE_NAME" 2>/dev/null || true
rm -f "/etc/systemd/system/${SERVICE_NAME}.service"
systemctl daemon-reload
echo "Xizmat olib tashlandi. Loyiha fayllari va data/ joyida qoldi."
