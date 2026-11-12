# Run the current flood system on a Raspberry Pi

The current runtime loads pressure, rainfall, ultrasonic distance, water flow, voltage, BME280, wind speed, wind direction, and SEN0460 air quality. Commands below run on the Pi from this repository root; adjust the path for your checkout.

## Prepare interfaces and Python

```bash
cd ~/Documents/flood-detection-system
sudo apt update
sudo apt install -y python3-venv python3-dev i2c-tools swig liblgpio-dev
sudo raspi-config
# Interface Options -> SPI -> Enable
# Interface Options -> I2C -> Enable
sudo usermod -aG gpio,spi,i2c,dialout "$USER"
# Reboot or log in again to apply interface/group changes.
```

After logging back in:

```bash
cd ~/Documents/flood-detection-system
ls /dev/spidev0.0
i2cdetect -y 1
# Expected: rain 1d, SEN0460 AQI 19, BME280 76 or 77.
python3 -m venv venv
source venv/bin/activate
python3 -m pip install -r requirements.txt
# Only if .env does not already exist:
test -f .env || cp .env.example .env
nano .env
```

Set the device ID/token, real API base URL, fallback latitude/longitude, and `EFWS_RUN_MODE=hardware`. Exported environment variables and systemd settings override `.env`; `.env` fills values that are not already set. The local `.env` is not modified by the branch changes.

Check [Pinout.md](Pinout.md), pressure range/burden/ADC reference, voltage divider ratio and battery endpoints, and flow pulses/litre. Battery percentage is only a linear voltage estimate. Configure the optional ultrasonic mounting height to use distance as a depth alarm/fallback. Without that measurement it reports distance only.

Edit `config/thresholds.json` for site-appropriate high-water, pressure, distance, hourly rainfall, and environmental limits. The example water limit is 0.5 m and main's hourly rain limit is 1 mm. With 180-second sampling and three consecutive danger readings, activation can take roughly nine minutes. Remote numeric thresholds override local fields. Match the flow calibration (default 12 pulses/litre) to the installed meter. Configure wind speed's Modbus address/register/scale and wind direction's UART settings in `.env`; neither may share the modem's AT port.

## Validate and run

```bash
python3 -m unittest discover -s tests -p test_runtime.py -v
python3 -m unittest discover -s tests -p test_aqi_runtime.py -v
python3 tests/test_aqi.py
python3 tests/test_all_sensors.py
EFWS_RUN_MODE=hardware python3 main.py
```

The hardware check reads all nine sensors and waits for AQI warm-up before its single reading. Pressure loop faults, missing ultrasonic echoes, and driver errors fail the check. Zero flow when stationary is valid. Verify pressure, voltage, flow, and serial-sensor calibration against independent measurements or the sensor datasheets.

SEN0460 shares the I2C bus at address 0x19 by default (`EFWS_AQI_ADDR`). In normal runtime its default 30-second warm-up reports null while other sensors continue; no sleep is added to the main loop. The available PM2.5/PM10 readings are averaged using the existing ISPU-style calculation over `EFWS_AQI_WINDOW_SEC` (default 86400). The average resets on restart. `aqi_provisional` is true until the window elapses after the first valid sample; it does not measure sampling completeness. `EFWS_AQI_WAKE=true` enables the existing optional wake command. The dedicated live check remains `python3 tests/test_aqi.py --live`.

In runtime a missing sensor is reported as null and an error; the remaining sensors keep running. Check the logs for errors rather than assuming a running process proves healthy hardware. Sensors that fail startup initialization remain unavailable until restart after repair. Stop with Ctrl+C; the siren is silenced and hardware resources are released.

For a local HTTP check, run `python3 tools/mock_api_server.py` in another terminal, then:

```bash
EFWS_RUN_MODE=mock EFWS_API_URL=http://127.0.0.1:5000/api/v1/efws python3 main.py
```

This uses simulated sensors. Confirm the actual backend accepts the fields and nulls described in [Architecture.md](Architecture.md). No production backend/schema is included in this repository.

## Optional systemd service

The service template is `efws.service`. Render its paths and user for the actual checkout before installing:

```bash
sed -e "s|/home/uwfadmin/ews|$PWD|g" \
    -e "s|User=uwfadmin|User=$USER|" \
    -e "s|Group=uwfadmin|Group=$(id -gn)|" \
    efws.service | sudo tee /etc/systemd/system/efws.service >/dev/null
sudo systemctl daemon-reload
sudo systemctl enable --now efws.service
journalctl -u efws.service -f
```

Verify the rendered `WorkingDirectory`, `ExecStart`, `EnvironmentFile`, `User`, and `Group` before starting. Stop an existing manual instance first to avoid GPIO contention. Wi-Fi/Ethernet operation does not require `gsm-connect.service`; configure cellular connectivity separately if using it. The service needs hardware mode in its environment file.

The optional backend `Reboot` command restarts this service after a delay, using `sudo -n systemctl restart efws.service`. Configure that exact sudo permission for the service user if the command is required. SUCCESS acknowledges scheduling only. Mock mode never restarts the service.
