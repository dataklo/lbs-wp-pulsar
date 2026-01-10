#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${APP_DIR}/.venv"
UNIT_PATH="/etc/systemd/system/pulser@.service"

echo "[*] pv-tools updater"
echo "    APP_DIR=${APP_DIR}"

if [ ! -d "${APP_DIR}/.git" ]; then
  echo "[!] This directory is not a git repo: ${APP_DIR}" >&2
  exit 1
fi

# If install looks missing, run it.
if [ ! -f "${UNIT_PATH}" ] || [ ! -x "${VENV_DIR}/bin/python" ]; then
  echo "[*] Missing systemd unit and/or venv -> running install.sh"
  "${APP_DIR}/install.sh"
fi

echo "[*] Pulling latest changes..."
git -C "${APP_DIR}" pull --ff-only

echo "[*] Updating Python deps..."
"${VENV_DIR}/bin/python" -m pip install -U pip
"${VENV_DIR}/bin/pip" install -r "${APP_DIR}/requirements.txt"

echo "[*] Reloading systemd + restarting services..."
sudo systemctl daemon-reload

shopt -s nullglob
found=0
for f in "${APP_DIR}"/*_pulser.py; do
  base="$(basename "$f")"
  inst="${base%_pulser.py}"
  echo "    - restart pulser@${inst}"
  sudo systemctl enable --now "pulser@${inst}"
  sudo systemctl restart "pulser@${inst}"
  found=1
done

if [ "$found" -eq 0 ]; then
  echo "[!] No *_pulser.py scripts found to restart."
fi

echo
echo "[✓] Update complete."
echo "    Tip: journalctl -u pulser@pv -f"
