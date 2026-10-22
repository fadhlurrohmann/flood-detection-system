# Flood Early Warning System

Raspberry Pi runtime for the current five sensors. All changes on this branch are local until reviewed.

| Sensor | Driver | Default interface |
|---|---|---|
| Water flow, YF-S201 | `sensors/YF_S201.py` | BCM16, pulse counting |
| Ultrasonic distance, JSN-SR04T | `sensors/JSN_SR04T.py` | TRIG BCM22, ECHO BCM18 |
| Submersible water pressure, 4–20 mA | `sensors/pressure.py` | MCP3008 CH0, 100 ohm burden |
| Battery voltage, divider module | `sensors/battery.py` | MCP3008 CH3 |
| Rainfall, DFRobot SEN0575 | `sensors/rainfall.py` | I2C bus 1, address 0x1D |

Soil is removed. BME280 is planned for later; its existing driver is retained but is not imported by `main.py` or required for installation. Wind, flame, and a separate buzzer are not part of the current runtime. GPS comes from the cellular modem; the relay/siren is an output rather than another sensor.

`main.py` reads and logs every cycle, evaluates high water and the last hour's rainfall, and sounds the siren after the configured number of consecutive dangerous readings. A safe reading resets the streak and silences the siren. An emergency queues an upload immediately; normal operation queues the first reading and then follows the routine reporting interval. Flow and battery voltage are monitored and reported; they do not independently trigger the flood siren.

GPS, uploads, and retention use background workers. SQLite stores each reading and the complete upload bundle before transmission. Pending uploads survive process restarts and are retried in order; missing sensors produce null values and logged errors. Old databases are upgraded without deleting historical readings.

The default water limit (0.5 m), hourly rain limit (30 mm), three-reading confirmation, pressure range, and battery percentage scale are examples. Set them for the installation before relying on alarms. The default 180-second sample interval can take approximately nine minutes to confirm a newly developing event. Battery percentage is a linear voltage estimate, not a measured state of charge.

Ultrasonic distance is always reported. To use it for a depth alarm or as a fallback when pressure fails, measure and set `EFWS_ULTRASONIC_MOUNT_HEIGHT_M` above the same depth zero datum. Without that calibration, only pressure supplies water depth. Flow totals reset when the program restarts.

See [deployment](docs/Deployment.md), [current wiring](docs/Pinout.md), and [runtime behavior/API fields](docs/Architecture.md).

Run on the Pi from the repository root after configuring `.env`:

```bash
source venv/bin/activate
python3 tests/test_all_sensors.py
EFWS_RUN_MODE=hardware python3 main.py
```

Run the hardware-free regression suite (only requests and python-dotenv are needed):

```bash
python3 -m unittest discover -s tests -p test_runtime.py -v
```
