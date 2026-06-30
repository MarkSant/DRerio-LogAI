# Per-Zone Arduino Commands (Live Projects)

How to make DRerio LogAI send a signal to an Arduino when a tracked animal
**enters** or **leaves** a region of interest (ROI) during a live recording.

## The contract: DRerio transports, the sketch decides

DRerio LogAI is only the **transport**. When an animal enters a ROI it sends one
integer over the serial port; when it leaves it sends another. **What that
integer does — light an LED, fire a relay, deliver a stimulus — lives entirely
in your Arduino sketch.** Using Arduino assumes you know how to program it.

The model is **edge-triggered**: the token is sent once on the transition, not
every frame. Your sketch is expected to hold the resulting state (e.g. keep an
LED on) between the *enter* and *leave* tokens. When recording stops, DRerio
sends every configured *exit* token once, as a "turn everything off" sweep.

## Prerequisites

- A **live** project created with **"Usar Arduino"** enabled in the wizard
  (live configuration step), with the correct serial **port** selected.
- The Arduino connected and flashed with your sketch.
- At least one **ROI** defined in the **"Configuração de Zonas"** tab.

The serial port (and baud rate) is a per-machine setting in
[`config.local.yaml`](../../../config.local.yaml):

```yaml
arduino:
  port: 'COM3'        # your device's port (COM3 on Windows, /dev/ttyACM0 on Linux)
  baud_rate: 9600
  handshake: none     # 'none' = connect as soon as the port opens (default, tolerant)
  ack: none           # 'none' = fire-and-forget; do not wait for an "OK" reply
```

`handshake: none` and `ack: none` are the defaults and match a typical sketch
that neither announces `"Arduino is ready."` on boot nor replies `"OK"` to each
command.

## Configure bindings

1. Open the project and go to the **"Configuração de Zonas"** tab.
2. Define your ROIs as usual.
3. In the **"Comandos Arduino por Zona"** panel (bottom of the left column):
   - Click **🔄 ROIs** to load the ROI names you just defined.
   - Pick a ROI from the **ROI** dropdown.
   - Type the integer to send in **Entrar** (on enter) and/or **Sair** (on exit).
   - Click **Adicionar / Atualizar**. The row appears in the table and is saved.
4. Repeat for each ROI. Use **Remover** / **Limpar** to edit the table.

You only ever *type* the short integer token — everything else is a selection.

## Example: the reference RGB sketch

The bundled `Program_Final.ino` maps integers to LED on/off pairs:

| Token | Effect          | Token | Effect           |
| ----- | --------------- | ----- | ---------------- |
| `1`   | Red LED 1 ON    | `2`   | Red LED 1 OFF    |
| `3`   | Blue LED ON     | `4`   | Blue LED OFF     |
| `5`   | Green LED ON    | `6`   | Green LED OFF    |
| `7`   | Red LED 2 ON    | `8`   | Red LED 2 OFF    |

To light Red LED 1 while a fish is in the ROI named `Direita`, set that ROI's
binding to **Entrar = 1**, **Sair = 2**. The LED turns on when the fish enters,
stays on while it remains, and turns off when it leaves — and the end-of-session
sweep guarantees it is off after recording stops.

## How it works (under the hood)

- Bindings are stored in `project_data["arduino_bindings"]` as a list of
  `{roi, on_enter, on_exit}` (see `core/services/arduino_bindings.py`).
- During the live processing loop, the bbox **centroid** of each detection is
  tested against the detector's scaled ROI polygons
  (`core/services/arduino_roi_evaluator.py`). A ROI counts as occupied while any
  animal is inside it (**any-track** scope).
- Transitions are diffed frame-to-frame
  (`core/services/arduino_event_mapper.py`) and the resulting tokens are queued
  on the `ArduinoManager` writer thread — **fire-and-forget**, so serial I/O
  never stalls frame processing.

## Troubleshooting

- **Panel not visible** — the project is not live, or **"Usar Arduino"** was not
  enabled at creation. A note in the panel explains this.
- **ROI dropdown empty** — define ROIs first, then click **🔄 ROIs**.
- **Nothing happens on the device** — check the port in `config.local.yaml`
  matches the connected Arduino, and that your sketch acts on the integers you
  configured. DRerio logs `arduino.command.sent_async` for every token it sends.
