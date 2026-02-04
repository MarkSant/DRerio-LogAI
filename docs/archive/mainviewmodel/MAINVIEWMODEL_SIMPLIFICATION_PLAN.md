<!-- markdownlint-disable MD024 -->

# MainViewModel Simplification Plan - Sprint 7-8

**Documento:** MAINVIEWMODEL_SIMPLIFICATION_PLAN
**Versão:** 1.0
**Data:** 2025-01-13
**Status:** 🚀 EM ANDAMENTO

---

## 📊 Estado Atual

| Métrica | Valor Inicial | Atual (Sprint 7) | Meta Final | Progresso |
| --------- | --------------- | ------------------ | ------------ | ----------- |
| **Linhas** | 5,683 | 5,713 (+30) | <800 | +0.5% |
| **Métodos** | 154 | ~154 | <40 | 0% |
| **Responsabilidades** | ~10 | ~10 | 1-2 | 0% |

**Nota:** Linhas aumentaram com adição de lógica UI nas delegações (validação de zonas).
**Commits:** 81bef82, 5775dc8 (Sprint 7 - Parts 1-2/3)

---

## 🎯 Estratégia de Simplificação

### Fase 1: Delegação para Coordinators (Sprint 7) - ✅ PARCIAL

Converter métodos existentes para simples wrappers que delegam aos coordinators.

**Status:**

- ✅ **DetectorCoordinator** - 7 métodos delegados (COMPLETO - commits 81bef82, 5775dc8)
- 🔴 **ProcessingCoordinator** - Requer refatoração (workflows diferentes entre ViewModel e Orchestrator)
- 🔴 **RecordingCoordinator** - Coordinator incompleto (apenas stubs, não delega para service)
- ✅ **LiveCameraCoordinator** - Já integrado (Sprint 6)
- ✅ **ProjectCoordinator** - Já integrado (Sprint 3)

### Fase 2: Remoção de Código Legado (Sprint 7-8) - 🔴 PENDENTE

Remover código duplicado, métodos obsoletos, e simplificar lógica.

**Requer:** Análise detalhada de código legado e duplicações.

### Fase 3: Testes e Validação (Sprint 8) - 🔴 PENDENTE

Garantir que todas as delegações funcionam corretamente.

---

## 📋 Métodos para Delegar

### ProjectCoordinator (3 métodos principais)

**Já Implementado (usando project_coordinator):**

- ✅ `create_project_workflow()` - Delega para `project_coordinator.create_project_from_wizard()`
- ✅ `open_project_workflow()` - Delega para `project_coordinator.load_project()`
- ✅ `close_project()` - Delega para `project_coordinator.close_project()`

**Status:** Estes métodos já delegam corretamente. Podem ser simplificados removendo lógica intermediária.

---

### DetectorCoordinator (7 métodos principais) - ✅ COMPLETO

**Delegados (Sprint 7 - commits 81bef82, 5775dc8):**

- ✅ `setup_detector()` → `detector_coordinator.setup_detector()`
- ✅ `setup_detector_zones()` → `detector_coordinator.configure_zones()`
- ✅ `update_detector_parameters()` → `detector_coordinator.update_detector_parameters()`
- ✅ `get_current_detector_parameters()` → `detector_coordinator.get_detector_parameters()`
- ✅ `get_factory_detector_parameters()` → `detector_coordinator.get_factory_detector_parameters()`
- ✅ `_restore_detector_settings()` → `detector_coordinator.restore_detector_settings()`
- ✅ `_configure_single_subject_tracker()` → `detector_coordinator.set_single_subject_mode()`

**Impacto:**

- +110 linhas no `detector_coordinator.py` (novo método `update_detector_parameters()`)
- +41 linhas, -12 linhas no `main_view_model.py` (lógica UI adicionada)
- Backward compatibility mantida (normalização de parâmetros preservada)
- Property getters/setters para `self.detector` mantidos inalterados

---

### RecordingCoordinator (3 métodos principais)

**Já Implementado:**

- `trigger_recording()` - Usa `recording_service` internamente
- `_schedule_recording()` - Usa `recording_service` internamente

**Podem ser Simplificados:**

- Remover lógica duplicada de validação
- Delegar completamente para `recording_coordinator`

---

### LiveCameraCoordinator (2 métodos principais)

**Já Implementado:**

- `start_live_camera_analysis()` - Delega para `live_camera_service`
- Pode ser atualizado para usar `live_camera_coordinator`

---

### ProcessingCoordinator (3 métodos principais)

**Já Implementado:**

- `start_project_processing_workflow()` - Delega para `video_orchestrator`
- `process_pending_project_videos()` - Delega para `video_orchestrator`

**Podem ser Simplificados:**

- Remover validações duplicadas (coordinator já valida)
- Delegar completamente para `processing_coordinator`

---

## 🗑️ Métodos para Remover/Consolidar

### Métodos Legados (Candidatos a Remoção)

- Métodos privados duplicados (helpers)
- Validações duplicadas (já nos coordinators)
- Callbacks que podem ser internalizados

### Métodos de Utilidade (Podem ser Movidos)

- Arduino helpers → HardwareCoordinator
- Model management helpers → DetectorCoordinator
- Weight management → WeightManager (já existe)

---

## 🔄 Plano de Implementação

### Sprint 7 - Parte 1: Detector Delegation

1. Atualizar métodos de detector para usar `detector_coordinator`
2. Remover delegação para `detector_service` direta
3. Simplificar validações (coordinator já valida)
4. Atualizar testes

**Redução estimada:** ~500 linhas

### Sprint 7 - Parte 2: Processing Delegation

1. Atualizar métodos de processing para usar `processing_coordinator`
2. Remover validações duplicadas
3. Simplificar workflow methods
4. Atualizar testes

**Redução estimada:** ~300 linhas

### Sprint 7 - Parte 3: Recording Delegation

1. Atualizar métodos de recording para usar `recording_coordinator`
2. Consolidar Arduino integration
3. Simplificar callbacks
4. Atualizar testes

**Redução estimada:** ~200 linhas

### Sprint 7 - Parte 4: Cleanup

1. Remover métodos privados não utilizados
2. Consolidar helpers
3. Remover código duplicado
4. Atualizar documentação

**Redução estimada:** ~800 linhas

### Sprint 8: Validation

1. Testes end-to-end completos
2. Performance validation
3. Regression tests
4. Documentation updates

**Total Redução Estimada:** ~1,800 linhas (de 5,683 para ~3,883)

**Nota:** Para chegar a <800 linhas, será necessário mais simplificação nas próximas iterações (Sprints 9+).

---

## ✅ Critérios de Sucesso Sprint 7-8

### Sprint 7

- [ ] Todos os métodos de detector delegam para `detector_coordinator`
- [ ] Todos os métodos de processing delegam para `processing_coordinator`
- [ ] Todos os métodos de recording delegam para `recording_coordinator`
- [ ] Redução de pelo menos 1,500 linhas
- [ ] Todos os testes passam
- [ ] Zero regressões funcionais

### Sprint 8

- [ ] Testes end-to-end completos (100% passing)
- [ ] Performance sem degradação
- [ ] Documentação atualizada (CLAUDE.md, ARCHITECTURE.md)
- [ ] Code review aprovado
- [ ] Métricas de complexidade melhoradas

---

## 📝 Notas de Implementação

### Padrão de Delegação

```python
# ANTES (delegação direta ao service)
def setup_detector(self, temp_animal_method: str | None = None) -> bool:
    success, error = self.detector_service.initialize_detector(
        animal_method=temp_animal_method,
        use_openvino=self.settings.detection.use_openvino,
    )
    return success

# DEPOIS (delegação ao coordinator)
def setup_detector(self, temp_animal_method: str | None = None) -> bool:
    """Setup detector. Delegates to DetectorCoordinator."""
    success, error = self.detector_coordinator.setup_detector(
        animal_method=temp_animal_method,
        use_openvino=self.settings.detection.use_openvino,
    )
    return success
```

### Backward Compatibility

- Manter assinaturas de métodos públicos
- Deprecar métodos que serão removidos (usar warnings)
- Adicionar aliases para métodos renomeados

---

## 🎯 Próximas Etapas Imediatas

1. **Detector Delegation (Priority 1)**
   - Atualizar `setup_detector()` para usar `detector_coordinator`
   - Atualizar `update_detector_parameters()` para usar `detector_coordinator`
   - Atualizar `get_current_detector_parameters()` para usar `detector_coordinator`

2. **Processing Delegation (Priority 2)**
   - Atualizar `start_project_processing_workflow()` para usar `processing_coordinator`
   - Atualizar `process_pending_project_videos()` para usar `processing_coordinator`

3. **Recording Delegation (Priority 3)**
   - Atualizar `trigger_recording()` para usar `recording_coordinator`

---

---

## 🔍 Descobertas do Sprint 7

### 1. Processing Delegation - Complexidade Identificada

Os workflows de processing têm responsabilidades diferentes:

- **VideoOrchestrator**: Valida → Publica evento UI para abrir diálogo
- **MainViewModel**: Valida → Abre diálogo → Processa vídeos

**Decisão:** Requer refatoração cuidadosa para separar:

- Orquestração de UI (fica no ViewModel)
- Lógica de negócio (delega para coordinator)

**Status:** Adiado para Sprint 9+ conforme complexidade identificada.

### 2. Recording Delegation - Coordinator Incompleto

O `RecordingCoordinator` criado no Sprint 4 tem apenas stubs:

- Métodos não delegam para `RecordingService`
- Apenas atualiza StateManager (linha 198: `# Delegate to recording service` - comentário apenas)
- MainViewModel já delega diretamente para `recording_service`

**Decisão:** Requer completar RecordingCoordinator antes de delegar.

**Status:** Adiado para sprint futuro quando RecordingCoordinator estiver completo.

### 3. Linhas Aumentaram, Não Diminuíram

Detector delegation adicionou +41 linhas, -12 linhas = **+29 linhas líquidas**.

**Razão:** Lógica de UI foi expandida nas delegações (validação de zonas, notificações).

**Conclusão:** Simplificação virá de:

- Remoção de código legado
- Consolidação de helpers
- Remoção de duplicações
- Não apenas de delegações

---

## 🎯 Próximas Etapas (Sprint 7-8 Restante)

### Imediato (Sprint 7)

1. ✅ Detector Delegation - COMPLETO
2. 🔴 Identificar código legado para remoção
3. 🔴 Identificar métodos privados não utilizados
4. 🔴 Identificar duplicações

### Sprint 8

1. Cleanup de código identificado
2. Testes de regressão
3. Performance validation
4. Atualizar REFACTOR-MASTER-PLAN-2025.md

### Sprints Futuros (9+)

1. Completar RecordingCoordinator (delegar para service)
2. Refatorar Processing workflows (separar UI de lógica)
3. Extrair helpers para módulos apropriados
4. Continuar redução de linhas para meta <800

---

**Documento vivo - será atualizado conforme o progresso.**
**Última atualização:** Sprint 7 - Detector Delegation Completa (commits 81bef82, 5775dc8)
