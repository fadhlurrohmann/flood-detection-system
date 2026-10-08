"""
TEST — BME280 (ambient temperature / humidity / pressure, I2C)

Check before running:
  sudo raspi-config → Interface Options → I2C → Yes
  i2cdetect -y 1     → 0x76 must appear (or 0x77 if the address is different)

Usage: python3 tests/test_bme280.py
"""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sensors.bme280_sensor import BME280Sensor

print("=" * 60)
print("  TEST — BME280 (I2C)")
print("=" * 60)

try:
    sensor = BME280Sensor()
except Exception as e:
    print(f"❌ Failed to initialise: {e}")
    print("Check: i2cdetect -y 1 must show the BME280 address (0x76/0x77)")
    sys.exit(1)

print("Reading 5x, every 2 seconds (Ctrl+C to stop early)...\n")
try:
    for i in range(5):
        reading = sensor.read()
        if reading.get("error"):
            print(f"  [{i+1}] ❌ error: {reading['error']}")
        else:
            print(f"  [{i+1}] temp={reading['temperature_c']}°C  "
                  f"hum={reading['humidity_percent']}%  "
                  f"pressure={reading['pressure_hpa']}hPa")
        time.sleep(2)
    print("\n✅ The BME280 reads well.")
except KeyboardInterrupt:
    print("\nStopped by the user.")
