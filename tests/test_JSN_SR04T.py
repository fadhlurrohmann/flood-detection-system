import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sensors.JSN_SR04T import JSN_SR04T

def main():
    sensor = JSN_SR04T()

    try:
        while True:
            distance_m = sensor.read()
            if distance_m is None:
                print("No echo from sensor; check wiring and power supply.")
                continue

            distance_cm = distance_m * 100

            print(f"Result Read Distance: {distance_cm:.2f} cm  |  {distance_m:.2f} m")
            time.sleep(1)

    except KeyboardInterrupt:
        print("Program complete.")
    finally:
        sensor.close()

if __name__ == "__main__":
    main()
