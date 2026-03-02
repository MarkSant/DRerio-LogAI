# Plano de Remediação — 7 Críticas da Auditoria Técnica

> **Criado**: 2026-03-01
> **Origem**: Auditoria CTO-level do repositório ZebTrack-AI
> **Execução**: 4 fases independentes, cada uma executável por um agente distinto

---

## Visão Geral das Críticas

| #   | Crítica                                      | Fase |
| --- | -------------------------------------------- | ---- |
| 8.5 | Legacy Artifacts não removidos               | 1    |
| 8.4 | Coverage gaps em coordinators/fluxos         | 1    |
| 8.2 | Event Payloads `dict[str, Any]`              | 2    |
| 8.6 | Duas `create_project()` C901                 | 3    |
| 8.7 | WidgetFactory 1467 linhas                    | 3    |
| 8.3 | MainViewModel God Object (872 linhas)        | 4    |
| 8.1 | `__main__.py` Composition Root (789 linhas)  | 4    |

---

## Fase 1 — Limpeza e Cobertura (Risco zero, ganho imediato)

**Objetivo**: Remover dead code e preencher gaps de coverage nos fluxos críticos.

**Agente deve receber este contexto**:

> Fase de limpeza e testes. Não alterar lógica de negócio.

### Tarefa 1.1 — Remover Legacy Artifacts (Crítica 8.5)

1. **Deletar** o diretório `src/zebtrack/orchestrators/` (contém apenas `__pycache__`)
2. **Deletar** `src/zebtrack/ui/integration_example.py` (87 statements, 0% coverage, nunca importado)
3. **Remover** o dicionário `EVENT_NAME_TO_UIEVENT` em `src/zebtrack/ui/event_bus_v2.py`
   - Buscar todas as referências a `EVENT_NAME_TO_UIEVENT` no codebase e remover chamadas
   - Se houver código que usa o mapping string→enum, migrar para uso direto de `UIEvents` enum
4. **Verificar**: `poetry run ruff check .` e `poetry run pytest -q` devem passar sem erros

### Tarefa 1.2 — Integration Tests para Fluxos Críticos (Crítica 8.4)

Escrever integration tests para os 5 fluxos que têm 0% coverage nos coordinators:

1. **Load Project**: `ProjectLifecycleCoordinator.create_project()` → `ProjectManager` → `StateManager`
2. **Process Video**: `VideoProcessingCoordinator.process_pending_project_videos()` → `ProcessingWorker`
3. **Generate Report**: `ReportGenerationCoordinator` → `AnalysisService` → `Reporter`
4. **Live Camera**: `LiveCameraSessionCoordinator` → `LiveCameraService` → `Recorder`
5. **Multi-Aquarium**: `MultiAquariumCoordinator` → `SequentialProcessingCoordinator`

**Regras**:

- Usar mocks para I/O (disco, câmera, GPU) mas exercitar a cadeia coordinator→service→state real
- Colocar em `tests/integration/test_coordinator_flows.py`
- Marcar com `@pytest.mark.integration`
- Target: cada fluxo com pelo menos 1 happy path + 1 error path test

**Verificar**: `poetry run pytest tests/integration/test_coordinator_flows.py -v`

---

## Fase 2 — Tipar Event Payloads (Risco baixo-médio, alto impacto de qualidade)

**Objetivo**: Substituir `dict[str, Any]` por dataclasses tipados em todos os 130+ eventos.

**Agente deve receber este contexto**:

> Refatoração de type safety no event bus. Abordagem incremental por domínio.

### Tarefa 2.1 — Criar Payload Dataclasses

1. Criar `src/zebtrack/ui/payloads.py` (se não existir, ou expandir o existente)
2. Para cada grupo de eventos, criar dataclasses tipados:

   ```text
   ZONE_* events → ZonePayloads (ZoneAutoDetectSuccess, ZoneAquariumSelected, etc.)
   PROCESSING_* events → ProcessingPayloads (ProcessingStarted, ProcessingProgress, etc.)
   PROJECT_* events → ProjectPayloads (ProjectLoaded, ProjectCreated, etc.)
   UI_* events → UIPayloads (UIStateChanged, etc.)
   ```

3. Cada dataclass deve ter campos explícitos com tipos (Path, int, list, etc.)

### Tarefa 2.2 — Atualizar EventBusV2

1. Modificar `EventBusV2.publish()` para aceitar payload tipado:

   ```python
   def publish(self, event: UIEvents, data: EventPayload | dict[str, Any] | None = None) -> None:
   ```

2. Manter backward compatibility — aceitar tanto dataclass quanto dict durante migração
3. Adicionar `TypeAlias` ou `Protocol` para `EventPayload` base

### Tarefa 2.3 — Migrar Handlers (Incremental)

1. Migrar handlers por domínio: Zone → Processing → Project → UI
2. Em cada handler, substituir `data["key"]` por `payload.key`
3. Manter testes passando a cada domínio migrado

**Verificar**: `poetry run pytest -q` + `poetry run mypy src/zebtrack/ui/event_bus_v2.py src/zebtrack/ui/payloads.py`

---

## Fase 3 — Decomposição de Módulos Gigantes (Risco médio)

**Objetivo**: Resolver críticas 8.6 (duas `create_project` C901) e 8.7 (WidgetFactory 1467 linhas).

**Agente deve receber este contexto**:

> Refatoração estrutural de arquivos grandes. Manter API pública idêntica.
> OBRIGATÓRIO: Rodar `python scripts/impact_analyzer.py` antes de cada mudança.

### Tarefa 3.1 — Unificar `create_project()` (Crítica 8.6)

**Problema**: `project_lifecycle_coordinator.py:255` e `project_workflow_service.py:356` ambos têm `create_project()` com `noqa: C901`.

1. Analisar ambas as implementações e identificar:
   - Qual é o "owner" da lógica de criação?
   - Qual é apenas um adapter/delegator?
2. **Decisão esperada**: `ProjectWorkflowService.create_project()` deve ser o owner único
3. `ProjectLifecycleCoordinator.create_project()` deve delegar para `ProjectWorkflowService` sem duplicar lógica
4. Decompor a implementação restante em sub-métodos com responsabilidades claras:
   - `_validate_project_input()`
   - `_create_project_structure()`
   - `_persist_project_data()`
   - `_emit_project_created_event()`
5. Remover `noqa: C901` de ambos após decomposição

### Tarefa 3.2 — Decompor WidgetFactory (Crítica 8.7)

**Problema**: `ui/components/widget_factory.py` tem 1467 linhas — SRP violation.

1. Ler o arquivo e categorizar métodos por domínio funcional
2. Criar sub-factories por domínio:
   - `ui/builders/zone_widgets.py` — widgets de zona/aquário
   - `ui/builders/analysis_widgets.py` — widgets de análise/métricas
   - `ui/builders/project_widgets.py` — widgets de projeto/navegação
   - `ui/builders/common_widgets.py` — widgets genéricos reutilizáveis
3. `widget_factory.py` passa a ser um facade fino que importa e delega para sub-factories
4. Target: nenhum arquivo resultante >400 linhas, `widget_factory.py` <100 linhas

**Verificar**: `poetry run pytest -q` + `poetry run ruff check .` + nenhum `noqa: C901` remanescente

---

## Fase 4 — Refatorar Core Architecture (Risco alto, maior impacto)

**Objetivo**: Resolver críticas 8.1 (`__main__.py` monolítico) e 8.3 (MainViewModel God Object).

**Agente deve receber este contexto**:

> Refatoração arquitetural do Composition Root e MainViewModel.
> OBRIGATÓRIO: Rodar `python scripts/impact_analyzer.py` antes de cada mudança.
> Manter todos os 2778+ testes passando a cada step.

### Tarefa 4.1 — Decompor MainViewModel (Crítica 8.3)

**Problema**: 872 linhas, ~40 facade methods, runtime flags, 5 dispatch modes.

1. **Migrar runtime flags** para `StateManager`:
   - `processing_thread` → `StateManager.ProcessingState`
   - `pending_single_video_analysis` → `StateManager.ProcessingState`
   - `is_capturing_for_video` → `StateManager.RecordingState`
2. **Eliminar facade methods** — os ~40 métodos que apenas delegam para sub-VMs:
   - Se o caller pode acessar o sub-VM diretamente (via container), remover a indireção
   - Se não pode, manter apenas os essenciais
3. **Simplificar `_EVENT_METHOD_MAPPING`** — substituir 5 dispatch modes por pattern matching:

   ```python
   def _handle_event(self, event: UIEvents, data: EventPayload) -> None:
       match event:
           case UIEvents.PROJECT_LOADED: self._on_project_loaded(data)
           case UIEvents.PROCESSING_START: self._on_processing_start(data)
           ...
   ```

4. Target: MainViewModel <400 linhas

### Tarefa 4.2 — Introduzir DI Container em `__main__.py` (Crítica 8.1)

**Problema**: 789 linhas de wiring imperativo com post-construction injection.

1. **Avaliar**: `punq` (200 LOC, zero deps) ou `dependency-injector` como candidatos
2. **Instalar**: `poetry add punq` (ou o escolhido)
3. **Criar módulo de registrations**: `src/zebtrack/core/di_registrations.py`
   - Cada grupo de serviços registrado como factory functions:

     ```python
     container.register(DetectorService, factory=lambda: DetectorService(...))
     container.register(ProjectManager, factory=...)
     ```

4. **Migrar `__main__.py`**:
   - Substituir criação manual por `container.resolve(MainViewModel)`
   - Eliminar post-construction injection — resolver ciclos via `LazyRef` registrado no container
   - Target: `__main__.py` <150 linhas (resolve container + root.mainloop)
5. **Manter `ApplicationBootstrapper`** como coordinator de inicialização (hardware detection, model loading), mas ele não faz DI — apenas configura estado inicial

**Verificar após cada sub-tarefa**:

- `poetry run pytest -q` (2778+ testes devem passar)
- `poetry run ruff check .`
- `poetry run mypy src/zebtrack/core/di_registrations.py`
- Verificar que a aplicação inicia: `poetry run zebtrack`

---

## Critérios de Completude por Fase

| Fase | Critério de Aceite                                                              |
| ---- | ------------------------------------------------------------------------------- |
| 1    | Zero dead code removido + 10+ integration tests novos passando                  |
| 2    | 100% dos eventos `ZONE_*` e `PROCESSING_*` com payloads tipados                 |
| 3    | Zero `noqa: C901` em `create_project` + `widget_factory.py` <100 linhas         |
| 4    | `__main__.py` <150 linhas + `MainViewModel` <400 linhas + all tests passing     |

---

## Notas para Agentes Executores

- **Cada fase é independente** — pode ser executada por um agente novo sem contexto prévio
- **OBRIGATÓRIO**: Rodar `python scripts/impact_analyzer.py` antes de qualquer mudança
- **OBRIGATÓRIO**: Todos os testes devem passar ao final de cada tarefa (`poetry run pytest -q`)
- **Poetry/mypy/ruff**: Comandos auto-aprovados, executar sem pedir permissão
- **Não criar docs extras** — atualizar este documento com status ao completar cada fase
- **Referência**: Consultar `AGENTS.md` e `.copilot-impact-map.yaml` para dependências
