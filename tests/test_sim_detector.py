"""
TEST — SIM Auto-Detector (A7670E vs SIM7600)

This script simulates what happens when EFWS starts up in hardware mode:
  1. Scan all /dev/ttyUSBx ports
  2. Send AT + ATI to each port
  3. Recognise the module from the fingerprint in the ATI response
  4. Save the result to .sim_cache for the next boot

Usage:
  python3 tests/test_sim_detector.py
  python3 tests/test_sim_detector.py --force   # force a rescan, ignore the cache
"""
import sys, os, json, argparse
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import settings

parser = argparse.ArgumentParser()
parser.add_argument("--force", action="store_true", help="Force a rescan, ignore the cache")
args = parser.parse_args()

print("=" * 60)
print("  TEST SIM Auto-Detector")
print("=" * 60)

if settings.RUN_MODE == "mock":
    print("MOCK mode — no real hardware scan.")
    print("In production (RUN_MODE=hardware), the detector will:")
    print("  1. Scan /dev/ttyUSB* one by one")
    print("  2. Send AT + ATI to each port")
    print("  3. A7670E/SIM7670E → 'A7670E' fingerprint in ATI → use AT+CGNSSPWR for GPS")
    print("  4. SIM7600          → 'SIM7600' fingerprint in ATI → use AT+CGPS for GPS")
    print("  5. Cache the port to .sim_cache for the next boot")
    print()
    print("Useful commands to troubleshoot on the Pi:")
    print("  ls /dev/ttyUSB*")
    print("  dmesg | grep ttyUSB")
    print("  python3 -c \"import serial.tools.list_ports; print(list(serial.tools.list_ports.comports()))\"")
    sys.exit(0)

from communication.sim_detector import detect_sim, scan_ports, CACHE_FILE

# Check the cache first
if CACHE_FILE.exists() and not args.force:
    print(f"Cache found: {CACHE_FILE}")
    try:
        cached = json.loads(CACHE_FILE.read_text())
        print(f"  module : {cached.get('module','?').upper()}")
        print(f"  port   : {cached.get('port','?')}")
        print()
        print("Use --force to rescan (useful after changing hardware).")
    except Exception as e:
        print(f"  Cache is corrupt: {e}")
    print()

print("Starting the port scan...")
result = scan_ports()

if result:
    print(f"\n✅ Module found: {result['module'].upper()} @ {result['port']}")
    if result["module"] == "a7670e":
        print("   GPS command: AT+CGNSSPWR=1 (A7670E/SIM7670E command set)")
    else:
        print("   GPS command: AT+CGPS=1 (SIM7600 command set)")
    print()
    print("Testing GPS from the detected module...")
    try:
        sim = detect_sim(force_scan=args.force)
        gps = sim.get_gps(timeout=30)
        if gps.get("fix"):
            print(f"✅ GPS fix: lat={gps['lat']}, lon={gps['lon']}")
        else:
            print(f"⚠️  GPS has no fix yet: {gps.get('reason')} (normal if just powered on / indoors)")
        sim.close()
    except Exception as e:
        print(f"❌ Error: {e}")
else:
    print("\n❌ No SIM module detected.")
    print("\nCheck:")
    print("  1. ls /dev/ttyUSB* (make sure the USB adapter is detected)")
    print("  2. The module is powered on and the SIM card is inserted")
    print("  3. User pi is in the dialout group: sudo usermod -aG dialout pi")
    print("  4. Try another port: python3 tests/test_a7670e.py --port /dev/ttyUSB1")
