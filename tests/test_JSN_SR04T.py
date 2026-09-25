import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sensors.JSN_SR04T import JSN_SR04T

def main():
    sensor = JSN_SR04T()

    try:
        while True:
            jarak_m = sensor.read() 
            if jarak_m is None:
                print("None echo from sensor; periksa wiring dan power supply.")
                continue

            jarak_cm = jarak_m * 100

            print(f"Hasil Baca Jarak: {jarak_cm:.2f} cm  |  {jarak_m:.2f} m")
            time.sleep(1)

    except KeyboardInterrupt:
        print("Program complete.")
    finally:
        sensor.close()

if __name__ == "__main__":
    main()
