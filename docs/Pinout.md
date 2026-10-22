# Current sensor wiring reference

These are the software defaults. Confirm the installed sensor model, labels, and wiring before powering hardware. BCM numbers below differ from physical header pin numbers.

| Signal | BCM | Physical pin |
|---|---|---|
| MCP3008 SCLK | 11 | 23 |
| MCP3008 MISO/DOUT | 9 | 21 |
| MCP3008 MOSI/DIN | 10 | 19 |
| MCP3008 CE0/CS | 8 | 24 |
| SEN0575 SDA | 2 | 3 |
| SEN0575 SCL | 3 | 5 |
| JSN-SR04T TRIG | 22 | 15 |
| JSN-SR04T ECHO, reduced to 3.3 V | 18 | 12 |
| YF-S201 pulse, reduced to 3.3 V | 16 | 36 |
| Siren relay IN | 27 | 13 |

Pi GPIO signals and MCP3008 channel inputs must stay within 0–3.3 V. The nominal 0–25 V label on a voltage divider module does not make its output safe for a Pi ADC at the full advertised input range. Measure the divider output at the highest expected battery voltage. Use suitable level conversion for 5 V digital signals; do not pass analog pressure/voltage signals through a BSS138 digital level converter.

## MCP3008 and analog sensors

Power MCP3008 VDD and VREF from 3.3 V; connect AGND and DGND to common ground. SPI0/CE0 defaults to `/dev/spidev0.0`.

- Pressure: CH0, configured 4–20 mA across a 100 ohm burden gives 0.4–2.0 V. Connect the loop-return/burden junction to CH0; the other end of the burden goes to common ground. The loop supply and voltage must match the physical sensor datasheet. Do not connect its supply directly to the ADC. Set `EFWS_PRESSURE_RANGE_M`, burden resistance, and ADC reference to match measured hardware.
- Battery: divider output S to CH3, divider ground to common ground; battery terminals feed the divider input. Default ratio is 5.0. Calibrate with a multimeter. CH2 is marked damaged in the existing project notes and remains unused.

## Rainfall and ultrasonic/flow

SEN0575 uses the existing project's 3.3 V I2C connection, bus 1, address 0x1D, SDA BCM2 and SCL BCM3. Verify your board's supply specification. The runtime validates PID/VID and selects a one-hour window before reading. `i2cdetect -y 1` should show `1d`.

JSN-SR04T must be in trigger/echo mode for this driver. Supply it according to the exact board specification and reduce any 5 V ECHO output before BCM18. Set `EFWS_ULTRASONIC_MOUNT_HEIGHT_M` only after measuring its height above the water-depth zero datum. No echo produces null, never a synthetic flood distance.

YF-S201 uses BCM16 and counts pulses continuously. Supply and pulse output depend on the actual unit; keep the Pi input at 3.3 V. Default calibration is 450 pulses/litre. Calibrate against a measured volume and set `EFWS_FLOW_PULSES_PER_LITER`.

## Relay and siren

The default relay control is active LOW on BCM27. Verify that the relay input accepts 3.3 V logic and cannot drive 5 V back into GPIO. The 12 V siren needs a correctly rated separate supply, fuse, and relay contacts; use COM/NO so it is off when the relay is deenergized. Never power a siren from a GPIO pin. Relay supply, contact rating, siren current, and the physical wiring have not been verified by software tests.

BME280 is not currently installed. Soil and wind are not wired or loaded by the current runtime. GPS/cellular modem setup remains in [the modem guide](Setup-SIM7600E%20%26%20SIM7670.md).
