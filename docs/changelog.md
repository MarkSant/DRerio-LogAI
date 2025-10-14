# Changelog

## 2025-10-14

### Documentation

- README e wiki atualizados com fluxo do wizard padrão v1.6+, sistema de templates de ROI, overlays avançados e editor de configurações in-app.
- `docs/PROJECT_WORKFLOW.md`, `docs/REFERENCE_GUIDE.md` e `docs/WIZARD_USER_GUIDE.md` revisados para remover referências a arquivos inexistentes e refletir o comportamento atual (clamping de ROI, templates e avanços no overlay).
- Wiki offline (`docs/wiki/*.md`) reescrita com instruções de instalação via Poetry, tutorial completo baseado no wizard e FAQ com recursos recentes.
- `docs/ZONE_PANEL_WIDTH_FIX.md` ajustado para referenciar somente documentação ativa.

### Removed

- Documentos redundantes no diretório raiz (`BUTTON_POSITION_FIX.md`, `BUTTON_REPOSITION_SUMMARY.md`, `EDIT_MODE_CLAMP_UPDATE.md`, `SNAP_INDICATOR_CLAMP_SUMMARY.md`, `TEMPLATE_FIX_SUMMARY.md`, `COMMIT_MESSAGE.md`, `COMMIT_SUMMARY.md`) foram consolidados no changelog e na documentação principal.
- Referências a `docs/WIZARD_INTEGRATION.md` e `docs/WIZARD_PROJECT_CREATION.md`, que não existiam no repositório, foram substituídas por links válidos.

### Testing

- Mudanças documentais; nenhuma alteração funcional. Mantido o status da suíte automatizada mais recente.

## 2025-10-13

### Added (2025-10-13)

- Indicador de modo de processamento na interface principal com bloqueio automático do seletor de trilhas quando o rastreamento está em modo de indivíduo único.
- Publicação de `ProcessingReport` pelo `AppController`, propagando o modo ativo para overlays, calibração e diagnósticos.

### Changed (2025-10-13)

- Fluxos de calibração e diagnóstico agora forçam o modo de rastreamento single subject para evitar ByteTrack durante operações auxiliares.
- Documentação (README e REFERENCE_GUIDE) atualizada para refletir o novo comportamento do modo de processamento.

### Tests (2025-10-13)

- `poetry run pytest -q`
- `poetry run ruff check`

## 2025-10-09 (Phase 8 & 9)

### Added (Phase 8 & 9)

- Curated baseline wizard templates (`resources/wizard_templates/*.json`) now ship with the repo and are zipped automatically during CI.
- Introduced Portuguese (`pt_BR`) translation catalog for reporter outputs with automated compilation via `scripts/compile_translations.py`.
- Added manual verification helpers under `tests/manual/` covering wizard flows, analysis profile matrices, and ROI template round-trips.
- Established a pre-release QA checklist documented in the README and referenced across flow guides.

### Changed (Phase 8 & 9)

- README, project workflow guide, wizard guide, and reference guide refreshed to describe the advanced configuration tab and release automation steps.
- CI workflow now packages wizard templates and compiles gettext catalogs before running lint/tests.

### Tests (Phase 8 & 9)

- CI executes `poetry run python scripts/build_templates.py`, `poetry run python scripts/compile_translations.py`, `poetry run ruff check`, and full pytest as part of the release gate.

## 2025-10-09

### Added (2025-10-09)

- Introduced the UI event bus infrastructure (`ui/event_bus.py`) behind the `settings.ui_features.enable_event_queue` feature flag.
- Application controller now publishes UI work through the event bus when enabled, and the main Tkinter view drains the queue using `root.after`.
- Added automated regression coverage ensuring event bus publishing is wired in `AppController`.
- Reporter now uses gettext-driven translations with docx template support, falling back to the legacy builder when templates are unavailable.
- Declared the `docxtpl` dependency to ship the templated reporting workflow.
- Wizard step 2 now includes an inline folder tree preview with summary counts for quick validation.
- Custom regex dialog ships with a live preview table and inline error feedback while editing patterns.

### Changed (2025-10-09)

- `ApplicationGUI` accepts an optional `event_bus` and schedules polling hooks, logging dispatch metrics via `structlog`.
- Updated architecture guide to reference the opt-in event bus deployment path.
- Confirmation summary surfaces the folder preview highlights and persists the preview structure in wizard metadata.

### Tests (2025-10-09)

- Extended `tests/test_controller.py` with event bus flow checks.
- Added focused reporter regression tests to validate the templated export path.
- Existing CI lint/test workflow already asserts `poetry run ruff check` and full pytest; no pipeline changes required.
- Added wizard file selection, adapter, and confirmation tests covering the new preview and live regex flows.
