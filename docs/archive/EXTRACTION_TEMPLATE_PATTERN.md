# PADRÃO DE EXTRAÇÃO PARA NOVOS COMPONENTES

Use este padrão ao criar DialogManager, ValidationManager, WidgetFactory e ProjectViewManager.

## Template Base (copiar de MenuManager/CanvasManager)

```python
"""[ComponentName] for ApplicationGUI.

Extracted from gui.py to reduce God Object complexity.
Handles [brief description of responsibility].
"""

import structlog

log = structlog.get_logger()


class [ComponentName]:
    """Manages [responsibility] for ApplicationGUI."""

    def __init__(self, gui):
        """Initialize [ComponentName].

        Args:
            gui: Reference to ApplicationGUI instance
        """
        self.gui = gui
        # Component-specific attributes here
        self._some_state = None

    # =========================================================================
    # [SECTION NAME]
    # =========================================================================

    def method_name(self):
        """Brief description."""
        # Implementation
        pass
```

## Dependência Injection Pattern

```python
# Em gui.py __init__, adicione:
class ApplicationGUI:
    def __init__(self, ...):
        # ... existing code ...

        # Create component managers
        self.dialog_manager = DialogManager(self)
        self.validation_manager = ValidationManager(self)
        self.widget_factory = WidgetFactory(self)
        self.project_view_manager = ProjectViewManager(self)

        # ... rest of initialization ...
```

## Como Refatorar Métodos Existentes

### EXEMPLO 1: Extrair Método Completo (DialogManager)

**Antes (em gui.py):**
```python
def show_error(self, title, message):
    """Shows an error message box."""
    messagebox.showerror(title, message)
```

**Depois (em dialog_manager.py):**
```python
def show_error(self, title, message):
    """Shows an error message box."""
    messagebox.showerror(title, message)
```

**Depois (em gui.py - update call):**
```python
# OLD: messagebox.showerror(title, message)
# NEW:
self.dialog_manager.show_error(title, message)
```

### EXEMPLO 2: Extrair Lógica Parcial (ValidationManager)

**Antes (em gui.py):**
```python
def _on_auto_detect_clicked(self, stabilization_frames: int | str | None = None):
    """Handler for the auto-detect button."""
    if self.analysis_active:
        self.show_warning(...)
        return

    raw_value = stabilization_frames or self.stabilization_frames_var.get()

    try:
        stabilization_frames_int = int(raw_value)
        if stabilization_frames_int <= 0:
            raise ValueError
    except (ValueError, TypeError):
        self.show_warning("Entrada Inválida", "...")
        return

    # Continue with analysis...
```

**Depois (em validation_manager.py - extract validation):**
```python
def validate_positive_integer(self, value: int | str | None,
                             field_name: str) -> int | None:
    """Validate that value is a positive integer.

    Returns None if invalid (showing warning automatically).
    Returns the validated integer if valid.
    """
    try:
        int_value = int(value) if value else 0
        if int_value <= 0:
            raise ValueError(f"{field_name} deve ser positivo")
        return int_value
    except (ValueError, TypeError) as e:
        self.gui.show_warning(
            "Entrada Inválida",
            f"{field_name}: {str(e)}"
        )
        return None
```

**Depois (em gui.py - simplified call):**
```python
def _on_auto_detect_clicked(self, stabilization_frames: int | str | None = None):
    """Handler for the auto-detect button."""
    if self.analysis_active:
        self.show_warning(...)
        return

    raw_value = stabilization_frames or self.stabilization_frames_var.get()

    # Use validation manager
    frames = self.validation_manager.validate_positive_integer(
        raw_value,
        "Número de frames para análise"
    )
    if frames is None:
        return

    # Continue with analysis...
```

### EXEMPLO 3: Extrair Método com Dependências (WidgetFactory)

**Antes (em gui.py):**
```python
def _create_main_controls_tab(self):
    """Creates the tab with the main project controls."""
    self.main_controls_frame = ttk.Frame(self.notebook, padding="10")
    self.notebook.add(self.main_controls_frame, text="Controle Principal")

    project_type = self.controller.project_manager.get_project_type()

    controls_container = ttk.Frame(self.main_controls_frame)
    controls_container.pack(fill="x", pady=(0, 10))

    if project_type == "live":
        # ... create live controls ...
    elif project_type == "pre-recorded":
        # ... create pre-recorded controls ...
```

**Depois (em widget_factory.py):**
```python
def create_main_controls_tab(self):
    """Creates the tab with the main project controls."""
    self.gui.main_controls_frame = ttk.Frame(self.gui.notebook, padding="10")
    self.gui.notebook.add(self.gui.main_controls_frame, text="Controle Principal")

    project_type = self.gui.controller.project_manager.get_project_type()

    controls_container = ttk.Frame(self.gui.main_controls_frame)
    controls_container.pack(fill="x", pady=(0, 10))

    if project_type == "live":
        self._create_live_controls(controls_container)
    elif project_type == "pre-recorded":
        self._create_pre_recorded_controls(controls_container)
```

**Depois (em gui.py - call in __init__ or setup):**
```python
# In _create_main_control_frame() or wherever it's called:
self.widget_factory.create_main_controls_tab()
```

## Testes para Cada Componente

```python
# tests/test_dialog_manager.py
import pytest
from zebtrack.ui.components.dialog_manager import DialogManager

class TestDialogManager:
    def test_show_error_calls_messagebox(self, mocker):
        gui_mock = mocker.Mock()
        manager = DialogManager(gui_mock)

        mock_showerror = mocker.patch("tkinter.messagebox.showerror")
        manager.show_error("Test", "Message")

        mock_showerror.assert_called_once_with("Test", "Message")
```

## Checklist para Extração

- [ ] Criar novo arquivo em `src/zebtrack/ui/components/[component_name].py`
- [ ] Copiar template base com docstring adequada
- [ ] Extrair métodos de gui.py para novo componente
- [ ] Atualizar todas as referências `self.method()` para `self.component.method()`
- [ ] Adicionar injeção de dependência em gui.py `__init__`
- [ ] Executar testes: `pytest -xvs tests/test_[component_name].py`
- [ ] Executar linting: `ruff check src/zebtrack/ui/components/`
- [ ] Verificar que gui.py linhas diminuíram
- [ ] Atualizar `__init__.py` em `ui/components/` se necessário
- [ ] Testar aplicação: `poetry run zebtrack`

## Ordem de Execução Recomendada

1. **ValidationManager** (PRIMEIRO)
   - Sem dependências
   - Base para outros componentes

2. **DialogManager** (SEGUNDO)
   - Usa ValidationManager
   - Padrão direto (wrapper para tkinter)

3. **WidgetFactory** (TERCEIRO)
   - Usa ValidationManager e DialogManager
   - Maior volume de código

4. **ProjectViewManager** (QUARTO)
   - Usa ValidationManager
   - Bastante independente

## Documentação no Componente

Cada componente deve ter:

```python
"""[ComponentName] for ApplicationGUI.

Extracted from gui.py to reduce God Object complexity.
Handles [specific responsibility].

This component manages [list of what it does]:
- Feature 1
- Feature 2
- Feature 3

Methods are organized into logical sections with clear separation of concerns.
"""
```

## Atributos de Referência

Sempre armazene referência ao gui:

```python
class [ComponentName]:
    def __init__(self, gui):
        self.gui = gui  # Always keep this

    def some_method(self):
        # Access gui's attributes like this:
        self.gui.controller
        self.gui.root
        self.gui.notebook
        # etc.
```

## Pattern: Batch Operations

Se o método faz múltiplas operações relacionadas:

```python
def handle_roi_import_workflow(self, file_path: str) -> dict | None:
    """Complete workflow: validate → import → save → update UI.

    Returns the result dict or None if failed.
    """
    # 1. Validate input
    if not self.validation_manager.validate_file_exists(file_path):
        self.gui.dialog_manager.show_error(...)
        return None

    # 2. Load data
    data = self._load_template_file(file_path)
    if not data:
        return None

    # 3. Save to project
    self._save_to_project(data)

    # 4. Update UI
    self.gui.project_view_manager.refresh_templates()

    # 5. Confirm to user
    self.gui.dialog_manager.show_info("Success", "...")

    return data
```
