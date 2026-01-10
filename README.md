# pv-tools (Pulser)

Kleines Repo mit 3 Python-Skripten, die aus Victron/Venus (Modbus TCP) Leistungswerte lesen und daraus Impulse per Shelly-Relay erzeugen:

- `pv_pulser.py`  → PV-Leistung (L1/L2/L3)
- `house_pulser.py` → Haus-Netto (House - HP - optional Wallbox), mit `USE_WALLBOX=0/1`
- `wp_pulser.py` → Wärmepumpe (HP) als einzelner Messwert

Die Konfiguration passiert über ENV-Dateien unter `/etc/pv-tools/*.env` und wird per systemd geladen.

## Voraussetzungen

- GitHub Repo (dieses Repo)
- Zielsystem: Ubuntu (VM)
- Zugriff auf:
  - Venus/Victron Modbus TCP (Port 502)
  - Shelly (Gen1 API: `/relay/<idx>?turn=on`)

## Repo-Struktur (empfohlen)

```
pv-tools/
  pv_pulser.py
  house_pulser.py
  wp_pulser.py
  requirements.txt
  install.sh
  update.sh
  uninstall.sh
  config/
    pv.env.example
    house.env.example
    wp.env.example
  .gitignore
  .gitattributes
```

## Windows → GitHub (Kurz)

1. Git installieren (PowerShell):
   ```powershell
   winget install --id Git.Git -e
   ```

2. Repo initialisieren & pushen:
   ```powershell
   cd C:\pfad\zum\pv-tools
   git init
   git branch -M main
   git add .
   git commit -m "Initial commit"
   git remote add origin <DEIN_REPO_URL>
   git push -u origin main
   ```

**Wichtig:** `.gitattributes` nutzen, damit `.py/.sh` als `LF` gespeichert werden.

## Ubuntu VM Installation

1. Repo klonen:
   ```bash
   sudo mkdir -p /opt
   sudo chown "$USER":"$USER" /opt
   cd /opt
   git clone <DEIN_REPO_URL> pv-tools
   cd pv-tools
   ```

2. Install ausführen:
   ```bash
   chmod +x install.sh update.sh uninstall.sh
   ./install.sh
   ```

Der Installer macht:
- apt Pakete installieren (`git`, `python3-venv`, `python3-pip`, `ca-certificates`)
- venv unter `./.venv` anlegen + `pip install -r requirements.txt`
- system user `pvtools` anlegen
- systemd Template `pulser@.service` installieren
- Env-Examples aus `config/*.env.example` nach `/etc/pv-tools/*.env` kopieren (nur wenn noch nicht vorhanden)
- Services für vorhandene `*_pulser.py` aktivieren und starten (pv/house/wp)

## Konfiguration

Die echten Konfig-Dateien liegen auf der VM hier:

- `/etc/pv-tools/pv.env`
- `/etc/pv-tools/house.env`
- `/etc/pv-tools/wp.env`

Nach dem Anpassen:
```bash
sudo systemctl restart pulser@pv pulser@house pulser@wp
```

### House: Wallbox optional

In `/etc/pv-tools/house.env`:
```bash
USE_WALLBOX=1   # mitrechnen/abziehen
# oder
USE_WALLBOX=0   # ignorieren
```

## Betrieb / Debugging

Status:
```bash
systemctl status pulser@pv
systemctl status pulser@house
systemctl status pulser@wp
```

Logs live:
```bash
journalctl -u pulser@pv -f
journalctl -u pulser@house -f
journalctl -u pulser@wp -f
```

## Update (Deploy)

```bash
cd /opt/pv-tools
./update.sh
```

Das macht:
- `git pull --ff-only`
- Python deps updaten
- systemd reload + Services restart

## Uninstall

```bash
cd /opt/pv-tools
./uninstall.sh
```

Optional auch Config löschen:
```bash
REMOVE_CONFIG=1 ./uninstall.sh
```

Optional auch system user löschen:
```bash
REMOVE_USER=1 ./uninstall.sh
```

## Sicherheit / Hinweise

- Config liegt bewusst unter `/etc/pv-tools` und nicht im Repo.
- Services laufen als system user `pvtools`.
- Wenn du Probleme mit Zugriffsrechten hast: `ls -la /opt/pv-tools` und prüfen, ob die Gruppe `pvtools` lesend/executing Zugriff hat.
