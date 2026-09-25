"""
CHECK — GPS / GNSS (verifikasi data GPS BENAR-BENAR datang from physical module
A7670E/SIM7670E or SIM7600, not cache/fallback config old)

Kenapa perlu script ini:
  main.py only memakai GPS secara pasif (poll every siklus). Script ini
  secara eksplisit:
    1. Deteksi module that installed (A7670E or SIM7600) beserta port-nya.
    2. Check module correct-correct merespons AT command (not port mati/nyasar).
    3. Turn on GNSS & polling AT+CGPSINFO sampai dapat fix or timeout.
    4. Tampilkan RAW NMEA response from module (+CGPSINFO: ...) sebagai bukti
       data itu correct-correct new dibaca sekarang from GNSS engine, not
       value old/result hardcode.
    5. Cetak ringkasan PASS/FAIL, dan SEKALIGUS tulis hasilnya ke efws.log
       (logger that sama used main.py) so that ada jejak permanen.

PENTING (kenapa file ini TIDAK bernama tests/test_gps.py):
  Ditaruh di tests/hardware_checks/ with prefix "check_" (not "test_")
  so that TIDAK ikut ter-collect oleh pytest -- script ini mengakses hardware
  serial sungguhan (buka port /dev/ttyUSBx) that akan crash/hang if
  pytest trying meng-import-nya di lingkungan without modem (CI, laptop dev,
  dst). Run manual, not through pytest.

Usage:
  python3 tests/hardware_checks/check_gps.py
  python3 tests/hardware_checks/check_gps.py --timeout 120
  python3 tests/hardware_checks/check_gps.py --force        # abaikan .sim_cache, scan again port
  python3 tests/hardware_checks/check_gps.py --port /dev/ttyUSB2 --module a7670e   # paksa, skip auto-detect
"""
import sys
import os
import json
import argparse
import logging
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from config import settings

# ─── Logger: use handler that SAMA with main.py (console + efws.log) ────
# So that result check ini juga permanen tercatat di file log that sama,
# not only tampil di layar lalu hilang.
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
    parser = argparse.ArgumentParser(description="Check apakah GPS correct-correct mengambil data from A7670E/SIM7600")
    parser.add_argument("--timeout", type=int, default=settings._int("EFWS_GPS_TIMEOUT", 90),
                         help="Seconds menunggu GNSS fix (default: EFWS_GPS_TIMEOUT / 90s)")
    parser.add_argument("--force", action="store_true", help="Abaikan .sim_cache, scan again all port")
    parser.add_argument("--port", default=None, help="Paksa port tertentu (skip auto-scan), needs --module")
    parser.add_argument("--module", choices=["a7670e", "sim7600"], default=None,
                         help="Paksa module tertentu (used bersama --port)")
    args = parser.parse_args()

    header("CHECK GPS — Deteksi module & get fix real")

    if settings.RUN_MODE == "mock":
        result(WARN, "RUN_MODE=mock", "GPS akan disimulasikan (MockSimInterface), BUKAN data hardware original")
        print("  Set EFWS_RUN_MODE=hardware di .env for tes physical module sungguhan.")

    # ── 1) Deteksi / pilih module ──────────────────────────────────
    from communication.sim_detector import detect_sim, SimInterface, scan_ports

    try:
        if args.port and args.module:
            header(f"Paksa modul: {args.module.upper()} @ {args.port}")
            sim = SimInterface(port=args.port, module=args.module)
        else:
            header("Auto-detect SIM module (A7670E vs SIM7600)")
            sim = detect_sim(force_scan=args.force)
    except Exception as e:
        result(FAIL, "Deteksi module", str(e))
        logger.error("GPS CHECK FAILED total -- none SIM module detected: %s", e)
        sys.exit(1)

    is_mock = getattr(sim, "module", "") == "mock"
    result(OK if not is_mock else WARN, "Module detected", f"{sim.module.upper()} @ {sim.port}")

    # ── 2) Module correct-correct merespons AT (not port mati) ────────
    header("Check module merespons AT command")
    try:
        alive = sim.check_module()
        result(OK if alive else FAIL, "AT ping", "OK" if alive else "Does not respond")
        if not alive and not is_mock:
            logger.error("GPS CHECK: module %s @ %s Does not respond AT command.", sim.module.upper(), sim.port)
    except Exception as e:
        result(FAIL, "AT ping", str(e))

    try:
        csq = sim.signal_quality().strip()
        result(INFO, "Kualitas signal (AT+CSQ)", csq.replace("\r\n", " | "))
    except Exception as e:
        result(WARN, "Kualitas signal", f"gagal baca: {e}")

    # ── 3) Get GPS fix REAL (polling AT+CGPSINFO) ──────────────
    header(f"Minta GPS fix (timeout {args.timeout}s) -- ini akan menunggu, pastikan antena GNSS di luar/langit terbuka")
    logger.info("GPS CHECK: start polling fix from %s @ %s (timeout=%ds)",
                sim.module.upper(), sim.port, args.timeout)

    gps_result = sim.get_gps(timeout=args.timeout)

    if gps_result.get("fix"):
        result(OK, "GPS FIX diterima", f"lat={gps_result['lat']:.6f}, lon={gps_result['lon']:.6f}")
        result(INFO, "Altitude", f"{gps_result.get('altitude_m')} m")
        result(INFO, "Waktu fix (UTC)", f"{gps_result.get('date_utc')} {gps_result.get('time_utc')}")

        # Bukti directly bahwa ini data LIVE from module, not value old:
        # tampilkan raw NMEA response persis seperti that sent module.
        raw_nmea = gps_result.get("raw")
        if raw_nmea:
            result(INFO, "RAW +CGPSINFO from module", raw_nmea)
        if gps_result.get("_mock"):
            result(WARN, "PERHATIAN", "Ini data MOCK (RUN_MODE=mock) -- BUKAN from hardware GPS sungguhan.")

        logger.info(
            "GPS CHECK SUKSES: fix real from %s @ %s -> lat=%.6f lon=%.6f alt=%sm waktu=%s %s | raw=%s",
            sim.module.upper(), sim.port,
            gps_result["lat"], gps_result["lon"],
            gps_result.get("altitude_m"), gps_result.get("date_utc"), gps_result.get("time_utc"),
            raw_nmea,
        )
        exit_code = 0
    else:
        reason = gps_result.get("reason", "not diketahui")
        result(FAIL, "GPS TIDAK fix", reason)
        logger.warning(
            "GPS CHECK FAILED fix: module %s @ %s not mendapat fix dalam %ds. Reason: %s",
            sim.module.upper(), sim.port, args.timeout, reason,
        )
        print("\n  Possibly penyebab:")
        print("   - Antenna GNSS belum installed / kabelnya lepas")
        print("   - Module di dalam room / sky blocked (GNSS needs line-of-sight ke satelit)")
        print("   - Cold start pertama kali bisa needs 30-60+ seconds, coba --timeout lebih besar")
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
