"""
SIMCom A7670E / SIM7670E (LTE Cat-1 4G) controller via AT command - GPS/GNSS.

NOTE IMPORTANT regarding compatibility AT command:
  Module A7670E/SIM7670E GENERALLY kompatibel with AT command set
  SIM7600 for function modem dasar (AT, AT+CSQ, AT+CREG?, AT+CGDCONT,
  AT+CGPADDR), BUT for GNSS/GPS commands DIFFERENT:

    SIM7600E   : AT+CGPS=1 / AT+CGPS=0   (turn on/turn off GPS engine)
    A7670E/SIM7670E : AT+CGNSSPWR=1 / AT+CGNSSPWR=0  (turn on/turn off GNSS)

  While AT+CGPSINFO for reading result fix format SAME in both
  keluarga module this, therefore parser NMEA below still used unchanged.
  (Referensi: SIMCom A76XX Series AT Command Manual & GNSS Application Note)

Fitur:
  - Diagnostics modem (signal, registered network, IP)
  - GPS: get koordinat lat/lon actual from antenna GNSS module

Flow AT command GNSS:
  AT+CGNSSPWR=1   -> turn on GNSS engine (wait "+CGNSSPWR: READY!")
  AT+CGPSINFO     -> read NMEA fix (lat, lon, alt, speed, direction, time)
  AT+CGNSSPWR=0   -> turn off GNSS (optional, save power)

Requires: pip install pyserial
"""
import re
import time
import logging
try:
    import serial
except ImportError:
    serial = None
from config import settings

logger = logging.getLogger("efws.sim7600")


class SIM7600:
    """
    Name class retained 'SIM7600' for compatibility import in
    main.py - but command internal already adapted for A7670E/SIM7670E.
    """

    def __init__(self, port=None, baudrate=None):
        if serial is None:
            raise RuntimeError("pyserial is not installed - pip install pyserial")
        self.ser = serial.Serial(
            port or settings.SIM7600_AT_PORT,
            baudrate or settings.SIM7600_BAUDRATE,
            timeout=2,
        )
        self._gnss_on = False

    # ─── AT command primitif ─────────────────────────────────────
    def send_at(self, command: str, wait: float = 1.0) -> str:
        """Send AT command, return response string."""
        self.ser.reset_input_buffer()
        self.ser.write((command + "\r\n").encode())
        time.sleep(wait)
        raw = self.ser.read(self.ser.in_waiting or 1)
        return raw.decode(errors="ignore")

    # ─── Diagnostics modem ────────────────────────────────────────
    def check_module(self) -> bool:
        return "OK" in self.send_at("AT")

    def signal_quality(self) -> str:
        """AT+CSQ -> +CSQ: <rssi>,<ber>. rssi 0-31 (increasingly high increasingly strong), 99=not diketahui."""
        return self.send_at("AT+CSQ")

    def network_registration(self) -> str:
        return self.send_at("AT+CREG?")

    def apn_setup(self, apn: str = None) -> str:
        apn = apn or settings.APN
        self.send_at(f'AT+CGDCONT=1,"IP","{apn}"')
        return self.send_at("AT+CGATT=1")

    def get_ip(self) -> str:
        return self.send_at("AT+CGPADDR=1")

    # ─── GNSS / GPS (A7670E/SIM7670E command set) ─────────────────
    def gps_power_on(self) -> bool:
        """
        Turn on GNSS engine A7670E/SIM7670E. Needs 15-60 seconds for fix
        first (cold start) outside room with antenna GNSS installed.
        """
        resp = self.send_at("AT+CGNSSPWR=1", wait=2.0)
        if "OK" in resp or "READY" in resp:
            self._gnss_on = True
            logger.info("GNSS engine ON. Wait fix (cold: ~15-60 seconds).")
            return True
        logger.warning("GNSS power ON failed: %s", resp.strip())
        return False

    def gps_power_off(self) -> bool:
        """Turn off GNSS engine (save power if not needed continuously-menerus)."""
        resp = self.send_at("AT+CGNSSPWR=0", wait=1.0)
        self._gnss_on = False
        return "OK" in resp

    def _parse_cgpsinfo(self, raw: str) -> dict | None:
        """
        Parse response AT+CGPSINFO (format same for SIM7600 & A7670E/SIM7670E).

        Format NMEA:
          +CGPSINFO: <lat>,<N/S>,<lon>,<E/W>,<date>,<utc_time>,<alt>,<speed>,<course>

        Example exists fix:
          +CGPSINFO: 0114.5506,S,11649.5982,E,260625,033042.0,8.2,0.0,0.0

        Example does not yet have fix:
          +CGPSINFO: ,,,,,,,,
        """
        match = re.search(r"\+CGPSINFO:\s*([^\r\n]+)", raw)
        if not match:
            return None

        parts = [p.strip() for p in match.group(1).split(",")]
        if len(parts) < 9 or parts[0] == "":
            return None   # does not yet have fix

        try:
            def _nmea_to_dd(nmea: str, direction: str) -> float:
                """Konversi NMEA ddmm.mmmm -> decimal degrees."""
                dot = nmea.index(".")
                deg = float(nmea[:dot - 2])
                minutes = float(nmea[dot - 2:])
                dd = deg + minutes / 60.0
                if direction in ("S", "W"):
                    dd = -dd
                return round(dd, 6)

            lat  = _nmea_to_dd(parts[0], parts[1])
            lon  = _nmea_to_dd(parts[2], parts[3])
            date = parts[4]   # DDMMYY
            utc  = parts[5]   # HHMMSS.s
            alt  = float(parts[6]) if parts[6] else None
            spd  = float(parts[7]) if parts[7] else None
            crs  = float(parts[8]) if parts[8] else None

            utc_fmt = f"{utc[:2]}:{utc[2:4]}:{utc[4:]}" if len(utc) >= 6 else utc
            date_fmt = f"{date[:2]}/{date[2:4]}/20{date[4:]}" if len(date) == 6 else date

            return {
                "fix":          True,
                "lat":          lat,
                "lon":          lon,
                "altitude_m":   alt,
                "speed_kmh":    round(spd * 1.852, 2) if spd is not None else None,  # knot->km/h
                "course_deg":   crs,
                "date_utc":     date_fmt,
                "time_utc":     utc_fmt,
                "raw":          match.group(1).strip(),
            }
        except (ValueError, IndexError) as e:
            logger.debug("GPS parse error: %s | raw: %s", e, raw.strip())
            return None

    def get_gps(self, timeout: int = 90, interval: float = 3.0) -> dict:
        """
        Get koordinat GPS from A7670E/SIM7670E.
        If GNSS engine not yet ON, will powered on automatically.
        Polling AT+CGPSINFO until exists fix or timeout.

        Return dict:
          fix=True  -> {"fix": True, "lat": float, "lon": float, ...}
          fix=False -> {"fix": False, "reason": str}
        """
        if not self._gnss_on:
            if not self.gps_power_on():
                return {"fix": False, "reason": "GNSS engine failed powered on"}

        logger.info("Waiting GNSS fix (timeout %ds)...", timeout)
        elapsed = 0.0

        while elapsed < timeout:
            raw = self.send_at("AT+CGPSINFO", wait=1.0)
            result = self._parse_cgpsinfo(raw)

            if result:
                logger.info(
                    "GNSS fix! lat=%.6f, lon=%.6f, alt=%.1fm, spd=%.1fkm/h",
                    result["lat"], result["lon"],
                    result.get("altitude_m") or 0,
                    result.get("speed_kmh") or 0,
                )
                return result

            logger.debug("Does not yet have fix (%.0fs/%.0fs)...", elapsed, timeout)
            time.sleep(interval)
            elapsed += interval + 1.0

        return {
            "fix":    False,
            "reason": f"Timeout {timeout}s - ensure antenna GNSS installed and sky open",
        }

    def get_gps_location(self) -> "tuple[float, float] | None":
        """Shortcut: return (lat, lon) or None if no fix."""
        result = self.get_gps()
        if result.get("fix"):
            return result["lat"], result["lon"]
        return None

    def close(self):
        if self._gnss_on:
            self.gps_power_off()
        self.ser.close()


# ─── Mock GPS for mode testing ─────────────────────────────────
class MockSIM7600:
    """Used when RUN_MODE=mock - not needs hardware A7670E/SIM7670E."""
    _gnss_on = False

    def gps_power_on(self) -> bool:
        self._gnss_on = True
        return True

    def gps_power_off(self) -> bool:
        self._gnss_on = False
        return True

    def get_gps(self, timeout=90, interval=3.0) -> dict:
        return {
            "fix":        True,
            "lat":        -1.265400,
            "lon":        116.831200,
            "altitude_m": 8.2,
            "speed_kmh":  0.0,
            "course_deg": 0.0,
            "date_utc":   "26/06/2025",
            "time_utc":   "03:30:42",
            "_mock":      True,
        }

    def get_gps_location(self) -> tuple:
        return (-1.265400, 116.831200)

    def check_module(self) -> bool: return True
    def signal_quality(self) -> str: return "+CSQ: 20,0\r\nOK"
    def network_registration(self) -> str: return "+CREG: 0,1\r\nOK"
    def send_at(self, cmd, wait=1.0) -> str: return "OK"
    def close(self): pass


if __name__ == "__main__":
    # Test directly: python communication/sim7600.py
    import json
    modem = SIM7600()
    print("Module:", modem.check_module())
    print("Signal:", modem.signal_quality().strip())
    result = modem.get_gps(timeout=90)
    print("GPS:", json.dumps(result, indent=2))
    modem.close()
