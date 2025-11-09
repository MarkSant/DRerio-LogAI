# Plano de Refatoração Paralela - ZebTrack-AI

## Parte 1: Fase 1 - Correções Críticas

---

## 📋 ÍNDICE

### Parte 1 (Este Arquivo)

- [Visão Geral](#visão-geral)
- [Estratégia de Branches](#estratégia-de-branches)
- [Ordem de Merge](#ordem-de-merge)
- [FASE 1: Correções Críticas](#fase-1-correções-críticas-2-semanas)
  - [P1-T1: Broad Exception Handling](#tarefa-p1-t1-broad-exception-handling)
  - [P1-T2: Resource Management](#tarefa-p1-t2-resource-management)
  - [P1-T3: Settings Injection](#tarefa-p1-t3-settings-injection-completion)
  - [P1-T4: CI Fixes](#tarefa-p1-t4-ci-fixes)
  - [P1-T5: Custom Exception Hierarchy](#tarefa-p1-t5-custom-exception-hierarchy)

### Parte 2 (Ver PLANO_REFATORACAO_PARALELA_PARTE2.md)

- FASE 2: Extração de God Objects
- FASE 3: Testes e Qualidade
- FASE 4: Performance e Documentação Final

---

## 🎯 VISÃO GERAL

Este plano divide a refatoração em **4 fases sequenciais**, cada uma com **múltiplas tarefas paralelas** que podem ser executadas por **agentes independentes** sem conflitos de código.

### Princípios

1. **Zero conflitos**: Cada tarefa modifica arquivos exclusivos ou seções isoladas
2. **100% testável**: Toda tarefa tem critérios de aceitação verificáveis
3. **Merge incremental**: Branches de tarefa → Branch de fase → Main
4. **CI enforcement**: Ruff + Pytest devem passar em cada PR

### Estrutura

```text
main
├── refactor/phase-1-critical-fixes (Semanas 1-2)
│   ├── task/p1-t1-exception-handling
│   ├── task/p1-t2-resource-management
│   ├── task/p1-t3-settings-injection
│   ├── task/p1-t4-ci-fixes
│   └── task/p1-t5-custom-exceptions
├── refactor/phase-2-god-objects (Semanas 3-4)
│   ├── task/p2-t1-hardware-coordinator
│   ├── task/p2-t2-analysis-coordinator
│   └── task/p2-t3-mainviewmodel-refactor
├── refactor/phase-3-testing-quality (Semanas 5-6)
│   ├── task/p3-t1-test-isolation
│   ├── task/p3-t2-coverage-increase
│   ├── task/p3-t3-integration-tests
│   └── task/p3-t4-code-quality
└── refactor/phase-4-performance-docs (Semana 7)
    ├── task/p4-t1-performance-optimization
    ├── task/p4-t2-devops-tooling
    └── task/p4-t3-documentation-curation
```

---

## 🌿 ESTRATÉGIA DE BRANCHES

### Criação de Branches

**Branch de Fase** (criada pelo coordenador):

```bash
git checkout main
git pull origin main
git checkout -b refactor/phase-X-name
git push origin refactor/phase-X-name
```

**Branch de Tarefa** (criada pelo agente):

```bash
git checkout refactor/phase-X-name
git pull origin refactor/phase-X-name
git checkout -b task/pX-tY-task-name
# ... trabalho ...
git push origin task/pX-tY-task-name
```

### Fluxo de PRs

```text
task/pX-tY-task-name → refactor/phase-X-name (PR individual)
refactor/phase-X-name → main (PR da fase completa)
```

---

## 📋 ORDEM DE MERGE

### Fase 1: Correções Críticas

```text
1. P1-T5 (Custom Exceptions) ← PRIMEIRO (dependência de P1-T1 e P1-T2)
2. P1-T4 (CI Fixes) ← Independente, pode mergear em paralelo com P1-T3
3. P1-T3 (Settings Injection) ← Independente
4. P1-T1 (Exception Handling) ← APÓS P1-T5
5. P1-T2 (Resource Management) ← APÓS P1-T5
6. Merge refactor/phase-1-critical-fixes → main
```

**CRÍTICO**: P1-T5 deve ser mergeado ANTES de P1-T1 e P1-T2 pois eles dependem das exceções customizadas.

---

## 🔥 FASE 1: CORREÇÕES CRÍTICAS (2 SEMANAS)

**Branch Base**: `refactor/phase-1-critical-fixes`

**Objetivo**: Resolver problemas críticos de arquitetura que bloqueiam melhorias futuras.

---

### TAREFA P1-T1: Broad Exception Handling

**Branch**: `task/p1-t1-exception-handling`

**Dependências**: P1-T5 (Custom Exception Hierarchy)

**Estimativa**: 3 dias

**Agente**: Agent-1

#### Contexto

Substituir 30+ ocorrências de `except Exception:` por exceções específicas da hierarquia customizada.

#### Arquivos a Modificar

```text
src/zebtrack/io/video_source.py
src/zebtrack/io/recorder.py
src/zebtrack/core/detector_service.py
src/zebtrack/core/processing_worker.py
src/zebtrack/ui/gui.py
tests/* (atualizar expects)
```

#### Instruções Detalhadas

##### Passo 1: Identificar Todas as Ocorrências

```bash
# Buscar todas as ocorrências de except Exception
grep -rn "except Exception:" src/ --include="*.py" > exceptions_to_fix.txt

# Deve mostrar ~30 ocorrências
wc -l exceptions_to_fix.txt
```

##### Passo 2: Análise por Arquivo

Para cada arquivo, identificar o contexto da exceção:

- **I/O operations**: `FileOperationError`, `CameraError`, `VideoError`
- **Detection**: `DetectorError`, `ModelLoadError`
- **Processing**: `ProcessingError`, `TrackingError`
- **UI**: `UIError`, `ValidationError`

##### Passo 3: Substituições Específicas

**Exemplo 1: src/zebtrack/io/video_source.py**

Antes:

```python
try:
    self.cap = cv2.VideoCapture(source)
except Exception as e:
    log.error("Failed to open video", error=str(e))
    raise
```

Depois:

```python
from zebtrack.exceptions import VideoSourceError

try:
    self.cap = cv2.VideoCapture(source)
except cv2.error as e:
    log.error("video.open.failed", source=source, error=str(e))
    raise VideoSourceError(f"Failed to open video source: {source}") from e
except Exception as e:
    log.error("video.open.unexpected", source=source, error=str(e))
    raise VideoSourceError(f"Unexpected error opening video: {e}") from e
```

**Exemplo 2: src/zebtrack/io/recorder.py**

Antes:

```python
try:
    self.writer.write(frame)
except Exception as e:
    log.error("Failed to write frame", error=str(e))
```

Depois:

```python
from zebtrack.exceptions import RecorderError

try:
    self.writer.write(frame)
except cv2.error as e:
    log.error("recorder.write.failed", frame_num=self.frame_count, error=str(e))
    raise RecorderError(f"Failed to write frame {self.frame_count}") from e
except Exception as e:
    log.error("recorder.write.unexpected", error=str(e))
    raise RecorderError(f"Unexpected recorder error: {e}") from e
```

**Exemplo 3: src/zebtrack/core/detector_service.py**

Antes:

```python
try:
    results = self.detector.detect(frame)
except Exception as e:
    log.error("Detection failed", error=str(e))
    return []
```

Depois:

```python
from zebtrack.exceptions import DetectorError, ModelError

try:
    results = self.detector.detect(frame)
except RuntimeError as e:
    if "CUDA" in str(e) or "GPU" in str(e):
        log.error("detector.gpu_error", error=str(e))
        raise DetectorError("GPU detection error") from e
    raise DetectorError(f"Detection runtime error: {e}") from e
except ValueError as e:
    log.error("detector.invalid_input", error=str(e))
    raise DetectorError(f"Invalid input for detection: {e}") from e
except Exception as e:
    log.error("detector.unexpected", error=str(e))
    raise DetectorError(f"Unexpected detection error: {e}") from e
```

##### Passo 4: Atualizar Imports

Em cada arquivo modificado, adicionar os imports necessários:

```python
from zebtrack.exceptions import (
    VideoSourceError,
    RecorderError,
    DetectorError,
    # ... outras conforme necessário
)
```

##### Passo 5: Atualizar Testes

Atualizar testes para esperar as novas exceções:

```python
# Antes
with pytest.raises(Exception):
    video_source.open("invalid_path")

# Depois
from zebtrack.exceptions import VideoSourceError

with pytest.raises(VideoSourceError):
    video_source.open("invalid_path")
```

#### Critérios de Aceitação

- [ ] 30+ ocorrências de `except Exception:` substituídas
- [ ] Cada exceção usa classe específica da hierarquia customizada
- [ ] Imports atualizados em todos os arquivos modificados
- [ ] Testes atualizados para esperar exceções específicas
- [ ] 100% dos testes passando
- [ ] `poetry run ruff check .` zero erros
- [ ] Logs seguem padrão `domain.action.result`

#### Comandos de Validação

```bash
# Verificar que nenhum except Exception genérico resta
grep -r "except Exception:" src/ --include="*.py"
# Deve retornar 0 resultados (ou apenas casos justificados com comentário)

# Executar testes
poetry run pytest -q

# Verificar linting
poetry run ruff check .
```

---

### TAREFA P1-T2: Resource Management

**Branch**: `task/p1-t2-resource-management`

**Dependências**: P1-T5 (Custom Exception Hierarchy)

**Estimativa**: 3 dias

**Agente**: Agent-2

#### Contexto

Adicionar context managers (`__enter__`/`__exit__`) para Camera e Recorder garantirem cleanup de recursos.

#### Arquivos a Modificar

```text
src/zebtrack/io/camera.py
src/zebtrack/io/video_source.py
src/zebtrack/io/recorder.py
tests/io/test_camera.py
tests/io/test_recorder.py
```

#### Instruções Detalhadas

##### Passo 1: Modificar Camera Class

```python
# src/zebtrack/io/camera.py

class Camera:
    """Camera wrapper with context manager support."""
    
    def __init__(self, index: int = 0, settings_obj: Settings | None = None):
        self.index = index
        self.settings = settings_obj
        self.cap: cv2.VideoCapture | None = None
        self._is_opened = False
        
    def open(self):
        """Open camera."""
        if self._is_opened:
            log.warning("camera.already_open", index=self.index)
            return
            
        try:
            self.cap = cv2.VideoCapture(self.index)
            if not self.cap.isOpened():
                raise CameraError(f"Failed to open camera {self.index}")
            self._is_opened = True
            log.info("camera.open.success", index=self.index)
        except Exception as e:
            log.error("camera.open.failed", index=self.index, error=str(e))
            raise CameraError(f"Camera {self.index} open failed") from e
            
    def release(self):
        """Release camera resources."""
        if not self._is_opened:
            return
            
        try:
            if self.cap:
                self.cap.release()
            self._is_opened = False
            log.info("camera.release.success", index=self.index)
        except Exception as e:
            log.error("camera.release.failed", index=self.index, error=str(e))
        finally:
            self.cap = None
            
    def __enter__(self):
        """Context manager entry."""
        self.open()
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - always releases camera."""
        self.release()
        return False  # Don't suppress exceptions
```

##### Passo 2: Modificar Recorder Class

```python
# src/zebtrack/io/recorder.py

class Recorder:
    """Video and data recorder with context manager support."""
    
    def __init__(self, output_path: str, settings_obj: Settings):
        self.output_path = Path(output_path)
        self.settings = settings_obj
        self.video_writer: cv2.VideoWriter | None = None
        self.parquet_writer: ParquetWriter | None = None
        self._is_recording = False
        
    def start(self):
        """Start recording."""
        if self._is_recording:
            log.warning("recorder.already_started")
            return
            
        try:
            # Initialize video writer
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            self.video_writer = cv2.VideoWriter(
                str(self.output_path / "output.mp4"),
                fourcc,
                30.0,
                (640, 480)
            )
            
            # Initialize Parquet writer
            self.parquet_writer = ParquetWriter(self.output_path / "tracks.parquet")
            
            self._is_recording = True
            log.info("recorder.start.success", path=str(self.output_path))
            
        except Exception as e:
            log.error("recorder.start.failed", error=str(e))
            self.stop()  # Cleanup partial initialization
            raise RecorderError(f"Failed to start recorder: {e}") from e
            
    def stop(self):
        """Stop recording and release resources."""
        if not self._is_recording:
            return
            
        try:
            if self.video_writer:
                self.video_writer.release()
                
            if self.parquet_writer:
                self.parquet_writer.close()
                
            self._is_recording = False
            log.info("recorder.stop.success")
            
        except Exception as e:
            log.error("recorder.stop.failed", error=str(e))
        finally:
            self.video_writer = None
            self.parquet_writer = None
            
    def __enter__(self):
        """Context manager entry."""
        self.start()
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - always stops recording."""
        self.stop()
        return False
```

##### Passo 3: Atualizar Usages

Atualizar código que usa Camera/Recorder para usar context manager:

```python
# Antes
camera = Camera(index=0, settings_obj=settings)
camera.open()
try:
    frame = camera.read()
    # ... process frame
finally:
    camera.release()

# Depois
with Camera(index=0, settings_obj=settings) as camera:
    frame = camera.read()
    # ... process frame
# Camera automatically released even if exception occurs
```

##### Passo 4: Criar Testes de Context Manager

```python
# tests/io/test_camera.py

def test_camera_context_manager(mock_cv2):
    """Test camera context manager releases resources."""
    with Camera(index=0) as camera:
        assert camera._is_opened
        
    # After context exit, should be released
    assert not camera._is_opened
    assert camera.cap is None
    
def test_camera_context_manager_with_exception(mock_cv2):
    """Test camera releases even on exception."""
    try:
        with Camera(index=0) as camera:
            assert camera._is_opened
            raise ValueError("Test exception")
    except ValueError:
        pass
        
    # Should still be released
    assert not camera._is_opened
    
# tests/io/test_recorder.py

def test_recorder_context_manager(tmp_path):
    """Test recorder context manager cleanup."""
    output_path = tmp_path / "output"
    
    with Recorder(output_path, settings_obj=Mock()) as recorder:
        assert recorder._is_recording
        recorder.write_frame(np.zeros((480, 640, 3), dtype=np.uint8))
        
    # After context, should be stopped
    assert not recorder._is_recording
    assert recorder.video_writer is None
```

#### Critérios de Aceitação

- [ ] `Camera` implementa context manager
- [ ] `Recorder` implementa context manager
- [ ] Recursos sempre liberados, mesmo com exceções
- [ ] Usages atualizados para usar `with` statements
- [ ] 10+ testes para context manager behavior
- [ ] 100% dos testes passando
- [ ] Zero erros Ruff

#### Comandos de Validação

```bash
# Executar testes de context manager
poetry run pytest tests/io/test_camera.py -v -k "context"
poetry run pytest tests/io/test_recorder.py -v -k "context"

# Executar todos os testes
poetry run pytest -q

# Verificar linting
poetry run ruff check .
```

---

### TAREFA P1-T3: Settings Injection Completion

**Branch**: `task/p1-t3-settings-injection`

**Dependências**: Nenhuma (independente)

**Estimativa**: 2 dias

**Agente**: Agent-3

#### Contexto

Completar migração de settings injection nos 2 arquivos restantes que ainda usam singleton.

#### Arquivos a Modificar

```text
src/zebtrack/ui/wizard/camera_step.py
src/zebtrack/ui/wizard/arena_step.py
src/zebtrack/ui/wizard/wizard_dialog.py (para passar settings_obj)
tests/ui/wizard/test_camera_step.py
tests/ui/wizard/test_arena_step.py
```

#### Instruções Detalhadas

##### Passo 1: Modificar src/zebtrack/ui/wizard/camera_step.py

```python
# REMOVER import singleton
# from zebtrack import settings

# ADICIONAR ao __init__
class CameraStep:
    def __init__(
        self,
        parent,
        wizard_data: dict,
        settings_obj: Settings,  # ✅ ADICIONAR
    ):
        self.parent = parent
        self.wizard_data = wizard_data
        self.settings = settings_obj  # ✅ USAR
        
        # ... resto do código permanece igual
        # Trocar todas as referências de 'settings.camera.X' para 'self.settings.camera.X'
```

##### Passo 2: Modificar src/zebtrack/ui/wizard/arena_step.py

```python
# REMOVER import singleton
# from zebtrack import settings

# ADICIONAR ao __init__
class ArenaStep:
    def __init__(
        self,
        parent,
        wizard_data: dict,
        settings_obj: Settings,  # ✅ ADICIONAR
    ):
        self.parent = parent
        self.wizard_data = wizard_data
        self.settings = settings_obj  # ✅ USAR
        
        # Trocar 'settings.arena.X' para 'self.settings.arena.X'
```

##### Passo 3: Atualizar Callers (WizardDialog)

```python
# src/zebtrack/ui/wizard/wizard_dialog.py

class WizardDialog:
    def __init__(self, parent, settings_obj: Settings):
        self.parent = parent
        self.settings = settings_obj
        self.wizard_data = {}
        
        # Criar steps passando settings_obj
        self.steps = [
            ProjectStep(self, self.wizard_data, self.settings),
            CameraStep(self, self.wizard_data, self.settings),  # ✅ PASSAR settings_obj
            ArenaStep(self, self.wizard_data, self.settings),   # ✅ PASSAR settings_obj
            # ... outros steps
        ]
```

##### Passo 4: Validar que Nenhum Singleton Resta

```bash
# Buscar imports de singleton
grep -r "from zebtrack import settings" src/zebtrack/

# Deve retornar ZERO resultados
# Se retornar algo, investigar e corrigir
```

#### Critérios de Aceitação

- [ ] `camera_step.py` usa `settings_obj` parameter
- [ ] `arena_step.py` usa `settings_obj` parameter
- [ ] `WizardDialog` passa `settings_obj` para todos os steps
- [ ] ZERO imports `from zebtrack import settings` em src/
- [ ] Testes atualizados para passar `settings_obj`
- [ ] 100% dos testes passando
- [ ] Zero erros Ruff

#### Comandos de Validação

```bash
# Verificar que singleton foi eliminado
grep -r "from zebtrack import settings" src/zebtrack/
# Deve retornar: (vazio)

# Executar testes
poetry run pytest tests/ui/wizard/ -v
poetry run pytest -q

# Linting
poetry run ruff check .
```

---

### TAREFA P1-T4: CI Fixes

**Branch**: `task/p1-t4-ci-fixes`

**Dependências**: Nenhuma (independente)

**Estimativa**: 1 dia

**Agente**: Agent-4

#### Contexto

Corrigir erro de sintaxe em `.github/workflows/ci.yml` (linha 86: espaço após `-`).

#### Arquivo a Modificar

```text
.github/workflows/ci.yml
```

#### Instruções Detalhadas

##### Passo 1: Localizar Erro

```bash
# Ver linha 86
sed -n '80,90p' .github/workflows/ci.yml

# Deve mostrar algo como:
#   - name: Run tests
#   - run: poetry run pytest  # ❌ espaço após '-'
```

##### Passo 2: Corrigir Sintaxe

```yaml
# .github/workflows/ci.yml

# ANTES (linha ~86):
  - run: poetry run pytest

# DEPOIS:
  -run: poetry run pytest
  
# OU (se o problema for diferente, ajustar conforme necessário)
```

**IMPORTANTE**: Validar o YAML completo após a correção.

##### Passo 3: Validar YAML

```bash
# Validar sintaxe YAML
poetry run python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))"

# Deve rodar sem erros
```

#### Critérios de Aceitação

- [ ] Sintaxe YAML corrigida na linha 86
- [ ] Validação YAML passa sem erros
- [ ] CI workflow roda sem erros de sintaxe
- [ ] Documentação atualizada se necessário

#### Comandos de Validação

```bash
# Validar YAML
poetry run python -c "import yaml; print('YAML OK')"

# Testar localmente (se possível)
act -l  # Se tiver 'act' instalado para testar GitHub Actions localmente

# Ou fazer commit e ver CI passar
git commit -m "fix(ci): correct YAML syntax in workflow"
git push
# Verificar GitHub Actions UI
```

---

### TAREFA P1-T5: Custom Exception Hierarchy

**Branch**: `task/p1-t5-custom-exceptions`

**Dependências**: Nenhuma (deve ser feita PRIMEIRO)

**Estimativa**: 2 dias

**Agente**: Agent-5

#### Contexto

Criar hierarquia completa de exceções customizadas em `src/zebtrack/exceptions.py`.

**CRÍTICO**: Esta tarefa deve ser mergeada ANTES de P1-T1 e P1-T2.

#### Arquivo a Modificar

```text
src/zebtrack/exceptions.py (expandir hierarquia existente)
tests/test_exceptions.py (NOVO)
src/zebtrack/__init__.py (atualizar exports)
```

#### Instruções Detalhadas

##### Passo 1: Analisar Exceções Existentes

```bash
# Ver exceções já definidas
cat src/zebtrack/exceptions.py

# Deve mostrar ~8 exceções básicas
```

##### Passo 2: Criar Hierarquia Expandida

```python
# src/zebtrack/exceptions.py

"""
Custom exception hierarchy for ZebTrack-AI.

All application exceptions inherit from ZebTrackError for easy catching.
"""

# ============================================================================
# Base Exception
# ============================================================================

class ZebTrackError(Exception):
    """Base exception for all ZebTrack errors."""
    pass


# ============================================================================
# I/O and File Operations
# ============================================================================

class FileOperationError(ZebTrackError):
    """Base for file operation errors."""
    pass

class VideoSourceError(FileOperationError):
    """Error opening or reading video source."""
    pass

class VideoWriteError(FileOperationError):
    """Error writing video output."""
    pass

class CameraError(FileOperationError):
    """Error accessing camera hardware."""
    pass

class CameraConnectionError(CameraError):
    """Failed to connect to camera."""
    pass

class RecorderError(FileOperationError):
    """Error in recording system."""
    pass

class ParquetError(FileOperationError):
    """Error reading/writing Parquet files."""
    pass


# ============================================================================
# Detection and Tracking
# ============================================================================

class DetectorError(ZebTrackError):
    """Base for detector errors."""
    pass

class ModelLoadError(DetectorError):
    """Failed to load detection model."""
    pass

class ModelError(DetectorError):
    """Error during model inference."""
    pass

class TrackingError(ZebTrackError):
    """Error in tracking system."""
    pass

class ZoneError(ZebTrackError):
    """Error in zone configuration or scaling."""
    pass


# ============================================================================
# Processing and Analysis
# ============================================================================

class ProcessingError(ZebTrackError):
    """Base for processing errors."""
    pass

class FrameProcessingError(ProcessingError):
    """Error processing a video frame."""
    pass

class AnalysisError(ZebTrackError):
    """Error during behavioral analysis."""
    pass


# ============================================================================
# Hardware
# ============================================================================

class HardwareError(ZebTrackError):
    """Base for hardware errors."""
    pass

class ArduinoError(HardwareError):
    """Error communicating with Arduino."""
    pass

class ArduinoConnectionError(ArduinoError):
    """Failed to connect to Arduino."""
    pass


# ============================================================================
# UI and User Input
# ============================================================================

class UIError(ZebTrackError):
    """Base for UI errors."""
    pass

class ValidationError(UIError):
    """User input validation failed."""
    pass

class WizardError(UIError):
    """Error in wizard workflow."""
    pass


# ============================================================================
# Configuration
# ============================================================================

class ConfigurationError(ZebTrackError):
    """Base for configuration errors."""
    pass

class SettingsError(ConfigurationError):
    """Error in settings validation or loading."""
    pass

class ProjectError(ConfigurationError):
    """Error in project configuration."""
    pass


# ============================================================================
# Export for convenience
# ============================================================================

__all__ = [
    'ZebTrackError',
    # I/O
    'FileOperationError',
    'VideoSourceError',
    'VideoWriteError',
    'CameraError',
    'CameraConnectionError',
    'RecorderError',
    'ParquetError',
    # Detection
    'DetectorError',
    'ModelLoadError',
    'ModelError',
    'TrackingError',
    'ZoneError',
    # Processing
    'ProcessingError',
    'FrameProcessingError',
    'AnalysisError',
    # Hardware
    'HardwareError',
    'ArduinoError',
    'ArduinoConnectionError',
    # UI
    'UIError',
    'ValidationError',
    'WizardError',
    # Configuration
    'ConfigurationError',
    'SettingsError',
    'ProjectError',
]
```

##### Passo 3: Adicionar Testes para Exceções

```python
# tests/test_exceptions.py (NOVO)

"""Tests for custom exception hierarchy."""

import pytest
from zebtrack.exceptions import (
    ZebTrackError,
    VideoSourceError,
    CameraError,
    DetectorError,
    ModelLoadError,
    UIError,
    ValidationError,
    # ... importar todas
)


class TestExceptionHierarchy:
    """Test exception inheritance."""
    
    def test_all_inherit_from_zebtrack_error(self):
        """Test all exceptions inherit from ZebTrackError."""
        assert issubclass(VideoSourceError, ZebTrackError)
        assert issubclass(CameraError, ZebTrackError)
        assert issubclass(DetectorError, ZebTrackError)
        assert issubclass(UIError, ZebTrackError)
        
    def test_specific_inheritance(self):
        """Test specific inheritance chains."""
        assert issubclass(CameraError, FileOperationError)
        assert issubclass(ModelLoadError, DetectorError)
        assert issubclass(ValidationError, UIError)
        
    def test_exception_instantiation(self):
        """Test exceptions can be instantiated with message."""
        exc = VideoSourceError("Test message")
        assert str(exc) == "Test message"
        
    def test_exception_raising(self):
        """Test exceptions can be raised and caught."""
        with pytest.raises(VideoSourceError):
            raise VideoSourceError("Test")
            
        with pytest.raises(ZebTrackError):
            raise VideoSourceError("Caught by base class")


class TestSpecificExceptions:
    """Test specific exception behaviors."""
    
    def test_camera_connection_error(self):
        """Test CameraConnectionError."""
        with pytest.raises(CameraConnectionError):
            raise CameraConnectionError("Camera not found")
            
    def test_model_load_error(self):
        """Test ModelLoadError."""
        with pytest.raises(ModelLoadError):
            raise ModelLoadError("Model file missing")
            
    def test_validation_error(self):
        """Test ValidationError."""
        with pytest.raises(ValidationError):
            raise ValidationError("Invalid input")
```

##### Passo 4: Atualizar __init__.py para Export

```python
# src/zebtrack/__init__.py

# Adicionar exports de exceções
from zebtrack.exceptions import (
    ZebTrackError,
    VideoSourceError,
    CameraError,
    DetectorError,
    # ... todas as principais
)

__all__ = [
    # ... existing exports
    'ZebTrackError',
    'VideoSourceError',
    'CameraError',
    'DetectorError',
    # ... etc
]
```

#### Critérios de Aceitação

- [ ] 15+ custom exceptions criadas
- [ ] Hierarquia organizada por domínio (I/O, Detection, UI, etc)
- [ ] Todas herdam de `ZebTrackError`
- [ ] Testes para hierarquia de herança
- [ ] Exports atualizados em `__init__.py`
- [ ] 100% dos testes passando
- [ ] Zero erros Ruff
- [ ] Documentação inline (docstrings) em todas as classes

#### Comandos de Validação

```bash
# Contar exceções criadas
grep -c "class.*Error.*:" src/zebtrack/exceptions.py
# Deve retornar ≥15

# Executar testes
poetry run pytest tests/test_exceptions.py -v

# Todos os testes
poetry run pytest -q

# Linting
poetry run ruff check .

# Verificar exports
poetry run python -c "from zebtrack import ZebTrackError, VideoSourceError; print('OK')"
```

---

**FIM DA PARTE 1**

Ver `PLANO_REFATORACAO_PARALELA_PARTE2.md` para Fases 2-4.
