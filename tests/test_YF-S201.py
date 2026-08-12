"""
Standalone test runner for the YF-S201 flow sensor.
Run: python3 test_yf.py
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sensors.waterflow import FlowSensor

sensor = FlowSensor()
print(f"Listening on GPIO {sensor.pin}... Ctrl+C to stop.\n")

try:
    while True:
        data = sensor.read()
        print(f"Flow: {data['flow_lpm']:.2f} L/min | Total: {data['total_liters']:.3f} L")
except KeyboardInterrupt:
    print("\nStopped.")
finally:
    sensor.close()