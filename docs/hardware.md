# Hardware

## Components

The current tunnel uses:

- ESP32 DevKit V1
- MAX485 RS485 transceiver
- DMX512 RGB decoder
- Conventional analog RGB LED strip and its separate power supply

The LEDs are mounted **outside** the photography tunnel.

## Connection

```text
Computer ── USB ── ESP32 ── MAX485 ── DMX decoder ── RGB strip
                         UART2      RS485          R / G / B
```

| ESP32 signal | GPIO | Role |
|---|---|---|
| TX (UART2) | `17` | DMX data |
| DE | `25` | RS485 driver enable |
| /RE | `26` | RS485 receiver control |

The ESP32's USB console uses UART0 at **115200 baud**. DMX uses UART2 at **250000 baud, 8N2**. The decoder starts at **DMX address 001**, with RGB on channels 1–3. White is mixed from RGB; the W output is not used.

Ensure compatible power and a common signal reference where required by your actual modules. Do not change wiring while powered.

## ESP32 commands

| Serial input | Result |
|---|---|
| `0` | Off |
| `1` | Red |
| `2` | Blue |
| `3` | Green |
| `4` | White |
| `?` | Firmware status |
| `R 255 100 40` + newline | Custom RGB on extended firmware |

The lighting API sends these commands over USB. Basic colors do not require a status handshake; custom RGB requires the firmware extension.

## Firmware

Build with PlatformIO:

```bash
pio run -e serial_only -e dmx_init -e esp32dev
```

The production target is `esp32dev`. Before replacing working firmware, preserve a backup and confirm the configured upload port in `platformio.ini`.

Flash **only during a planned hardware test**:

```bash
pio run -e esp32dev -t upload
```

The API and Serial Monitor cannot own the USB port at the same time.

## Before accepting physical operation

1. Verify red, blue, green, white and off through the API.
2. On updated firmware, test custom RGB, brightness and smooth effects.
3. Try changing effects rapidly, then stopping one with OFF.
4. Disconnect and reconnect USB and confirm recovery.
5. Test a full CABEK AI scan sequence and observe the real lights.

Automated serial tests do not prove the LEDs or DMX wiring work physically.

The separate NAVIGATE 24V “Magic RGB” strip has not been verified or integrated. Its label does not establish the control IC or protocol. Do not connect it directly to ESP32 GPIO or assume the current analog DMX decoder can address individual zones.
