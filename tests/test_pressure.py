"""
TEST — Submersible Pressure Sensor (water level, loop 4-20mA via burden resistor)

Check first before run:
  ls /dev/spidev*  → must exists /dev/spidev0.0
  R_BURDEN 250Ω installed in loop, tap-nya to LLC HV-5 → LV-5 → MCP3008 CH4
  PSU loop 12-24V already active (sensor this loop-powered, NOT from Pi/buck 5V)

That checked:
  1. Sensor can read without exception.
  2. current_ma exists in range reasonable 4-20mA (outside that = signal abnormal/loop faulty).
  3. fault_open_loop not active continuously-menerus (if iya → loop possibly disconnects).
  4. depth_m enter sense (0 until PRESSURE_RANGE_M).

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
print(f"Range mA  : {settings.PRESSURE_MIN_MA}-{settings.PRESSURE_MAX_MA}mA")
print(f"Range depth : 0-{settings.PRESSURE_RANGE_M}m  (adjust EFWS_PRESSURE_RANGE_M if differs from datasheet)\n")

try:
    sensor = PressureWaterSensor()
except Exception as e:
    print(f"❌ Failed inisialisasi: {e}")
    print("Check: ls /dev/spidev* must shows /dev/spidev0.0")
    sys.exit(1)

N = 5
fault_count = 0
readings = []

print(f"Reading {N}x, every 2 seconds (Ctrl+C for stop more early)...\n")
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
    print("\nStopped by user.")
    sys.exit(0)

print("\n" + "=" * 60)
print("  RINGKASAN")
print("=" * 60)

problems = []

ma_values = [r["current_ma"] for r in readings]
out_of_range = [ma for ma in ma_values if ma < 3.5 or ma > 21.0]
if out_of_range:
    problems.append(f"Exists reading current_ma outside range reasonable 4-20mA: {out_of_range}")
else:
    print(f"  ✅ current_ma all in range reasonable ({min(ma_values)}-{max(ma_values)}mA)")

if fault_count == N:
    problems.append("fault_open_loop active in ALL reading — loop possibly disconnects/not yet connected")
elif fault_count > 0:
    print(f"  ⚠️  fault_open_loop active {fault_count}/{N}x — check connection loop if this not expected")
else:
    print("  ✅ No fault_open_loop during test")

depth_values = [r["depth_m"] for r in readings]
if any(d < 0 or d > settings.PRESSURE_RANGE_M for d in depth_values):
    problems.append(f"Exists depth_m outside range 0-{settings.PRESSURE_RANGE_M}m")
else:
    print(f"  ✅ depth_m all in range 0-{settings.PRESSURE_RANGE_M}m ({min(depth_values)}-{max(depth_values)}m)")

print()
if problems:
    print("❌ Exists that needs checked:")
    for p in problems:
        print(f"   - {p}")
    print("\nLihat docs/Pinout.md section 'Submersible Pressure Sensor' for details wiring.")
    sys.exit(1)
else:
    print("✅ Submersible pressure sensor read successfully.")
