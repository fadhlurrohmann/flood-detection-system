"""
CHECK — GPS / GNSS (verify that the GPS data TRULY comes from the physical
A7670E/SIM7670E or SIM7600 module, not an old cache/config fallback)

Why this script is needed:
  main.py only uses GPS passively (polled every cycle). This script
  explicitly:
    1. Detects the installed module (A7670E or SIM7600) and its port.
    2. Checks that the module really responds to AT commands (not a dead/wrong port).
    3. Turns on GNSS & polls AT+CGPSINFO until it gets a fix or times out.
    4. Shows the RAW NMEA response from the module (+CGPSINFO: ...) as proof
       that the data was just read now from the GNSS engine, not an
       old/hardcoded value.
    5. Prints a PASS/FAIL summary, and ALSO writes the result to efws.log
       (the same logger main.py uses) so there is a permanent trace.

IMPORTANT (why this file is NOT named tests/test_gps.py):
  It is placed in tests/hardware_checks/ with the "check_" prefix (not "test_")
  so it is NOT collected by pytest -- this script accesses real serial
  hardware (opens a /dev/ttyUSBx port) which would crash/hang if
  pytest tried to import it in an environment without a modem (CI, dev laptop,
  etc.). Run it manually, not through pytest.

Usage:
  python3 tests/hardware_checks/check_gps.py
  python3 tests/hardware_checks/check_gps.py --timeout 120
  python3 tests/hardware_checks/check_gps.py --force        # ignore .sim_cache, rescan the ports
  python3 tests/hardware_checks/check_gps.py --port /dev/ttyUSB2 --module a7670e   # force it, skip auto-detect
"""
import sys
import os
import json
import argparse
import logging
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from config import settings

# ─── Logger: use the SAME handlers as main.py (console + efws.log) ──────────
# So the result of this check is also permanently recorded in the same log file,
# not just shown on screen and then lost.
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
    parser = argparse.ArgumentParser(description="Check whether the GPS really takes data from the A7670E/SIM7600")
    parser.add_argument("--timeout", type=int, default=settings._int("EFWS_GPS_TIMEOUT", 90),
                         help="Seconds to wait for a GNSS fix (default: EFWS_GPS_TIMEOUT / 90s)")
    parser.add_argument("--force", action="store_true", help="Ignore .sim_cache, rescan all ports")
    parser.add_argument("--port", default=None, help="Force a specific port (skip auto-scan), needs --module")
    parser.add_argument("--module", choices=["a7670e", "sim7600"], default=None,
                         help="Force a specific module (used together with --port)")
    args = parser.parse_args()

    header("CHECK GPS — Detect the module & get a real fix")

    if settings.RUN_MODE == "mock":
        result(WARN, "RUN_MODE=mock", "GPS will be simulated (MockSimInterface), NOT real hardware data")
        print("  Set EFWS_RUN_MODE=hardware in .env to test the real physical module.")

    # ── 1) Detect / pick the module ───────────────────────────────
    from communication.sim_detector import detect_sim, SimInterface, scan_ports

    try:
        if args.port and args.module:
            header(f"Forced module: {args.module.upper()} @ {args.port}")
            sim = SimInterface(port=args.port, module=args.module)
        else:
            header("Auto-detect the SIM module (A7670E vs SIM7600)")
            sim = detect_sim(force_scan=args.force)
    except Exception as e:
        result(FAIL, "Module detection", str(e))
        logger.error("GPS CHECK TOTAL FAILURE -- no SIM module detected: %s", e)
        sys.exit(1)

    is_mock = getattr(sim, "module", "") == "mock"
    result(OK if not is_mock else WARN, "Module detected", f"{sim.module.upper()} @ {sim.port}")

    # ── 2) The module really responds to AT (not a dead port) ──────
    header("Check that the module responds to AT commands")
    try:
        alive = sim.check_module()
        result(OK if alive else FAIL, "AT ping", "OK" if alive else "NOT responding")
        if not alive and not is_mock:
            logger.error("GPS CHECK: module %s @ %s does NOT respond to AT commands.", sim.module.upper(), sim.port)
    except Exception as e:
        result(FAIL, "AT ping", str(e))

    try:
        csq = sim.signal_quality().strip()
        result(INFO, "Signal quality (AT+CSQ)", csq.replace("\r\n", " | "))
    except Exception as e:
        result(WARN, "Signal quality", f"failed to read: {e}")

    # ── 3) Get a REAL GPS fix (poll AT+CGPSINFO) ──────────────────
    header(f"Request a GPS fix (timeout {args.timeout}s) -- this will wait, make sure the GNSS antenna is outside/under an open sky")
    logger.info("GPS CHECK: starting to poll for a fix from %s @ %s (timeout=%ds)",
                sim.module.upper(), sim.port, args.timeout)

    gps_result = sim.get_gps(timeout=args.timeout)

    if gps_result.get("fix"):
        result(OK, "GPS FIX received", f"lat={gps_result['lat']:.6f}, lon={gps_result['lon']:.6f}")
        result(INFO, "Altitude", f"{gps_result.get('altitude_m')} m")
        result(INFO, "Fix time (UTC)", f"{gps_result.get('date_utc')} {gps_result.get('time_utc')}")

        # Direct proof that this is LIVE data from the module, not an old value:
        # show the raw NMEA response exactly as the module sent it.
        raw_nmea = gps_result.get("raw")
        if raw_nmea:
            result(INFO, "RAW +CGPSINFO from the module", raw_nmea)
        if gps_result.get("_mock"):
            result(WARN, "NOTE", "This is MOCK data (RUN_MODE=mock) -- NOT from real GPS hardware.")

        logger.info(
            "GPS CHECK SUCCESS: real fix from %s @ %s -> lat=%.6f lon=%.6f alt=%sm time=%s %s | raw=%s",
            sim.module.upper(), sim.port,
            gps_result["lat"], gps_result["lon"],
            gps_result.get("altitude_m"), gps_result.get("date_utc"), gps_result.get("time_utc"),
            raw_nmea,
        )
        exit_code = 0
    else:
        reason = gps_result.get("reason", "unknown")
        result(FAIL, "GPS has NO fix", reason)
        logger.warning(
            "GPS CHECK FAILED to get a fix: module %s @ %s got no fix within %ds. Reason: %s",
            sim.module.upper(), sim.port, args.timeout, reason,
        )
        print("\n  Possible causes:")
        print("   - The GNSS antenna is not attached / its cable has come loose")
        print("   - The module is indoors / the sky is blocked (GNSS needs line-of-sight to the satellites)")
        print("   - The first cold start can take 30-60+ seconds, try a larger --timeout")
        exit_code = 1

    sim.close()

    header("Summary")
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
