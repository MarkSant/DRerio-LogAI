<!-- markdownlint-disable MD024 -->

# Contextos de Tarefas - Rodadas 3, 4 e 5

## ZebTrack-AI - Continuação da Refatoração

**Branch**: `claude/fix-post-refactor-bugs-011CUpYC3FjTK9gyrCusQND3`
**Documento Base**: `EXECUTION_PLAN.md`
**Pré-requisito**: Tasks 1.1, 2.2 e 3.1 completas

---

## 🔶 RODADA 3 - Refatorações e Testes (5 conversas paralelas)

---

## Task 2.1: Refatorar GUI.py (Extração de Componentes UI)

**ID**: `REFACTOR-GUI-001`
**Status**: PENDENTE
**Prioridade**: ALTA
**Dependências**: Tasks 1.1 e 2.2 completas
**Tempo Estimado**: 5-7 dias

## Contexto do Projeto

**Nome**: ZebTrack-AI
**Arquitetura**: MVVM-S com Dependency Injection
**Tech Stack**: Poetry, Tkinter, YOLO/OpenVINO, Parquet
**Branch**: `claude/fix-post-refactor-bugs-011CUpYC3FjTK9gyrCusQND3`

## Objetivo da Task

Refatorar `ApplicationGUI` (ui/gui.py, 9951 linhas) extraindo componentes UI em módulos independentes:

- Extrair gerenciamento de menus para `MenuManager`
- Extrair desenho e overlay para `CanvasManager`
- Extrair sincronização de estado para `StateSynchronizer`
- Extrair handlers de eventos para `EventDispatcher`
- **Meta**: ~4000 linhas no gui.py final (redução de 60%)

## God Object Atual

**Arquivo**: `src/zebtrack/ui/gui.py` (9951 linhas, 322 métodos)

**Responsabilidades Identificadas**:

1. Menu management (File, Edit, View, etc.) - ~800 linhas
2. Canvas drawing e overlay rendering - ~1200 linhas
3. State synchronization com StateManager - ~600 linhas
4. Event handling (user interactions) - ~400 linhas
5. Layout e widget management - restante

## Arquivos a Criar

1. `src/zebtrack/ui/components/menu_manager.py` (~800 linhas)
2. `src/zebtrack/ui/components/canvas_manager.py` (~1200 linhas)
3. `src/zebtrack/ui/components/state_synchronizer.py` (~600 linhas)
4. `src/zebtrack/ui/components/event_dispatcher.py` (~400 linhas)

## Arquivo a Modificar

1. `src/zebtrack/ui/gui.py` (9951 → ~4000 linhas)

## Estratégia de Refatoração

### Fase 1: Criar MenuManager

**Responsabilidade**: Gerenciar todos os menus da aplicação

**Métodos a Extrair** (buscar em gui.py):

- `_create_menu_bar()`
- `_create_file_menu()`
- `_create_edit_menu()`
- `_create_view_menu()`
- `_create_tools_menu()`
- `_create_help_menu()`
- Todos os handlers de menu items

**Template Inicial**:

```python
"""Menu management for ApplicationGUI."""

import tkinter as tk
from tkinter import Menu
import structlog

logger = structlog.get_logger()


class MenuManager:
    """Manages menu bar and menu items for the main application."""

    def __init__(self, parent, controller):
        """
        Initialize MenuManager.

        Args:
            parent: Parent Tkinter widget (ApplicationGUI)
            controller: MainViewModel controller
        """
        self.parent = parent
        self.controller = controller
        self.menu_bar = None

    def create_menu_bar(self) -> Menu:
        """Create and return the main menu bar."""
        self.menu_bar = Menu(self.parent)

        # Create all menus
        file_menu = self._create_file_menu()
        edit_menu = self._create_edit_menu()
        view_menu = self._create_view_menu()
        tools_menu = self._create_tools_menu()
        help_menu = self._create_help_menu()

        # Add to menu bar
        self.menu_bar.add_cascade(label="Arquivo", menu=file_menu)
        self.menu_bar.add_cascade(label="Editar", menu=edit_menu)
        self.menu_bar.add_cascade(label="Visualizar", menu=view_menu)
        self.menu_bar.add_cascade(label="Ferramentas", menu=tools_menu)
        self.menu_bar.add_cascade(label="Ajuda", menu=help_menu)

        return self.menu_bar

    def _create_file_menu(self) -> Menu:
        """Create File menu."""
        menu = Menu(self.menu_bar, tearoff=0)
        # Extrair implementação de ApplicationGUI
        return menu

    # ... mais métodos
```

### Fase 2: Criar CanvasManager

**Responsabilidade**: Gerenciar canvas, desenho e overlays

**Métodos a Extrair**:

- `_draw_detections()`
- `_draw_zones()`
- `_draw_arena()`
- `_draw_roi()`
- `_draw_trajectory()`
- `_update_overlay()`
- `_clear_canvas()`
- Todos os métodos `_draw_*`

**Template Inicial**:

```python
"""Canvas drawing and overlay management."""

import tkinter as tk
import cv2
import numpy as np
from PIL import Image, ImageTk
import structlog

logger = structlog.get_logger()


class CanvasManager:
    """Manages canvas drawing operations and overlay rendering."""

    def __init__(self, canvas, controller):
        """
        Initialize CanvasManager.

        Args:
            canvas: Tkinter Canvas widget
            controller: MainViewModel controller
        """
        self.canvas = canvas
        self.controller = controller
        self.current_image = None
        self.overlay_items = []

    def draw_frame(self, frame: np.ndarray, detections=None, zones=None):
        """
        Draw frame with overlays on canvas.

        Args:
            frame: OpenCV frame (numpy array)
            detections: Detection results
            zones: Zone definitions
        """
        # Convert frame to PhotoImage
        self._display_frame(frame)

        # Draw overlays
        if detections:
            self._draw_detections(detections)

        if zones:
            self._draw_zones(zones)

    def _display_frame(self, frame: np.ndarray):
        """Display frame on canvas."""
        # Extrair implementação
        pass

    def _draw_detections(self, detections):
        """Draw detection overlays."""
        # Extrair implementação
        pass

    # ... mais métodos
```

### Fase 3: Criar StateSynchronizer

**Responsabilidade**: Sincronizar UI com StateManager

**Métodos a Extrair**:

- `_update_ui_from_state()`
- `_sync_recording_state()`
- `_sync_processing_state()`
- `_sync_project_state()`
- `_on_state_changed()`

**Template Inicial**:

```python
"""State synchronization between UI and StateManager."""

import structlog
from zebtrack.core.state_manager import StateManager

logger = structlog.get_logger()


class StateSynchronizer:
    """Synchronizes UI state with StateManager."""

    def __init__(self, parent, state_manager: StateManager):
        """
        Initialize StateSynchronizer.

        Args:
            parent: Parent UI (ApplicationGUI)
            state_manager: Centralized state manager
        """
        self.parent = parent
        self.state_manager = state_manager

        # Subscribe to state changes
        self.state_manager.add_observer(self._on_state_changed)

    def _on_state_changed(self, state):
        """Handle state changes from StateManager."""
        # Schedule UI update on main thread
        self.parent.after(0, self._update_ui_from_state, state)

    def _update_ui_from_state(self, state):
        """Update UI elements based on state."""
        self._sync_recording_state(state.is_recording)
        self._sync_processing_state(state.is_processing)
        self._sync_project_state(state.current_project)

    def _sync_recording_state(self, is_recording: bool):
        """Sync UI with recording state."""
        # Extrair implementação
        pass

    # ... mais métodos
```

### Fase 4: Criar EventDispatcher

**Responsabilidade**: Gerenciar event handlers

**Métodos a Extrair**:

- `_on_button_click()`
- `_on_canvas_click()`
- `_on_key_press()`
- `_handle_menu_action()`
- Todos os handlers `_on_*`

**Template Inicial**:

```python
"""Event handling and dispatching."""

import structlog

logger = structlog.get_logger()


class EventDispatcher:
    """Dispatches and handles UI events."""

    def __init__(self, parent, controller):
        """
        Initialize EventDispatcher.

        Args:
            parent: Parent UI (ApplicationGUI)
            controller: MainViewModel controller
        """
        self.parent = parent
        self.controller = controller

    def setup_bindings(self):
        """Setup all event bindings."""
        # Canvas events
        self.parent.canvas.bind("<Button-1>", self._on_canvas_click)
        self.parent.canvas.bind("<B1-Motion>", self._on_canvas_drag)

        # Keyboard shortcuts
        self.parent.bind("<Control-s>", self._on_save_shortcut)
        self.parent.bind("<Control-o>", self._on_open_shortcut)

    def _on_canvas_click(self, event):
        """Handle canvas click event."""
        # Extrair implementação
        pass

    # ... mais métodos
```

### Fase 5: Refatorar ApplicationGUI

**Mudanças em gui.py**:

1. **Importar novos componentes**:

```python
from zebtrack.ui.components.menu_manager import MenuManager
from zebtrack.ui.components.canvas_manager import CanvasManager
from zebtrack.ui.components.state_synchronizer import StateSynchronizer
from zebtrack.ui.components.event_dispatcher import EventDispatcher
```

1. **Atualizar `__init__`**:

```python
def __init__(self, root, controller):
    # ... inicialização existente ...

    # Initialize component managers
    self.menu_manager = MenuManager(self, controller)
    self.canvas_manager = CanvasManager(self.canvas, controller)
    self.state_synchronizer = StateSynchronizer(self, controller.state_manager)
    self.event_dispatcher = EventDispatcher(self, controller)

    # Setup UI
    self._create_layout()
    menu_bar = self.menu_manager.create_menu_bar()
    self.config(menu=menu_bar)
    self.event_dispatcher.setup_bindings()
```

1. **Substituir métodos por delegação**:

```python
def draw_frame(self, frame, detections=None, zones=None):
    """Delegate to CanvasManager."""
    self.canvas_manager.draw_frame(frame, detections, zones)
```

1. **Remover métodos extraídos**

## Implementação Passo-a-Passo

1. **Ler gui.py completo** (entender estrutura atual)

2. **Criar componentes na ordem**:
   - MenuManager (menos dependências)
   - EventDispatcher (handlers simples)
   - CanvasManager (desenho e rendering)
   - StateSynchronizer (integração com StateManager)

3. **Para cada componente**:
   - Criar arquivo novo
   - Extrair métodos relevantes de gui.py
   - Implementar `__init__` com DI
   - Adicionar logging com structlog
   - Testar isoladamente se possível

4. **Refatorar ApplicationGUI**:
   - Importar componentes
   - Atualizar `__init__`
   - Substituir implementações por delegação
   - Remover código duplicado

5. **Atualizar testes** (se necessário):
   - Adaptar mocks para novos componentes
   - Garantir testes existentes continuam passando

## Validação

```bash
## Verificar sintaxe Python
poetry run ruff check src/zebtrack/ui/

## Testes de GUI (se disponíveis)
poetry run pytest tests/test_gui.py -v -m gui -n0

## Testes de integração
poetry run pytest tests/integration/test_gui_integration.py -v -n0

## Suite completa (garantir sem regressão)
poetry run pytest -q
```

## Commit e Push

```bash
## Criar diretório de componentes
mkdir -p src/zebtrack/ui/components

## Adicionar novos arquivos
git add src/zebtrack/ui/components/menu_manager.py
git add src/zebtrack/ui/components/canvas_manager.py
git add src/zebtrack/ui/components/state_synchronizer.py
git add src/zebtrack/ui/components/event_dispatcher.py

## Adicionar gui.py modificado
git add src/zebtrack/ui/gui.py

## Adicionar __init__ no diretório components
git add src/zebtrack/ui/components/__init__.py

git commit -m "refactor: extrair componentes UI de ApplicationGUI

- Criar MenuManager (800 linhas) para gerenciamento de menus
- Criar CanvasManager (1200 linhas) para canvas e overlays
- Criar StateSynchronizer (600 linhas) para sync com StateManager
- Criar EventDispatcher (400 linhas) para event handling
- Refatorar ApplicationGUI (9951 → 4000 linhas, -60%)

Benefícios:
- Redução de complexidade da ApplicationGUI
- Componentes reutilizáveis e testáveis
- Separação clara de responsabilidades
- Facilita manutenção futura

Refs: REFACTOR-GUI-001"

git push -u origin claude/fix-post-refactor-bugs-011CUpYC3FjTK9gyrCusQND3
```

## Notas Importantes

1. **Manter funcionalidade**: Garantir que toda funcionalidade existente continue funcionando
2. **Threading**: Manter uso de `root.after(0, ...)` para UI updates
3. **Event Bus**: Preservar integração com UI event bus se existente
4. **Estado**: Garantir sincronização correta com StateManager

---

## Task 2.3: Refatorar ProjectManager (Separação de Responsabilidades)

**ID**: `REFACTOR-PROJECTMGR-001`
**Status**: PENDENTE
**Prioridade**: ALTA
**Dependências**: Tasks 1.1 e 2.2 completas
**Tempo Estimado**: 4-5 dias

## Objetivo da Task

Refatorar `ProjectManager` (2795 linhas) separando gerenciamento de projetos, vídeos, zonas e assets:

- Extrair gerenciamento de vídeos para `VideoManager`
- Extrair gerenciamento de zonas para `ZoneManager`
- Extrair gerenciamento de assets para `AssetManager`
- **Meta**: ~1200 linhas no ProjectManager final (redução de 57%)

## God Object Atual

**Arquivo**: `src/zebtrack/core/project_manager.py` (2795 linhas, 79 métodos)

**Responsabilidades Identificadas**:

1. Gerenciamento de projetos (CRUD) - ~700 linhas
2. Gerenciamento de vídeos - ~500 linhas
3. Gerenciamento de zonas e ROIs - ~600 linhas
4. Gerenciamento de assets (profiles, templates) - ~400 linhas
5. Parquet operations - ~400 linhas
6. Utilities - restante

## Arquivos a Criar

1. `src/zebtrack/core/video_manager.py` (~500 linhas)
2. `src/zebtrack/core/zone_manager.py` (~600 linhas)
3. `src/zebtrack/core/asset_manager.py` (~400 linhas)

## Arquivo a Modificar

1. `src/zebtrack/core/project_manager.py` (2795 → ~1200 linhas)

## Estratégia de Refatoração

### Fase 1: Criar VideoManager

**Métodos a Extrair**:

- `add_video()`
- `remove_video()`
- `get_video_info()`
- `update_video_metadata()`
- `get_pending_videos()`
- `get_processed_videos()`

**Template Inicial**:

```python
"""Video management for projects."""

import structlog
from pathlib import Path

logger = structlog.get_logger()


class VideoManager:
    """Manages video files within projects."""

    def __init__(self, project_data: dict):
        """
        Initialize VideoManager.

        Args:
            project_data: Project configuration dictionary
        """
        self.project_data = project_data

    def add_video(self, video_path: str | Path) -> bool:
        """Add video to project."""
        # Extrair implementação
        pass

    def remove_video(self, video_path: str | Path) -> bool:
        """Remove video from project."""
        # Extrair implementação
        pass

    def get_video_list(self) -> list[str]:
        """Get list of all videos in project."""
        return self.project_data.get("videos", [])

    # ... mais métodos
```

### Fase 2: Criar ZoneManager

**Métodos a Extrair**:

- `add_zone()`
- `update_zone()`
- `remove_zone()`
- `get_zone_data()`
- `import_zones_from_template()`
- `export_zones_to_template()`

### Fase 3: Criar AssetManager

**Métodos a Extrair**:

- `load_profile()`
- `save_profile()`
- `get_available_profiles()`
- `load_roi_template()`
- `save_roi_template()`

### Fase 4: Refatorar ProjectManager

**Atualizar `__init__`**:

```python
def __init__(self, settings):
    self.settings = settings
    self.project_data = {}

    # Initialize managers
    self.video_manager = None  # Created when project loaded
    self.zone_manager = None
    self.asset_manager = AssetManager(settings)

def load_project(self, project_path):
    # Load project
    # ...
    # Initialize managers with project data
    self.video_manager = VideoManager(self.project_data)
    self.zone_manager = ZoneManager(self.project_data)
```

## Validação

```bash
poetry run pytest tests/test_project_manager.py -v
poetry run pytest tests/test_project_manager_video_operations.py -v
poetry run pytest -q
```

## Commit

```bash
git add src/zebtrack/core/video_manager.py
git add src/zebtrack/core/zone_manager.py
git add src/zebtrack/core/asset_manager.py
git add src/zebtrack/core/project_manager.py

git commit -m "refactor: extrair managers de ProjectManager

- Criar VideoManager (500 linhas)
- Criar ZoneManager (600 linhas)
- Criar AssetManager (400 linhas)
- Refatorar ProjectManager (2795 → 1200 linhas, -57%)

Refs: REFACTOR-PROJECTMGR-001"

git push -u origin claude/fix-post-refactor-bugs-011CUpYC3FjTK9gyrCusQND3
```

---

## Task 2.4: Refatorar VideoProcessingService (Quebrar Método God)

**ID**: `REFACTOR-VIDEOPROCESSING-001`
**Status**: PENDENTE
**Prioridade**: ALTA
**Dependências**: Tasks 1.1 e 2.2 completas
**Tempo Estimado**: 3-4 dias

## Objetivo da Task

Refatorar `VideoProcessingService` quebrando o método god `_collect_params_from_single_video()`:

- Método atual: 641 linhas, complexidade ciclomática ~40
- **Meta**: Reduzir para ~90 linhas, CC ~8
- Extrair 5 métodos especializados

## God Method Atual

**Arquivo**: `src/zebtrack/core/video_processing_service.py`
**Método**: `_collect_params_from_single_video()` (641 linhas)

## Estratégia de Refatoração

### Métodos a Extrair

1. **`_validate_arena_roi_compatibility()`** (~80 linhas)
   - Validação de compatibilidade arena/ROI
   - Retorna: bool (is_valid)

2. **`_setup_detector_for_video()`** (~100 linhas)
   - Setup de detector e zonas
   - Retorna: bool (success)

3. **`_collect_detection_params()`** (~150 linhas)
   - Coleta parâmetros de detecção
   - Retorna: dict (detection_params)

4. **`_collect_recording_params()`** (~120 linhas)
   - Coleta parâmetros de gravação
   - Retorna: dict (recording_params)

5. **`_collect_analysis_params()`** (~100 linhas)
   - Coleta parâmetros de análise
   - Retorna: dict (analysis_params)

### Estrutura Refatorada

```python
def _collect_params_from_single_video(self, video_path, ...):
    """
    Collect parameters for single video processing.

    Refactored: Orchestrates parameter collection through specialized methods.
    """
    # Validate compatibility
    if not self._validate_arena_roi_compatibility(project_data):
        return None

    # Setup detector
    if not self._setup_detector_for_video(video_path, zone_data):
        return None

    # Collect parameters
    detection_params = self._collect_detection_params(project_data)
    recording_params = self._collect_recording_params(project_data, video_path)
    analysis_params = self._collect_analysis_params(project_data)

    # Assemble final params
    return {
        "video_path": video_path,
        "detection": detection_params,
        "recording": recording_params,
        "analysis": analysis_params,
    }
```

## Validação

```bash
poetry run pytest tests/test_video_processing_service.py -v
poetry run pytest tests/integration/test_video_processing.py -v
poetry run pytest -q
```

## Commit

```bash
git add src/zebtrack/core/video_processing_service.py

git commit -m "refactor: quebrar método god _collect_params_from_single_video

- Extrair _validate_arena_roi_compatibility (80 linhas)
- Extrair _setup_detector_for_video (100 linhas)
- Extrair _collect_detection_params (150 linhas)
- Extrair _collect_recording_params (120 linhas)
- Extrair _collect_analysis_params (100 linhas)
- Refatorar _collect_params_from_single_video (641 → 90 linhas)
- Reduzir complexidade ciclomática de ~40 para ~8

Refs: REFACTOR-VIDEOPROCESSING-001"

git push -u origin claude/fix-post-refactor-bugs-011CUpYC3FjTK9gyrCusQND3
```

---

## Task 3.2: Testes LiveCameraService Thread Safety

**ID**: `TEST-LIVECAMERA-001`
**Status**: PENDENTE
**Prioridade**: CRÍTICA
**Dependências**: Task 1.1 completa
**Tempo Estimado**: 2-3 dias

## Objetivo da Task

Adicionar testes abrangentes de thread safety para `LiveCameraService`:

- Testar lifecycle de threads
- Testar operações de queue
- Testar race conditions
- Testar error handling em threads
- **Meta**: ~400 linhas de testes, cobertura >80%

## Arquivo a Testar

`src/zebtrack/core/live_camera_service.py` (445 linhas, 12 métodos)

## Arquivo a Criar

`tests/test_live_camera_service_threading.py` (NOVO, ~400 linhas)

## Estrutura do Teste (Resumida)

```python
"""Testes de thread safety para LiveCameraService."""

import pytest
import threading
import time
from unittest.mock import Mock, patch
from zebtrack.core.live_camera_service import LiveCameraService

class TestLiveCameraServiceThreading:
    """Testes de lifecycle de threads."""

    def test_thread_start_stop_lifecycle(self, live_camera_service):
        """Test: Start/stop de threads múltiplas vezes."""
        for _ in range(3):
            live_camera_service.start_session(...)
            time.sleep(0.1)
            live_camera_service.stop_session()

    def test_rapid_start_stop_cycles(self, live_camera_service):
        """Test: Race conditions em start/stop rápidos."""
        # Testar start/stop muito rápidos
        pass

class TestLiveCameraServiceQueueOperations:
    """Testes de operações de queue."""

    def test_frame_queue_overflow(self, live_camera_service):
        """Test: Queue full scenario."""
        pass

## ... 6 classes de teste, ~25 métodos total
```

## Validação

```bash
## Rodar testes sequencialmente (threading)
poetry run pytest tests/test_live_camera_service_threading.py -v -n0

## Rodar múltiplas vezes para detectar race conditions
poetry run pytest tests/test_live_camera_service_threading.py --repeat 10 -n0
```

## Commit

```bash
git add tests/test_live_camera_service_threading.py

git commit -m "test: adicionar testes de thread safety para LiveCameraService

- 6 classes de teste, 25+ métodos
- Testar lifecycle, queue ops, race conditions
- Testar error handling em threads
- Cobertura threading >80%

Refs: TEST-LIVECAMERA-001"

git push -u origin claude/fix-post-refactor-bugs-011CUpYC3FjTK9gyrCusQND3
```

---

## Task 3.3: Testes LiveAnalysisDialog e LivePreviewWindow

**ID**: `TEST-LIVEUI-001`
**Status**: PENDENTE
**Prioridade**: ALTA
**Dependências**: Task 1.1 completa
**Tempo Estimado**: 1-2 dias

## Objetivo

Testar UI components de live analysis (v2.0 feature):

- LiveAnalysisDialog (configuração)
- LivePreviewWindow (preview em tempo real)
- **Meta**: ~250 linhas, cobertura >80%

## Estrutura (Resumida)

```python
@pytest.mark.gui
class TestLiveAnalysisDialog:
    def test_init_default_values(self, root):
        """Test: Valores default."""
        pass

    def test_camera_detection(self, root):
        """Test: Hardware detection."""
        pass

@pytest.mark.gui
class TestLivePreviewWindow:
    def test_frame_update_with_detections(self, root):
        """Test: Frame display."""
        pass
```

## Commit

```bash
git commit -m "test: adicionar testes para LiveAnalysisDialog e LivePreviewWindow

Refs: TEST-LIVEUI-001"
```

---

## 🔶 RODADA 4 - Refatoração Final + Testes Dialogs (6 conversas paralelas)

---

## Task 2.5: Refatorar Reporter (Separar Transformação/Visualização/Relatório)

**ID**: `REFACTOR-REPORTER-001`
**Status**: PENDENTE
**Prioridade**: MÉDIA-ALTA
**Dependências**: Task 1.1 completa
**Tempo Estimado**: 2-3 dias

## Objetivo

Refatorar `Reporter` (1412 linhas) separando responsabilidades:

- Extrair transformação de dados para `DataTransformer`
- Extrair visualização para `VisualizationGenerator`
- **Meta**: ~600 linhas no Reporter final (redução de 58%)

## Arquivos a Criar

1. `src/zebtrack/analysis/data_transformer.py` (~300 linhas)
2. `src/zebtrack/analysis/visualization_generator.py` (~400 linhas)

## Commit

```bash
git commit -m "refactor: extrair componentes de Reporter

- Criar DataTransformer (300 linhas)
- Criar VisualizationGenerator (400 linhas)
- Refatorar Reporter (1412 → 600 linhas, -58%)

Refs: REFACTOR-REPORTER-001"
```

---

## Task 3.4: Testes Dialogs - Batch 1 (High Complexity)

**ID**: `TEST-DIALOGS-BATCH1-001`
**Status**: PENDENTE
**Tempo Estimado**: 2-3 dias

## Dialogs a Testar (5 dialogs alta complexidade)

1. CalibrationDialog (983 linhas)
2. CreateProjectDialog (508 linhas)
3. ManageWeightsDialog (300+ linhas)
4. StartRecordingDialog (200+ linhas)
5. SingleVideoConfigDialog (250+ linhas)

## Arquivo a Criar

`tests/ui/dialogs/test_dialogs_batch1.py` (~250 linhas)

## Commit

```bash
git commit -m "test: adicionar testes para dialogs batch 1 (alta complexidade)

Refs: TEST-DIALOGS-BATCH1-001"
```

---

## Task 3.5: Testes Dialogs - Batch 2 (Medium Complexity)

**ID**: `TEST-DIALOGS-BATCH2-001`

## Dialogs (5 dialogs média complexidade)

1. TemplateDialog
2. PendingVideosDialog
3. CenterPeripheryDialog
4. DiagnosticProgressDialog
5. MissingMetadataDialog

## Arquivo

`tests/ui/dialogs/test_dialogs_batch2.py` (~250 linhas)

---

## Task 3.6: Testes Dialogs - Batch 3 (Low Complexity)

**ID**: `TEST-DIALOGS-BATCH3-001`

## Dialogs (5 dialogs baixa complexidade)

1. SubjectSelectionDialog
2. SaveRoiTemplateDialog
3. ColorSelectionDialog
4. Outros dialogs simples

## Arquivo

`tests/ui/dialogs/test_dialogs_batch3.py` (~200 linhas)

---

## Task 4.1: Testes Error Handling Paths

**ID**: `TEST-ERRORHANDLING-001`

## Objetivo

Expandir testes de error handling em 3 módulos:

- `test_detector_service.py` (+150 linhas)
- `test_recording_service.py` (+200 linhas)
- `test_project_workflow_service.py` (+200 linhas)

## Cenários

- Zone setup com polígonos inválidos
- Model file corruption
- Parquet writer failures (disk full)
- Arduino command failures
- State manager update failures

---

## Task 4.2: Testes Thread Safety Modules

**ID**: `TEST-THREADSAFETY-001`

## Módulos (4 novos arquivos de teste)

1. `test_main_view_model_threading.py` (300 linhas)
2. `test_project_manager_threading.py` (200 linhas)
3. `test_ui_coordinator_threading.py` (200 linhas)
4. `test_weight_manager_threading.py` (150 linhas)

---

## 🔶 RODADA 5 - Expansão Final (2 conversas paralelas)

---

## Task 4.3: Testes Wizard Integration

**ID**: `TEST-WIZARD-001`

## Wizard Steps (4 steps com baixa cobertura)

1. `test_calibration_step.py` (150 linhas)
2. `test_model_selection_step.py` (120 linhas)
3. Expansão de `test_confirmation_step.py` (+100 linhas)
4. Expansão de `test_detection_step.py` (+150 linhas)

---

## Task 4.4: Testes Edge Cases e Boundary Conditions

**ID**: `TEST-EDGECASES-001`

## Categorias

1. **Recorder Edge Cases** (+150 linhas)
   - Empty detection list
   - Single frame recording
   - Very large detection count
   - NaN values

2. **Behavior Analysis Edge Cases** (+120 linhas)
   - Zero-velocity conditions
   - Negative displacement
   - Very short trajectories

3. **Zone Management Edge Cases** (+130 linhas)
   - Self-intersecting polygons
   - Degenerate zones
   - Very small zones

---

## 📊 Resumo das Rodadas

| Rodada | Tasks | Conversas | Tipo |
| -------- | ------- | ----------- | ------ |
| 1 | 1.1 | 1 | Bugfixes (COMPLETA) |
| 2 | 2.2, 3.1 | 2 | Refatoração + Testes (EM ANDAMENTO) |
| 3 | 2.1, 2.3, 2.4, 3.2, 3.3 | 5 | Refatorações + Testes |
| 4 | 2.5, 3.4-3.6, 4.1, 4.2 | 6 | Refatoração + Testes Dialogs + Error/Thread |
| 5 | 4.3, 4.4 | 2 | Testes Wizard + Edge Cases |

**Total**: 21 tasks, 16 conversas máximas simultâneas (somando todas rodadas)

---

## ✅ Como Usar Este Documento

Para cada task:

1. Copiar a seção completa da task desejada
2. Colar em uma nova conversa Claude Code
3. A task será executada com todos os detalhes necessários
4. Commit e push automáticos ao final

**Branch**: `claude/fix-post-refactor-bugs-011CUpYC3FjTK9gyrCusQND3`

---

**Última Atualização**: 2025-11-05
**Tasks Disponíveis**: 18 tasks (Tasks 1.1, 2.2, 3.1 já iniciadas/completas)
