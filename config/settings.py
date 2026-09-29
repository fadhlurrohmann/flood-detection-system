"""
Global configuration for EFWS.
All value sensitive read from file .env (via python-dotenv).
File .env NOT may in-commit to git — see .env.example for template.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# ─── Find .env in a automatically (up folder until found) ───────────────────
def _find_and_load_dotenv():
    """
    Find file .env start from location settings.py, up to above until 2 level.
    This so that not matter how inside structure folder project.
    """
    search_start = Path(__file__).resolve().parent  # start from config/
    for candidate in [search_start, *search_start.parents[:2]]:
        env_file = candidate / ".env"
        if env_file.exists():
            print(f"[OK] Found .env at {env_file}, loading...")
            load_dotenv(env_file, override=True)
            return candidate   # return root that found
    # Not found .env — load_dotenv still running (read from env var system only)
    print("[INFO] .env not found; using defaults and system environment variables.")
    load_dotenv(override=True)
    return search_start.parent

_ROOT = _find_and_load_dotenv()
print("ROOT :", _ROOT)
print("EFWS_API_URL =", os.getenv("EFWS_API_URL"))


# ─── Helper ──────────────────────────────────────────────────────────────────
def _req(key: str) -> str:
    """Read env var required. Raise error clear if none."""
    val = os.getenv(key)
    if not val:
        raise EnvironmentError(
            f"\n\n  ❌  Environment variable '{key}' not found.\n"
            f"      Ensure file .env exists in root project and already filled in.\n"
            f"      Example: cp .env.example .env\n"
        )
    return val

def _opt(key: str, default: str = "") -> str:
    return os.getenv(key, default)

def _int(key: str, default: int) -> int:
    return int(os.getenv(key, str(default)))

def _float(key: str, default: float) -> float:
    return float(os.getenv(key, str(default)))

def _bool(key: str, default: bool = True) -> bool:
    return os.getenv(key, str(default)).lower() in ("1", "true", "yes")


# ─── Device Identity ─────────────────────────────────────────────────────────
DEVICE_ID    = _opt("EFWS_DEVICE_ID",    "FLOOD-JAM-TEST02")
DEVICE_TOKEN = _opt("EFWS_DEVICE_TOKEN", "test")
DEVICE_LOCATION = {
    "lat": _float("EFWS_LAT", 0.0),
    "lon": _float("EFWS_LON", 0.0),
}

# ─── Mode operation ────────────────────────────────────────────────────────────
RUN_MODE = _opt("EFWS_RUN_MODE", "mock").strip().lower()
if RUN_MODE not in {"mock", "hardware"}:
    raise ValueError("EFWS_RUN_MODE must be either 'mock' or 'hardware'")

# ─── I2C (BME280 — temperature/humidity/pressure ambient, native I2C) ────────────
I2C_BUS        = _int("EFWS_I2C_BUS", 1)
BME280_ADDRESS = int(_opt("EFWS_BME280_ADDR", "0x76"), 16)

# ─── SPI / MCP3008 (ADC 8-channel, ONE Logic Level Converter) ─────────────
# Hardware version: 1x MCP3008, 1x LLC (at least 6 channels, such as an 8-channel module),
# 2x soil probe, MQ-2, MQ-135, anemometer RS485 (directly USB, without LLC),
# submersible pressure sensor (loop 4-20mA + burden resistor), module sensor
# battery voltage DC 0-25V, and modem 4G (A7670E OR SIM7600 — auto-detect,
# only one that installed).
#
#   LLC (HV=5V, LV=3.3V) — all sensor analog 0-5V:
#     HV-1 → LV-1 : Soil Surface AOUT                     → CH0
#     HV-2 → LV-2 : Soil Deep    AOUT                     → CH1
#     HV-3 → LV-3 : Pressure sensor (through R_BURDEN)      → CH2
#     HV-4 → LV-4 : Voltage Sensor Module OUT             → CH3
#     HV-5..8 / CH4-CH7 : spare, not wired
SPI_BUS          = _int("EFWS_SPI_BUS", 0)
SPI_DEVICE       = _int("EFWS_SPI_DEVICE", 0)
SPI_MAX_SPEED_HZ = _int("EFWS_SPI_SPEED", 1350000)
MCP3008_VREF     = _float("EFWS_MCP3008_VREF", 3.3)

ADC_CHANNEL_SOIL_SURFACE    = _int("EFWS_ADC_SOIL_SURFACE",  0)   # LLC HV-0 (probe 0-30cm)
ADC_CHANNEL_SOIL_DEEP       = _int("EFWS_ADC_SOIL_DEEP",     1)   # LLC HV-1 (probe 30-60cm)
# Compatibility for older deployments that used this incorrect setting name.
ADC_CHANNEL_WATER_FLOW      = _int("EFWS_ADC_WATER_FLOW", ADC_CHANNEL_SOIL_DEEP)
ADC_CHANNEL_PRESSURE        = _int("EFWS_ADC_PRESSURE",      2)   # LLC HV-2 (pressure sensor via R_BURDEN)
ADC_CHANNEL_BATTERY         = _int("EFWS_ADC_BATTERY",       3)   # LLC HV-3 (voltage sensor module OUT)
# CH4-CH7 are not wired and remain spare MCP3008 channels.

# ─── Gravity Rainfall Sensor (DFRobot SEN0575) ─────────────────────────────
I2C_BUS = 1
# DFRobot SEN0575
RAINFALL_I2C_ADDRESS = 0x1D
# Interval reading (seconds)
RAINFALL_READ_INTERVAL = 2

# ─── Battery — Module Sensor Voltage DC 0-25V ────────────────────────────────
BATTERY_SENSOR_MAX_V = _float("EFWS_BATTERY_SENSOR_MAX_V", 25.0)  # max input module sensor (V)
BATTERY_MAX_V        = _float("EFWS_BATTERY_MAX_V",        12.6)  # battery voltage full (V)
BATTERY_MIN_V        = _float("EFWS_BATTERY_MIN_V",         9.0)  # battery voltage empty (V)

# ─── Submersible Pressure Sensor — loop 4-20mA ──────────────────────────────
# Sensor loop-powered 2-cable, read via burden resistor presisi then LLC
# (see sensors/pressure.py for calculation and wiring details).
PRESSURE_BURDEN_OHM = _float("EFWS_PRESSURE_BURDEN_OHM", 100)  # 4mA→0.4V, 20mA→2V
PRESSURE_MIN_MA     = _float("EFWS_PRESSURE_MIN_MA",       4.0)
PRESSURE_MAX_MA     = _float("EFWS_PRESSURE_MAX_MA",      20.0)
PRESSURE_RANGE_M    = _float("EFWS_PRESSURE_RANGE_M",      3.0)  # range full sensor, adjust datasheet
PRESSURE_ADC_REF_VOLTAGE = _float("EFWS_PRESSURE_ADC_REF_VOLTAGE",3.3)


GPIO_RELAY_SIREN  = _int("EFWS_GPIO_RELAY",  27)
GPIO_STATUS_LED   = _int("EFWS_GPIO_LED",    23)


#-------- JSN-SR04T----------
GPIO_JSN_TRIG = _int("EFWS_GPIO_JSN_TRIG", _int("EWF_JSN_TRIG", 22))
GPIO_JSN_ECHO = _int("EFWS_GPIO_JSN_ECHO", _int("EWF_JSN_ECHO", 18))

#------- YF-S201-------------
GPIO_YF = _int("EFWS_GPIO_YF", _int("EWF_GPIO_YF", 16))

# ─── A7670E / SIM7670E 4G LTE Cat-1 ──────────────────────────────────────────────────────────
A7670E_AT_PORT  = _opt("EFWS_SIM_PORT", "/dev/ttyUSB2")
A7670E_BAUDRATE = _int("EFWS_A7670E_BAUD", 115200)
APN              = _opt("EFWS_APN", "internet")

# Compatibility names used by the direct SIM7600 driver.
SIM7600_AT_PORT = _opt("EFWS_SIM7600_PORT", A7670E_AT_PORT)
SIM7600_BAUDRATE = _int("EFWS_SIM7600_BAUD", A7670E_BAUDRATE)
GPS_TIMEOUT = _int("EFWS_GPS_TIMEOUT", 90)

# ─── REST API ────────────────────────────────────────────────────────────────
API_BASE_URL = _opt("EFWS_API_URL", "http://127.0.0.1:5000/api/v1/efws")
# Endpoint URLs are intentionally resolved through the functions below instead
# of module constants. This ensures runtime calls use the latest EFWS_API_URL,
# including after the .env file changes and the service restarts. Four endpoints exist:
#   telemetry_endpoint()   -> /sensors/telemetry     (scheduled, bawa config remote)
#   location_endpoint()    -> /sensors/location       (scheduled)
#   heartbeat_endpoint()   -> /sensors/heartbeat      (scheduled, bawa commands)
#   command_ack_endpoint() -> /sensors/commands/ack   (event-driven, from commands)

def _base_url() -> str:
    return os.getenv("EFWS_API_URL", API_BASE_URL).rstrip("/")

def telemetry_endpoint() -> str:
    """Sensor telemetry endpoint; its response may contain remote threshold config."""
    return _base_url() + "/sensors/telemetry"

def location_endpoint() -> str:
    """Update posisi GPS/fallback device."""
    return _base_url() + "/sensors/location"

def heartbeat_endpoint() -> str:
    """Health endpoint where the backend may provide commands such as Reboot."""
    return _base_url() + "/sensors/heartbeat"

def command_ack_endpoint() -> str:
    """ACK result execute command that received through heartbeat. Event-driven, not scheduled."""
    return _base_url() + "/sensors/commands/ack"

API_SECRET_KEY     = _opt("EFWS_API_KEY", "")
API_VERIFY_SSL     = _bool("EFWS_VERIFY_SSL", True)
API_TIMEOUT_SEC    = _int("EFWS_API_TIMEOUT", 10)
API_MAX_RETRIES    = _int("EFWS_API_RETRIES", 3)
API_RETRY_DELAY    = _int("EFWS_API_RETRY_DELAY", 5)

# ─── Local database ──────────────────────────────────────────────────────────
DB_PATH = _opt("EFWS_DB_PATH", str(_ROOT / "database" / "efws_data.db"))

# Retention local data -- rows sensor_readings & api_queue (that whose status
# is complete: sent OR already discarded permanently) that more old from
# this automatically DELETED by background thread (see main.py:
# EFWS._retention_loop). This deleting ROWS-ROWS old in inside database,
# NOT deleting file database that its own -- tabel & data newest still exists.
DB_RETENTION_DAYS        = _int("EFWS_DB_RETENTION_DAYS", 3)
DB_RETENTION_CHECK_SEC   = _int("EFWS_DB_RETENTION_CHECK_SEC", 6 * 3600)  # check every 6 hours

# ─── Log files ───────────────────────────────────────────────────────────────
LOG_PATH = _opt("EFWS_LOG_PATH", str(_ROOT / "logs" / "efws.log"))

# ─── Timing ──────────────────────────────────────────────────────────────────
# Cycle CHECK sensor -- always running every interval this, purely evaluation
# threshold (fast, for deteksi emergency responsive). NOT always means
# send data -- see ROUTINE_SEND_INTERVAL_SEC below.
SENSOR_READ_INTERVAL_SEC = _int("EFWS_READ_INTERVAL", 180)
# Set to a positive number for smoke tests or one-shot runs. Zero runs forever.
MAX_CYCLES = _int("EFWS_MAX_CYCLES", 0)

# Cycle Routine send (location+telemetry+heartbeat) when condition NORMAL --
# INTENTIONALLY separated from SENSOR_READ_INTERVAL_SEC: threshold still checked every
# 3 minutes (response fast if emergency), but if all normal, device
# enough report to backend every ROUTINE_SEND_INTERVAL_SEC (default 3600s /
# 60 minutes) so that not appear off/lost without flooding API.
# Once exists threshold that exceeded, send DIRECTLY when that also
# ("emergency upload") without waiting schedule rutin this, and schedule rutin
# is reset from that point because the backend has just received a report.
ROUTINE_SEND_INTERVAL_SEC = _int("EFWS_ROUTINE_SEND_INTERVAL_SEC", 360)

# Retry offline queue -- running in separate thread from cycle read sensors
# (see main.py EFWS._flush_queue_loop), so that still every 2 minutes exactly
# although read cycle now 3 minutes.
EFWS_CONNECTIVITY_CHECK_SEC = _int("EFWS_CONNECTIVITY_CHECK_SEC", 120)

# ─── Command executor (endpoint 4: /sensors/commands/ack) ──────────────────
# Delay before restarting after a "Reboot" command is received.
# Why needs delay: process this must sempat SENDING ack SUCCESS first
# before systemctl restart terminates process Python that medium running.
# See main.py: EFWS._cmd_reboot() for details.
COMMAND_REBOOT_DELAY_SEC = _int("EFWS_REBOOT_DELAY_SEC", 5)

# ─── Threshold file ──────────────────────────────────────────────────────────
THRESHOLDS_PATH = str(_ROOT / "config" / "thresholds.json")
