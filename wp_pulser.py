#!/usr/bin/env python3
import os
import time
import requests
from pymodbus.client import ModbusTcpClient


def env_str(key: str, default: str) -> str:
    v = os.getenv(key)
    return default if v is None or v == "" else v


def env_int(key: str, default: int) -> int:
    v = os.getenv(key)
    if v is None or v == "":
        return default
    return int(v)


def env_float(key: str, default: float) -> float:
    v = os.getenv(key)
    if v is None or v == "":
        return default
    return float(v)


# ========= Konfiguration (per ENV überschreibbar) =========
# Modbus TCP (Victron Venus)
VENUS_IP = env_str("VENUS_IP", "192.168.41.101")
VENUS_PORT = env_int("VENUS_PORT", 502)
MODBUS_TIMEOUT_S = env_float("MODBUS_TIMEOUT_S", 2.0)

# Heatpump consumption (W), uint32, scale 1
HP_UNIT_ID = env_int("HP_UNIT_ID", 31)
REG_HP_POWER_U32 = env_int("REG_HP_POWER_U32", 5502)
HP_WORDORDER = env_str("HP_WORDORDER", "big")  # falls HP-Wert unsinnig: "little" testen

# Impulsrate (z.B. 100 Imp/kWh => 10 Wh pro Puls)
IMP_PER_KWH = env_int("IMP_PER_KWH", 100)
# 1 kWh = 3_600_000 Ws = 3_600_000_000 Wms
WMS_PER_PULSE = 3_600_000_000 // max(1, IMP_PER_KWH)

# Optional: deckeln, damit Ausreißer nicht zu Puls-Stürmen führen
MAX_POWER_W = env_int("MAX_POWER_W", 25_000)

# Shelly: Relay pulsen (Gen1 API /relay/<idx>?turn=on)
SHELLY_IP = env_str("SHELLY_IP", "192.168.41.124")
SHELLY_RELAY_IDX = env_int("SHELLY_RELAY_IDX", 2)
SHELLY_ON_URL = env_str("SHELLY_ON_URL", f"http://{SHELLY_IP}/relay/{SHELLY_RELAY_IDX}?turn=on")

# Shelly: 30ms ON (intern), mind. 30ms OFF -> Sicherheitsabstand
MIN_TRIGGER_INTERVAL_S = env_float("MIN_TRIGGER_INTERVAL_S", 0.080)

HTTP_CONNECT_TIMEOUT_S = env_float("HTTP_CONNECT_TIMEOUT_S", 2.0)
HTTP_READ_TIMEOUT_S = env_float("HTTP_READ_TIMEOUT_S", 2.0)
HTTP_TIMEOUT = (HTTP_CONNECT_TIMEOUT_S, HTTP_READ_TIMEOUT_S)  # (connect, read)

POLL_INTERVAL_S = env_float("POLL_INTERVAL_S", 0.2)

# Logging / Glättung
LOG_EVERY_S = env_float("LOG_EVERY_S", 5.0)
ALPHA_AVG = env_float("ALPHA_AVG", 0.90)

# Shelly retry
SHELLY_RETRIES = env_int("SHELLY_RETRIES", 1)
RETRY_DELAY_S = env_float("RETRY_DELAY_S", 0.2)


def u32_from_regs(r0: int, r1: int, wordorder: str = "big") -> int:
    """uint32 aus 2x16-bit holding regs."""
    if wordorder == "little":
        return (r1 << 16) | r0
    return (r0 << 16) | r1


def read_hp_power_w(client: ModbusTcpClient) -> int:
    """
    Liest Heatpump-Power in Watt aus REG_HP_POWER_U32 (2 Register, uint32), Unit-ID HP_UNIT_ID.
    """
    rr = client.read_holding_registers(REG_HP_POWER_U32, count=2, slave=HP_UNIT_ID)
    if rr.isError():
        raise RuntimeError(f"Modbus read error: unit={HP_UNIT_ID} addr={REG_HP_POWER_U32} -> {rr}")

    r0, r1 = int(rr.registers[0]), int(rr.registers[1])
    p = int(u32_from_regs(r0, r1, HP_WORDORDER))

    if p < 0:
        p = 0
    if p > MAX_POWER_W:
        p = MAX_POWER_W
    return p


def shelly_trigger_pulse(session: requests.Session) -> None:
    """
    Triggert einen Puls (Shelly auto-off nach 30ms).
    """
    last_exc: Exception | None = None
    for attempt in range(SHELLY_RETRIES + 1):
        try:
            r = session.get(SHELLY_ON_URL, timeout=HTTP_TIMEOUT, headers={"Connection": "close"})
            r.raise_for_status()
            return
        except Exception as e:
            last_exc = e
            if attempt < SHELLY_RETRIES:
                time.sleep(RETRY_DELAY_S)
    raise last_exc  # type: ignore[misc]


def main() -> None:
    client = ModbusTcpClient(VENUS_IP, port=VENUS_PORT, timeout=MODBUS_TIMEOUT_S)
    session = requests.Session()

    last_ns = time.monotonic_ns()
    last_trigger_ts = 0.0

    # Energie-Integrator in W*ms
    energy_wms = 0

    # Queue für Pulse
    pulse_queue = 0
    pulses_sent = 0

    avg_power_w = 0.0
    last_log = 0.0

    while True:
        try:
            if not client.connect():
                raise RuntimeError("Modbus connect() fehlgeschlagen")

            now_ns = time.monotonic_ns()
            dt_ms = max(1, (now_ns - last_ns) // 1_000_000)  # integer ms
            last_ns = now_ns

            p_w = read_hp_power_w(client)
            avg_power_w = ALPHA_AVG * avg_power_w + (1.0 - ALPHA_AVG) * p_w

            # integrieren
            energy_wms += int(p_w) * int(dt_ms)

            # Pulse ernten
            if energy_wms >= WMS_PER_PULSE:
                add = energy_wms // WMS_PER_PULSE
                pulse_queue += int(add)
                energy_wms -= int(add) * WMS_PER_PULSE

            # gewünschter Pulsabstand aus aktueller Leistung
            desired_interval = (WMS_PER_PULSE / max(1, p_w)) / 1000.0  # ms -> s
            desired_interval = max(MIN_TRIGGER_INTERVAL_S, desired_interval)

            # Pulse senden (max 1 pro Loop), Mindestabstand beachten
            now = time.monotonic()
            if pulse_queue > 0 and (now - last_trigger_ts) >= MIN_TRIGGER_INTERVAL_S:
                try:
                    shelly_trigger_pulse(session)
                    pulses_sent += 1
                    pulse_queue -= 1
                    last_trigger_ts = time.monotonic()
                    print(
                        f"PULSE #{pulses_sent} @ {time.strftime('%H:%M:%S')} | "
                        f"HP={p_w}W | next~{desired_interval:.2f}s | queue={pulse_queue}"
                    )
                except Exception as e:
                    print(f"Shelly Fehler: {e} (Queue bleibt, retry später)")
                    time.sleep(1.0)

            # Status-Log
            if time.monotonic() - last_log > LOG_EVERY_S:
                last_log = time.monotonic()
                print(f"HP_power={p_w}W (avg~{int(avg_power_w)}W) queue={pulse_queue}")

            time.sleep(POLL_INTERVAL_S)

        except Exception as e:
            print(f"Fehler: {e}")
            try:
                client.close()
            except Exception:
                pass
            time.sleep(2.0)


if __name__ == "__main__":
    main()
