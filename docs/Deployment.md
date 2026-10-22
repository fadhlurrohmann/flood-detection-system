# Run the current flood system on a Raspberry Pi

The current runtime uses pressure, rainfall, ultrasonic distance, water flow, and voltage. BME280 is planned for later; soil and wind are not required. Commands below run on the Pi, from this repository root. Adjust the directory if your checkout is elsewhere.

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
# Expected rain address: 1d; a BME280 address is not required.
python3 -m venv venv
source venv/bin/activate
python3 -m pip install -r requirements.txt
# Only if .env does not already exist:
test -f .env || cp .env.example .env
nano .env
```

Set the device ID/token, real API base URL, fallback latitude/longitude, and `EFWS_RUN_MODE=hardware`. Exported environment variables and systemd settings override `.env`; `.env` fills values that are not already set. The local `.env` is not modified by the branch changes.

Check [Pinout.md](Pinout.md), pressure range/burden/ADC reference, voltage divider ratio and battery endpoints, and flow pulses/litre. Battery percentage is only a linear voltage estimate. Configure the optional ultrasonic mounting height to use distance as a depth alarm/fallback. Without that measurement it reports distance only.

Edit `config/thresholds.json` for site-appropriate **high-water** and last-hour rainfall limits. The example values 0.5 m and 30 mm/hour are not validated deployment limits. With 180-second sampling and three consecutive danger readings, a new event can take roughly nine minutes to activate the siren; choose the sampling interval and streak deliberately. Remote numeric thresholds can override each local field after the server responds.

## Validate and run

```bash
python3 -m unittest discover -s tests -p test_runtime.py -v
python3 tests/test_all_sensors.py
EFWS_RUN_MODE=hardware python3 main.py
```

The hardware check reads all five sensors. No soil/BME/wind is expected. Pressure open-loop faults or missing ultrasonic echoes fail that check. A zero flow rate when water is stationary is valid; verify flow calibration with water moving. A disconnected analog input can float, so compare pressure and voltage readings against independent measurements.

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
