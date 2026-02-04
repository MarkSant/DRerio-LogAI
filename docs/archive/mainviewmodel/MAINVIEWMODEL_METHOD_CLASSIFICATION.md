# 📂 MainViewModel Method Classification

**Document:** MAINVIEWMODEL_METHOD_CLASSIFICATION.md
**Version:** 1.0
**Date:** 2025-01-14
**Sprint:** 23 - Análise de Dependências
**Status:** ✅ COMPLETED

---

## 📊 Overview

Este documento classifica todos os 141 métodos do MainViewModel em **12 categorias funcionais**, facilitando a identificação de responsabilidades e guiando a extração para orchestrators especializados nos Sprints 24-35.

**Categorias:**

1. **Orchestration** - Workflows públicos de alto nível
2. **Orchestration Internal** - Helpers de orquestração privados
3. **Utility Internal** - Utilitários e helpers privados
4. **State Management** - Gerenciamento de estado e configuração
5. **UI Method** - Métodos de atualização de UI
6. **UI Internal** - Helpers de UI privados
7. **Event Handler** - Handlers de eventos públicos
8. **Event Handler Internal** - Handlers de eventos privados
9. **Query** - Getters e consultas (read-only)
10. **Mutator** - Setters e mutações (write)
11. **Property** - Properties Python (@property)
12. **Other** - Miscelânea não categorizada

---

## 📈 Estatísticas por Categoria

| Categoria | Métodos | Linhas | % Total | Avg Linhas/Método | Destino Extração |
| ----------- | --------- | -------- | --------- | ------------------- | ------------------ |
| **Utility Internal** | 38 | 1,550 | 29.7% | 40.8 | Vários Orchestrators |
| **Orchestration** | 15 | 1,225 | 23.4% | 81.7 | VideoProcessing, Recording |
| **Orchestration Internal** | 15 | 713 | 13.6% | 47.5 | VideoProcessing, Analysis |
| **State Management** | 15 | 434 | 8.3% | 28.9 | Project, Detector |
| **Event Handler Internal** | 13 | 332 | 6.4% | 25.5 | Event Handlers |
| **Mutator** | 6 | 277 | 5.3% | 46.2 | Detector, Project |
| **Other** | 14 | 274 | 5.2% | 19.6 | Vários |
| **Query** | 8 | 132 | 2.5% | 16.5 | Detector, Project |
| **UI Internal** | 4 | 148 | 2.8% | 37.0 | UIStateController |
| **UI Method** | 4 | 77 | 1.5% | 19.3 | UIStateController |
| **Event Handler** | 4 | 41 | 0.8% | 10.3 | Event Handlers |
| **Property** | 5 | 24 | 0.5% | 4.8 | Manter no MainViewModel |
| **TOTAL** | **141** | **5,227** | **100%** | **37.1** | - |

---

## 🔷 1. ORCHESTRATION (15 métodos, 1,225 linhas)

**Descrição:** Workflows públicos de alto nível que orquestram múltiplos serviços. Pontos de entrada principais da aplicação.

**Destino:** VideoProcessingOrchestrator, RecordingSessionOrchestrator, AnalysisOrchestrator

| Método | Linhas | Linha | Prioridade |
| -------- | -------- | ------- | ------------ |
| `process_pending_project_videos` | 239 | 3695 | 🔴 ALTA (Sprint 24) |
| `start_single_video_processing` | 153 | 3449 | 🔴 ALTA (Sprint 24) |
| `start_live_camera_analysis_from_config` | 148 | 2771 | 🔴 ALTA (Sprint 26) |
| `run_aquarium_detection` | 108 | 2073 | 🟡 MÉDIA (Sprint 25) |
| `run_model_diagnostic` | 102 | 5122 | 🟡 MÉDIA (Sprint 27) |
| `run_live_calibration` | 99 | 2491 | 🔴 ALTA (Sprint 26) |
| `start_project_processing_workflow` | 91 | 3603 | 🔴 ALTA (Sprint 24) |
| `start_recording` | 66 | 2638 | 🔴 ALTA (Sprint 26) |
| `start_live_camera_analysis` | 65 | 2705 | 🔴 ALTA (Sprint 26) |
| `start_live_project_session` | 63 | 2942 | 🔴 ALTA (Sprint 26) |
| `start_single_video_workflow` | 50 | 3177 | 🟡 MÉDIA (Sprint 24) |
| `create_project_workflow` | 20 | 1229 | 🟡 MÉDIA (Sprint 27) |
| `generate_parquet_summaries` | 8 | 3935 | 🟢 BAIXA (Sprint 25) |
| `run` | 7 | 585 | ⚠️ NÃO EXTRAIR (entry point) |
| `generate_report` | 6 | 5115 | 🟢 BAIXA (Sprint 25) |

**Análise:**

- **Método mais longo:** `process_pending_project_videos` (239 linhas, C901 warning)
- **Total extraível:** ~1,218 linhas (99.4%)
- **Manter:** `run` (7 linhas)

**Estratégia de Extração:**

- **Sprint 24:** 4 métodos de video processing (531 linhas)
- **Sprint 25:** 3 métodos de análise (217 linhas)
- **Sprint 26:** 5 métodos de recording (445 linhas)
- **Sprint 27:** 2 métodos diversos (122 linhas)

---

## 🔶 2. ORCHESTRATION INTERNAL (15 métodos, 713 linhas)

**Descrição:** Helpers privados de orquestração. Suporte para workflows complexos.

**Destino:** VideoProcessingOrchestrator, AnalysisOrchestrator

| Método | Linhas | Linha | Prioridade |
| -------- | -------- | ------- | ------------ |
| `_process_summary_video` | 151 | 4451 | 🔴 ALTA (Sprint 25) |
| `_create_processing_callbacks` | 132 | 4936 | 🔴 ALTA (Sprint 24) |
| `_run_diagnostic_frame_loop` | 87 | 5410 | 🟡 MÉDIA (Sprint 27) |
| `_diagnostic_processing_thread` | 52 | 5225 | 🟡 MÉDIA (Sprint 27) |
| `_process_single_video` | 47 | 4794 | 🟡 MÉDIA (Sprint 24) |
| `_run_analysis_pipeline` | 39 | 4754 | 🟡 MÉDIA (Sprint 25) |
| `_prepare_zone_data_for_tracking` | 30 | 3971 | 🟢 BAIXA (Sprint 24) |
| `_determine_processing_intervals` | 29 | 4138 | 🟢 BAIXA (Sprint 24) |
| `_determine_processing_mode` | 26 | 1056 | ⚠️ NÃO EXTRAIR (core) |
| `_run_tracking_if_needed` | 26 | 3944 | 🟢 BAIXA (Sprint 24) |
| `_finalize_processing` | 26 | 4250 | 🟡 MÉDIA (Sprint 24) |
| `_process_videos` | 25 | 5089 | 🟡 MÉDIA (Sprint 24) |
| `_create_processing_context` | 19 | 5069 | 🔴 ALTA (Sprint 24) |
| `_publish_processing_mode` | 18 | 1083 | ⚠️ NÃO EXTRAIR (core, 11 dependentes) |
| `_prepare_results_directory` | 6 | 4929 | 🟢 BAIXA (Sprint 24) |

**Análise:**

- **Método mais longo:** `_process_summary_video` (151 linhas)
- **Total extraível:** ~669 linhas (93.8%)
- **Manter:** `_publish_processing_mode` (18 linhas), `_determine_processing_mode` (26 linhas)

**Estratégia de Extração:**

- **Sprint 24:** 10 métodos de video processing (550 linhas)
- **Sprint 25:** 2 métodos de análise (190 linhas)
- **Sprint 27:** 2 métodos de diagnostic (139 linhas)

---

## 🔷 3. UTILITY INTERNAL (38 métodos, 1,550 linhas)

**Descrição:** Utilitários e helpers privados diversos. Maior categoria em número de métodos.

**Destino:** Vários Orchestrators (detector, project, UI, analysis)

### Top 20 Métodos (por tamanho)

| Método | Linhas | Linha | Destino | Prioridade |
| -------- | -------- | ------- | --------- | ------------ |
| `__init__` | 280 | 128 | ⚠️ MainViewModel | NÃO EXTRAIR (DI root) |
| `_init_coordinators` | 162 | 422 | ⚠️ MainViewModel | NÃO EXTRAIR (DI) |
| `_format_diagnostic_report` | 97 | 5536 | DiagnosticOrchestrator | 🟡 MÉDIA |
| `_ensure_zones_before_recording` | 93 | 3006 | RecordingOrchestrator | 🔴 ALTA |
| `_select_eligible_videos` | 81 | 4305 | VideoProcessingOrchestrator | 🔴 ALTA |
| `_initialize_diagnostic_openvino_model` | 72 | 5337 | DiagnosticOrchestrator | 🟡 MÉDIA |
| `_make_progress_callback` | 68 | 4603 | VideoProcessingOrchestrator | 🔴 ALTA |
| `_temporary_single_animal_mode` | 64 | 4169 | DetectorOrchestrator | 🟡 MÉDIA |
| `_generate_parquet_summaries_worker` | 63 | 4387 | AnalysisOrchestrator | 🔴 ALTA |
| `_resolve_single_subject_tracker_preference` | 54 | 4071 | DetectorOrchestrator | 🟡 MÉDIA |
| `_apply_wizard_detector_overrides` | 47 | 1250 | DetectorOrchestrator | 🟢 BAIXA |
| `_finish_diagnostic_and_save_report` | 37 | 5498 | DiagnosticOrchestrator | 🟡 MÉDIA |
| `_initialize_diagnostic_yolo_model` | 36 | 5300 | DiagnosticOrchestrator | 🟡 MÉDIA |
| `_init_recording_service` | 36 | 838 | ⚠️ MainViewModel | NÃO EXTRAIR (setup) |
| `_resolve_single_animal_mode` | 35 | 4035 | DetectorOrchestrator | 🟢 BAIXA |
| `_create_event_dispatcher` | 35 | 986 | ⚠️ MainViewModel | NÃO EXTRAIR (events) |
| `_register_project_outputs` | 27 | 4726 | ProjectOrchestrator | 🟡 MÉDIA |
| `_build_metadata_context` | 26 | 4277 | VideoProcessingOrchestrator | 🟢 BAIXA |
| `_prepare_calibration_context` | 25 | 4679 | RecordingOrchestrator | 🟢 BAIXA |
| `_persist_project_model_settings` | 25 | 1807 | ProjectOrchestrator | 🟡 MÉDIA |

**Restante (18 métodos, 268 linhas):** Métodos pequenos (<25 linhas)

**Análise:**

- **Total extraível:** ~1,158 linhas (74.7%)
- **Manter no MainViewModel:** ~392 linhas (25.3%) - DI, setup, events

**Estratégia de Extração:**

- **Sprint 24:** 5 métodos video processing (~290 linhas)
- **Sprint 25:** 2 métodos análise (~160 linhas)
- **Sprint 26:** 3 métodos recording (~180 linhas)
- **Sprint 27:** 10 métodos diversos (~528 linhas)

---

## 🔶 4. STATE MANAGEMENT (15 métodos, 434 linhas)

**Descrição:** Gerenciamento de estado, configuração e persistência.

**Destino:** ProjectOrchestrator, DetectorOrchestrator

| Método | Linhas | Linha | Destino | Prioridade |
| -------- | -------- | ------- | --------- | ------------ |
| `apply_project_settings_to_batch` | 86 | 4842 | ProjectOrchestrator | 🔴 ALTA |
| `apply_roi_template` | 51 | 2182 | ProjectOrchestrator | 🟡 MÉDIA |
| `convert_active_weight_to_openvino` | 41 | 1593 | DetectorOrchestrator | 🔴 ALTA |
| `load_new_weight` | 38 | 1534 | DetectorOrchestrator | 🟡 MÉDIA |
| `setup_detector_zones` | 36 | 1388 | DetectorOrchestrator | 🔴 ALTA (4 dependentes) |
| `apply_project_model_overrides` | 31 | 1964 | ProjectOrchestrator | 🔴 ALTA (3 dependentes) |
| `save_project_model_overrides` | 29 | 1996 | ProjectOrchestrator | 🟡 MÉDIA |
| `save_current_calibration_to_project` | 29 | 1861 | ProjectOrchestrator | 🟡 MÉDIA |
| `set_openvino_usage` | 19 | 1573 | DetectorOrchestrator | 🟢 BAIXA |
| `update_main_arena` | 17 | 2294 | ProjectOrchestrator | 🟢 BAIXA |
| `open_project_workflow` | 17 | 1342 | ProjectOrchestrator | 🟡 MÉDIA |
| `setup_detector` | 16 | 1360 | DetectorOrchestrator | 🟡 MÉDIA (2 dependentes) |
| `close_project` | 13 | 1215 | ProjectOrchestrator | 🟡 MÉDIA |
| `setup_arduino` | 10 | 1377 | ⚠️ MainViewModel | NÃO EXTRAIR (hardware) |
| `get_openvino_status` | 9 | 749 | DetectorOrchestrator | 🟢 BAIXA |
| `save_manual_arena` | 9 | 2284 | ProjectOrchestrator | 🟢 BAIXA |

**Análise:**

- **Total extraível:** ~415 linhas (95.6%)
- **Manter:** `setup_arduino` (10 linhas)

**Estratégia de Extração:**

- **Sprint 27 - ProjectOrchestrator:** 9 métodos (~295 linhas)
- **Sprint 27 - DetectorOrchestrator:** 6 métodos (~120 linhas)

---

## 🔷 5. EVENT HANDLER INTERNAL (13 métodos, 332 linhas)

**Descrição:** Handlers de eventos privados e callbacks internos.

**Destino:** EventHandlers, UIStateController

| Método | Linhas | Linha | Destino | Prioridade |
| -------- | -------- | ------- | --------- | ------------ |
| `_handle_mixed_data_scenario` | 53 | 3228 | ProjectEventHandler | 🟡 MÉDIA |
| `_handle_validation_error` | 49 | 3399 | ValidationHandler | 🔴 ALTA (3 dependentes) |
| `_handle_external_trigger` | 46 | 2591 | RecordingEventHandler | 🟡 MÉDIA |
| `_on_state_change_for_test` | 27 | 662 | ⚠️ MainViewModel | NÃO EXTRAIR (test) |
| `_register_event_handlers` | 26 | 1022 | ⚠️ MainViewModel | NÃO EXTRAIR (setup) |
| `_build_calibration_context` | 24 | 4002 | RecordingOrchestrator | 🟢 BAIXA |
| `_show_post_creation_guide` | 22 | 1298 | UIStateController | 🟢 BAIXA |
| `_on_recording_state_changed` | 20 | 716 | ⚠️ MainViewModel | NÃO EXTRAIR (observer) |
| `_on_detector_state_changed` | 13 | 702 | ⚠️ MainViewModel | NÃO EXTRAIR (observer) |
| `_on_processing_state_changed` | 11 | 737 | ⚠️ MainViewModel | NÃO EXTRAIR (observer) |
| `_on_project_state_changed` | 10 | 691 | ⚠️ MainViewModel | NÃO EXTRAIR (observer) |
| `_handle_setup_zone_definition_for_single_video` | 6 | 1049 | VideoProcessingOrchestrator | 🟢 BAIXA |

**Análise:**

- **Total extraível:** ~200 linhas (60.2%)
- **Manter:** ~132 linhas (39.8%) - State observers, event setup, tests

**Estratégia de Extração:**

- **Sprint 31:** Event Handlers (148 linhas)
- **Sprint 28:** UIStateController (22 linhas)
- **Sprint 24:** VideoProcessing (6 linhas)
- **Sprint 26:** Recording (24 linhas)

---

## 🔶 6. MUTATOR (6 métodos, 277 linhas)

**Descrição:** Métodos que modificam estado (setters, add, delete, remove).

**Destino:** DetectorOrchestrator, ProjectOrchestrator

| Método | Linhas | Linha | Destino | Prioridade |
| -------- | -------- | ------- | --------- | ------------ |
| `add_roi_polygon` | 125 | 2312 | ProjectOrchestrator | 🔴 ALTA |
| `set_main_arena_polygon` | 49 | 2234 | ProjectOrchestrator | 🟡 MÉDIA |
| `delete_project_asset` | 34 | 2456 | ProjectOrchestrator | 🟢 BAIXA |
| `set_active_weight` | 26 | 1503 | DetectorOrchestrator | 🔴 ALTA (3 dependentes) |
| `delete_weight` | 23 | 1479 | DetectorOrchestrator | 🟢 BAIXA |
| `add_new_weight` | 20 | 1458 | DetectorOrchestrator | 🟢 BAIXA |

**Análise:**

- **Total extraível:** 277 linhas (100%)

**Estratégia de Extração:**

- **Sprint 27 - ProjectOrchestrator:** 3 métodos (208 linhas)
- **Sprint 27 - DetectorOrchestrator:** 3 métodos (69 linhas)

---

## 🔷 7. QUERY (8 métodos, 132 linhas)

**Descrição:** Getters e consultas read-only.

**Destino:** DetectorOrchestrator, ProjectOrchestrator

| Método | Linhas | Linha | Destino | Prioridade |
| -------- | -------- | ------- | --------- | ------------ |
| `get_calibration_scope_info` | 56 | 1688 | ProjectOrchestrator | 🟡 MÉDIA |
| `can_remove_project_asset` | 17 | 2438 | ProjectOrchestrator | 🟢 BAIXA |
| `get_current_detector_parameters` | 13 | 1745 | DetectorOrchestrator | 🟢 BAIXA |
| `get_factory_detector_parameters` | 13 | 1759 | DetectorOrchestrator | 🟢 BAIXA |
| `has_project_override_settings` | 10 | 1677 | ProjectOrchestrator | 🟡 MÉDIA (2 dependentes) |
| `get_global_model_defaults` | 10 | 1651 | ProjectOrchestrator | 🟢 BAIXA |
| `get_all_weight_names` | 7 | 1446 | DetectorOrchestrator | 🔴 ALTA (4 dependentes) |
| `is_recording` | 6 | 617 | ⚠️ MainViewModel | NÃO EXTRAIR (property setter) |

**Análise:**

- **Total extraível:** ~126 linhas (95.5%)
- **Manter:** `is_recording` (6 linhas)

**Estratégia de Extração:**

- **Sprint 27 - ProjectOrchestrator:** 4 métodos (93 linhas)
- **Sprint 27 - DetectorOrchestrator:** 3 métodos (33 linhas)

---

## 🔶 8. UI METHOD (4 métodos, 77 linhas)

**Descrição:** Métodos públicos de atualização de UI.

**Destino:** UIStateController

| Método | Linhas | Linha | Prioridade |
| -------- | -------- | ------- | ------------ |
| `update_detector_parameters` | 33 | 1773 | 🟡 MÉDIA |
| `refresh_project_views` | 21 | 1102 | 🔴 ALTA (9 dependentes) |
| `update_main_arena` | 17 | 2294 | 🟢 BAIXA |
| `update_openvino_status` | 6 | 1635 | 🔴 ALTA (4 dependentes) |

**Análise:**

- **Total extraível:** 77 linhas (100%)

**Estratégia de Extração:**

- **Sprint 28 - UIStateController:** 4 métodos (77 linhas)

---

## 🔷 9. UI INTERNAL (4 métodos, 148 linhas)

**Descrição:** Helpers de UI privados.

**Destino:** UIStateController

| Método | Linhas | Linha | Prioridade |
| -------- | -------- | ------- | ------------ |
| `_validate_zones_with_ui` | 116 | 3282 | 🔴 ALTA |
| `_update_diagnostic_progress` | 16 | 5278 | 🟢 BAIXA |
| `_prepare_processing_ui` | 8 | 4241 | 🟢 BAIXA |
| `_schedule_on_ui` | 8 | 808 | ⚠️ NÃO EXTRAIR (core, thread safety) |

**Análise:**

- **Total extraível:** ~140 linhas (94.6%)
- **Manter:** `_schedule_on_ui` (8 linhas)

**Estratégia de Extração:**

- **Sprint 28 - UIStateController:** 3 métodos (140 linhas)

---

## 🔶 10. EVENT HANDLER (4 métodos, 41 linhas)

**Descrição:** Handlers de eventos públicos (callbacks).

**Destino:** EventHandlers

| Método | Linhas | Linha | Destino | Prioridade |
| -------- | -------- | ------- | --------- | ------------ |
| `on_arduino_event` | 21 | 1150 | ArduinoEventHandler | 🟢 BAIXA |
| `on_close` | 14 | 759 | ⚠️ MainViewModel | NÃO EXTRAIR (lifecycle) |
| `on_arduino_status_change` | 3 | 1142 | ArduinoEventHandler | 🟢 BAIXA |
| `on_arduino_command_sent` | 3 | 1146 | ArduinoEventHandler | 🟢 BAIXA |

**Análise:**

- **Total extraível:** ~27 linhas (65.9%)
- **Manter:** `on_close` (14 linhas)

**Estratégia de Extração:**

- **Sprint 31 - ArduinoEventHandler:** 3 métodos (27 linhas)

---

## 🔷 11. OTHER (14 métodos, 274 linhas)

**Descrição:** Métodos não categorizados (miscelânea).

**Destino:** Vários

| Método | Linhas | Linha | Destino | Prioridade |
| -------- | -------- | ------- | --------- | ------------ |
| `resolve_project_model_settings` | 63 | 1900 | ProjectOrchestrator | 🟡 MÉDIA |
| `cancel_current_analysis` | 53 | 3102 | VideoProcessingOrchestrator | 🟡 MÉDIA |
| `copy_global_model_settings_to_project` | 27 | 1833 | ProjectOrchestrator | 🟢 BAIXA |
| `join_threads` | 19 | 774 | ⚠️ MainViewModel | NÃO EXTRAIR (lifecycle) |
| `global_calibration_session` | 19 | 2033 | ProjectOrchestrator | 🟢 BAIXA |
| `project_calibration_session` | 18 | 2054 | ProjectOrchestrator | 🟢 BAIXA |
| `stop_recording` | 21 | 2920 | RecordingOrchestrator | 🟡 MÉDIA |
| `bind_events` | 14 | 593 | ⚠️ MainViewModel | NÃO EXTRAIR (setup) |
| `detector` (setter) | 7 | 635 | ⚠️ MainViewModel | NÃO EXTRAIR (property) |
| `detector` (deleter) | 7 | 644 | ⚠️ MainViewModel | NÃO EXTRAIR (property) |
| `trigger_recording` | 17 | 1172 | RecordingOrchestrator | 🟢 BAIXA |
| `log_arduino_event` | 3 | 1138 | ArduinoEventHandler | 🟢 BAIXA |
| `classify_weight_type` | 3 | 1454 | DetectorOrchestrator | 🟢 BAIXA |
| `manage_weights` | 3 | 1530 | DetectorOrchestrator | 🟢 BAIXA |

**Análise:**

- **Total extraível:** ~221 linhas (80.7%)
- **Manter:** ~53 linhas (19.3%) - lifecycle, properties, setup

**Estratégia de Extração:**

- **Sprint 27 - ProjectOrchestrator:** 5 métodos (127 linhas)
- **Sprint 24 - VideoProcessingOrchestrator:** 1 método (53 linhas)
- **Sprint 26 - RecordingOrchestrator:** 2 métodos (38 linhas)
- **Sprint 27 - DetectorOrchestrator:** 2 métodos (6 linhas)
- **Sprint 31 - EventHandlers:** 1 método (3 linhas)

---

## 🔶 12. PROPERTY (5 métodos, 24 linhas)

**Descrição:** Python properties (@property decorators).

**Destino:** ⚠️ MANTER no MainViewModel (expõem estado interno)

| Método | Linhas | Linha | Nota |
| -------- | -------- | ------- | ------ |
| `detector` (getter) | 8 | 625 | Property - não extrair |
| `are_project_overrides_active` | 7 | 1643 | Property - não extrair |
| `is_recording` (getter) | 3 | 612 | Property - não extrair |
| `detector_initialized` | 3 | 653 | Property - não extrair |
| `is_processing` | 3 | 658 | Property - não extrair |

**Análise:**

- **Total:** 24 linhas
- **Manter:** 100% (properties devem ficar no MainViewModel)

---

## 📊 Resumo por Destino de Extração

| Destino | Métodos | Linhas | % Total |
| --------- | --------- | -------- | --------- |
| **VideoProcessingOrchestrator** | 22 | ~1,150 | 22.0% |
| **ProjectOrchestrator** | 27 | ~950 | 18.2% |
| **RecordingOrchestrator** | 12 | ~680 | 13.0% |
| **DetectorOrchestrator** | 18 | ~450 | 8.6% |
| **UIStateController** | 11 | ~420 | 8.0% |
| **AnalysisOrchestrator** | 5 | ~370 | 7.1% |
| **EventHandlers** | 6 | ~180 | 3.4% |
| **DiagnosticOrchestrator** | 6 | ~350 | 6.7% |
| **⚠️ MANTER no MainViewModel** | 34 | ~677 | 13.0% |
| **TOTAL** | **141** | **5,227** | **100%** |

---

## ✅ Métodos a MANTER no MainViewModel (34 métodos, 677 linhas)

### 1. DI & Initialization (5 métodos, 520 linhas)

- `__init__` (280 linhas) - Composition Root
- `_init_coordinators` (162 linhas) - DI wiring
- `_inject_or_create` (12 linhas) - DI helper
- `_init_recording_service` (36 linhas) - Service setup
- `_create_event_dispatcher` (35 linhas) - Event dispatcher factory

### 2. Event Binding & Setup (3 métodos, 60 linhas)

- `_setup_recording_service_callbacks` (20 linhas)
- `bind_events` (14 linhas)
- `_register_event_handlers` (26 linhas)

### 3. Core Orchestration (2 métodos, 26 linhas)

- `_publish_processing_mode` (18 linhas) - 11 dependentes
- `_schedule_on_ui` (8 linhas) - Thread safety

### 4. State Observers (5 métodos, 54 linhas)

- `_on_project_state_changed` (10 linhas)
- `_on_detector_state_changed` (13 linhas)
- `_on_recording_state_changed` (20 linhas)
- `_on_processing_state_changed` (11 linhas)
- `_determine_processing_mode` (26 linhas)

### 5. Lifecycle (3 métodos, 40 linhas)

- `run` (7 linhas)
- `on_close` (14 linhas)
- `join_threads` (19 linhas)

### 6. Properties (5 métodos, 24 linhas)

- `is_recording` (3 linhas)
- `detector` (8 linhas)
- `detector_initialized` (3 linhas)
- `is_processing` (3 linhas)
- `are_project_overrides_active` (7 linhas)

### 7. Property Setters/Deleters (3 métodos, 20 linhas)

- `is_recording` (setter, 6 linhas)
- `detector` (setter, 7 linhas)
- `detector` (deleter, 7 linhas)

### 8. Hardware (1 método, 10 linhas)

- `setup_arduino` (10 linhas)

### 9. Test Support (1 método, 27 linhas)

- `_on_state_change_for_test` (27 linhas)

### 10. Shutdown (2 métodos, 12 linhas)

- `_get_arduino_manager` (4 linhas)
- `_shutdown_arduino_manager` (8 linhas)

---

## 🎯 Conclusão

**Classificação completa:**

- ✅ **141 métodos** categorizados em 12 categorias
- ✅ **Destinos de extração** identificados
- ✅ **Prioridades** definidas
- ✅ **Métodos núcleo** protegidos

**Principais insights:**

1. **Orchestration + Orchestration Internal** = 28 métodos, 1,938 linhas (37.1%)
2. **Utility Internal** é a maior categoria em número de métodos (38)
3. **34 métodos** devem permanecer no MainViewModel (677 linhas)
4. **107 métodos** podem ser extraídos (4,550 linhas, 87%)

**Próximo Sprint:** Sprint 24 - Extrair VideoProcessingOrchestrator (22 métodos, ~1,150 linhas)

---

**Versão:** 1.0
**Última Atualização:** 2025-01-14
**Próxima Revisão:** Após Sprint 24
