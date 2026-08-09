# External Trigger Mode (Live Projects)

How to make the **Arduino start the recording** instead of the operator clicking.
Use it when the start of a recording must coincide with an external event — a
stimulus, a gate opening, a button on your own rig, another instrument.

This document covers the **inbound** trigger (Arduino → DRerio: "start now").
For the opposite direction — DRerio → Arduino, lighting an LED when the animal
enters a ROI — see [`arduino-bindings.md`](arduino-bindings.md). The two are
independent and can be used together.

## Do I need this? (short answer: probably not)

**No. The mode is OPT-IN and ships disabled.** If you leave the box unticked
nothing changes: recording starts when you click "Iniciar", exactly as before.
No Arduino is required, nothing blocks, no warning appears.

Ticking **"Usar Arduino"** does **not** enable the trigger either — they are two
separate checkboxes. You can use the Arduino purely for per-zone commands and
keep starting recordings by hand. Unticking "Usar Arduino" clears and disables
the trigger checkbox along with it.

## The contract: your sketch must SPEAK

This is where most setups fail:

> **The reference sketch shipped with this project does NOT work for the
> trigger.** It only *receives* tokens (per-zone commands) — it never *sends*
> anything numeric. Enable the trigger and record with it, and the session will
> wait forever.

DRerio listens on the serial port continuously and interprets **numeric lines**
coming from the device:

| Arduino sends | DRerio does |
| ------------- | ----------- |
| `1` | Starts the armed recording |
| `0` | Stops the running recording (or disarms the wait) |
| any other number | Logged and ignored |
| text (e.g. `Red LED 1 ON`) | Treated as an ACK/message, **never** as a trigger |

That number-vs-text distinction is what separates a trigger from an ACK.
`Serial.println(1)` fires the recording; `Serial.println("1 ON")` does not.

## Minimal sketch

A button on pin 2 that starts the recording when pressed:

```cpp
const int START_BUTTON = 2;
int lastState = HIGH;
unsigned long lastDebounce = 0;
const unsigned long DEBOUNCE_MS = 50;

void setup() {
  // INPUT_PULLUP, never INPUT: a floating pin triggers by itself.
  pinMode(START_BUTTON, INPUT_PULLUP);
  Serial.begin(9600);   // must match arduino.baud_rate
}

void loop() {
  // Never use delay() here — it blocks the serial read for its full duration.
  int state = digitalRead(START_BUTTON);

  if (state != lastState && (millis() - lastDebounce) > DEBOUNCE_MS) {
    lastDebounce = millis();
    if (state == LOW) {          // pressed (pull-up: LOW = closed)
      Serial.println(1);         // bare NUMBER -> DRerio starts recording
    }
    lastState = state;
  }
}
```

To stop from hardware, send `Serial.println(0)` the same way. If you never send
`0`, the recording ends normally at its configured duration.

## Step by step

1. **In the wizard** (step 3, "Configuração de Gravação ao Vivo"):
   - tick **"Usar Arduino para sincronização"** — the port is detected and
     preselected automatically (the app prefers the one that answers the
     handshake and has "Arduino" in its description);
   - click **"Testar"** to confirm the port opens;
   - tick **"Modo de Gatilho Externo (External Trigger)"**.
2. **Finish the wizard** and open the project. The port is opened at load time.
3. **In the Progress grid**, click a subject and then **"▶️ Iniciar"**.
   - Recording does **not** start. The notice
     **"Aguardando sinal externo... (porta COMx)"** appears.
   - Zones are requested BEFORE this wait — the polygon must be ready before we
     sit waiting for a signal.
4. **Fire the trigger.** On receiving `1`, recording begins.

## Port configuration

Per machine, in [`config.local.yaml`](../../../config.local.yaml):

```yaml
arduino:
  port: 'COM3'        # COM3 on Windows, /dev/ttyACM0 on Linux
  baud_rate: 9600     # must match the sketch's Serial.begin()
  handshake: none     # 'none' (default) = connected as soon as the port opens
  ack: none           # 'none' (default) = do not wait for an "OK" reply
```

`handshake: ready_line` requires the sketch to print `Arduino is ready.` on boot.
With the default `none`, opening the port is enough.

## When the recording is REFUSED

With the trigger enabled, DRerio prefers refusing the session over recording at
the wrong moment — an out-of-sync recording is useless data that only surfaces at
analysis time.

| Situation | Message | What to do |
| --------- | ------- | ---------- |
| Trigger on, **"Usar Arduino" off** | "…exige um Arduino configurado" | Enable the Arduino in the project, or turn the trigger off |
| Trigger on, Arduino on, **port not connected** | "…o Arduino não está conectado (porta COMx)" | Check the cable and that no other program holds the port; reopen the project |

The second case is common and quiet: if the cable is loose when you open the
project, a "modo offline" warning appears and the project opens anyway. Without
this refusal the session would arm and wait for a signal that has no way to
arrive.

## Troubleshooting

| Symptom | Likely cause |
| ------- | ------------ |
| Stuck on "Aguardando sinal externo" forever | The sketch is not sending a bare number. `Serial.println("1")` with quotes is text, not a trigger — check in the IDE's Serial Monitor |
| Nothing happens and no notice appears | The trigger is not enabled in the project; check "Config. Avançadas" / the project JSON |
| "Não foi possível conectar" when opening the project | Port held by the Arduino IDE's Serial Monitor — close it (one program per port) |
| Fires on its own, untouched | Button pin declared as `INPUT` instead of `INPUT_PULLUP` — a floating pin oscillates |
| Fires with a long delay | `delay()` inside `loop()`. Use `millis()` |
| DRerio logs the event but does not record | No session armed. The `1` only counts after "▶️ Iniciar"; before that it is logged and ignored |

## References

- [`arduino-bindings.md`](arduino-bindings.md) — the opposite direction (ROI → device)
- [`system_integration.md`](../../reference/system_integration.md) § 5.11 — gate architecture
- `scripts/ard_sketch/Program_Final/Program_Final.ino` — reference sketch for
  per-zone commands (**does not** implement the trigger; use it as a base and add
  the `Serial.println(1)` shown above)
