"""
TEST — DC 0-25V Voltage Sensor Module (battery, via MCP3008 CH3)

Check before running:
  ls /dev/spidev*  → /dev/spidev0.0 must exist
  The module's S pin is connected DIRECTLY to MCP3008 CH3
  The module's GND (output side, − pin) is connected to the Pi / MCP3008 GND (common ground)

Each line shows 50 fast samples: raw min/median/max, the voltage at the
MCP3008 pin (V_pin), and the computed battery voltage. At the end there is an
automatic diagnosis if the reading is unstable.

Usage: python3 tests/test_battery.py
"""
import sys, os, time, statistics
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import settings
from sensors.battery import BatterySensor

BURST = 50

print("=" * 60)
print(f"  TEST — Battery Voltage Sensor (MCP3008 CH{settings.ADC_CHANNEL_BATTERY})")
print("=" * 60)

sensor = BatterySensor()
print(f"VREF={sensor.vref}V  divider_ratio={sensor.ratio}  "
      f"(V_battery = raw/1023 × {sensor.vref} × {sensor.ratio})")
print("Reading 5x, every 2 seconds (Ctrl+C to stop early)...\n")

all_samples = []
try:
    for i in range(5):
        samples = [sensor.adc.read_raw(sensor.channel) for _ in range(BURST)]
        all_samples += samples
        med   = statistics.median(samples)
        v_pin = med / 1023 * sensor.vref
        v_bat = sensor.raw_to_voltage(int(med))
        print(f"  [{i+1}] raw min/med/max = {min(samples):4d}/{int(med):4d}/{max(samples):4d}"
              f"  V_pin={v_pin:.3f}V  voltage={v_bat}V  percent={sensor.voltage_to_percent(v_bat)}%")
        time.sleep(2)
except KeyboardInterrupt:
    print("\nStopped by the user.")

if not all_samples:
    sys.exit(0)

spread = max(all_samples) - min(all_samples)
v_pin  = statistics.median(all_samples) / 1023 * sensor.vref
print()
if spread > 30 or v_pin < 0.3:
    print(f"❌ The reading is UNSTABLE (raw spread {spread}, median V_pin {v_pin:.2f}V).")
    print("   The CH3 input is 'floating' — the MCP3008 does not see a clear voltage. Check:")
    print("   1. Is the module's GND (− pin on the output side) connected to the Pi GND / MCP3008 pin 14 (AGND)?")
    print("   2. Is the S wire really on MCP3008 pin 4 (= CH3; pin 1 is next to the dot/notch)?")
    print("   3. Multimeter: MCP3008 pin 4 relative to pin 14 should be ≈ V_battery / 5 (e.g. 2.65V).")
    print("   4. ADC test: jumper CH3 to 3.3V → raw ≈ 1023; jumper CH3 to GND → raw ≈ 0.")
    print("      If this is random too → the problem is in the MCP3008 wiring (VDD/VREF/AGND/DGND/SPI).")
elif v_pin > 3.2:
    print(f"❌ V_pin {v_pin:.2f}V is pinned at ~3.3V — CH3 is being pulled to 3.3V by another connection.")
    print("   Make sure MCP3008 pin 4 is connected ONLY to the module's S pin (measure pin 4 vs pin 14 ≈ 2.65V).")
else:
    print(f"✅ Stable (raw spread {spread}). Compare the voltage above with a multimeter on the")
    print("   battery terminals; if it differs, set EFWS_BATTERY_DIVIDER_RATIO = V_battery / V_pin_S.")
