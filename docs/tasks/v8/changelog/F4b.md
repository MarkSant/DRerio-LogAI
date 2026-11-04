# F4b — window analysis: fragments for F7

Front F4b (`feat/v8-window-analysis`) applies the analysis window of
[ADR-011](../ADR-011-conditions-and-time.md) to the metrics and the reports, and adds the
Barnes end-to-end test. F7 owns `CHANGELOG.md`, `TEST_MAP.md`, `CLAUDE.md` and the locales;
the text below is ready to paste. Every new user-visible string is in `_()` and still needs
its pt_BR msgstr.

## CHANGELOG fragment (under `## [8.0.0]`)

### Added

```markdown
- **Janela de análise aplicada às métricas** (ADR-011). A regra salva em
  `project_data["analysis_window"]` passa a valer em toda análise: relatório individual
  (vídeo padrão e multi-aquário, uma janela por aquário), sumários parquet, pipeline de
  vídeo único/lote, geração de sumários e pós-análise da sessão ao vivo. O recorte é híbrido: validação, suavização,
  velocidade e presença em ROI (com debounce) rodam na gravação inteira e só então as
  métricas leem [START, STOP], com o índice de tempo absoluto preservado.
  - Denominadores passam a ser STOP − START (percentuais, curvas por minuto, inatividade
    %, `percentage_of_recording`); a latência a cada ROI conta a partir do START; quem já
    está dentro no START tem latência 0 (`latency_present_at_start`); quem nunca entra sai
    com o teto = duração da janela e `latency_censored = True`.
  - Episódio de congelamento cortado pela borda é truncado e o `min_duration` vale para o
    que sobra.
  - Início nunca atingido: `on_start_not_met="whole_recording"` analisa a gravação
    inteira com aviso; `"empty"` deixa as métricas da janela vazias.
  - `report["analysis_window"]` completo (status, applied, start/stop com frame e t_s,
    reason, censored, spec_hash, window_duration_s, clock, spec); sem janela continua
    `{"status": "none"}`.
- **`7_AnalysisWindow_<base>.json` reaproveitado.** O START/STOP calculado fica ao lado da
  trajetória e é reaproveitado enquanto a regra e os arquivos de entrada (trajetória,
  `3c_Objetos_`, ROIs) não mudarem; os eventos externos e a seção `online` gravados ao vivo
  são preservados. O `offline` governa a análise; divergência > 1 frame com o `online`
  vira aviso no relatório.
- Sem `3c_Objetos_` (projeto 7.2 ou sidecar desligado) a janela é avaliada só com a
  trajetória (presença do sujeito e ROIs), com aviso; condição sobre classe de contexto
  vira `inputs_missing` em vez de ser lida como "ausente".
- Resumo `.xlsx`: colunas `window_status`, `window_start_s`, `window_stop_s`,
  `window_duration_s`, `window_reason` (sempre presentes, vazias sem janela) e, por ROI,
  `latency_censored_<roi>` e `latency_present_at_start_<roi>` (também na aba
  `por_animal`). Todas no fim, para nenhuma coluna antiga mudar de posição.
- `.docx`: seção "Analysis Window" com o recorte, a regra, o status e a ressalva de censura.
```

### Changed

```markdown
- O log de eventos de ROI do `.docx` mostra o tempo absoluto da gravação (antes contava a
  partir do primeiro evento) e, com janela, uma coluna relativa ao START.
- Com janela, os eixos de tempo dos gráficos começam no START.
- `total_frames_analisados` conta só as linhas dentro da janela quando há recorte.
```

## TEST_MAP lines

```markdown
| `analysis/window_observations.py` | `tests/analysis/test_window_observations.py` (3c heartbeat → observations, report ROI rule, external events, trajectory-only fallback, `missing_inputs`) + `--module window_observations` |
| `analysis/analysis_window_service.py` | `tests/analysis/test_analysis_window_service.py` (reuse by spec/input hashes, offline vs online, external events kept, not-met policies, spec lookup) + `--module analysis_window_service` |
| `analysis/behavior.py` (`restrict_to_window`) | `tests/analysis/test_behavior.py::TestRestrictToWindow` + hypothesis properties + `--module analysis_window_cut` |
| `analysis/roi.py` (`restrict_to_window`, `from_rule`, `presence_timeline`) | `tests/analysis/test_roi_analyzer.py::TestRestrictToWindow*` + `--module analysis_window_cut_roi` |
| `analysis/analysis_service.py` (`window=`) | `tests/analysis/test_analysis_service.py` (window block) + `--module analysis_window_cut_service` |
| `analysis/metrics_cache.py` (window key) | `tests/analysis/test_metrics_cache.py` + `--module metrics_cache_window` |
| `analysis/data_transformer.py` (`window_*`, latency flags) | `tests/analysis/test_data_transformer.py`, `tests/analysis/test_data_transformer_roi_metrics.py` + `--module report_window_columns` |
| `analysis/reporters/word_reporter.py` (window note, event log) | `tests/analysis/reporters/test_word_reporter.py::TestAnalysisWindowSection` + `--module word_report_window` |
| `analysis/visualization_generator.py` (time axes) | `tests/analysis/test_visualization_generator.py::TestWindowTimeAxes` + `--module visualization_window_axes` |
| `analysis/reporters/reporter_context.py` (`window=`) | `tests/analysis/reporters/test_reporter_context.py::TestReporterContextWindow` + `--module reporter_context_window` |
| `coordinators/report_generation_coordinator.py` (window wiring) | `tests/coordinators/test_report_generation_coordinator.py::TestAnalysisWindowWiring` + `--module report_window_wiring` |
| `core/video/analysis_pipeline_runner.py` (window wiring) | `tests/core/video/test_analysis_pipeline_runner.py::TestAnalysisWindowResolution` + `--module pipeline_runner_window` |
| `core/recording/live_analysis_post_processor.py` (window) | `tests/core/recording/test_live_analysis_post_processor.py::TestPostAnalysisWindow` + `--module live_post_analysis_window` |
| Barnes acceptance (ADR-011) | `tests/integration/test_barnes_window_e2e.py` |
```

Mutation blocks added to `scripts/mutation_catalog.yaml` (F7: add them to
`docs/testing/MUTATION_BASELINE.md`): `analysis_window_cut` (5), `analysis_window_cut_roi`
(6), `window_observations` (8), `analysis_window_service` (8), `analysis_window_cut_service`
(5), `metrics_cache_window` (1), `report_window_columns` (4), `word_report_window` (4),
`visualization_window_axes` (2), `reporter_context_window` (1), `report_window_wiring` (3),
`pipeline_runner_window` (1), `live_post_analysis_window` (3). The F1 mutation `video_duration::window-silently-ignored`
targeted the `NotImplementedError` block, which no longer exists; it now targets the line
that fills `report["analysis_window"]`.

## Live post-processor (wired after F5 was merged)

`core/recording/live_analysis_post_processor.py` was wired by F4b once F5 landed
(`_resolve_live_window`, step by step in [F5.md](F5.md), "Window hook: what was done"). It
uses `AnalysisWindowService.resolve(..., clock="capture_perf")` directly because the live
spec comes from `self._analysis_window_raw`, not from the project. A future live path that
starts from the project can use the same entry every other path uses:

```python
from zebtrack.analysis.analysis_window_service import resolve_analysis_window

window = resolve_analysis_window(
    project_data,                # None/{} for live ad hoc: no window, returns None
    trajectory_path,             # the session's 3_CoordMovimento_<base>.parquet
    trajectory_df=df,            # ALREADY re-timed by retime_from_ledger (capture clock)
    rois=rois,                   # same pixel space as df
    aquarium_id=aq_id,           # multi-aquarium: one window per aquarium
    roi_rule=analysis_service.resolve_roi_rule(),
    clock="capture_perf",        # only used when there is no 3c
)
```

- The `7_` artifact F5 writes live must keep `spec_hash` equal to `spec_hash(spec)` and
  record `external_events` and `online`; `resolve()` keeps both when it rewrites `offline`.
- `online` is compared with `offline` frame by frame; > 1 frame apart becomes a report
  warning. `offline` always governs the metrics.
- `resolve_window_spec(project_data, video_entry=None)` is the single spec lookup; it
  raises `InvalidWindowSpecError` (translated) for a spec that does not validate instead of
  silently analysing the whole recording.
- `ROIAnalyzer.from_rule(b_analyzer, rois, rule, mask_source=...)` is how a resolved
  `RoiRuleConfig` becomes an analyzer (the report and `RoiInside` conditions share it).

## Deviations

- ROI time percentages keep the OBSERVED-time denominator (sum of capped `dt` inside the
  window), as before v8, now clipped to [START, STOP]; the row whose interval straddles
  START is re-credited with its part after START only. Behavioural rates use STOP − START.
- `report["analysis_window"]` stays exactly `{"status": "none"}` without a window, so the
  golden (`prerecorded_single_report.json`, owned by F1) does not change.
- Axis labels of the figures stay untranslated English, like every other label there.
- `analysis_window_cut` is split in four blocks (behaviour, ROI, service, cache) because a
  catalogue block has one source file.
