# EFWS — Complete Guide: Wiring → Testing → Prototyping API → Running in the Background

This guide goes from ZERO to having EFWS running stably in the background, using actual hardware: Raspberry Pi 4, MCP3008 (SPI ADC), Logic Level Converter, MQ-2, MQ-135, BME280, 2x Soil moisture probes, Submersible pressure sensor (4-20mA), 0-25V DC voltage sensor module (battery), RS485 Anemometer, A7670E/SIM7600 (4G+GNSS, use one), 5V Relay + 12V 120dB Siren.

The project structure is **flat** — `main.py` is located directly in the project root (not in a subfolder). `venv/`, `.env`, `scripts/`, `logs/`, `database/`
are all aligned to `main.py`.

---

## STAGE 0 — Physical Wiring

**MUST read first**: `docs/Pinout.md` — contains a complete wiring table for each component, including logic level converter safety notes (the 5V analog sensor signal MUST pass through the level converter before entering the MCP3008/GPIO) and safety notes for the siren's 12V line.

Once all cables are installed, **DO NOT run the code immediately** — proceed to
OS preparation and device checks in Step 2.

## STEP 1 — Transfer the project to the Raspberry Pi

```bash
scp -r efws pi@<ip-raspberry-pi>:/home/pi/efws
ssh pi@<ip-raspberry-pi>
cd /home/pi/efws
```

---

## STAGE 2 — OS preparation (one time only)

```bash
sudo apt update && sudo apt install -y python3-venv python3-pip \
    i2c-tools usb-modeswitch modemmanager network-manager git

sudo raspi-config
# Interface Options -> I2C -> Yes (for BME280)
# Interface Options -> SPI -> Yes (for MCP3008)
# Interface Options -> Serial Port -> "login shell over serial" = No,
#                                      "serial port hardware" = Yes
#                                       (ONLY if the A7670E is connected via UART,
#                                       if via USB, this step can be skipped)
sudo reboot
```

After rebooting, check that the physical devices are detected before continuing:
```bash
ls /dev/spidev*              # should show /dev/spidev0.0 (MCP3008)
i2cdetect -y 1               # should show 0x76 (BME280)
ls /dev/ttyUSB*              # should show multiple ttyUSBx (A7670E + anemometer)
```
If any of the above does NOT appear, stop first and check the wiring/
`raspi-config` before continuing — do not force continue with Python installation.

Add the `pi` user to the required groups to avoid having to use `sudo` for each hardware access:
```bash
sudo usermod -aG gpio,spi,i2c,dialout pi
sudo reboot
```

---

## STAGE 3 — Setup Python environment

```bash
cd /home/pi/efws
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
deactivate
```

Install dependencies required for LGPIO python library installation. 
```bash
sudo apt update
sudo apt install swig python3-dev
sudo apt install liblgpio-dev
```


---

## STEP 4 — Setup `.env` (mock mode first, then webhook.site)

```bash
cp .env.example .env
nano .env
```

For **quick API prototyping**, open https://webhook.site in a browser, copy "Your unique URL," and then enter:

```ini
EFWS_RUN_MODE=mock
EFWS_API_URL=https://webhook.site/xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
EFWS_API_KEY=
```
Leave `EFWS_RUN_MODE=mock` for now — we'll test the API connection
WITHOUT hardware first, then test each sensor individually, then move on to `hardware` in STEP 7.

---

## STEP 5 — Test the API connection (webhook.site) first

```bash
source venv/bin/activate
python3 tests/test_webhook_api.py
```
Open your webhook.site page — a single JSON telemetry POST request should appear live there. If this is successful, the Pi → internet → API path has been proven to work. Now, you can proceed to testing the sensors individually.


> Don't have an internet/4G connection on your Pi? Use `tools/mock_api_server.py`
> first (run it on a laptop on the same network as the Pi, then set
> `EFWS_API_URL=http://<laptop-ip>:5000/api/v1/efws` in `.env`) to view the sent JSON directly without needing an internet connection at all.

---

## STEP 6 — Test each sensor one by one (THIS ORDER IS IMPORTANT)

Run them **in order** — if one fails, resolve it before moving on to the next (the analog sensors are all dependent on the MCP3008, so if test #1 fails, all analog sensors after it will fail as well).

```bash
#1. MCP3008 first - the foundation of all analog sensors
python3 tests/test_mcp3008.py

# 2. BME280 (I2C, independent of MCP3008)
python3 tests/test_bme280.py

# 3. Submersible pressure sensor (analog via burden resistor, lewat MCP3008)
python3 tests/test_pressure.py

# 4. Battery voltage sensor (analog, via MCP3008)
python3 tests/test_battery.py

# 5. RS485 Anemometer
python3 tests/test_anemometer.py

#6 JSN_SR04T ultrasonic
python3 tests/test_JSN_SR04T.p6

#7 YF_S201.py flow sensor
python3 tests/test_YF_S201.py

#8. A7670E/SIM7600 - sinyal, SIM, GPS
python3 tests/test_a7670e.py --gps-timeout 90

#9. Relay + Sirine (⚠️ LOUD NOISE 120dB, read cautions from script)
python3 tests/test_relay_siren.py

#10. All sensors at once, one read loop (final check before main.py)
python3 tests/test_all_sensors.py

#11. Offline queue integrity (simulate signal disconnection, check data is unchanged)
python3 tests/test_offline_queue_integrity.py
```

---

## STEP 7 — Run full EFWS in hardware mode (foreground first)

```bash
nano .env
# change: EFWS_RUN_MODE=hardware

python3 main.py
```
Observe several read cycles (default is every 5 seconds) — ensure all sensor values ​​are reasonable, then check webhook.site to confirm the data was actually sent. Press Ctrl+C to stop once you're sure everything is working properly.

---

## STEP 8 — Run in background (without disturbing terminal)

Two ways — choose one according to your needs:

### Method A: `scripts/efws_ctl.sh` (quick, for those who still edit code frequently)

```bash
chmod +x scripts/efws_ctl.sh
./scripts/efws_ctl.sh start      # run
./scripts/efws_ctl.sh status     # cek running or not + CPU/RAM
./scripts/efws_ctl.sh logs       # tail log real-time (Ctrl+C just stop monitoring, the process continues)
./scripts/efws_ctl.sh restart    # MUST run on every update code
./scripts/efws_ctl.sh stop       # stop
```

### Method B: systemd (recommended for production — auto-start on boot, auto-restart on crash)

```bash
sudo cp efws.service /etc/systemd/system/efws.service
sudo systemctl daemon-reload
sudo systemctl enable efws      # auto-start when boot
sudo systemctl start efws       # run now

sudo systemctl status efws          # check run
sudo systemctl restart efws         # MANDATORY to run this every time you update the code
sudo systemctl stop efws            # stop
sudo journalctl -u efws -f          # log sistem real-time
tail -f logs/efws.log               # log aplication (more detail)
```
`.env` is read automatically via `EnvironmentFile=` in `efws.service` — so editing `.env` and then `systemctl restart efws` is sufficient; there's no need to touch the service file again unless you change the path/user.

---

## STEP 9 — Moving from webhook.site to production API

Once prototyping is complete and the live backend is ready:

```bash
nano .env
# EFWS_API_URL=https://api-anda.com/api/v1/efws
# EFWS_API_KEY=your_secret_token (if backend uses auth Bearer token)

./scripts/efws_ctl.sh restart    # or: sudo systemctl restart efws
```

---

## Troubleshooting per komponen

| Component | Symptoms | Possible Causes |
|----------|--------|------------------------|
| MCP3008 | `test_mcp3008.py` fails to open SPI | PI is not enabled in raspi-config; spidev is not installed; incorrect CLK/DOUT/DIN/CS wiring |
| BME280 | `i2cdetect -y 1` does not show 0x76 | I2C is not enabled; SDA/SCL wiring is reversed; actual address is 0x77 (set`EFWS_BME280_ADDR=0x77`)|
| Pressure sensor | `current_ma` always ~0, `fault_open_loop=True` | The loop is disconnected/not connected, or the 12–24V loop PSU is not powered on — run `python3 tests/test_pressure.py` for diagnostics |
| Pressure sensor | `depth_m` is unreasonable | `EFWS_PRESSURE_RANGE_M` has not been adjusted to match your sensors datasheet|
| Battery sensor | `voltage`/`percent` doesnt make sence | `BATTERY_SENSOR_MAX_V`/`BATTERY_MAX_V`/`BATTERY_MIN_V` Not yet adjusted to battery specifications |
| Anemometer | Exception when read | Incorrect Modbus slave ID/register (check your unit's datasheet); reversed A/B wiring |
| A7670E | `AT` doesnt response| wrong salah (`ls /dev/ttyUSB*`),module not yet powered on, baudrate is incorrect |
| A7670E | GPS always timeout | GNSS antenna not installed/no open sky; make sure to use it `AT+CGNSSPWR` not `AT+CGPS` (it's correct in this code) |
| Relay/Sirine | Relay "click" bit sirine doesnt make soundd | 12V source not connected; COM/NO wiring incorrect|
| Relay/Sirine | Relay doesnt "click" at all | `active_low` is wrong; GPIO pin in `.env` wiring  is not correct  |
| API | `test_webhook_api.py` fails to send | Check `ping 8.8.8.8` (internet run?); `EFWS_API_URL` still on placeholder |
| systemd | `status` → `failed` | `journalctl -u efws -n 50 --no-pager` untuk detail; biasanya modul Python belum terinstall di venv, atau `.env` tidak ditemukan |
