# Agent Instructions - Phase 1, Group 1 (BLOCKER CRÍTICO)

**⚠️ ATENÇÃO: Esta tarefa é BLOQUEADORA - deve ser concluída ANTES de iniciar Grupo 3**

## 📋 Visão Geral
- **Grupo de Execução**: Phase 1, Group 1
- **Número de Agentes**: 1
- **Dependências**: Nenhuma (pode iniciar imediatamente)
- **Bloqueia**: Agent-1 (P1-T1), Agent-2 (P1-T2)
- **Branch**: `refactor/phase-1-critical-fixes`

---

## 🤖 AGENT-5: Hierarquia de Exceções Customizadas (P1-T5)

### 📌 Contexto
Você é o **Agent-5** responsável por criar a hierarquia de exceções customizadas do ZebTrack-AI. Esta é uma tarefa **BLOQUEADORA CRÍTICA** - outras tarefas (P1-T1 e P1-T2) dependem da sua conclusão.

### 🎯 Objetivo
Criar arquivo `src/zebtrack/core/exceptions.py` com hierarquia completa de exceções customizadas, seguindo padrões Python modernos e permitindo tratamento granular de erros.

### 📂 Acesso ao Repositório
```bash
# Clone o repositório
git clone https://github.com/MarkSant/ZebTrack-AI.git
cd ZebTrack-AI

# Crie e faça checkout da branch de trabalho
git checkout -b refactor/phase-1-critical-fixes

# Configure o ambiente
poetry install
poetry shell
```

### 📖 Documentação Detalhada
Leia cuidadosamente as seguintes seções da documentação:

1. **PLANO_REFATORACAO_PARALELA_PARTE1.md**
   - Seção: "P1-T5: Criar Hierarquia de Exceções Customizadas (Agent-5)"
   - Linhas: ~600-750
   - Conteúdo: Código completo, estrutura de testes, exemplos

2. **AGENT_ORCHESTRATION_GUIDE.md**
   - Seção: "Agent-5: Custom Exception Hierarchy (P1-T5)"
   - Linhas: ~350-400
   - Conteúdo: Comandos exatos, troubleshooting

3. **REFACTORING_QUICK_REFERENCE.md**
   - Seção: "Phase 1 Critical Fixes"
   - Item: "P1-T5"
   - Conteúdo: Resumo executivo

### 🛠️ Implementação Passo a Passo

#### Passo 1: Criar Estrutura Base
```bash
# Navegue até o diretório core
cd src/zebtrack/core

# Crie o arquivo de exceções (se não existir)
New-Item -ItemType File -Force exceptions.py
```

#### Passo 2: Implementar Hierarquia de Exceções
Crie o arquivo `src/zebtrack/core/exceptions.py` com o seguinte conteúdo completo:

```python
"""
Custom exception hierarchy for ZebTrack-AI.

This module defines a comprehensive exception hierarchy that allows
granular error handling throughout the application. All custom exceptions
inherit from ZebTrackError base class.

Exception Hierarchy:
    ZebTrackError (base)
    ├── ConfigurationError
    │   ├── InvalidSettingsError
    │   └── MissingConfigError
    ├── ResourceError
    │   ├── CameraError
    │   │   ├── CameraNotFoundError
    │   │   └── CameraAccessError
    │   ├── VideoError
    │   │   ├── VideoNotFoundError
    │   │   └── VideoReadError
    │   └── FileError
    │       ├── FileNotFoundError (shadows builtin)
    │       └── FileWriteError
    ├── ProcessingError
    │   ├── DetectionError
    │   ├── TrackingError
    │   └── AnalysisError
    ├── ProjectError
    │   ├── ProjectNotFoundError
    │   ├── ProjectLoadError
    │   └── ProjectSaveError
    └── ValidationError (renamed from existing)
        ├── ROIValidationError
        └── IntervalValidationError

Usage Example:
    try:
        camera = LiveCameraService(settings, camera_id=0)
    except CameraNotFoundError as e:
        logger.error("camera.init.failed", error=str(e))
        show_error_dialog("Camera not found")
    except CameraAccessError as e:
        logger.error("camera.access.denied", error=str(e))
        show_error_dialog("Permission denied")
"""


class ZebTrackError(Exception):
    """
    Base exception for all ZebTrack-AI custom exceptions.
    
    All custom exceptions should inherit from this class to allow
    catching all application-specific errors with a single except clause.
    
    Attributes:
        message: Human-readable error message
        details: Optional dict with additional error context
    """
    
    def __init__(self, message: str, details: dict | None = None):
        self.message = message
        self.details = details or {}
        super().__init__(self.message)
    
    def __str__(self) -> str:
        if self.details:
            details_str = ", ".join(f"{k}={v}" for k, v in self.details.items())
            return f"{self.message} ({details_str})"
        return self.message


# Configuration Exceptions
class ConfigurationError(ZebTrackError):
    """Base exception for configuration-related errors."""
    pass


class InvalidSettingsError(ConfigurationError):
    """Raised when settings validation fails."""
    pass


class MissingConfigError(ConfigurationError):
    """Raised when required configuration is missing."""
    pass


# Resource Exceptions
class ResourceError(ZebTrackError):
    """Base exception for resource-related errors."""
    pass


class CameraError(ResourceError):
    """Base exception for camera-related errors."""
    pass


class CameraNotFoundError(CameraError):
    """Raised when specified camera device is not found."""
    pass


class CameraAccessError(CameraError):
    """Raised when camera access is denied (permissions, busy, etc.)."""
    pass


class VideoError(ResourceError):
    """Base exception for video file errors."""
    pass


class VideoNotFoundError(VideoError):
    """Raised when video file does not exist."""
    pass


class VideoReadError(VideoError):
    """Raised when video file cannot be read or is corrupted."""
    pass


class FileError(ResourceError):
    """Base exception for file I/O errors."""
    pass


class FileNotFoundError(FileError):  # Shadows builtin intentionally
    """Raised when required file does not exist."""
    pass


class FileWriteError(FileError):
    """Raised when file write operation fails."""
    pass


# Processing Exceptions
class ProcessingError(ZebTrackError):
    """Base exception for processing pipeline errors."""
    pass


class DetectionError(ProcessingError):
    """Raised when object detection fails."""
    pass


class TrackingError(ProcessingError):
    """Raised when object tracking fails."""
    pass


class AnalysisError(ProcessingError):
    """Raised when behavioral analysis fails."""
    pass


# Project Exceptions
class ProjectError(ZebTrackError):
    """Base exception for project management errors."""
    pass


class ProjectNotFoundError(ProjectError):
    """Raised when project file does not exist."""
    pass


class ProjectLoadError(ProjectError):
    """Raised when project cannot be loaded."""
    pass


class ProjectSaveError(ProjectError):
    """Raised when project cannot be saved."""
    pass


# Validation Exceptions
class ZebTrackValidationError(ZebTrackError):
    """Base exception for validation errors (renamed to avoid conflict)."""
    pass


class ROIValidationError(ZebTrackValidationError):
    """Raised when ROI coordinates are invalid."""
    pass


class IntervalValidationError(ZebTrackValidationError):
    """Raised when interval configuration is invalid."""
    pass


# Export all exceptions
__all__ = [
    # Base
    'ZebTrackError',
    # Configuration
    'ConfigurationError',
    'InvalidSettingsError',
    'MissingConfigError',
    # Resources
    'ResourceError',
    'CameraError',
    'CameraNotFoundError',
    'CameraAccessError',
    'VideoError',
    'VideoNotFoundError',
    'VideoReadError',
    'FileError',
    'FileNotFoundError',
    'FileWriteError',
    # Processing
    'ProcessingError',
    'DetectionError',
    'TrackingError',
    'AnalysisError',
    # Project
    'ProjectError',
    'ProjectNotFoundError',
    'ProjectLoadError',
    'ProjectSaveError',
    # Validation
    'ZebTrackValidationError',
    'ROIValidationError',
    'IntervalValidationError',
]
```

#### Passo 3: Criar Testes Unitários
Crie o arquivo `tests/test_exceptions.py`:

```python
"""Unit tests for custom exception hierarchy."""

import pytest
from zebtrack.core.exceptions import (
    ZebTrackError,
    ConfigurationError,
    InvalidSettingsError,
    MissingConfigError,
    ResourceError,
    CameraError,
    CameraNotFoundError,
    CameraAccessError,
    VideoError,
    VideoNotFoundError,
    VideoReadError,
    FileError,
    FileNotFoundError,
    FileWriteError,
    ProcessingError,
    DetectionError,
    TrackingError,
    AnalysisError,
    ProjectError,
    ProjectNotFoundError,
    ProjectLoadError,
    ProjectSaveError,
    ZebTrackValidationError,
    ROIValidationError,
    IntervalValidationError,
)


class TestExceptionHierarchy:
    """Test exception inheritance hierarchy."""
    
    def test_base_exception(self):
        """ZebTrackError is base for all custom exceptions."""
        err = ZebTrackError("test error")
        assert str(err) == "test error"
        assert err.message == "test error"
        assert err.details == {}
    
    def test_exception_with_details(self):
        """ZebTrackError can include additional details."""
        err = ZebTrackError("test error", {"camera_id": 0, "attempt": 3})
        assert "test error" in str(err)
        assert "camera_id=0" in str(err)
        assert "attempt=3" in str(err)
    
    def test_configuration_hierarchy(self):
        """Configuration exceptions inherit correctly."""
        assert issubclass(ConfigurationError, ZebTrackError)
        assert issubclass(InvalidSettingsError, ConfigurationError)
        assert issubclass(MissingConfigError, ConfigurationError)
    
    def test_resource_hierarchy(self):
        """Resource exceptions inherit correctly."""
        assert issubclass(ResourceError, ZebTrackError)
        assert issubclass(CameraError, ResourceError)
        assert issubclass(CameraNotFoundError, CameraError)
        assert issubclass(CameraAccessError, CameraError)
        assert issubclass(VideoError, ResourceError)
        assert issubclass(VideoNotFoundError, VideoError)
        assert issubclass(VideoReadError, VideoError)
        assert issubclass(FileError, ResourceError)
        assert issubclass(FileNotFoundError, FileError)
        assert issubclass(FileWriteError, FileError)
    
    def test_processing_hierarchy(self):
        """Processing exceptions inherit correctly."""
        assert issubclass(ProcessingError, ZebTrackError)
        assert issubclass(DetectionError, ProcessingError)
        assert issubclass(TrackingError, ProcessingError)
        assert issubclass(AnalysisError, ProcessingError)
    
    def test_project_hierarchy(self):
        """Project exceptions inherit correctly."""
        assert issubclass(ProjectError, ZebTrackError)
        assert issubclass(ProjectNotFoundError, ProjectError)
        assert issubclass(ProjectLoadError, ProjectError)
        assert issubclass(ProjectSaveError, ProjectError)
    
    def test_validation_hierarchy(self):
        """Validation exceptions inherit correctly."""
        assert issubclass(ZebTrackValidationError, ZebTrackError)
        assert issubclass(ROIValidationError, ZebTrackValidationError)
        assert issubclass(IntervalValidationError, ZebTrackValidationError)
    
    def test_catch_all_exceptions(self):
        """Can catch all custom exceptions with base class."""
        exceptions_to_test = [
            InvalidSettingsError("test"),
            CameraNotFoundError("test"),
            VideoReadError("test"),
            DetectionError("test"),
            ProjectLoadError("test"),
            ROIValidationError("test"),
        ]
        
        for exc in exceptions_to_test:
            with pytest.raises(ZebTrackError):
                raise exc
    
    def test_catch_specific_category(self):
        """Can catch exceptions by category."""
        # Test camera errors
        with pytest.raises(CameraError):
            raise CameraNotFoundError("Camera 0 not found")
        
        with pytest.raises(CameraError):
            raise CameraAccessError("Permission denied")
        
        # Test video errors
        with pytest.raises(VideoError):
            raise VideoNotFoundError("video.mp4")
        
        # Test processing errors
        with pytest.raises(ProcessingError):
            raise DetectionError("YOLO failed")


class TestExceptionMessages:
    """Test exception message formatting."""
    
    def test_simple_message(self):
        """Simple error message works."""
        err = CameraNotFoundError("Camera ID 0 not available")
        assert str(err) == "Camera ID 0 not available"
    
    def test_message_with_details(self):
        """Error with details includes both message and context."""
        err = CameraAccessError(
            "Failed to open camera",
            {"camera_id": 0, "backend": "DSHOW", "attempts": 3}
        )
        msg = str(err)
        assert "Failed to open camera" in msg
        assert "camera_id=0" in msg
        assert "backend=DSHOW" in msg
        assert "attempts=3" in msg
    
    def test_details_attribute(self):
        """Details are accessible as attribute."""
        err = VideoReadError("Corrupted frame", {"frame": 150, "codec": "h264"})
        assert err.details["frame"] == 150
        assert err.details["codec"] == "h264"
```

#### Passo 4: Validar Implementação
```bash
# Execute os testes
poetry run pytest tests/test_exceptions.py -v

# Verifique se todos os 12 testes passam
# Expected output: 12 passed
```

#### Passo 5: Verificar Linting
```bash
# Execute Ruff para verificar estilo
poetry run ruff check src/zebtrack/core/exceptions.py tests/test_exceptions.py

# Execute formatter
poetry run ruff format src/zebtrack/core/exceptions.py tests/test_exceptions.py
```

#### Passo 6: Commit e Push
```bash
# Adicione os arquivos
git add src/zebtrack/core/exceptions.py tests/test_exceptions.py

# Commit com mensagem descritiva
git commit -m "feat(core): Add custom exception hierarchy (P1-T5)

- Create comprehensive exception hierarchy in core/exceptions.py
- Add base ZebTrackError with message and details support
- Implement 5 categories: Configuration, Resource, Processing, Project, Validation
- Add 17 specific exception classes for granular error handling
- Include full unit test suite (12 tests)
- Enable structured error handling for P1-T1 and P1-T2

Blocks: P1-T1, P1-T2
Task: P1-T5
Agent: Agent-5"

# Push para o repositório
git push origin refactor/phase-1-critical-fixes
```

### ✅ Critérios de Sucesso
Verifique se TODOS os critérios foram atendidos:

- [ ] Arquivo `src/zebtrack/core/exceptions.py` criado com 17 classes de exceção
- [ ] Hierarquia de 3 níveis implementada (Base → Category → Specific)
- [ ] Todas as exceções herdam de `ZebTrackError`
- [ ] Suporte para `message` e `details` implementado
- [ ] Arquivo `tests/test_exceptions.py` criado com 12 testes
- [ ] Todos os testes passam (`pytest tests/test_exceptions.py`)
- [ ] Zero erros de Ruff (`ruff check`)
- [ ] Código formatado (`ruff format`)
- [ ] Commit realizado com mensagem padrão
- [ ] Push para branch `refactor/phase-1-critical-fixes` concluído

### 🚨 Troubleshooting

**Problema**: Testes falhando com `ModuleNotFoundError`
```bash
# Solução: Reinstale o pacote em modo editable
poetry install
```

**Problema**: Conflito com `FileNotFoundError` builtin
```bash
# Solução: A exceção customizada intencionalmente shadowing o builtin
# Use sempre import completo: from zebtrack.core.exceptions import FileNotFoundError
```

**Problema**: Ruff reporta linhas muito longas
```bash
# Solução: Quebre docstrings em múltiplas linhas
# Limite: 100 caracteres por linha
```

### 📞 Comunicação de Conclusão
Após completar a tarefa, comunique:

```
✅ AGENT-5 CONCLUÍDO

Tarefa: P1-T5 - Hierarquia de Exceções Customizadas
Status: ✅ Completo

Arquivos Criados:
- src/zebtrack/core/exceptions.py (17 classes, 250 linhas)
- tests/test_exceptions.py (12 testes)

Validação:
- ✅ 12/12 testes passando
- ✅ Zero erros Ruff
- ✅ Código formatado

Commit: [hash do commit]
Branch: refactor/phase-1-critical-fixes

Desbloqueado para iniciar:
- Agent-1 (P1-T1): Exception Handling Modernization
- Agent-2 (P1-T2): Resource Management

Próximo passo: Iniciar Grupo 3 (Agent-1 e Agent-2)
```

### ⏱️ Estimativa de Tempo
- Leitura de documentação: 15 minutos
- Implementação: 30 minutos
- Testes: 20 minutos
- Validação e commit: 10 minutos
- **Total**: ~75 minutos

---

**Data de Execução**: ___________
**Agent Responsável**: ___________
**Status**: [ ] Não Iniciado | [ ] Em Progresso | [ ] Concluído | [ ] Bloqueado
