# F4a — conditions-core: fragments for F7

Front F4a (`feat/v8-conditions-core`) adds the pure condition engine of
[ADR-011](../ADR-011-conditions-and-time.md). Nothing in the app calls it yet:
F4b wires it into the analysis and F5 into the live pipeline. F7 owns
`CHANGELOG.md` and `TEST_MAP.md`; the text below is ready to paste.

## CHANGELOG fragment (under `## [8.0.0]` → `### Added`)

```markdown
- **Motor de condições de início e fim da análise** (`core/conditions/`, ADR-011).
  Uma `WindowSpec` declara quando a análise COMEÇA e quando TERMINA, com nós de
  nível (`ClassPresence` por classe ou papel, `RoiInside`, `Not`, `AllOfLevel`,
  `AnyOfLevel`) e de gatilho (`Persist`, `RoiEdge`, `TimeReached`,
  `FrameReached`, `Delay`, `External`, `EndOfStream`, `FirstOf`, `AllOf`,
  `Sequence`). A persistência é medida no relógio do evento (PTS no
  pré-gravado, captura no ao vivo) e o evento é datado no PRIMEIRO frame da
  sequência válida. Um único avaliador serve ao vivo (`step` por frame) e à
  análise (`evaluate_window`, a mesma dobra), então os dois não divergem sobre a
  mesma entrada. Início nunca atingido vira `start_not_met`; fim nunca atingido
  vira `end_of_stream` com `censored=True`. A janela aplicada fica registrada em
  `7_AnalysisWindow_<base>.json` ao lado da trajetória, com escrita atômica.
```

## TEST_MAP lines

Layer mapping table, new row (after `src/zebtrack/core/services/`):

```markdown
| `src/zebtrack/core/conditions/`       | 3     | `tests/core/conditions/test_*.py`               | 3     |
```

High-traffic quick lookup, new row:

```markdown
| `core/conditions/*.py` | `tests/core/conditions/` (unit + Barnes VFR + hypothesis properties: batch ≡ online, back-dating, STOP ≥ START, duplicates) |
```

Mutation blocks added to `scripts/mutation_catalog.yaml`: `conditions_model`,
`conditions_evaluator`, `conditions_artifact` (5 mutations each). F7 should add
them to `docs/testing/MUTATION_BASELINE.md`.

## Contract notes for F4b / F5

- `WindowEvent` carries `confirmed_frame`/`confirmed_t_s` besides the
  back-dated `frame`/`t_s`: live acts at the confirmation, analysis cuts at the
  instant.
- `WindowResult.status` is `"pending"` while a live evaluator is still running;
  `OfflineWindow.from_result` refuses a pending result.
- STOP only sees observations strictly later than START's confirmation, so one
  external press never both starts and stops a window.
- `External` fires on the observation that delivers the event (its `frame` and
  `t_s`); the event's own `t_s` is preserved in `external_events` of the
  artifact.
- `TimeReached(clock="wall")` is wall time elapsed since the first observation
  that carried `t_wall`.
- The artifact stores the engine reason token (`"delay"`), not the ADR example's
  `"max_duration"`.
- `read_artifact` also rejects a file whose `spec_hash` no longer matches its
  `spec` (hand-edited), so it is recomputed.
- Multi-aquarium path: `<results>/aquarium_{id+1}/7_AnalysisWindow_<base>_aquarium_{id+1}.json`,
  the recorder's layout.
