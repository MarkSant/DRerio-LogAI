# Plano de Execução Modular - ZebTrack-AI
## Correção de Bugs, Refatoração de God Objects e Expansão de Testes

**Data de Criação**: 2025-11-05
**Branch**: `claude/fix-post-refactor-bugs-011CUpYC3FjTK9gyrCusQND3`
**Status Inicial**: 712 testes passando, 70% cobertura

---

## 📊 Resumo Executivo

### Problemas Identificados
- **4 bugs críticos/high** detectados pós-refatoração
- **5 God Objects** (9951 a 445 linhas)
- **~6,550 linhas de testes** faltando
- **1 módulo crítico** com 0% cobertura (AquariumDetector)
- **15 dialogs** sem testes unitários
- **8 módulos** com problemas de thread safety não testados

### Estratégia de Execução
- **Fases paralelas**: Múltiplas tasks independentes podem rodar simultaneamente
- **Zero overlap de código**: Cada task trabalha em arquivos distintos
- **Commits incrementais**: Cada task gera commits independentes
- **Validação contínua**: Cada task valida com `pytest` antes do commit

---

## 🔴 FASE 1: CORREÇÕES CRÍTICAS (Executar PRIMEIRO)
**Prioridade**: CRÍTICA
**Dependências**: Nenhuma
**Tempo Estimado**: 2-3 horas
**Arquivos Afetados**: 3 arquivos únicos

### Task 1.1: Corrigir Bugs Críticos
**ID**: `BUGFIX-CRITICAL-001`
**Responsável**: Conversa Principal (ESTA CONVERSA)
**Status**: PENDING

**Arquivos**:
- `src/zebtrack/core/main_view_model.py` (Bug #1: import)
- `src/zebtrack/core/live_camera_service.py` (Bugs #2, #3, #4)

**Bugs a Corrigir**:
1. **BUG #1 (CRITICAL)**: `main_view_model.py:5153` - Import incorreto de `DiagnosticProgressDialog`
   - Fix: `from zebtrack.ui.dialogs import DiagnosticProgressDialog`

2. **BUG #2 (HIGH)**: `live_camera_service.py:183-191` - Callback de completion não registrado
   - Fix: Registrar `on_complete` no `RecordingService.start_session()`

3. **BUG #3 (HIGH)**: `live_camera_service.py:402-407` - Violação thread safety em preview update
   - Fix: Usar `root.after(0, ...)` para updates de Tkinter

4. **BUG #4 (MEDIUM)**: `live_camera_service.py:148` - Zone rescaling com dimensões incorretas
   - Fix: Passar `camera.actual_width/height` para `configure_zones()`

**Validação**:
```bash
poetry run pytest tests/test_main_view_model.py -v
poetry run pytest tests/integration/test_live_camera_analysis_integration.py -v
poetry run ruff check src/zebtrack/core/
```

**Commit Message**:
```
fix: corrigir 4 bugs críticos pós-refatoração

- Fix import de DiagnosticProgressDialog (main_view_model.py:5153)
- Fix callback de completion não registrado (live_camera_service.py:183)
- Fix violação thread safety em preview updates (live_camera_service.py:405)
- Fix zone rescaling com dimensões incorretas (live_camera_service.py:148)

Refs: BUG #1, #2, #3, #4 do relatório de análise
```

---

## 🟡 FASE 2: REFATORAÇÃO DE GOD OBJECTS (Paralelo)
**Prioridade**: ALTA
**Dependências**: FASE 1 completa
**Tempo Estimado**: 3-4 semanas
**Paralelizável**: SIM (5 tasks independentes)

### Task 2.1: Refatorar GUI.py (Extração de Componentes UI)
**ID**: `REFACTOR-GUI-001`
**Arquivos**: `src/zebtrack/ui/gui.py` (9951 linhas → objetivo: ~4000 linhas)
**Paralelizável**: ✅ SIM (arquivos únicos)

**Objetivo**: Extrair componentes UI em módulos independentes

**Estratégia**:
1. **Criar `ui/components/menu_manager.py`** (~800 linhas)
   - Extrair métodos de menu (File, Edit, View, etc.)
   - Métodos: `_create_menu_bar()`, `_create_file_menu()`, etc.

2. **Criar `ui/components/canvas_manager.py`** (~1200 linhas)
   - Extrair métodos de desenho e overlay
   - Métodos: `_draw_*()`, `_update_overlay()`, etc.

3. **Criar `ui/components/state_synchronizer.py`** (~600 linhas)
   - Extrair métodos de sincronização de estado
   - Métodos: `_update_ui_from_state()`, `_sync_*()`, etc.

4. **Criar `ui/components/event_dispatcher.py`** (~400 linhas)
   - Extrair handlers de eventos
   - Métodos: `_on_*()`, `_handle_*()`, etc.

**Validação**:
```bash
poetry run pytest tests/test_gui.py -v
poetry run pytest tests/integration/test_gui_integration.py -v
```

**Entregáveis**:
- 4 novos arquivos em `ui/components/`
- `gui.py` reduzido para ~4000 linhas
- Testes existentes continuam passando
- Commit com descrição das extrações

---

### Task 2.2: Refatorar MainViewModel.py (Extração de Serviços)
**ID**: `REFACTOR-VIEWMODEL-001`
**Arquivos**: `src/zebtrack/core/main_view_model.py` (5588 linhas → objetivo: ~2500 linhas)
**Paralelizável**: ✅ SIM (arquivos únicos)

**Objetivo**: Reduzir de 13 dependências para 8, extrair lógica de negócio

**Estratégia**:
1. **Criar `core/video_orchestrator.py`** (~800 linhas)
   - Extrair métodos de processamento de vídeo
   - Métodos: `process_single_video()`, `process_batch()`, etc.
   - Dependências: `video_processing_service`, `detector_service`, `recorder`

2. **Criar `core/hardware_coordinator.py`** (~400 linhas)
   - Extrair métodos de hardware (camera, Arduino)
   - Métodos: `setup_camera()`, `send_arduino_command()`, etc.
   - Dependências: `camera`, `arduino_facade`

3. **Criar `core/analysis_coordinator.py`** (~600 linhas)
   - Extrair métodos de análise
   - Métodos: `run_analysis()`, `generate_reports()`, etc.
   - Dependências: `analysis_service`, `reporter`

4. **Refatorar MainViewModel** (restante: ~2500 linhas)
   - Manter apenas orquestração high-level
   - Reduzir para 8 dependências principais

**Validação**:
```bash
poetry run pytest tests/test_main_view_model.py -v
poetry run pytest tests/integration/ -v
```

**Entregáveis**:
- 3 novos serviços em `core/`
- `main_view_model.py` reduzido para ~2500 linhas
- Testes existentes adaptados
- Commit com descrição das extrações

---

### Task 2.3: Refatorar ProjectManager.py (Separação de Responsabilidades)
**ID**: `REFACTOR-PROJECTMGR-001`
**Arquivos**: `src/zebtrack/core/project_manager.py` (2795 linhas → objetivo: ~1200 linhas)
**Paralelizável**: ✅ SIM (arquivos únicos)

**Objetivo**: Separar gerenciamento de projetos, vídeos, zonas e assets

**Estratégia**:
1. **Criar `core/video_manager.py`** (~500 linhas)
   - Extrair métodos de gerenciamento de vídeos
   - Métodos: `add_video()`, `remove_video()`, `get_video_info()`, etc.

2. **Criar `core/zone_manager.py`** (~600 linhas)
   - Extrair métodos de zonas e ROIs
   - Métodos: `add_zone()`, `update_zone()`, `get_zone_data()`, etc.

3. **Criar `core/asset_manager.py`** (~400 linhas)
   - Extrair métodos de assets (profiles, templates)
   - Métodos: `load_profile()`, `save_template()`, etc.

4. **Refatorar ProjectManager** (restante: ~1200 linhas)
   - Manter apenas lógica core de projeto
   - Delegar para managers especializados

**Validação**:
```bash
poetry run pytest tests/test_project_manager.py -v
poetry run pytest tests/test_project_manager_video_operations.py -v
```

**Entregáveis**:
- 3 novos managers em `core/`
- `project_manager.py` reduzido para ~1200 linhas
- Testes existentes adaptados
- Commit com descrição das extrações

---

### Task 2.4: Refatorar VideoProcessingService.py (Quebrar Método God)
**ID**: `REFACTOR-VIDEOPROCESSING-001`
**Arquivos**: `src/zebtrack/core/video_processing_service.py` (1513 linhas → objetivo: ~1000 linhas)
**Paralelizável**: ✅ SIM (arquivos únicos)

**Objetivo**: Quebrar `_collect_params_from_single_video()` (641 linhas, CC ~40)

**Estratégia**:
1. **Extrair `_validate_arena_roi_compatibility()`** (~80 linhas)
   - Validação de compatibilidade arena/ROI

2. **Extrair `_setup_detector_for_video()`** (~100 linhas)
   - Setup de detector e zonas

3. **Extrair `_collect_detection_params()`** (~150 linhas)
   - Coleta de parâmetros de detecção

4. **Extrair `_collect_recording_params()`** (~120 linhas)
   - Coleta de parâmetros de gravação

5. **Extrair `_collect_analysis_params()`** (~100 linhas)
   - Coleta de parâmetros de análise

6. **Refatorar `_collect_params_from_single_video()`** (restante: ~90 linhas)
   - Apenas orquestração dos métodos extraídos
   - Complexidade ciclomática reduzida para ~8

**Validação**:
```bash
poetry run pytest tests/test_video_processing_service.py -v
poetry run pytest tests/integration/test_video_processing.py -v
```

**Entregáveis**:
- 5 novos métodos privados bem definidos
- `_collect_params_from_single_video()` reduzido para ~90 linhas
- Testes existentes continuam passando
- Commit com descrição da refatoração

---

### Task 2.5: Refatorar Reporter.py (Separar Transformação/Visualização/Relatório)
**ID**: `REFACTOR-REPORTER-001`
**Arquivos**: `src/zebtrack/analysis/reporter.py` (1412 linhas → objetivo: ~600 linhas)
**Paralelizável**: ✅ SIM (arquivos únicos)

**Objetivo**: Separar responsabilidades de transformação, visualização e geração de relatórios

**Estratégia**:
1. **Criar `analysis/data_transformer.py`** (~300 linhas)
   - Extrair métodos de transformação de dados
   - Métodos: `_transform_trajectory_data()`, `_calculate_metrics()`, etc.

2. **Criar `analysis/visualization_generator.py`** (~400 linhas)
   - Extrair métodos de visualização
   - Métodos: `_generate_heatmap()`, `_generate_trajectory_plot()`, etc.

3. **Refatorar Reporter** (restante: ~600 linhas)
   - Manter apenas geração de relatórios finais (Excel, Word)
   - Usar `DataTransformer` e `VisualizationGenerator`

**Validação**:
```bash
poetry run pytest tests/test_reporter.py -v
```

**Entregáveis**:
- 2 novos módulos em `analysis/`
- `reporter.py` reduzido para ~600 linhas
- Testes existentes adaptados
- Commit com descrição das extrações

---

## 🟢 FASE 3: TESTES CRÍTICOS (Paralelo com Fase 2)
**Prioridade**: CRÍTICA
**Dependências**: FASE 1 completa
**Tempo Estimado**: 2-3 semanas
**Paralelizável**: SIM (6 tasks independentes)

### Task 3.1: Testes AquariumDetector (0% → 90%)
**ID**: `TEST-AQUARIUM-001`
**Arquivos**: `tests/test_aquarium_detector.py` (NOVO, ~200 linhas)
**Paralelizável**: ✅ SIM (novo arquivo)

**Objetivo**: Adicionar cobertura completa para módulo crítico sem testes

**Cenários de Teste**:
1. **Teste de Inicialização**:
   - Model loading com arquivo válido
   - Error handling: arquivo não existe
   - Error handling: arquivo corrompido
   - Error handling: formato inválido

2. **Teste de IoU Calculation**:
   - Polígonos válidos com overlap
   - Polígonos sem overlap (IoU = 0)
   - Polígonos coincidentes (IoU = 1)
   - Edge cases: polígonos degenerados, área zero

3. **Teste de Polygon Extraction**:
   - Detecção com segmentação válida
   - Detecção com bounding box apenas
   - Resultado vazio/None
   - Múltiplas detecções com filtro de confiança

4. **Teste de Detection**:
   - Frame único com detecção válida
   - Mode switching (seg vs det)
   - Error handling: frame inválido, modelo não carregado

5. **Teste de Video Detection**:
   - Vídeo completo com múltiplos frames
   - Error handling: vídeo não existe, vídeo corrompido
   - Progress callback verification

6. **Teste de Stabilization**:
   - Temporal consistency com frames consecutivos
   - Outlier detection
   - Boundary conditions (início/fim de vídeo)

**Estrutura do Teste**:
```python
import pytest
from zebtrack.core.aquarium_detector import AquariumDetector

class TestAquariumDetectorInit:
    def test_init_valid_model(self, tmp_path):
        # Test valid model loading

    def test_init_missing_model(self):
        # Test error handling for missing file

class TestAquariumDetectorIoU:
    def test_iou_overlapping_polygons(self):
        # Test IoU calculation with overlap

class TestAquariumDetectorExtraction:
    def test_extract_polygon_from_detection_with_seg(self):
        # Test segmentation extraction

# ... mais 3-4 classes de teste
```

**Validação**:
```bash
poetry run pytest tests/test_aquarium_detector.py -v --cov=src/zebtrack/core/aquarium_detector
# Objetivo: >90% cobertura
```

**Entregáveis**:
- `tests/test_aquarium_detector.py` (~200 linhas)
- 6 classes de teste, ~20 métodos de teste
- Cobertura >90%
- Commit: "test: adicionar cobertura completa para AquariumDetector"

---

### Task 3.2: Testes LiveCameraService Thread Safety
**ID**: `TEST-LIVECAMERA-001`
**Arquivos**: `tests/test_live_camera_service_threading.py` (NOVO, ~400 linhas)
**Paralelizável**: ✅ SIM (novo arquivo)

**Objetivo**: Garantir thread safety e testar cenários de concorrência

**Cenários de Teste**:
1. **Teste de Thread Lifecycle**:
   - Start/stop de threads múltiplas vezes
   - Join timeout handling
   - Graceful shutdown com queue cheia
   - Daemon thread cleanup

2. **Teste de Queue Operations**:
   - Frame queue overflow (put com timeout)
   - Frame queue empty (get com timeout)
   - Múltiplos producers/consumers
   - Queue cleanup no stop

3. **Teste de Race Conditions**:
   - Concurrent start/stop calls
   - Detector access durante processing
   - Preview update durante session stop
   - State manager updates concorrentes

4. **Teste de Error Handling em Threads**:
   - Camera disconnect durante capture
   - Detection failure durante processing
   - Preview update exception handling
   - Thread crash recovery

5. **Teste de Memory Pressure**:
   - Frame queue com limite atingido
   - Frame drop scenarios
   - Memory leak detection (session repetida)

6. **Teste de Integration com RecordingService**:
   - Timed session expiration
   - Manual stop durante recording
   - Callback registration e execution
   - Output directory creation

**Estrutura do Teste**:
```python
import pytest
import threading
import time
from unittest.mock import Mock, patch
from zebtrack.core.live_camera_service import LiveCameraService

class TestLiveCameraServiceThreading:
    def test_thread_start_stop_lifecycle(self, live_camera_service):
        # Test thread lifecycle

    def test_rapid_start_stop_cycles(self, live_camera_service):
        # Test race conditions in start/stop

class TestLiveCameraServiceQueueOperations:
    def test_frame_queue_overflow(self, live_camera_service):
        # Test queue full scenario

# ... mais classes
```

**Validação**:
```bash
poetry run pytest tests/test_live_camera_service_threading.py -v -n0
# Note: -n0 para rodar sequencialmente (teste de threading)
poetry run pytest tests/test_live_camera_service_threading.py --repeat 10
# Rodar múltiplas vezes para detectar race conditions
```

**Entregáveis**:
- `tests/test_live_camera_service_threading.py` (~400 linhas)
- 6 classes de teste, ~25 métodos de teste
- Testes de concorrência validados com múltiplas execuções
- Commit: "test: adicionar testes de thread safety para LiveCameraService"

---

### Task 3.3: Testes LiveAnalysisDialog e LivePreviewWindow
**ID**: `TEST-LIVEUI-001`
**Arquivos**: `tests/test_live_analysis_ui.py` (NOVO, ~250 linhas)
**Paralelizável**: ✅ SIM (novo arquivo)

**Objetivo**: Testar UI de live analysis (v2.0 feature)

**Cenários de Teste**:
1. **LiveAnalysisDialog**:
   - Initialization com valores default
   - Camera hardware detection (mock WizardService)
   - Duration validation (bounds, invalid input)
   - Analysis interval validation
   - Record video checkbox state
   - Experiment ID generation
   - OK button (result assembly)
   - Cancel button (result=None)
   - Hardware detection caching

2. **LivePreviewWindow**:
   - Window creation e layout
   - Frame update com detections
   - Duration countdown
   - Stop button callback
   - FPS calculation
   - Image scaling/resize
   - Canvas updates
   - Auto-close on duration complete

**Estrutura do Teste**:
```python
import pytest
from unittest.mock import Mock, patch
from zebtrack.ui.dialogs import LiveAnalysisDialog, LivePreviewWindow

@pytest.mark.gui
class TestLiveAnalysisDialog:
    def test_init_default_values(self, root):
        dialog = LiveAnalysisDialog(root, controller=Mock())
        # Verify defaults

    def test_camera_detection(self, root):
        # Test hardware detection integration

@pytest.mark.gui
class TestLivePreviewWindow:
    def test_frame_update_with_detections(self, root):
        # Test frame display
```

**Validação**:
```bash
poetry run pytest tests/test_live_analysis_ui.py -v -m gui -n0
```

**Entregáveis**:
- `tests/test_live_analysis_ui.py` (~250 linhas)
- 2 classes de teste, ~18 métodos de teste
- Cobertura >80%
- Commit: "test: adicionar testes para LiveAnalysisDialog e LivePreviewWindow"

---

### Task 3.4: Testes Dialogs - Batch 1 (High Complexity)
**ID**: `TEST-DIALOGS-BATCH1-001`
**Arquivos**: `tests/ui/dialogs/test_dialogs_batch1.py` (NOVO, ~250 linhas)
**Paralelizável**: ✅ SIM (novo arquivo)

**Dialogs a Testar** (5 dialogs de alta complexidade):
1. `calibration_dialog.py` (983 linhas)
2. `create_project_dialog.py` (508 linhas)
3. `manage_weights_dialog.py` (300+ linhas)
4. `start_recording_dialog.py` (200+ linhas)
5. `single_video_config_dialog.py` (250+ linhas)

**Cenários por Dialog** (comum):
- Initialization
- Input validation
- OK/Cancel/Apply button behavior
- State persistence
- Error handling
- Integration com controller

**Estrutura do Teste**:
```python
import pytest
from zebtrack.ui.dialogs import (
    CalibrationDialog,
    CreateProjectDialog,
    ManageWeightsDialog,
    StartRecordingDialog,
    SingleVideoConfigDialog
)

@pytest.mark.gui
class TestCalibrationDialog:
    def test_init(self, root):
        # Test initialization

    def test_calibration_upload(self, root):
        # Test file upload

# ... 4 mais classes
```

**Validação**:
```bash
poetry run pytest tests/ui/dialogs/test_dialogs_batch1.py -v -m gui -n0
```

**Entregáveis**:
- `tests/ui/dialogs/test_dialogs_batch1.py` (~250 linhas)
- 5 classes de teste, ~25 métodos de teste
- Commit: "test: adicionar testes para dialogs batch 1 (alta complexidade)"

---

### Task 3.5: Testes Dialogs - Batch 2 (Medium Complexity)
**ID**: `TEST-DIALOGS-BATCH2-001`
**Arquivos**: `tests/ui/dialogs/test_dialogs_batch2.py` (NOVO, ~250 linhas)
**Paralelizável**: ✅ SIM (novo arquivo)

**Dialogs a Testar** (5 dialogs de média complexidade):
1. `template_dialog.py` (200+ linhas)
2. `pending_videos_dialog.py` (200+ linhas)
3. `center_periphery_dialog.py` (150+ linhas)
4. `diagnostic_progress_dialog.py` (150+ linhas)
5. `missing_metadata_dialog.py` (100+ linhas)

**Estrutura do Teste**:
```python
import pytest
from zebtrack.ui.dialogs import (
    TemplateDialog,
    PendingVideosDialog,
    CenterPeripheryDialog,
    DiagnosticProgressDialog,
    MissingMetadataDialog
)

@pytest.mark.gui
class TestTemplateDialog:
    def test_init(self, root):
        # Test initialization

# ... 4 mais classes
```

**Validação**:
```bash
poetry run pytest tests/ui/dialogs/test_dialogs_batch2.py -v -m gui -n0
```

**Entregáveis**:
- `tests/ui/dialogs/test_dialogs_batch2.py` (~250 linhas)
- 5 classes de teste, ~20 métodos de teste
- Commit: "test: adicionar testes para dialogs batch 2 (média complexidade)"

---

### Task 3.6: Testes Dialogs - Batch 3 (Low Complexity)
**ID**: `TEST-DIALOGS-BATCH3-001`
**Arquivos**: `tests/ui/dialogs/test_dialogs_batch3.py` (NOVO, ~200 linhas)
**Paralelizável**: ✅ SIM (novo arquivo)

**Dialogs a Testar** (5 dialogs de baixa complexidade):
1. `subject_selection_dialog.py` (150+ linhas)
2. `save_roi_template_dialog.py` (150+ linhas)
3. `color_selection_dialog.py` (100+ linhas)
4. Outros dialogs simples restantes

**Estrutura do Teste**:
```python
import pytest
from zebtrack.ui.dialogs import (
    SubjectSelectionDialog,
    SaveRoiTemplateDialog,
    ColorSelectionDialog
)

@pytest.mark.gui
class TestSubjectSelectionDialog:
    def test_init(self, root):
        # Test initialization

# ... mais classes
```

**Validação**:
```bash
poetry run pytest tests/ui/dialogs/test_dialogs_batch3.py -v -m gui -n0
```

**Entregáveis**:
- `tests/ui/dialogs/test_dialogs_batch3.py` (~200 linhas)
- 3-5 classes de teste, ~15 métodos de teste
- Commit: "test: adicionar testes para dialogs batch 3 (baixa complexidade)"

---

## 🔵 FASE 4: EXPANSÃO DE COBERTURA (Paralelo)
**Prioridade**: MÉDIA-ALTA
**Dependências**: FASE 1 completa
**Tempo Estimado**: 2-3 semanas
**Paralelizável**: SIM (4 tasks independentes)

### Task 4.1: Testes Error Handling Paths
**ID**: `TEST-ERRORHANDLING-001`
**Arquivos**: Múltiplos arquivos de teste existentes (expansão)
**Paralelizável**: ✅ SIM (arquivos distintos)

**Módulos a Expandir**:
1. `tests/test_detector_service.py` (+150 linhas)
   - Zone setup com polígonos inválidos
   - Model file corruption
   - Out-of-memory scenarios
   - Tracking parameter conflicts

2. `tests/test_recording_service.py` (+200 linhas)
   - Parquet writer failures (disk full)
   - Video writer initialization failures
   - Arduino command execution failures
   - State manager update failures

3. `tests/test_project_workflow_service.py` (+200 linhas)
   - Project load com arquivos missing
   - Zone import com geometria inválida
   - ROI template load failures
   - Concurrent project operations

**Validação**:
```bash
poetry run pytest tests/test_detector_service.py -v
poetry run pytest tests/test_recording_service.py -v
poetry run pytest tests/test_project_workflow_service.py -v
```

**Entregáveis**:
- 3 arquivos de teste expandidos (+550 linhas total)
- ~25 novos métodos de teste
- Commit: "test: expandir cobertura de error handling paths"

---

### Task 4.2: Testes Thread Safety Modules
**ID**: `TEST-THREADSAFETY-001`
**Arquivos**: Múltiplos novos arquivos de teste
**Paralelizável**: ✅ SIM (novos arquivos)

**Módulos a Testar** (8 módulos sem testes de threading):
1. `tests/test_main_view_model_threading.py` (NOVO, ~300 linhas)
   - Concurrent detector/recording operations
   - UI callback synchronization
   - State manager integration

2. `tests/test_project_manager_threading.py` (NOVO, ~200 linhas)
   - Concurrent project updates
   - Zone data access concorrente

3. `tests/test_ui_coordinator_threading.py` (NOVO, ~200 linhas)
   - State update synchronization
   - Event queue processing

4. `tests/test_weight_manager_threading.py` (NOVO, ~150 linhas)
   - Concurrent weight access
   - Lock contention scenarios

**Validação**:
```bash
poetry run pytest tests/test_*_threading.py -v -n0 --repeat 10
```

**Entregáveis**:
- 4 novos arquivos de teste (~850 linhas total)
- ~40 métodos de teste
- Commit: "test: adicionar testes de thread safety para múltiplos módulos"

---

### Task 4.3: Testes Wizard Integration
**ID**: `TEST-WIZARD-001`
**Arquivos**: Múltiplos arquivos de teste para wizard steps
**Paralelizável**: ✅ SIM (arquivos distintos por step)

**Wizard Steps a Testar** (4 steps com baixa cobertura):
1. `tests/wizard/test_calibration_step.py` (NOVO, ~150 linhas)
   - Calibration upload
   - Validation
   - Preview display

2. `tests/wizard/test_model_selection_step.py` (NOVO, ~120 linhas)
   - Model list loading
   - Selection logic
   - Weight path validation

3. `tests/wizard/test_confirmation_step.py` (expansão, +100 linhas)
   - Error display
   - Data validation
   - Navigation logic

4. `tests/wizard/test_detection_step.py` (expansão, +150 linhas)
   - Model loading
   - Threshold testing
   - Parameter validation

**Validação**:
```bash
poetry run pytest tests/wizard/ -v -m gui -n0
```

**Entregáveis**:
- 2 novos arquivos + 2 expandidos (~520 linhas total)
- ~30 métodos de teste
- Commit: "test: expandir cobertura de testes para wizard integration"

---

### Task 4.4: Testes Edge Cases e Boundary Conditions
**ID**: `TEST-EDGECASES-001`
**Arquivos**: Múltiplos arquivos de teste (expansão)
**Paralelizável**: ✅ SIM (arquivos distintos)

**Categorias de Edge Cases**:
1. **Recorder Edge Cases** (`tests/test_recorder.py`, +150 linhas)
   - Empty detection list
   - Single frame recording
   - Very large detection count (1000+ per frame)
   - Calibration columns com NaN
   - Timestamp discontinuities

2. **Behavior Analysis Edge Cases** (`tests/test_behavior.py`, +120 linhas)
   - Zero-velocity conditions
   - Negative displacement
   - Very short trajectories (<1s)
   - Noisy position data
   - Outlier detection

3. **Zone Management Edge Cases** (`tests/test_zone_manager.py`, +130 linhas)
   - Self-intersecting polygons
   - Degenerate zones (point, line)
   - Zones outside arena bounds
   - Very small zones (1-5 pixels)
   - Overlapping zones

**Validação**:
```bash
poetry run pytest tests/test_recorder.py tests/test_behavior.py tests/test_zone_manager.py -v
```

**Entregáveis**:
- 3 arquivos de teste expandidos (+400 linhas total)
- ~25 métodos de teste
- Commit: "test: adicionar testes para edge cases e boundary conditions"

---

## 📝 RESUMO DE TAREFAS POR ARQUIVO

### Arquivos que NÃO Podem Ser Modificados Simultaneamente
| Arquivo | Tasks Conflitantes | Solução |
|---------|-------------------|---------|
| `main_view_model.py` | Task 1.1, Task 2.2 | Executar Task 1.1 PRIMEIRO |
| `live_camera_service.py` | Task 1.1, Task 3.2 | Executar Task 1.1 PRIMEIRO |
| `gui.py` | Task 2.1 | Apenas Task 2.1 modifica |

### Tarefas Totalmente Paralelas (ZERO conflito)
- **FASE 2**: Tasks 2.1, 2.3, 2.4, 2.5 (após 1.1 e 2.2 completos)
- **FASE 3**: Tasks 3.1, 3.2, 3.3, 3.4, 3.5, 3.6 (todas paralelas)
- **FASE 4**: Tasks 4.1, 4.2, 4.3, 4.4 (todas paralelas)

---

## 🚀 ESTRATÉGIA DE EXECUÇÃO PARALELA

### Rodada 1 (Sequencial - CRÍTICA)
1. ✅ **Task 1.1** (Conversa Principal) - Bugfixes críticos
2. ⏸️ Aguardar commit e push de Task 1.1

### Rodada 2 (Paralelo - 2 conversas)
1. 🟡 **Task 2.2** (Conversa A) - Refatorar MainViewModel
2. 🟢 **Task 3.1** (Conversa B) - Testes AquariumDetector

### Rodada 3 (Paralelo - 5 conversas)
1. 🟡 **Task 2.1** (Conversa C) - Refatorar GUI
2. 🟡 **Task 2.3** (Conversa D) - Refatorar ProjectManager
3. 🟡 **Task 2.4** (Conversa E) - Refatorar VideoProcessingService
4. 🟢 **Task 3.2** (Conversa F) - Testes LiveCameraService threading
5. 🟢 **Task 3.3** (Conversa G) - Testes LiveAnalysis UI

### Rodada 4 (Paralelo - 6 conversas)
1. 🟡 **Task 2.5** (Conversa H) - Refatorar Reporter
2. 🟢 **Task 3.4** (Conversa I) - Testes Dialogs Batch 1
3. 🟢 **Task 3.5** (Conversa J) - Testes Dialogs Batch 2
4. 🟢 **Task 3.6** (Conversa K) - Testes Dialogs Batch 3
5. 🔵 **Task 4.1** (Conversa L) - Testes Error Handling
6. 🔵 **Task 4.2** (Conversa M) - Testes Thread Safety

### Rodada 5 (Paralelo - 2 conversas)
1. 🔵 **Task 4.3** (Conversa N) - Testes Wizard Integration
2. 🔵 **Task 4.4** (Conversa O) - Testes Edge Cases

---

## 📊 MÉTRICAS DE SUCESSO

### Cobertura de Testes
- **Inicial**: 70% (712 testes)
- **Meta Final**: 85% (~1,000+ testes)
- **Incremento**: +288 testes, +6,550 linhas

### Redução de God Objects
| Arquivo | Antes | Depois | Redução |
|---------|-------|--------|---------|
| gui.py | 9,951 | ~4,000 | -60% |
| main_view_model.py | 5,588 | ~2,500 | -55% |
| project_manager.py | 2,795 | ~1,200 | -57% |
| video_processing_service.py | 1,513 | ~1,000 | -34% |
| reporter.py | 1,412 | ~600 | -58% |

### Bugs Corrigidos
- 4 bugs críticos/high corrigidos

---

## 🔄 PROTOCOLO DE MERGE

Cada task deve seguir:

1. **Pré-Merge**:
   ```bash
   git fetch origin claude/fix-post-refactor-bugs-011CUpYC3FjTK9gyrCusQND3
   git rebase origin/claude/fix-post-refactor-bugs-011CUpYC3FjTK9gyrCusQND3
   ```

2. **Validação**:
   ```bash
   poetry run pytest -q  # Todos passam
   poetry run ruff check .  # Sem erros
   ```

3. **Commit**:
   ```bash
   git add <arquivos modificados>
   git commit -m "<mensagem descritiva>"
   ```

4. **Push**:
   ```bash
   git push -u origin claude/fix-post-refactor-bugs-011CUpYC3FjTK9gyrCusQND3
   ```

5. **Notificar**:
   - Atualizar status no EXECUTION_PLAN.md
   - Commit: "docs: atualizar status de task X"

---

## 📞 CONTEXTO PARA NOVAS CONVERSAS

**Template de Contexto**:
```
# Contexto da Task [ID]

## Projeto
- Nome: ZebTrack-AI
- Branch: claude/fix-post-refactor-bugs-011CUpYC3FjTK9gyrCusQND3
- Arquitetura: MVVM-S com DI
- Tech Stack: Python 3.12+, Poetry, Tkinter, YOLO

## Objetivo da Task
[Descrição específica da task]

## Arquivos a Modificar
[Lista de arquivos]

## Dependências Completadas
- Task 1.1: Bugfixes críticos (COMPLETADO)

## Validação
[Comandos específicos]

## Commit Message
[Mensagem pré-definida]

## Documentos de Referência
- CLAUDE.md (instruções do projeto)
- docs/ARCHITECTURE.md
- docs/CHEATSHEET.md
- EXECUTION_PLAN.md (este documento)
```

---

## ✅ CHECKLIST FINAL

### Antes de Iniciar Execução
- [ ] Task 1.1 completa e commitada
- [ ] Branch atualizada: `git pull origin claude/fix-post-refactor-bugs-011CUpYC3FjTK9gyrCusQND3`
- [ ] Pytest baseline: `poetry run pytest -q` (todos passam)
- [ ] Ruff baseline: `poetry run ruff check .` (sem erros)

### Durante Execução de Cada Task
- [ ] Ler CLAUDE.md antes de começar
- [ ] Ler documentação relevante (ARCHITECTURE.md, etc.)
- [ ] Implementar mudanças conforme especificação
- [ ] Rodar testes locais: `poetry run pytest <arquivo> -v`
- [ ] Rodar linting: `poetry run ruff check <arquivo>`
- [ ] Atualizar documentação se necessário
- [ ] Commit com mensagem descritiva

### Após Completar Cada Task
- [ ] Todos os testes passando: `poetry run pytest -q`
- [ ] Sem erros de linting: `poetry run ruff check .`
- [ ] Push para branch: `git push -u origin <branch>`
- [ ] Atualizar EXECUTION_PLAN.md com status
- [ ] Notificar conclusão

---

## 📚 REFERÊNCIAS

- **CLAUDE.md**: Instruções do projeto
- **GOD_OBJECTS_ANALYSIS.md**: Análise detalhada dos God Objects
- **docs/ARCHITECTURE.md**: Arquitetura do sistema
- **docs/CHEATSHEET.md**: Referência rápida
- **README_TESTS.md**: Guia de testes

---

**Última Atualização**: 2025-11-05
**Status Geral**: PENDENTE
**Progresso**: 0/21 tasks completas
