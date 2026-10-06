# EFWS — Complete Guide: Wiring → Testing → API Prototyping → Background Operation

This guide from NOL until EFWS running stabil in background, using
real hardware: Raspberry Pi 4, MCP3008 (ADC SPI), Logic Level Converter,
BME280, Submersible pressure sensor
(4-20mA), Module sensor voltage DC 0-25V (battery), RS485 Anemometer,
A7670E/SIM7600 (4G+GNSS, one only), Relay 5V + Siren 12V 120dB.

Structure project this **flat** — `main.py` exists directly in root project
(not in subfolder). `venv/`, `.env`, `scripts/`, `logs/`, `database/`
all sejajar with `main.py`.

---

## STAGE 0 — Wiring physical

**REQUIRED read first**: `docs/Pinout.md` — contains tabel wiring complete per
components, including note safety logic level converter (5V DIGITAL signals must go
through the level converter before entering GPIO; ANALOG signals to the MCP3008
must stay below 3.3V and connect directly, never through the LLC) and
note safety route 12V siren.

After all cable installed, **DO NOT directly Run code** — continue
first to preparation OS & check device first in Stage 2.

---

## STAGE 1 — Move project to Raspberry Pi

```bash
scp -r efws pi@<ip-raspberry-pi>:/home/pi/efws
ssh pi@<ip-raspberry-pi>
cd /home/pi/efws
```

---

## STAGE 2 — Preparation OS (sekali only)

```bash
sudo apt update && sudo apt install -y python3-venv python3-pip \
    i2c-tools usb-modeswitch modemmanager network-manager git

sudo raspi-config
# Interface Options -> I2C  -> Yes   (for BME280)
# Interface Options -> SPI  -> Yes   (for MCP3008)
# Interface Options -> Serial Port -> "login shell over serial" = No,
#                                     "serial port hardware" = Yes
#                                     (ONLY if A7670E disambung via UART,
#                                      If via USB step this can exceeded)
sudo reboot
```

After reboot, check device-device physical already detected before continue:
```bash
ls /dev/spidev*     # must appear /dev/spidev0.0 (MCP3008)
i2cdetect -y 1       # must appear 0x76 (BME280)
ls /dev/ttyUSB*      # must appear several ttyUSBx (A7670E + anemometer)
```
If one above NOT appear, stop first and check wiring/
`raspi-config` before continue — do not force continue to instalasi Python.

Add user `pi` to group that needed so that NOT need `sudo`
every access hardware:
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

---

## STAGE 4 — Setup `.env` (mode mock first, then webhook.site)

```bash
cp .env.example .env
nano .env
```

for **prototyping fast to API**, open https://webhook.site in browser,
copy "Your unique URL", then content:
```this
EFWS_RUN_MODE=mock
EFWS_API_URL=https://webhook.site/xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
EFWS_API_KEY=
```
Leave `EFWS_RUN_MODE=mock` first in stage this — we test connection API
without hardware first, new testing per-sensor one by one, new
move to `hardware` in STAGE 7.

---

## STAGE 5 — Test connection API (webhook.site) duluan

```bash
source venv/bin/activate
python3 tests/test_webhook_api.py
```
Open page webhook.site You — one request POST JSON telemetry must
appear there live. If this succeeds, the Pi-to-internet-to-API route is
terbukti bekerja, new continue to testing sensor one by one.

> not yet a connection internet/4G in Pi? Use `tools/mock_api_server.py`
> first (Run in laptop that one network with Pi, then set
> `EFWS_API_URL=http://<ip-laptop>:5000/api/v1/efws` in `.env`) so that can
> see JSON that sent in a directly without need internet at all.

---

## STAGE 6 — Test every sensor one by one (ORDER THIS IMPORTANT)

Run **sequential** — If one failed, resolve it first before continue
to the next test (all analog sensors depend on the MCP3008, so
If test #1 failed, all sensor analog afterward also will failed).

```bash
# 1. MCP3008 first - foundation for all analog sensors
python3 tests/test_mcp3008.py

# 2. BME280 (I2C, independent from MCP3008)
python3 tests/test_bme280.py

# 3. Submersible pressure sensor (analog via burden resistor, through MCP3008)
python3 tests/test_pressure.py

# 4. Battery voltage sensor (analog, through MCP3008)
python3 tests/test_battery.py

# 5. RS485 Anemometer
python3 tests/test_anemometer.py

# 6. A7670E/SIM7600 - signal, SIM, GPS
python3 tests/test_a7670e.py --gps-timeout 90

# 7. Relay + Siren (⚠️ SUARA LOUD 120dB, read warning in the script)
python3 tests/test_relay_siren.py

# 8. All sensors together, one read cycle (final check before main.py)
python3 tests/test_all_sensors.py

# 9. Offline queue integrity (simulate signal loss and verify data is unchanged)
python3 tests/test_offline_queue_integrity.py
```

---

## STAGE 7 — Run EFWS full in mode hardware (foreground first)

```bash
nano .env
# Change: EFWS_RUN_MODE=hardware

python3 main.py
```
Amati several cycle read (default every 5 seconds) — make sure all value
sensor produces sensible values, then check webhook.site to confirm that the data
sent. Press `Ctrl+C` for stop After sure all running either.

---

## STAGE 8 — Run in background (without mengganggu terminal)

Two methods — select one according to needs:

### Methods A: `scripts/efws_ctl.sh` (fast, for still sering edit code)

```bash
chmod +x scripts/efws_ctl.sh
./scripts/efws_ctl.sh start      # Run
./scripts/efws_ctl.sh status     # check running/NOT + CPU/RAM
./scripts/efws_ctl.sh logs       # tail log real-time (Ctrl+C only stop monitoring, process still running)
./scripts/efws_ctl.sh restart    # REQUIRED Run this every time update code
./scripts/efws_ctl.sh stop       # stop
```

### Methods B: systemd (recommended for production — auto-start when boot, auto-restart when crash)

```bash
sudo cp efws.service /etc/systemd/system/efws.service
sudo systemctl daemon-reload
sudo systemctl enable efws      # auto-start when boot
sudo systemctl start efws       # Run now

sudo systemctl status efws          # check running/NOT
sudo systemctl restart efws         # REQUIRED Run this every time update code
sudo systemctl stop efws            # stop
sudo journalctl -u efws -f          # log system real-time
tail -f logs/efws.log               # log aplikasi (more details)
```

`.env` read automatically through `EnvironmentFile=` in `efws.service` — therefore
edit `.env` then `systemctl restart efws` enough, NOT need sentuh file
service again unless you replace the path or user.

---

## STAGE 9 — Move from webhook.site to API production

After prototyping finished and backend original already ready:
```bash
nano .env
# EFWS_API_URL=https://api-you.com/api/v1/efws
# EFWS_API_KEY=token_rahasia_anda   (if backend use auth Bearer token)

./scripts/efws_ctl.sh restart    # or: sudo systemctl restart efws
```

---

## Troubleshooting per components

| Components | Gejala | Possibly penyebab |
|----------|--------|------------------------|
| MCP3008 | `test_mcp3008.py` failed open SPI | SPI not active yet in raspi-config; `spidev` not yet terinstall; wiring CLK/DOUT/DIN/CS wrong |
| BME280 | `i2cdetect -y 1` NOT appear 0x76 | I2C not active yet; wiring SDA/SCL reversed; address actually 0x77 (set `EFWS_BME280_ADDR=0x77`) |
| Pressure sensor | `current_ma` always ~0, `fault_open_loop=True` | Loop disconnected/not yet connected, or PSU 12-24V loop not yet on — Run `python3 tests/test_pressure.py` for diagnosis |
| Pressure sensor | `depth_m` NOT enter sense | `EFWS_PRESSURE_RANGE_M` not yet adapted datasheet sensor You |
| Battery sensor | `voltage`/`percent` NOT enter sense | `BATTERY_DIVIDER_RATIO`/`BATTERY_MAX_V`/`BATTERY_MIN_V` not yet adapted to your module and battery |
| Anemometer | Exception when read | Slave ID/register Modbus wrong (check datasheet unit You); wiring A/B reversed |
| A7670E | `AT` NOT responds | Port wrong (`ls /dev/ttyUSB*`), module not yet power-on, baudrate wrong |
| A7670E | GPS timeout continuously | Antenna GNSS not yet installed/There is no sky open; make sure use `AT+CGNSSPWR` not `AT+CGPS` (already correct in code this) |
| Relay/Siren | Relay "click" but siren NOT sound | source 12V not yet connected; wiring COM/NO wrong |
| Relay/Siren | Relay NOT "click" at all | `active_low` wrong; GPIO pin in `.env` NOT according to wiring physical |
| API | `test_webhook_api.py` failed send | check `ping 8.8.8.8` (internet running?); `EFWS_API_URL` still placeholder |
| systemd | `status` → `failed` | `journalctl -u efws -n 50 --no-pager` for details; usually module Python not yet terinstall in venv, or `.env` NOT found |
