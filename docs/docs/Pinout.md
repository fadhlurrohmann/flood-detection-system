# EFWS — Output & Wiring Reference

Final hardware:
**Raspberry Pi 4 · MCP3008 (SPI ADC 8-ch) · 1x Logic Level Converter (min. 6-channel)
· MQ-2 · MQ-135 · BME280 (I2C) · Soil Probe Surface · Soil Probe Deep
· Submersible Pressure Sensor (4-20mA loop) · DC Voltage Sensor Module 0-25V (battery)
· RS485 Anemometer · A7670E OR SIM7600 (auto-detect, only one installed)
· 5V Relay · 12V Siren**

> There is no flame sensor in this hardware. There is no separate buzzer — a
> single relay + siren is enough (2 alarm escalation levels via pulsing vs.
> continuous-on pattern; see `alarm/siren.py`). Thresholds and alarm level
> decisions are evaluated locally ONLY to trigger the siren in real time — they
> are not stored in the local database because the official alarm evaluation occurs
> in the backend.

---

## 1. Raspberry Pi 4 — Pins Used (BCM Numbering)

| Function | GPIO (BCM) | Physical Pin | Notes |
|----------|------------|--------------|-------|
| SPI SCLK (MCP3008) | GPIO11 | Pin 23 | SPI clock |
| SPI MISO (MCP3008) | GPIO9  | Pin 21 | Data from MCP3008 |
| SPI MOSI (MCP3008) | GPIO10 | Pin 19 | Data to MCP3008 |
| SPI CE0  (MCP3008) | GPIO8  | Pin 24 | Chip select |
| I2C SDA (BME280)   | GPIO2  | Pin 3  | I2C data |
| I2C SCL (BME280)   | GPIO3  | Pin 5  | I2C clock |
| Siren Relay (output) | GPIO27 | Pin 13 | To 5V relay IN |
| Status LED (output, optional) | GPIO23 | Pin 16 | Heartbeat indicator |
| 5V Rail | — | Pin 2 & 4 | Power LLC HV (do not use this for high current) |
| 3.3V Rail | — | Pin 1 & 17 | Power LLC LV, MCP3008 VDD/VREF, BME280 |
| GND | — | Pin 6, 9, 14, 20, 25, 30, 34, 39 | Shared ground |

Enable interfaces:
```bash
sudo raspi-config
# Interface Options → SPI → Yes
# Interface Options → I2C → Yes
```

---
## 2. BME280 & Rainfall Sensors — I2C Wiring (ambient: temperature / humidity / pressure)

### BME280 (ambient: suhu / kelembaban / tekanan)
| Pin BME280 | Hubung ke |
|-----------|-----------|
| VIN | Pi 3.3V |
| GND | GND bersama |
| SCL | GPIO3 (Pin 5) |
| SDA | GPIO2 (Pin 3) |

Alamat I2C: `0x76` (atau `0x77` tergantung solder jumper modul).

### DFRobot Gravity Rainfall Sensor (SEN0575) — Tipping Bucket
| Pin sensor | Hubung ke |
|-----------|-----------|
| VCC | Pi 3.3V |
| GND | GND bersama |
| SCL | GPIO3 (Pin 5) — **sama seperti BME280** |
| SDA | GPIO2 (Pin 3) — **sama seperti BME280** |

Alamat I2C: `0x1D` (`RAINFALL_I2C_ADDRESS` di `config/settings.py`) —
**beda dari BME280 (`0x76`/`0x77`)**, jadi wiring paralel di bus I2C yang
sama aman, tidak perlu multiplexer.

```bash
i2cdetect -y 1     # should show 0x76 (or 0x77 if address differs)
python3 tests/test_bme280.py
```

---

## 3. MCP3008 — Wiring to Raspberry Pi

| MCP3008 Pin | Connect To | Notes |
|-------------|------------|-------|
| VDD (pin 16) | Pi 3.3V | **DO NOT USE 5V** |
| VREF (pin 15) | Pi 3.3V | ADC scale 0-3.3V = raw 0-1023 |
| AGND (pin 14) | Common GND | |
| CLK (pin 13)  | GPIO11 (SCLK) | |
| DOUT (pin 12) | GPIO9 (MISO)  | |
| DIN (pin 11)  | GPIO10 (MOSI) | |
| CS/SHDN (pin 10) | GPIO8 (CE0) | |
| DGND (pin 9)  | Common GND | |
| CH0-CH5 | See channel table below | All routed through LLC |
| CH6-CH7 | Spare, not wired | |

Verification: `ls /dev/spidev*` → should show `/dev/spidev0.0`

---

## 4. MCP3008 Channel Map — ONE Logic Level Converter

All 0-5V analog signals **must** pass through the LLC before entering the MCP3008 (VREF 3.3V).
Use a bidirectional LLC module with at least 6 channels (for example, an 8-channel TXS0108E module — more commonly sold and leaves 2 channels for expansion).

| LLC | HV Side (5V) ← from sensor | LV Side (3.3V) → to MCP3008 | Channel |
|-----|---------------------------|------------------------------|---------|
| HV-1 / LV-1 | YF-S201 **AOUT** | NONE | water flow digital |
|manual RESISTOR | Pressure sensor (via **R_BURDEN**) |  **CH1** | Water level (4-20mA loop) | Re
| HV-6 / LV-6 | Voltage Sensor Module **OUT** | **CH2** | Battery voltage (0-25V) |
| HV-7..8 / LV-7..8 | *(spare / expansion)* | CH3-CH7 | — |

### LLC Module Wiring

```
LLC:
  HV  pin  ←── 5V  (from buck converter / Pi pin 2/4)
  LV  pin  ←── 3.3V (from Pi pin 1/17)
  GND HV   ←── common ground
  GND LV   ←── common ground
```

---

## 5. Sensor-by-Sensor Wiring Details

### MQ-2 (Smoke / Combustible Gas)
| Sensor pin | Connect to |
|-----------|------------|
| VCC | 5V (directly from source, not from Pi GPIO 5V) |
| GND | Common ground |
| AOUT | LLC **HV-1** → LV-1 → MCP3008 **CH0** |

> Heater ~150mA — power directly from buck converter, not from Pi GPIO 5V.

### YF-S201 (Water Flow Sensor)
| Sensor pin | Connect to |
|-----------|------------|
| VCC | 5V (directly from source) |
| GND | Common ground |
| AOUT | LLC **HV-1** → LV-1 → MCP3008 |


### Submersible Pressure Sensor — 4-20mA loop (Water Level)

This sensor is a **2-wire loop-powered device** (not a direct 0-5V sensor), so its wiring differs from other sensors: it requires a precise **burden resistor** to convert the loop current into a voltage readable by the ADC.

```
PSU 12-24V (+) ──────────► Sensor Loop V+
                                  │
                    Sensor (variable 4-20mA depending on pressure/depth)
                                  │
                                  ▼
                    ┌─────────────────────────┐
                    │  R_BURDEN = 250Ω 0.1%   │
                    │  (precision, low-drift)  │
                    └────────────┬────────────┘
                                 │ tap here →  0-5V
                                 ▼
                      LLC HV-5 (5V side)
                                 │ level shift
                      LLC LV-5 (3.3V side)
                                 │
                       MCP3008 CH4
                                 │
PSU 12-24V (−) ──────────► common ground (after R_BURDEN)
```

| Point | Connect to |
|-------|------------|
| Loop V+ | PSU 12-24V (+) — **not** from Pi/buck converter 5V |
| Loop output (after sensor) | Top of R_BURDEN (250Ω, 0.1%) |
| Bottom of R_BURDEN | Common ground & PSU (−) |
| Sensor/R_BURDEN connection point | LLC **HV-5** → LV-5 → MCP3008 **CH4** |

**Why 250Ω exactly?**
- 4mA × 250Ω = **1.0V** → "empty" level (0m)
- 20mA × 250Ω = **5.0V** → "full" level (`PRESSURE_RANGE_M`, default 5m — adjust to your sensor datasheet)

The conversion formula is in `sensors/pressure.py`. **Adjust** `EFWS_PRESSURE_RANGE_M`
in `.env` to match the physical sensor depth/pressure range (many variants: 0-5m,
0-10m, 0-20m). The API payload sends two values from this sensor: `waterLevel` (meters)
and `waterLevelCurrentMa` (raw loop current, useful for the backend to detect a loop break — a sudden drop to ~0mA means a broken cable, not empty water).

### DC Voltage Sensor Module 0-25V (Battery)

This module already includes an internal voltage divider (no need to build one yourself).

| Module pin | Connect to |
|------------|------------|
| IN+ | Battery+ terminal (12V LiFePO4 or similar) |
| IN− | Battery− terminal |
| GND (output side) | Common ground |
| S (output, 0-5V proportional to 0-25V) | LLC **HV-6** → LV-6 → MCP3008 **CH5** |

The conversion formula is in `sensors/battery.py`. Calibrate `BATTERY_MAX_V` /
`BATTERY_MIN_V` in `.env` according to your battery specification (default 12.6V full,
9.0V empty, suitable for 3S LiFePO4 packs).

### RS485 Anemometer (Modbus RTU)
| Connection | Connect to |
|-----------|------------|
| A (D+) | USB-RS485 converter terminal A |
| B (D−) | USB-RS485 converter terminal B |
| VCC | 12V or 5V depending on unit datasheet |
| GND | Common ground |

USB-RS485 → Pi USB port → appears as `/dev/ttyUSB0`. **No LLC required.**

### A7670E OR SIM7600 (choose one)

No different wiring is required between them — **install only one module**,
`communication/sim_detector.py` will auto-detect which one is present
(`AT+CGNSSPWR` → A7670E, `AT+CGPS` → SIM7600) and the software adapts automatically.

| Connection | Details |
|-----------|---------|
| Power | Depends on the HAT board (usually 5V from the Pi or separate 3.7-4.2V Li-ion) |
| Data | USB to Pi — appears as one of several `/dev/ttyUSBx` |
| LTE antenna | Required |
| GNSS antenna | Required separately |
| SIM card | Install before power-on |

```bash
ls /dev/ttyUSB*
python3 tests/test_sim_detector.py   # confirm which modem is detected
```

### 5V Relay → 12V Siren

```
Control side (Pi 3.3V GPIO):          High-power side (12V):
  GPIO27 ──────────────► IN relay       Battery+ ─── relay COM
  5V     ──────────────► VCC relay            Relay NO ─── Siren (+)
  GND    ──────────────► GND relay            Siren (−) ─── Battery−
```

> ⚠️ The 12V siren line **must never** touch any Pi pin.
> There is no separate buzzer — this relay handles 2 escalation levels
> (WARNING = slow pulse, CRITICAL = constant on), see `alarm/siren.py`.

---

## 6. Complete Signal Block Diagram

```
MQ-2 AOUT (5V)      ──┐
MQ-135 AOUT (5V)    ──┤
Soil-S AOUT (5V)    ──┤    LLC (1 module, 6 channels used)
Soil-D AOUT (5V)    ──┤    HV1-6 (5V) → LV1-6 (3.3V)
Pressure via R_BURDEN─┤
Battery Sensor OUT  ──┘         │
                                ▼
                     MCP3008 CH0-CH5  (SPI0)
                                │
BME280 (I2C direct) ─────────────┤
RS485 Anemometer (USB) ──────────┤
A7670E / SIM7600 (USB) ──────────┤
                                ▼
                       Raspberry Pi 4 — main.py
                       1) read all sensors
                       2) SAVE to SQLite first (sensor_readings)
                       3) local evaluation → siren (real-time, not stored)
                       4) try to send to API — fail? queue it (api_queue)
                       5) re-check signal every 2 minutes → auto-flush queue
                                │ GPIO27
                                ▼
                        5V Relay ──► 12V Siren
```

---

## 7. Power Supply for Each Load

| Load | Voltage | Source | Notes |
|------|---------|--------|-------|
| Raspberry Pi 4 | 5V | Buck converter output | Via GPIO pins 2/4 or USB-C |
| MCP3008 VDD/VREF | 3.3V | Pi 3.3V rail | |
| BME280 | 3.3V | Pi 3.3V rail | I2C direct, no LLC |
| LLC LV | 3.3V | Pi 3.3V rail | |
| LLC HV | 5V | Buck converter / Pi 5V rail | |
| Submersible pressure sensor | 12-24V (loop) | **Separate PSU**, not from Pi/buck 5V | Loop-powered |
| Voltage sensor module (battery) | Passive, tapped from Battery+/− | — | No separate supply needed |
| RS485 anemometer | 12V or 5V | According to unit datasheet | |
| A7670E/SIM7600 | 5V or 3.7-4.2V | According to HAT board | |
| Relay coil | 5V | Pi 5V rail | |
| Siren | 12V | Battery (via relay NO/COM) | |

---

## 8. Checklist Before First Power-On

```
[ ] SPI enabled (raspi-config → Interface → SPI)
[ ] I2C enabled (raspi-config → Interface → I2C)
[ ] Common ground: Pi, MCP3008, LLC, all sensors, relay, pressure PSU → one GND
[ ] LLC: HV=5V, LV=3.3V, 6 channels connected from sensors (CH0-CH5)
[ ] MCP3008 VDD & VREF to 3.3V (not 5V)
[ ] R_BURDEN 250Ω installed correctly in the pressure sensor loop, tapped to LLC HV-5
[ ] Pressure sensor PSU isolated from Pi/buck converter 5V
[ ] Voltage sensor module taps directly to Battery+/− (not through relay)
[ ] 12V siren path only through relay COM/NO, never touching Pi pins
[ ] Only ONE module installed: A7670E OR SIM7600 (do not install both)
[ ] LTE + GNSS antennas installed
[ ] SIM card installed before turning on the module

Software verification:
[ ] ls /dev/spidev*    → /dev/spidev0.0 present
[ ] i2cdetect -y 1     → BME280 address appears (0x76/0x77)
[ ] ls /dev/ttyUSB*    → multiple ports present (modem + anemometer)
[ ] python3 tests/test_all_sensors.py     → all sensors OK
[ ] python3 tests/test_offline_queue_integrity.py → queue integrity OK
[ ] python3 tests/test_sim_detector.py    → SIM module identified
```
