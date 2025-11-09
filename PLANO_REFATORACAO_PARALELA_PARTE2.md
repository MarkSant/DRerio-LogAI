# Plano de Refatoração Paralela - ZebTrack-AI

## Parte 2: Fases 2-4

---

## 📋 ÍNDICE

### Parte 2 (Este Arquivo)

- [FASE 2: Extração de God Objects](#fase-2-extração-de-god-objects)
- [FASE 3: Testes e Qualidade](#fase-3-testes-e-qualidade)
- [FASE 4: Performance e Documentação](#fase-4-performance-e-documentação)

### Parte 1 (Ver PLANO_REFATORACAO_PARALELA_PARTE1.md)

- Visão Geral
- Estratégia de Branches
- FASE 1: Correções Críticas

---

## 🏗️ FASE 2: EXTRAÇÃO DE GOD OBJECTS

**Branch Base**: `refactor/phase-2-god-objects` (criar APÓS Phase 1 mergeada em main)

**Objetivo**: Extrair lógica de `MainViewModel` para coordenadores especializados, reduzindo de 5,383 para <2,000 linhas.

**Duração**: 2 semanas

---

### TAREFA P2-T1: Extract HardwareCoordinator

**Branch**: `task/p2-t1-hardware-coordinator`

**Dependências**: Nenhuma (pode ser paralela com P2-T2)

**Estimativa**: 4 dias

**Agente**: Agent-6

#### Resumo

Extrair toda lógica de hardware (camera, Arduino) de `MainViewModel` para novo `HardwareCoordinator`.

**Redução esperada**: ~800 linhas do MainViewModel

#### Arquivos Envolvidos

**Criar**:

- `src/zebtrack/core/hardware_coordinator.py` (~400 linhas)
- `tests/core/test_hardware_coordinator.py` (~300 linhas)

**Modificar**:

- `src/zebtrack/core/main_view_model.py` (remover ~800 linhas)
- `src/zebtrack/__main__.py` (adicionar HardwareCoordinator ao DI)
- `docs/ARCHITECTURE.md` (atualizar diagrama)

#### Implementação

**Métodos a Extrair do MainViewModel**:

- `setup_camera()`
- `release_camera()`
- `setup_arduino()`
- `send_arduino_command()`
- `shutdown_arduino()`
- `run_hardware_diagnostic()`

**Estrutura do HardwareCoordinator**:

```python
# src/zebtrack/core/hardware_coordinator.py

from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from zebtrack.settings import Settings

import structlog
from zebtrack.io.camera import Camera
from zebtrack.io.arduino_manager import ArduinoManager
from zebtrack.exceptions import CameraConnectionError, ArduinoConnectionError

log = structlog.get_logger()


class HardwareCoordinator:
    """
    Coordinates camera and Arduino hardware setup and lifecycle.

    Extracted from MainViewModel to reduce god object complexity.
    """

    def __init__(
        self,
        settings_obj: Settings,
        state_manager: "StateManager",
        ui_coordinator: "UICoordinator",
    ):
        self.settings = settings_obj
        self.state_manager = state_manager
        self.ui_coordinator = ui_coordinator

        self.camera: Camera | None = None
        self.arduino_manager: ArduinoManager | None = None
        self._camera_initialized = False
        self._arduino_initialized = False

    # Camera Management
    def setup_camera(self) -> Camera:
        """Setup camera with configured settings."""
        if self._camera_initialized and self.camera:
            log.warning("hardware.camera.already_initialized")
            return self.camera

        try:
            log.info("hardware.camera.setup.start")
            self.camera = Camera(
                index=self.settings.camera.index,
                settings_obj=self.settings
            )
            self.camera.open()

            self._camera_initialized = True
            self.state_manager.update_hardware_state(camera_connected=True)

            log.info("hardware.camera.setup.success", index=self.settings.camera.index)
            return self.camera

        except Exception as e:
            log.error("hardware.camera.setup.failed", error=str(e), exc_info=True)
            self._camera_initialized = False
            raise CameraConnectionError(f"Camera setup failed: {e}") from e

    def release_camera(self):
        """Release camera resources gracefully."""
        if not self.camera:
            return

        try:
            log.info("hardware.camera.release.start")
            self.camera.release()
            self._camera_initialized = False
            self.state_manager.update_hardware_state(camera_connected=False)
            log.info("hardware.camera.release.success")
        except Exception as e:
            log.error("hardware.camera.release.failed", error=str(e))
        finally:
            self.camera = None

    # Arduino Management
    def setup_arduino(self, port: str | None = None):
        """Setup Arduino connection."""
        if self._arduino_initialized and self.arduino_manager:
            log.warning("hardware.arduino.already_initialized")
            return self.arduino_manager.arduino

        try:
            log.info("hardware.arduino.setup.start", port=port)
            self.arduino_manager = ArduinoManager(
                settings_obj=self.settings,
                state_manager=self.state_manager,
            )
            arduino = self.arduino_manager.connect(port=port)
            self._arduino_initialized = True
            self.state_manager.update_hardware_state(arduino_connected=True)
            log.info("hardware.arduino.setup.success")
            return arduino
        except Exception as e:
            log.error("hardware.arduino.setup.failed", error=str(e))
            self._arduino_initialized = False
            raise ArduinoConnectionError(f"Arduino setup failed: {e}") from e

    def send_arduino_command(self, command: str) -> str | None:
        """Send command to Arduino."""
        if not self.arduino_manager or not self._arduino_initialized:
            raise ArduinoConnectionError("Arduino not connected")
        return self.arduino_manager.send_command(command)

    def shutdown_arduino(self):
        """Shutdown Arduino connection."""
        if self.arduino_manager:
            try:
                self.arduino_manager.shutdown()
                log.info("hardware.arduino.shutdown.success")
            except Exception as e:
                log.warning("hardware.arduino.shutdown.failed", error=str(e))
            finally:
                self.arduino_manager = None
                self._arduino_initialized = False
                self.state_manager.update_hardware_state(arduino_connected=False)

    def run_hardware_diagnostic(self) -> dict:
        """Run comprehensive hardware diagnostic."""
        from zebtrack.utils.hardware_detection import (
            get_hardware_summary,
            recommend_backend,
        )
        log.info("hardware.diagnostic.start")
        results = {
            "summary": get_hardware_summary(),
            "recommended_backend": recommend_backend(),
            "camera_status": self._camera_initialized,
            "arduino_status": self._arduino_initialized,
        }
        log.info("hardware.diagnostic.complete", results=results)
        return results

    def shutdown_all(self):
        """Shutdown all hardware."""
        log.info("hardware.shutdown_all.start")
        self.release_camera()
        self.shutdown_arduino()
        log.info("hardware.shutdown_all.complete")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.shutdown_all()
        return False
```

**Testes**:

```python
# tests/core/test_hardware_coordinator.py

import pytest
from unittest.mock import Mock, patch
from zebtrack.core.hardware_coordinator import HardwareCoordinator
from zebtrack.exceptions import CameraConnectionError, ArduinoConnectionError


@pytest.fixture
def coordinator(mock_settings, mock_state_manager, mock_ui_coordinator):
    return HardwareCoordinator(
        settings_obj=mock_settings,
        state_manager=mock_state_manager,
        ui_coordinator=mock_ui_coordinator,
    )


def test_setup_camera_success(coordinator):
    """Test successful camera setup."""
    with patch('zebtrack.core.hardware_coordinator.Camera') as mock_camera:
        camera = coordinator.setup_camera()
        assert coordinator._camera_initialized
        mock_camera.assert_called_once()


def test_setup_camera_failure(coordinator):
    """Test camera setup failure."""
    with patch('zebtrack.core.hardware_coordinator.Camera', side_effect=Exception):
        with pytest.raises(CameraConnectionError):
            coordinator.setup_camera()
        assert not coordinator._camera_initialized


def test_release_camera(coordinator):
    """Test camera release."""
    coordinator.camera = Mock()
    coordinator._camera_initialized = True
    coordinator.release_camera()
    assert coordinator.camera is None
    assert not coordinator._camera_initialized


def test_setup_arduino_success(coordinator):
    """Test Arduino setup."""
    with patch('zebtrack.core.hardware_coordinator.ArduinoManager') as mock_mgr:
        coordinator.setup_arduino()
        assert coordinator._arduino_initialized


def test_send_arduino_command_not_connected(coordinator):
    """Test sending command when not connected."""
    with pytest.raises(ArduinoConnectionError):
        coordinator.send_arduino_command("TEST")


def test_context_manager(coordinator):
    """Test context manager cleanup."""
    with coordinator:
        coordinator.camera = Mock()
    assert coordinator.camera is None
```

**Atualizar MainViewModel**:

```python
# src/zebtrack/core/main_view_model.py

class MainViewModel:
    def __init__(
        self,
        # ... existing params
        hardware_coordinator: HardwareCoordinator,  # ADICIONAR
    ):
        # ... existing init
        self.hardware_coordinator = hardware_coordinator

    # REMOVER métodos:
    # - setup_camera() → delegar para hardware_coordinator.setup_camera()
    # - release_camera()
    # - setup_arduino()
    # - send_arduino_command()
    # - shutdown_arduino()
    # - run_hardware_diagnostic()

    # Se necessário manter interface pública, criar delegações:
    def setup_camera(self):
        """Delegate to HardwareCoordinator."""
        return self.hardware_coordinator.setup_camera()
```

**Atualizar Composition Root**:

```python
# src/zebtrack/__main__.py

from zebtrack.core.hardware_coordinator import HardwareCoordinator

# ... após state_manager, ui_coordinator

hardware_coordinator = HardwareCoordinator(
    settings_obj=settings_obj,
    state_manager=state_manager,
    ui_coordinator=ui_coordinator,
)

controller = MainViewModel(
    # ... existing params
    hardware_coordinator=hardware_coordinator,  # PASSAR
)
```

#### Validação

```bash
# Verificar redução de linhas
wc -l src/zebtrack/core/main_view_model.py
# Deve mostrar ~4500 linhas (redução de ~800)

# Executar testes
poetry run pytest tests/core/test_hardware_coordinator.py -v
poetry run pytest -q

# Linting
poetry run ruff check .
```

#### Critérios de Aceitação

- [ ] `HardwareCoordinator` criado com ~400 linhas
- [ ] 6 métodos de hardware extraídos de `MainViewModel`
- [ ] `MainViewModel` reduzido em ~800 linhas
- [ ] Dependency injection atualizado em `__main__.py`
- [ ] 20+ testes para `HardwareCoordinator`
- [ ] 100% dos testes passando
- [ ] Zero erros Ruff
- [ ] Documentação atualizada

---

### TAREFA P2-T2: Extract AnalysisCoordinator

**Branch**: `task/p2-t2-analysis-coordinator`

**Dependências**: Nenhuma (pode ser paralela com P2-T1)

**Estimativa**: 4 dias

**Agente**: Agent-7

#### Resumo

Extrair lógica de análise batch de `MainViewModel` para novo `AnalysisCoordinator`.

**Redução esperada**: ~900 linhas do MainViewModel

#### Arquivos Envolvidos

**Criar**:

- `src/zebtrack/core/analysis_coordinator.py` (~500 linhas)
- `tests/core/test_analysis_coordinator.py` (~350 linhas)

**Modificar**:

- `src/zebtrack/core/main_view_model.py` (remover ~900 linhas)
- `src/zebtrack/__main__.py` (adicionar AnalysisCoordinator)
- `docs/ARCHITECTURE.md`

#### Implementação

**Métodos a Extrair**:

- `run_batch_analysis()`
- `analyze_single_video()`
- `prepare_results_directory()`
- `build_metadata_context()`
- `cleanup_cancelled_results()`

**Estrutura do AnalysisCoordinator**:

```python
# src/zebtrack/core/analysis_coordinator.py

from pathlib import Path
from typing import Callable
import structlog
from zebtrack.analysis.analysis_service import AnalysisService
from zebtrack.exceptions import AnalysisError

log = structlog.get_logger()


class AnalysisCoordinator:
    """
    Coordinates batch video analysis workflows.

    Extracted from MainViewModel to reduce god object complexity.
    """

    def __init__(
        self,
        settings_obj: Settings,
        project_manager: ProjectManager,
        analysis_service: AnalysisService,
        state_manager: StateManager,
    ):
        self.settings = settings_obj
        self.project_manager = project_manager
        self.analysis_service = analysis_service
        self.state_manager = state_manager
        self._is_analyzing = False
        self._cancel_requested = False

    def run_batch_analysis(
        self,
        videos: list[str],
        on_progress: Callable[[float, str], None] | None = None,
        on_complete: Callable[[list[dict]], None] | None = None,
    ) -> list[dict]:
        """Run analysis on batch of videos."""
        if self._is_analyzing:
            raise RuntimeError("Analysis already in progress")

        log.info("analysis.batch.start", video_count=len(videos))
        self._is_analyzing = True
        self._cancel_requested = False
        results = []

        try:
            for idx, video_path in enumerate(videos):
                if self._cancel_requested:
                    log.warning("analysis.batch.cancelled", completed=idx)
                    break

                progress = (idx + 1) / len(videos)
                if on_progress:
                    on_progress(progress, f"Analyzing {idx+1}/{len(videos)}")

                try:
                    video_results = self._analyze_single_video(video_path)
                    results.append(video_results)
                except Exception as e:
                    log.error("analysis.video.failed", video=video_path, error=str(e))
                    raise

            log.info("analysis.batch.complete", successful=len(results))
            if on_complete:
                on_complete(results)
            return results
        finally:
            self._is_analyzing = False

    def _analyze_single_video(self, video_path: str) -> dict:
        """Analyze single video."""
        project_data = self.project_manager.get_project_data()
        return self.analysis_service.run_full_analysis(
            video_path=video_path,
            project_data=project_data,
            settings_obj=self.settings,
        )

    def cancel_analysis(self):
        """Request cancellation."""
        if self._is_analyzing:
            log.info("analysis.cancel.requested")
            self._cancel_requested = True

    def prepare_results_directory(self, video_path: str) -> Path:
        """Prepare results directory."""
        video_name = Path(video_path).stem
        results_dir = Path(video_path).parent / f"{video_name}_results"
        results_dir.mkdir(parents=True, exist_ok=True)
        return results_dir

    @property
    def is_analyzing(self) -> bool:
        return self._is_analyzing
```

**Testes similares ao P2-T1** (ver AGENT_ORCHESTRATION_GUIDE.md para detalhes completos)

#### Critérios de Aceitação

- [ ] `AnalysisCoordinator` criado com ~500 linhas
- [ ] Métodos de análise extraídos de `MainViewModel`
- [ ] `MainViewModel` reduzido em ~900 linhas
- [ ] DI atualizado
- [ ] 15+ testes
- [ ] 100% testes passando
- [ ] Zero erros Ruff

---

### TAREFA P2-T3: Refactor MainViewModel

**Branch**: `task/p2-t3-mainviewmodel-refactor`

**Dependências**: P2-T1 E P2-T2 (deve esperar ambas serem mergeadas)

**Estimativa**: 3 dias

**Agente**: Agent-8

#### Resumo

Integrar os coordinators extraídos e finalizar refatoração do MainViewModel para <2,000 linhas.

#### Objetivos

1. Verificar que ambos coordinators estão integrados
2. Remover quaisquer duplicações restantes
3. Reduzir dependências do construtor: 11 → 7
4. Garantir que MainViewModel < 2,000 linhas

#### Implementação

```python
# src/zebtrack/core/main_view_model.py

class MainViewModel:
    """
    Main view model - refactored to delegate hardware and analysis concerns.

    Now focuses on:
    - UI state coordination
    - Wizard workflow
    - Project lifecycle
    """

    def __init__(
        self,
        settings_obj: Settings,
        state_manager: StateManager,
        ui_coordinator: UICoordinator,
        project_manager: ProjectManager,
        hardware_coordinator: HardwareCoordinator,  # Delegação
        analysis_coordinator: AnalysisCoordinator,  # Delegação
        event_bus: EventBus | None = None,
    ):
        # 7 dependências (reduzido de 11)
        self.settings = settings_obj
        self.state_manager = state_manager
        self.ui_coordinator = ui_coordinator
        self.project_manager = project_manager
        self.hardware = hardware_coordinator
        self.analysis = analysis_coordinator
        self.event_bus = event_bus

    # Delegações para hardware
    def setup_camera(self):
        return self.hardware.setup_camera()

    def send_arduino_command(self, cmd: str):
        return self.hardware.send_arduino_command(cmd)

    # Delegações para análise
    def run_batch_analysis(self, videos: list[str], **kwargs):
        return self.analysis.run_batch_analysis(videos, **kwargs)

    # ... métodos de UI e wizard permanecem aqui
```

#### Validação

```bash
# Verificar tamanho final
wc -l src/zebtrack/core/main_view_model.py
# DEVE MOSTRAR < 2000 linhas

# Contar dependências no construtor
grep -A 20 "def __init__" src/zebtrack/core/main_view_model.py | grep -c ":"
# DEVE MOSTRAR ≤ 7

# Testes
poetry run pytest -q
poetry run pytest -m gui -n0
```

#### Critérios de Aceitação

- [ ] `MainViewModel` < 2,000 linhas (de 5,383)
- [ ] Redução: 11 → 7 dependências no construtor
- [ ] Todos os métodos delegam para coordinators apropriados
- [ ] 100% dos testes passando
- [ ] Zero erros Ruff
- [ ] Docs atualizadas com nova arquitetura

---

## 🧪 FASE 3: TESTES E QUALIDADE

**Branch Base**: `refactor/phase-3-testing-quality` (APÓS Phase 2 mergeada)

**Objetivo**: Aumentar cobertura de testes, resolver isolamento, melhorar qualidade do código.

**Duração**: 2 semanas

---

### TAREFA P3-T1: Fix Test Isolation Issues

**Branch**: `task/p3-t1-test-isolation`

**Agente**: Agent-9

**Estimativa**: 2 dias

**Independente**: Pode rodar em paralelo com P3-T2, P3-T3, P3-T4

#### Resumo

Isolar 11 testes de UI componentes que causam problemas na suite completa.

#### Implementação

```python
# Adicionar markers
@pytest.mark.skipif(
    not os.environ.get("RUN_UI_TESTS"),
    reason="UI component tests require special isolation"
)
def test_ui_component():
    ...
```

#### Critérios de Aceitação

- [ ] 11 testes isolados ou marcados
- [ ] Suite completa passa sem problemas
- [ ] Documentação em `docs/TESTING.md`

---

### TAREFA P3-T2: Increase Test Coverage to 80%

**Branch**: `task/p3-t2-coverage-increase`

**Agente**: Agent-10

**Estimativa**: 4 dias

**Independente**: Pode rodar em paralelo com P3-T1, P3-T3, P3-T4

#### Resumo

Aumentar cobertura de testes de 70% para 80%.

#### Implementação

1. Gerar relatório de cobertura: `poetry run pytest --cov=zebtrack --cov-report=html`
2. Identificar gaps em `htmlcov/index.html`
3. Adicionar testes para:
   - Edge cases
   - Error paths
   - Branches não cobertas

#### Critérios de Aceitação

- [ ] Coverage ≥80%
- [ ] `pyproject.toml` atualizado: `--cov-fail-under=80`
- [ ] Testes para edge cases adicionados
- [ ] CI enforça 80% coverage

---

### TAREFA P3-T3: Add Integration Tests

**Branch**: `task/p3-t3-integration-tests`

**Agente**: Agent-11

**Estimativa**: 3 dias

**Independente**: Pode rodar em paralelo com P3-T1, P3-T2, P3-T4

#### Resumo

Adicionar 10+ testes de integração end-to-end.

#### Implementação

```python
# tests/integration/test_wizard_workflow.py

def test_complete_wizard_workflow(tmp_path):
    """Test wizard from start to finish."""
    # Setup
    # Run wizard
    # Verify project created
    # Verify all steps completed

# tests/integration/test_video_processing.py

def test_complete_video_processing_pipeline(sample_video):
    """Test full video processing."""
    # Load video
    # Run detection
    # Record results
    # Verify outputs
```

#### Critérios de Aceitação

- [ ] 10+ testes de integração
- [ ] Wizard workflows completos testados
- [ ] Video processing pipelines testados
- [ ] Todos passam no CI

---

### TAREFA P3-T4: Code Quality Improvements

**Branch**: `task/p3-t4-code-quality`

**Agente**: Agent-12

**Estimativa**: 3 dias

**Independente**: Pode rodar em paralelo com P3-T1, P3-T2, P3-T3

#### Resumo

Extrair constantes, padronizar logging, otimizar código.

#### Implementação

```python
# Antes
if width == 640 and height == 480:
    ...

# Depois
class VideoConfig:
    DEFAULT_WIDTH = 640
    DEFAULT_HEIGHT = 480

if width == VideoConfig.DEFAULT_WIDTH:
    ...
```

#### Critérios de Aceitação

- [ ] 15+ valores hardcoded extraídos para constantes
- [ ] Structured logging consistente
- [ ] Color maps como class constants
- [ ] Tree clearing otimizado

---

## 🚀 FASE 4: PERFORMANCE E DOCUMENTAÇÃO

**Branch Base**: `refactor/phase-4-performance-docs` (APÓS Phase 3 mergeada)

**Objetivo**: Otimizar performance, adicionar DevOps tooling, curar documentação.

**Duração**: 1 semana

---

### TAREFA P4-T1: Performance Optimization

**Branch**: `task/p4-t1-performance-optimization`

**Agente**: Agent-13

**Estimativa**: 2 dias

#### Resumo

Profiling e otimização de hot paths.

#### Implementação

```bash
# Profiling
poetry run python -m cProfile -o profile.stats -m zebtrack

# Análise
poetry run python -c "import pstats; p = pstats.Stats('profile.stats'); p.sort_stats('cumulative').print_stats(20)"
```

#### Critérios de Aceitação

- [ ] Profiling realizado
- [ ] Hot paths otimizados
- [ ] Benchmarks documentados

---

### TAREFA P4-T2: DevOps Tooling

**Branch**: `task/p4-t2-devops-tooling`

**Agente**: Agent-14

**Estimativa**: 1 dia

#### Resumo

Configurar pre-commit hooks.

#### Implementação

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.1.0
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format
```

#### Critérios de Aceitação

- [ ] Pre-commit hooks configurados
- [ ] Documentação em CONTRIBUTING.md

---

### TAREFA P4-T3: Documentation Curation

**Branch**: `task/p4-t3-documentation-curation`

**Agente**: Agent-15

**Estimativa**: 3 dias

**IMPORTANTE**: Deve ser mergeada POR ÚLTIMO (documenta todas as mudanças)

#### Resumo

Curadoria completa de toda documentação do repositório.

#### Objetivos

1. Auditar todos os `.md` no repo
2. Consolidar informações duplicadas
3. Arquivar documentos obsoletos
4. Criar índice unificado
5. Atualizar README principal

#### Implementação

```bash
# Auditoria
find . -name "*.md" | grep -v node_modules > all_docs.txt

# Criar estrutura
mkdir -p docs/archive/refactoring_history
mkdir -p docs/archive/planning

# Mover obsoletos
mv GOD_OBJECTS*.md docs/archive/refactoring_history/
mv TASK_CONTEXTS*.md docs/archive/planning/
```

**Estrutura Alvo**:

```text
docs/
├── README.md (índice principal)
├── ARCHITECTURE.md
├── USER_GUIDE.md (consolidado)
├── DEVELOPER_GUIDE.md (consolidado)
├── TESTING_GUIDE.md (consolidado)
├── TROUBLESHOOTING.md
└── archive/
    ├── refactoring_history/
    └── planning/
```

#### Critérios de Aceitação

- [ ] Todos `.md` auditados
- [ ] Docs obsoletos em `docs/archive/`
- [ ] Duplicações consolidadas
- [ ] `docs/README.md` criado
- [ ] README.md principal atualizado
- [ ] Links validados
- [ ] Zero erros de linting MD
- [ ] Zero TODOs em docs principais

---

## 📊 MÉTRICAS FINAIS

| Métrica | Antes | Meta | Comando |
|---------|-------|------|---------|
| MainViewModel | 5,383 | <2,000 | `wc -l main_view_model.py` |
| Deps MainViewModel | 11 | ≤7 | Contar params __init__ |
| Coverage | 70% | 80% | `pytest --cov` |
| Custom Exceptions | 8 | 15+ | Contar em exceptions.py |
| Singleton Imports | 2 | 0 | `grep "from zebtrack import settings"` |
| Docs Obsoletos | ~50 | <10 | Contar .md fora archive |

---

**FIM DO PLANO COMPLETO**

Ver `PLANO_REFATORACAO_PARALELA_PARTE1.md` para Fase 1 detalhada e `AGENT_ORCHESTRATION_GUIDE.md` para instruções de execução.
