#!/usr/bin/env python3
"""
SEN0460 -> ISPU (Indonesia) on a Raspberry Pi. Standalone: needs only smbus2.

Method (PermenLHK P.14/2020, as I remember it -- VERIFY the breakpoint table):
  1. PM2.5 and PM10 are averaged over 24 hours.
  2. Each average becomes a sub-index by linear interpolation between breakpoints.
  3. ISPU = the highest sub-index; the pollutant behind it is the "critical parameter".
PM1.0 is shown but has no ISPU breakpoints.

The average lives in memory only: restarting the script restarts it.

pinout: D > SDA1 (pin3)
        C > SCL1 (pin5)  
        - > GND (pin6) 
        + > 3v3 (pin1)        

Usage (on the Pi):
  python3 sensors/aqi.py                  # real 24 h window
  python3 sensors/aqi.py --window 120     # 2-minute window, to watch it react while testing
  python3 sensors/aqi.py --wake           # also send the sensor's "wake" command first
Automated checks: python3 tests/test_aqi.py   (add --live to also read the real sensor)
"""
import argparse
import sys
import time
from collections import deque

try:
    from smbus2 import SMBus, i2c_msg
except ImportError:          # not on a Pi / smbus2 not installed: ispu() and WindowMean still import
    SMBus = i2c_msg = None

BUS = 1
REG_POWER = 0x01                                       # write 0x02 = wake, 0x01 = low power
REG_VERSION = 0x1D
REG_ATM = {"pm1": 0x0B, "pm25": 0x0D, "pm10": 0x0F}    # atmosphere values (use these)

# (concentration ug/m3, ISPU value) knots, linearly interpolated between neighbours
PM25_KNOTS = [(0, 0), (15.5, 50), (55.4, 100), (150.4, 200), (250.4, 300), (500, 500)]
PM10_KNOTS = [(0, 0), (50, 50),   (150, 100),  (350, 200),   (420, 300),   (500, 500)]


# ---------------- sensor ----------------
def read_reg(bus, address, reg, length, retries=5):
    """Try the combined read first (DFRobot's way), then write-stop-read."""
    last = None
    for _ in range(retries):
        try:
            return bus.read_i2c_block_data(address, reg, length)
        except OSError as e:
            last = e
        try:
            bus.i2c_rdwr(i2c_msg.write(address, [reg]))
            time.sleep(0.01)
            msg = i2c_msg.read(address, length)
            bus.i2c_rdwr(msg)
            return list(msg)
        except OSError as e:
            last = e
        time.sleep(0.05)
    raise last


def read_pm(bus, address, retries=5):
    """A raw value with bit 15 set (e.g. 32769 = 0x8001) is invalid: re-read it,
    and raise ValueError if it never clears."""
    out = {}
    for name, reg in REG_ATM.items():
        value = 0
        for _ in range(retries):
            high, low = read_reg(bus, address, reg, 2)
            value = (high << 8) | low
            if not value & 0x8000:
                out[name] = value
                break
            time.sleep(0.1)
        else:
            raise ValueError(f"{name} stayed invalid (raw 0x{value:04X})")
    return out


# ---------------- ISPU ----------------
def sub_index(c, knots):
    if c is None or c <= 0:
        return 0
    for (x_lo, i_lo), (x_hi, i_hi) in zip(knots, knots[1:]):
        if c <= x_hi:
            return round(i_lo + (i_hi - i_lo) * (c - x_lo) / (x_hi - x_lo))
    return 500


def category(v):
    if v <= 50:  return "Baik (Good)"
    if v <= 100: return "Sedang (Moderate)"
    if v <= 200: return "Tidak Sehat (Unhealthy)"
    if v <= 300: return "Sangat Tidak Sehat (Very Unhealthy)"
    return "Berbahaya (ur fucked. get inside)"


def ispu(pm25_avg, pm10_avg):
    s25 = sub_index(pm25_avg, PM25_KNOTS)
    s10 = sub_index(pm10_avg, PM10_KNOTS)
    value = max(s25, s10)
    critical = "PM2.5" if s25 >= s10 else "PM10"
    return value, category(value), critical


# ---------------- rolling average ----------------
class WindowMean:
    """Mean over the last `window_s` seconds, stored as ~1440 bucket averages."""

    def __init__(self, window_s):
        self.window_s = window_s
        self.bucket_s = max(1.0, window_s / 1440)
        self.buckets = deque()                  # (bucket start time, bucket mean)
        self.cur_t, self.cur_sum, self.cur_n = None, 0.0, 0
        self.started = time.time()

    def add(self, value, now=None):
        now = time.time() if now is None else now
        if self.cur_t is None:
            self.cur_t = now
        if now - self.cur_t >= self.bucket_s:
            self.buckets.append((self.cur_t, self.cur_sum / self.cur_n))
            self.cur_t, self.cur_sum, self.cur_n = now, 0.0, 0
        self.cur_sum += value
        self.cur_n += 1
        while self.buckets and now - self.buckets[0][0] > self.window_s:
            self.buckets.popleft()

    def mean(self):
        vals = [m for _, m in self.buckets]
        if self.cur_n:
            vals.append(self.cur_sum / self.cur_n)
        return sum(vals) / len(vals) if vals else None

    def coverage(self, now=None):
        now = time.time() if now is None else now
        return min(1.0, (now - self.started) / self.window_s)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--addr", default="0x19")
    p.add_argument("--interval", type=float, default=2.0, help="seconds between readings")
    p.add_argument("--window", type=float, default=24 * 3600, help="averaging window in seconds")
    p.add_argument("--warmup", type=float, default=30.0)
    p.add_argument("--wake", action="store_true", help="send the sensor's wake command first")
    args = p.parse_args()
    address = int(args.addr, 0)

    if SMBus is None:
        print("smbus2 is not installed - pip install smbus2 (and run this on the Raspberry Pi)")
        sys.exit(1)

    try:
        bus = SMBus(BUS)
        version = read_reg(bus, address, REG_VERSION, 1)[0]
    except Exception as e:
        print(f"No answer at 0x{address:02X}: {type(e).__name__}: {e}")
        sys.exit(1)
    print(f"Sensor found at 0x{address:02X}, firmware {version}")
    print(f"Averaging window: {args.window / 3600:.2f} h   (use --window 120 to watch it react)")

    if args.wake:
        bus.write_i2c_block_data(address, REG_POWER, [0x02])
        print("Wake command sent.")

    if args.warmup > 0:
        print(f"Warming up {args.warmup:.0f}s (Ctrl+C to skip)...")
        try:
            time.sleep(args.warmup)
        except KeyboardInterrupt:
            pass

    avg25, avg10 = WindowMean(args.window), WindowMean(args.window)
    skipped = 0
    print("\ntime      PM1  PM2.5  PM10 | avg2.5  avg10 | ISPU  category            critical  window")
    try:
        while True:
            try:
                pm = read_pm(bus, address)
            except (OSError, ValueError) as e:
                skipped += 1
                print(f"{time.strftime('%H:%M:%S')}  skipped sample #{skipped}: {e}")
                time.sleep(args.interval)
                continue

            avg25.add(pm["pm25"])
            avg10.add(pm["pm10"])
            a25, a10 = avg25.mean(), avg10.mean()
            value, cat, critical = ispu(a25, a10)
            cov = avg25.coverage()
            tag = "provisional" if cov < 1.0 else "full"
            print(f"{time.strftime('%H:%M:%S')}  {pm['pm1']:3d}  {pm['pm25']:5d}  {pm['pm10']:4d} |"
                  f" {a25:6.1f} {a10:6.1f} | {value:4d}  {cat:<19} {critical:<8}  {cov*100:3.0f}% {tag}")
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        bus.close()


if __name__ == "__main__":
    main()