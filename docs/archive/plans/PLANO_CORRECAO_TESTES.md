# Plano de Correção de Testes e Aumento de Cobertura

## 1. Estado Atual

### 1.1 Resumo dos Testes
- **Total de testes**: 2691 coletados (1952 fast, 739 GUI/slow)
- **Passando**: 1942
- **Falhando**: 8 testes
- **Skipped**: 2 testes

### 1.2 Testes Falhando (8 total)

| # | Arquivo | Teste | Categoria | Prioridade |
|---|---------|-------|-----------|------------|
| 1 | `test_class_names_validation.py` | `test_validate_model_classes_missing_class` | Validação | Média |
| 2 | `test_detector.py` | `test_single_subject_mode_assigns_constant_track_id` | Core | Alta |
| 3 | `test_gui_state_observer.py` | `test_processing_state_stop_updates_ui` | UI/State | Alta |
| 4 | `test_logging_advanced.py` | `test_compact_console_renderer_reduces_whitespace` | Logging | Baixa |
| 5 | `test_logging_advanced.py` | `test_root_logger_set_to_info` | Logging | Baixa |
| 6 | `test_settings.py` | `test_load_settings_success_without_zones` | Settings | Média |
| 7 | `test_smoke.py` | `test_docs_exist` | Docs | Baixa |
| 8 | `test_gui_public_api_contract.py` | `test_total_public_api_count` | API Contract | Média |

### 1.3 Cobertura Atual por Módulo Crítico

| Módulo | Cobertura | Linhas Faltando | Prioridade |
|--------|-----------|-----------------|------------|
| `processing_coordinator.py` | **12%** | 739 linhas | **CRÍTICA** |
| `hardware_coordinator.py` | **0%** | 461 linhas | Alta |
| `session_coordinator.py` | **0%** | 378 linhas | Alta |
| `project_lifecycle_coordinator.py` | **0%** | 282 linhas | Alta |
| `reporter.py` | **36%** | 211 linhas | Alta |
| `dialog_coordinator.py` | **43%** | 66 linhas | Média |
| `trajectory_validator.py` | **67%** | 24 linhas | Média |
| `metrics_cache.py` | **21%** | 45 linhas | Média |
| `base_coordinator.py` | **58%** | 10 linhas | Baixa |

---

## 2. Plano de Correção (Fase 1 - Testes Falhando)

### 2.1 Prioridade Alta (Core + UI/State)

#### 2.1.1 `test_detector.py::test_single_subject_mode_assigns_constant_track_id`
- **Erro**: `(10, 10, 30, 30) != (100, 100, 120, 120)`
- **Causa provável**: Mudança no comportamento do detector em modo single_subject
- **Ação**: Investigar se o teste está desatualizado ou se há regressão no código

#### 2.1.2 `test_gui_state_observer.py::test_processing_state_stop_updates_ui`
- **Erro**: Falha de asserção (provavelmente timing)
- **Causa provável**: Race condition ou mudança no StateManager
- **Ação**: Verificar sincronização e possível necessidade de `root.after()` ou sleep

### 2.2 Prioridade Média (Validação + Settings + API)

#### 2.2.1 `test_class_names_validation.py::test_validate_model_classes_missing_class`
- **Erro**: `DID NOT RAISE ValueError`
- **Causa provável**: Função de validação mudou comportamento (não levanta mais exceção)
- **Ação**: Verificar se o teste precisa ser atualizado para novo comportamento

#### 2.2.2 `test_settings.py::test_load_settings_success_without_zones`
- **Ação**: Verificar mudanças no schema de settings

#### 2.2.3 `test_gui_public_api_contract.py::test_total_public_api_count`
- **Causa provável**: Novos métodos públicos adicionados à GUI
- **Ação**: Atualizar contagem esperada de métodos públicos

### 2.3 Prioridade Baixa (Logging + Docs)

#### 2.3.1 `test_logging_advanced.py` (2 testes)
- **Ação**: Atualizar expectativas de formatação de logs

#### 2.3.2 `test_smoke.py::test_docs_exist`
- **Ação**: Verificar quais arquivos de docs estão faltando

---

## 3. Plano de Aumento de Cobertura (Fase 2)

### 3.1 Cobertura Crítica: `processing_coordinator.py` (12% → 70%+)

Funções a testar (por grupo lógico):

#### Grupo A: Video Processing Workflows
- [ ] `register_event_handlers()` - linhas 231-269
- [ ] `select_eligible_videos()` - linhas 283-365
- [ ] `create_processing_context()` - linhas 382-407
- [ ] `create_processing_callbacks()` - linhas 432-656
- [ ] `cancel_processing()` - linhas 668-673
- [ ] `make_progress_callback()` - linhas 688-734
- [ ] `start_single_video_processing()` - linhas 746-876
- [ ] `process_pending_project_videos()` - linhas 919-1035

#### Grupo B: Analysis Workflows
- [ ] `run_aquarium_detection()` - linhas 1057-1145
- [ ] `generate_parquet_summaries()` - linhas 1157-1215
- [ ] `generate_project_reports()` - linhas 1750-1887

#### Grupo C: Zone and Arena Management
- [ ] `set_main_arena_polygon()` - linhas 1226-1271
- [ ] `save_manual_arena()` - linhas 1278-1283
- [ ] `add_roi_polygon()` - linhas 1290-1415

#### Grupo D: Processing Configuration
- [ ] `_determine_processing_mode()` - linhas 1426-1448
- [ ] `_publish_processing_mode()` - linhas 1461-1469
- [ ] `_resolve_single_animal_mode()` - linhas 1477-1508
- [ ] `_determine_processing_intervals()` - linhas 1577-1604
- [ ] `_temporary_single_animal_mode()` - linhas 1612-1671

#### Grupo E: Validation
- [ ] `validate_can_start_processing()` - linhas 1710-1746

#### Grupo F: Internal Methods
- [ ] `_process_summary_video()` - linhas 2097-2248 (CORRIGIDO HOJE)
- [ ] `_load_zones_for_eligible_videos()` - linhas 2020-2085
- [ ] `_extract_metadata_from_config()` - linhas 1903-1919
- [ ] `_handle_targeted_selection_errors()` - linhas 1925-1958
- [ ] `_handle_pending_selection_errors()` - linhas 1962-1971

### 3.2 Cobertura Alta: Super Coordinators (0% → 50%+)

#### `hardware_coordinator.py` - 461 linhas
- [ ] Testes para inicialização de detector
- [ ] Testes para diagnóstico de modelo
- [ ] Testes para gerenciamento de zonas

#### `session_coordinator.py` - 378 linhas
- [ ] Testes para ciclo de vida de sessão
- [ ] Testes para gerenciamento de estado

#### `project_lifecycle_coordinator.py` - 282 linhas
- [ ] Testes para criação de projeto
- [ ] Testes para abertura de projeto
- [ ] Testes para salvamento de projeto

### 3.3 Cobertura Média: Reporter e Analysis

#### `reporter.py` (36% → 70%+)
- [ ] `export_individual_report()` - linhas 404-464
- [ ] `export_project_report()` - linhas 473-533
- [ ] `_generate_trajectory_plot()` - linhas 633-807
- [ ] `_create_docx_from_template()` - linhas 821-874

---

## 4. Estratégia de Implementação

### Fase 1: Correção de Testes Falhando (Estimativa: 2-3 horas)
1. Investigar cada falha individualmente
2. Corrigir testes ou código conforme necessário
3. Validar que todos os 8 testes passam

### Fase 2: Cobertura Crítica - ProcessingCoordinator (Estimativa: 4-6 horas)
1. Criar fixtures robustas com mocks adequados
2. Implementar testes para Grupo A (Video Processing)
3. Implementar testes para Grupo B (Analysis)
4. Implementar testes para Grupo C (Zone Management)
5. Meta: Alcançar 70% de cobertura

### Fase 3: Cobertura de Super Coordinators (Estimativa: 4-6 horas)
1. `hardware_coordinator.py` - Testes básicos de inicialização
2. `session_coordinator.py` - Testes de ciclo de vida
3. `project_lifecycle_coordinator.py` - Testes de CRUD de projeto

### Fase 4: Cobertura de Reporter (Estimativa: 2-3 horas)
1. Testes para geração de relatórios Word
2. Testes para geração de plots
3. Testes de integração end-to-end

---

## 5. Critérios de Aceitação

- [ ] Todos os 8 testes falhando corrigidos
- [ ] `processing_coordinator.py` com cobertura ≥ 70%
- [ ] Super coordinators com cobertura ≥ 50%
- [ ] `reporter.py` com cobertura ≥ 60%
- [ ] Nenhum teste novo com `@pytest.mark.skip` permanente
- [ ] Todos os testes passando em `poetry run pytest -q`

---

## 6. Riscos e Mitigações

| Risco | Probabilidade | Impacto | Mitigação |
|-------|---------------|---------|-----------|
| Testes GUI com race conditions | Alta | Médio | Usar `root.after()` e timeouts adequados |
| Mocks complexos para coordinators | Média | Alto | Criar fixtures compartilhadas em conftest.py |
| Dependências circulares em testes | Baixa | Alto | Isolamento via dependency injection |
| Testes lentos | Média | Baixo | Marcar com `@pytest.mark.slow` |

---

## 7. Próximos Passos Imediatos

1. **Investigar** `test_detector.py::test_single_subject_mode_assigns_constant_track_id`
2. **Investigar** `test_gui_state_observer.py::test_processing_state_stop_updates_ui`
3. **Corrigir** os 8 testes falhando
4. **Iniciar** cobertura do `processing_coordinator.py`

---

*Documento criado em: 2025-12-10*
*Baseado na análise de: pytest + coverage reports*
