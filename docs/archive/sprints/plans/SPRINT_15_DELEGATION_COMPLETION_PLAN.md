# Sprint 15 - Delegation Completion Plan

**Data:** 2025-01-13
**Status:** 📋 PLANEJAMENTO
**Branch:** `claude/access-voice-feature-01XPHyf4NAi2ivKGLoDUCYjq`

---

## 🎯 Objetivos

Completar as delegations pendentes do Sprint 7:

1. **Processing Delegation** - Finalizar delegation ao ProcessingCoordinator
2. **Recording Delegation** - Integrar RecordingCoordinator no MainViewModel

**Estimativa Total:** -100 a -200 linhas

---

## 📊 Análise Atual

### Processing Delegation - Status

**Já Completo (Sprints 11-14):**

- ✅ Validation extraction → ProcessingCoordinator.validate_can_start_processing()
- ✅ Helper services (VideoClassificationService, VideoSelectionService, VideoValidationService)
- ✅ Workflow simplification (Extract Method patterns)
- ✅ Cleanup deprecated code

**Ainda Pendente:**

- ❌ `_create_processing_callbacks()` (133 linhas) - criar callbacks de progresso
- ❌ `_create_processing_context()` (20 linhas) - criar contexto de processamento
- ❌ Delegation completa dos workflows para ProcessingCoordinator

**Métodos que ainda estão no MainViewModel:**

```python
# Public workflows (UI orchestration - devem permanecer)
- start_single_video_processing()       # 154 lines
- start_project_processing_workflow()   # 92 lines
- process_pending_project_videos()      # 149 lines

# Private helpers (candidates for delegation)
- _create_processing_callbacks()        # 133 lines ← DELEGAR
- _create_processing_context()          # 20 lines  ← DELEGAR
- _process_single_video()               # ~50 lines ← VERIFICAR
- _process_videos()                     # ~30 lines ← VERIFICAR
```

### Recording Delegation - Status

**RecordingCoordinator existente:**

- ✅ `start_recording()` - implementado
- ✅ `stop_recording()` - implementado
- ✅ `is_recording()` - implementado

**Problema:** RecordingCoordinator NÃO está sendo usado no MainViewModel!

- ❌ MainViewModel não usa `self.recording_coordinator`
- ❌ Métodos de recording ainda estão diretamente no MainViewModel

**Buscar no MainViewModel:**

- Métodos relacionados a recording/gravação
- Integração com RecordingService

---

## 🎯 Estratégia de Implementação

### Part 1: Processing Delegation Completion

**Objetivo:** Delegar helpers de processing ao ProcessingCoordinator

**Tarefas:**

1. Mover `_create_processing_callbacks()` para ProcessingCoordinator
   - Criar método `create_processing_callbacks()` no coordinator
   - Manter callback factories (podem ter UI dependencies)

2. Mover `_create_processing_context()` para ProcessingCoordinator
   - Criar método `create_processing_context()` no coordinator
   - Simplificar lógica de configuração

3. Atualizar workflows para usar coordinator methods
   - start_single_video_processing() → usa coordinator
   - start_project_processing_workflow() → usa coordinator
   - process_pending_project_videos() → usa coordinator

**Estimativa:** -80 a -120 linhas

### Part 2: Recording Delegation

**Objetivo:** Integrar RecordingCoordinator no MainViewModel

**Tarefas:**

1. Identificar métodos de recording no MainViewModel
   - Buscar padrões: record, recording, gravação
   - Analisar dependências com RecordingService

2. Fazer MainViewModel usar self.recording_coordinator
   - Delegar start/stop recording
   - Delegar status checks
   - Manter UI callbacks

3. Remover código duplicado
   - Eliminar wrappers desnecessários
   - Usar coordinator como single source of truth

**Estimativa:** -20 a -80 linhas

---

## 📋 Checklist

### Part 1: Processing Delegation ⏳

- [ ] Analisar _create_processing_callbacks() dependencies
- [ ] Mover _create_processing_callbacks() para ProcessingCoordinator
- [ ] Analisar _create_processing_context() dependencies
- [ ] Mover _create_processing_context() para ProcessingCoordinator
- [ ] Atualizar start_single_video_processing()
- [ ] Atualizar start_project_processing_workflow()
- [ ] Atualizar process_pending_project_videos()
- [ ] Validar syntax e linting
- [ ] Commit Part 1

### Part 2: Recording Delegation ⏳

- [ ] Identificar métodos de recording no MainViewModel
- [ ] Analisar dependências com RecordingService
- [ ] Fazer MainViewModel usar recording_coordinator
- [ ] Remover código duplicado
- [ ] Validar syntax e linting
- [ ] Commit Part 2

### Finalização ⏳

- [ ] Atualizar documentação (REFACTOR-MASTER-PLAN-2025.md)
- [ ] Push all changes
- [ ] Criar Sprint 16 plan

---

## ⚠️ Riscos

1. **UI Dependencies** - Callbacks podem ter dependencies complexas com UI
   - Mitigação: Manter factories no ViewModel, delegar apenas criação

2. **Recording Integration** - RecordingCoordinator pode ter API incompleta
   - Mitigação: Analisar primeiro, completar API se necessário

3. **Regressões** - Mudanças em código crítico
   - Mitigação: Validação incremental, commits pequenos

---

**Próximo:** Analisar _create_processing_callbacks() para delegation
