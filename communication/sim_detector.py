"""
SIM Auto-Detector — automatically detects whether this node uses an
A7670E/SIM7670E (LTE Cat-1) or SIM7600 (LTE Cat-4/3G) module.

How it works:
  1. Scan all available /dev/ttyUSBx ports.
  2. Send an AT command to each port; if one responds, check the module identity
     via ATI (Product Identification Information).
  3. A7670E/SIM7670E → instantiate the A7670E class (GNSS command: AT+CGNSSPWR)
  4. SIM7600           → instantiate the SIM7600 class (GNSS command: AT+CGPS)
  5. The detection result is saved in .sim_cache (a text file) so the next boot
     goes straight to the right port without rescanning.

Why two separate classes (not one unified)?
  The AT commands for GNSS differ between the A7670E and the SIM7600, and
  mixing both in one class would sacrifice code clarity.
  This auto-detector acts as the bridge — callers in main.py do not need to know
  which module is used, because the public interface is the same.

Usage:
  from communication.sim_detector import detect_sim, SimInterface
  sim = detect_sim()              # auto-detect at startup
  coords = sim.get_gps()          # unified API, regardless of the physical module
"""
import os
import time
import logging
import glob
import json
from pathlib import Path

try:
    import serial
except ImportError:
    serial = None

from config import settings

logger = logging.getLogger("efws.sim_detector")

CACHE_FILE = Path(__file__).parent.parent / ".sim_cache"
SCAN_PORTS = ["/dev/ttyUSB2", "/dev/ttyUSB3", "/dev/ttyUSB1", "/dev/ttyUSB0"]
BAUD       = 115200
TIMEOUT    = 2


# ─── ATI fingerprint → module ────────────────────────────────────────────────
# Keywords that appear in the ATI response for each module.
# Add other variants if there are other SIMCom modules in this project.
_FINGERPRINTS = {
    "a7670e":  ["A7670E", "A7670", "SIM7670"],
    "sim7600": ["SIM7600", "SIM7600E", "SIM7600G"],
}


def _send_at(ser, cmd: str, wait: float = 1.0) -> str:
    ser.reset_input_buffer()
    ser.write((cmd + "\r\n").encode())
    time.sleep(wait)
    return ser.read(ser.in_waiting or 1).decode(errors="ignore")


def _identify_port(port: str) -> "str | None":
    """
    Open the port, send AT, send ATI.
    Return: "a7670e", "sim7600", or None (not recognised / not responding).
    """
    if serial is None:
        raise RuntimeError("pyserial is not installed - pip install pyserial")
    try:
        ser = serial.Serial(port, BAUD, timeout=TIMEOUT)
        at_resp = _send_at(ser, "AT", wait=1.0)
        if "OK" not in at_resp:
            ser.close()
            return None

        ati_resp = _send_at(ser, "ATI", wait=1.0).upper()
        ser.close()

        for module_key, keywords in _FINGERPRINTS.items():
            if any(kw.upper() in ati_resp for kw in keywords):
                return module_key

        # Responds to AT but ATI does not match a fingerprint — probably another SIMCom module
        logger.warning("Port %s responds to AT but is not recognised from ATI: %s",
                       port, ati_resp[:80])
        return None

    except serial.SerialException as e:
        logger.debug(
            "%s busy (%s)",
            port,
            e
        )

        return None

    except OSError as e:
        logger.debug(
            "%s error (%s)",
            port,
            e
        )

        return None


def scan_ports() -> "dict | None":
    """
    Scan all candidate serial ports, return a dict {port, module} when one is found,
    or None if none respond.
    """
    # Merge with the glob result so ports that are not in SCAN_PORTS are included
    candidates = list(dict.fromkeys(
        SCAN_PORTS + sorted(glob.glob("/dev/ttyUSB*"))
    ))

    logger.info("🔍 Scanning %d candidate port(s) for a SIM module...", len(candidates))
    for port in candidates:
        if not os.path.exists(port):
            continue
        logger.debug("  Trying %s ...", port)
        module = _identify_port(port)
        if module:
            logger.info("  ✅ Module %s found on %s", module.upper(), port)
            return {"port": port, "module": module}

    logger.warning("❌ No SIM module detected on any port.")
    return None


def _load_cache() -> "dict | None":
    try:
        data = json.loads(CACHE_FILE.read_text())
        # Validate that the port still exists (it can change after a reboot)
        if os.path.exists(data.get("port", "")):
            logger.info("📋 SIM cache: port=%s module=%s", data["port"], data["module"])
            return data
        logger.info("Cache stale (port %s does not exist), rescanning...", data.get("port"))
    except Exception:
        pass
    return None


def _save_cache(info: dict):
    try:
        CACHE_FILE.write_text(json.dumps(info))
    except Exception:
        pass


def detect_sim(force_scan: bool = False) -> "SimInterface":

    if settings.RUN_MODE == "mock":
        logger.info("MOCK mode — using MockSimInterface.")
        return MockSimInterface()

    info = None if force_scan else _load_cache()

    # ==========================
    # CACHE VALIDATION
    # ==========================

    if info is not None:

        try:

            sim = SimInterface(
                port=info["port"],
                module=info["module"],
            )

            if sim.check_module():
                return sim

            logger.warning(
                "Cache not valid (AT does not respond), rescanning..."
            )

        except Exception as e:

            logger.warning(
                "Cache failed (%s), rescanning...",
                e
            )

        info = None

    # ==========================
    # RESCAN
    # ==========================

    if info is None:

        info = scan_ports()

        if info:
            _save_cache(info)

        else:
            raise RuntimeError(
                "No SIM module detected."
            )

    return SimInterface(
        port=info["port"],
        module=info["module"],
    )
# ─── Unified interface ────────────────────────────────────────────────────────

class SimInterface:
    """
    Unified wrapper over the A7670E or SIM7600 — callers do not need to know
    which module is used, the public interface is identical.
    """

    def __init__(self, port: str, module: str):
        self.port   = port
        self.module = module   # "a7670e" or "sim7600"
        self._drv   = self._init_driver(port, module)
        logger.info("SimInterface: %s @ %s", module.upper(), port)

    def _init_driver(self, port: str, module: str):
        if module == "a7670e":
            from communication.a7670e import A7670E
            return A7670E(port=port, baudrate=BAUD)
        elif module == "sim7600":
            from communication.sim7600_legacy import SIM7600
            return SIM7600(port=port, baudrate=BAUD)
        else:
            raise ValueError(f"Unknown module: {module}")

    # ── Public API (same for both) ───────────────────────────────
    def get_gps(self, timeout: int = None, interval: float = 3.0) -> dict:
        t = timeout if timeout is not None else settings.GPS_TIMEOUT
        return self._drv.get_gps(timeout=t, interval=interval)

    def get_gps_location(self) -> "tuple | None":
        return self._drv.get_gps_location()

    def signal_quality(self) -> str:
        return self._drv.signal_quality()

    def network_registration(self) -> str:
        return self._drv.network_registration()

    def check_module(self) -> bool:
        return self._drv.check_module()

    def close(self):
        self._drv.close()

    def __repr__(self):
        return f"<SimInterface module={self.module} port={self.port}>"


class MockSimInterface:
    """Used when RUN_MODE=mock — needs no hardware at all."""
    module = "mock"
    port   = "mock"

    def get_gps(self, timeout=90, interval=3.0) -> dict:
        return {
            "fix": True, "lat": -1.265400, "lon": 116.831200,
            "altitude_m": 8.2, "speed_kmh": 0.0, "course_deg": 0.0,
            "date_utc": "30/06/2025", "time_utc": "07:00:42", "_mock": True,
        }

    def get_gps_location(self) -> tuple:
        return (-1.265400, 116.831200)

    def signal_quality(self) -> str:
        return "+CSQ: 20,0\r\nOK"

    def network_registration(self) -> str:
        return "+CREG: 0,1\r\nOK"

    def check_module(self) -> bool:
        return True

    def close(self):
        pass

    def __repr__(self):
        return "<MockSimInterface>"
