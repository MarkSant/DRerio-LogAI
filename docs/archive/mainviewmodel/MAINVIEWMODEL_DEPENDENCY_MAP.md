# 🗺️ MainViewModel Dependency Map

**Document:** MAINVIEWMODEL_DEPENDENCY_MAP.md
**Version:** 1.0
**Date:** 2025-01-14
**Sprint:** 23 - Análise de Dependências
**Status:** ✅ COMPLETED

---

## 📊 Overview

Este documento mapeia todas as dependências entre os 141 métodos do MainViewModel, identificando:

- **Métodos mais chamados** (alto acoplamento - "dependers")
- **Métodos que mais chamam outros** (alto fan-out - "callers")
- **Cadeias de dependências** críticas
- **Pontos de entrada** principais
- **Métodos isolados** (sem dependências)

**Objetivo:** Guiar a extração de métodos nos Sprints 24-35, identificando onde cortar dependências sem quebrar funcionalidades.

---

## 🎯 Estatísticas Gerais

| Métrica | Valor |
| --------- | ------- |
| **Total de métodos** | 141 |
| **Total de linhas** | 5,227 |
| **Média linhas/método** | 37.1 |
| **Métodos sem dependências** | ~95 métodos |
| **Métodos com dependências** | ~46 métodos |
| **Max dependências (caller)** | 7 métodos (`start_recording`) |
| **Max vezes chamado** | 11 vezes (`_publish_processing_mode`) |

---

## 🔥 Top 30 Métodos Mais Chamados (Alto Acoplamento)

Estes métodos são **críticos** - muitos outros dependem deles. Devem ser extraídos COM CUIDADO.

| # | Método | Chamado por | Categoria | Estratégia |
| --- | -------- | ------------- | ----------- | ------------ |
| 1 | `_publish_processing_mode` | 11× | orchestration_internal | ⚠️ MANTER no MainViewModel (núcleo) |
| 2 | `refresh_project_views` | 9× | ui_method | ✅ Extrair para UIStateController |
| 3 | `update_openvino_status` | 4× | ui_method | ✅ Extrair para UIStateController |
| 4 | `get_all_weight_names` | 4× | query | ✅ Extrair para DetectorOrchestrator |
| 5 | `setup_detector_zones` | 4× | state_management | ✅ Extrair para DetectorOrchestrator |
| 6 | `_finish_progress_dialog` | 4× | utility_internal | ✅ Extrair para UIStateController |
| 7 | `_safe_get_default_weight` | 3× | utility_internal | ✅ Extrair para DetectorOrchestrator |
| 8 | `set_active_weight` | 3× | mutator | ✅ Extrair para DetectorOrchestrator |
| 9 | `convert_active_weight_to_openvino` | 3× | state_management | ✅ Extrair para DetectorOrchestrator |
| 10 | `apply_project_model_overrides` | 3× | state_management | ✅ Extrair para ProjectOrchestrator |
| 11 | `_create_processing_callbacks` | 3× | orchestration_internal | ✅ Extrair para VideoProcessingOrchestrator |
| 12 | `_create_processing_context` | 3× | orchestration_internal | ✅ Extrair para VideoProcessingOrchestrator |
| 13 | `_activate_analysis_view_mode` | 3× | utility_internal | ✅ Extrair para UIStateController |
| 14 | `_handle_validation_error` | 3× | event_handler_internal | ✅ Extrair para ValidationHandler |
| 15 | `_setup_recording_service_callbacks` | 2× | utility_internal | ⚠️ Manter (setup interno) |
| 16 | `_show_cancel_feedback` | 2× | utility_internal | ✅ Extrair para UIStateController |
| 17 | `_schedule_on_ui` | 2× | ui_internal | ⚠️ MANTER no MainViewModel (núcleo) |
| 18 | `_schedule_recording` | 2× | utility_internal | ✅ Extrair para RecordingOrchestrator |
| 19 | `_get_project_data_dict` | 2× | utility_internal | ✅ Extrair para ProjectOrchestrator |
| 20 | `_ensure_project_overrides_record` | 2× | utility_internal | ✅ Extrair para ProjectOrchestrator |
| 21 | `has_project_override_settings` | 2× | query | ✅ Extrair para ProjectOrchestrator |
| 22 | `_persist_project_model_settings` | 2× | utility_internal | ✅ Extrair para ProjectOrchestrator |
| 23 | `_apply_model_settings` | 2× | utility_internal | ✅ Extrair para DetectorOrchestrator |
| 24 | `_clear_external_trigger_wait` | 2× | utility_internal | ✅ Extrair para RecordingOrchestrator |
| 25 | `setup_detector` | 2× | state_management | ✅ Extrair para DetectorOrchestrator |
| 26 | `_prepare_results_directory` | 2× | orchestration_internal | ✅ Extrair para VideoProcessingOrchestrator |
| 27 | `_temporary_single_animal_mode` | 2× | utility_internal | ✅ Extrair para DetectorOrchestrator |
| 28 | `_update_diagnostic_progress` | 2× | ui_internal | ✅ Extrair para UIStateController |
| 29 | `_init_coordinators` | 1× | utility_internal | ⚠️ MANTER (inicialização) |
| 30 | `_init_recording_service` | 1× | utility_internal | ⚠️ MANTER (inicialização) |

### 🔑 Métodos Núcleo (NÃO extrair)

Estes métodos são fundamentais e devem permanecer no MainViewModel:

- `_publish_processing_mode` (11 dependentes)
- `_schedule_on_ui` (2 dependentes)
- `_init_coordinators` (inicialização DI)
- `_init_recording_service` (inicialização)
- `_setup_recording_service_callbacks` (setup interno)

---

## 📡 Top 30 Métodos que Mais Chamam Outros (Alto Fan-out)

Estes métodos têm **alta complexidade de orquestração** - bons candidatos para extração.

| # | Método | Chama | Linhas | Categoria | Prioridade Extração |
| --- | -------- | ------- | -------- | ----------- | --------------------- |
| 1 | `start_recording` | 7 | 66 | orchestration | 🔴 ALTA (Sprint 26) |
| 2 | `start_single_video_processing` | 6 | 153 | orchestration | 🔴 ALTA (Sprint 24) |
| 3 | `start_project_processing_workflow` | 6 | 91 | orchestration | 🔴 ALTA (Sprint 24) |
| 4 | `_diagnostic_processing_thread` | 6 | 52 | orchestration_internal | 🟡 MÉDIA (Sprint 27) |
| 5 | `__init__` | 5 | 280 | utility_internal | ⚠️ NÃO EXTRAIR (DI root) |
| 6 | `process_pending_project_videos` | 5 | 239 | orchestration | 🔴 ALTA (Sprint 24) |
| 7 | `_temporary_single_animal_mode` | 4 | 64 | utility_internal | 🟡 MÉDIA (Sprint 27) |
| 8 | `on_arduino_event` | 3 | 21 | event_handler | 🟢 BAIXA (Sprint 31) |
| 9 | `delete_weight` | 3 | 23 | mutator | 🟢 BAIXA (Sprint 27) |
| 10 | `set_active_weight` | 3 | 26 | mutator | 🟢 BAIXA (Sprint 27) |
| 11 | `copy_global_model_settings_to_project` | 3 | 27 | other | 🟡 MÉDIA (Sprint 27) |
| 12 | `save_current_calibration_to_project` | 3 | 29 | state_management | 🟡 MÉDIA (Sprint 27) |
| 13 | `_publish_processing_mode` | 2 | 18 | orchestration_internal | ⚠️ NÃO EXTRAIR |
| 14 | `add_new_weight` | 2 | 20 | mutator | 🟢 BAIXA |
| 15 | `load_new_weight` | 2 | 38 | state_management | 🟢 BAIXA |
| 16 | `set_openvino_usage` | 2 | 19 | state_management | 🟢 BAIXA |
| 17 | `_persist_project_model_settings` | 2 | 25 | utility_internal | 🟡 MÉDIA |
| 18 | `_apply_model_settings` | 2 | 8 | utility_internal | 🟢 BAIXA |
| 19 | `resolve_project_model_settings` | 2 | 63 | other | 🟡 MÉDIA |
| 20 | `apply_project_model_overrides` | 2 | 31 | state_management | 🟡 MÉDIA |
| 21 | `_finalize_processing` | 2 | 26 | orchestration_internal | 🟡 MÉDIA |
| 22 | `_generate_parquet_summaries_worker` | 2 | 63 | utility_internal | 🟡 MÉDIA |
| 23 | `_process_single_video` | 2 | 47 | orchestration_internal | 🟡 MÉDIA |
| 24 | `_create_processing_callbacks` | 2 | 132 | orchestration_internal | 🔴 ALTA |
| 25 | `run_model_diagnostic` | 2 | 102 | orchestration | 🟡 MÉDIA |
| 26 | `_run_diagnostic_frame_loop` | 2 | 87 | orchestration_internal | 🟡 MÉDIA |
| 27 | `_finish_diagnostic_and_save_report` | 2 | 37 | utility_internal | 🟡 MÉDIA |
| 28 | `_init_coordinators` | 1 | 162 | utility_internal | ⚠️ NÃO EXTRAIR |
| 29 | `bind_events` | 1 | 14 | other | ⚠️ NÃO EXTRAIR |
| 30 | `_on_detector_state_changed` | 1 | 13 | event_handler_internal | ⚠️ NÃO EXTRAIR |

---

## 🔗 Cadeias de Dependências Críticas

### 1. **Video Processing Chain** (Maior cadeia - 239 linhas)

```text
process_pending_project_videos (239 linhas) →
  ├─ _select_eligible_videos (81 linhas)
  ├─ _create_processing_callbacks (132 linhas) →
  │    ├─ _publish_processing_mode (18 linhas)
  │    └─ refresh_project_views (21 linhas)
  ├─ _create_processing_context (19 linhas)
  ├─ _activate_analysis_view_mode (6 linhas)
  └─ _handle_validation_error (49 linhas)
```

**Total:** 565 linhas
**Extração:** Sprint 24 - VideoProcessingOrchestrator
**Risco:** 🔴 ALTO (método muito complexo, C901 warning)

### 2. **Single Video Processing Chain** (153 linhas)

```text
start_single_video_processing (153 linhas) →
  ├─ refresh_project_views (21 linhas)
  ├─ _prepare_results_directory (6 linhas)
  ├─ _create_processing_callbacks (132 linhas)
  ├─ _create_processing_context (19 linhas)
  ├─ _activate_analysis_view_mode (6 linhas)
  └─ _handle_validation_error (49 linhas)
```

**Total:** 386 linhas
**Extração:** Sprint 24 - VideoProcessingOrchestrator
**Risco:** 🟡 MÉDIO

### 3. **Recording Chain** (66 linhas)

```text
start_recording (66 linhas) →
  ├─ _clear_external_trigger_wait (13 linhas)
  ├─ setup_detector_zones (36 linhas)
  ├─ _handle_external_trigger (46 linhas)
  ├─ _schedule_recording (24 linhas)
  ├─ _ensure_zones_before_recording (93 linhas) →
  │    └─ run_live_calibration (99 linhas)
  ├─ setup_detector (16 linhas)
  └─ setup_arduino (10 linhas)
```

**Total:** 403 linhas
**Extração:** Sprint 26 - RecordingSessionOrchestrator
**Risco:** 🔴 ALTO (hardware integration)

### 4. **Detector Configuration Chain** (162 linhas)

```text
_init_coordinators (162 linhas) →
  └─ _inject_or_create (12 linhas)
```

**Total:** 174 linhas
**Extração:** ⚠️ NÃO EXTRAIR (DI root)
**Risco:** ❌ CRÍTICO (quebra DI)

### 5. **Model Settings Chain** (63 linhas)

```text
resolve_project_model_settings (63 linhas) →
  ├─ _safe_get_default_weight (18 linhas)
  └─ get_all_weight_names (7 linhas)

apply_project_model_overrides (31 linhas) →
  ├─ resolve_project_model_settings (63 linhas)
  └─ _apply_model_settings (8 linhas) →
       ├─ set_openvino_usage (19 linhas)
       └─ set_active_weight (26 linhas)
```

**Total:** 235 linhas
**Extração:** Sprint 27 - ProjectOrchestrator
**Risco:** 🟡 MÉDIO

### 6. **Diagnostic Chain** (102 linhas)

```text
run_model_diagnostic (102 linhas) →
  ├─ _publish_processing_mode (18 linhas)
  └─ convert_active_weight_to_openvino (41 linhas)

_diagnostic_processing_thread (52 linhas) →
  ├─ _update_diagnostic_progress (16 linhas)
  ├─ _initialize_diagnostic_yolo_model (36 linhas)
  ├─ _initialize_diagnostic_openvino_model (72 linhas)
  ├─ _run_diagnostic_frame_loop (87 linhas) →
  │    ├─ _finish_progress_dialog (4 linhas)
  │    └─ _update_diagnostic_progress (16 linhas)
  ├─ _finish_progress_dialog (4 linhas)
  └─ _publish_processing_mode (18 linhas)
```

**Total:** 466 linhas
**Extração:** Sprint 27 - DiagnosticOrchestrator
**Risco:** 🟡 MÉDIO

---

## 🏝️ Métodos Isolados (Sem Dependências)

Total: ~95 métodos sem chamadas a outros métodos do MainViewModel.

### Por Categoria

**Orchestration (sem dependências internas):**

- `run` (7 linhas)
- `generate_parquet_summaries` (8 linhas)
- `start_live_camera_analysis` (65 linhas)
- `start_live_camera_analysis_from_config` (148 linhas)
- `start_live_project_session` (63 linhas)
- `generate_report` (6 linhas)

**Query (getters):**

- `get_all_weight_names` (7 linhas)
- `get_global_model_defaults` (10 linhas)
- `get_current_detector_parameters` (13 linhas)
- `get_factory_detector_parameters` (13 linhas)
- `get_calibration_scope_info` (56 linhas)
- `can_remove_project_asset` (17 linhas)

**Mutators:**

- `set_main_arena_polygon` (49 linhas)
- `delete_project_asset` (34 linhas)

**Utilities:**

- `_safe_get_default_weight` (18 linhas)
- `_get_project_data_dict` (6 linhas)
- `_clear_external_trigger_wait` (13 linhas)
- `_tracking_cancelled` (7 linhas)
- E mais ~80 métodos auxiliares

**Estratégia:** Métodos isolados são **mais fáceis de extrair** pois não têm dependências internas. Priorizar extração destes primeiro.

---

## 🔴 Pontos de Atenção (Circular Dependencies)

Nenhuma dependência circular detectada! ✅

**Observação:** A análise AST não encontrou chamadas circulares diretas (A → B → A). No entanto, verificar em runtime se há dependências indiretas através de callbacks ou event bus.

---

## 📋 Dependências Completas por Método (Top 50)

### Orchestration Methods

#### `process_pending_project_videos` (linha 3695, 239 linhas)

**Chama:**

- `_select_eligible_videos`
- `_create_processing_callbacks`
- `_create_processing_context`
- `_activate_analysis_view_mode`
- `_handle_validation_error`

**É chamado por:** Nenhum método interno (ponto de entrada público)

---

#### `start_single_video_processing` (linha 3449, 153 linhas)

**Chama:**

- `refresh_project_views`
- `_prepare_results_directory`
- `_create_processing_callbacks`
- `_create_processing_context`
- `_activate_analysis_view_mode`
- `_handle_validation_error`

**É chamado por:** Nenhum método interno (ponto de entrada público)

---

#### `start_project_processing_workflow` (linha 3603, 91 linhas)

**Chama:**

- `_handle_mixed_data_scenario`
- `_create_processing_callbacks`
- `_create_processing_context`
- `_activate_analysis_view_mode`
- `_handle_validation_error`
- `_validate_zones_with_ui`

**É chamado por:** Nenhum método interno (ponto de entrada público)

---

#### `start_recording` (linha 2638, 66 linhas)

**Chama:**

- `_clear_external_trigger_wait`
- `setup_detector_zones`
- `_handle_external_trigger`
- `_schedule_recording`
- `_ensure_zones_before_recording`
- `setup_detector`
- `setup_arduino`

**É chamado por:**

- `on_arduino_event`

---

#### `run_model_diagnostic` (linha 5122, 102 linhas)

**Chama:**

- `_publish_processing_mode`
- `convert_active_weight_to_openvino`

**É chamado por:** Nenhum método interno (ponto de entrada público)

---

#### `run_aquarium_detection` (linha 2073, 108 linhas)

**Chama:**

- `_publish_processing_mode`

**É chamado por:** Nenhum método interno (ponto de entrada público)

---

#### `run_live_calibration` (linha 2491, 99 linhas)

**Chama:**

- `_publish_processing_mode`

**É chamado por:**

- `_ensure_zones_before_recording`

---

### Orchestration Internal Methods

#### `_create_processing_callbacks` (linha 4936, 132 linhas)

**Chama:**

- `_publish_processing_mode`
- `refresh_project_views`

**É chamado por:**

- `start_single_video_processing`
- `start_project_processing_workflow`
- `process_pending_project_videos`

---

#### `_process_summary_video` (linha 4451, 151 linhas)

**Chama:** Nenhum

**É chamado por:**

- `_generate_parquet_summaries_worker`

---

#### `_diagnostic_processing_thread` (linha 5225, 52 linhas)

**Chama:**

- `_update_diagnostic_progress`
- `_initialize_diagnostic_yolo_model`
- `_initialize_diagnostic_openvino_model`
- `_run_diagnostic_frame_loop`
- `_finish_progress_dialog`
- `_publish_processing_mode`

**É chamado por:** Nenhum método interno (callback thread)

---

### Utility Internal Methods

#### `__init__` (linha 128, 280 linhas)

**Chama:**

- `_safe_get_default_weight`
- `_publish_processing_mode`
- `_init_coordinators`
- `_init_recording_service`
- `_setup_recording_service_callbacks`

**É chamado por:** Constructor (ponto de entrada)

---

#### `_init_coordinators` (linha 422, 162 linhas)

**Chama:**

- `_inject_or_create`

**É chamado por:**

- `__init__`

---

#### `_temporary_single_animal_mode` (linha 4169, 64 linhas)

**Chama:**

- `_resolve_single_animal_mode`
- `_resolve_single_subject_tracker_preference`
- `_configure_single_subject_tracker`
- `_publish_processing_mode`

**É chamado por:**

- `_process_videos`
- `_process_single_video`

---

#### `_ensure_zones_before_recording` (linha 3006, 93 linhas)

**Chama:**

- `run_live_calibration`

**É chamado por:**

- `start_recording`

---

### UI Methods

#### `refresh_project_views` (linha 1102, 21 linhas)

**Chama:**

- `_schedule_on_ui`

**É chamado por:**

- `copy_global_model_settings_to_project`
- `save_current_calibration_to_project`
- `start_single_video_processing`
- `_finalize_processing`
- `_generate_parquet_summaries_worker`
- `_run_analysis_pipeline`
- `_process_single_video`
- `_create_processing_callbacks`
- `_register_project_outputs`

---

#### `update_openvino_status` (linha 1635, 6 linhas)

**Chama:**

- `get_openvino_status`

**É chamado por:**

- `_on_detector_state_changed`
- `set_active_weight`
- `set_openvino_usage`
- `convert_active_weight_to_openvino`

---

### State Management Methods

#### `setup_detector_zones` (linha 1388, 36 linhas)

**Chama:** Nenhum

**É chamado por:**

- `apply_roi_template`
- `update_main_arena`
- `add_roi_polygon`
- `start_recording`

---

#### `apply_project_model_overrides` (linha 1964, 31 linhas)

**Chama:**

- `resolve_project_model_settings`
- `_apply_model_settings`

**É chamado por:**

- `save_current_calibration_to_project`
- `save_project_model_overrides`
- `global_calibration_session`

---

---

## 🎯 Recomendações para Extração

### Prioridade 1: Orchestrators (Sprints 24-27)

**VideoProcessingOrchestrator:**

- `process_pending_project_videos` + cadeia (565 linhas)
- `start_single_video_processing` + cadeia (386 linhas)
- `start_project_processing_workflow` + cadeia (277 linhas)
- `_create_processing_callbacks` (132 linhas)
- `_create_processing_context` (19 linhas)
- `_process_summary_video` (151 linhas)

**Total:** ~1,530 linhas

---

**RecordingSessionOrchestrator:**

- `start_recording` + cadeia (403 linhas)
- `_schedule_recording` (24 linhas)
- `_clear_external_trigger_wait` (13 linhas)
- `_ensure_zones_before_recording` (93 linhas)

**Total:** ~533 linhas

---

**ProjectOrchestrator:**

- `resolve_project_model_settings` + cadeia (235 linhas)
- `apply_project_model_overrides` (31 linhas)
- `_persist_project_model_settings` (25 linhas)
- `_get_project_data_dict` (6 linhas)
- `_ensure_project_overrides_record` (7 linhas)

**Total:** ~304 linhas

---

**DetectorOrchestrator:**

- `setup_detector_zones` (36 linhas)
- `setup_detector` (16 linhas)
- `_apply_model_settings` (8 linhas)
- `set_active_weight` (26 linhas)
- `convert_active_weight_to_openvino` (41 linhas)
- `_temporary_single_animal_mode` (64 linhas)

**Total:** ~191 linhas

---

### Prioridade 2: UI Controllers (Sprints 28-30)

**UIStateController:**

- `refresh_project_views` (21 linhas)
- `update_openvino_status` (6 linhas)
- `_activate_analysis_view_mode` (6 linhas)
- `_finish_progress_dialog` (4 linhas)
- `_show_cancel_feedback` (20 linhas)
- `_update_diagnostic_progress` (16 linhas)
- `_validate_zones_with_ui` (116 linhas)
- `_prepare_processing_ui` (8 linhas)

**Total:** ~197 linhas

---

### Prioridade 3: Event Handlers (Sprints 31-32)

**EventHandlers:**

- `_handle_validation_error` (49 linhas)
- `_handle_mixed_data_scenario` (53 linhas)
- `_handle_external_trigger` (46 linhas)

**Total:** ~148 linhas

---

## 🚨 Métodos a NÃO Extrair

Estes métodos devem **permanecer** no MainViewModel:

1. **DI & Initialization:**
   - `__init__` (280 linhas) - Composition Root
   - `_init_coordinators` (162 linhas) - DI wiring
   - `_inject_or_create` (12 linhas) - DI helper
   - `_init_recording_service` (36 linhas) - Service setup
   - `_setup_recording_service_callbacks` (20 linhas) - Callbacks

2. **Core Orchestration:**
   - `_publish_processing_mode` (18 linhas) - Chamado por 11 métodos
   - `_schedule_on_ui` (8 linhas) - Thread safety critical

3. **Event Binding:**
   - `bind_events` (14 linhas) - Event bus setup
   - `_register_event_handlers` (26 linhas) - Event registration

4. **State Observers:**
   - `_on_project_state_changed` (10 linhas)
   - `_on_detector_state_changed` (13 linhas)
   - `_on_recording_state_changed` (20 linhas)
   - `_on_processing_state_changed` (11 linhas)

5. **Lifecycle:**
   - `run` (7 linhas) - Entry point
   - `on_close` (14 linhas) - Cleanup
   - `join_threads` (19 linhas) - Thread management

**Total a MANTER:** ~670 linhas

---

## 📊 Resumo de Extração Estimada

| Alvo | Linhas | % do Total |
| ------ | -------- | ------------ |
| **VideoProcessingOrchestrator** | ~1,530 | 29.3% |
| **RecordingSessionOrchestrator** | ~533 | 10.2% |
| **ProjectOrchestrator** | ~304 | 5.8% |
| **DetectorOrchestrator** | ~191 | 3.7% |
| **UIStateController** | ~197 | 3.8% |
| **EventHandlers** | ~148 | 2.8% |
| **Métodos menores** | ~1,654 | 31.6% |
| **TOTAL EXTRAÍVEL** | **~4,557** | **87.2%** |
| **MANTER no MainViewModel** | **~670** | **12.8%** |

---

## ✅ Conclusão

- **141 métodos** mapeados com sucesso
- **Dependências identificadas** e categorizadas
- **Nenhuma dependência circular** detectada
- **Cadeias críticas** documentadas
- **Estratégia de extração** definida
- **Métodos núcleo** protegidos

**Próximo Sprint:** Sprint 24 - Extrair VideoProcessingOrchestrator (~1,530 linhas)

---

**Versão:** 1.0
**Última Atualização:** 2025-01-14
**Próxima Revisão:** Após Sprint 24
