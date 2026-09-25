# EFWS — Complete Guide: Wiring → Testing → API Prototyping → Background Operation

This guide from NOL sampai EFWS jalan stabil di background, memakai
hardware aktual: Raspberry Pi 4, MCP3008 (ADC SPI), Logic Level Converter,
MQ-2, MQ-135, BME280, 2x Soil moisture probe, Submersible pressure sensor
(4-20mA), Module sensor voltage DC 0-25V (battery), RS485 Anemometer,
A7670E/SIM7600 (4G+GNSS, wrong satu saja), Relay 5V + Sirine 12V 120dB.

Struktur project ini **flat** — `main.py` ada directly di root project
(not di subfolder). `venv/`, `.env`, `scripts/`, `logs/`, `database/`
semuanya sejajar with `main.py`.

---

## TAHAP 0 — Wiring physical

**WAJIB dibaca dulu**: `docs/Pinout.md` — contains tabel wiring lengkap per
komponen, termasuk catatan keselamatan logic level converter (signal 5V
sensor analog must through level converter before enter MCP3008/GPIO) and
catatan keselamatan jalur 12V sirine.

After all kabel installed, **JANGAN directly Run kode** — lanjut
dulu ke persiapan OS & check device terlebih dulu di Tahap 2.

---

## TAHAP 1 — Pindahkan project ke Raspberry Pi

```bash
scp -r efws pi@<ip-raspberry-pi>:/home/pi/efws
ssh pi@<ip-raspberry-pi>
cd /home/pi/efws
```

---

## TAHAP 2 — Persiapan OS (sekali saja)

```bash
sudo apt update && sudo apt install -y python3-venv python3-pip \
    i2c-tools usb-modeswitch modemmanager network-manager git

sudo raspi-config
# Interface Options -> I2C  -> Yes   (for BME280)
# Interface Options -> SPI  -> Yes   (for MCP3008)
# Interface Options -> Serial Port -> "login shell over serial" = No,
#                                     "serial port hardware" = Yes
#                                     (ONLY if A7670E disambung via UART,
#                                      If via USB langkah ini can dilewati)
sudo reboot
```

After reboot, check device-device physical already detected before lanjut:
```bash
ls /dev/spidev*     # must appear /dev/spidev0.0 (MCP3008)
i2cdetect -y 1       # must appear 0x76 (BME280)
ls /dev/ttyUSB*      # must appear several ttyUSBx (A7670E + anemometer)
```
If wrong satu di atas NOT appear, stop dulu and check wiring/
`raspi-config` before lanjut — jangan paksa lanjut ke instalasi Python.

Add user `pi` ke grup that dibutuhkan so that NOT need `sudo`
every akses hardware:
```bash
sudo usermod -aG gpio,spi,i2c,dialout pi
sudo reboot
```

---

## TAHAP 3 — Setup Python environment

```bash
cd /home/pi/efws
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
deactivate
```

---

## TAHAP 4 — Setup `.env` (mode mock dulu, lalu webhook.site)

```bash
cp .env.example .env
nano .env
```

for **prototyping cepat ke API**, buka https://webhook.site di browser,
copy "Your unique URL", lalu content:
```ini
EFWS_RUN_MODE=mock
EFWS_API_URL=https://webhook.site/xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
EFWS_API_KEY=
```
Biarkan `EFWS_RUN_MODE=mock` dulu di tahap ini — kita test connection API
without hardware terlebih dulu, new testing per-sensor satu-satu, new
pindah ke `hardware` di TAHAP 7.

---

## TAHAP 5 — Test connection API (webhook.site) duluan

```bash
source venv/bin/activate
python3 tests/test_webhook_api.py
```
Buka halaman webhook.site Anda — satu request POST JSON telemetry must
appear live di sana. If ini sukses, jalur Pi → internet → API already
terbukti bekerja, new lanjut ke testing sensor satu-satu.

> not yet ada connection internet/4G di Pi? Use `tools/mock_api_server.py`
> dulu (Run di laptop that satu jaringan with Pi, lalu set
> `EFWS_API_URL=http://<ip-laptop>:5000/api/v1/efws` di `.env`) so that can
> see JSON that sent secara directly without need internet sama sekali.

---

## TAHAP 6 — Test every sensor satu-satu (URUTAN INI PENTING)

Run **sequential** — If satu failed, selesaikan dulu before lanjut
ke that next (sensor analog semuanya bergantung ke MCP3008, jadi
If test #1 failed, all sensor analog setelahnya juga akan failed).

```bash
# 1. MCP3008 dulu - fondasi all sensor analog
python3 tests/test_mcp3008.py

# 2. MQ-2 & MQ-135 (analog, through MCP3008)
python3 tests/test_gas_sensors.py

# 3. BME280 (I2C, independen from MCP3008)
python3 tests/test_bme280.py

# 4. Soil moisture probe (analog, through MCP3008) - termasuk kalibrasi
python3 tests/test_soil.py

# 5. Submersible pressure sensor (analog via burden resistor, through MCP3008)
python3 tests/test_pressure.py

# 6. Battery voltage sensor (analog, through MCP3008)
python3 tests/test_battery.py

# 7. RS485 Anemometer
python3 tests/test_anemometer.py

# 8. A7670E/SIM7600 - signal, SIM, GPS
python3 tests/test_a7670e.py --gps-timeout 90

# 9. Relay + Sirine (⚠️ SUARA KERAS 120dB, read warning di scriptnya)
python3 tests/test_relay_siren.py

# 10. All sensor sekaligus, satu putaran read (final check before main.py)
python3 tests/test_all_sensors.py

# 11. Integritas offline queue (simulasi signal lost, check data NOT berubah)
python3 tests/test_offline_queue_integrity.py
```

---

## TAHAP 7 — Run EFWS full di mode hardware (foreground dulu)

```bash
nano .env
# Ubah: EFWS_RUN_MODE=hardware

python3 main.py
```
Amati several siklus read (default every 5 seconds) — make sure all value
sensor enter akal, lalu check webhook.site for konfirmasi data correct-correct
sent. Tekan `Ctrl+C` for stop After yakin semuanya jalan baik.

---

## TAHAP 8 — Run di background (without mengganggu terminal)

Dua cara — pilih wrong satu sesuai kebutuhan:

### Cara A: `scripts/efws_ctl.sh` (cepat, for masih sering edit kode)

```bash
chmod +x scripts/efws_ctl.sh
./scripts/efws_ctl.sh start      # Run
./scripts/efws_ctl.sh status     # check jalan/NOT + CPU/RAM
./scripts/efws_ctl.sh logs       # tail log real-time (Ctrl+C only stop pantau, proses tetap jalan)
./scripts/efws_ctl.sh restart    # WAJIB Run ini every kali update kode
./scripts/efws_ctl.sh stop       # stop
```

### Cara B: systemd (recommended for production — auto-start when boot, auto-restart when crash)

```bash
sudo cp efws.service /etc/systemd/system/efws.service
sudo systemctl daemon-reload
sudo systemctl enable efws      # auto-start when boot
sudo systemctl start efws       # Run sekarang

sudo systemctl status efws          # check jalan/NOT
sudo systemctl restart efws         # WAJIB Run ini every kali update kode
sudo systemctl stop efws            # stop
sudo journalctl -u efws -f          # log sistem real-time
tail -f logs/efws.log               # log aplikasi (lebih detail)
```

`.env` dibaca automatically through `EnvironmentFile=` di `efws.service` — jadi
edit `.env` lalu `systemctl restart efws` cukup, NOT need sentuh file
service lagi kecuali ganti path/user.

---

## TAHAP 9 — Pindah from webhook.site ke API production

After prototyping finished and backend original already ready:
```bash
nano .env
# EFWS_API_URL=https://api-anda.com/api/v1/efws
# EFWS_API_KEY=token_rahasia_anda   (if backend use auth Bearer token)

./scripts/efws_ctl.sh restart    # or: sudo systemctl restart efws
```

---

## Troubleshooting per komponen

| Komponen | Gejala | Possibly penyebab |
|----------|--------|------------------------|
| MCP3008 | `test_mcp3008.py` failed buka SPI | SPI not yet aktif di raspi-config; `spidev` not yet terinstall; wiring CLK/DOUT/DIN/CS wrong |
| MQ-2/MQ-135 | value selalu mentok di angka sama (clipping) | Lupa pasang logic level converter di jalur analognya |
| MQ-2/MQ-135 | value ppm NOT enter akal | Sensor not yet preheat (needs 24-48 hours for akurasi full) |
| BME280 | `i2cdetect -y 1` NOT appear 0x76 | I2C not yet aktif; wiring SDA/SCL terbalik; alamat sebenarnya 0x77 (set `EFWS_BME280_ADDR=0x77`) |
| Soil probe | moisture_percent selalu 0% or 100% | not yet dikalibrasi (`dry_raw`/`wet_raw` di `sensors/soil.py`) |
| Pressure sensor | `current_ma` selalu ~0, `fault_open_loop=True` | Loop disconnected/not yet connected, or PSU 12-24V loop not yet nyala — Run `python3 tests/test_pressure.py` for diagnosis |
| Pressure sensor | `depth_m` NOT enter akal | `EFWS_PRESSURE_RANGE_M` not yet disesuaikan datasheet sensor Anda |
| Battery sensor | `voltage`/`percent` NOT enter akal | `BATTERY_SENSOR_MAX_V`/`BATTERY_MAX_V`/`BATTERY_MIN_V` not yet disesuaikan specification battery |
| Anemometer | Exception when read | Slave ID/register Modbus wrong (check datasheet unit Anda); wiring A/B terbalik |
| A7670E | `AT` NOT merespons | Port wrong (`ls /dev/ttyUSB*`), module not yet power-on, baudrate wrong |
| A7670E | GPS timeout terus | Antenna GNSS not yet installed/There is no sky open; make sure use `AT+CGNSSPWR` not `AT+CGPS` (already correct di kode ini) |
| Relay/Sirine | Relay "klik" tapi sirine NOT bunyi | source 12V not yet connected; wiring COM/NO wrong |
| Relay/Sirine | Relay NOT "klik" sama sekali | `active_low` wrong; GPIO pin di `.env` NOT sesuai wiring physical |
| API | `test_webhook_api.py` failed send | check `ping 8.8.8.8` (internet jalan?); `EFWS_API_URL` masih placeholder |
| systemd | `status` → `failed` | `journalctl -u efws -n 50 --no-pager` for detail; biasanya module Python not yet terinstall di venv, or `.env` NOT found |
