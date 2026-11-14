# Effects

The existing DMX decoder controls the **entire RGB strip as one light**. These effects vary its color and brightness over time; they do not animate individual LEDs.

## Available effects

| Effect | Behavior | Final output when not repeating |
|---|---|---|
| `solid` | Hold one color | Selected color |
| `fade_in` | Gradually brighten | Selected color |
| `fade_out` | Gradually dim | Off |
| `breathing` | Smooth bright/dark cycle | Off |
| `pulse` | Short pulse with a dark interval | Off |
| `transition` | Move between colors | Last color |
| `color_cycle` | Cycle through a custom palette | First palette color |
| `cyber_morph` | Blue, cyan and purple | Blue, or first custom color |
| `system_awakening` | Increasing blue startup pulses | Blue |
| `target_lock` | White → orange → red | Red |
| `mission_complete` | Green success pulse | Green |
| `warning` | Amber warning pulse | Off |
| `shutdown` | Fade through dim blue | Off |

## Customization

- **Color:** use `color: "#RRGGBB"` for color-based effects.
- **Brightness:** `0` to `100`, applied to the final output.
- **Speed:** `1` is normal, `2` is twice as fast, `0.5` is half-speed.
- **Repeat:** `true` keeps cycling; `false` stops at the effect's final frame.
- **Duration:** `duration_ms` is a complete cycle at normal speed.
- **Palette:** `colors` is for `transition`, `color_cycle` and `cyber_morph`.
- **Easing:** controls how color or brightness moves between keyframes.

Example:

```json
{
  "effect": "transition",
  "colors": ["#FFFFFF", "#FF6600", "#FF0000"],
  "duration_ms": 1800,
  "speed": 1,
  "easing": "ease_in_out"
}
```

Send it to `POST /api/lights/set`. A new SET replaces it; `POST /api/lights/off` stops it.

## Firmware requirements

The ESP32's five legacy full-strength colors can work without the RGB extension. Smooth animations and most custom brightness/color settings require firmware supporting `R r g b` and `protocol=rgb8-v1`.

Addressable effects such as a running light across physical LED zones are **not implemented** for the current decoder.

See [Hardware](hardware.md) and [API](api.md).
