<!-- markdownlint-disable MD024 -->

# Plano de Correção de Vulnerabilidades - ZebTrack-AI

**Data:** 02 Dez 2025
**Objetivo:** Corrigir 5 vulnerabilidades críticas no sistema de eventos e arquitetura
**Duração Estimada:** 6-8 semanas (incremental)
**Cobertura de Testes:** Manter 2568 testes passando (70%+ cobertura)

---

## Status de Execução

| Fase | Status | Data Conclusão |
| ------ | -------- | ---------------- |
| **Fase 1** | ✅ CONCLUÍDA | 02 Dez 2025 |
| **Fase 2** | ✅ CONCLUÍDA | 02 Dez 2025 |
| **Fase 3** | ✅ CONCLUÍDA | 02 Dez 2025 |
| **Fase 4** | ✅ CONCLUÍDA | 02 Dez 2025 |

### Resultados

- 7 orchestrators deletados (~2,500 linhas removidas)
- 2 orchestrators slim mantidos (VideoProcessingOrchestrator, UIStateController)
- UICoordinator renomeado para UIScheduler (colisão resolvida)
- Live Camera divergência documentada (ADR-004)
- 1934+ testes passando

---

## Resumo Executivo

### Vulnerabilidades Identificadas

| ID | Vulnerabilidade | Arquivos | Linhas | Risco | Status |
| ---- | ---------------- | ---------- | -------- | ------- | -------- |
| **V1** | Payload Mismatch (`UI_UPDATE_PROCESSING_MODE`) | 5 | ~50 | Médio | ✅ RESOLVIDO |
| **V2** | Colisão de Nomes (`UICoordinator` duplicado) | 3 | ~850 | Baixo | ✅ RESOLVIDO |
| **V3** | Orchestrators Legados ⚠️ | 9+ | **4,579** | **ALTO** | ✅ RESOLVIDO (7 deletados) |
| **V4** | Eventos Mortos | 4 | ~30 | Baixo | ✅ RESOLVIDO |
| **V5** | Divergência Live Camera | 2 | N/A | Baixo-Médio | ✅ DOCUMENTADO (ADR-004) |

---

## Fase 1: Quick Wins - Payload & Eventos Mortos (Semanas 1-2)

### Risco: BAIXO | Testes: Unitários por componente

### 1.1. Corrigir Payload Mismatch - `UI_UPDATE_PROCESSING_MODE`

**Problema:** 3 orchestrators publicam `{source: str, force: bool}` ao invés de `{report: ProcessingReport}`

#### Arquivos a Modificar

### 1. `src/zebtrack/orchestrators/video_processing_orchestrator.py`

- **Linhas 334-337, 401-405:** Substituir payload legado por `ProcessingReport`

```python
# ANTES
{"source": "worker.completed", "force": True}

# DEPOIS
from zebtrack.core.processing_mode import ProcessingMode, ProcessingReport
{"report": ProcessingReport(mode=ProcessingMode.READY, source="worker.completed")}
```

### 2. `src/zebtrack/orchestrators/analysis_orchestrator.py`

- **Linhas 158-161:** Mesmo padrão acima

### 3. `src/zebtrack/ui/components/event_dispatcher.py`

- **Linhas 388-395:** REMOVER camada de compatibilidade defensiva após corrigir publishers
- Deletar código do adapter legado em `_handle_update_processing_mode`

### 4. `docs/SYSTEM_INTEGRATION_MAP.md`

- **Linha 23:** Remover warning sobre legacy orchestrators
- Atualizar: "Todos publishers usam formato correto desde v3.1"

### Testes

```bash
poetry run pytest tests/orchestrators/test_video_processing_orchestrator.py -v
poetry run pytest tests/orchestrators/test_analysis_orchestrator.py -v
poetry run pytest -m "not slow" -q
```

---

### 1.2. Remover Eventos Mortos

#### Arquivos a Modificar

### 1. `src/zebtrack/ui/ui_coordinator.py`

- **Linhas 141-142:** Remover subscrições para `UIEvents.ANALYSIS_STARTED/COMPLETED`
- **Linhas 421-440:** Deletar métodos `_on_analysis_started` e `_on_analysis_completed`

### 2. `src/zebtrack/core/video_orchestrator.py`

- **Linha 227:** Remover publicação de `UI_OPEN_ADD_VIDEOS_DIALOG` (nunca definido)

### 3. `src/zebtrack/core/viewmodels/project_view_model.py`

- **Linha 78:** Remover publicação de `UI_UPDATE_PROJECT_INFO` (nunca definido)

### 4. `src/zebtrack/ui/event_bus_v2.py`

- **Linhas 42-43:** Deletar `ANALYSIS_STARTED` e `ANALYSIS_COMPLETED` do enum

### 5. `docs/SYSTEM_INTEGRATION_MAP.md`

- **Linhas 33-40:** Deletar seção "Known Dead or Unused Events"

### Testes

```bash
poetry run pytest tests/ui/test_ui_coordinator.py -v
poetry run pytest -q
```

---

## Fase 2: Resolver Colisão UICoordinator (Semana 2)

### Risco: BAIXO | Padrão: Search & Replace

### Decisão: Renomear `core.ui_coordinator.UICoordinator` → `UIScheduler`

### Justificativa

- `core.ui_coordinator` (325 linhas) = **Scheduler Tkinter** - agenda atualizações via `root.after()`
- `ui.ui_coordinator` (536 linhas) = **Mediator Event-Driven** - coordena entre componentes UI
- Renomear a classe menor é menos disruptivo

#### Ações

### 1. Renomear arquivo

```bash
mv src/zebtrack/core/ui_coordinator.py src/zebtrack/core/ui_scheduler.py
```

### 2. `src/zebtrack/core/ui_scheduler.py`

- Renomear classe `UICoordinator` → `UIScheduler`
- Atualizar docstrings

### 3. Atualizar imports (~20 arquivos estimados)

- **Padrão:** `from zebtrack.core.ui_coordinator import UICoordinator`
- **Substituir:** `from zebtrack.core.ui_scheduler import UIScheduler`
- **Arquivos principais:**
  - `src/zebtrack/core/application_bootstrapper.py` (~linha 170)
  - `src/zebtrack/core/dependency_container.py`
  - `src/zebtrack/__main__.py` (linhas 214-219)
  - `src/zebtrack/orchestrators/*.py` (5-7 arquivos)
  - `tests/core/test_ui_coordinator.py` → renomear para `test_ui_scheduler.py`

### 4. Corrigir type hint em ProcessingCoordinator

**Arquivo:** `src/zebtrack/coordinators/processing_coordinator.py`

```python
# Linha 60 - ANTES (import errado)
from zebtrack.ui.components.ui_coordinator import UICoordinator

# DEPOIS (path correto)
from zebtrack.core.ui_scheduler import UIScheduler

# Linha 155 - Atualizar construtor
def __init__(self, ..., ui_scheduler: UIScheduler, ...):
```

### 5. Atualizar UIStateController

**Arquivo:** `src/zebtrack/orchestrators/ui_state_controller.py` (linha 26)

- Corrigir import: `from zebtrack.core.ui_scheduler import UIScheduler`

### Testes

```bash
poetry run python -m zebtrack --help  # Validar imports
poetry run pytest tests/core/test_ui_scheduler.py -v
poetry run pytest tests/coordinators/test_processing_coordinator.py -v
poetry run pytest -q
```

### Documentação

- `docs/SYSTEM_INTEGRATION_MAP.md` (linha 57): Atualizar para `UIScheduler`
- `docs/ARCHITECTURE.md`: Atualizar diagramas
- `docs/DEPENDENCY_INJECTION_GUIDE.md`: Atualizar exemplos
- `CLAUDE.md`: Atualizar referências

---

## Fase 3: Remover Orchestrators Legados ⚠️ CRÍTICO (Semanas 3-8)

### Risco: ALTO | Abordagem: Incremental (1-2 por semana)

### Contexto

### Estado Atual Confirmado

- `application_bootstrapper.py` linhas 546-594: Inicializa **9 orchestrators**
- `ProcessingCoordinator` (linhas 1-15): Comenta que consolidou 5 orchestrators
- **PROBLEMA:** Orchestrators ainda existem e rodam em paralelo com coordinators → duplicação + race conditions

### Orchestrators Ativos (4,579 linhas)

1. `video_processing_orchestrator.py` - **961 linhas** - CRÍTICO
2. `analysis_orchestrator.py` - **380 linhas** - CRÍTICO
3. `ui_state_controller.py` - **626 linhas**
4. `recording_session_orchestrator.py` - 757 linhas
5. `project_orchestrator.py` - 526 linhas
6. `model_diagnostics_orchestrator.py` - 608 linhas
7. `processing_config_orchestrator.py` - 300 linhas
8. `zone_arena_orchestrator.py` - 229 linhas
9. `calibration_orchestrator.py` - 155 linhas

---

### 3.1. Auditoria e Mapeamento de Dependências (Semana 3)

### Risco: ZERO (read-only)

#### Deliverables

### 1. Criar `docs/ORCHESTRATOR_MIGRATION_PLAN.md`

Para cada orchestrator, documentar:

- Métodos chamados externamente (call sites em MainViewModel)
- Lógica já migrada para qual Coordinator
- Testes dependentes
- Blockers para remoção

### Template

```markdown
## VideoProcessingOrchestrator (961 linhas)

### Métodos Públicos
- `start_single_video_processing()` (linha 424) → ProcessingCoordinator.start_processing()
- `process_pending_project_videos()` (linha 818) → ProcessingCoordinator.process_videos()
- `create_processing_callbacks()` (linha 210) → MIGRAR para ProcessingCoordinator

### Call Sites
- MainViewModel.method_x() linha Y
- ApplicationGUI.on_button_click() linha Z

### Testes
- tests/orchestrators/test_video_processing_orchestrator.py (15 testes)

**Status:** Lógica já existe em ProcessingCoordinator. Orchestrator é DUPLICAÇÃO PURA.
```

### 2. Identificar padrões de blocker

- Chamadas diretas de MainViewModel para orchestrator.method()
- Registros de event handlers
- Dependências de callbacks

---

### 3.2. Migrar VideoProcessingOrchestrator (Semana 4)

### Risco: ALTO**|**Arquivo mais crítico

#### Estratégia

1. Mover lógica faltante orchestrator → coordinator
2. Atualizar MainViewModel para chamar coordinator
3. Desabilitar orchestrator no bootstrapper
4. Validar testes
5. Deletar após 1 semana de estabilidade

#### Arquivos a Modificar

### 1. `src/zebtrack/coordinators/processing_coordinator.py`

Adicionar métodos faltantes de VideoProcessingOrchestrator:

- `select_eligible_videos()` (linhas 102-184) - se não existir
- `create_processing_callbacks()` (linhas 210-348) - **MIGRAR ESTE**
- `make_progress_callback()` (linhas 350-422) - **MIGRAR ESTE**

### 2. `src/zebtrack/core/main_view_model.py`

Substituir todas chamadas:

```python
# ANTES
callbacks = self.video_processing_orchestrator.create_processing_callbacks(videos)

# DEPOIS
callbacks = self.processing_coordinator.create_processing_callbacks(videos)
```

### 3. `src/zebtrack/core/application_bootstrapper.py`

- **Linhas 556-557:** Comentar instantiation de `VideoProcessingOrchestrator`
- **Linhas 598, 609, 613:** Remover do registry

### 4. Migrar testes

- **De:** `tests/orchestrators/test_video_processing_orchestrator.py`
- **Para:** `tests/coordinators/test_processing_coordinator.py`
- Adaptar fixtures e mocks

### 5. Após 1 semana de estabilidade

- Deletar `src/zebtrack/orchestrators/video_processing_orchestrator.py`

### Estratégia de Testes

```bash
# 1. Adicionar métodos ao ProcessingCoordinator
poetry run pytest tests/coordinators/test_processing_coordinator.py -v

# 2. Atualizar MainViewModel
poetry run pytest tests/core/test_main_view_model.py -v

# 3. Testes de integração
poetry run pytest tests/integration/ -v -k "video_processing"

# 4. Full suite
poetry run pytest -q

# 5. Manual GUI
poetry run zebtrack
```

---

### 3.3. Migrar AnalysisOrchestrator (Semana 5)

### Risco: MÉDIO**|**Padrão similar a 3.2

#### Métodos a Migrar para ProcessingCoordinator

- `run_aquarium_detection()` (linhas 55-162)
- `_generate_parquet_summaries_worker()` (linhas 164-228)
- `_process_summary_video()` (linhas 230-380)

#### Arquivos

- Mesmo padrão da etapa 3.2
- Target: `ProcessingCoordinator`

---

### 3.4. Migrar Orchestrators Restantes (Semanas 6-8)

### Ordem por Complexidade

### Semana 6 (Risco: MÉDIO)

1. `zone_arena_orchestrator.py` (229 linhas) → ProcessingCoordinator
2. `processing_config_orchestrator.py` (300 linhas) → ProcessingCoordinator
3. `calibration_orchestrator.py` (155 linhas) → ProcessingCoordinator

### Semana 7 (Risco: MÉDIO)

1. `recording_session_orchestrator.py` (757 linhas) → SessionCoordinator
2. `project_orchestrator.py` (526 linhas) → ProjectLifecycleCoordinator

### Semana 8 (Risco: MÉDIO)

1. `ui_state_controller.py` (626 linhas) → **ESPECIAL** - mesclar com Phase 4 UIStateController
2. `model_diagnostics_orchestrator.py` (608 linhas) → HardwareCoordinator ou novo service

#### Checklist por Orchestrator

- [ ] Documentar métodos e call sites
- [ ] Mover lógica para coordinator alvo
- [ ] Atualizar MainViewModel calls
- [ ] Remover de application_bootstrapper.py
- [ ] Migrar testes
- [ ] Rodar full test suite
- [ ] Período de estabilidade (1 semana)
- [ ] Deletar arquivo
- [ ] Commit: `refactor: remove [name] - migrado para [coordinator]`

---

### 3.5. Limpeza Final (Semana 8)

### Risco: BAIXO

#### Ações

### 1. Deletar diretório

```bash
rm -rf src/zebtrack/orchestrators/
```

### 2. Remover de imports

- `src/zebtrack/core/application_bootstrapper.py` - remover imports de orchestrators
- `src/zebtrack/core/orchestrator_registry.py` - **DELETAR arquivo inteiro**

### 3. Atualizar MainViewModel

- Remover atributos de orchestrator
- Remover método `_init_orchestrators()` se existir

### 4. Limpar testes

- Deletar `tests/orchestrators/` directory
- Deletar `tests/core/test_orchestrator_registry.py`

### Validação Final

```bash
poetry run pytest -m "" -n0  # Todos 2568 testes
poetry run pytest --cov=zebtrack --cov-report=term-missing
poetry run ruff check .
```

### Atualizar Documentação

- `docs/ARCHITECTURE.md` - Remover camada de orchestrators
- `CLAUDE.md` (linhas 50-56) - Remover da tabela de layers
- `docs/SYSTEM_INTEGRATION_MAP.md` - Atualizar dependências de componentes

---

## Fase 4: Decisão sobre Live Camera (Semana 9)

### Risco: BAIXO | Recomendação: DOCUMENTAR (não unificar)

### Contexto

- Live camera unificado em Phase 8 (Jan 2025) - estabilizado recentemente
- Sistema funciona, sem queixas de usuários
- Risco/benefício favorece documentação vs refactor

### Ação Recomendada: **Documentar Divergência como Intencional**

#### Arquivos

### 1. `docs/SYSTEM_INTEGRATION_MAP.md` (linhas 109-114)

Expandir seção com justificativa:

```markdown
### 3.3. Fluxo Live Camera (Divergência Intencional)

**Decisão de Design:** Live camera usa `LivePreviewWindow` dedicado ao invés de `CanvasManager`.

### Justificativa
- Requer modelo de threading diferente (threads de captura + processamento)
- Lifecycle de preview window ligado à sessão de câmera, não ao canvas principal
- Reutilizar CanvasManager adiciona complexidade sem benefício claro

### Trade-offs
- Features construídas para CanvasManager (ferramentas de desenho) NÃO disponíveis no preview live
- Se necessário, implementar equivalente em LivePreviewWindow

### Implementação
- Lógica: `LiveCameraCoordinator` → `LiveCameraService`
- Display: `LivePreviewWindow` via `root.after()`
- Eventos: NÃO usa `Events.UI_DISPLAY_FRAME`
```

### 2. `src/zebtrack/core/live_camera_service.py`

- Adicionar docstring explicando divergência

### 3. Criar `docs/decisions/ADR-004-live-camera-divergence.md`

- Architecture Decision Record formal

---

## Estratégia de Testes - Validação Contínua

### Após Cada Etapa

```bash
# 1. Testes unitários do componente modificado
poetry run pytest tests/[component]/ -v

# 2. Testes de integração
poetry run pytest tests/integration/ -v -k "[feature]"

# 3. Fast suite (pre-commit)
poetry run pytest -q

# 4. Full suite (antes de merge)
poetry run pytest -m "" -n0  # Todos 2568 testes
```

### Categorias Críticas

1. **Sistema de Eventos** - Validação de payload, matching de subscrições
2. **Orchestrator/Coordinator** - Equivalência de métodos, callbacks, estado
3. **Integração** - Vídeo único, processamento de projeto, live camera, wizard
4. **Regressão** - Workflows existentes, responsividade UI, memória/threads

**Cobertura:** Mínimo 70% (enforced), Alvo 75% pós-refactor

---

## Mitigação de Riscos

### Áreas de Alto Risco

### 1. Remoção de VideoProcessingOrchestrator

- **Risco:** Quebrar workflows de vídeo
- **Mitigação:**
  - Testes de integração abrangentes antes/depois
  - Testes manuais na GUI
  - Manter comentado 1 semana antes de deletar

### 2. Mudanças de Payload de Eventos

- **Risco:** Falhas silenciosas
- **Mitigação:**
  - Corrigir todos publishers antes de remover código defensivo
  - Adicionar testes de validação de payload
  - Type checking no event bus

### 3. Migração de Testes

- **Risco:** Perder cobertura
- **Mitigação:**
  - Migrar testes ANTES de deletar orchestrators
  - Verificar cobertura equivalente
  - Adicionar testes de edge cases

### Estratégia de Rollback

### Por fase

- Git branching: Cada fase em branch separado
- Granularidade de commit: Pequenos, atômicos (max 500 linhas)
- Checkpoints: Tag releases após fases principais
- **Gatilhos de rollback:** Falhas de teste, novos bugs, perda de >10% performance

### Rollback emergencial

```bash
git revert <phase_commit_range>
# Ou reset hard se não foi pushed
git reset --hard <before_phase_tag>
```

---

## Critérios de Sucesso

### Fase 1

- ✅ Todos eventos usam estrutura de payload correta
- ✅ Código defensivo de EventDispatcher removido
- ✅ Sem subscrições/publicações mortas
- ✅ Todos 2568 testes passam

### Fase 2

- ✅ Zero conflitos de import
- ✅ Type hints de ProcessingCoordinator corretos
- ✅ Todos testes passam
- ✅ Documentação atualizada

### Fase 3

- ✅ Todos 9 orchestrators deletados
- ✅ Lógica em Phase 3 coordinators
- ✅ Diretório orchestrators/ removido
- ✅ Todos testes passam (2568)
- ✅ Sem referências a orchestrator em MainViewModel
- ✅ Cobertura ≥70%

### Fase 4

- ✅ Divergência documentada
- ✅ ADR criado
- ✅ Comentários de código adicionados

### Geral

- ✅ Zero breaking changes para workflows de usuário
- ✅ CI/CD passa
- ✅ Testes manuais de GUI confirmam funcionalidade
- ✅ Sem regressões de performance

---

## Arquivos Críticos para Implementação

### Prioridade Máxima (Fases 1-2, Semanas 1-2)

1. **`src/zebtrack/orchestrators/video_processing_orchestrator.py`**
   - Corrigir payload: linhas 334-337, 401-405
   - Mais crítico para Fase 3

2. **`src/zebtrack/orchestrators/analysis_orchestrator.py`**
   - Corrigir payload: linhas 158-161
   - Segundo mais crítico para Fase 3

3. **`src/zebtrack/ui/components/event_dispatcher.py`**
   - Remover adapter defensivo: linhas 388-395
   - Crítico para sistema de eventos limpo

4. **`src/zebtrack/core/ui_coordinator.py`**
   - Renomear para `ui_scheduler.py`, classe para `UIScheduler`
   - Resolve colisão de nomes

5. **`docs/SYSTEM_INTEGRATION_MAP.md`**
   - Documentar mudanças de payload de eventos
   - Fonte de verdade para agentes AI

### Prioridade Fase 3 (Semanas 3-8)

1. **`src/zebtrack/coordinators/processing_coordinator.py`**
   - Alvo para lógica migrada de orchestrators
   - Já tem 1400+ linhas, vai crescer

2. **`src/zebtrack/core/application_bootstrapper.py`**
   - Remover instantiation de orchestrators: linhas 444-625
   - Crítico para limpeza de DI

3. **`src/zebtrack/core/main_view_model.py`**
   - Substituir calls de orchestrator por coordinator
   - Hub central para workflows

---

## Cronograma de Execução

```text
Semana 1-2:  Fase 1 - Payload Mismatch & Eventos Mortos (✅ Baixo Risco)
Semana 2:    Fase 2 - Colisão UICoordinator (✅ Baixo Risco)
Semana 3:    Fase 3.1 - Auditoria Orchestrators (✅ Zero Risco - Read-only)
Semana 4:    Fase 3.2 - VideoProcessingOrchestrator (⚠️ Alto Risco)
Semana 5:    Fase 3.3 - AnalysisOrchestrator (⚠️ Médio Risco)
Semana 6:    Fase 3.4a - Zone/Config/Calibration (⚠️ Médio Risco)
Semana 7:    Fase 3.4b - Recording/Project (⚠️ Médio Risco)
Semana 8:    Fase 3.4c - UIState/Diagnostics + Limpeza (⚠️ Médio Risco)
Semana 9:    Fase 4 - Documentação Live Camera (✅ Baixo Risco)

Total: 6-8 semanas (ajustável baseado em tolerância a risco)
```

---

## Questões em Aberto (Para Confirmação)

Antes de iniciar implementação, confirmar:

1. **Prioridade de Remoção de Orchestrators:** Começar com VideoProcessingOrchestrator (maior risco) ou orchestrators menores (zone, config) para ganhar confiança?

2. **Cobertura de Testes:** Mínimo de 70% aceitável, ou alvo maior durante refactor?

3. **Fluxo Live Camera:** Documentar divergência (recomendado) ou unificar com CanvasManager?

4. **Breaking Changes:** Plano assume zero breaking changes. Requisito estrito ou aceita mudanças menores com guia de migração?

5. **Ritmo de Execução:** 6-8 semanas assume 1-2 dias por orchestrator. Podemos dedicar este tempo, ou espalhar por período mais longo?

---

## Conclusão

Este plano fornece um **caminho seguro e incremental**para corrigir todas 5 vulnerabilidades mantendo os 2,568 testes funcionando. O trabalho mais crítico é a Fase 3 (remoção de orchestrators legados), que eliminará**4,579 linhas** de código duplicado.

### Ordem de execução recomendada

1. **Quick wins primeiro** (Fases 1-2) - Ganhar confiança, risco mínimo
2. **Auditoria antes de refactor** (Fase 3.1) - Entender dependências
3. **Migração incremental** (Fases 3.2-3.5) - Um orchestrator por vez
4. **Documentar decisões** (Fase 4) - Capturar escolhas arquiteturais

### Fatores-chave de sucesso

- Testes contínuos a cada etapa
- Commits pequenos e atômicos para rollback fácil
- Atualizações abrangentes de documentação
- Testes manuais de GUI junto com testes automatizados

### Pronto para prosseguir com Fase 1
