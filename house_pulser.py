#!/usr/bin/env python3
import os
import time
from typing import Optional, Tuple

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


def env_bool(key: str, default: bool) -> bool:
    v = os.getenv(key)
    if v is None or v == "":
        return default
    return v.strip().lower() in ("1", "true", "yes", "y", "on")


# =========================
# Netzwerk / Modbus (per ENV überschreibbar)
# =========================
VENUS_IP = env_str("VENUS_IP", "192.168.41.101")
VENUS_PORT = env_int("VENUS_PORT", 502)
MODBUS_TIMEOUT_S = env_float("MODBUS_TIMEOUT_S", 2.0)

# =========================
# Datenquellen (Modbus) (per ENV überschreibbar)
# =========================
# Household total consumption L1/L2/L3 (W), uint16, scale 1
HOUSE_UNIT_ID = env_int("HOUSE_UNIT_ID", 100)
REG_HOUSE_L1_W = env_int("REG_HOUSE_L1_W", 817)
REG_HOUSE_L2_W = env_int("REG_HOUSE_L2_W", 818)
REG_HOUSE_L3_W = env_int("REG_HOUSE_L3_W", 819)

# Heatpump consumption (W), uint32, scale 1
HP_UNIT_ID = env_int("HP_UNIT_ID", 31)
REG_HP_POWER_U32 = env_int("REG_HP_POWER_U32", 5502)
HP_WORDORDER = env_str("HP_WORDORDER", "big")  # falls HP-Wert unsinnig: "little" testen

# Wallbox / AC load (Shelly 3EM) L1/L2/L3 (W), uint16, scale 1
CHG_UNIT_ID = env_int("CHG_UNIT_ID", 52)
REG_CHG_L1_W = env_int("REG_CHG_L1_W", 3900)
REG_CHG_L2_W = env_int("REG_CHG_L2_W", 3901)
REG_CHG_L3_W = env_int("REG_CHG_L3_W", 3902)

# Wallbox berücksichtigen? (1/0, true/false, yes/no)
USE_WALLBOX = env_bool("USE_WALLBOX", True)

# =========================
# Pulse-Parameter (per ENV überschreibbar)
# =========================
IMP_PER_KWH = env_int("IMP_PER_KWH", 100)  # z.B. WP erwartet 100 Imp/kWh

# 1 kWh = 3_600_000 Ws = 3_600_000_000 Wms
WMS_PER_PULSE = 3_600_000_000 // max(1, IMP_PER_KWH)  # bei 100 Imp/kWh = 36_000_000 Wms (=10 Wh)

# optional: deckeln (falls du nie mehr als X W abbilden willst)
MAX_NET_POWER_W = env_int("MAX_NET_POWER_W", 25_000)

# =========================
# Shelly (per ENV überschreibbar)
# =========================
SHELLY_IP = env_str("SHELLY_IP", "192.168.41.124")
SHELLY_RELAY_IDX = env_int("SHELLY_RELAY_IDX", 1)
SHELLY_ON_URL = env_str("SHELLY_ON_URL", f"http://{SHELLY_IP}/relay/{SHELLY_RELAY_IDX}?turn=on")

# Shelly: 30ms ON intern + mind. 30ms OFF -> Sicherheitsabstand
MIN_TRIGGER_INTERVAL_S = env_float("MIN_TRIGGER_INTERVAL_S", 0.080)  # 80ms

HTTP_CONNECT_TIMEOUT_S = env_float("HTTP_CONNECT_TIMEOUT_S", 2.0)
HTTP_READ_TIMEOUT_S = env_float("HTTP_READ_TIMEOUT_S", 2.0)
HTTP_TIMEOUT = (HTTP_CONNECT_TIMEOUT_S, HTTP_READ_TIMEOUT_S)  # (connect, read)

SHELLY_RETRIES = env_int("SHELLY_RETRIES", 1)
RETRY_DELAY_S = env_float("RETRY_DELAY_S", 0.2)

# =========================
# Loop / Logging (per ENV überschreibbar)
# =========================
POLL_INTERVAL_S = env_float("POLL_INTERVAL_S", 0.2)
LOG_EVERY_S = env_float("LOG_EVERY_S", 5.0)
ALPHA_AVG = env_float("ALPHA_AVG", 0.90)


# =========================
# Helpers
# =========================
def u32_from_regs(r0: int, r1: int, wordorder: str = "big") -> int:
    """uint32 aus 2x16-bit holding regs."""
    if wordorder == "little":
        return (r1 << 16) | r0
    # default "big"
    return (r0 << 16) | r1


def read_u16_3sum(client: ModbusTcpClient, unit_id: int, base_addr: int) -> Tuple[int, int, int, int]:
    """Liest 3x uint16 ab base_addr -> (sum, a, b, c)."""
    rr = client.read_holding_registers(base_addr, count=3, slave=unit_id)
    if rr.isError():
        raise RuntimeError(f"Modbus read error: unit={unit_id} addr={base_addr} -> {rr}")
    a, b, c = int(rr.registers[0]), int(rr.registers[1]), int(rr.registers[2])
    s = a + b + c
    if s < 0:
        s = 0
    return s, a, b, c


def read_house_power_w(client: ModbusTcpClient) -> Tuple[int, int, int, int]:
    return read_u16_3sum(client, HOUSE_UNIT_ID, REG_HOUSE_L1_W)


def read_wallbox_power_w(client: ModbusTcpClient) -> Tuple[int, int, int, int]:
    # CHG = Wallbox (AC load)
    return read_u16_3sum(client, CHG_UNIT_ID, REG_CHG_L1_W)


def read_hp_power_w(client: ModbusTcpClient) -> int:
    rr = client.read_holding_registers(REG_HP_POWER_U32, count=2, slave=HP_UNIT_ID)
    if rr.isError():
        raise RuntimeError(f"Modbus read error: unit={HP_UNIT_ID} addr={REG_HP_POWER_U32} -> {rr}")
    r0, r1 = int(rr.registers[0]), int(rr.registers[1])
    val = u32_from_regs(r0, r1, wordorder=HP_WORDORDER)
    if val < 0:
        val = 0
    return val


def shelly_trigger_pulse(session: requests.Session) -> None:
    """Triggert einen Puls (Shelly auto-off nach 30ms)."""
    last_exc: Optional[Exception] = None
    for attempt in range(SHELLY_RETRIES + 1):
        try:
            r = session.get(SHELLY_ON_URL, timeout=HTTP_TIMEOUT, headers={"Connection": "close"})
            r.raise_for_status()
            return
        except Exception as e:
            last_exc = e
            if attempt < SHELLY_RETRIES:
                time.sleep(RETRY_DELAY_S)
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("Shelly trigger failed (unknown error)")


# =========================
# Main
# =========================
def main() -> None:
    client = ModbusTcpClient(VENUS_IP, port=VENUS_PORT, timeout=MODBUS_TIMEOUT_S)
    session = requests.Session()

    last_ns = time.monotonic_ns()
    last_trigger_ts = 0.0

    # Energie-Integrator (W*ms) + Pulsqueue
    energy_wms = 0
    pulse_queue = 0

    pulses_sent = 0
    avg_net = 0.0
    last_log_ts = 0.0

    while True:
        try:
            # Zeitdelta
            now_ns = time.monotonic_ns()
            dt_ms = max(1, (now_ns - last_ns) // 1_000_000)
            last_ns = now_ns

            if not client.connect():
                raise RuntimeError("Modbus connect() fehlgeschlagen")

            # House
            house_sum, h_l1, h_l2, h_l3 = read_house_power_w(client)

            # HP robust lesen (bei Fehler: 0 annehmen, damit es weiterläuft)
            try:
                hp_w = read_hp_power_w(client)
            except Exception as e:
                hp_w = 0
                print(f"Warn: HP read failed -> assume 0W ({e})")

            # Wallbox optional
            if USE_WALLBOX:
                try:
                    chg_sum, c_l1, c_l2, c_l3 = read_wallbox_power_w(client)
                except Exception as e:
                    chg_sum, c_l1, c_l2, c_l3 = 0, 0, 0, 0
                    print(f"Warn: Wallbox read failed -> assume 0W ({e})")
            else:
                chg_sum, c_l1, c_l2, c_l3 = 0, 0, 0, 0

            # Netto
            net_w = int(house_sum - hp_w - chg_sum)
            if net_w < 0:
                net_w = 0
            if net_w > MAX_NET_POWER_W:
                net_w = MAX_NET_POWER_W

            avg_net = (ALPHA_AVG * avg_net) + ((1.0 - ALPHA_AVG) * net_w)

            # integrieren (W*ms)
            energy_wms += int(net_w) * int(dt_ms)

            # Pulse ernten
            if energy_wms >= WMS_PER_PULSE:
                add = energy_wms // WMS_PER_PULSE
                pulse_queue += int(add)
                energy_wms -= int(add) * WMS_PER_PULSE

            # gewünschter Pulsabstand aus aktueller Netto-Leistung
            desired_interval = (WMS_PER_PULSE / max(1, net_w)) / 1000.0  # ms -> s
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
                        f"House={house_sum}W - HP={hp_w}W - "
                        f"Wallbox={('DISABLED' if not USE_WALLBOX else str(chg_sum)+'W')} => Net={net_w}W | "
                        f"next~{desired_interval:.1f}s | queue={pulse_queue}"
                    )
                except Exception as e:
                    print(f"Shelly Fehler: {e} (Queue bleibt, retry später)")
                    time.sleep(1.0)

            # Statuslog
            if (now - last_log_ts) >= LOG_EVERY_S:
                last_log_ts = now
                print(
                    f"Net={net_w}W (avg~{int(avg_net)}W) | "
                    f"House={house_sum}W (L1={h_l1} L2={h_l2} L3={h_l3}) | "
                    f"HP={hp_w}W | "
                    f"Wallbox={('DISABLED' if not USE_WALLBOX else str(chg_sum)+'W')} "
                    f"(L1={c_l1} L2={c_l2} L3={c_l3}) | "
                    f"queue={pulse_queue}"
                )

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
