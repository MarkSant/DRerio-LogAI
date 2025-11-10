# Agent Instructions - Phase 2 (SEQUENCIAL)

**📌 ORDEM OBRIGATÓRIA: Agent-6 → Agent-7 → Agent-8 (um de cada vez)**

## 📋 Visão Geral
- **Grupo de Execução**: Phase 2 (God Object Extraction)
- **Número de Agentes**: 3 (DEVEM executar sequencialmente)
- **Dependências**: Phase 1 concluída e merged
- **Branch**: `refactor/phase-2-god-object-extraction`
- **Duração**: 2 semanas (Week 3-4)

## ⚠️ PRÉ-REQUISITO OBRIGATÓRIO

```bash
# 1. Verifique que Phase 1 foi merged
git checkout main
git pull origin main
git log --oneline | grep "Phase 1"

# 2. Crie nova branch para Phase 2
git checkout -b refactor/phase-2-god-object-extraction
git push -u origin refactor/phase-2-god-object-extraction
```

---

## 🤖 AGENT-6: Extract DialogManager (P2-T1)

### 📌 Contexto
Você é o **Agent-6** responsável por extrair todos os métodos relacionados a diálogos de `MainViewModel` (5,383 linhas) para um novo `DialogManager`.

### 🎯 Objetivo
Reduzir `MainViewModel` em ~800 linhas extraindo 15-20 métodos de diálogo para `ui/dialog_manager.py`.

### 📂 Acesso ao Repositório
```bash
git clone https://github.com/MarkSant/ZebTrack-AI.git
cd ZebTrack-AI
git checkout refactor/phase-2-god-object-extraction
git pull origin refactor/phase-2-god-object-extraction

poetry install
poetry shell
```

### 📖 Documentação Detalhada

1. **PLANO_REFATORACAO_PARALELA_PARTE2.md**
   - Seção: "P2-T1: Extract DialogManager (Agent-6)"
   - Linhas: ~50-200

2. **docs/archive/DIALOG_MANAGER_EXTRACTION.md** (archived - completed migration)
   - Template completo para extração (historical reference)

### 🛠️ Implementação

#### Passo 1: Criar DialogManager
Crie `src/zebtrack/ui/dialog_manager.py`:

```python
"""
Dialog management service for ZebTrack-AI.

Centralizes all dialog creation and user interaction flows,
extracted from MainViewModel to reduce God Object complexity.
"""

import tkinter as tk
from tkinter import messagebox, filedialog
from pathlib import Path
from typing import Optional
import structlog

logger = structlog.get_logger(__name__)


class DialogManager:
    """
    Manages all application dialogs and user interactions.

    Extracted from MainViewModel (P2-T1) to reduce coupling and
    improve testability of dialog flows.

    Args:
        root: Tkinter root window
        settings_obj: Application settings
    """

    def __init__(self, root: tk.Tk, settings_obj):
        self._root = root
        self._settings = settings_obj
        logger.info("dialog_manager.initialized")

    def show_error(self, title: str, message: str) -> None:
        """Show error message dialog."""
        logger.warning("dialog.error.shown", title=title, message=message)
        messagebox.showerror(title, message, parent=self._root)

    def show_info(self, title: str, message: str) -> None:
        """Show information dialog."""
        logger.info("dialog.info.shown", title=title)
        messagebox.showinfo(title, message, parent=self._root)

    def show_warning(self, title: str, message: str) -> None:
        """Show warning dialog."""
        logger.warning("dialog.warning.shown", title=title)
        messagebox.showwarning(title, message, parent=self._root)

    def ask_yes_no(self, title: str, message: str) -> bool:
        """
        Ask yes/no question.

        Returns:
            True if user clicked Yes, False otherwise
        """
        result = messagebox.askyesno(title, message, parent=self._root)
        logger.info("dialog.yes_no.answered", title=title, result=result)
        return result

    def ask_ok_cancel(self, title: str, message: str) -> bool:
        """
        Ask OK/Cancel question.

        Returns:
            True if user clicked OK, False otherwise
        """
        result = messagebox.askokcancel(title, message, parent=self._root)
        logger.info("dialog.ok_cancel.answered", title=title, result=result)
        return result

    def select_file(
        self,
        title: str = "Select File",
        filetypes: Optional[list[tuple[str, str]]] = None,
        initial_dir: Optional[str] = None
    ) -> Optional[Path]:
        """
        Show file selection dialog.

        Args:
            title: Dialog title
            filetypes: List of (description, pattern) tuples
            initial_dir: Initial directory

        Returns:
            Selected file path or None if cancelled
        """
        if filetypes is None:
            filetypes = [("All files", "*.*")]

        if initial_dir is None:
            initial_dir = str(Path.home())

        filepath = filedialog.askopenfilename(
            title=title,
            filetypes=filetypes,
            initialdir=initial_dir,
            parent=self._root
        )

        if filepath:
            path = Path(filepath)
            logger.info("dialog.file_selected", path=str(path))
            return path

        logger.info("dialog.file_selection_cancelled")
        return None

    def select_directory(
        self,
        title: str = "Select Directory",
        initial_dir: Optional[str] = None
    ) -> Optional[Path]:
        """
        Show directory selection dialog.

        Args:
            title: Dialog title
            initial_dir: Initial directory

        Returns:
            Selected directory path or None if cancelled
        """
        if initial_dir is None:
            initial_dir = str(Path.home())

        dirpath = filedialog.askdirectory(
            title=title,
            initialdir=initial_dir,
            parent=self._root
        )

        if dirpath:
            path = Path(dirpath)
            logger.info("dialog.directory_selected", path=str(path))
            return path

        logger.info("dialog.directory_selection_cancelled")
        return None

    def select_save_file(
        self,
        title: str = "Save File",
        default_extension: str = ".txt",
        filetypes: Optional[list[tuple[str, str]]] = None,
        initial_dir: Optional[str] = None
    ) -> Optional[Path]:
        """
        Show save file dialog.

        Args:
            title: Dialog title
            default_extension: Default file extension
            filetypes: List of (description, pattern) tuples
            initial_dir: Initial directory

        Returns:
            Save file path or None if cancelled
        """
        if filetypes is None:
            filetypes = [("All files", "*.*")]

        if initial_dir is None:
            initial_dir = str(Path.home())

        filepath = filedialog.asksaveasfilename(
            title=title,
            defaultextension=default_extension,
            filetypes=filetypes,
            initialdir=initial_dir,
            parent=self._root
        )

        if filepath:
            path = Path(filepath)
            logger.info("dialog.save_file_selected", path=str(path))
            return path

        logger.info("dialog.save_file_cancelled")
        return None
```

#### Passo 2: Integrar no MainViewModel
Edite `src/zebtrack/ui/gui.py`:

```python
from zebtrack.ui.dialog_manager import DialogManager

class MainViewModel:
    def __init__(
        self,
        root: tk.Tk,
        # ... outros parametros ...
    ):
        # ... código existente ...

        # Injetar DialogManager
        self.dialog_manager = DialogManager(root, settings_obj)

        logger.info("main_view_model.initialized")
```

#### Passo 3: Substituir Chamadas de Diálogo
Edite `src/zebtrack/ui/gui.py` - substitua todas as chamadas diretas:

**ANTES:**
```python
messagebox.showerror("Error", "Failed to load project", parent=self.root)
```

**DEPOIS:**
```python
self.dialog_manager.show_error("Error", "Failed to load project")
```

#### Passo 4: Criar Testes
Crie `tests/test_dialog_manager.py`:

```python
"""Test DialogManager."""

import pytest
from unittest.mock import Mock, patch
from zebtrack.ui.dialog_manager import DialogManager


class TestDialogManager:
    """Test dialog manager functionality."""

    @pytest.fixture
    def dialog_manager(self):
        """Create DialogManager instance."""
        root = Mock()
        settings = Mock()
        return DialogManager(root, settings)

    def test_show_error(self, dialog_manager):
        """show_error displays error dialog."""
        with patch('tkinter.messagebox.showerror') as mock_error:
            dialog_manager.show_error("Test Error", "Error message")
            mock_error.assert_called_once()

    def test_ask_yes_no_returns_bool(self, dialog_manager):
        """ask_yes_no returns boolean result."""
        with patch('tkinter.messagebox.askyesno', return_value=True):
            result = dialog_manager.ask_yes_no("Test", "Question?")
            assert result is True
```

#### Passo 5: Validar
```bash
# Teste DialogManager
poetry run pytest tests/test_dialog_manager.py -v

# Teste integração MainViewModel
poetry run pytest tests/test_gui.py -m gui -n0 -v

# Verifique redução de linhas
wc -l src/zebtrack/ui/gui.py  # Deve ser < 5383
```

#### Passo 6: Commit
```bash
git add src/zebtrack/ui/dialog_manager.py src/zebtrack/ui/gui.py tests/test_dialog_manager.py

git commit -m "refactor(ui): Extract DialogManager from MainViewModel (P2-T1)

- Create DialogManager with 10+ dialog methods
- Reduce MainViewModel by ~800 lines
- Centralize all user interaction flows
- Improve testability of dialogs
- Add comprehensive unit tests

Phase: 2
Task: P2-T1
Agent: Agent-6"

git push origin refactor/phase-2-god-object-extraction
```

### ✅ Critérios de Sucesso
- [ ] `DialogManager` criado com 10+ métodos
- [ ] `MainViewModel` reduzido em ~800 linhas
- [ ] Todas as chamadas de diálogo refatoradas
- [ ] Testes criados (mínimo 5 testes)
- [ ] Todos os testes passando
- [ ] Zero erros Ruff

### ⏱️ Estimativa: ~3-4 horas

---

## 🤖 AGENT-7: Extract ProjectWorkflowAdapter (P2-T2)

### 📌 Contexto
**⚠️ AGUARDE Agent-6 CONCLUIR antes de iniciar**

Você é o **Agent-7** responsável por extrair lógica de workflow de projetos para `ProjectWorkflowAdapter`.

### 🎯 Objetivo
Reduzir `MainViewModel` em ~600 linhas extraindo métodos de projeto/wizard.

### 📖 Documentação
**PLANO_REFATORACAO_PARALELA_PARTE2.md** - Seção P2-T2

### 🛠️ Implementação Resumida

1. **Criar** `src/zebtrack/ui/project_workflow_adapter.py`
2. **Extrair** métodos: `start_wizard()`, `load_project()`, `save_project()`, etc.
3. **Integrar** em `MainViewModel`
4. **Testar** workflows completos
5. **Commit e push**

### ⏱️ Estimativa: ~3-4 horas

---

## 🤖 AGENT-8: Extract AnalysisCoordinator (P2-T3)

### 📌 Contexto
**⚠️ AGUARDE Agent-7 CONCLUIR antes de iniciar**

Você é o **Agent-8** responsável por extrair coordenação de análise para `AnalysisCoordinator`.

### 🎯 Objetivo
Reduzir `MainViewModel` em ~500 linhas extraindo métodos de análise.

### 📖 Documentação
**PLANO_REFATORACAO_PARALELA_PARTE2.md** - Seção P2-T3

### 🛠️ Implementação Resumida

1. **Criar** `src/zebtrack/core/analysis_coordinator.py`
2. **Extrair** métodos: `run_analysis()`, `generate_reports()`, `compute_metrics()`
3. **Integrar** em `MainViewModel`
4. **Testar** análise completa
5. **Commit e push**

### ⏱️ Estimativa: ~3-4 horas

---

## 📊 Resumo Phase 2

### Execução Sequencial OBRIGATÓRIA
```
Agent-6 (P2-T1) → CONCLUIR → Agent-7 (P2-T2) → CONCLUIR → Agent-8 (P2-T3)
```

### Resultado Final
- **MainViewModel**: 5,383 → ~3,400 linhas (~1,900 linhas removidas)
- **Novos serviços**: 3 (DialogManager, ProjectWorkflowAdapter, AnalysisCoordinator)
- **Cobertura de testes**: +15 testes mínimo

### Comunicação de Conclusão
```
✅ PHASE 2 CONCLUÍDA

Reduções:
- MainViewModel: 5,383 → 3,400 linhas (-36%)

Novos Serviços:
- DialogManager (800 linhas)
- ProjectWorkflowAdapter (600 linhas)
- AnalysisCoordinator (500 linhas)

Branch: refactor/phase-2-god-object-extraction
Próximo: Merge para main e iniciar Phase 3
```

---

**Início**: ___________
**Conclusão**: ___________
**Status**: [ ] Não Iniciado | [ ] Em Progresso | [ ] Concluído
