"""
SIM Auto-Detector — detecting automatically whether node this using
module A7670E/SIM7670E (LTE Cat-1) or SIM7600 (LTE Cat-4/3G).

Methods kerja:
  1. Scan all port /dev/ttyUSBx that available.
  2. Send AT command to every port; if exists that responds, check identitas
     module through ATI (Product Identification Information).
  3. A7670E/SIM7670E → instantiasi class A7670E (command GNSS: AT+CGNSSPWR)
  4. SIM7600           → instantiasi class SIM7600 (command GNSS: AT+CGPS)
  5. Result deteksi stored in .sim_cache (file text) so boot next
     directly to port that correct without scan again.

Why two class separate (not one unified)?
  AT command for GNSS different between A7670E and SIM7600, and
  mixing both inside one class will sacrificing clarity code.
  Auto-detector this become jembatan — callers in main.py not needs tahu
  module which that used, because interface public interface is same.

Usage:
  from communication.sim_detector import detect_sim, SimInterface
  sim = detect_sim()              # auto-detect when startup
  coords = sim.get_gps()          # unified API, terlepas from physical module
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


# ─── ATI fingerprint → module ─────────────────────────────────────────────────
# Word key that appears in response ATI for each module.
# Add variant other if exists module SIMCom other in project this.
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
    Open port, send AT, send ATI.
    Return: "a7670e", "sim7600", or None (not recognized / does not respond).
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

        # Responds AT but ATI not cocok fingerprint — possibly module SIMCom other
        logger.warning("Port %s responds AT but not recognized from ATI: %s",
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
    Scan all kandidat port serial, return dict {port, module} when found,
    or None if none responds.
    """
    # Combine with result glob so that got port that none in SCAN_PORTS
    candidates = list(dict.fromkeys(
        SCAN_PORTS + sorted(glob.glob("/dev/ttyUSB*"))
    ))

    logger.info("🔍 Scanning %d port kandidat for SIM module...", len(candidates))
    for port in candidates:
        if not os.path.exists(port):
            continue
        logger.debug("  Trying %s ...", port)
        module = _identify_port(port)
        if module:
            logger.info("  ✅ Module %s found in %s", module.upper(), port)
            return {"port": port, "module": module}

    logger.warning("❌ No SIM module that detected in port anywhere.")
    return None


def _load_cache() -> "dict | None":
    try:
        data = json.loads(CACHE_FILE.read_text())
        # Validasi port still exists (can changes after reboot)
        if os.path.exists(data.get("port", "")):
            logger.info("📋 SIM cache: port=%s module=%s", data["port"], data["module"])
            return data
        logger.info("Cache stale (port %s is unavailable), scan again...", data.get("port"))
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
        logger.info("Mode MOCK — use MockSimInterface.")
        return MockSimInterface()

    info = None if force_scan else _load_cache()

    # ==========================
    # VALIDASI CACHE
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
                "Cache not valid (AT does not respond), scan again..."
            )

        except Exception as e:

            logger.warning(
                "Cache failed (%s), scan again...",
                e
            )

        info = None

    # ==========================
    # SCAN AGAIN
    # ==========================

    if info is None:

        info = scan_ports()

        if info:
            _save_cache(info)

        else:
            raise RuntimeError(
                "No SIM module that detected."
            )

    return SimInterface(
        port=info["port"],
        module=info["module"],
    )
# ─── Unified interface ────────────────────────────────────────────────────────

class SimInterface:
    """
    Wrapper unified above A7670E or SIM7600 — callers not needs tahu
    module which that used, interface public interface is identical.
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
            raise ValueError(f"Module not recognized: {module}")

    # ── Public API (same for both) ─────────────────────────
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
    """Used when RUN_MODE=mock — not needs hardware anything."""
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
