# Flood Early Warning System

Raspberry Pi monitoring runtime with nine sensor drivers and main's telemetry contract, extended with particulate/AQI readings.

| Sensor | Driver | Default interface |
|---|---|---|
| Water flow, YF-S201 | `sensors/YF_S201.py` | BCM16, pulse counting |
| Ultrasonic distance, JSN-SR04T | `sensors/JSN_SR04T.py` | TRIG BCM22, ECHO BCM18 |
| Submersible water pressure, 4–20 mA | `sensors/pressure.py` | MCP3008 CH0, 100 ohm burden |
| Battery voltage, divider module | `sensors/battery.py` | MCP3008 CH3 |
| Rainfall, DFRobot SEN0575 | `sensors/rainfall.py` | I2C bus 1, address 0x1D |
| Temperature, humidity, ambient pressure, BME280 | `sensors/bme280_sensor.py` | I2C bus 1, address 0x76 |
| Wind speed, Modbus anemometer | `sensors/wind_speed.py` | Configurable RS485 serial port |
| Wind direction | `sensors/wind_direction.py` | Configurable UART, default /dev/serial0 |
| Particulates and ISPU/AQI, SEN0460 | `sensors/aqi.py` | I2C bus 1, address 0x19 |

Soil, flame, and a separate buzzer are not loaded. GPS comes from the cellular modem; the relay/siren is an output. Drivers that cannot initialize report null measurements and errors while the remaining sensors continue.

`main.py` reads and logs every cycle, evaluates configured thresholds, and sounds the siren after consecutive dangerous readings. A normal reading resets the streak and silences the siren. Emergency reports queue immediately; normal operation reports initially and then at the routine interval. Local alarms do not wait for GPS or HTTP.

GPS, uploads, and retention use background workers. SQLite stores each reading and the complete upload bundle before transmission. Pending uploads survive process restarts and are retried in order; missing sensors produce null values and logged errors. Old databases are upgraded without deleting historical readings.

The water limit (0.5 m), main's hourly rain limit (1 mm), three-reading confirmation, and environmental limits are examples that need site calibration. At 180-second sampling, three-reading confirmation can take about nine minutes. Main's flow calibration of 12 pulses/litre is retained; set it for the installed meter. Battery percentage is a linear estimate.

Telemetry uses main's exact field names: `bme_temp_c`, `bme_humidity_pct`, `bme_pressure_hpa`, `sps_depth_m`, `sps_pressure_bar`, `wind_speed_ms`, `wind_dir`, `flow_lpm`, `distance_m`, `battery_pct`, and `rainfall`, plus a UTC timestamp. Rainfall is the cumulative-counter delta since the previous durably queued report; hourly rainfall remains the alarm input. Raw voltage, flow totals, and hourly/cumulative rain remain available in SQLite. The rainfall baseline survives restart. Flow totals reset on restart.

AQI adds `pm1`, `pm25`, `pm10` (ug/m3), `aqi`, and `aqi_provisional` to every telemetry record. The index reuses the existing driver's Indonesian ISPU calculation from rolling PM2.5/PM10 averages, rather than a US EPA AQI formula. Averages are in memory and reset on restart; the default window is 24 hours. `aqi_provisional` stays true until that window has elapsed since the first valid sample. A false flag does not certify data completeness or regulatory accuracy. Missing measurements and the flag are null on sensor failure.

The SEN0460 defaults to a nonblocking 30-second warm-up; other sensors and alarms continue during it. Configure `EFWS_AQI_ADDR`, `EFWS_AQI_WINDOW_SEC`, `EFWS_AQI_WARMUP_SEC`, and optionally `EFWS_AQI_WAKE` in `.env`. AQI is monitored and reported; it does not add a siren trigger. Mock mode includes synthetic particulate readings and the same rolling calculation.

Ultrasonic-derived depth is used locally only when `EFWS_ULTRASONIC_MOUNT_HEIGHT_M` is measured. Otherwise the configured raw-distance threshold applies. `sps_depth_m` always means pressure depth and is null on a pressure fault; it is never replaced by another sensor's measurement. Use distinct wind and modem serial ports.

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
python3 -m unittest discover -s tests -p test_aqi_runtime.py -v
python3 tests/test_aqi.py
```
