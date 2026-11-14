# Hardware and firmware

Wire the existing ESP32 DevKit V1 → MAX485 → DMX512 RGB decoder → conventional
RGB strip. Depends on the preserved firmware in `src/`; effects change the whole
strip together. This analog decoder cannot address individual pixels or zones.

- USB serial: 115200 baud, UART0.
- DMX: UART2, 250000 baud, 8N2; TX GPIO17, DE GPIO25, /RE GPIO26.
- Decoder address: 001, RGB channels 1–3. White mixes RGB, without a W wire.
- Use one serial owner; close PlatformIO Serial Monitor while the API runs.

| Command | Result |
| --- | --- |
| `0` | OFF |
| `1` | RED |
| `2` | BLUE |
| `3` | GREEN |
| `4` | WHITE |
| `?` | STATUS |
| `R r g b` + newline | Custom RGB, on extended firmware |

Basic colors are sent directly without any mandatory handshake or firmware
validation. The existing matching `OK` acknowledgment confirms delivery. Before
RGB commands or animations, the API checks STATUS for `protocol=rgb8-v1`. Missing
extension returns `501`, while legacy commands still work. Brightness below 100%
generally needs RGB too. One serial session stays open with DTR/RTS disabled;
USB failures trigger reconnection, without repeated open/close cycles per frame.

No DMX transmission code was changed by the API simplification. If the extension
is not installed, retain a backup of the working image before choosing to flash:

```sh
pio run -e serial_only -e dmx_init -e esp32dev
# Optional, only during your chosen hardware maintenance window:
pio run -e esp32dev -t upload
```

## Manual hardware checklist

Software tests cannot confirm USB reset behavior, electrical DMX or visible colors.

- [ ] Start the API without CABEK AI; confirm red, blue, green, white and OFF.
- [ ] Check a custom RGB color and brightness 0, 50, 100 on RGB firmware.
- [ ] Try all 13 effects; observe finite final colors and repeat until replaced.
- [ ] Compare duration 2000 ms at speed 1 and 2: two seconds and one second.
- [ ] Check a multicolor palette and each easing curve.
- [ ] Replace a running animation with solid red; confirm immediate replacement.
- [ ] Send OFF during a repeating effect; confirm it stops and stays off.
- [ ] Unplug USB during an effect: new commands return 503; reconnect and observe recovery.
- [ ] Send OFF while unplugged, reconnect, and confirm OFF is retried.
- [ ] On legacy firmware, confirm five legacy outputs work and smooth effects return 501.
- [ ] Run CABEK AI: startup → white → red scan pulses → green → white after ten seconds.
- [ ] Begin another capture during green; check that the previous timer cannot overwrite red.
- [ ] Confirm the frontend has no lighting controls or requests to port 8001; refresh/close it during a capture and verify backend lighting continues.

Historical firmware investigations remain in the [journal archive](archive/technical-journal-2026-11.md).
