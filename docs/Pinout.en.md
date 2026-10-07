# EFWS — out & Wiring Reference

Final hardware:
**Raspberry Pi 4 · MCP3008 (8-ch SPI ADC) · 1x Logic Level Converter (min. 6-channel)
·  BME280 (I2C) · Submersible Pressure Sensor (4-20mA loop) · DC Voltage Sensor Module 0-25V (battery)
· RS485 Anemometer · A7670E OR SIM7600 (auto-detected, only one is installed)
· 5V Relay · 12V Siren**

> There is no flame sensor in this hardware. There is no separate buzzer — just
> one relay + siren (2 escalation levels via a pulsing vs. steady-on pattern,
> see `alarm/siren.py`). Thresholds & alarm-level decisions are evaluated locally
> ONLY to drive the siren in real time — they are not stored in the local database,
> because the "official" alarm evaluation happens in the backend.

---

## 1. Raspberry Pi 4 — Pins Used (BCM Numbering)

| Function | GPIO (BCM) | Physical Pin | Notes |
|--------|-----------|-----------|------------|
| SPI SCLK (MCP3008) | GPIO11 | Pin 23 | SPI clock |
| SPI MISO (MCP3008) | GPIO9  | Pin 21 | Data from MCP3008 |
| SPI MOSI (MCP3008) | GPIO10 | Pin 19 | Data to MCP3008 |
| SPI CE0  (MCP3008) | GPIO8  | Pin 24 | Chip Select |
| I2C SDA (BME280)   | GPIO2  | Pin 3  | I2C data |
| I2C SCL (BME280)   | GPIO3  | Pin 5  | I2C clock |
| Siren Relay (output) | GPIO27 | Pin 13 | To 5V relay IN |
| Status LED (output, optional) | GPIO23 | Pin 16 | Heartbeat indicator |
| 5V Rail | — | Pin 2 & 4 | Powers LLC HV (don't draw from here for high current) |
| 3.3V Rail | — | Pin 1 & 17 | Powers LLC LV, MCP3008 VDD/VREF, BME280 |
| GND | — | Pin 6, 9, 14, 20, 25, 30, 34, 39 | Common ground |

Enable the interfaces:
```bash
sudo raspi-config
# Interface Options → SPI → Yes
# Interface Options → I2C → Yes
```

---

## 2. BME280 — I2C Wiring (ambient: temperature / humidity / pressure)

| BME280 Pin | Connect to |
|-----------|-----------|
| VIN | Pi 3.3V |
| GND | Common GND |
| SCL | GPIO3 (Pin 5) |
| SDA | GPIO2 (Pin 3) |

The BME280 does **not** go through the MCP3008/LLC — this module is native I2C, wired directly to the Pi.

```bash
i2cdetect -y 1     # should show 0x76 (or 0x77 if the address differs)
python3 tests/test_bme280.py
```

---

## 3. MCP3008 — Wiring to the Raspberry Pi

| MCP3008 Pin | Connect to | Notes |
|-------------|-----------|---------|
| VDD (pin 16) | Pi 3.3V | **DO NOT use 5V** |
| VREF (pin 15) | Pi 3.3V | ADC scale 0-3.3V = raw 0-1023 |
| AGND (pin 14) | Common GND | |
| CLK (pin 13)  | GPIO11 (SCLK) | |
| DOUT (pin 12) | GPIO9 (MISO)  | |
| DIN (pin 11)  | GPIO10 (MOSI) | |
| CS/SHDN (pin 10) | GPIO8 (CE0) | |
| DGND (pin 9)  | Common GND | |
| CH0-CH5 | See the channel table below | All go through the LLC |
| CH6-CH7 | Spare, not wired | |

Verify: `ls /dev/spidev*` → `/dev/spidev0.0` should appear

---

## 4. MCP3008 Channel Map — ONE Logic Level Converter

All 0-5V analog signals **must** pass through the LLC before entering the MCP3008 (VREF 3.3V).
Use a bidirectional LLC module with at least 6 channels (e.g. an 8-channel TXS0108E module —
more commonly sold, and it leaves 2 channels free for expansion).

| LLC | HV side (5V) ← from sensor | LV side (3.3V) → to MCP3008 | Channel |
|-----|---------------------------|------------------------------|---------|
| HV-1 / LV-1 | YF-S201 **AOUT** | NONE | water flow digital |
| HV-5 / LV-5 | Pressure sensor (via **R_BURDEN**) | **CH4** | Water level (4-20mA loop) |
| HV-6 / LV-6 | Voltage Sensor Module **OUT** | **CH5** | Battery voltage (0-25V) |
| HV-7..8 / LV-7..8 | *(spare / expansion)* | CH6-CH7 | — |

### LLC module wiring

```
LLC:
  HV  pin  ←── 5V  (from buck converter / Pi pin 2/4)
  LV  pin  ←── 3.3V (from Pi pin 1/17)
  GND HV   ←── Common GND
  GND LV   ←── Common GND
```

---

## 5. Sensor by Sensor — Wiring Details

> Heater draws ~150mA — power it directly from the buck converter, not from the Pi GPIO 5V.

### YF-S201 (Water flow sensor)
| Sensor pin | Connect to |
|-----------|-----------|
| VCC | 5V (directly from the supply) |
| GND | Common GND |
| AOUT | LLC **HV-1** → LV-1 → MCP3008 |


> Per-probe calibration is required (see `sensors/soil.py`): dry_raw in dry air, wet_raw submerged in water.

### Submersible Pressure Sensor — 4-20mA loop (Water Level)

This sensor is **2-wire loop-powered** (not a direct 0-5V output), so its wiring differs
from the other sensors: it needs a precision **burden resistor** to convert the loop
current into a voltage the ADC can read.

```
PSU 12-24V (+) ──────────► Sensor Loop V+
                                  │
                    Sensor (4-20mA, varies with pressure/depth)
                                  │
                                  ▼
                    ┌─────────────────────────┐
                    │  R_BURDEN = 250Ω 0.1%   │
                    │  (precision, low-drift) │
                    └────────────┬────────────┘
                                 │ tap at this point →  0-5V
                                 ▼
                      LLC HV-5 (5V side)
                                 │ level shift
                      LLC LV-5 (3.3V side)
                                 │
                       MCP3008 CH4
                                 │
PSU 12-24V (−) ──────────► Common GND (after R_BURDEN)
```

| Point | Connect to |
|-------|-----------|
| Loop V+ | PSU 12-24V (+) — **not** from the Pi/5V buck converter |
| Loop return (after the sensor) | Top end of R_BURDEN (250Ω, 0.1%) |
| Bottom end of R_BURDEN | Common GND & PSU (−) |
| Sensor/R_BURDEN junction | LLC **HV-5** → LV-5 → MCP3008 **CH4** |

**Why exactly 250Ω?**
- 4mA × 250Ω = **1.0V** → "empty" level (0m)
- 20mA × 250Ω = **5.0V** → "full" level (`PRESSURE_RANGE_M`, default 5m — adjust to your sensor's datasheet)

The conversion formula is in `sensors/pressure.py`. **Adjust** `EFWS_PRESSURE_RANGE_M`
in `.env` to match the depth/pressure range of your physical sensor (there are many variants: 0-5m,
0-10m, 0-20m). The API payload sends two values from this sensor: `waterLevel` (meters)
and `waterLevelCurrentMa` (raw loop current, useful for the backend to detect a broken
loop — a sudden drop to ~0mA means a cut wire, not empty water).

### DC Voltage Sensor Module 0-25V (Battery)

This module already has a built-in voltage divider (no need to build your own).

| Module pin | Connect to |
|-----------|-----------|
| IN+ | Battery+ terminal (12V LiFePO4 or similar) |
| IN− | Battery− terminal |
| GND (output side) | Common GND |
| S (output, 0-5V proportional to 0-25V) | LLC **HV-6** → LV-6 → MCP3008 **CH5** |

The conversion formula is in `sensors/battery.py`. Calibrate `BATTERY_MAX_V` /
`BATTERY_MIN_V` in `.env` to match your battery's specifications (default 12.6V full,
9.0V empty, suitable for a 3S LiFePO4 pack).

### RS485 Anemometer (Modbus RTU)
| Connection | Connect to |
|---------|-----------|
| A (D+) | USB-RS485 converter terminal A |
| B (D−) | USB-RS485 converter terminal B |
| VCC | 12V or 5V per the unit's datasheet |
| GND | Common GND |

USB-RS485 → Pi USB port → appears as `/dev/ttyUSB0`. **No LLC needed.**

### A7670E OR SIM7600 (choose one)

The wiring is the same for both — **install only one module**;
`communication/sim_detector.py` will auto-detect which one is installed
(`AT+CGNSSPWR` → A7670E, `AT+CGPS` → SIM7600) and the software adapts on its own.

| Connection | Details |
|---------|--------|
| Power | Per the HAT board (usually 5V from the Pi or a separate 3.7-4.2V Li-ion) |
| Data | USB to the Pi — appears as several `/dev/ttyUSBx` |
| LTE antenna | Required |
| GNSS antenna | Required, separate |
| SIM card | Insert before power-on |

```bash
ls /dev/ttyUSB*
python3 tests/test_sim_detector.py   # confirm which module was detected
```

### 5V Relay → 12V Siren

```
Control side (Pi 3.3V GPIO):          High-power side (12V):
  GPIO27 ──────────────► relay IN       Battery+ ─── relay COM
  5V     ──────────────► relay VCC            Relay NO ─── Siren (+)
  GND    ──────────────► relay GND            Siren (−) ─── Battery−
```

> ⚠️ The 12V siren line must **never** touch any Pi pin.
> There is no separate buzzer — this single relay handles 2 escalation levels
> (WARNING = slow pulsing, CRITICAL = steady on), see `alarm/siren.py`.

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
BME280 (direct I2C) ────────────┤
RS485 Anemometer (USB) ─────────┤
A7670E / SIM7600 (USB) ─────────┤
                                ▼
                       Raspberry Pi 4 — main.py
                       1) read all sensors
                       2) SAVE to SQLite first (sensor_readings)
                       3) local evaluation → siren (real-time, not stored)
                       4) try sending to the API — failed? goes into the queue (api_queue)
                       5) re-check signal every 2 minutes → auto-flush the queue
                                │ GPIO27
                                ▼
                        5V Relay ──► 12V Siren
```

---

## 7. Power Supply per Load

| Load | Voltage | Source | Notes |
|-------|---------|--------|---------|
| Raspberry Pi 4 | 5V | Buck converter output | Via GPIO pin 2/4 or USB-C |
| MCP3008 VDD/VREF | 3.3V | Pi 3.3V rail | |
| BME280 | 3.3V | Pi 3.3V rail | Direct I2C, no LLC |
| LLC LV | 3.3V | Pi 3.3V rail | |
| LLC HV | 5V | Buck converter / Pi 5V rail | |
| MQ-2 / MQ-135 heater | 5V | Buck converter directly | ~150mA each |
| Soil probe ×2 | 5V or 3.3V | Per the probe's datasheet | |
| Submersible pressure sensor | 12-24V (loop) | **Separate PSU**, not from the Pi/5V buck | Loop-powered |
| Voltage sensor module (battery) | Passive, tapped from Battery+/− | — | No separate supply needed |
| RS485 anemometer | 12V or 5V | Per the unit's datasheet | |
| A7670E/SIM7600 | 5V or 3.7-4.2V | Per the HAT board | |
| Relay coil | 5V | Pi 5V rail | |
| Siren | 12V | Battery (via relay NO/COM) | |

---

## 8. Checklist Before First Power-On

```
[ ] SPI enabled (raspi-config → Interface → SPI)
[ ] I2C enabled (raspi-config → Interface → I2C)
[ ] Common ground: Pi, MCP3008, LLC, all sensors, relay, pressure sensor PSU → one GND
[ ] LLC: HV=5V, LV=3.3V, 6 sensor channels connected (CH0-CH5)
[ ] MCP3008 VDD & VREF to 3.3V (not 5V)
[ ] 250Ω R_BURDEN correctly installed in the pressure sensor loop, tapped to LLC HV-5
[ ] Pressure sensor loop PSU separate from the Pi/5V buck converter
[ ] Voltage sensor module tapped directly to Battery+/− (not through the relay)
[ ] 12V siren line runs only through relay COM/NO, never touches the Pi
[ ] Only ONE module installed: A7670E OR SIM7600 (not both)
[ ] LTE + GNSS antennas attached
[ ] SIM card inserted before the module is powered on

Software verification:
[ ] ls /dev/spidev*    → /dev/spidev0.0 exists
[ ] i2cdetect -y 1     → BME280 address (0x76/0x77) appears
[ ] ls /dev/ttyUSB*    → several ports present (modem + anemometer)
[ ] python3 tests/test_all_sensors.py     → all sensors OK
[ ] python3 tests/test_offline_queue_integrity.py → queue integrity OK
[ ] python3 tests/test_sim_detector.py    → SIM module identified
```
