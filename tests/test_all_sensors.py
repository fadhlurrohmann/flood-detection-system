"""Read each sensor used by the current hardware configuration once."""

import importlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


TESTS = [
    ("Submersible pressure", "sensors.pressure", "PressureWaterSensor", "read"),
    ("Soil moisture (dual)", "sensors.soil", "SoilMoistureSensor", "read"),
    ("Rainfall", "sensors.rainfall", "RainfallSensor", "read"),
    ("Ultrasonic distance", "sensors.JSN_SR04T", "JSN_SR04T", "read"),
    ("Water flow", "sensors.YF-S201", "YFS201", "read_flow_rate"),
]


def main():
    print("=" * 60)
    print("  ALL-SENSOR HARDWARE TEST (one reading per sensor)")
    print("=" * 60)
    results = {}

    for name, module_name, class_name, read_method in TESTS:
        sensor = None
        print(f"\n  {name}")
        try:
            module = importlib.import_module(module_name)
            sensor = getattr(module, class_name)()
            reading = getattr(sensor, read_method)()
            print(f"  Reading: {reading}")
            results[name] = "OK"
        except Exception as error:
            print(f"  FAILED: {error}")
            results[name] = "FAILED"
        finally:
            if sensor is not None and hasattr(sensor, "close"):
                sensor.close()

    print("\n" + "=" * 60)
    print("  SUMMARY")
    print("=" * 60)
    for name, status in results.items():
        print(f"  {status:6s}  {name}")

    if "FAILED" in results.values():
        print("\nFor failed sensors:")
        print("  - SPI: ls /dev/spidev*  (pressure and soil through MCP3008)")
        print("  - I2C: i2cdetect -y 1   (rainfall sensor)")
        print("  - GPIO: verify distance and flow pins in .env")
        print("  - See docs/Pinout.md for complete wiring details")
        return 1

    print("\nAll sensors passed. The hardware is ready to run main.py.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
