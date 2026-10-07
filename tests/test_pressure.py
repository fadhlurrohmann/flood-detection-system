"""
TEST — Submersible Pressure Sensor (water level, 4-20mA loop via burden resistor)

Check before running:
  ls /dev/spidev*  → /dev/spidev0.0 must exist
  R_BURDEN 250Ω installed in the loop, its tap going to LLC HV-5 → LV-5 → MCP3008 CH4
  The 12-24V loop PSU is on (this sensor is loop-powered, NOT from the Pi/5V buck)

What is checked:
  1. The sensor can be read without an exception.
  2. current_ma is in the reasonable 4-20mA range (outside that = a strange signal/loop problem).
  3. fault_open_loop is not on all the time (if it is → the loop is probably broken).
  4. depth_m is sensible (0 to PRESSURE_RANGE_M).

Usage: python3 tests/test_pressure.py
"""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import settings
from sensors.pressure import PressureWaterSensor

print("=" * 60)
print("  TEST — Submersible Pressure Sensor (MCP3008 CH4)")
print("=" * 60)
print(f"R_BURDEN    : {settings.PRESSURE_BURDEN_OHM}Ω")
print(f"mA range    : {settings.PRESSURE_MIN_MA}-{settings.PRESSURE_MAX_MA}mA")
print(f"Depth range : 0-{settings.PRESSURE_RANGE_M}m  (adjust EFWS_PRESSURE_RANGE_M if the datasheet differs)\n")

try:
    sensor = PressureWaterSensor()
except Exception as e:
    print(f"❌ Failed to initialise: {e}")
    print("Check: ls /dev/spidev* must show /dev/spidev0.0")
    sys.exit(1)

N = 5
fault_count = 0
readings = []

print(f"Reading {N}x, every 2 seconds (Ctrl+C to stop early)...\n")
try:
    for i in range(N):
        r = sensor.read()
        readings.append(r)
        if r["fault_open_loop"]:
            fault_count += 1
        flag = "  ⚠️ fault_open_loop!" if r["fault_open_loop"] else ""
        print(f"  [{i+1}] current={r['current_ma']}mA  depth={r['depth_m']}m  "
              f"pressure={r['pressure_bar']}bar{flag}")
        time.sleep(2)
except KeyboardInterrupt:
    print("\nStopped by the user.")
    sys.exit(0)

print("\n" + "=" * 60)
print("  SUMMARY")
print("=" * 60)

problems = []

ma_values = [r["current_ma"] for r in readings]
out_of_range = [ma for ma in ma_values if ma < 3.5 or ma > 21.0]
if out_of_range:
    problems.append(f"Some current_ma readings are outside the reasonable 4-20mA range: {out_of_range}")
else:
    print(f"  ✅ current_ma is all in the reasonable range ({min(ma_values)}-{max(ma_values)}mA)")

if fault_count == N:
    problems.append("fault_open_loop is on in ALL readings — the loop is probably broken/not connected")
elif fault_count > 0:
    print(f"  ⚠️  fault_open_loop was on {fault_count}/{N}x — check the loop connection if this is not expected")
else:
    print("  ✅ No fault_open_loop during the test")

depth_values = [r["depth_m"] for r in readings]
if any(d < 0 or d > settings.PRESSURE_RANGE_M for d in depth_values):
    problems.append(f"Some depth_m values are outside the range 0-{settings.PRESSURE_RANGE_M}m")
else:
    print(f"  ✅ depth_m is all in the range 0-{settings.PRESSURE_RANGE_M}m ({min(depth_values)}-{max(depth_values)}m)")

print()
if problems:
    print("❌ Some things need checking:")
    for p in problems:
        print(f"   - {p}")
    print("\nSee the 'Submersible Pressure Sensor' section of docs/Pinout.md for the wiring details.")
    sys.exit(1)
else:
    print("✅ The submersible pressure sensor reads well.")
