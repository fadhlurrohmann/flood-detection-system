import time
from sensors import JSN_SR04T

def main():
    sensor_jarak = JSN_SR04T()

    try:
        while True:
            jarak_cm = sensor_jarak.read()
            jarak_m = jarak_cm / 100

            print(f"Hasil Baca Jarak: {jarak_cm:.2f} cm  |  {jarak_m} m")
            time.sleep(1)

    except KeyboardInterrupt:
        print("Program selesai.")

if __name__ == "__main__":
    main()
