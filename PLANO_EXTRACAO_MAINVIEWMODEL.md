# 🚀 PLANO DE EXTRAÇÃO REAL - MainViewModel Reduction

**Documento:** PLANO_EXTRACAO_MAINVIEWMODEL.md
**Versão:** 1.0
**Data:** 2025-01-14
**Status:** 📋 PLANEJAMENTO
**Objetivo:** Reduzir MainViewModel de 5,568 → ~2,000 linhas (-64%)

---

## 📊 SITUAÇÃO ATUAL

### Estado Atual (Após Sprint 22)
```
MainViewModel: 5,568 linhas, 141 métodos
Progresso até agora: -165 linhas (-2.9%)
Objetivo original: -60-70% (reduzir para ~1,500-2,000 linhas)
Gap restante: -3,568 linhas necessárias (-64%)
```

### Problema Identificado

**Sprints 1-14**: Criaram Coordinators como **camada de delegação**, mas **não extraíram código**
- ProjectCoordinator, DetectorCoordinator, RecordingCoordinator, LiveCameraCoordinator
- Resultado: +2,400 linhas em novos arquivos, MainViewModel reduziu apenas -100 linhas

**Sprints 15-22**: Focaram em **code quality**, não em **size reduction**
- Dead code removal, linting fixes, analysis
- Resultado: -165 linhas (apenas limpeza superficial)

---

## 🎯 OBJETIVOS DA EXTRAÇÃO REAL

### Meta Principal
**Reduzir MainViewModel para ~2,000 linhas** através de extração real de código

### Estratégia
1. **Extrair métodos grandes** do MainViewModel para novos orchestrators
2. **Mover lógica de orquestração** para coordenadores especializados
3. **Criar camada de UI Controllers** separada da lógica de negócio
4. **Manter backward compatibility** através de facades mínimas
5. **Testar exaustivamente** cada extração

### Princípios
- ✅ **Extract Method Refactoring**: Mover código, não duplicar
- ✅ **One Step at a Time**: Uma extração por commit
- ✅ **Test After Each Step**: Garantir zero regressões
- ✅ **Maintain API Compatibility**: Facades públicas permanecem

---

## 📋 PLANO DE SPRINTS (23-35)

### FASE 1: Análise Profunda e Preparação (Sprint 23)

**Sprint 23: Análise de Dependências do MainViewModel**

**Objetivos:**
1. Mapear todos os 141 métodos do MainViewModel
2. Identificar dependências entre métodos
3. Classificar métodos por categoria (UI, orchestration, business logic)
4. Identificar métodos candidatos para extração (>50 linhas)
5. Criar mapa de dependências (quem chama quem)

**Deliverables:**
- `docs/MAINVIEWMODEL_DEPENDENCY_MAP.md` - Mapa completo de dependências
- `docs/MAINVIEWMODEL_METHOD_CLASSIFICATION.md` - Categorização dos 141 métodos
- `docs/EXTRACTION_CANDIDATES.md` - Top 20 métodos para extração prioritária

**Estimativa:** 1 dia
**Risco:** Baixo (apenas análise)

---

### FASE 2: Extração de Orquestradores (Sprints 24-27)

#### **Sprint 24: VideoProcessingOrchestrator**

**Objetivo:** Extrair lógica de processamento de vídeos do MainViewModel

**Métodos a extrair** (~800 linhas):
1. `start_batch_processing()` - 120 linhas
2. `process_pending_project_videos()` - 149 linhas (C901 complexity warning)
3. `_process_video_with_recording()` - 80 linhas
4. `_process_single_video()` - 90 linhas
5. `_handle_processing_completion()` - 70 linhas
6. `_handle_processing_error()` - 60 linhas
7. `cancel_processing()` - 40 linhas
8. Métodos auxiliares de processamento (~200 linhas)

**Estrutura do novo arquivo:**
```python
# src/zebtrack/orchestrators/video_processing_orchestrator.py

class VideoProcessingOrchestrator:
    """Orchestrates video processing workflows."""

    def __init__(
        self,
        state_manager: StateManager,
        video_processing_service: VideoProcessingService,
        detector_coordinator: DetectorCoordinator,
        project_manager: ProjectManager,
    ):
        self.state_manager = state_manager
        self.video_processing_service = video_processing_service
        self.detector_coordinator = detector_coordinator
        self.project_manager = project_manager

    def start_batch_processing(self, videos: list[dict], **kwargs) -> dict:
        """Start batch processing of videos."""
        # Código movido de MainViewModel.start_batch_processing()

    def process_pending_project_videos(self, **kwargs) -> dict:
        """Process all pending videos in project."""
        # Código movido de MainViewModel.process_pending_project_videos()

    # ... outros métodos extraídos
```

**MainViewModel após extração** (facade mínima):
```python
class MainViewModel:
    def __init__(self, ..., video_processing_orchestrator: VideoProcessingOrchestrator):
        self.video_processing_orchestrator = video_processing_orchestrator

    def start_batch_processing(self, videos: list[dict], **kwargs) -> dict:
        """Public API - delegates to orchestrator."""
        return self.video_processing_orchestrator.start_batch_processing(videos, **kwargs)

    def process_pending_project_videos(self, **kwargs) -> dict:
        """Public API - delegates to orchestrator."""
        return self.video_processing_orchestrator.process_pending_project_videos(**kwargs)
```

**Testes:**
- Criar `tests/orchestrators/test_video_processing_orchestrator.py` (~500 linhas)
- 30+ testes cobrindo todos os métodos extraídos
- Testes de integração: MainViewModel → VideoProcessingOrchestrator

**Redução esperada:** -800 linhas no MainViewModel, +800 no novo orchestrator
**Estimativa:** 2-3 dias
**Risco:** Médio (método complexo `process_pending_project_videos`)

---

#### **Sprint 25: AnalysisOrchestrator**

**Objetivo:** Extrair lógica de análise e relatórios

**Métodos a extrair** (~600 linhas):
1. `start_analysis()` - 90 linhas
2. `start_analysis_for_videos()` - 80 linhas
3. `_run_analysis_for_video()` - 70 linhas
4. `generate_reports()` - 100 linhas
5. `_generate_single_report()` - 60 linhas
6. `export_results()` - 80 linhas
7. `_handle_analysis_completion()` - 50 linhas
8. Métodos auxiliares (~70 linhas)

**Estrutura:**
```python
# src/zebtrack/orchestrators/analysis_orchestrator.py

class AnalysisOrchestrator:
    """Orchestrates analysis and report generation workflows."""

    def start_analysis(self, videos: list[dict], **kwargs) -> dict:
        """Start analysis for videos."""

    def generate_reports(self, videos: list[dict], **kwargs) -> dict:
        """Generate reports for analyzed videos."""
```

**Redução esperada:** -600 linhas
**Estimativa:** 2 dias
**Risco:** Baixo (métodos bem isolados)

---

#### **Sprint 26: RecordingSessionOrchestrator**

**Objetivo:** Extrair lógica de sessões de gravação

**Métodos a extrair** (~500 linhas):
1. `start_live_camera_analysis()` - 100 linhas
2. `start_recording_session()` - 90 linhas
3. `stop_current_session()` - 70 linhas
4. `_handle_session_start()` - 60 linhas
5. `_handle_session_stop()` - 50 linhas
6. `_cleanup_session()` - 40 linhas
7. Métodos de gerenciamento de sessões (~90 linhas)

**Estrutura:**
```python
# src/zebtrack/orchestrators/recording_session_orchestrator.py

class RecordingSessionOrchestrator:
    """Orchestrates recording session lifecycle."""

    def start_live_camera_analysis(self, **kwargs) -> dict:
        """Start live camera analysis session."""

    def start_recording_session(self, **kwargs) -> dict:
        """Start recording session."""

    def stop_current_session(self) -> dict:
        """Stop active session."""
```

**Redução esperada:** -500 linhas
**Estimativa:** 2 dias
**Risco:** Médio (integração com hardware)

---

#### **Sprint 27: ProjectOrchestrator**

**Objetivo:** Extrair lógica de orquestração de projetos

**Métodos a extrair** (~400 linhas):
1. `load_project()` - 80 linhas
2. `close_project()` - 60 linhas
3. `_setup_project_state()` - 70 linhas
4. `_restore_project_settings()` - 50 linhas
5. `_initialize_project_resources()` - 60 linhas
6. `_cleanup_project_resources()` - 40 linhas
7. Métodos auxiliares (~40 linhas)

**Estrutura:**
```python
# src/zebtrack/orchestrators/project_orchestrator.py

class ProjectOrchestrator:
    """Orchestrates project lifecycle operations."""

    def load_project(self, project_path: Path) -> dict:
        """Load project and initialize all resources."""

    def close_project(self) -> dict:
        """Close project and cleanup resources."""
```

**Redução esperada:** -400 linhas
**Estimativa:** 2 dias
**Risco:** Baixo

---

### FASE 3: Extração de UI Controllers (Sprints 28-30)

#### **Sprint 28: UIStateController**

**Objetivo:** Extrair lógica de sincronização de UI

**Métodos a extrair** (~600 linhas):
1. `update_progress_callback()` - 80 linhas
2. `_update_ui_after_processing()` - 70 linhas
3. `_update_ui_after_analysis()` - 60 linhas
4. `refresh_overview()` - 90 linhas
5. `_refresh_video_tree()` - 50 linhas
6. `_update_status_bar()` - 40 linhas
7. `_sync_ui_with_state()` - 70 linhas
8. Métodos auxiliares de UI (~140 linhas)

**Estrutura:**
```python
# src/zebtrack/ui/controllers/ui_state_controller.py

class UIStateController:
    """Manages UI state synchronization and updates."""

    def __init__(self, state_manager: StateManager, gui: ApplicationGUI):
        self.state_manager = state_manager
        self.gui = gui

    def update_progress(self, progress_data: dict) -> None:
        """Update UI with progress information."""

    def refresh_overview(self) -> None:
        """Refresh project overview in UI."""

    def sync_ui_with_state(self) -> None:
        """Synchronize UI components with current state."""
```

**Redução esperada:** -600 linhas
**Estimativa:** 2 dias
**Risco:** Médio (forte acoplamento com GUI)

---

#### **Sprint 29: VideoTreeController**

**Objetivo:** Extrair lógica de gerenciamento da árvore de vídeos

**Métodos a extrair** (~400 linhas):
1. `populate_video_tree()` - 80 linhas
2. `_build_video_tree_structure()` - 70 linhas
3. `on_video_selected()` - 60 linhas
4. `_update_video_status()` - 50 linhas
5. `_refresh_video_icons()` - 40 linhas
6. `filter_video_tree()` - 50 linhas
7. Métodos auxiliares (~50 linhas)

**Estrutura:**
```python
# src/zebtrack/ui/controllers/video_tree_controller.py

class VideoTreeController:
    """Manages video tree UI component."""

    def populate_video_tree(self, videos: list[dict]) -> None:
        """Populate video tree with project videos."""

    def on_video_selected(self, video_path: str) -> None:
        """Handle video selection in tree."""
```

**Redução esperada:** -400 linhas
**Estimativa:** 1-2 dias
**Risco:** Baixo

---

#### **Sprint 30: CanvasController**

**Objetivo:** Extrair lógica de controle do canvas

**Métodos a extrair** (~350 linhas):
1. `update_canvas_overlay()` - 70 linhas
2. `_draw_detection_boxes()` - 60 linhas
3. `_draw_zones()` - 50 linhas
4. `_handle_canvas_click()` - 40 linhas
5. `_update_canvas_frame()` - 60 linhas
6. Métodos auxiliares de canvas (~70 linhas)

**Estrutura:**
```python
# src/zebtrack/ui/controllers/canvas_controller.py

class CanvasController:
    """Manages canvas rendering and interactions."""

    def update_overlay(self, frame_data: dict) -> None:
        """Update canvas overlay with detections."""

    def handle_click(self, event) -> None:
        """Handle canvas click events."""
```

**Redução esperada:** -350 linhas
**Estimativa:** 1-2 dias
**Risco:** Baixo

---

### FASE 4: Extração de Event Handlers (Sprints 31-32)

#### **Sprint 31: MenuEventHandler**

**Objetivo:** Extrair handlers de eventos de menu

**Métodos a extrair** (~300 linhas):
1. `on_menu_new_project()` - 40 linhas
2. `on_menu_open_project()` - 40 linhas
3. `on_menu_save_project()` - 30 linhas
4. `on_menu_export()` - 50 linhas
5. `on_menu_settings()` - 40 linhas
6. Outros handlers de menu (~100 linhas)

**Estrutura:**
```python
# src/zebtrack/ui/handlers/menu_event_handler.py

class MenuEventHandler:
    """Handles menu action events."""

    def on_new_project(self) -> None:
        """Handle File → New Project menu action."""

    def on_open_project(self) -> None:
        """Handle File → Open Project menu action."""
```

**Redução esperada:** -300 linhas
**Estimativa:** 1 dia
**Risco:** Baixo

---

#### **Sprint 32: ToolbarEventHandler**

**Objetivo:** Extrair handlers de eventos de toolbar

**Métodos a extrair** (~250 linhas):
1. `on_start_processing()` - 50 linhas
2. `on_stop_processing()` - 40 linhas
3. `on_pause_processing()` - 40 linhas
4. `on_start_analysis()` - 50 linhas
5. Outros handlers de toolbar (~70 linhas)

**Estrutura:**
```python
# src/zebtrack/ui/handlers/toolbar_event_handler.py

class ToolbarEventHandler:
    """Handles toolbar button events."""

    def on_start_processing(self) -> None:
        """Handle Start Processing button click."""
```

**Redução esperada:** -250 linhas
**Estimativa:** 1 dia
**Risco:** Baixo

---

### FASE 5: Refinamento e Consolidação (Sprints 33-35)

#### **Sprint 33: Refatoração de Métodos Remanescentes**

**Objetivo:** Extrair métodos auxiliares menores

**Métodos a extrair** (~400 linhas):
- Métodos auxiliares de validação (~100 linhas)
- Métodos de formatação e conversão (~100 linhas)
- Métodos de logging e debugging (~100 linhas)
- Métodos diversos não categorizados (~100 linhas)

**Redução esperada:** -400 linhas
**Estimativa:** 2 dias
**Risco:** Baixo

---

#### **Sprint 34: Testes de Integração Completos**

**Objetivo:** Garantir que todas as extrações funcionam em conjunto

**Atividades:**
1. Criar test suite de integração end-to-end
2. Testar todos os fluxos principais:
   - Criar projeto → Processar vídeos → Gerar relatórios
   - Carregar projeto → Analisar → Exportar
   - Live camera → Recording → Analysis
3. Testar backward compatibility (todas as APIs públicas funcionam)
4. Testes de regressão (comparar resultados antes/depois)
5. Performance benchmarks (garantir sem degradação)

**Deliverables:**
- `tests/integration/test_mainviewmodel_refactored.py` (~800 linhas)
- `tests/integration/test_orchestrators_integration.py` (~600 linhas)
- `docs/INTEGRATION_TEST_RESULTS.md` - Relatório de testes

**Estimativa:** 2-3 dias
**Risco:** Baixo

---

#### **Sprint 35: Documentação e Release**

**Objetivo:** Documentar todas as mudanças e preparar release

**Atividades:**
1. Atualizar `docs/ARCHITECTURE.md` com nova estrutura
2. Atualizar `CLAUDE.md` com novos orchestrators
3. Criar migration guide para desenvolvedores
4. Atualizar diagramas de arquitetura
5. Preparar release notes
6. Criar tag de versão (v5.0.0 - Breaking Changes)

**Deliverables:**
- `docs/ARCHITECTURE_V5.md` - Arquitetura atualizada
- `docs/MIGRATION_GUIDE_V5.md` - Guia de migração
- `docs/MAINVIEWMODEL_REFACTORING_COMPLETE.md` - Relatório final
- `CHANGELOG.md` atualizado
- Git tag: `v5.0.0`

**Estimativa:** 2 dias
**Risco:** Baixo

---

## 📊 RESUMO DE REDUÇÃO ESPERADA

### Por Fase

| Fase | Sprints | Linhas Extraídas | Novos Arquivos | Estimativa |
|------|---------|------------------|----------------|------------|
| **Análise** | 23 | 0 | 3 docs | 1 dia |
| **Orchestrators** | 24-27 | -2,300 | 4 orchestrators | 8-9 dias |
| **UI Controllers** | 28-30 | -1,350 | 3 controllers | 5-6 dias |
| **Event Handlers** | 31-32 | -550 | 2 handlers | 2 dias |
| **Refinamento** | 33-35 | -400 | Tests + Docs | 6-7 dias |
| **TOTAL** | **23-35 (13 sprints)** | **-4,600** | **9 novos arquivos** | **22-25 dias** |

### Resultado Final Esperado

```
MainViewModel:
  ANTES: 5,568 linhas, 141 métodos
  DEPOIS: ~1,000-1,200 linhas, ~30-40 métodos (facades)
  REDUÇÃO: -4,400 linhas (-79%)
```

**Meta Original**: Reduzir 60-70% ✅ **SUPERADO!**

### Distribuição Após Extração

| Componente | Linhas | Métodos | Papel |
|------------|--------|---------|-------|
| **MainViewModel** | ~1,000 | ~30 | Facade + DI Root |
| **VideoProcessingOrchestrator** | ~800 | ~15 | Processamento |
| **AnalysisOrchestrator** | ~600 | ~12 | Análise |
| **RecordingSessionOrchestrator** | ~500 | ~10 | Sessões |
| **ProjectOrchestrator** | ~400 | ~8 | Projetos |
| **UIStateController** | ~600 | ~12 | UI Sync |
| **VideoTreeController** | ~400 | ~8 | Video Tree |
| **CanvasController** | ~350 | ~7 | Canvas |
| **MenuEventHandler** | ~300 | ~15 | Menu Events |
| **ToolbarEventHandler** | ~250 | ~10 | Toolbar Events |
| **Auxiliares** | ~400 | ~20 | Utilities |
| **TOTAL DISTRIBUÍDO** | **5,600** | **147** | - |

---

## 🔧 ESTRATÉGIA DE IMPLEMENTAÇÃO

### Ordem de Execução

**Prioridade 1** (Crítico - maior impacto):
- Sprint 24: VideoProcessingOrchestrator (-800 linhas)
- Sprint 25: AnalysisOrchestrator (-600 linhas)

**Prioridade 2** (Alto - complexidade média):
- Sprint 26: RecordingSessionOrchestrator (-500 linhas)
- Sprint 27: ProjectOrchestrator (-400 linhas)
- Sprint 28: UIStateController (-600 linhas)

**Prioridade 3** (Médio - refinamento):
- Sprint 29: VideoTreeController (-400 linhas)
- Sprint 30: CanvasController (-350 linhas)
- Sprint 31: MenuEventHandler (-300 linhas)
- Sprint 32: ToolbarEventHandler (-250 linhas)

**Prioridade 4** (Baixo - consolidação):
- Sprint 33: Métodos remanescentes (-400 linhas)
- Sprint 34: Testes de integração
- Sprint 35: Documentação

### Padrão de Commit

Cada Sprint deve seguir este padrão:

```bash
# 1. Criar novo arquivo com código extraído
git add src/zebtrack/orchestrators/video_processing_orchestrator.py
git commit -m "feat: Create VideoProcessingOrchestrator with extracted methods"

# 2. Modificar MainViewModel para delegar
git add src/zebtrack/core/main_view_model.py
git commit -m "refactor: Delegate video processing to VideoProcessingOrchestrator"

# 3. Atualizar DI no __main__.py
git add src/zebtrack/__main__.py
git commit -m "feat: Wire VideoProcessingOrchestrator in DI container"

# 4. Adicionar testes
git add tests/orchestrators/test_video_processing_orchestrator.py
git commit -m "test: Add comprehensive tests for VideoProcessingOrchestrator"

# 5. Verificar testes passam
poetry run pytest

# 6. Documentar no sprint results
git add docs/SPRINT_24_RESULTS.md
git commit -m "docs: Complete Sprint 24 - VideoProcessingOrchestrator extraction"
```

### Checklist por Sprint

Cada Sprint deve cumprir:

- [ ] ✅ Criar novo arquivo com código extraído
- [ ] ✅ Modificar MainViewModel para delegar (facades)
- [ ] ✅ Atualizar DI no `__main__.py`
- [ ] ✅ Adicionar testes (>80% coverage do novo arquivo)
- [ ] ✅ Executar suite completa de testes (2568 testes devem passar)
- [ ] ✅ Verificar linting (ruff check)
- [ ] ✅ Documentar no `SPRINT_XX_RESULTS.md`
- [ ] ✅ Atualizar `REFACTOR-MASTER-PLAN-2025.md`
- [ ] ✅ Commit e push

---

## ⚠️ RISCOS E MITIGAÇÕES

### Riscos Identificados

| Risco | Probabilidade | Impacto | Mitigação |
|-------|---------------|---------|-----------|
| **Regressões** | Alta | Alto | Testes exaustivos após cada extração |
| **Breaking Changes** | Média | Alto | Manter facades públicas no MainViewModel |
| **Performance degradation** | Baixa | Médio | Benchmarks antes/depois |
| **Aumento de complexidade** | Média | Médio | Documentação clara + diagramas |
| **Circular dependencies** | Baixa | Alto | Análise de dependências no Sprint 23 |

### Estratégias de Mitigação

1. **Testes Rigorosos**
   - Executar suite completa após cada commit
   - Testes de integração end-to-end
   - Comparação de resultados antes/depois

2. **Backward Compatibility**
   - Manter APIs públicas do MainViewModel
   - Facades mínimas delegam para orchestrators
   - Zero breaking changes para usuários

3. **Documentação Contínua**
   - Atualizar docs em cada Sprint
   - Diagramas de arquitetura
   - Migration guides

4. **Code Review**
   - Revisar cada extração antes de merge
   - Validar que a extração faz sentido
   - Verificar que não há duplicação

---

## 📈 MÉTRICAS DE SUCESSO

### Métricas Principais

| Métrica | Antes | Meta | Como Medir |
|---------|-------|------|------------|
| **Linhas no MainViewModel** | 5,568 | <2,000 | `wc -l main_view_model.py` |
| **Métodos no MainViewModel** | 141 | <50 | `grep "^    def " \| wc -l` |
| **Linting Issues** | 1 | 0 | `ruff check` |
| **Test Coverage** | 61% | >80% | `pytest --cov` |
| **Método mais longo** | 149 linhas | <80 linhas | Manual inspection |

### Métricas Secundárias

| Métrica | Como Medir |
|---------|------------|
| **Cyclomatic Complexity** | `ruff check --select C901` |
| **Duplicação de código** | `pylint --duplicate-code` |
| **Imports circulares** | `pytest --import-errors` |
| **Performance** | Benchmarks de processamento |

### Critérios de Aceitação

Para considerar o plano completo, TODOS os critérios devem ser atendidos:

- [ ] ✅ MainViewModel reduzido para <2,000 linhas
- [ ] ✅ Nenhum método >80 linhas no MainViewModel
- [ ] ✅ Zero linting warnings (ruff check)
- [ ] ✅ Coverage >80% em todos os novos arquivos
- [ ] ✅ Todos os 2568+ testes passando
- [ ] ✅ Zero regressões funcionais
- [ ] ✅ Documentação completa atualizada
- [ ] ✅ Migration guide criado
- [ ] ✅ Performance mantida ou melhorada

---

## 🎯 CRONOGRAMA

### Estimativa Total: 22-25 dias úteis (~5 semanas)

```
Semana 1 (5 dias):
  Sprint 23: Análise (1 dia)
  Sprint 24: VideoProcessingOrchestrator (2-3 dias)
  Sprint 25: AnalysisOrchestrator (início, 1 dia)

Semana 2 (5 dias):
  Sprint 25: AnalysisOrchestrator (conclusão, 1 dia)
  Sprint 26: RecordingSessionOrchestrator (2 dias)
  Sprint 27: ProjectOrchestrator (2 dias)

Semana 3 (5 dias):
  Sprint 28: UIStateController (2 dias)
  Sprint 29: VideoTreeController (1-2 dias)
  Sprint 30: CanvasController (1-2 dias)

Semana 4 (5 dias):
  Sprint 31: MenuEventHandler (1 dia)
  Sprint 32: ToolbarEventHandler (1 dia)
  Sprint 33: Métodos remanescentes (2 dias)
  Sprint 34: Testes integração (início, 1 dia)

Semana 5 (5 dias):
  Sprint 34: Testes integração (conclusão, 2 dias)
  Sprint 35: Documentação e Release (2 dias)
  Buffer para ajustes finais (1 dia)
```

### Milestones

| Milestone | Data Estimada | Entregáveis |
|-----------|---------------|-------------|
| **M1: Análise Completa** | Dia 1 | Dependency maps, classification docs |
| **M2: Orchestrators Completos** | Dia 9 | 4 orchestrators extraídos, -2,300 linhas |
| **M3: UI Controllers Completos** | Dia 15 | 3 controllers extraídos, -1,350 linhas |
| **M4: Handlers Completos** | Dia 17 | 2 handlers extraídos, -550 linhas |
| **M5: Refinamento Completo** | Dia 21 | -400 linhas auxiliares extraídas |
| **M6: Release v5.0** | Dia 25 | Docs completos, testes passando, release |

---

## 📚 ESTRUTURA DE ARQUIVOS PÓS-EXTRAÇÃO

```
src/zebtrack/
├── orchestrators/           # NOVO - Camada de orquestração
│   ├── __init__.py
│   ├── video_processing_orchestrator.py   (~800 linhas)
│   ├── analysis_orchestrator.py           (~600 linhas)
│   ├── recording_session_orchestrator.py  (~500 linhas)
│   └── project_orchestrator.py            (~400 linhas)
│
├── ui/
│   ├── controllers/         # NOVO - UI Controllers
│   │   ├── __init__.py
│   │   ├── ui_state_controller.py         (~600 linhas)
│   │   ├── video_tree_controller.py       (~400 linhas)
│   │   └── canvas_controller.py           (~350 linhas)
│   │
│   ├── handlers/            # NOVO - Event Handlers
│   │   ├── __init__.py
│   │   ├── menu_event_handler.py          (~300 linhas)
│   │   └── toolbar_event_handler.py       (~250 linhas)
│   │
│   └── gui.py              # Existente (3,737 linhas - mantido)
│
├── core/
│   └── main_view_model.py  # Reduzido: 5,568 → ~1,000 linhas ✨
│
└── __main__.py             # Atualizado: wire novos orchestrators

tests/
├── orchestrators/          # NOVO - Testes de orchestrators
│   ├── test_video_processing_orchestrator.py
│   ├── test_analysis_orchestrator.py
│   ├── test_recording_session_orchestrator.py
│   └── test_project_orchestrator.py
│
├── ui/
│   ├── controllers/        # NOVO - Testes de controllers
│   │   ├── test_ui_state_controller.py
│   │   ├── test_video_tree_controller.py
│   │   └── test_canvas_controller.py
│   │
│   └── handlers/           # NOVO - Testes de handlers
│       ├── test_menu_event_handler.py
│       └── test_toolbar_event_handler.py
│
└── integration/            # NOVO - Testes de integração
    ├── test_mainviewmodel_refactored.py
    └── test_orchestrators_integration.py

docs/
├── MAINVIEWMODEL_DEPENDENCY_MAP.md        # Sprint 23
├── MAINVIEWMODEL_METHOD_CLASSIFICATION.md # Sprint 23
├── EXTRACTION_CANDIDATES.md               # Sprint 23
├── SPRINT_23_RESULTS.md ... SPRINT_35_RESULTS.md
├── ARCHITECTURE_V5.md                     # Sprint 35
├── MIGRATION_GUIDE_V5.md                  # Sprint 35
└── MAINVIEWMODEL_REFACTORING_COMPLETE.md  # Sprint 35
```

---

## 🚦 CRITÉRIOS DE GO/NO-GO

### Antes de Iniciar (Sprint 23)

**GO se:**
- ✅ Todos os testes atuais passando (2568 testes)
- ✅ Coverage atual medido (baseline: 61%)
- ✅ Performance atual medida (baseline benchmarks)
- ✅ Backup do código atual criado
- ✅ Branch de desenvolvimento criada

**NO-GO se:**
- ❌ Testes falhando
- ❌ Linting com >5 issues
- ❌ Coverage <60%

### Após Cada Sprint

**GO para próximo sprint se:**
- ✅ Todos os testes passando (incluindo novos testes)
- ✅ Linting clean (ruff check)
- ✅ Coverage mantido ou aumentado
- ✅ Code review aprovado
- ✅ Documentação atualizada

**NO-GO se:**
- ❌ Qualquer teste falhando
- ❌ Coverage diminuiu
- ❌ Performance degradou >10%
- ❌ Regressões funcionais detectadas

### Release Final (Sprint 35)

**GO para release se:**
- ✅ MainViewModel <2,000 linhas
- ✅ Todos os critérios de aceitação atendidos
- ✅ Migration guide completo
- ✅ Documentação completa
- ✅ Todos os stakeholders aprovaram

---

## 📞 PONTOS DE CONTATO

### Dúvidas Durante Implementação

Se encontrar dificuldades durante a implementação, consulte:

1. **Análise de Dependências** (`docs/MAINVIEWMODEL_DEPENDENCY_MAP.md`)
2. **Classification Guide** (`docs/MAINVIEWMODEL_METHOD_CLASSIFICATION.md`)
3. **Sprints anteriores** (Sprints 1-22 como referência)
4. **CLAUDE.md** (arquitetura atual)

### Reporting

Após cada Sprint, atualizar:
- `docs/SPRINT_XX_RESULTS.md` - Resultados detalhados
- `docs/REFACTOR-MASTER-PLAN-2025.md` - Progresso no master plan
- Este documento (`PLANO_EXTRACAO_MAINVIEWMODEL.md`) - Status dos sprints

---

## 🎓 LIÇÕES APRENDIDAS (Sprints 1-22)

### O Que Funcionou ✅

1. **Criação de Coordinators** - Boa separação de responsabilidades
2. **Testes abrangentes** - >110 testes por coordinator
3. **DI Pattern** - Facilita injeção de dependências
4. **Documentation** - Docs detalhados ajudaram compreensão

### O Que Não Funcionou ❌

1. **Delegação sem extração** - Coordinators criados mas MainViewModel não reduziu
2. **Foco em qualidade vs tamanho** - Sprints 15-22 focaram em linting, não extração
3. **Falta de métricas claras** - Não medimos redução de linhas consistentemente

### Aplicar Neste Plano ✨

1. **Extração real** - Mover código, não duplicar
2. **Métricas em cada Sprint** - Medir redução de linhas após cada extração
3. **Facades mínimas** - MainViewModel mantém apenas delegates
4. **Testes antes e depois** - Garantir zero regressões

---

## 🎯 PRÓXIMOS PASSOS

### Para Iniciar Sprint 23

Execute este comando para criar o prompt de início:

```bash
# Ver seção "PROMPT PARA NOVA CONVERSA" abaixo
```

### Preparação Recomendada

Antes de iniciar Sprint 23:

1. **Criar branch de desenvolvimento**
   ```bash
   git checkout -b refactor/mainviewmodel-extraction-v5
   ```

2. **Verificar estado atual**
   ```bash
   poetry run pytest  # Todos passando?
   poetry run ruff check  # Zero issues?
   wc -l src/zebtrack/core/main_view_model.py  # Baseline
   ```

3. **Criar backup**
   ```bash
   git tag -a backup-pre-extraction-v5 -m "Backup before MainViewModel extraction"
   git push origin backup-pre-extraction-v5
   ```

4. **Ler documentação**
   - `docs/ARCHITECTURE.md`
   - `docs/DEPENDENCY_INJECTION_GUIDE.md`
   - `CLAUDE.md`

---

## 📝 NOTAS FINAIS

### Filosofia do Plano

Este plano foi criado com base nas lições aprendidas dos Sprints 1-22. O foco é **extração real de código**, não apenas criação de camadas de delegação.

### Compromisso com Qualidade

- ✅ Zero breaking changes para usuários finais
- ✅ Zero regressões funcionais
- ✅ Manter ou melhorar performance
- ✅ Aumentar testabilidade e cobertura
- ✅ Documentação clara e completa

### Flexibilidade

Este plano é um guia, não uma camisa de força:
- Ajuste estimativas conforme necessário
- Combine ou divida Sprints se fizer sentido
- Adicione Sprints se descobrir mais código para extrair
- Pause se encontrar problemas críticos

### Sucesso

O sucesso será medido por:
1. **MainViewModel <2,000 linhas** (objetivo primário)
2. **Zero regressões** (objetivo de qualidade)
3. **Código mais testável** (objetivo de manutenibilidade)
4. **Documentação completa** (objetivo de sustentabilidade)

---

**Boa sorte com a extração! 🚀**

---

**Versão:** 1.0
**Última Atualização:** 2025-01-14
**Próxima Revisão:** Após Sprint 23 (análise de dependências)
