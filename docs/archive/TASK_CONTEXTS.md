# Contextos de Tarefas para Execução Paralela
## ZebTrack-AI - Refatoração e Correções

**Branch**: `claude/fix-post-refactor-bugs-011CUpYC3FjTK9gyrCusQND3`
**Documento Base**: `EXECUTION_PLAN.md`

---

## 📋 Como Usar Este Documento

1. **Criar nova conversa** com Claude Code
2. **Copiar o contexto da task** desejada (seção completa)
3. **Colar na nova conversa** para iniciar a task
4. **Aguardar conclusão** e verificar commit/push
5. **Atualizar status** no `EXECUTION_PLAN.md`

---

## ⚠️ IMPORTANTE - Ordem de Execução

**PRIMEIRO** (Sequencial):
- Task 1.1 - DEVE ser completada antes de qualquer outra

**DEPOIS** (Paralelo - Rodada 2):
- Task 2.2 + Task 3.1 (podem rodar juntas)

**DEPOIS** (Paralelo - Rodada 3+):
- Todas as outras tasks podem rodar em paralelo

---

# Task 1.1: Corrigir Bugs Críticos
**ID**: `BUGFIX-CRITICAL-001`
**Status**: PENDENTE
**Prioridade**: CRÍTICA
**Tempo Estimado**: 1-2 horas

## Contexto do Projeto

**Nome**: ZebTrack-AI
**Descrição**: Python 3.12+ Tkinter app para rastreamento e análise comportamental de zebrafish
**Arquitetura**: MVVM-S com Dependency Injection
**Tech Stack**: Poetry, Tkinter, YOLO/OpenVINO, Parquet, structlog, Pydantic v2
**Branch**: `claude/fix-post-refactor-bugs-011CUpYC3FjTK9gyrCusQND3`

## Objetivo da Task

Corrigir 4 bugs críticos/high detectados após refatoração recente:
1. Import incorreto de `DiagnosticProgressDialog`
2. Callback de completion não registrado em `LiveCameraService`
3. Violação de thread safety em preview updates
4. Zone rescaling com dimensões incorretas

Estes bugs foram introduzidos durante a extração de dialogs (Phase 4) e integração do `LiveCameraService` (v2.0).

## Bugs Detalhados

### BUG #1 (CRITICAL): Import Incorreto
**Arquivo**: `src/zebtrack/core/main_view_model.py:5153`
**Problema**: `from zebtrack.ui.gui import DiagnosticProgressDialog`
**Causa**: Dialog foi extraído para módulo separado mas import não foi atualizado
**Impacto**: ImportError quando diagnostic tool é invocado, feature quebra completamente

**Fix**:
```python
# Linha 5153: Trocar
from zebtrack.ui.gui import DiagnosticProgressDialog

# Por:
from zebtrack.ui.dialogs import DiagnosticProgressDialog
```

**Validação**: Verificar que `DiagnosticProgressDialog` está em `src/zebtrack/ui/dialogs/__init__.py`

---

### BUG #2 (HIGH): Callback Não Registrado
**Arquivo**: `src/zebtrack/core/live_camera_service.py:183-191`
**Problema**: `on_complete` callback é definido mas nunca passado para `RecordingService`
**Causa**: Callback criado mas não registrado na chamada de `start_session()`
**Impacto**: Session completa sem notificar usuário, nenhum feedback sobre onde resultados foram salvos

**Context** (linhas 183-191):
```python
def on_complete():
    self._on_session_complete(output_dir)

# Register UI callbacks with RecordingService
self.recording_service.set_ui_callbacks({
    "stop_recording_callback": self.stop_session,
})

self.recording_service.start_session(
    context=context,
    project_data=project_data,
    trigger_source="live_analysis",
)
```

**Fix**: Adicionar callback ao dict de UI callbacks:
```python
def on_complete():
    self._on_session_complete(output_dir)

# Register UI callbacks with RecordingService
self.recording_service.set_ui_callbacks({
    "stop_recording_callback": self.stop_session,
    "on_complete_callback": on_complete,  # ADICIONAR ESTA LINHA
})

self.recording_service.start_session(
    context=context,
    project_data=project_data,
    trigger_source="live_analysis",
)
```

**Nota**: Verificar se `RecordingService.set_ui_callbacks()` suporta `on_complete_callback`. Se não, ajustar método para aceitar este callback.

---

### BUG #3 (HIGH): Violação Thread Safety
**Arquivo**: `src/zebtrack/core/live_camera_service.py:402-407`
**Problema**: `preview_window.update_frame()` é chamado diretamente de worker thread
**Causa**: Update de Tkinter widget sem usar `root.after(0, ...)`
**Impacto**: Crashes aleatórios, UI congelada, display corrompido (depende de timing)

**Context** (linhas 402-407):
```python
# Chamado de _processing_loop() worker thread
if self.preview_window and should_display:
    try:
        self.preview_window.update_frame(frame, detections)
    except Exception as e:
        log.error("live_camera_service.preview_update_error", error=str(e))
```

**Fix**: Agendar update na main thread:
```python
if self.preview_window and should_display:
    try:
        if self.root:
            # CRITICAL: Schedule on main thread for Tkinter thread safety
            self.root.after(0, self.preview_window.update_frame, frame, detections)
        else:
            # Fallback se root não disponível (edge case)
            self.preview_window.update_frame(frame, detections)
    except Exception as e:
        log.error("live_camera_service.preview_update_error", error=str(e))
```

**Referência**: `CLAUDE.md` - seção "Threading & UI":
> "All UI updates MUST use `root.after(0, ...)` (Tkinter main thread)"

---

### BUG #4 (MEDIUM): Zone Rescaling Incorreto
**Arquivo**: `src/zebtrack/core/live_camera_service.py:148`
**Related**: `src/zebtrack/core/detector_service.py:250-256`
**Problema**: Zones rescaled para `desired_width/height` ao invés de dimensões reais da câmera
**Causa**: `setup_detector_zones()` chamado sem passar dimensões da câmera
**Impacto**: Detection ROI checks incorretos se câmera real tem resolução diferente da configurada

**Exemplo de Problema**:
- Zones definidas para câmera 640x480
- Live session inicia com câmera 1920x1080
- Zones são rescaled para desired_width/height (640x480) ao invés de 1920x1080
- Coordinate transformations e ROI checks ficam errados

**Context** (linhas 145-149):
```python
zone_data = self.project_manager.get_zone_data() if self.project_manager else None
if zone_data and self.camera:
    self.controller.setup_detector_zones()  # SEM dimensões!
```

**Fix**: Passar dimensões reais da câmera:
```python
zone_data = self.project_manager.get_zone_data() if self.project_manager else None
if zone_data and self.camera:
    # CRITICAL: Use actual camera dimensions for zone rescaling
    self.detector_service.configure_zones(
        zone_data=zone_data,
        width=self.camera.actual_width,
        height=self.camera.actual_height
    )
```

**Nota**: Verificar que `Camera` tem atributos `actual_width` e `actual_height`. Se não, usar `self.camera.width` e `self.camera.height` ou equivalente.

**Referência**: `docs/COORDINATE_SYSTEMS.md`:
> "MUST call Detector.set_zones() after video dimensions known to rescale"

---

## Arquivos a Modificar

1. `src/zebtrack/core/main_view_model.py` (1 linha - import)
2. `src/zebtrack/core/live_camera_service.py` (3 seções)

## Comandos de Setup

```bash
# Verificar branch correta
git branch --show-current
# Deve mostrar: claude/fix-post-refactor-bugs-011CUpYC3FjTK9gyrCusQND3

# Se não estiver na branch, fazer checkout
git checkout claude/fix-post-refactor-bugs-011CUpYC3FjTK9gyrCusQND3

# Atualizar branch
git pull origin claude/fix-post-refactor-bugs-011CUpYC3FjTK9gyrCusQND3

# Verificar status inicial
git status
```

## Implementação Passo-a-Passo

1. **Ler arquivos afetados**:
   - `src/zebtrack/core/main_view_model.py` (procurar linha ~5153)
   - `src/zebtrack/core/live_camera_service.py` (linhas ~145-191, ~402-407)

2. **Aplicar fixes** (na ordem):
   - Fix BUG #1: Update import
   - Fix BUG #2: Register callback
   - Fix BUG #3: Add root.after(0, ...)
   - Fix BUG #4: Pass camera dimensions

3. **Verificar sintaxe**:
   ```bash
   poetry run ruff check src/zebtrack/core/main_view_model.py
   poetry run ruff check src/zebtrack/core/live_camera_service.py
   ```

4. **Rodar testes relevantes**:
   ```bash
   # Teste de MainViewModel
   poetry run pytest tests/test_main_view_model.py -v

   # Testes de LiveCameraService
   poetry run pytest tests/integration/test_live_camera_analysis_integration.py -v

   # Se testes falharem, analisar e ajustar
   ```

5. **Rodar suite completa** (garantir nenhuma regressão):
   ```bash
   poetry run pytest -q
   # Todos os 712 testes devem passar
   ```

## Validação Final

```bash
# Linting (sem erros)
poetry run ruff check .

# Testes (todos passam)
poetry run pytest -q

# Verificar mudanças
git diff
```

## Commit e Push

```bash
# Adicionar arquivos modificados
git add src/zebtrack/core/main_view_model.py
git add src/zebtrack/core/live_camera_service.py

# Commit com mensagem descritiva
git commit -m "fix: corrigir 4 bugs críticos pós-refatoração

- Fix import de DiagnosticProgressDialog (main_view_model.py:5153)
- Fix callback de completion não registrado (live_camera_service.py:183)
- Fix violação thread safety em preview updates (live_camera_service.py:405)
- Fix zone rescaling com dimensões incorretas (live_camera_service.py:148)

Refs: BUG #1, #2, #3, #4 do relatório de análise
Closes: BUGFIX-CRITICAL-001"

# Push para branch
git push -u origin claude/fix-post-refactor-bugs-011CUpYC3FjTK9gyrCusQND3
```

## Documentação de Referência

- `CLAUDE.md` - Instruções gerais do projeto
- `EXECUTION_PLAN.md` - Plano completo de execução
- `docs/COORDINATE_SYSTEMS.md` - Sistemas de coordenadas e zones
- `docs/ARCHITECTURE.md` - Arquitetura MVVM-S

## Notas Importantes

1. **NÃO simplificar** funções ou código por economia de tokens
2. **Manter** toda a lógica e funcionalidade existente
3. **Apenas corrigir** os 4 bugs especificados
4. **Não refatorar** outras partes do código nesta task
5. **Thread safety** é crítico - sempre usar `root.after(0, ...)` para UI updates

## Próximas Tasks

Após completar e fazer push desta task:
- **Task 2.2**: Refatorar MainViewModel (pode iniciar em paralelo com Task 3.1)
- **Task 3.1**: Testes AquariumDetector (pode iniciar em paralelo com Task 2.2)

---

# Task 2.2: Refatorar MainViewModel
**ID**: `REFACTOR-VIEWMODEL-001`
**Status**: PENDENTE
**Prioridade**: ALTA
**Dependências**: Task 1.1 completa
**Tempo Estimado**: 3-5 dias

## Contexto do Projeto

[Mesmo contexto de Task 1.1]

## Objetivo da Task

Refatorar `MainViewModel` (5588 linhas) extraindo lógica de negócio em serviços especializados:
- Reduzir de 13 dependências para 8
- Extrair processamento de vídeo para `VideoOrchestrator`
- Extrair coordenação de hardware para `HardwareCoordinator`
- Extrair coordenação de análise para `AnalysisCoordinator`
- Meta: ~2500 linhas no MainViewModel final

## Arquivos a Criar

1. `src/zebtrack/core/video_orchestrator.py` (~800 linhas)
2. `src/zebtrack/core/hardware_coordinator.py` (~400 linhas)
3. `src/zebtrack/core/analysis_coordinator.py` (~600 linhas)

## Arquivo a Modificar

1. `src/zebtrack/core/main_view_model.py` (5588 → ~2500 linhas)

## Estratégia de Refatoração

### Fase 1: Criar VideoOrchestrator

**Métodos a Extrair** (buscar no main_view_model.py):
- `process_single_video()`
- `process_batch()`
- `_prepare_video_processing()`
- `_validate_video_requirements()`
- Outros métodos relacionados a processamento de vídeo

**Dependências do VideoOrchestrator**:
- `video_processing_service: VideoProcessingService`
- `detector_service: DetectorService`
- `recorder: Recorder`
- `state_manager: StateManager`

**Template Inicial**:
```python
"""Video processing orchestration service."""

import structlog
from zebtrack.core.video_processing_service import VideoProcessingService
from zebtrack.core.detector_service import DetectorService
from zebtrack.io.recorder import Recorder
from zebtrack.core.state_manager import StateManager

logger = structlog.get_logger()

class VideoOrchestrator:
    """Orchestrates video processing workflows."""

    def __init__(
        self,
        video_processing_service: VideoProcessingService,
        detector_service: DetectorService,
        recorder: Recorder,
        state_manager: StateManager
    ):
        self.video_processing_service = video_processing_service
        self.detector_service = detector_service
        self.recorder = recorder
        self.state_manager = state_manager

    def process_single_video(self, ...):
        """Process a single video."""
        # Extrair implementação de MainViewModel
        pass

    # ... mais métodos
```

### Fase 2: Criar HardwareCoordinator

**Métodos a Extrair**:
- `setup_camera()`
- `send_arduino_command()`
- `_validate_hardware()`
- Outros métodos relacionados a hardware

**Dependências do HardwareCoordinator**:
- `camera: Camera`
- `arduino_facade: ArduinoFacade`
- `state_manager: StateManager`

### Fase 3: Criar AnalysisCoordinator

**Métodos a Extrair**:
- `run_analysis()`
- `generate_reports()`
- `_prepare_analysis()`
- Outros métodos relacionados a análise

**Dependências do AnalysisCoordinator**:
- `analysis_service: AnalysisService`
- `reporter: Reporter`
- `state_manager: StateManager`

### Fase 4: Refatorar MainViewModel

1. **Atualizar `__init__`** para injetar novos coordinators
2. **Substituir métodos** por delegação aos coordinators
3. **Manter** apenas orquestração high-level
4. **Reduzir** lista de dependências injetadas

## Implementação Passo-a-Passo

1. **Ler arquivo completo**:
   ```bash
   # Ler MainViewModel para entender estrutura
   ```

2. **Criar VideoOrchestrator**:
   - Criar arquivo `src/zebtrack/core/video_orchestrator.py`
   - Extrair métodos relacionados a vídeo
   - Implementar __init__ com DI
   - Adicionar logging com structlog

3. **Criar HardwareCoordinator**:
   - Similar ao VideoOrchestrator

4. **Criar AnalysisCoordinator**:
   - Similar ao VideoOrchestrator

5. **Atualizar MainViewModel**:
   - Importar novos coordinators
   - Atualizar `__init__` no Composition Root (`__main__.py`)
   - Substituir implementações por delegação
   - Remover código duplicado

6. **Atualizar Composition Root** (`src/zebtrack/__main__.py`):
   - Instanciar novos coordinators
   - Injetar em MainViewModel

7. **Atualizar testes**:
   - Adaptar testes existentes de MainViewModel
   - Adicionar testes básicos para novos coordinators (opcional, mas recomendado)

## Validação

```bash
# Testes de MainViewModel
poetry run pytest tests/test_main_view_model.py -v

# Testes de integração
poetry run pytest tests/integration/ -v -k view_model

# Suite completa
poetry run pytest -q

# Linting
poetry run ruff check src/zebtrack/core/
```

## Commit e Push

```bash
git add src/zebtrack/core/video_orchestrator.py
git add src/zebtrack/core/hardware_coordinator.py
git add src/zebtrack/core/analysis_coordinator.py
git add src/zebtrack/core/main_view_model.py
git add src/zebtrack/__main__.py
git add tests/  # Se testes foram adaptados

git commit -m "refactor: extrair coordinators de MainViewModel

- Criar VideoOrchestrator (800 linhas)
- Criar HardwareCoordinator (400 linhas)
- Criar AnalysisCoordinator (600 linhas)
- Refatorar MainViewModel (5588 → 2500 linhas)
- Reduzir dependências de 13 para 8

Refs: REFACTOR-VIEWMODEL-001"

git push -u origin claude/fix-post-refactor-bugs-011CUpYC3FjTK9gyrCusQND3
```

## Documentação de Referência

- `EXECUTION_PLAN.md` - Detalhes da refatoração
- `docs/ARCHITECTURE.md` - Padrões de arquitetura
- `docs/DEPENDENCY_INJECTION_GUIDE.md` - Guia de DI

---

# Task 3.1: Testes AquariumDetector
**ID**: `TEST-AQUARIUM-001`
**Status**: PENDENTE
**Prioridade**: CRÍTICA
**Dependências**: Task 1.1 completa
**Tempo Estimado**: 1-2 dias

## Contexto do Projeto

[Mesmo contexto de Task 1.1]

## Objetivo da Task

Adicionar cobertura completa de testes para `AquariumDetector`:
- **Cobertura atual**: 0% (ZERO testes)
- **Meta**: >90% cobertura
- **Linhas de teste**: ~200 linhas
- **Classes de teste**: 6 classes, ~20 métodos

**Importância**: AquariumDetector é módulo CRÍTICO na pipeline de detecção, usado ativamente em produção, mas sem nenhum teste.

## Arquivo a Testar

`src/zebtrack/core/aquarium_detector.py` (452 linhas, 6 métodos públicos)

## Arquivo a Criar

`tests/test_aquarium_detector.py` (NOVO, ~200 linhas)

## Métodos a Testar

1. `__init__(model_path: str, use_seg: bool)` - Inicialização e carregamento de modelo
2. `_calculate_iou(poly1, poly2)` - Cálculo de IoU entre polígonos
3. `_extract_polygon_from_detection(results, use_seg)` - Extração de polígono de detecção
4. `detect(frame, mode)` - Detecção em frame único
5. `detect_from_video(video_path, mode)` - Detecção em vídeo
6. `stabilize_aquarium_region(detections)` - Estabilização temporal

## Estrutura do Teste

```python
"""Testes para AquariumDetector."""

import pytest
import numpy as np
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from zebtrack.core.aquarium_detector import AquariumDetector


class TestAquariumDetectorInit:
    """Testes de inicialização do AquariumDetector."""

    def test_init_valid_model(self, tmp_path):
        """Test: Inicialização com modelo válido."""
        # Criar mock de modelo
        model_path = tmp_path / "model.pt"
        model_path.write_text("fake model")

        with patch('zebtrack.core.aquarium_detector.YOLO') as mock_yolo:
            detector = AquariumDetector(str(model_path), use_seg=True)

            assert detector.model_path == str(model_path)
            assert detector.use_seg is True
            mock_yolo.assert_called_once_with(str(model_path))

    def test_init_missing_model(self):
        """Test: Error handling quando modelo não existe."""
        with pytest.raises(FileNotFoundError):
            AquariumDetector("/path/to/nonexistent/model.pt", use_seg=False)

    def test_init_invalid_model_format(self, tmp_path):
        """Test: Error handling com modelo corrompido."""
        model_path = tmp_path / "corrupt.pt"
        model_path.write_text("not a valid model")

        with patch('zebtrack.core.aquarium_detector.YOLO') as mock_yolo:
            mock_yolo.side_effect = RuntimeError("Invalid model format")

            with pytest.raises(RuntimeError):
                AquariumDetector(str(model_path), use_seg=True)


class TestAquariumDetectorIoU:
    """Testes de cálculo de IoU."""

    @pytest.fixture
    def detector(self, tmp_path):
        """Fixture: AquariumDetector mock."""
        model_path = tmp_path / "model.pt"
        model_path.write_text("fake model")
        with patch('zebtrack.core.aquarium_detector.YOLO'):
            return AquariumDetector(str(model_path), use_seg=False)

    def test_iou_overlapping_polygons(self, detector):
        """Test: IoU com polígonos sobrepostos."""
        poly1 = np.array([[0, 0], [10, 0], [10, 10], [0, 10]])
        poly2 = np.array([[5, 5], [15, 5], [15, 15], [5, 15]])

        iou = detector._calculate_iou(poly1, poly2)

        # IoU esperado: área de interseção / área de união
        # Área interseção: 5x5 = 25
        # Área união: 100 + 100 - 25 = 175
        # IoU = 25/175 ≈ 0.143
        assert 0.14 <= iou <= 0.15

    def test_iou_no_overlap(self, detector):
        """Test: IoU com polígonos sem overlap (IoU = 0)."""
        poly1 = np.array([[0, 0], [10, 0], [10, 10], [0, 10]])
        poly2 = np.array([[20, 20], [30, 20], [30, 30], [20, 30]])

        iou = detector._calculate_iou(poly1, poly2)

        assert iou == 0.0

    def test_iou_identical_polygons(self, detector):
        """Test: IoU com polígonos idênticos (IoU = 1)."""
        poly1 = np.array([[0, 0], [10, 0], [10, 10], [0, 10]])
        poly2 = np.array([[0, 0], [10, 0], [10, 10], [0, 10]])

        iou = detector._calculate_iou(poly1, poly2)

        assert iou == 1.0

    def test_iou_degenerate_polygon(self, detector):
        """Test: IoU com polígono degenerado (área zero)."""
        poly1 = np.array([[0, 0], [10, 0], [10, 10], [0, 10]])
        poly2 = np.array([[0, 0], [0, 0], [0, 0]])  # Ponto único

        iou = detector._calculate_iou(poly1, poly2)

        assert iou == 0.0


class TestAquariumDetectorExtraction:
    """Testes de extração de polígono."""

    @pytest.fixture
    def detector(self, tmp_path):
        model_path = tmp_path / "model.pt"
        model_path.write_text("fake model")
        with patch('zebtrack.core.aquarium_detector.YOLO'):
            return AquariumDetector(str(model_path), use_seg=True)

    def test_extract_polygon_from_seg(self, detector):
        """Test: Extração com segmentação válida."""
        # Mock de resultado YOLO com segmentação
        mock_result = Mock()
        mock_result.masks = Mock()
        mock_result.masks.xy = [np.array([[0, 0], [10, 0], [10, 10], [0, 10]])]
        mock_result.boxes = Mock()
        mock_result.boxes.conf = [0.95]

        polygon = detector._extract_polygon_from_detection([mock_result], use_seg=True)

        assert polygon is not None
        assert polygon.shape == (4, 2)

    def test_extract_polygon_from_bbox(self, detector):
        """Test: Extração com bounding box apenas."""
        # Mock de resultado YOLO com bbox
        mock_result = Mock()
        mock_result.masks = None
        mock_result.boxes = Mock()
        mock_result.boxes.xyxy = [np.array([0, 0, 10, 10])]
        mock_result.boxes.conf = [0.90]

        polygon = detector._extract_polygon_from_detection([mock_result], use_seg=False)

        assert polygon is not None
        assert polygon.shape == (4, 2)  # Bbox convertido em 4 pontos

    def test_extract_polygon_empty_results(self, detector):
        """Test: Resultado vazio/None."""
        polygon = detector._extract_polygon_from_detection(None, use_seg=True)

        assert polygon is None

    def test_extract_polygon_low_confidence(self, detector):
        """Test: Filtro de confiança baixa."""
        mock_result = Mock()
        mock_result.masks = Mock()
        mock_result.masks.xy = [np.array([[0, 0], [10, 0], [10, 10], [0, 10]])]
        mock_result.boxes = Mock()
        mock_result.boxes.conf = [0.3]  # Confiança baixa

        # Assumindo threshold de 0.5
        polygon = detector._extract_polygon_from_detection([mock_result], use_seg=True)

        # Deve retornar None ou primeira detecção (verificar implementação)
        # Ajustar assertion conforme comportamento real
        assert polygon is not None or polygon is None


class TestAquariumDetectorDetect:
    """Testes de detecção em frame único."""

    @pytest.fixture
    def detector(self, tmp_path):
        model_path = tmp_path / "model.pt"
        model_path.write_text("fake model")
        with patch('zebtrack.core.aquarium_detector.YOLO'):
            return AquariumDetector(str(model_path), use_seg=False)

    def test_detect_valid_frame(self, detector):
        """Test: Detecção com frame válido."""
        frame = np.zeros((480, 640, 3), dtype=np.uint8)

        with patch.object(detector.model, 'predict') as mock_predict:
            mock_result = Mock()
            mock_result.boxes = Mock()
            mock_result.boxes.xyxy = [np.array([0, 0, 100, 100])]
            mock_result.boxes.conf = [0.95]
            mock_predict.return_value = [mock_result]

            with patch.object(detector, '_extract_polygon_from_detection') as mock_extract:
                mock_extract.return_value = np.array([[0, 0], [100, 0], [100, 100], [0, 100]])

                polygon = detector.detect(frame, mode='det')

                assert polygon is not None
                assert polygon.shape == (4, 2)
                mock_predict.assert_called_once()

    def test_detect_mode_switching(self, detector):
        """Test: Switching entre modo seg e det."""
        frame = np.zeros((480, 640, 3), dtype=np.uint8)

        # Test modo det
        with patch.object(detector.model, 'predict') as mock_predict:
            mock_predict.return_value = [Mock()]
            with patch.object(detector, '_extract_polygon_from_detection') as mock_extract:
                detector.detect(frame, mode='det')
                mock_extract.assert_called_with(mock_predict.return_value, use_seg=False)

        # Test modo seg
        with patch.object(detector.model, 'predict') as mock_predict:
            mock_predict.return_value = [Mock()]
            with patch.object(detector, '_extract_polygon_from_detection') as mock_extract:
                detector.detect(frame, mode='seg')
                mock_extract.assert_called_with(mock_predict.return_value, use_seg=True)

    def test_detect_invalid_frame(self, detector):
        """Test: Error handling com frame inválido."""
        invalid_frame = None

        with pytest.raises((AttributeError, TypeError)):
            detector.detect(invalid_frame, mode='det')


class TestAquariumDetectorVideoDetection:
    """Testes de detecção em vídeo."""

    @pytest.fixture
    def detector(self, tmp_path):
        model_path = tmp_path / "model.pt"
        model_path.write_text("fake model")
        with patch('zebtrack.core.aquarium_detector.YOLO'):
            return AquariumDetector(str(model_path), use_seg=False)

    def test_detect_from_video_valid(self, detector, tmp_path):
        """Test: Detecção em vídeo válido."""
        video_path = tmp_path / "test.mp4"
        video_path.write_text("fake video")

        with patch('cv2.VideoCapture') as mock_cap:
            mock_cap_instance = Mock()
            mock_cap.return_value = mock_cap_instance
            mock_cap_instance.isOpened.return_value = True
            mock_cap_instance.read.side_effect = [
                (True, np.zeros((480, 640, 3), dtype=np.uint8)),
                (True, np.zeros((480, 640, 3), dtype=np.uint8)),
                (False, None)
            ]

            with patch.object(detector, 'detect') as mock_detect:
                mock_detect.return_value = np.array([[0, 0], [100, 0], [100, 100], [0, 100]])

                detections = detector.detect_from_video(str(video_path), mode='det')

                assert len(detections) == 2
                assert mock_detect.call_count == 2

    def test_detect_from_video_missing_file(self, detector):
        """Test: Error handling quando vídeo não existe."""
        with pytest.raises(FileNotFoundError):
            detector.detect_from_video("/path/to/nonexistent.mp4", mode='det')

    def test_detect_from_video_corrupted(self, detector, tmp_path):
        """Test: Error handling com vídeo corrompido."""
        video_path = tmp_path / "corrupt.mp4"
        video_path.write_text("not a video")

        with patch('cv2.VideoCapture') as mock_cap:
            mock_cap_instance = Mock()
            mock_cap.return_value = mock_cap_instance
            mock_cap_instance.isOpened.return_value = False

            with pytest.raises(RuntimeError):
                detector.detect_from_video(str(video_path), mode='det')


class TestAquariumDetectorStabilization:
    """Testes de estabilização temporal."""

    @pytest.fixture
    def detector(self, tmp_path):
        model_path = tmp_path / "model.pt"
        model_path.write_text("fake model")
        with patch('zebtrack.core.aquarium_detector.YOLO'):
            return AquariumDetector(str(model_path), use_seg=False)

    def test_stabilize_consistent_detections(self, detector):
        """Test: Estabilização com detecções consistentes."""
        detections = [
            np.array([[0, 0], [100, 0], [100, 100], [0, 100]]),
            np.array([[1, 1], [101, 1], [101, 101], [1, 101]]),
            np.array([[0, 0], [100, 0], [100, 100], [0, 100]]),
        ]

        stabilized = detector.stabilize_aquarium_region(detections)

        assert stabilized is not None
        assert stabilized.shape == (4, 2)

    def test_stabilize_with_outlier(self, detector):
        """Test: Outlier detection."""
        detections = [
            np.array([[0, 0], [100, 0], [100, 100], [0, 100]]),
            np.array([[1, 1], [101, 1], [101, 101], [1, 101]]),
            np.array([[500, 500], [600, 500], [600, 600], [500, 600]]),  # Outlier
            np.array([[0, 0], [100, 0], [100, 100], [0, 100]]),
        ]

        stabilized = detector.stabilize_aquarium_region(detections)

        # Stabilized deve ignorar outlier
        assert stabilized is not None
        # Verificar que resultado está próximo de (0,0) - (100,100)
        assert np.mean(stabilized) < 200

    def test_stabilize_empty_list(self, detector):
        """Test: Boundary condition com lista vazia."""
        stabilized = detector.stabilize_aquarium_region([])

        assert stabilized is None

    def test_stabilize_single_detection(self, detector):
        """Test: Boundary condition com detecção única."""
        detections = [np.array([[0, 0], [100, 0], [100, 100], [0, 100]])]

        stabilized = detector.stabilize_aquarium_region(detections)

        assert stabilized is not None
        np.testing.assert_array_equal(stabilized, detections[0])
```

## Implementação Passo-a-Passo

1. **Ler módulo a testar**:
   ```python
   # Ler e entender implementação de AquariumDetector
   ```

2. **Criar arquivo de teste**:
   - Criar `tests/test_aquarium_detector.py`
   - Adicionar imports necessários

3. **Implementar classes de teste** (na ordem):
   - TestAquariumDetectorInit
   - TestAquariumDetectorIoU
   - TestAquariumDetectorExtraction
   - TestAquariumDetectorDetect
   - TestAquariumDetectorVideoDetection
   - TestAquariumDetectorStabilization

4. **Rodar testes iterativamente**:
   ```bash
   poetry run pytest tests/test_aquarium_detector.py -v
   ```

5. **Verificar cobertura**:
   ```bash
   poetry run pytest tests/test_aquarium_detector.py --cov=src/zebtrack/core/aquarium_detector --cov-report=term-missing
   # Meta: >90%
   ```

6. **Ajustar testes** conforme comportamento real do código

## Validação

```bash
# Testes do módulo
poetry run pytest tests/test_aquarium_detector.py -v

# Cobertura
poetry run pytest tests/test_aquarium_detector.py --cov=src/zebtrack/core/aquarium_detector --cov-report=term-missing

# Suite completa (garantir sem regressão)
poetry run pytest -q
```

## Commit e Push

```bash
git add tests/test_aquarium_detector.py

git commit -m "test: adicionar cobertura completa para AquariumDetector

- 6 classes de teste, 20+ métodos
- Cobertura: 0% → 90%+
- Testes de inicialização, IoU, extração, detecção, vídeo, estabilização
- Error handling e edge cases cobertos

Refs: TEST-AQUARIUM-001"

git push -u origin claude/fix-post-refactor-bugs-011CUpYC3FjTK9gyrCusQND3
```

---

# [TEMPLATE PARA OUTRAS TASKS]

Para as outras tasks (2.1, 2.3, 2.4, 2.5, 3.2, 3.3, etc.), o usuário pode usar a estrutura similar:

- Copiar template acima
- Ajustar "Objetivo da Task"
- Ajustar "Arquivos a Criar/Modificar"
- Ajustar "Implementação Passo-a-Passo"
- Manter seções de Validação e Commit

---

## ✅ CHECKLIST DE USO

Para cada nova conversa:

1. [ ] Copiar contexto da task desejada
2. [ ] Verificar dependências completadas
3. [ ] Colar na nova conversa Claude Code
4. [ ] Aguardar execução completa
5. [ ] Verificar commit e push
6. [ ] Atualizar EXECUTION_PLAN.md com status
7. [ ] Notificar time/outras conversas se necessário

---

**Última Atualização**: 2025-11-05
**Documento Base**: EXECUTION_PLAN.md
