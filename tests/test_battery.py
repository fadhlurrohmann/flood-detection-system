"""
TEST - DC 0-25V Battery Voltage Sensor (through MCP3008 CH3)

Check first before run:
  ls /dev/spidev*  -> must show /dev/spidev0.0
  Module S pin connected to LLC HV-3 -> LV-3 -> MCP3008 CH3

Usage: python3 tests/test_battery.py
"""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sensors.battery import BatterySensor

print("=" * 60)
print("  TEST - Battery Voltage Sensor (MCP3008 CH3)")
print("=" * 60)

sensor = BatterySensor()
print("Taking five readings at two-second intervals (Ctrl+C to stop)...\n")
try:
    for i in range(5):
        reading = sensor.read()
        print(f"  [{i+1}] voltage={reading['voltage']}V  percent={reading['percent']}%")
        time.sleep(2)
    print("\n[OK] Battery sensor read successfully.")
except KeyboardInterrupt:
    print("\nStopped by user.")
