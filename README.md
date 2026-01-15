# lbs-wp-pulsar (Victron/Venus → Shelly Impulse)

Kleine Sammlung von Python-Skripten, die **Leistungswerte per Modbus TCP** aus einem Victron/Venus-System lesen
und daraus **Impulse** erzeugen, indem ein Shelly-Ausgang kurz eingeschaltet wird (Shelly-seitig mit *Auto-Off* konfiguriert).

Enthaltene Skripte:

- `wp_pulser.py`  → Wärmepumpe (HP) als einzelner Messwert (uint32)
- `pv_pulser.py`  → PV-Leistung L1/L2/L3 (uint16)
- `house_pulser.py` → Haus-Netto (House - HP - optional Wallbox)

Die Services laufen über **systemd** (Template `pulser@.service`) und laden ihre Konfig aus **ENV-Dateien**.

---

## Unterstützte Shelly-Geräte

Dieses Repo unterstützt zwei API-Varianten:

1. **Shelly UNI (Gen1)** – URL Schema: `/relay/<idx>?turn=on`
2. **Shelly Plus UNI (Gen2)** – URL Schema: `/rpc/Switch.Set?id=<idx>&on=true`

Wahl per ENV:

```bash
SHELLY_DEVICE=uni       # Gen1
SHELLY_DEVICE=plus_uni  # Gen2
```

Du kannst jederzeit auch manuell überschreiben:

```bash
SHELLY_ON_URL=http://<IP>/...  # komplette URL, wenn du etwas Spezielles brauchst
```

> Wichtig: Stelle am Shelly-Ausgang **Auto-Off auf ~0.03s (30ms)** ein, damit daraus echte Impulse werden.

---

## Installation (Ubuntu/Debian)

### 1) Repo klonen

```bash
sudo mkdir -p /opt
sudo chown "$USER":"$USER" /opt
cd /opt
git clone https://github.com/dataklo/lbs-wp-pulsar.git
cd lbs-wp-pulsar
```

### 2) Install ausführen

```bash
chmod +x install.sh update.sh uninstall.sh
./install.sh
```

Der Installer erledigt:

- apt Pakete installieren (`git`, `python3-venv`, `python3-pip`, `ca-certificates`)
- Python venv unter `./.venv` anlegen und `pip install -r requirements.txt`
- system user/group anlegen (Default: `lbspulser`)
- systemd Template `pulser@.service` installieren
- Example-Konfigs nach `/etc/lbs-wp-pulsar/*.env` kopieren (nur falls noch nicht vorhanden)
- Services für vorhandene `*_pulser.py` aktivieren und starten (pv/house/wp)

**Non-interactive (z.B. per Script):**

```bash
SHELLY_DEVICE=plus_uni ./install.sh
```

---

## Konfiguration

Die echten Konfig-Dateien liegen hier:

- `/etc/lbs-wp-pulsar/pv.env`
- `/etc/lbs-wp-pulsar/house.env`
- `/etc/lbs-wp-pulsar/wp.env`

Nach dem Anpassen:

```bash
sudo systemctl restart pulser@pv pulser@house pulser@wp
```

### House: Wallbox optional

In `/etc/lbs-wp-pulsar/house.env`:

```bash
USE_WALLBOX=1   # berücksichtigen
# oder
USE_WALLBOX=0   # ignorieren
```

---

## Betrieb / Debugging

Status:

```bash
systemctl status pulser@wp
systemctl status pulser@pv
systemctl status pulser@house
```

Logs live:

```bash
journalctl -u pulser@wp -f
journalctl -u pulser@pv -f
journalctl -u pulser@house -f
```

---

## Update (Deploy)

```bash
cd /opt/lbs-wp-pulsar
./update.sh
```

---

## Uninstall

```bash
cd /opt/lbs-wp-pulsar
./uninstall.sh
```

Optional auch Config löschen:

```bash
REMOVE_CONFIG=1 ./uninstall.sh
```

Optional auch den system user löschen:

```bash
REMOVE_USER=1 ./uninstall.sh
```

---

## Git Workflow (kurz)

Änderungen committen und pushen:

```bash
git status
git add -A
git commit -m "..."
git push
```

Auf dem Server aktualisieren:

```bash
cd /opt/lbs-wp-pulsar
./update.sh
```

---

## Sicherheit / Hinweise

- Config liegt bewusst unter `/etc/lbs-wp-pulsar` und nicht im Repo.
- Services laufen als system user (Default `lbspulser`).
- Wenn du Berechtigungsprobleme hast: `ls -la /opt/lbs-wp-pulsar` und prüfen, ob Gruppe `lbspulser` Leserechte hat.
