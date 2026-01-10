#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CFG_DIR="/etc/pv-tools"
UNIT_PATH="/etc/systemd/system/pulser@.service"

# Optional flags:
#   REMOVE_CONFIG=1 ./uninstall.sh   -> removes /etc/pv-tools/*.env
#   REMOVE_USER=1   ./uninstall.sh   -> removes pvtools system user/group (if possible)
REMOVE_CONFIG="${REMOVE_CONFIG:-0}"
REMOVE_USER="${REMOVE_USER:-0}"

echo "[*] pv-tools uninstall"
echo "    APP_DIR=${APP_DIR}"
echo "    REMOVE_CONFIG=${REMOVE_CONFIG}  REMOVE_USER=${REMOVE_USER}"

echo "[*] Stopping/disabling pulser services (for scripts present)..."
shopt -s nullglob
for f in "${APP_DIR}"/*_pulser.py; do
  base="$(basename "$f")"
  inst="${base%_pulser.py}"
  echo "    - pulser@${inst}"
  sudo systemctl stop "pulser@${inst}" >/dev/null 2>&1 || true
  sudo systemctl disable "pulser@${inst}" >/dev/null 2>&1 || true
done

echo "[*] Removing systemd unit..."
if [ -f "${UNIT_PATH}" ]; then
  sudo rm -f "${UNIT_PATH}"
fi
sudo systemctl daemon-reload

if [ "${REMOVE_CONFIG}" = "1" ]; then
  echo "[*] Removing config directory: ${CFG_DIR}"
  sudo rm -rf "${CFG_DIR}" || true
else
  echo "[*] Keeping config directory: ${CFG_DIR} (set REMOVE_CONFIG=1 to remove)"
fi

if [ "${REMOVE_USER}" = "1" ]; then
  echo "[*] Removing system user/group pvtools..."
  sudo userdel pvtools >/dev/null 2>&1 || true
  sudo groupdel pvtools >/dev/null 2>&1 || true
else
  echo "[*] Keeping system user/group pvtools (set REMOVE_USER=1 to remove)"
fi

echo
echo "[✓] Uninstall complete."
