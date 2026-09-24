# EFWS — out & Wiring Reference

Hardware final:
**Raspberry Pi 4 · MCP3008 (SPI ADC 8-ch) · 1x Logic Level Converter (min. 6-channel)
· MQ-2 · MQ-135 · BME280 (I2C) · Soil Probe Surface · Soil Probe Deep
· Submersible Pressure Sensor (loop 4-20mA) · Modul Sensor Tegangan DC 0-25V (battery)
· RS485 Anemometer · A7670E or SIM7600 (auto-detect, ONLY salah satu dipasang)
· Relay 5V · Sirine 12V**

> There is no flame sensor di hardware ini. There is no buzzer terpisah — cukup
> satu relay + sirine (2 tingkat eskalasi lewat pola berdenyut vs nyala terus,
> see `alarm/siren.py`). Threshold & keputusan alarm level dievaluasi lokal
> ONLY for menyalakan sirine real-time — NOT disimpan ke database lokal,
> because evaluasi alarm "resmi" ada di backend.

---

## 1. Raspberry Pi 4 — Pin that Digunakan (BCM Numbering)

| Fungsi | GPIO (BCM) | Pin Fisik | Keterangan |
|--------|-----------|-----------|------------|
| SPI SCLK (MCP3008) | GPIO11 | Pin 23 | Clock SPI |
| SPI MISO (MCP3008) | GPIO9  | Pin 21 | Data from MCP3008 |
| SPI MOSI (MCP3008) | GPIO10 | Pin 19 | Data ke MCP3008 |
| SPI CE0  (MCP3008) | GPIO8  | Pin 24 | Chip Select |
| I2C SDA (BME280)   | GPIO2  | Pin 3  | Data I2C |
| I2C SCL (BME280)   | GPIO3  | Pin 5  | Clock I2C |
| Relay Sirine (output) | GPIO27 | Pin 13 | Ke IN relay 5V |
| Status LED (output, opsional) | GPIO23 | Pin 16 | Indikator heartbeat |
| 5V Rail | — | Pin 2 & 4 | Power LLC HV (jangan from sini If arus besar) |
| 3.3V Rail | — | Pin 1 & 17 | Power LLC LV, MCP3008 VDD/VREF, BME280 |
| GND | — | Pin 6, 9, 14, 20, 25, 30, 34, 39 | Ground bersama |

Aktifkan interface:
```bash
sudo raspi-config
# Interface Options → SPI → Yes
# Interface Options → I2C → Yes
```

---

## 2. BME280 — Wiring I2C (ambient: suhu / kelembaban / pressure)

| Pin BME280 | Hubung ke |
|-----------|-----------|
| VIN | Pi 3.3V |
| GND | GND bersama |
| SCL | GPIO3 (Pin 5) |
| SDA | GPIO2 (Pin 3) |

BME280 **NOT** lewat MCP3008/LLC — modul ini I2C native, langsung ke Pi.

```bash
i2cdetect -y 1     # must appear 0x76 (or 0x77 If alamat berbeda)
python3 tests/test_bme280.py
```

---

## 3. MCP3008 — Wiring ke Raspberry Pi

| Pin MCP3008 | Hubung ke | Catatan |
|-------------|-----------|---------|
| VDD (pin 16) | Pi 3.3V | **JANGAN 5V** |
| VREF (pin 15) | Pi 3.3V | Skala ADC 0-3.3V = raw 0-1023 |
| AGND (pin 14) | GND bersama | |
| CLK (pin 13)  | GPIO11 (SCLK) | |
| DOUT (pin 12) | GPIO9 (MISO)  | |
| DIN (pin 11)  | GPIO10 (MOSI) | |
| CS/SHDN (pin 10) | GPIO8 (CE0) | |
| DGND (pin 9)  | GND bersama | |
| CH0-CH5 | see tabel channel di bawah | Semua lewat LLC |
| CH6-CH7 | Spare, NOT dikabel | |

Verifikasi: `ls /dev/spidev*` → must appear `/dev/spidev0.0`

---

## 4. Peta Channel MCP3008 — SATU Logic Level Converter

Semua sinyal analog 0-5V **wajib** lewat LLC before masuk MCP3008 (VREF 3.3V).
Gunakan modul LLC minimal 6-channel bidirectional (mis. modul 8-channel TXS0108E —
lebih umum dijual and menyisakan 2 channel for ekspansi).

| LLC | Sisi HV (5V) ← from sensor | Sisi LV (3.3V) → ke MCP3008 | Channel |
|-----|---------------------------|------------------------------|---------|
| HV-1 / LV-1 | YF-S201 **AOUT** | NONE | water flow digital |
| HV-2 / LV-2 | MQ-135 **AOUT** | **CH1** | Air quality analog |
| HV-3 / LV-3 | Soil Surface **AOUT** | **CH2** | Kelembaban 0-30cm |
| HV-4 / LV-4 | Soil Deep **AOUT** | **CH3** | Kelembaban 30-60cm |
| HV-5 / LV-5 | Pressure sensor (via **R_BURDEN**) | **CH4** | Ketinggian air (loop 4-20mA) |
| HV-6 / LV-6 | Voltage Sensor Module **OUT** | **CH5** | Tegangan battery (0-25V) |
| HV-7..8 / LV-7..8 | *(spare / ekspansi)* | CH6-CH7 | — |

### Wiring modul LLC

```
LLC:
  HV  pin  ←── 5V  (from buck converter / Pi pin 2/4)
  LV  pin  ←── 3.3V (from Pi pin 1/17)
  GND HV   ←── GND bersama
  GND LV   ←── GND bersama
```

---

## 5. Sensor per Sensor — Detail Wiring

### MQ-2 (Smoke / Combustible Gas)
| Pin sensor | Hubung ke |
|-----------|-----------|
| VCC | 5V (langsung from source, bukan from Pi GPIO 5V) |
| GND | GND bersama |
| AOUT | LLC **HV-1** → LV-1 → MCP3008 **CH0** |

> Heater ~150mA — power langsung from buck converter, jangan from Pi GPIO 5V.

### YF-S201 (Water flow sensor)
| Pin sensor | Hubung ke |
|-----------|-----------|
| VCC | 5V (langsung from source) |
| GND | GND bersama |
| AOUT | LLC **HV-1** → LV-1 → MCP3008 |

### Soil Moisture Probe — Surface (0-30cm)
| Pin probe | Hubung ke |
|----------|-----------|
| VCC | 5V |
| GND | GND bersama |
| AOUT | LLC **HV-3** → LV-3 → MCP3008 **CH2** |

### Soil Moisture Probe — Deep (30-60cm)
| Pin probe | Hubung ke |
|----------|-----------|
| VCC | 5V |
| GND | GND bersama |
| AOUT | LLC **HV-4** → LV-4 → MCP3008 **CH3** |

> Kalibrasi wajib per probe (see `sensors/soil.py`): dry_raw di udara kering, wet_raw terendam air.

### Submersible Pressure Sensor — loop 4-20mA (Ketinggian Air)

Sensor ini **loop-powered 2-kabel** (bukan 0-5V langsung), jadi wiring-nya beda
from sensor lain: butuh **burden resistor** presisi for mengubah arus loop
menjadi tegangan that can dibaca ADC.

```
PSU 12-24V (+) ──────────► Sensor Loop V+
                                  │
                    Sensor (variabel 4-20mA sesuai pressure/kedalaman)
                                  │
                                  ▼
                    ┌─────────────────────────┐
                    │  R_BURDEN = 250Ω 0.1%   │
                    │  (presisi, low-drift)   │
                    └────────────┬────────────┘
                                 │ tap di titik ini →  0-5V
                                 ▼
                      LLC HV-5 (5V sisi)
                                 │ level shift
                      LLC LV-5 (3.3V sisi)
                                 │
                       MCP3008 CH4
                                 │
PSU 12-24V (−) ──────────► GND bersama (After R_BURDEN)
```

| Titik | Hubung ke |
|-------|-----------|
| Loop V+ | PSU 12-24V (+) — **bukan** from Pi/buck converter 5V |
| Loop keluar (After sensor) | Ujung atas R_BURDEN (250Ω, 0.1%) |
| Ujung bawah R_BURDEN | GND bersama & PSU (−) |
| Titik sambung sensor/R_BURDEN | LLC **HV-5** → LV-5 → MCP3008 **CH4** |

**Kenapa 250Ω persis?**
- 4mA × 250Ω = **1.0V** → level "kosong" (0m)
- 20mA × 250Ω = **5.0V** → level "penuh" (`PRESSURE_RANGE_M`, default 5m — sesuaikan datasheet sensor Anda)

Formula konversi ada di `sensors/pressure.py`. **Sesuaikan** `EFWS_PRESSURE_RANGE_M`
di `.env` with rentang kedalaman/pressure sensor fisik Anda (banyak varian: 0-5m,
0-10m, 0-20m). Payload API sending dua value from sensor ini: `waterLevel` (meter)
and `waterLevelCurrentMa` (arus loop mentah, berguna buat backend mendeteksi loop
disconnected — value mendadak jatuh ke ~0mA berarti kabel disconnected, bukan air kosong).

### Modul Sensor Tegangan DC 0-25V (battery)

Modul ini already punya voltage divider internal (NOT need buat sendiri).

| Pin modul | Hubung ke |
|-----------|-----------|
| IN+ | Terminal Battery+ (12V LiFePO4/sejenis) |
| IN− | Terminal Battery− |
| GND (sisi output) | GND bersama |
| S (output, 0-5V proporsional 0-25V) | LLC **HV-6** → LV-6 → MCP3008 **CH5** |

Formula konversi ada di `sensors/battery.py`. Kalibrasi `BATTERY_MAX_V` /
`BATTERY_MIN_V` di `.env` sesuai specification battery Anda (default 12.6V penuh,
9.0V kosong, cocok for pack 3S LiFePO4).

### RS485 Anemometer (Modbus RTU)
| connection | Hubung ke |
|---------|-----------|
| A (D+) | USB-RS485 converter terminal A |
| B (D−) | USB-RS485 converter terminal B |
| VCC | 12V or 5V sesuai datasheet unit |
| GND | GND bersama |

USB-RS485 → port USB Pi → appear sebagai `/dev/ttyUSB0`. **NOT need LLC.**

### A7670E or SIM7600 (pilih salah satu)

NOT need wiring berbeda antara keduanya — **ONLY pasang salah satu modul**,
`communication/sim_detector.py` akan auto-detect mana that installed
(`AT+CGNSSPWR` → A7670E, `AT+CGPS` → SIM7600) and software menyesuaikan sendiri.

| connection | Detail |
|---------|--------|
| Power | Sesuai board HAT (biasanya 5V from Pi or 3.7-4.2V Li-ion terpisah) |
| Data | USB ke Pi — appear sebagai several `/dev/ttyUSBx` |
| Antena LTE | Wajib |
| Antena GNSS | Wajib terpisah |
| SIM card | Pasang before power-on |

```bash
ls /dev/ttyUSB*
python3 tests/test_sim_detector.py   # konfirmasi modul mana that terdeteksi
```

### Relay 5V → Sirine 12V

```
Sisi kontrol (Pi 3.3V GPIO):          Sisi power high (12V):
  GPIO27 ──────────────► IN relay       Battery+ ─── relay COM
  5V     ──────────────► VCC relay            Relay NO ─── Sirine (+)
  GND    ──────────────► GND relay            Sirine (−) ─── Battery−
```

> ⚠️ Jalur 12V sirine **NOT pernah** boleh menyentuh pin Pi manapun.
> There is no buzzer terpisah — satu relay ini menangani 2 tingkat eskalasi
> (WARNING = berdenyut pelan, CRITICAL = nyala terus), see `alarm/siren.py`.

---

## 6. Diagram Blok Sinyal Lengkap

```
MQ-2 AOUT (5V)      ──┐
MQ-135 AOUT (5V)    ──┤
Soil-S AOUT (5V)    ──┤    LLC (1 modul, 6 channel dipakai)
Soil-D AOUT (5V)    ──┤    HV1-6 (5V) → LV1-6 (3.3V)
Pressure via R_BURDEN─┤
Battery Sensor OUT  ──┘         │
                                ▼
                     MCP3008 CH0-CH5  (SPI0)
                                │
BME280 (I2C langsung) ──────────┤
RS485 Anemometer (USB) ─────────┤
A7670E / SIM7600 (USB) ─────────┤
                                ▼
                       Raspberry Pi 4 — main.py
                       1) read semua sensor
                       2) Save ke SQLite dulu (sensor_readings)
                       3) evaluasi lokal → sirine (real-time, NOT disimpan)
                       4) coba send ke API — failed? masuk antrian (api_queue)
                       5) check sinyal ulang tiap 2 menit → auto-flush antrian
                                │ GPIO27
                                ▼
                        Relay 5V ──► Sirine 12V
```

---

## 7. Catu power Tiap Beban

| Beban | Tegangan | source | Catatan |
|-------|---------|--------|---------|
| Raspberry Pi 4 | 5V | Buck converter output | Via GPIO pin 2/4 or USB-C |
| MCP3008 VDD/VREF | 3.3V | Pi 3.3V rail | |
| BME280 | 3.3V | Pi 3.3V rail | I2C langsung, without LLC |
| LLC LV | 3.3V | Pi 3.3V rail | |
| LLC HV | 5V | Buck converter / Pi 5V rail | |
| MQ-2 / MQ-135 heater | 5V | Buck converter langsung | ~150mA masing-masing |
| Soil probe ×2 | 5V or 3.3V | Sesuai datasheet probe | |
| Submersible pressure sensor | 12-24V (loop) | **PSU terpisah**, bukan from Pi/buck 5V | Loop-powered |
| Modul sensor tegangan (battery) | Pasif, tap from Battery+/− | — | NOT need suplai terpisah |
| RS485 anemometer | 12V or 5V | Sesuai datasheet unit | |
| A7670E/SIM7600 | 5V or 3.7-4.2V | Sesuai board HAT | |
| Relay coil | 5V | Pi 5V rail | |
| Sirine | 12V | Battery (via relay NO/COM) | |

---

## 8. Checklist before Power-On Pertama

```
[ ] SPI aktif (raspi-config → Interface → SPI)
[ ] I2C aktif (raspi-config → Interface → I2C)
[ ] Common ground: Pi, MCP3008, LLC, semua sensor, relay, PSU pressure sensor → satu GND
[ ] LLC: HV=5V, LV=3.3V, 6 channel from sensor connected (CH0-CH5)
[ ] MCP3008 VDD & VREF ke 3.3V (bukan 5V)
[ ] R_BURDEN 250Ω installed benar di loop pressure sensor, tap ke LLC HV-5
[ ] PSU loop pressure sensor terpisah from Pi/buck converter 5V
[ ] Modul sensor tegangan tap langsung ke Battery+/− (bukan lewat relay)
[ ] Jalur 12V sirine ONLY lewat relay COM/NO, NOT menyentuh Pi
[ ] ONLY SATU modul installed: A7670E or SIM7600 (jangan dua-duanya)
[ ] Antena LTE + GNSS installed
[ ] SIM card installed before modul dinyalakan

Verifikasi software:
[ ] ls /dev/spidev*    → /dev/spidev0.0 ada
[ ] i2cdetect -y 1     → alamat BME280 (0x76/0x77) appear
[ ] ls /dev/ttyUSB*    → several port ada (modem + anemometer)
[ ] python3 tests/test_all_sensors.py     → semua sensor OK
[ ] python3 tests/test_offline_queue_integrity.py → integritas queue OK
[ ] python3 tests/test_sim_detector.py    → modul SIM teridentifikasi
```
