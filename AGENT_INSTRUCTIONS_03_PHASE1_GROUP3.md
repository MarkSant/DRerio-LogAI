# Agent Instructions - Phase 1, Group 3 (APÓS P1-T5)

**⚠️ AGUARDAR: Este grupo SÓ pode iniciar DEPOIS que Agent-5 (P1-T5) concluir**

## 📋 Visão Geral
- **Grupo de Execução**: Phase 1, Group 3
- **Número de Agentes**: 2 (podem trabalhar simultaneamente)
- **Dependências**: ✋ **BLOQUEADO por P1-T5** (Custom Exception Hierarchy)
- **Bloqueia**: Ninguém
- **Branch**: `refactor/phase-1-critical-fixes`

## ⚠️ PRÉ-REQUISITO OBRIGATÓRIO

**ANTES de iniciar, verifique:**

```bash
# 1. Verifique se P1-T5 foi concluído
git log --oneline | grep "P1-T5"

# 2. Verifique se exceptions.py existe
test -f src/zebtrack/core/exceptions.py && echo "✅ P1-T5 concluído" || echo "❌ AGUARDE P1-T5"

# 3. Pull das mudanças
git pull origin refactor/phase-1-critical-fixes
```

**Se exceptions.py NÃO existe**: ❌ **PARE E AGUARDE Agent-5 concluir**

---

## 🤖 AGENT-1: Exception Handling Modernization (P1-T1)

### 📌 Contexto
Você é o **Agent-1** responsável por substituir blocos `except Exception` genéricos por exceções customizadas específicas em 30+ arquivos.

### 🎯 Objetivo
Substituir exceções genéricas por exceções customizadas de `zebtrack.core.exceptions`, melhorando granularidade e debugging.

### 📂 Acesso ao Repositório
```bash
# Clone o repositório (se ainda não tiver)
git clone https://github.com/MarkSant/ZebTrack-AI.git
cd ZebTrack-AI

# Checkout da branch
git checkout refactor/phase-1-critical-fixes

# IMPORTANTE: Pull para pegar P1-T5
git pull origin refactor/phase-1-critical-fixes

# Verifique que exceptions.py existe
cat src/zebtrack/core/exceptions.py | head -20

# Configure o ambiente
poetry install
poetry shell
```

### 📖 Documentação Detalhada

1. **PLANO_REFATORACAO_PARALELA_PARTE1.md**
   - Seção: "P1-T1: Exception Handling Modernization (Agent-1)"
   - Linhas: ~100-250

2. **src/zebtrack/core/exceptions.py**
   - Hierarquia completa de exceções (criada por Agent-5)

3. **AGENT_ORCHESTRATION_GUIDE.md**
   - Seção: "Agent-1: Exception Handling (P1-T1)"

### 🛠️ Implementação Passo a Passo

#### Passo 1: Identificar Arquivos com Exception Genérica
```bash
# Liste todos os arquivos com except Exception
grep -r "except Exception" src/ --include="*.py" | cut -d: -f1 | sort -u

# Principais arquivos (ordem de prioridade):
# 1. src/zebtrack/io/live_camera.py
# 2. src/zebtrack/io/video_source.py
# 3. src/zebtrack/core/detector_service.py
# 4. src/zebtrack/core/project_manager.py
# 5. src/zebtrack/analysis/analysis_service.py
```

#### Passo 2: Refatorar LiveCameraService
Edite `src/zebtrack/io/live_camera.py`:

**ANTES:**
```python
try:
    self.cap = cv2.VideoCapture(self.camera_id, self.backend)
    if not self.cap.isOpened():
        raise RuntimeError(f"Camera {self.camera_id} not available")
except Exception as e:
    logger.error("camera.init.failed", error=str(e))
    raise
```

**DEPOIS:**
```python
from zebtrack.core.exceptions import CameraNotFoundError, CameraAccessError

try:
    self.cap = cv2.VideoCapture(self.camera_id, self.backend)
    if not self.cap.isOpened():
        raise CameraNotFoundError(
            f"Camera {self.camera_id} not available",
            {"camera_id": self.camera_id, "backend": self.backend}
        )
except PermissionError as e:
    logger.error("camera.access.denied", camera_id=self.camera_id, error=str(e))
    raise CameraAccessError(
        f"Permission denied for camera {self.camera_id}",
        {"camera_id": self.camera_id, "error": str(e)}
    ) from e
except OSError as e:
    logger.error("camera.not.found", camera_id=self.camera_id, error=str(e))
    raise CameraNotFoundError(
        f"Camera {self.camera_id} not found",
        {"camera_id": self.camera_id, "error": str(e)}
    ) from e
```

#### Passo 3: Refatorar VideoSource
Edite `src/zebtrack/io/video_source.py`:

**ANTES:**
```python
try:
    cap = cv2.VideoCapture(self.video_path)
except Exception as e:
    logger.error("video.open.failed", error=str(e))
    raise
```

**DEPOIS:**
```python
from zebtrack.core.exceptions import VideoNotFoundError, VideoReadError
from pathlib import Path

try:
    if not Path(self.video_path).exists():
        raise VideoNotFoundError(
            f"Video file not found: {self.video_path}",
            {"path": self.video_path}
        )

    cap = cv2.VideoCapture(self.video_path)
    if not cap.isOpened():
        raise VideoReadError(
            f"Cannot read video file: {self.video_path}",
            {"path": self.video_path}
        )
except FileNotFoundError as e:
    raise VideoNotFoundError(
        f"Video file not found: {self.video_path}",
        {"path": self.video_path, "error": str(e)}
    ) from e
except OSError as e:
    raise VideoReadError(
        f"Error reading video: {self.video_path}",
        {"path": self.video_path, "error": str(e)}
    ) from e
```

#### Passo 4: Refatorar ProjectManager
Edite `src/zebtrack/core/project_manager.py`:

**ANTES:**
```python
try:
    with open(project_path, 'r') as f:
        data = json.load(f)
except Exception as e:
    logger.error("project.load.failed", error=str(e))
    raise
```

**DEPOIS:**
```python
from zebtrack.core.exceptions import (
    ProjectNotFoundError,
    ProjectLoadError,
    ProjectSaveError
)

try:
    if not Path(project_path).exists():
        raise ProjectNotFoundError(
            f"Project file not found: {project_path}",
            {"path": project_path}
        )

    with open(project_path, 'r') as f:
        data = json.load(f)
except FileNotFoundError as e:
    raise ProjectNotFoundError(
        f"Project not found: {project_path}",
        {"path": project_path}
    ) from e
except json.JSONDecodeError as e:
    raise ProjectLoadError(
        f"Invalid project file: {project_path}",
        {"path": project_path, "error": str(e)}
    ) from e
except OSError as e:
    raise ProjectLoadError(
        f"Cannot read project: {project_path}",
        {"path": project_path, "error": str(e)}
    ) from e
```

#### Passo 5: Criar Testes
Crie/atualize `tests/test_exception_handling.py`:

```python
"""Test exception handling with custom exceptions."""

import pytest
from pathlib import Path
from zebtrack.core.exceptions import (
    CameraNotFoundError,
    CameraAccessError,
    VideoNotFoundError,
    VideoReadError,
    ProjectNotFoundError,
    ProjectLoadError,
)
from zebtrack.io.live_camera import LiveCameraService
from zebtrack.io.video_source import VideoSource
from zebtrack.core.project_manager import ProjectManager


class TestCameraExceptions:
    """Test camera-specific exception handling."""

    def test_camera_not_found_raises_specific_exception(self, settings_obj):
        """Invalid camera ID raises CameraNotFoundError."""
        with pytest.raises(CameraNotFoundError) as exc_info:
            service = LiveCameraService(settings_obj, camera_id=9999)
            service.start()

        assert "9999" in str(exc_info.value)
        assert exc_info.value.details.get("camera_id") == 9999


class TestVideoExceptions:
    """Test video-specific exception handling."""

    def test_video_not_found_raises_specific_exception(self):
        """Non-existent video raises VideoNotFoundError."""
        with pytest.raises(VideoNotFoundError) as exc_info:
            source = VideoSource("nonexistent.mp4")

        assert "nonexistent.mp4" in str(exc_info.value)
        assert "nonexistent.mp4" in exc_info.value.details.get("path", "")


class TestProjectExceptions:
    """Test project-specific exception handling."""

    def test_project_not_found_raises_specific_exception(self):
        """Non-existent project raises ProjectNotFoundError."""
        manager = ProjectManager()

        with pytest.raises(ProjectNotFoundError) as exc_info:
            manager.load_project("nonexistent.json")

        assert "nonexistent.json" in str(exc_info.value)
```

#### Passo 6: Validar Implementação
```bash
# Execute testes de exceções
poetry run pytest tests/test_exception_handling.py -v

# Execute suite completa
poetry run pytest -q

# Verifique coverage de exception handling
poetry run pytest --cov=zebtrack.io.live_camera --cov=zebtrack.io.video_source --cov=zebtrack.core.project_manager
```

#### Passo 7: Verificar Linting
```bash
# Check style
poetry run ruff check src/zebtrack/io/ src/zebtrack/core/project_manager.py

# Format
poetry run ruff format src/zebtrack/io/ src/zebtrack/core/project_manager.py
```

#### Passo 8: Commit e Push
```bash
# Adicione arquivos
git add src/zebtrack/io/live_camera.py src/zebtrack/io/video_source.py src/zebtrack/core/project_manager.py tests/test_exception_handling.py

# Commit
git commit -m "refactor(exceptions): Replace generic Exception with custom exceptions (P1-T1)

- Replace except Exception in LiveCameraService, VideoSource, ProjectManager
- Use CameraNotFoundError, CameraAccessError, VideoNotFoundError, etc.
- Add structured error details (camera_id, path, error context)
- Improve error granularity for better debugging
- Add comprehensive exception handling tests

Depends: P1-T5
Task: P1-T1
Agent: Agent-1"

# Push
git push origin refactor/phase-1-critical-fixes
```

### ✅ Critérios de Sucesso
- [ ] `exceptions.py` existe e foi importado (de P1-T5)
- [ ] Mínimo 3 arquivos refatorados (live_camera, video_source, project_manager)
- [ ] Todas as exceções incluem `details` dict
- [ ] Testes de exceções criados (mínimo 5 testes)
- [ ] Todos os testes passando
- [ ] Zero erros Ruff
- [ ] Commit e push concluídos

### ⏱️ Estimativa
**Total**: ~120 minutos

---

## 🤖 AGENT-2: Resource Management (P1-T2)

### 📌 Contexto
Você é o **Agent-2** responsável por adicionar context managers e garantir cleanup adequado de recursos (câmeras, arquivos, threads).

### 🎯 Objetivo
Implementar `__enter__`/`__exit__` em classes que gerenciam recursos, garantindo cleanup automático mesmo em caso de exceções.

### 📂 Acesso ao Repositório
```bash
# Clone/checkout (se ainda não tiver)
git clone https://github.com/MarkSant/ZebTrack-AI.git
cd ZebTrack-AI
git checkout refactor/phase-1-critical-fixes

# IMPORTANTE: Pull para pegar P1-T5
git pull origin refactor/phase-1-critical-fixes

# Configure ambiente
poetry install
poetry shell
```

### 📖 Documentação Detalhada

1. **PLANO_REFATORACAO_PARALELA_PARTE1.md**
   - Seção: "P1-T2: Resource Management (Agent-2)"
   - Linhas: ~250-400

2. **AGENT_ORCHESTRATION_GUIDE.md**
   - Seção: "Agent-2: Resource Management (P1-T2)"

### 🛠️ Implementação Passo a Passo

#### Passo 1: Adicionar Context Manager ao LiveCameraService
Edite `src/zebtrack/io/live_camera.py`:

**ADICIONE no início da classe:**
```python
from types import TracebackType
from zebtrack.core.exceptions import CameraError

class LiveCameraService:
    """
    Service for managing live camera capture.

    Supports context manager protocol for automatic resource cleanup.

    Example:
        with LiveCameraService(settings_obj, camera_id=0) as camera:
            frame = camera.read_frame()
    """

    def __enter__(self) -> 'LiveCameraService':
        """Enter context manager - start camera."""
        self.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None
    ) -> bool:
        """
        Exit context manager - cleanup camera resources.

        Args:
            exc_type: Exception type if raised
            exc_val: Exception value if raised
            exc_tb: Exception traceback if raised

        Returns:
            False to propagate exceptions
        """
        try:
            self.stop()
        except Exception as e:
            logger.warning("camera.cleanup.failed", error=str(e))
        return False  # Don't suppress exceptions

    def stop(self) -> None:
        """Stop camera and release resources."""
        if hasattr(self, 'cap') and self.cap is not None:
            try:
                self.cap.release()
                logger.info("camera.stopped", camera_id=self.camera_id)
            except Exception as e:
                logger.error("camera.release.failed", camera_id=self.camera_id, error=str(e))
            finally:
                self.cap = None
```

#### Passo 2: Adicionar Context Manager ao Recorder
Edite `src/zebtrack/io/recorder.py`:

**ADICIONE:**
```python
from types import TracebackType

class Recorder:
    """
    Records tracking data and video output.

    Supports context manager for automatic file closure.

    Example:
        with Recorder(output_dir, settings_obj) as recorder:
            recorder.write_frame(frame, detections)
    """

    def __enter__(self) -> 'Recorder':
        """Enter context manager."""
        # Resources opened in __init__ or start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None
    ) -> bool:
        """Exit context manager - close all files."""
        self.close()
        return False

    def close(self) -> None:
        """Close all open file handles and release resources."""
        # Close Parquet writer
        if hasattr(self, '_parquet_writer') and self._parquet_writer is not None:
            try:
                self._parquet_writer.close()
                logger.info("recorder.parquet.closed")
            except Exception as e:
                logger.error("recorder.parquet.close.failed", error=str(e))
            finally:
                self._parquet_writer = None

        # Close video writer
        if hasattr(self, '_video_writer') and self._video_writer is not None:
            try:
                self._video_writer.release()
                logger.info("recorder.video.closed")
            except Exception as e:
                logger.error("recorder.video.release.failed", error=str(e))
            finally:
                self._video_writer = None
```

#### Passo 3: Atualizar ProcessingWorker para usar Context Managers
Edite `src/zebtrack/core/processing_worker.py`:

**ANTES:**
```python
camera = LiveCameraService(settings_obj, camera_id=0)
camera.start()
try:
    while running:
        frame = camera.read_frame()
finally:
    camera.stop()
```

**DEPOIS:**
```python
with LiveCameraService(settings_obj, camera_id=0) as camera:
    while running:
        frame = camera.read_frame()
# Automatic cleanup on exit
```

#### Passo 4: Criar Testes
Crie `tests/test_resource_management.py`:

```python
"""Test resource management and context managers."""

import pytest
from unittest.mock import Mock, patch
from zebtrack.io.live_camera import LiveCameraService
from zebtrack.io.recorder import Recorder


class TestLiveCameraContextManager:
    """Test LiveCameraService context manager."""

    def test_context_manager_starts_and_stops(self, settings_obj):
        """Context manager automatically starts and stops camera."""
        with patch('cv2.VideoCapture') as mock_capture:
            mock_cap = Mock()
            mock_cap.isOpened.return_value = True
            mock_capture.return_value = mock_cap

            with LiveCameraService(settings_obj, camera_id=0) as camera:
                assert camera.cap is not None
                mock_cap.isOpened.assert_called()

            # After exit, cap is released
            mock_cap.release.assert_called_once()

    def test_context_manager_cleans_up_on_exception(self, settings_obj):
        """Context manager cleans up even if exception raised."""
        with patch('cv2.VideoCapture') as mock_capture:
            mock_cap = Mock()
            mock_cap.isOpened.return_value = True
            mock_capture.return_value = mock_cap

            with pytest.raises(RuntimeError):
                with LiveCameraService(settings_obj, camera_id=0) as camera:
                    raise RuntimeError("Test error")

            # Still cleaned up
            mock_cap.release.assert_called_once()


class TestRecorderContextManager:
    """Test Recorder context manager."""

    def test_context_manager_closes_files(self, tmp_path, settings_obj):
        """Context manager automatically closes files."""
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        with Recorder(str(output_dir), settings_obj) as recorder:
            assert recorder is not None

        # Files closed after exit
        # (Verify by checking if files can be opened again)
```

#### Passo 5: Validar
```bash
# Teste resource management
poetry run pytest tests/test_resource_management.py -v

# Teste suite completa
poetry run pytest -q
```

#### Passo 6: Commit
```bash
git add src/zebtrack/io/live_camera.py src/zebtrack/io/recorder.py src/zebtrack/core/processing_worker.py tests/test_resource_management.py

git commit -m "refactor(resources): Add context managers for automatic cleanup (P1-T2)

- Implement __enter__/__exit__ in LiveCameraService
- Implement __enter__/__exit__ in Recorder
- Update ProcessingWorker to use context managers
- Ensure cleanup even on exceptions
- Add resource management tests

Depends: P1-T5
Task: P1-T2
Agent: Agent-2"

git push origin refactor/phase-1-critical-fixes
```

### ✅ Critérios de Sucesso
- [ ] LiveCameraService implements `__enter__`/`__exit__`
- [ ] Recorder implements `__enter__`/`__exit__`
- [ ] ProcessingWorker usa context managers
- [ ] Testes de cleanup criados (mínimo 3 testes)
- [ ] Todos os testes passando
- [ ] Zero erros Ruff
- [ ] Commit e push concluídos

### ⏱️ Estimativa
**Total**: ~90 minutos

---

## 📊 Resumo do Grupo 3

### Dependência Crítica
✋ **AGUARDAR Agent-5 (P1-T5) concluir ANTES de iniciar este grupo**

### Execução Paralela
Agent-1 e Agent-2 podem trabalhar **simultaneamente** após P1-T5:
- ✅ Modificam arquivos diferentes
- ✅ Ambos dependem apenas de P1-T5 (exceptions.py)

### Comunicação de Conclusão
```
✅ GRUPO 3 CONCLUÍDO (Phase 1)

Tarefas:
- ✅ Agent-1 (P1-T1): Exception Handling Modernization
- ✅ Agent-2 (P1-T2): Resource Management

Branch: refactor/phase-1-critical-fixes

🎉 PHASE 1 COMPLETA - Pronto para merge e Phase 2
```

---

**Data de Execução**: ___________
**Agents Responsáveis**: ___________
**Status**: [ ] Aguardando P1-T5 | [ ] Em Progresso | [ ] Concluído
