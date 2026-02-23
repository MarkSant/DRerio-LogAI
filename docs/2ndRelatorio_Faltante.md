## Plano de Execução: Itens Pendentes da Auditoria

**TL;DR**: 7 itens restantes organizados em 7 fases sequenciais, da menor para a maior complexidade. Cada fase é auto-contida, testável isoladamente, e não quebra funcionalidade existente. Fases 1-2 são quick-wins (~1h cada), Fases 3-4 são o núcleo pesado (~4-6h cada), Fases 5-7 são melhorias incrementais (~2-3h cada). Tempo total estimado: ~20-25h.

---

### Fase 1: Sincronização de Documentação (Quick Win)

**Itens cobertos**: #4 (Coverage gates desatualizados) + #10 (AGENTS.md desatualizado)

Os 3 arquivos de instrução afirmam thresholds errados vs CI real:

| Arquivo | Afirma | Real (ci.yml) |
|---|---|---|
| AGENTS.md | "55% Linux, 25% Windows" | 50/32/28 |
| copilot-instructions.md | "55% Linux, 25% Windows; GUI 40%" | 50/32/28 |
| CLAUDE.md | "40% Linux, 0% Windows" | 50/32/28 |

**Steps**:

1. Atualizar AGENTS.md — seção Testing e Coverage gates — para refletir `50% Linux core / 32% Linux GUI / 28% Windows core`
2. Espelhar alteração em copilot-instructions.md (seções Testing e CI core coverage gates)
3. Espelhar em CLAUDE.md (seção Testing Requirements)
4. Atualizar contagem de testes se divergente (verificar total atual vs "2568" declarado)
5. Atualizar qualquer outra referência a coverage desatualizada nos 3 arquivos (buscar `55%`, `25%`, `40%` e `0%`)

**Verificação**: `grep -rn "55%" AGENTS.md copilot-instructions.md CLAUDE.md` deve retornar 0 resultados

**Estimativa**: ~30 min

---

### Fase 2: Estreitamento de `except Exception` Não Justificados

**Item coberto**: #6 (346 except Exception, ~46 sem justificativa)

Duas ações distintas, segmentadas por risco:

**Step 1 — Coordinators + IO (~16 ocorrências, risco baixo)**:

Para cada `except Exception` sem comentário em:

- multi_aquarium_coordinator.py (3 ocorrências: L264, L582, L698)
- progress_tracking_coordinator.py (L211)
- sequential_processing_coordinator.py (L431)
- video_processing_coordinator.py (5: L146, L164, L686, L735, L782)
- _unified_report_mixin.py (4: L159, L186, L345, L373)
- _video_completion_mixin.py (L226)
- _video_selection_mixin.py (L311)
- report_generation_coordinator.py (3: L125, L505, L639)
- recorder.py (L1102)
- arduino_manager.py (L66, L245)

Para cada: analisar o contexto → OU estreitar para tipo específico (`OSError`, `ValueError`, `RuntimeError`) OU adicionar `# except Exception justified: <reason>` como done no Phase 2 anterior.

**Step 2 — UI (~30+ ocorrências, risco médio)**:

Priorizar os piores ofendores:

- wizard/templates.py (6 instâncias)
- wizard/model_selection_step.py (5 instâncias)
- wizard/live_config_step.py (3 instâncias)
- components/roi_template_manager.py (6 instâncias)
- components/validation_manager.py (3 instâncias)
- icon_utils.py (3 instâncias)

Mesma abordagem: estreitar tipo ou justificar.

**Verificação**: `poetry run ruff check . --select S110` (sem novos except...pass) + `poetry run pytest -q` (suite completa passa)

**Estimativa**: ~2h

---

### Fase 3: Redução de `gui.py` — Remoção da Shim Layer

**Item coberto**: #3 (gui.py com 1.480 linhas / 143 métodos)

A pesquisa revelou que **~100 métodos** (~400 linhas) são pure delegation shims — wrappers de 2-4 linhas que fazem forward para componentes já extraídos. Exemplo: `gui.show_error(title, msg)` → `gui.dialog_manager.show_error(title, msg)`.

**Step 1 — Inventário de callers**:

Usar impact analyzer + grep para mapear **cada** shim method e seus callers (MainViewModel, coordinators, tests). Gerar tabela: `shim_name → [caller1:line, caller2:line, ...]`

**Step 2 — Exposição pública dos componentes**:

Garantir que `gui.dialog_manager`, `gui.canvas_manager`, `gui.roi_template_manager`, etc., são atributos públicos acessíveis (já são, verificar).

**Step 3 — Migrar callers por grupo** (ordem de menor para maior impacto):

| Grupo | Shims | Callers estimados | Risco |
|---|---|---|---|
| `DialogManager` (12 shims) | `show_error`, `show_warning`, `show_info`, `ask_ok_cancel`, etc. | Coordinators, MainViewModel | Médio |
| `WeightHardwareManager` (10 shims) | `update_weights_dropdown`, etc. | MainViewModel, DetectorSetupCoordinator | Baixo |
| `ROITemplateManager` (11 shims) | `_refresh_roi_templates`, etc. | ZoneControls, MainViewModel | Baixo |
| `CanvasManager` (13 shims) | `setup_interactive_polygon`, etc. | MainViewModel, EventDispatcher | Médio |
| `AnalysisViewController` (16 shims) | `update_analysis_progress`, etc. | MainViewModel | Baixo |
| Outros (38 shims) | Diversos | Variados | Baixo-Médio |

**Step 4 — Para cada grupo**: atualizar callers → remover shim → rodar testes → commit

**Step 5 — Constructor decomposition**: Extrair `__init__` (280 linhas) em `_init_component_managers()`, `_init_state_variables()`, `_init_event_subscriptions()`

**Step 6 — Mover business logic restante**: `_remove_selected_roi_confirm` (62 linhas), `_get_zone_data_for_active_context` (34 linhas), `_on_apply_roi_settings` (31 linhas) → serviço ou componente adequado

**Step 7 — Remover dead code**: Duplicata em gui.py, 2 métodos `pass`

**Meta**: gui.py de ~1.480 → **~700 linhas** e **~43 métodos** (thin shell)

**Verificação**: `poetry run pytest -m gui -n0` (todos GUI tests passam) + `poetry run pytest -q` (fast suite)

**Estimativa**: ~5h

---

### Fase 4: Migração EventBus v1 → v2

**Item coberto**: #1 (dois buses coexistindo, ~37 source files em v1, ~19 em v2)

Esta é a maior e mais arriscada mudança. Estratégia: **migração incremental por camada, com adapter bridge**.

#### Sub-Fase 4.1 — Criar Adapter Bridge (~1h)

Criar `EventBusAdapter` que implementa a API v1 (`subscribe(str)`, `publish_event(str, dict)`) mas delega internamente para v2 (`subscribe(UIEvents.X)`, `publish(Event(...))`). Mapear todos os event names de events.py (strings) para `UIEvents` enum members em event_bus_v2.py.

**Resultado**: V1 callers continuam funcionando sem mudança, mas eventos fluem via v2 internamente.

#### Sub-Fase 4.2 — Migrar Composition Root (~1h)

Em \_\_main\_\_.py: substituir `event_bus = EventBus()` por `event_bus = EventBusAdapter(EventBusV2())`. Todos os coordinators que recebem `event_bus` via DI continuam funcionando sem mudança.

**Verificação**: `poetry run pytest -q` — suite inteira deve passar sem alteração de comportamento.

#### Sub-Fase 4.3 — Migrar camada `coordinators/` (~2h)

Migrar os 15+ coordinators que usam v1 (a maioria via `TYPE_CHECKING` — impacto real é nas chamadas `self.event_bus.publish_event(name, data)`):

- Substituir `publish_event(str, dict)` por `publish(Event(UIEvents.X, data))`
- Atualizar imports de `EventBus` → `EventBusV2` + `Event` + `UIEvents`
- Atualizar `BaseCoordinator` typehint de `EventBus` → `EventBusV2`

#### Sub-Fase 4.4 — Migrar camada `ui/components/` (~2h)

Migrar os 12+ componentes que ainda usam v1 diretamente:

- `event_dispatcher.py` (815 linhas, é o **v1 runtime engine**) — refactoring mais pesado: substituir poll loop por subscriptions diretas em v2
- `zone_controls.py`, `control_panel.py`, `config_editor.py`, `video_display.py`, etc.

#### Sub-Fase 4.5 — Migrar `wizard/`, `dialogs/`, `core/services/` (~1h)

Migrar os importadores restantes (maioria `TYPE_CHECKING` only).

#### Sub-Fase 4.6 — Remover v1 + Adapter (~30min)

- Deletar event_bus.py (316 linhas)
- Deletar `EventBusAdapter`
- Remover `@deprecated` markers do v2
- Atualizar testes (`test_event_bus_migration.py`, `test_event_bus_phase1.py`)

**Verificação a cada sub-fase**: `poetry run pytest -q` + `poetry run pytest -m gui -n0`

**Estimativa**: ~6h total

---

### Fase 5: Decomposição dos 2 Ficheiros > 1.000 Linhas

**Item coberto**: #9

#### 5A — `reports_tree_manager.py` (1.036 linhas, 33 métodos)

Pesquisa identificou 5 clusters claros. Extrair em 3 módulos dentro de ui/components/project_views/:

| Módulo novo | Métodos | Linhas estimadas |
|---|---|---|
| `report_tree_builder.py` | `_populate_reports_tree_from_hierarchy` + 5 insert methods | ~300 |
| `report_generator_actions.py` | `handle_report_video_node`, `generate_unified_report`, `generate_partial_report`, `_resolve_unified_generation_strategy` | ~250 |
| `report_asset_actions.py` | `_delete_video_asset`, `_delete_all_processing_data`, `_delete_video_from_project`, `_delete_all_unified_reports` | ~180 |

`ReportsTreeManager` permanece como facade fina (~300 linhas) com event handling + delegation.

#### 5B — `project_lifecycle_coordinator.py` (1.085 linhas, 38 métodos)

4 grupos identificados. Extrair:

| Módulo novo | Métodos | Linhas estimadas |
|---|---|---|
| `model_override_service.py` (em `core/services/`) | `apply_project_model_overrides`, `save_project_model_overrides`, `resolve_project_model_settings`, `copy_global_model_settings_to_project`, helpers | ~200 |
| `calibration_coordinator.py` (em `coordinators/`) | `save_current_calibration_to_project`, `get_calibration_scope_info`, `build_calibration_context`, `global_calibration_session`, `project_calibration_session` | ~250 |

`ProjectLifecycleCoordinator` mantém lifecycle (create/open/close) + asset management (~600 linhas).

**Verificação**: `poetry run pytest -q` + impact analyzer nos ficheiros modificados

**Estimativa**: ~3h

---

### Fase 6: Resolver padrão `__new__` Two-Phase Init

**Item coberto**: #5

O pattern em `__main__.py` existe porque `ApplicationBootstrapper.initialize()` precisa de uma referência ao `controller_proxy` antes do `__init__` rodar — para que coordinators criados durante bootstrap tenham uma back-reference.

**Abordagem**: Lazy DI Container com property injection.

**Steps**:

1. Expandir dependency_container.py com um `LazyRef[T]` — um proxy que resolve na primeira chamada a `.get()`, permitindo referências circulares declarativas
2. `MainViewModelDependencies` passa a conter `controller_ref: LazyRef[MainViewModel]` em vez de referência direta
3. Coordinators recebem `LazyRef` e acessam via `self.controller_ref.get()` quando precisam (após init completo)
4. Em `__main__.py`: instanciar `MainViewModel` normalmente (`__init__` direto), sem `__new__`; o `LazyRef` é resolvido automaticamente após construção
5. Remover o bloco manual de patching `.view` em `__main__.py`

**Verificação**: `poetry run pytest -q` + verificar que o app inicia corretamente (`poetry run zebtrack`)

**Estimativa**: ~3h

---

### Fase 7: OpenVINO Batch Inference

**Item coberto**: #7

Atualmente o openvino_detector.py herda o fallback sequencial de `base.py` para `detect_batch()`.

**Steps**:

1. Ler a API OpenVINO para `AsyncInferQueue` — permite N infer requests assíncronos em paralelo
2. Implementar `detect_batch()` override em `OpenVINODetectorPlugin`:
   - Criar `AsyncInferQueue` com `nireq=batch_size`
   - Submeter todos os frames pré-processados
   - Coletar resultados na callback com preservação de ordem
   - Pós-processar resultados no formato padrão `list[list[dict]]`
3. Adicionar testes unitários com mock do modelo OpenVINO
4. Adicionar benchmark comparativo (sequencial vs batch) em debug

**Verificação**: `poetry run pytest -q` + benchmark mostrando speedup

**Estimativa**: ~3h

---

### Resumo Sequencial

| Fase | Item(s) | Escopo | Risco | Estimativa |
|:---:|---|---|:---:|---:|
| **1** | #4, #10 | Sync docs (coverage gates + contagens) | Nulo | 30 min |
| **2** | #6 | Estreitar/justificar ~46 `except Exception` | Baixo | 2h |
| **3** | #3 | Remover ~100 shims de gui.py (1.480→~700 linhas) | Médio | 5h |
| **4** | #1 | Migrar EventBus v1→v2 (37 ficheiros) | Alto | 6h |
| **5** | #9 | Decompor 2 ficheiros >1K linhas | Baixo | 3h |
| **6** | #5 | Eliminar `__new__` pattern com LazyRef DI | Médio | 3h |
| **7** | #7 | Implementar OpenVINO batch inference | Baixo | 3h |
| | | **Total** | | **~22.5h** |

**Nota**: Item #8 (Dependabot) **já está implementado** — dependabot.yml existe com ecosystems `pip` + `github-actions`. Removido do plano.

**Verificação global ao final**: `poetry run pytest -m "" -n0` (todos os ~2568 testes) + `poetry run ruff check .` + `poetry run pre-commit run --all-files`
