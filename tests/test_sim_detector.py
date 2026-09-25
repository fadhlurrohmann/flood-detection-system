"""
TEST — SIM Auto-Detector (A7670E vs SIM7600)

Script this Simulates process that occurs when EFWS startup in mode hardware:
  1. Scan all port /dev/ttyUSBx
  2. Send AT + ATI to every port
  3. Kenali module from fingerprint in response ATI
  4. Save result to .sim_cache for boot next

Usage:
  python3 tests/test_sim_detector.py
  python3 tests/test_sim_detector.py --force   # force scan again, ignore cache
"""
import sys, os, json, argparse
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import settings

parser = argparse.ArgumentParser()
parser.add_argument("--force", action="store_true", help="Force scan again, ignore cache")
args = parser.parse_args()

print("=" * 60)
print("  TEST SIM Auto-Detector")
print("=" * 60)

if settings.RUN_MODE == "mock":
    print("Mode MOCK — no scan real hardware.")
    print("Inside production (RUN_MODE=hardware), detector will:")
    print("  1. Scan /dev/ttyUSB* one per one")
    print("  2. Send AT + ATI to every port")
    print("  3. A7670E/SIM7670E → fingerprint 'A7670E' in ATI → use AT+CGNSSPWR for GPS")
    print("  4. SIM7600          → fingerprint 'SIM7600' in ATI → use AT+CGPS for GPS")
    print("  5. Cache port to .sim_cache for boot next")
    print()
    print("Perintah berguna for troubleshoot in Pi:")
    print("  ls /dev/ttyUSB*")
    print("  dmesg | grep ttyUSB")
    print("  python3 -c \"import serial.tools.list_ports; print(list(serial.tools.list_ports.comports()))\"")
    sys.exit(0)

from communication.sim_detector import detect_sim, scan_ports, CACHE_FILE

# Check cache first
if CACHE_FILE.exists() and not args.force:
    print(f"Cache found: {CACHE_FILE}")
    try:
        cached = json.loads(CACHE_FILE.read_text())
        print(f"  module : {cached.get('module','?').upper()}")
        print(f"  port   : {cached.get('port','?')}")
        print()
        print("Use --force for scan again (berguna after replace hardware).")
    except Exception as e:
        print(f"  Cache rusak: {e}")
    print()

print("Starting scan port...")
result = scan_ports()

if result:
    print(f"\n✅ Module found: {result['module'].upper()} @ {result['port']}")
    if result["module"] == "a7670e":
        print("   GPS command: AT+CGNSSPWR=1 (A7670E/SIM7670E command set)")
    else:
        print("   GPS command: AT+CGPS=1 (SIM7600 command set)")
    print()
    print("Test GPS from module that detected...")
    try:
        sim = detect_sim(force_scan=args.force)
        gps = sim.get_gps(timeout=30)
        if gps.get("fix"):
            print(f"✅ GPS fix: lat={gps['lat']}, lon={gps['lon']}")
        else:
            print(f"⚠️  GPS not yet fix: {gps.get('reason')} (normal if just power-on / indoor)")
        sim.close()
    except Exception as e:
        print(f"❌ Error: {e}")
else:
    print("\n❌ No SIM module detected.")
    print("\nCek:")
    print("  1. ls /dev/ttyUSB* (make sure adapter USB detected)")
    print("  2. Module already powered on and SIM card installed")
    print("  3. User pi enter group dialout: sudo usermod -aG dialout pi")
    print("  4. Try port other: python3 tests/test_a7670e.py --port /dev/ttyUSB1")
