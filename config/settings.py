"""
Global configuration for EFWS.
All sensitive values are read from the .env file (via python-dotenv).
The .env file must NOT be committed to git — see .env.example for the template.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# ─── Find .env automatically (walk up the folders until it is found) ─────────
def _find_and_load_dotenv():
    """
    Look for the .env file starting from the location of settings.py, going up at most 2 levels.
    This way it does not matter how deep the project folder structure is.
    """
    search_start = Path(__file__).resolve().parent  # start from config/
    for candidate in [search_start, *search_start.parents[:2]]:
        env_file = candidate / ".env"
        if env_file.exists():
            print(f"✅  Found .env at {env_file}, loading...")
            load_dotenv(env_file, override=True)
            return candidate   # return the root that was found
    # .env not found — load_dotenv still runs (reads system env vars only)
    print("❌  .env not found, using system environment variables only.")
    load_dotenv(override=True)
    return search_start.parent   # project root (one level above config/)

_ROOT = _find_and_load_dotenv()
print("ROOT :", _ROOT)
print("EFWS_API_URL =", os.getenv("EFWS_API_URL"))


# ─── Helper ──────────────────────────────────────────────────────────────────
def _req(key: str) -> str:
    """Read a required env var. Raise a clear error if it is missing."""
    val = os.getenv(key)
    if not val:
        raise EnvironmentError(
            f"\n\n  ❌  Environment variable '{key}' was not found.\n"
            f"      Make sure the .env file exists in the project root and is filled in.\n"
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

# ─── Operating mode ──────────────────────────────────────────────────────────
RUN_MODE = _opt("EFWS_RUN_MODE", "hardware")

# ─── I2C (BME280 — ambient temperature/humidity/pressure, native I2C) ───────
I2C_BUS        = _int("EFWS_I2C_BUS", 1)
BME280_ADDRESS = int(_opt("EFWS_BME280_ADDR", "0x76"), 16)

# ─── SPI / MCP3008 (8-channel ADC, direct analog input, WITHOUT an LLC) ─────
# Hardware version: 1x MCP3008, 1x LLC (only for 5V digital signals → GPIO),
# RS485 anemometer (direct USB, no LLC),
# submersible pressure sensor (4-20mA loop + burden resistor), DC 0-25V
# battery voltage sensor module, and a 4G modem (A7670E OR SIM7600 — auto-detect,
# only one is installed).
#
#   MCP3008 channel map:
#     CH2 : Pressure sensor via R_BURDEN — direct, WITHOUT an LLC (max ~2V)
#     CH3 : Voltage Sensor Module S  — direct (max ~2.9V)
#     CH0, CH1, CH4-CH7 : spare, not wired
SPI_BUS          = _int("EFWS_SPI_BUS", 0)
SPI_DEVICE       = _int("EFWS_SPI_DEVICE", 0)
SPI_MAX_SPEED_HZ = _int("EFWS_SPI_SPEED", 1350000)
MCP3008_VREF     = _float("EFWS_MCP3008_VREF", 3.3)

ADC_CHANNEL_PRESSURE        = _int("EFWS_ADC_PRESSURE",      2)   # via R_BURDEN, no LLC
ADC_CHANNEL_BATTERY         = _int("EFWS_ADC_BATTERY",       3)   # voltage sensor module S, direct
# CH0, CH1, CH4-CH7 are not wired — physical spares on the MCP3008

# ─── Gravity Rainfall Sensor (DFRobot SEN0575) ─────────────────────────────
I2C_BUS = 1
# DFRobot SEN0575
RAINFALL_I2C_ADDRESS = 0x1D
# Read interval (seconds)
RAINFALL_READ_INTERVAL = 2

# ─── Battery — DC 0-25V Voltage Sensor Module ─────────────────────────────────
# V_battery = raw/1023 × MCP3008_VREF × BATTERY_DIVIDER_RATIO. Calibration: ratio = battery V (multimeter) / V at pin S.
BATTERY_DIVIDER_RATIO = _float("EFWS_BATTERY_DIVIDER_RATIO", 5.0)  # 30k/7.5k module
BATTERY_MAX_V        = _float("EFWS_BATTERY_MAX_V",        12.6)  # fully charged battery voltage (V)
BATTERY_MIN_V        = _float("EFWS_BATTERY_MIN_V",         9.0)  # empty battery voltage (V)

# ─── Submersible Pressure Sensor — 4-20mA loop ──────────────────────────────
# 2-wire loop-powered sensor, read via a precision burden resistor straight into the MCP3008 (no LLC)
# (see sensors/pressure.py for the calculation & wiring details).
PRESSURE_BURDEN_OHM = _float("EFWS_PRESSURE_BURDEN_OHM", 100)  # 4mA→0.4V, 20mA→2.0V
PRESSURE_MIN_MA     = _float("EFWS_PRESSURE_MIN_MA",       4.0)
PRESSURE_MAX_MA     = _float("EFWS_PRESSURE_MAX_MA",      20.0)
PRESSURE_RANGE_M    = _float("EFWS_PRESSURE_RANGE_M",      3.0)  # full sensor range, adjust to the datasheet
PRESSURE_ADC_REF_VOLTAGE = _float("EFWS_PRESSURE_ADC_REF_VOLTAGE",3.3)


GPIO_RELAY_SIREN  = _int("EFWS_GPIO_RELAY",  27)
GPIO_STATUS_LED   = _int("EFWS_GPIO_LED",    23)


#-------- JSN-SR04T----------
GPIO_JSN_TRIG = _int("EWF_JSN_TRIG", 22)
GPIO_JSN_ECHO = _int("EWF_JSN_ECHO", 18)

#------- YF-S201-------------
GPIO_YF = _int("EWF_GPIO_YF", 16)

# ─── RS485 wind-speed anemometer (Modbus RTU) ───────────────────────────────
# Verify register address and scale against the specific anemometer datasheet.
ANEMOMETER_PORT = _opt("EFWS_ANEM_PORT", "/dev/ttyUSB0")
ANEMOMETER_BAUDRATE = _int("EFWS_ANEM_BAUDRATE", 9600)
ANEMOMETER_SLAVE_ID = _int("EFWS_ANEM_SLAVE_ID", 1)
ANEMOMETER_SPEED_REGISTER = int(_opt("EFWS_ANEM_SPEED_REGISTER", "0"), 0)
ANEMOMETER_FUNCTION_CODE = _int("EFWS_ANEM_FUNCTION_CODE", 3)
ANEMOMETER_SPEED_SCALE = _float("EFWS_ANEM_SPEED_SCALE", 0.1)

# ─── A7670E / SIM7670E 4G LTE Cat-1 ──────────────────────────────────────────────────────────
A7670E_AT_PORT  = _opt("EFWS_SIM_PORT", "/dev/ttyUSB2")
A7670E_BAUDRATE = _int("EFWS_A7670E_BAUD", 115200)
APN              = _opt("EFWS_APN", "internet")

# ─── REST API ────────────────────────────────────────────────────────────────
API_BASE_URL       = _req("EFWS_API_URL")
# NOTE: the endpoint URLs are DELIBERATELY not defined as module
# constants, but through the dynamic functions below, so the URL in effect at
# runtime always uses the current EFWS_API_URL from the env — including when
# .env is changed and the service is restarted. There are 4 endpoints:
#   telemetry_endpoint()   -> /sensors/telemetry     (scheduled, carries remote config)
#   location_endpoint()    -> /sensors/location       (scheduled)
#   heartbeat_endpoint()   -> /sensors/heartbeat      (scheduled, carries commands)
#   command_ack_endpoint() -> /sensors/commands/ack   (event-driven, from commands)

def _base_url() -> str:
    return os.getenv("EFWS_API_URL", API_BASE_URL).rstrip("/")

def telemetry_endpoint() -> str:
    """Sensor data (waterLevel, rainfallMm, etc.). Its response carries 'config' (remote thresholds)."""
    return _base_url() + "/sensors/telemetry"

def location_endpoint() -> str:
    """Update the device's GPS/fallback position."""
    return _base_url() + "/sensors/location"

def heartbeat_endpoint() -> str:
    """Health check + where the backend leaves 'commands' (e.g. Reboot)."""
    return _base_url() + "/sensors/heartbeat"

def command_ack_endpoint() -> str:
    """ACK of the result of executing a command received via heartbeat. Event-driven, not scheduled."""
    return _base_url() + "/sensors/commands/ack"

API_SECRET_KEY     = _opt("EFWS_API_KEY", "")
API_VERIFY_SSL     = _bool("EFWS_VERIFY_SSL", True)
API_TIMEOUT_SEC    = _int("EFWS_API_TIMEOUT", 10)
API_MAX_RETRIES    = _int("EFWS_API_RETRIES", 3)
API_RETRY_DELAY    = _int("EFWS_API_RETRY_DELAY", 5)

# ─── Local database ──────────────────────────────────────────────────────────
DB_PATH = _opt("EFWS_DB_PATH", str(_ROOT / "database" / "efws_data.db"))

# Local data retention -- rows in sensor_readings & api_queue (those already
# finished: delivered OR permanently discarded) older than this are
# automatically DELETED by a background thread (see main.py:
# EFWS._retention_loop). This deletes old ROWS inside the database,
# NOT the database file itself -- the tables & recent data stay.
DB_RETENTION_DAYS        = _int("EFWS_DB_RETENTION_DAYS", 3)
DB_RETENTION_CHECK_SEC   = _int("EFWS_DB_RETENTION_CHECK_SEC", 6 * 3600)  # check every 6 hours

# ─── Log files ───────────────────────────────────────────────────────────────
LOG_PATH = _opt("EFWS_LOG_PATH", str(_ROOT / "logs" / "efws.log"))

# ─── Timing ──────────────────────────────────────────────────────────────────
# Sensor CHECK cycle -- always runs every this interval, purely evaluating
# thresholds (fast, for responsive emergency detection). Does NOT always mean
# sending data -- see ROUTINE_SEND_INTERVAL_SEC below.
SENSOR_READ_INTERVAL_SEC = _int("EFWS_READ_INTERVAL", 180)

# Routine SEND cycle (location+telemetry+heartbeat) in NORMAL conditions --
# DELIBERATELY separate from SENSOR_READ_INTERVAL_SEC: thresholds are still checked every
# 3 minutes (fast response in an emergency), but when everything is normal, the device
# only needs to report to the backend every ROUTINE_SEND_INTERVAL_SEC (default 3600s /
# 60 minutes) so it does not look dead/missing without flooding the API.
# As soon as a threshold is crossed, send IMMEDIATELY at that moment
# ("emergency upload") without waiting for this routine schedule, and the routine schedule
# is reset from that point (because the backend has just received a report).
ROUTINE_SEND_INTERVAL_SEC = _int("EFWS_ROUTINE_SEND_INTERVAL_SEC", 360)

# Offline queue retry -- runs in a SEPARATE thread from the sensor read cycle
# (see main.py EFWS._flush_queue_loop), so it stays exactly every 2 minutes
# even though the read cycle is now 3 minutes.
EFWS_CONNECTIVITY_CHECK_SEC = _int("EFWS_CONNECTIVITY_CHECK_SEC", 120)

# ─── Command executor (endpoint 4: /sensors/commands/ack) ──────────────────
# Delay before actually restarting after a "Reboot" command is received.
# Why a delay is needed: this process must get to SEND the SUCCESS ack first
# before systemctl restart kills the running Python process.
# See main.py: EFWS._cmd_reboot() for details.
COMMAND_REBOOT_DELAY_SEC = _int("EFWS_REBOOT_DELAY_SEC", 5)

# ─── Threshold file ──────────────────────────────────────────────────────────
THRESHOLDS_PATH = str(_ROOT / "config" / "thresholds.json")
