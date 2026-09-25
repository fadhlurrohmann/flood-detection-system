"""
TEST — Module Sensor Voltage DC 0-25V (battery, through MCP3008 CH5)

Check first before run:
  ls /dev/spidev*  → must exists /dev/spidev0.0
  Pin S module connected to LLC HV-6 → LV-6 → MCP3008 CH5

Usage: python3 tests/test_battery.py
"""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sensors.battery import BatterySensor

print("=" * 60)
print("  TEST — Battery Voltage Sensor (MCP3008 CH5)")
print("=" * 60)

sensor = BatterySensor()
print("Reading 5x, every 2 seconds (Ctrl+C for stop more early)...\n")
try:
    for i in range(5):
        reading = sensor.read()
        print(f"  [{i+1}] voltage={reading['voltage']}V  percent={reading['percent']}%")
        time.sleep(2)
    print("\n✅ Battery sensor read successfully.")
except KeyboardInterrupt:
    print("\nStopped by user.")
