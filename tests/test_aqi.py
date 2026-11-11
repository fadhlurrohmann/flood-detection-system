"""
TEST — Air quality: SEN0460 particulate sensor + ISPU (sensors/aqi.py)

Two parts:

  A. OFFLINE checks (no hardware, run anywhere, always run):
       1. ISPU sub-index / category / overall maths at the breakpoints
       2. the rolling average forgets old values (a spike drops out of the window)
       3. the sensor-read helper decodes big-endian values and rejects/retries
          the glitch where bit 15 is set (e.g. 32769 = 0x8001), using a fake I2C bus

  B. LIVE check on the Raspberry Pi (only with --live):
       - the sensor answers on the I2C address, reports its firmware version
       - N readings succeed, values are plausible, and PM1 <= PM2.5 <= PM10
       - how many samples had to be skipped because of the bit-15 glitch

Before --live:
  sudo raspi-config → Interface Options → I2C → Yes
  i2cdetect -y 1     → 19 must appear
  pip install smbus2

Usage:
  python3 tests/test_aqi.py                       # offline checks only
  python3 tests/test_aqi.py --live                # + read the real sensor
  python3 tests/test_aqi.py --live --count 20 --interval 2 --warmup 30
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sensors import aqi


failures = []
checks = 0


def check(condition, label, detail=""):
    """Record one assertion and print its result."""
    global checks
    checks += 1
    if condition:
        print(f"  ✅ {label}")
    else:
        print(f"  ❌ {label}" + (f"  ({detail})" if detail else ""))
        failures.append(label)


# ─── A1. ISPU maths ──────────────────────────────────────────────
def test_ispu():
    print("\n[A1] ISPU maths")
    check(aqi.sub_index(0, aqi.PM25_KNOTS) == 0, "0 ug/m3 -> sub-index 0")
    check(aqi.sub_index(15.5, aqi.PM25_KNOTS) == 50, "PM2.5 15.5 -> 50 (top of Baik)")
    check(aqi.sub_index(55.4, aqi.PM25_KNOTS) == 100, "PM2.5 55.4 -> 100")
    check(aqi.sub_index(150.4, aqi.PM25_KNOTS) == 200, "PM2.5 150.4 -> 200")
    check(aqi.sub_index(50, aqi.PM10_KNOTS) == 50, "PM10 50 -> 50")
    check(aqi.sub_index(150, aqi.PM10_KNOTS) == 100, "PM10 150 -> 100")
    check(aqi.sub_index(35.45, aqi.PM25_KNOTS) == 75, "PM2.5 midway in a band interpolates linearly (75)")
    check(aqi.sub_index(600, aqi.PM25_KNOTS) == 500, "beyond the scale is capped at 500")
    check(aqi.sub_index(None, aqi.PM25_KNOTS) == 0, "None -> 0 (missing data is not an alarm)")

    for value, expected in [(0, "Baik"), (50, "Baik"), (51, "Sedang"), (100, "Sedang"),
                            (101, "Tidak Sehat"), (200, "Tidak Sehat"),
                            (201, "Sangat Tidak Sehat"), (300, "Sangat Tidak Sehat"),
                            (301, "Berbahaya"), (500, "Berbahaya")]:
        check(aqi.category(value).startswith(expected), f"category({value}) is {expected}", aqi.category(value))

    value, cat, critical = aqi.ispu(35.45, 200)
    check(value == 125 and cat.startswith("Tidak Sehat") and critical == "PM10",
          "ispu(35.45, 200) = 125, Tidak Sehat, critical PM10", f"got {(value, cat, critical)}")
    value, cat, critical = aqi.ispu(100, 20)
    check(critical == "PM2.5" and value == aqi.sub_index(100, aqi.PM25_KNOTS),
          "overall ISPU is the worst sub-index (PM2.5 dominates here)")


# ─── A2. rolling average ─────────────────────────────────────────
def test_window_mean():
    print("\n[A2] Rolling average")
    w = aqi.WindowMean(window_s=100)
    check(w.mean() is None, "empty average is None")
    w.add(1000, now=0)                       # a one-off spike
    for t in range(1, 6):
        w.add(10, now=t)
    check(w.mean() > 100, "the spike is in the average at first", f"mean={w.mean():.1f}")
    for t in range(6, 111):
        w.add(10, now=t)
    check(abs(w.mean() - 10) < 1e-9, "after the window passes, the spike is gone", f"mean={w.mean():.3f}")

    w2 = aqi.WindowMean(window_s=100)
    check(abs(w2.coverage(now=w2.started + 50) - 0.5) < 1e-9, "coverage is 50% halfway through the window")
    check(w2.coverage(now=w2.started + 500) == 1.0, "coverage is capped at 100%")


# ─── A3. sensor read helper, with a fake I2C bus ─────────────────
class FakeBus:
    """Returns scripted 2-byte values per register; the last one repeats forever."""

    def __init__(self, script):
        self.script = {reg: list(values) for reg, values in script.items()}
        self.reads = 0

    def read_i2c_block_data(self, address, reg, length):
        self.reads += 1
        values = self.script[reg]
        value = values.pop(0) if len(values) > 1 else values[0]
        return [(value >> 8) & 0xFF, value & 0xFF][:length]


def test_read_pm():
    print("\n[A3] read_pm with a fake bus")
    PM1, PM25, PM10 = aqi.REG_ATM["pm1"], aqi.REG_ATM["pm25"], aqi.REG_ATM["pm10"]

    bus = FakeBus({PM1: [8], PM25: [0x012C], PM10: [0x0190]})
    result = aqi.read_pm(bus, 0x19)
    check(result == {"pm1": 8, "pm25": 300, "pm10": 400},
          "values are decoded big-endian (0x012C = 300)", str(result))

    # the real glitch: first read has bit 15 set, the re-read is clean
    bus = FakeBus({PM1: [0x8000, 0x0000], PM25: [0x8001, 0x0001], PM10: [0x8001, 0x0002]})
    result = aqi.read_pm(bus, 0x19)
    check(result == {"pm1": 0, "pm25": 1, "pm10": 2},
          "a value with bit 15 set is re-read, not used (32769 -> 1)", str(result))
    check(all(v < 0x8000 for v in result.values()), "no invalid value reaches the caller")

    # never clears -> must raise, so the caller can skip the sample
    bus = FakeBus({PM1: [0x8000], PM25: [0x8001], PM10: [0x8002]})
    try:
        aqi.read_pm(bus, 0x19, retries=2)
        check(False, "a stuck invalid value raises ValueError")
    except ValueError:
        check(True, "a stuck invalid value raises ValueError (sample is skipped)")


# ─── B. live sensor ──────────────────────────────────────────────
def test_live(args):
    print("\n[B] LIVE sensor")
    if aqi.SMBus is None:
        check(False, "smbus2 is installed", "pip install smbus2, and run this on the Pi")
        return
    address = int(args.addr, 0)
    try:
        bus = aqi.SMBus(aqi.BUS)
        version = aqi.read_reg(bus, address, aqi.REG_VERSION, 1)[0]
    except Exception as e:
        check(False, f"sensor answers at 0x{address:02X}", f"{type(e).__name__}: {e}")
        print("     Check i2cdetect -y 1 (19 must appear), the SDA/SCL wiring and the power.")
        return
    check(True, f"sensor answers at 0x{address:02X}, firmware version {version}")

    if args.warmup > 0:
        print(f"  Warming up {args.warmup:.0f}s (Ctrl+C to skip)...")
        try:
            time.sleep(args.warmup)
        except KeyboardInterrupt:
            pass

    readings, skipped = [], 0
    print("   PM1  PM2.5  PM10")
    try:
        for i in range(args.count):
            try:
                pm = aqi.read_pm(bus, address)
            except (OSError, ValueError) as e:
                skipped += 1
                print(f"   skipped: {e}")
            else:
                readings.append(pm)
                print(f"  {pm['pm1']:4d}  {pm['pm25']:5d}  {pm['pm10']:4d}")
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("  Stopped early.")
    finally:
        bus.close()

    check(len(readings) > 0, "at least one valid reading", f"{skipped} skipped")
    if not readings:
        return
    check(all(0 <= v <= 1000 for r in readings for v in r.values()),
          "all values are within 0-1000 ug/m3 (the sensor's maximum range)")
    bad_order = sum(1 for r in readings if not r["pm1"] <= r["pm25"] <= r["pm10"])
    check(bad_order <= max(1, len(readings) // 5),
          "PM1 <= PM2.5 <= PM10 holds (size bins are cumulative)", f"{bad_order} of {len(readings)} violated")
    check(skipped <= len(readings), "skipped samples (bit-15 glitch) are not the majority",
          f"{skipped} skipped vs {len(readings)} valid")
    last = readings[-1]
    value, cat, critical = aqi.ispu(last["pm25"], last["pm10"])
    print(f"  Last reading -> instantaneous ISPU {value} ({cat}, critical {critical})"
          "  [the real index uses 24 h averages]")


def run_safely(fn, *fn_args):
    try:
        fn(*fn_args)
    except Exception as e:
        check(False, f"{fn.__name__} ran without crashing", f"{type(e).__name__}: {e}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--live", action="store_true", help="also read the real sensor (on the Pi)")
    p.add_argument("--addr", default="0x19")
    p.add_argument("--count", type=int, default=10)
    p.add_argument("--interval", type=float, default=2.0)
    p.add_argument("--warmup", type=float, default=10.0)
    args = p.parse_args()

    print("=" * 60)
    print("  TEST — Air quality (SEN0460 + ISPU)")
    print("=" * 60)

    for fn in (test_ispu, test_window_mean, test_read_pm):
        run_safely(fn)
    if args.live:
        run_safely(test_live, args)
    else:
        print("\n[B] LIVE sensor: skipped (add --live on the Pi to read the real sensor)")

    print("\n" + "=" * 60)
    if failures:
        print(f"  ❌ {len(failures)} of {checks} checks FAILED")
        for f in failures:
            print(f"   - {f}")
        sys.exit(1)
    print(f"  ✅ All {checks} checks passed.")


if __name__ == "__main__":
    main()
