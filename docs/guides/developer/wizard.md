# Developer Guide: Wizard Architecture

Este guia documenta a arquitetura do sistema de wizard do DRerio LogAI (v2.0+), incluindo melhorias implementadas na Fase 4 das refatorações.

## Visão Geral

O wizard é o fluxo principal de criação de projetos desde a v1.6. Ele usa uma arquitetura em camadas com separação clara entre UI, lógica de negócio e validação de dados.

## Arquitetura em Camadas

### Camada 1: Service Layer (`wizard_service.py`)

**Localização**: `src/zebtrack/core/wizard_service.py`

A camada de serviço contém toda a lógica de negócio, isolada da UI:

```python
from zebtrack.core.wizard_service import WizardService

# Detecção de hardware
cameras = WizardService.detect_available_cameras()
ports = WizardService.detect_arduino_ports()

# Validações
is_valid, error_msg = WizardService.validate_live_config(data)

# Cálculos
metrics = WizardService.calculate_experiment_structure(groups=2, days=7, subjects=5)
# → {'total_sessions': 70, 'total_animals': 10, ...}
```

**Métodos Principais**:
- `detect_available_cameras()` - Detecta câmeras com supressão de logs OpenCV
- `detect_arduino_ports()` - Detecta portas serial com handshake Arduino
- `validate_live_config(data)` - Valida configuração de projetos live
- `validate_experimental_design(data)` - Valida design experimental
- `validate_calibration_data(data)` - Valida dados de calibração completos
- `validate_basic_calibration(data)` - Valida calibração básica (sem intervals/ROI rules)
- `suggest_analysis_interval(fps)` - Sugere intervalo baseado em FPS
- `calculate_experiment_structure(...)` - Calcula métricas do experimento

**Benefícios**:
- ✅ Testável independentemente da UI
- ✅ Reutilizável em diferentes contextos
- ✅ Sem dependências de Tkinter
- ✅ Logging estruturado com structlog

### Camada 2: Data Models (`wizard/models.py`)

**Localização**: `src/zebtrack/ui/wizard/models.py`

Modelos Pydantic v2 para validação type-safe dos dados do wizard:

```python
from zebtrack.ui.wizard.models import LiveConfigData, WizardData
from pydantic import ValidationError

# Validação automática
try:
    config = LiveConfigData(
        camera_index=0,
        use_arduino=True,
        arduino_port="COM3",
        external_trigger_mode=True  # OK: Arduino está ativado
    )
except ValidationError as e:
    print(e)  # Erros de validação detalhados
```

**Modelos Disponíveis**:
- `LiveConfigData` - Configuração de gravação ao vivo
- `ExperimentalDesignData` - Estrutura do experimento
- `CalibrationData` - Dados de calibração física
- `ModelSelectionData` - Seleção de modelo de detecção
- `FileSelectionData` - Seleção de vídeos pré-gravados
- `WizardData` - Agregação de todos os steps

**Validações Cross-Field**:
```python
@field_validator("external_trigger_mode")
@classmethod
def validate_external_trigger(cls, v, info):
    if v and not info.data.get("use_arduino"):
        raise ValueError("Modo de trigger externo requer Arduino ativado")
    return v
```

### Camada 3: UI Steps (`wizard/*.py`)

**Localização**: `src/zebtrack/ui/wizard/`

Steps do wizard são **puramente UI**, delegando toda lógica para `WizardService`:

```python
class LiveConfigStep(WizardStep):
    def _detect_cameras(self):
        # Usa WizardService ao invés de implementar detecção
        cameras = WizardService.detect_available_cameras()
        available_indices = [cam["index"] for cam in cameras]
        # Atualiza UI...

    def validate(self) -> tuple[bool, str]:
        # Delega validação para WizardService
        data = self.get_data()
        return WizardService.validate_live_config(data)
```

**Steps Existentes**:
1. `DiscoveryStep` - Seleção do tipo de projeto
2. `LiveConfigStep` - Configuração de hardware (live only)
3. `ExperimentalDesignStep` - Estrutura do experimento (live only)
4. `CalibrationStep` - Calibração física
5. `ModelSelectionStep` - Seleção de modelo (advanced mode)
6. `FileSelectionStep` - Seleção de vídeos (pre-recorded only)
7. `ConfirmationStep` - Resumo final

## Fluxo de Dados

```
┌─────────────┐
│ User Input  │
│   (UI)      │
└──────┬──────┘
       │ get_data()
       v
┌─────────────┐
│ WizardStep  │ ─────────────┐
│  validate() │              │
└──────┬──────┘              │
       │                     │
       │ WizardService       │ Pydantic
       │ .validate_*()       │ Models
       v                     │
┌─────────────┐              │
│   Service   │ <────────────┘
│   Layer     │
└──────┬──────┘
       │ (is_valid, error_msg)
       v
┌─────────────┐
│ WizardDialog│
│  (Next/Back)│
└─────────────┘
```

## Como Adicionar um Novo Step

### 1. Criar o Step (UI Layer)

```python
# src/zebtrack/ui/wizard/my_new_step.py
from zebtrack.ui.wizard.base import WizardStep
from zebtrack.ui.wizard.enums import WizardStepID
from zebtrack.core.wizard_service import WizardService

class MyNewStep(WizardStep):
    """Descrição do step."""

    def __init__(self, parent, wizard_data: dict):
        super().__init__(parent, wizard_data)
        self.step_id = WizardStepID.MY_NEW_STEP

        # Criar UI widgets...

    def validate(self) -> tuple[bool, str]:
        """Validar dados usando WizardService."""
        data = self.get_data()
        return WizardService.validate_my_new_data(data)

    def get_data(self) -> dict:
        """Extrair dados dos widgets."""
        return {
            "field1": self.field1_var.get(),
            "field2": self.field2_var.get(),
        }

    def set_data(self, data: dict):
        """Restaurar dados (navegação para trás)."""
        if "field1" in data:
            self.field1_var.set(data["field1"])
```

### 2. Adicionar Validação (Service Layer)

```python
# src/zebtrack/core/wizard_service.py
class WizardService:
    @staticmethod
    def validate_my_new_data(data: dict) -> tuple[bool, str]:
        """Validar os novos dados."""
        field1 = data.get("field1")
        if not field1 or len(field1) < 3:
            return (False, "Campo 1 deve ter pelo menos 3 caracteres")

        return (True, "")
```

### 3. Criar Modelo Pydantic (opcional, mas recomendado)

```python
# src/zebtrack/ui/wizard/models.py
from pydantic import BaseModel, Field, field_validator

class MyNewStepData(BaseModel):
    field1: str = Field(min_length=3, max_length=50)
    field2: int = Field(ge=1, le=100)

    @field_validator("field1")
    @classmethod
    def validate_field1(cls, v):
        if "forbidden" in v.lower():
            raise ValueError("Campo contém palavra proibida")
        return v
```

### 4. Registrar no WizardDialog

```python
# src/zebtrack/ui/wizard/wizard_dialog.py
from zebtrack.ui.wizard.my_new_step import MyNewStep

class WizardDialog:
    def _build_step_sequence(self):
        # Adicionar step na sequência apropriada
        if self.wizard_mode == "advanced":
            steps.append(MyNewStep)
```

## Widgets Reutilizáveis

### NumberInput

Widget para entrada numérica com botões +/-:

```python
from zebtrack.ui.wizard.experimental_design_step import NumberInput

number_widget = NumberInput(
    parent=frame,
    variable=self.my_var,
    min_value=1,
    max_value=100,
    label="Meu Número:",
    width=10
)
number_widget.pack()
```

### CollapsibleFrame

Frame colapsável para organizar UI:

```python
from zebtrack.ui.collapsible_frame import CollapsibleFrame

collapsible = CollapsibleFrame(
    parent,
    title="📋 Minha Seção",
    start_collapsed=False
)
collapsible.pack(fill="x", padx=5, pady=5)

# Obter frame interno para adicionar widgets
content = collapsible.get_content_frame()
Label(content, text="Conteúdo").pack()
```

## Testes

### Teste de Service Layer

```python
# tests/test_wizard_service.py
from zebtrack.core.wizard_service import WizardService

def test_validate_live_config_valid():
    data = {
        "camera_index": 0,
        "use_arduino": False,
        "use_timed_recording": False,
        "external_trigger_mode": False,
    }
    is_valid, error = WizardService.validate_live_config(data)
    assert is_valid
    assert error == ""

def test_validate_live_config_invalid_trigger():
    data = {
        "camera_index": 0,
        "use_arduino": False,  # Arduino desativado
        "external_trigger_mode": True,  # Mas trigger ativado!
    }
    is_valid, error = WizardService.validate_live_config(data)
    assert not is_valid
    assert "trigger externo requer Arduino" in error.lower()
```

### Teste de Pydantic Models

```python
# tests/test_wizard_models.py
from zebtrack.ui.wizard.models import LiveConfigData
from pydantic import ValidationError
import pytest

def test_live_config_data_valid():
    config = LiveConfigData(
        camera_index=0,
        use_arduino=True,
        arduino_port="COM3"
    )
    assert config.camera_index == 0

def test_live_config_data_trigger_validation():
    with pytest.raises(ValidationError, match="trigger.*Arduino"):
        LiveConfigData(
            camera_index=0,
            use_arduino=False,
            external_trigger_mode=True  # Inválido
        )
```

## Boas Práticas

### ✅ DO

- **Sempre use WizardService** para lógica de negócio
- **Sempre crie modelos Pydantic** para novos tipos de dados
- **Delegue validações** ao service layer
- **Use tooltips** (`ToolTip(widget, "Texto")`) em todos os campos
- **Forneça defaults inteligentes** (ex: sugestões baseadas em FPS)
- **Log todas as operações importantes** com structlog

### ❌ DON'T

- **Não implemente lógica de negócio** em steps de UI
- **Não use `if`/`else` complexos** em validações - use Pydantic
- **Não faça detecção de hardware** diretamente em steps
- **Não esqueça de implementar** `get_data()` e `set_data()`
- **Não hardcode valores** - use `settings` quando possível

## Debugging

### Logs Estruturados

O WizardService já possui logging integrado:

```python
import structlog
log = structlog.get_logger()

# Logs aparecem como:
# wizard_service.detect_cameras.complete count=2 indices=[0, 1]
```

### Inspecionar Wizard Data

```python
# No final do wizard
wizard_data = wizard_dialog.wizard_data
print(wizard_data)  # Dict completo com dados de todos os steps
```

### Mode Debugging

Para testar o wizard em modo avançado diretamente:

```python
# wizard_dialog.py
wizard = WizardDialog(
    parent=root,
    controller=controller,
    wizard_mode="advanced",  # Força modo avançado
    project_type="live"
)
```

## Referências

- [CLAUDE.md](../../../CLAUDE.md) - Instruções gerais do projeto
- [Operational reference](../../reference/operational_reference.md) - Comportamentos e parâmetros atuais
- [Testing (Windows GUI)](testing_gui_windows.md) - Guia de testes
- [Architecture](../../explanation/architecture.md) - Contexto arquitetural
- [Pydantic v2 Docs](https://docs.pydantic.dev/latest/) - Validação de dados
