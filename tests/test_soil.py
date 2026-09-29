"""
TEST - Soil Moisture Probes (surface and deep)

SURFACE probe (CH0): depth 0-30 cm
DEEP probe    (CH1): depth 30-60 cm

EFWS evaluates both probes independently against their configured thresholds.

Usage: python3 tests/test_soil.py
"""
import sys, time, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sensors.soil import SoilMoistureSensor

print("=" * 60)
print("  TEST Soil Moisture (dual probe: surface + deep)")
print("=" * 60)

try:
    sensor = SoilMoistureSensor()
    print("[OK] Soil sensor initialized (CH0=surface, CH1=deep).\n")
except Exception as e:
    print(f"[FAIL] {e}"); sys.exit(1)

print("CALIBRATION STEPS for each probe:")
print("  1. Hold the probe in dry air and record raw as dry_raw")
print("  2. Submerge the probe in water and record raw as wet_raw")
print("  Update these values in SoilMoistureSensor.__init__ in sensors/soil.py\n")

print("Reading once per second (Ctrl+C to stop)...\n")
try:
    for _ in range(20):
        d = sensor.read()
        s = d["surface"]
        dp = d["deep"]
        worst = min(s["moisture_percent"], dp["moisture_percent"])
        status = "CRITICAL" if worst < 10 else "WARNING" if worst < 20 else "OK"
        print(f"  Surface: raw={s['raw']:4d}  {s['moisture_percent']:5.1f}%  |  "
              f"Deep: raw={dp['raw']:4d}  {dp['moisture_percent']:5.1f}%  |  "
              f"Worst={worst:.1f}%  {status}")
        time.sleep(1)
except KeyboardInterrupt:
    pass
