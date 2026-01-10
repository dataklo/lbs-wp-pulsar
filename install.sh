#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CFG_DIR="/etc/pv-tools"
UNIT_PATH="/etc/systemd/system/pulser@.service"
VENV_DIR="${APP_DIR}/.venv"

need_cmd() { command -v "$1" >/dev/null 2>&1; }

echo "[*] pv-tools installer"
echo "    APP_DIR=${APP_DIR}"

if ! need_cmd sudo; then
  echo "[!] sudo not found. Please install sudo or run as root." >&2
  exit 1
fi

echo "[*] Installing OS packages (Ubuntu/Debian)..."
sudo apt-get update -y
sudo apt-get install -y git python3 python3-venv python3-pip ca-certificates

echo "[*] Ensuring system user/group 'pvtools' exists..."
if ! getent group pvtools >/dev/null; then
  sudo groupadd --system pvtools
fi
if ! id -u pvtools >/dev/null 2>&1; then
  sudo useradd --system --gid pvtools --home /nonexistent --shell /usr/sbin/nologin pvtools
fi

echo "[*] Creating venv + installing Python deps..."
python3 -m venv "${VENV_DIR}"
"${VENV_DIR}/bin/python" -m pip install -U pip
if [ -f "${APP_DIR}/requirements.txt" ]; then
  "${VENV_DIR}/bin/pip" install -r "${APP_DIR}/requirements.txt"
else
  echo "[!] requirements.txt not found in ${APP_DIR}" >&2
  exit 1
fi

echo "[*] Installing systemd template unit: ${UNIT_PATH}"
sudo tee "${UNIT_PATH}" >/dev/null <<EOF
[Unit]
Description=Pulser (%i)
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
User=pvtools
Group=pvtools
WorkingDirectory=${APP_DIR}
EnvironmentFile=-${CFG_DIR}/%i.env
Environment=PYTHONUNBUFFERED=1
ExecStart=${VENV_DIR}/bin/python ${APP_DIR}/%i_pulser.py
Restart=always
RestartSec=2

# light hardening (can be relaxed if needed)
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload

echo "[*] Installing config examples to ${CFG_DIR} (only if missing)..."
sudo mkdir -p "${CFG_DIR}"
if [ -d "${APP_DIR}/config" ]; then
  for ex in "${APP_DIR}/config/"*.env.example; do
    [ -e "$ex" ] || continue
    name="$(basename "$ex" .env.example)"
    target="${CFG_DIR}/${name}.env"
    if [ ! -f "${target}" ]; then
      sudo cp "$ex" "${target}"
      echo "    - created ${target}"
    fi
  done
fi

# permissions: allow service user to read/execute code + venv
echo "[*] Setting permissions so pvtools can run..."
sudo chown -R "$USER":pvtools "${APP_DIR}"
sudo chmod -R g+rX "${APP_DIR}"
sudo chmod -R o-rwx "${APP_DIR}" || true

# config perms (readable by pvtools)
sudo chown -R root:pvtools "${CFG_DIR}"
sudo chmod -R 750 "${CFG_DIR}"
sudo find "${CFG_DIR}" -type f -name "*.env" -exec sudo chmod 640 {} \;

echo "[*] Enabling and starting services for existing *_pulser.py scripts..."
shopt -s nullglob
found=0
for f in "${APP_DIR}"/*_pulser.py; do
  base="$(basename "$f")"
  inst="${base%_pulser.py}"   # pv / house / wp ...
  echo "    - pulser@${inst}"
  sudo systemctl enable --now "pulser@${inst}"
  found=1
done
if [ "$found" -eq 0 ]; then
  echo "[!] No *_pulser.py scripts found in ${APP_DIR}"
fi

echo
echo "[✓] Install complete."
echo "    Status:  systemctl status pulser@pv pulser@house pulser@wp"
echo "    Logs:    journalctl -u pulser@pv -f"
