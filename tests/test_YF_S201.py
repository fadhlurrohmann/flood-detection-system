"""Standalone hardware test runner for the YF-S201 flow sensor."""

import importlib.util
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

module_path = os.path.join(os.path.dirname(__file__), "..", "sensors", "YF-S201.py")
module_spec = importlib.util.spec_from_file_location("yf_s201", module_path)
module = importlib.util.module_from_spec(module_spec)
module_spec.loader.exec_module(module)
YFS201 = module.YFS201

sensor = YFS201()
print(f"Listening on GPIO {sensor.GPIO_YF}... Ctrl+C to stop.\n")

try:
    while True:
        flow_rate = sensor.read_flow_rate()
        print(
            f"GPIO {sensor.GPIO_YF} | Pulses: {sensor.pulse_count} /s | "
            f"Flow: {flow_rate:.2f} L/min"
        )
except KeyboardInterrupt:
    print("\nStopped.")
finally:
    sensor.close()