# EFWS — out & Wiring Reference

Hardware final:
**Raspberry Pi 4 · MCP3008 (SPI ADC 8-ch) · 1x Logic Level Converter (min. 6-channel)
· MQ-2 · MQ-135 · BME280 (I2C) · Soil Probe Surface · Soil Probe Deep
· Submersible Pressure Sensor (loop 4-20mA) · Module Sensor Voltage DC 0-25V (battery)
· RS485 Anemometer · A7670E or SIM7600 (auto-detect, ONLY one installed)
· Relay 5V · Siren 12V**

> There is no flame sensor in hardware this. There is no buzzer separate — enough
> one relay + siren (2 levels escalation through pattern pulses vs on continuously,
> see `alarm/siren.py`). Threshold & keputusan alarm level dievaluasi local
> ONLY for activating siren real-time — NOT stored to local database,
> because evaluation alarm "resmi" exists in backend.

---

## 1. Raspberry Pi 4 — Pin that Used (BCM Numbering)

| Function | GPIO (BCM) | Pin Physical | Description |
|--------|-----------|-----------|------------|
| SPI SCLK (MCP3008) | GPIO11 | Pin 23 | Clock SPI |
| SPI MISO (MCP3008) | GPIO9  | Pin 21 | Data from MCP3008 |
| SPI MOSI (MCP3008) | GPIO10 | Pin 19 | Data to MCP3008 |
| SPI CE0  (MCP3008) | GPIO8  | Pin 24 | Chip Select |
| I2C SDA (BME280)   | GPIO2  | Pin 3  | Data I2C |
| I2C SCL (BME280)   | GPIO3  | Pin 5  | Clock I2C |
| Relay Siren (output) | GPIO27 | Pin 13 | To IN relay 5V |
| Status LED (output, optional) | GPIO23 | Pin 16 | Indikator heartbeat |
| 5V Rail | — | Pin 2 & 4 | Power LLC HV (do not from here If current large) |
| 3.3V Rail | — | Pin 1 & 17 | Power LLC LV, MCP3008 VDD/VREF, BME280 |
| GND | — | Pin 6, 9, 14, 20, 25, 30, 34, 39 | Ground together |

Enable interface:
```bash
sudo raspi-config
# Interface Options → SPI → Yes
# Interface Options → I2C → Yes
```

---

## 2. BME280 — Wiring I2C (ambient: temperature / humidity / pressure)

| Pin BME280 | Connect to |
|-----------|-----------|
| VIN | Pi 3.3V |
| GND | GND together |
| SCL | GPIO3 (Pin 5) |
| SDA | GPIO2 (Pin 3) |

BME280 **NOT** through MCP3008/LLC — module this I2C native, directly to Pi.

```bash
i2cdetect -y 1     # must appear 0x76 (or 0x77 If address different)
python3 tests/test_bme280.py
```

---

## 3. MCP3008 — Wiring to Raspberry Pi

| Pin MCP3008 | Connect to | Note |
|-------------|-----------|---------|
| VDD (pin 16) | Pi 3.3V | **DO NOT 5V** |
| VREF (pin 15) | Pi 3.3V | Skala ADC 0-3.3V = raw 0-1023 |
| AGND (pin 14) | GND together | |
| CLK (pin 13)  | GPIO11 (SCLK) | |
| DOUT (pin 12) | GPIO9 (MISO)  | |
| DIN (pin 11)  | GPIO10 (MOSI) | |
| CS/SHDN (pin 10) | GPIO8 (CE0) | |
| DGND (pin 9)  | GND together | |
| CH0-CH5 | see tabel channel below | All through LLC |
| CH6-CH7 | Spare, NOT dikabel | |

Verify: `ls /dev/spidev*` → must appear `/dev/spidev0.0`

---

## 4. Peta Channel MCP3008 — ONE Logic Level Converter

All signal analog 0-5V **required** through LLC before enter MCP3008 (VREF 3.3V).
Use module LLC minimal 6-channel bidirectional (mis. module 8-channel TXS0108E —
more commonly sold and leaves 2 channels for expansion).

| LLC | Side HV (5V) ← from sensor | Side LV (3.3V) → to MCP3008 | Channel |
|-----|---------------------------|------------------------------|---------|
| HV-1 / LV-1 | YF-S201 **AOUT** | NONE | water flow digital |
| HV-2 / LV-2 | MQ-135 **AOUT** | **CH1** | Air quality analog |
| HV-3 / LV-3 | Soil Surface **AOUT** | **CH2** | Humidity 0-30cm |
| HV-4 / LV-4 | Soil Deep **AOUT** | **CH3** | Humidity 30-60cm |
| HV-5 / LV-5 | Pressure sensor (via **R_BURDEN**) | **CH4** | Water level (loop 4-20mA) |
| HV-6 / LV-6 | Voltage Sensor Module **OUT** | **CH5** | Voltage battery (0-25V) |
| HV-7..8 / LV-7..8 | *(spare / expansion)* | CH6-CH7 | — |

### Wiring module LLC

```
LLC:
  HV  pin  ←── 5V  (from buck converter / Pi pin 2/4)
  LV  pin  ←── 3.3V (from Pi pin 1/17)
  GND HV   ←── GND together
  GND LV   ←── GND together
```

---

## 5. Sensor per Sensor — Details Wiring

### MQ-2 (Smoke / Combustible Gas)
| Pin sensor | Connect to |
|-----------|-----------|
| VCC | 5V (directly from source, not from Pi GPIO 5V) |
| GND | GND together |
| AOUT | LLC **HV-1** → LV-1 → MCP3008 **CH0** |

> Heater ~150mA — power directly from buck converter, do not from Pi GPIO 5V.

### YF-S201 (Water flow sensor)
| Pin sensor | Connect to |
|-----------|-----------|
| VCC | 5V (directly from source) |
| GND | GND together |
| AOUT | LLC **HV-1** → LV-1 → MCP3008 |

### Soil Moisture Probe — Surface (0-30cm)
| Pin probe | Connect to |
|----------|-----------|
| VCC | 5V |
| GND | GND together |
| AOUT | LLC **HV-3** → LV-3 → MCP3008 **CH2** |

### Soil Moisture Probe — Deep (30-60cm)
| Pin probe | Connect to |
|----------|-----------|
| VCC | 5V |
| GND | GND together |
| AOUT | LLC **HV-4** → LV-4 → MCP3008 **CH3** |

> Calibration required per probe (see `sensors/soil.py`): dry_raw in air dry, wet_raw submerged air.

### Submersible Pressure Sensor — loop 4-20mA (Water level)

Sensor this **loop-powered 2-cable** (not 0-5V directly), therefore wiring-nya differs from
from sensor other: needs **burden resistor** presisi for converting loop current
become voltage that can read ADC.

```
PSU 12-24V (+) ──────────► Sensor Loop V+
                                  │
                    Sensor (variabel 4-20mA according to pressure/depth)
                                  │
                                  ▼
                    ┌─────────────────────────┐
                    │  R_BURDEN = 250Ω 0.1%   │
                    │  (presisi, low-drift)   │
                    └────────────┬────────────┘
                                 │ tap in point this →  0-5V
                                 ▼
                      LLC HV-5 (5V side)
                                 │ level shift
                      LLC LV-5 (3.3V side)
                                 │
                       MCP3008 CH4
                                 │
PSU 12-24V (−) ──────────► GND together (After R_BURDEN)
```

| Point | Connect to |
|-------|-----------|
| Loop V+ | PSU 12-24V (+) — **not** from Pi/buck converter 5V |
| Loop exit (After sensor) | End above R_BURDEN (250Ω, 0.1%) |
| End bottom R_BURDEN | GND together & PSU (−) |
| Point sambung sensor/R_BURDEN | LLC **HV-5** → LV-5 → MCP3008 **CH4** |

**Why 250Ω exactly?**
- 4mA × 250Ω = **1.0V** → level "empty" (0m)
- 20mA × 250Ω = **5.0V** → level "full" (`PRESSURE_RANGE_M`, default 5m — adjust datasheet sensor You)

Formula konversi exists in `sensors/pressure.py`. **Adjust** `EFWS_PRESSURE_RANGE_M`
in `.env` with range depth/pressure physical sensor You (many variants: 0-5m,
0-10m, 0-20m). Payload API sending two value from sensor this: `waterLevel` (meter)
and `waterLevelCurrentMa` (loop current raw, berguna for backend detecting loop
disconnected — value suddenly falls back to ~0mA means cable disconnected, not air empty).

### Module Sensor Voltage DC 0-25V (battery)

Module this already has voltage divider internal (NOT need for its own).

| Pin module | Connect to |
|-----------|-----------|
| IN+ | Terminal Battery+ (12V LiFePO4/sejenis) |
| IN− | Terminal Battery− |
| GND (side output) | GND together |
| S (output, 0-5V proporsional 0-25V) | LLC **HV-6** → LV-6 → MCP3008 **CH5** |

Formula konversi exists in `sensors/battery.py`. Calibration `BATTERY_MAX_V` /
`BATTERY_MIN_V` in `.env` according to specification battery You (default 12.6V full,
9.0V empty, cocok for pack 3S LiFePO4).

### RS485 Anemometer (Modbus RTU)
| connection | Connect to |
|---------|-----------|
| A (D+) | USB-RS485 converter terminal A |
| B (D−) | USB-RS485 converter terminal B |
| VCC | 12V or 5V according to datasheet unit |
| GND | GND together |

USB-RS485 → port USB Pi → appear as `/dev/ttyUSB0`. **NOT need LLC.**

### A7670E or SIM7600 (select one)

NOT need wiring different between both — **ONLY pasang one module**,
`communication/sim_detector.py` will auto-detect which that installed
(`AT+CGNSSPWR` → A7670E, `AT+CGPS` → SIM7600) and software adapts its own.

| connection | Details |
|---------|--------|
| Power | According to board HAT (usually 5V from Pi or 3.7-4.2V Li-ion separate) |
| Data | USB to Pi — appear as several `/dev/ttyUSBx` |
| Antenna LTE | Required |
| Antenna GNSS | Required separate |
| SIM card | Pasang before power-on |

```bash
ls /dev/ttyUSB*
python3 tests/test_sim_detector.py   # confirmation module which that detected
```

### Relay 5V → Siren 12V

```
Side control (Pi 3.3V GPIO):          Side power high (12V):
  GPIO27 ──────────────► IN relay       Battery+ ─── relay COM
  5V     ──────────────► VCC relay            Relay NO ─── Siren (+)
  GND    ──────────────► GND relay            Siren (−) ─── Battery−
```

> ⚠️ Route 12V siren **NOT ever** may menyentuh pin Pi anywhere.
> There is no buzzer separate — this one relay handles 2 levels escalation
> (WARNING = pulses slowly, CRITICAL = on continuously), see `alarm/siren.py`.

---

## 6. Diagram Blok Signal Complete

```
MQ-2 AOUT (5V)      ──┐
MQ-135 AOUT (5V)    ──┤
Soil-S AOUT (5V)    ──┤    LLC (1 module, 6 channel used)
Soil-D AOUT (5V)    ──┤    HV1-6 (5V) → LV1-6 (3.3V)
Pressure via R_BURDEN─┤
Battery Sensor OUT  ──┘         │
                                ▼
                     MCP3008 CH0-CH5  (SPI0)
                                │
BME280 (I2C directly) ──────────┤
RS485 Anemometer (USB) ─────────┤
A7670E / SIM7600 (USB) ─────────┤
                                ▼
                       Raspberry Pi 4 — main.py
                       1) read all sensor
                       2) Save to SQLite first (sensor_readings)
                       3) evaluation local → siren (real-time, NOT stored)
                       4) try send to API — failed? enter queue (api_queue)
                       5) check signal again every 2 minutes → auto-flush queue
                                │ GPIO27
                                ▼
                        Relay 5V ──► Siren 12V
```

---

## 7. Supply power Every Beban

| Beban | Voltage | source | Note |
|-------|---------|--------|---------|
| Raspberry Pi 4 | 5V | Buck converter output | Via GPIO pin 2/4 or USB-C |
| MCP3008 VDD/VREF | 3.3V | Pi 3.3V rail | |
| BME280 | 3.3V | Pi 3.3V rail | I2C directly, without LLC |
| LLC LV | 3.3V | Pi 3.3V rail | |
| LLC HV | 5V | Buck converter / Pi 5V rail | |
| MQ-2 / MQ-135 heater | 5V | Buck converter directly | ~150mA each |
| Soil probe ×2 | 5V or 3.3V | According to datasheet probe | |
| Submersible pressure sensor | 12-24V (loop) | **PSU separate**, not from Pi/buck 5V | Loop-powered |
| Module sensor voltage (battery) | Passively, tap from Battery+/− | — | NOT need suplai separate |
| RS485 anemometer | 12V or 5V | According to datasheet unit | |
| A7670E/SIM7600 | 5V or 3.7-4.2V | According to board HAT | |
| Relay coil | 5V | Pi 5V rail | |
| Siren | 12V | Battery (via relay NO/COM) | |

---

## 8. Checklist before Power-On First

```
[ ] SPI active (raspi-config → Interface → SPI)
[ ] I2C active (raspi-config → Interface → I2C)
[ ] Common ground: Pi, MCP3008, LLC, all sensor, relay, PSU pressure sensor → one GND
[ ] LLC: HV=5V, LV=3.3V, 6 channel from sensor connected (CH0-CH5)
[ ] MCP3008 VDD & VREF to 3.3V (not 5V)
[ ] R_BURDEN 250Ω installed correct in loop pressure sensor, tap to LLC HV-5
[ ] PSU loop pressure sensor separate from Pi/buck converter 5V
[ ] Module sensor voltage tap directly to Battery+/− (not through relay)
[ ] Route 12V siren ONLY through relay COM/NO, NOT menyentuh Pi
[ ] ONLY ONE module installed: A7670E or SIM7600 (do not install both)
[ ] Antenna LTE + GNSS installed
[ ] SIM card installed before module powered on

Verify software:
[ ] ls /dev/spidev*    → /dev/spidev0.0 exists
[ ] i2cdetect -y 1     → address BME280 (0x76/0x77) appear
[ ] ls /dev/ttyUSB*    → several port exists (modem + anemometer)
[ ] python3 tests/test_all_sensors.py     → all sensor OK
[ ] python3 tests/test_offline_queue_integrity.py → integrity queue OK
[ ] python3 tests/test_sim_detector.py    → SIM module teridentifikasi
```
