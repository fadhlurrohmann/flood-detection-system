"""
TEST - Submersible Pressure Sensor (water level, loop 4-20mA via burden resistor)

Check before running:
  ls /dev/spidev*  -> must show /dev/spidev0.0
  R_BURDEN 100 ohm installed in the loop and connected directly to MCP3008 CH2
  The 12-24V loop supply is on (the sensor is loop-powered, not powered by the Pi)

Checks performed:
  1. Sensor can read without exception.
  2. current_ma is in the reasonable 4-20mA range.
  3. fault_open_loop is not continuously active.
  4. depth_m is between 0 and PRESSURE_RANGE_M.

Usage: python3 tests/test_pressure.py
"""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import settings
from sensors.pressure import PressureWaterSensor

print("=" * 60)
print("  TEST - Submersible Pressure Sensor (MCP3008 CH2)")
print("=" * 60)
print(f"R_BURDEN    : {settings.PRESSURE_BURDEN_OHM} ohm")
print(f"Range mA  : {settings.PRESSURE_MIN_MA}-{settings.PRESSURE_MAX_MA}mA")
print(f"Range depth : 0-{settings.PRESSURE_RANGE_M}m  (adjust EFWS_PRESSURE_RANGE_M if differs from datasheet)\n")

try:
    sensor = PressureWaterSensor()
except Exception as e:
    print(f"[FAIL] Initialization failed: {e}")
    print("Check that ls /dev/spidev* shows /dev/spidev0.0")
    sys.exit(1)

N = 5
fault_count = 0
readings = []

print(f"Taking {N} readings at two-second intervals (Ctrl+C to stop)...\n")
try:
    for i in range(N):
        r = sensor.read()
        readings.append(r)
        if r["fault_open_loop"]:
            fault_count += 1
        flag = "  [WARNING] fault_open_loop!" if r["fault_open_loop"] else ""
        print(f"  [{i+1}] current={r['current_ma']}mA  depth={r['depth_m']}m  "
              f"pressure={r['pressure_bar']}bar{flag}")
        time.sleep(2)
except KeyboardInterrupt:
    print("\nStopped by user.")
    sys.exit(0)

print("\n" + "=" * 60)
print("  SUMMARY ")
print("=" * 60)

problems = []

ma_values = [r["current_ma"] for r in readings]
out_of_range = [ma for ma in ma_values if ma < 3.5 or ma > 21.0]
if out_of_range:
    problems.append(f"current_ma readings outside the reasonable 4-20mA range: {out_of_range}")
else:
    print(f"  [OK] all current_ma readings are reasonable ({min(ma_values)}-{max(ma_values)}mA)")

if fault_count == N:
    problems.append("fault_open_loop was active for every reading; the loop may be disconnected")
elif fault_count > 0:
    print(f"  [WARNING] fault_open_loop was active {fault_count}/{N} times; check the loop wiring")
else:
    print("  [OK] No fault_open_loop during test")

depth_values = [r["depth_m"] for r in readings]
if any(d < 0 or d > settings.PRESSURE_RANGE_M for d in depth_values):
    problems.append(f"depth_m readings outside 0-{settings.PRESSURE_RANGE_M}m")
else:
    print(f"  [OK] depth_m all in range 0-{settings.PRESSURE_RANGE_M}m ({min(depth_values)}-{max(depth_values)}m)")

print()
if problems:
    print("[FAIL] Problems found:")
    for p in problems:
        print(f"   - {p}")
    print("\nSee the 'Submersible Pressure Sensor' section of docs/Pinout.md for wiring details.")
    sys.exit(1)
else:
    print("[OK] Submersible pressure sensor read successfully.")
