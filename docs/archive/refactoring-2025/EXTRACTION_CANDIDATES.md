# 🎯 Extraction Candidates - Top Métodos para Extração

**Document:** EXTRACTION_CANDIDATES.md
**Version:** 1.0
**Date:** 2025-01-14
**Sprint:** 23 - Análise de Dependências
**Status:** ✅ COMPLETED

---

## 📊 Overview

Este documento identifica e analisa em profundidade os **Top 28 métodos candidatos** para extração do MainViewModel, priorizados por:
1. **Tamanho** (>50 linhas)
2. **Impacto** (número de dependências)
3. **Complexidade** (fan-out, linting warnings)
4. **Retorno** (redução de linhas vs risco)

**Objetivo:** Guiar os Sprints 24-35 com análise detalhada de cada candidato, incluindo:
- Localização exata (linha início/fim)
- Dependências (chama/é chamado por)
- Destino de extração sugerido
- Risco e complexidade
- Ordem de extração recomendada

---

## 🏆 Top 28 Candidatos (>50 linhas)

Total: **3,368 linhas** (64.4% do MainViewModel)

| # | Método | Linhas | Linha | Categoria | Sprint | Risco |
|---|--------|--------|-------|-----------|--------|-------|
| 1 | `__init__` | 280 | 128 | utility_internal | ⚠️ NÃO EXTRAIR | ❌ |
| 2 | `process_pending_project_videos` | 239 | 3695 | orchestration | 24 | 🔴 |
| 3 | `_init_coordinators` | 162 | 422 | utility_internal | ⚠️ NÃO EXTRAIR | ❌ |
| 4 | `start_single_video_processing` | 153 | 3449 | orchestration | 24 | 🟡 |
| 5 | `_process_summary_video` | 151 | 4451 | orchestration_internal | 25 | 🟡 |
| 6 | `start_live_camera_analysis_from_config` | 148 | 2771 | orchestration | 26 | 🟡 |
| 7 | `_create_processing_callbacks` | 132 | 4936 | orchestration_internal | 24 | 🔴 |
| 8 | `add_roi_polygon` | 125 | 2312 | mutator | 27 | 🟡 |
| 9 | `_validate_zones_with_ui` | 116 | 3282 | ui_internal | 28 | 🟡 |
| 10 | `run_aquarium_detection` | 108 | 2073 | orchestration | 25 | 🟢 |
| 11 | `run_model_diagnostic` | 102 | 5122 | orchestration | 27 | 🟡 |
| 12 | `run_live_calibration` | 99 | 2491 | orchestration | 26 | 🟡 |
| 13 | `_format_diagnostic_report` | 97 | 5536 | utility_internal | 27 | 🟢 |
| 14 | `_ensure_zones_before_recording` | 93 | 3006 | utility_internal | 26 | 🔴 |
| 15 | `start_project_processing_workflow` | 91 | 3603 | orchestration | 24 | 🔴 |
| 16 | `_run_diagnostic_frame_loop` | 87 | 5410 | orchestration_internal | 27 | 🟡 |
| 17 | `apply_project_settings_to_batch` | 86 | 4842 | state_management | 27 | 🟡 |
| 18 | `_select_eligible_videos` | 81 | 4305 | utility_internal | 24 | 🟢 |
| 19 | `_initialize_diagnostic_openvino_model` | 72 | 5337 | utility_internal | 27 | 🟢 |
| 20 | `_make_progress_callback` | 68 | 4603 | utility_internal | 24 | 🟡 |
| 21 | `start_recording` | 66 | 2638 | orchestration | 26 | 🔴 |
| 22 | `start_live_camera_analysis` | 65 | 2705 | orchestration | 26 | 🟡 |
| 23 | `_temporary_single_animal_mode` | 64 | 4169 | utility_internal | 27 | 🟡 |
| 24 | `resolve_project_model_settings` | 63 | 1900 | other | 27 | 🟡 |
| 25 | `start_live_project_session` | 63 | 2942 | orchestration | 26 | 🟡 |
| 26 | `_generate_parquet_summaries_worker` | 63 | 4387 | utility_internal | 25 | 🟡 |
| 27 | `get_calibration_scope_info` | 56 | 1688 | query | 27 | 🟢 |
| 28 | `_resolve_single_subject_tracker_preference` | 54 | 4071 | utility_internal | 27 | 🟢 |

---

## 🔴 Prioridade CRÍTICA - Sprint 24 (VideoProcessingOrchestrator)

### #2: `process_pending_project_videos` ⚠️ C901 WARNING

**Localização:** `main_view_model.py:3695-3933` (239 linhas)
**Categoria:** orchestration
**Complexidade:** 🔴 MUITO ALTA (C901 cyclomatic complexity warning)

**Dependências:**
```python
# CHAMA:
- _select_eligible_videos (81 linhas)
- _create_processing_callbacks (132 linhas)
- _create_processing_context (19 linhas)
- _activate_analysis_view_mode (6 linhas)
- _handle_validation_error (49 linhas)

# É CHAMADO POR:
- Nenhum método interno (ponto de entrada público)
```

**Cadeia de dependências:** 565 linhas total
**Risco:** 🔴 ALTO
- Método muito complexo com warning de complexidade ciclomática
- Múltiplas condicionais e loops aninhados
- Lógica de validação crítica

**Estratégia de Extração:**
1. Criar `VideoProcessingOrchestrator.process_pending_videos()`
2. Extrair métodos auxiliares junto: `_select_eligible_videos`, `_create_processing_callbacks`, `_create_processing_context`
3. Manter facade mínima no MainViewModel
4. Testes exaustivos de regressão (>30 testes)

**Retorno:** -239 linhas (4.6% do MainViewModel)

---

### #4: `start_single_video_processing`

**Localização:** `main_view_model.py:3449-3601` (153 linhas)
**Categoria:** orchestration
**Complexidade:** 🟡 ALTA

**Dependências:**
```python
# CHAMA:
- refresh_project_views (21 linhas)
- _prepare_results_directory (6 linhas)
- _create_processing_callbacks (132 linhas)
- _create_processing_context (19 linhas)
- _activate_analysis_view_mode (6 linhas)
- _handle_validation_error (49 linhas)

# É CHAMADO POR:
- Nenhum método interno (ponto de entrada público)
```

**Cadeia de dependências:** 386 linhas total
**Risco:** 🟡 MÉDIO
- Workflow bem definido
- Depende de helpers compartilhados com #2

**Estratégia de Extração:**
1. Criar `VideoProcessingOrchestrator.process_single_video()`
2. Reutilizar helpers já extraídos de #2
3. Garantir callbacks de progresso funcionam

**Retorno:** -153 linhas (2.9% do MainViewModel)

---

### #7: `_create_processing_callbacks`

**Localização:** `main_view_model.py:4936-5067` (132 linhas)
**Categoria:** orchestration_internal
**Complexidade:** 🔴 ALTA (3 dependentes)

**Dependências:**
```python
# CHAMA:
- _publish_processing_mode (18 linhas) [⚠️ MANTER]
- refresh_project_views (21 linhas)

# É CHAMADO POR:
- start_single_video_processing
- start_project_processing_workflow
- process_pending_project_videos
```

**Risco:** 🔴 ALTO
- Usado por 3 métodos principais
- Cria closures complexas
- Essencial para feedback de progresso

**Estratégia de Extração:**
1. Extrair para `VideoProcessingOrchestrator._create_callbacks()`
2. Injetar `_publish_processing_mode` via callback
3. Testar todos os 3 fluxos que o usam

**Retorno:** -132 linhas (2.5% do MainViewModel)

---

### #15: `start_project_processing_workflow`

**Localização:** `main_view_model.py:3603-3693` (91 linhas)
**Categoria:** orchestration
**Complexidade:** 🔴 ALTA (6 chamadas)

**Dependências:**
```python
# CHAMA:
- _handle_mixed_data_scenario (53 linhas)
- _create_processing_callbacks (132 linhas)
- _create_processing_context (19 linhas)
- _activate_analysis_view_mode (6 linhas)
- _handle_validation_error (49 linhas)
- _validate_zones_with_ui (116 linhas)

# É CHAMADO POR:
- Nenhum método interno (ponto de entrada público)
```

**Cadeia de dependências:** 466 linhas total
**Risco:** 🔴 ALTO
- Validação complexa de zonas
- Cenário de dados mistos (tracking + vídeos novos)

**Estratégia de Extração:**
1. Criar `VideoProcessingOrchestrator.start_project_workflow()`
2. Extrair `_validate_zones_with_ui` para UIStateController separadamente
3. Testar fluxo de dados mistos cuidadosamente

**Retorno:** -91 linhas (1.7% do MainViewModel)

---

### #18: `_select_eligible_videos`

**Localização:** `main_view_model.py:4305-4385` (81 linhas)
**Categoria:** utility_internal
**Complexidade:** 🟢 BAIXA (isolado)

**Dependências:**
```python
# CHAMA: Nenhum

# É CHAMADO POR:
- process_pending_project_videos
```

**Risco:** 🟢 BAIXO
- Método isolado, sem dependências internas
- Lógica de filtragem simples

**Estratégia de Extração:**
1. Mover para `VideoProcessingOrchestrator._select_videos()`
2. Extração direta, sem refatoração

**Retorno:** -81 linhas (1.5% do MainViewModel)

---

### #20: `_make_progress_callback`

**Localização:** `main_view_model.py:4603-4670` (68 linhas)
**Categoria:** utility_internal
**Complexidade:** 🟡 MÉDIA

**Dependências:**
```python
# CHAMA:
- _publish_processing_mode (18 linhas) [⚠️ MANTER]

# É CHAMADO POR:
- Nenhum método interno (usado em closures)
```

**Risco:** 🟡 MÉDIO
- Usado via closures em callbacks
- Atualiza progresso em tempo real

**Estratégia de Extração:**
1. Mover para `VideoProcessingOrchestrator._make_callback()`
2. Injetar `_publish_processing_mode` via dependency

**Retorno:** -68 linhas (1.3% do MainViewModel)

---

**Subtotal Sprint 24:** ~815 linhas (15.6% do MainViewModel)

---

## 🟡 Prioridade ALTA - Sprint 25 (AnalysisOrchestrator)

### #5: `_process_summary_video`

**Localização:** `main_view_model.py:4451-4601` (151 linhas)
**Categoria:** orchestration_internal
**Complexidade:** 🟡 MÉDIA

**Dependências:**
```python
# CHAMA: Nenhum (isolado)

# É CHAMADO POR:
- _generate_parquet_summaries_worker
```

**Risco:** 🟡 MÉDIO
- Lógica de análise complexa
- Gera sumários Parquet

**Estratégia de Extração:**
1. Criar `AnalysisOrchestrator.process_summary()`
2. Extração direta (sem dependências internas)

**Retorno:** -151 linhas (2.9% do MainViewModel)

---

### #10: `run_aquarium_detection`

**Localização:** `main_view_model.py:2073-2180` (108 linhas)
**Categoria:** orchestration
**Complexidade:** 🟢 BAIXA

**Dependências:**
```python
# CHAMA:
- _publish_processing_mode (18 linhas) [⚠️ MANTER]

# É CHAMADO POR:
- Nenhum método interno (ponto de entrada público)
```

**Risco:** 🟢 BAIXO
- Workflow bem isolado
- Única dependência: _publish_processing_mode

**Estratégia de Extração:**
1. Criar `AnalysisOrchestrator.detect_aquarium()`
2. Injetar `_publish_processing_mode` via callback

**Retorno:** -108 linhas (2.1% do MainViewModel)

---

### #26: `_generate_parquet_summaries_worker`

**Localização:** `main_view_model.py:4387-4449` (63 linhas)
**Categoria:** utility_internal
**Complexidade:** 🟡 MÉDIA

**Dependências:**
```python
# CHAMA:
- refresh_project_views (21 linhas)
- _process_summary_video (151 linhas)

# É CHAMADO POR:
- Nenhum método interno (thread worker)
```

**Risco:** 🟡 MÉDIO
- Worker thread separado
- Coordena geração de sumários

**Estratégia de Extração:**
1. Mover para `AnalysisOrchestrator._summary_worker()`
2. Extrair junto com `_process_summary_video`

**Retorno:** -63 linhas (1.2% do MainViewModel)

---

**Subtotal Sprint 25:** ~322 linhas (6.2% do MainViewModel)

---

## 🔴 Prioridade CRÍTICA - Sprint 26 (RecordingSessionOrchestrator)

### #6: `start_live_camera_analysis_from_config`

**Localização:** `main_view_model.py:2771-2918` (148 linhas)
**Categoria:** orchestration
**Complexidade:** 🟡 MÉDIA

**Dependências:**
```python
# CHAMA: Nenhum (isolado)

# É CHAMADO POR:
- Nenhum método interno (ponto de entrada público)
```

**Risco:** 🟡 MÉDIO
- Workflow de câmera ao vivo
- Integração com hardware

**Estratégia de Extração:**
1. Criar `RecordingSessionOrchestrator.start_live_from_config()`
2. Testar com câmera real e mock

**Retorno:** -148 linhas (2.8% do MainViewModel)

---

### #12: `run_live_calibration`

**Localização:** `main_view_model.py:2491-2589` (99 linhas)
**Categoria:** orchestration
**Complexidade:** 🟡 MÉDIA

**Dependências:**
```python
# CHAMA:
- _publish_processing_mode (18 linhas) [⚠️ MANTER]

# É CHAMADO POR:
- _ensure_zones_before_recording
```

**Risco:** 🟡 MÉDIO
- Calibração ao vivo crítica
- Dependência: _ensure_zones_before_recording

**Estratégia de Extração:**
1. Criar `RecordingSessionOrchestrator.calibrate_live()`
2. Extrair junto com `_ensure_zones_before_recording`

**Retorno:** -99 linhas (1.9% do MainViewModel)

---

### #14: `_ensure_zones_before_recording`

**Localização:** `main_view_model.py:3006-3098` (93 linhas)
**Categoria:** utility_internal
**Complexidade:** 🔴 ALTA

**Dependências:**
```python
# CHAMA:
- run_live_calibration (99 linhas)

# É CHAMADO POR:
- start_recording
```

**Risco:** 🔴 ALTO
- Validação crítica antes de gravação
- Pode iniciar calibração (modal dialog)

**Estratégia de Extração:**
1. Mover para `RecordingSessionOrchestrator._ensure_zones()`
2. Extrair junto com `run_live_calibration`
3. Testar todos os cenários de validação

**Retorno:** -93 linhas (1.8% do MainViewModel)

---

### #21: `start_recording` ⚠️ ALTO FAN-OUT

**Localização:** `main_view_model.py:2638-2703` (66 linhas)
**Categoria:** orchestration
**Complexidade:** 🔴 MUITO ALTA (chama 7 métodos)

**Dependências:**
```python
# CHAMA:
- _clear_external_trigger_wait (13 linhas)
- setup_detector_zones (36 linhas)
- _handle_external_trigger (46 linhas)
- _schedule_recording (24 linhas)
- _ensure_zones_before_recording (93 linhas)
- setup_detector (16 linhas)
- setup_arduino (10 linhas) [⚠️ MANTER]

# É CHAMADO POR:
- on_arduino_event
```

**Cadeia de dependências:** 304 linhas total
**Risco:** 🔴 MUITO ALTO
- Método mais complexo de recording
- Integração com Arduino (hardware)
- Validação crítica de zonas

**Estratégia de Extração:**
1. Criar `RecordingSessionOrchestrator.start()`
2. Extrair helpers: `_schedule_recording`, `_clear_external_trigger_wait`, `_handle_external_trigger`
3. `setup_arduino` permanece no MainViewModel (hardware)
4. Testes com/sem Arduino

**Retorno:** -66 linhas (1.3% do MainViewModel)

---

### #22: `start_live_camera_analysis`

**Localização:** `main_view_model.py:2705-2769` (65 linhas)
**Categoria:** orchestration
**Complexidade:** 🟡 MÉDIA

**Dependências:**
```python
# CHAMA: Nenhum (isolado)

# É CHAMADO POR:
- Nenhum método interno (ponto de entrada público)
```

**Risco:** 🟡 MÉDIO
- Workflow de análise ao vivo
- Similar a `start_live_camera_analysis_from_config`

**Estratégia de Extração:**
1. Criar `RecordingSessionOrchestrator.start_live_analysis()`
2. Consolidar com método #6

**Retorno:** -65 linhas (1.2% do MainViewModel)

---

### #25: `start_live_project_session`

**Localização:** `main_view_model.py:2942-3004` (63 linhas)
**Categoria:** orchestration
**Complexidade:** 🟡 MÉDIA

**Dependências:**
```python
# CHAMA: Nenhum (isolado)

# É CHAMADO POR:
- Nenhum método interno (ponto de entrada público)
```

**Risco:** 🟡 MÉDIO
- Sessão de projeto ao vivo
- Coordena múltiplos vídeos

**Estratégia de Extração:**
1. Criar `RecordingSessionOrchestrator.start_project_session()`
2. Extração direta

**Retorno:** -63 linhas (1.2% do MainViewModel)

---

**Subtotal Sprint 26:** ~534 linhas (10.2% do MainViewModel)

---

## 🟡 Prioridade MÉDIA - Sprint 27 (Vários Orchestrators)

### #8: `add_roi_polygon` (ProjectOrchestrator)

**Localização:** `main_view_model.py:2312-2436` (125 linhas)
**Categoria:** mutator
**Complexidade:** 🟡 MÉDIA

**Dependências:**
```python
# CHAMA:
- setup_detector_zones (36 linhas)

# É CHAMADO POR:
- Nenhum método interno (chamado pela UI)
```

**Risco:** 🟡 MÉDIO
- Lógica de ROI complexa
- Validação de polígonos

**Estratégia de Extração:**
1. Mover para `ProjectOrchestrator.add_roi()`
2. Extrair junto com `setup_detector_zones`

**Retorno:** -125 linhas (2.4% do MainViewModel)

---

### #11: `run_model_diagnostic` (DiagnosticOrchestrator)

**Localização:** `main_view_model.py:5122-5223` (102 linhas)
**Categoria:** orchestration
**Complexidade:** 🟡 MÉDIA

**Dependências:**
```python
# CHAMA:
- _publish_processing_mode (18 linhas) [⚠️ MANTER]
- convert_active_weight_to_openvino (41 linhas)

# É CHAMADO POR:
- Nenhum método interno (ponto de entrada público)
```

**Risco:** 🟡 MÉDIO
- Workflow de diagnóstico
- Thread worker separado

**Estratégia de Extração:**
1. Criar `DiagnosticOrchestrator.run_diagnostic()`
2. Extrair cadeia de helpers de diagnostic junto

**Retorno:** -102 linhas (2.0% do MainViewModel)

---

### #13: `_format_diagnostic_report` (DiagnosticOrchestrator)

**Localização:** `main_view_model.py:5536-5632` (97 linhas)
**Categoria:** utility_internal
**Complexidade:** 🟢 BAIXA

**Dependências:**
```python
# CHAMA: Nenhum (isolado)

# É CHAMADO POR:
- _finish_diagnostic_and_save_report
```

**Risco:** 🟢 BAIXO
- Formatação de texto pura
- Sem lógica de negócio

**Estratégia de Extração:**
1. Mover para `DiagnosticOrchestrator._format_report()`
2. Extração direta

**Retorno:** -97 linhas (1.9% do MainViewModel)

---

### #16: `_run_diagnostic_frame_loop` (DiagnosticOrchestrator)

**Localização:** `main_view_model.py:5410-5496` (87 linhas)
**Categoria:** orchestration_internal
**Complexidade:** 🟡 MÉDIA

**Dependências:**
```python
# CHAMA:
- _finish_progress_dialog (4 linhas)
- _update_diagnostic_progress (16 linhas)

# É CHAMADO POR:
- _diagnostic_processing_thread
```

**Risco:** 🟡 MÉDIO
- Loop de processamento
- Atualização de progresso

**Estratégia de Extração:**
1. Mover para `DiagnosticOrchestrator._frame_loop()`
2. Extrair junto com outros métodos diagnostic

**Retorno:** -87 linhas (1.7% do MainViewModel)

---

### #17: `apply_project_settings_to_batch` (ProjectOrchestrator)

**Localização:** `main_view_model.py:4842-4927` (86 linhas)
**Categoria:** state_management
**Complexidade:** 🟡 MÉDIA

**Dependências:**
```python
# CHAMA:
- _prepare_results_directory (6 linhas)

# É CHAMADO POR:
- Nenhum método interno (chamado externamente)
```

**Risco:** 🟡 MÉDIO
- Aplica configurações em lote
- Coordena múltiplos vídeos

**Estratégia de Extração:**
1. Mover para `ProjectOrchestrator.apply_batch_settings()`
2. Extração direta

**Retorno:** -86 linhas (1.6% do MainViewModel)

---

### #19: `_initialize_diagnostic_openvino_model` (DiagnosticOrchestrator)

**Localização:** `main_view_model.py:5337-5408` (72 linhas)
**Categoria:** utility_internal
**Complexidade:** 🟢 BAIXA

**Dependências:**
```python
# CHAMA:
- _finish_progress_dialog (4 linhas)

# É CHAMADO POR:
- _diagnostic_processing_thread
```

**Risco:** 🟢 BAIXO
- Inicialização de modelo
- Sem lógica complexa

**Estratégia de Extração:**
1. Mover para `DiagnosticOrchestrator._init_openvino()`
2. Extração junto com outros métodos diagnostic

**Retorno:** -72 linhas (1.4% do MainViewModel)

---

### #23: `_temporary_single_animal_mode` (DetectorOrchestrator)

**Localização:** `main_view_model.py:4169-4232` (64 linhas)
**Categoria:** utility_internal
**Complexidade:** 🟡 MÉDIA (context manager)

**Dependências:**
```python
# CHAMA:
- _resolve_single_animal_mode (35 linhas)
- _resolve_single_subject_tracker_preference (54 linhas)
- _configure_single_subject_tracker (11 linhas)
- _publish_processing_mode (18 linhas) [⚠️ MANTER]

# É CHAMADO POR:
- _process_videos
- _process_single_video
```

**Risco:** 🟡 MÉDIO
- Context manager (@contextmanager)
- Usado por 2 métodos

**Estratégia de Extração:**
1. Mover para `DetectorOrchestrator.single_animal_mode()`
2. Extrair helpers junto: `_resolve_single_animal_mode`, `_resolve_single_subject_tracker_preference`

**Retorno:** -64 linhas (1.2% do MainViewModel)

---

### #24: `resolve_project_model_settings` (ProjectOrchestrator)

**Localização:** `main_view_model.py:1900-1962` (63 linhas)
**Categoria:** other
**Complexidade:** 🟡 MÉDIA

**Dependências:**
```python
# CHAMA:
- _safe_get_default_weight (18 linhas)
- get_all_weight_names (7 linhas)

# É CHAMADO POR:
- apply_project_model_overrides
```

**Risco:** 🟡 MÉDIO
- Lógica de configuração de modelo
- Usado por overrides

**Estratégia de Extração:**
1. Mover para `ProjectOrchestrator.resolve_settings()`
2. Extrair junto com `apply_project_model_overrides`

**Retorno:** -63 linhas (1.2% do MainViewModel)

---

### #27: `get_calibration_scope_info` (ProjectOrchestrator)

**Localização:** `main_view_model.py:1688-1743` (56 linhas)
**Categoria:** query
**Complexidade:** 🟢 BAIXA

**Dependências:**
```python
# CHAMA:
- has_project_override_settings (10 linhas)

# É CHAMADO POR:
- Nenhum método interno (chamado pela UI)
```

**Risco:** 🟢 BAIXO
- Query read-only
- Sem side effects

**Estratégia de Extração:**
1. Mover para `ProjectOrchestrator.get_calibration_info()`
2. Extração direta

**Retorno:** -56 linhas (1.1% do MainViewModel)

---

### #28: `_resolve_single_subject_tracker_preference` (DetectorOrchestrator)

**Localização:** `main_view_model.py:4071-4124` (54 linhas)
**Categoria:** utility_internal
**Complexidade:** 🟢 BAIXA

**Dependências:**
```python
# CHAMA: Nenhum (isolado)

# É CHAMADO POR:
- _temporary_single_animal_mode
```

**Risco:** 🟢 BAIXO
- Helper puro
- Sem dependências

**Estratégia de Extração:**
1. Mover para `DetectorOrchestrator._resolve_tracker()`
2. Extrair junto com `_temporary_single_animal_mode`

**Retorno:** -54 linhas (1.0% do MainViewModel)

---

**Subtotal Sprint 27:** ~906 linhas (17.3% do MainViewModel)

---

## 🟢 Prioridade BAIXA - Sprint 28 (UIStateController)

### #9: `_validate_zones_with_ui`

**Localização:** `main_view_model.py:3282-3397` (116 linhas)
**Categoria:** ui_internal
**Complexidade:** 🟡 MÉDIA

**Dependências:**
```python
# CHAMA:
- set_main_arena_polygon (49 linhas)

# É CHAMADO POR:
- start_project_processing_workflow
```

**Risco:** 🟡 MÉDIO
- UI modal complexa
- Validação interativa

**Estratégia de Extração:**
1. Mover para `UIStateController.validate_zones()`
2. Testar interação com usuário

**Retorno:** -116 linhas (2.2% do MainViewModel)

---

**Subtotal Sprint 28:** ~116 linhas (2.2% do MainViewModel)

---

## 📊 Resumo de Extração Projetada

| Sprint | Orchestrator | Métodos | Linhas | % Total | Risco |
|--------|--------------|---------|--------|---------|-------|
| **24** | VideoProcessing | 6 | ~815 | 15.6% | 🔴 |
| **25** | Analysis | 3 | ~322 | 6.2% | 🟡 |
| **26** | RecordingSession | 6 | ~534 | 10.2% | 🔴 |
| **27** | Vários (Project, Diagnostic, Detector) | 10 | ~906 | 17.3% | 🟡 |
| **28** | UIStateController | 1 | ~116 | 2.2% | 🟡 |
| **TOTAL TOP 28** | - | **26** | **~2,693** | **51.5%** | - |

**Observação:** Os métodos #1 (`__init__`, 280 linhas) e #3 (`_init_coordinators`, 162 linhas) **NÃO** serão extraídos (DI root), portanto o total extraível dos Top 28 é **26 métodos, 2,693 linhas** (51.5% do MainViewModel).

---

## 🎯 Ordem de Extração Recomendada

### Fase 1: Orchestrators de Processamento (Sprints 24-25)
1. ✅ `_select_eligible_videos` (isolado, sem dependências)
2. ✅ `_create_processing_context` (usado por 3 métodos)
3. ✅ `_create_processing_callbacks` (usado por 3 métodos)
4. ✅ `start_single_video_processing` (usa #2 e #3)
5. ✅ `start_project_processing_workflow` (usa #2 e #3)
6. ✅ `process_pending_project_videos` (C901 warning, usa #1, #2, #3)
7. ✅ `_process_summary_video` (isolado)
8. ✅ `run_aquarium_detection` (isolado)
9. ✅ `_generate_parquet_summaries_worker` (usa #7)

### Fase 2: Recording & Live Camera (Sprint 26)
10. ✅ `run_live_calibration` (isolado)
11. ✅ `_ensure_zones_before_recording` (usa #10)
12. ✅ `start_recording` (usa #11, mais crítico)
13. ✅ `start_live_camera_analysis` (isolado)
14. ✅ `start_live_camera_analysis_from_config` (isolado)
15. ✅ `start_live_project_session` (isolado)

### Fase 3: Project, Detector, Diagnostic (Sprint 27)
16. ✅ `get_calibration_scope_info` (isolado query)
17. ✅ `_resolve_single_subject_tracker_preference` (isolado)
18. ✅ `_temporary_single_animal_mode` (usa #17)
19. ✅ `resolve_project_model_settings` (isolado)
20. ✅ `add_roi_polygon` (mutator)
21. ✅ `apply_project_settings_to_batch` (state)
22. ✅ `_format_diagnostic_report` (isolado)
23. ✅ `_initialize_diagnostic_openvino_model` (isolado)
24. ✅ `_run_diagnostic_frame_loop` (usa #22, #23)
25. ✅ `run_model_diagnostic` (usa #24)

### Fase 4: UI (Sprint 28)
26. ✅ `_validate_zones_with_ui` (UI complexa)

---

## ⚠️ Riscos Identificados

### 🔴 Riscos ALTOS

**1. Complexidade Ciclomática (#2 - `process_pending_project_videos`)**
- C901 warning indica lógica muito complexa
- Múltiplas condicionais aninhadas
- **Mitigação:** Testes exaustivos (>30 casos), refatoração em submétodos

**2. Alto Acoplamento (#7 - `_create_processing_callbacks`)**
- Usado por 3 workflows críticos
- Cria closures complexas
- **Mitigação:** Testar todos os 3 fluxos, validar callbacks

**3. Hardware Integration (#21 - `start_recording`)**
- Integração com Arduino
- Validação de zonas crítica
- **Mitigação:** Testes com/sem hardware, mocks robustos

**4. Validação UI (#14 - `_ensure_zones_before_recording`)**
- Pode abrir dialogs modais
- Bloqueia fluxo até usuário responder
- **Mitigação:** Testar todos os cenários de validação

### 🟡 Riscos MÉDIOS

**1. Context Managers (#23 - `_temporary_single_animal_mode`)**
- Decorator @contextmanager
- Gerenciamento de estado temporário
- **Mitigação:** Testar setup/teardown, exceções

**2. Thread Workers (#11, #26)**
- Executam em threads separados
- Coordenação de progresso
- **Mitigação:** Testes de concorrência

**3. UI Modals (#9 - `_validate_zones_with_ui`)**
- Interação com usuário
- Pode cancelar operação
- **Mitigação:** Testar todos os caminhos (OK, Cancel, Close)

### 🟢 Riscos BAIXOS

Métodos isolados sem dependências internas: #5, #10, #13, #18, #19, #22, #27, #28

---

## ✅ Critérios de Sucesso

Para cada extração:
- [ ] ✅ Método extraído para novo orchestrator
- [ ] ✅ Facade mínima criada no MainViewModel (1-3 linhas)
- [ ] ✅ Testes criados (>80% coverage do novo método)
- [ ] ✅ Testes de regressão passando (2568+ testes)
- [ ] ✅ Linting clean (ruff check)
- [ ] ✅ Documentação atualizada

---

## 📈 Projeção Final

**Total de linhas extraíveis (Top 28):** ~2,693 linhas (51.5% do MainViewModel)
**Linhas remanescentes após Sprints 24-28:** ~2,534 linhas

**Para atingir meta de ~1,000 linhas:**
- Sprints 29-33: Extrair mais ~1,534 linhas (métodos <50 linhas)
- Total final projetado: ~1,000 linhas (-81%)

---

## ✅ Conclusão

- ✅ **28 candidatos** analisados em profundidade
- ✅ **26 extraíveis** (2 são DI root)
- ✅ **Ordem de extração** otimizada
- ✅ **Riscos identificados** e mitigados
- ✅ **Estratégias** definidas

**Próximo Sprint:** Sprint 24 - Extrair VideoProcessingOrchestrator (6 métodos, ~815 linhas)

---

**Versão:** 1.0
**Última Atualização:** 2025-01-14
**Próxima Revisão:** Após Sprint 24
