"""
CHECK — GPS / GNSS (verify data GPS ACTUALLY datang from physical module
A7670E/SIM7670E or SIM7600, not cache/fallback config old)

Why needs script this:
  main.py only using GPS in a passively (poll every cycle). Script this
  in a explicit:
    1. Deteksi module that installed (A7670E or SIM7600) beserta port-nya.
    2. Check module correct-correct responds AT command (not port off/nyasar).
    3. Turn on GNSS & polling AT+CGPSINFO until got fix or timeout.
    4. Display RAW NMEA response from module (+CGPSINFO: ...) as evidence
       data that correct-correct new read now from GNSS engine, not
       value old/result hardcode.
    5. Cetak ringkasan PASS/FAIL, and SIMULTANEOUSLY tulis the result to efws.log
       (logger that same used main.py) so that exists jejak permanently.

IMPORTANT (why file this NOT named tests/test_gps.py):
  Ditaruh in tests/hardware_checks/ with prefix "check_" (not "test_")
  so that NOT ikut ter-collect by pytest -- script this accesses hardware
  serial actual (open port /dev/ttyUSBx) that will crash/hang if
  pytest trying meng-import-nya in lingkungan without modem (CI, laptop dev,
  dst). Run manual, not through pytest.

Usage:
  python3 tests/hardware_checks/check_gps.py
  python3 tests/hardware_checks/check_gps.py --timeout 120
  python3 tests/hardware_checks/check_gps.py --force        # ignore .sim_cache, scan again port
  python3 tests/hardware_checks/check_gps.py --port /dev/ttyUSB2 --module a7670e   # force, skip auto-detect
"""
import sys
import os
import json
import argparse
import logging
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from config import settings

# ─── Logger: use handler that SAME with main.py (console + efws.log) ────
# So that result check this also permanently tercatat in file log that same,
# not only tampil in layar then lost.
Path(settings.LOG_PATH).parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(settings.LOG_PATH, mode="a"),
    ],
)
logger = logging.getLogger("efws.check_gps")

OK, FAIL, WARN, INFO = "[OK]  ", "[FAIL]", "[WARN]", "[INFO]"
SEP = "-" * 64


def header(title):
    line = f"\n{SEP}\n  {title}\n{SEP}"
    print(line)
    logger.info("=== %s ===", title)


def result(status, label, value=""):
    val = f"  -> {value}" if value else ""
    print(f"  {status} {label}{val}")
    logger.info("%s %s%s", status.strip(), label, (f" -> {value}" if value else ""))


def main():
    parser = argparse.ArgumentParser(description="Check whether GPS correct-correct retrieving data from A7670E/SIM7600")
    parser.add_argument("--timeout", type=int, default=settings._int("EFWS_GPS_TIMEOUT", 90),
                         help="Seconds waiting GNSS fix (default: EFWS_GPS_TIMEOUT / 90s)")
    parser.add_argument("--force", action="store_true", help="Ignore .sim_cache, scan again all port")
    parser.add_argument("--port", default=None, help="Force port specific (skip auto-scan), needs --module")
    parser.add_argument("--module", choices=["a7670e", "sim7600"], default=None,
                         help="Force module specific (used together --port)")
    args = parser.parse_args()

    header("CHECK GPS — Deteksi module & get fix actual")

    if settings.RUN_MODE == "mock":
        result(WARN, "RUN_MODE=mock", "GPS will simulated (MockSimInterface), NOT data hardware original")
        print("  Set EFWS_RUN_MODE=hardware in .env for tes physical module actual.")

    # ── 1) Deteksi / select module ──────────────────────────────────
    from communication.sim_detector import detect_sim, SimInterface, scan_ports

    try:
        if args.port and args.module:
            header(f"Force module: {args.module.upper()} @ {args.port}")
            sim = SimInterface(port=args.port, module=args.module)
        else:
            header("Auto-detect SIM module (A7670E vs SIM7600)")
            sim = detect_sim(force_scan=args.force)
    except Exception as e:
        result(FAIL, "Deteksi module", str(e))
        logger.error("GPS CHECK FAILED total -- No SIM module detected: %s", e)
        sys.exit(1)

    is_mock = getattr(sim, "module", "") == "mock"
    result(OK if not is_mock else WARN, "Module detected", f"{sim.module.upper()} @ {sim.port}")

    # ── 2) Module correct-correct responds AT (not port off) ────────
    header("Check module responds AT command")
    try:
        alive = sim.check_module()
        result(OK if alive else FAIL, "AT ping", "OK" if alive else "Does not respond")
        if not alive and not is_mock:
            logger.error("GPS CHECK: module %s @ %s Does not respond AT command.", sim.module.upper(), sim.port)
    except Exception as e:
        result(FAIL, "AT ping", str(e))

    try:
        csq = sim.signal_quality().strip()
        result(INFO, "Quality signal (AT+CSQ)", csq.replace("\r\n", " | "))
    except Exception as e:
        result(WARN, "Quality signal", f"failed read: {e}")

    # ── 3) Get GPS fix ACTUAL (polling AT+CGPSINFO) ──────────────
    header(f"Request GPS fix (timeout {args.timeout}s) -- this will waiting, ensure antenna GNSS outside/sky open")
    logger.info("GPS CHECK: start polling fix from %s @ %s (timeout=%ds)",
                sim.module.upper(), sim.port, args.timeout)

    gps_result = sim.get_gps(timeout=args.timeout)

    if gps_result.get("fix"):
        result(OK, "GPS FIX received", f"lat={gps_result['lat']:.6f}, lon={gps_result['lon']:.6f}")
        result(INFO, "Altitude", f"{gps_result.get('altitude_m')} m")
        result(INFO, "Time fix (UTC)", f"{gps_result.get('date_utc')} {gps_result.get('time_utc')}")

        # Evidence directly bahwa this data LIVE from module, not value old:
        # display raw NMEA response exactly like that sent module.
        raw_nmea = gps_result.get("raw")
        if raw_nmea:
            result(INFO, "RAW +CGPSINFO from module", raw_nmea)
        if gps_result.get("_mock"):
            result(WARN, "ATTENTION", "This data MOCK (RUN_MODE=mock) -- NOT from hardware real GPS.")

        logger.info(
            "GPS CHECK SUCCESS: fix actual from %s @ %s -> lat=%.6f lon=%.6f alt=%sm time=%s %s | raw=%s",
            sim.module.upper(), sim.port,
            gps_result["lat"], gps_result["lon"],
            gps_result.get("altitude_m"), gps_result.get("date_utc"), gps_result.get("time_utc"),
            raw_nmea,
        )
        exit_code = 0
    else:
        reason = gps_result.get("reason", "not diketahui")
        result(FAIL, "GPS NOT fix", reason)
        logger.warning(
            "GPS CHECK FAILED fix: module %s @ %s not obtain fix inside %ds. Reason: %s",
            sim.module.upper(), sim.port, args.timeout, reason,
        )
        print("\n  Possibly penyebab:")
        print("   - Antenna GNSS not yet installed / its cable is disconnected")
        print("   - Module in inside room / sky blocked (GNSS needs line-of-sight to satelit)")
        print("   - Cold start first time can require 30-60+ seconds, try --timeout larger")
        exit_code = 1

    sim.close()

    header("Ringkasan")
    print(json.dumps({
        "module": sim.module,
        "port": sim.port,
        "fix": gps_result.get("fix", False),
        "lat": gps_result.get("lat"),
        "lon": gps_result.get("lon"),
        "mock": bool(gps_result.get("_mock", False)),
    }, indent=2))

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
