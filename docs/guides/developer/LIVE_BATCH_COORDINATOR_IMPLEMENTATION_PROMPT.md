# 🚀 LiveBatchCoordinator v2.3.0 - Implementation Prompt

## 📋 Context

**Project**: ZebTrack-AI (DRerio LogAI)
**Current Version**: v2.2.0
**Target Version**: v2.3.0
**Base Commit**: Current main branch
**Primary Language**: Python 3.12+
**Framework**: Tkinter (desktop GUI)

---

## 🎯 Mission Overview

Implement **two major features** for experimental workflow management:

### Feature 1: LiveBatchCoordinator Integration

Activate the existing `LiveBatchCoordinator` implementation to enable unified batch reporting across multiple live camera sessions.

### Feature 2: Experiment Progress Dashboard

Create an interactive UI in the existing "Progresso do Experimento" tab where users can:

- Click on Day/Group blocks to see session details
- Select subjects (cobaias) for new sessions
- Track what has been done vs. planned
- Manage experimental workflow visually

---

## 📚 Required Reading (MANDATORY)

Before starting, read these documents in order:

1. **Architecture**:
   - `.github/copilot-instructions.md` - Agent playbook and quick navigation
   - `docs/architecture/ARCHITECTURE.md` - System overview
   - `docs/architecture/DEPENDENCY_INJECTION_GUIDE.md` - DI patterns

2. **LiveBatchCoordinator Context**:
   - `docs/decisions/ADR-006-live-batch-coordinator-future.md` - Why it was deferred
   - `src/zebtrack/coordinators/live_batch_coordinator.py` - Existing implementation (433 lines)
   - `tests/test_live_camera_workflow_e2e.py` (lines 197-240) - E2E tests

3. **UI & Workflow**:
   - `src/zebtrack/ui/gui.py` - MainWindow structure
   - `src/zebtrack/ui/wizard/wizard_dialog.py` - Wizard flow
   - `src/zebtrack/coordinators/session_coordinator.py` - Session lifecycle

4. **Validation Report**:
   - `docs/guides/developer/LIVE_CAMERA_V2.2_VALIDATION_REPORT.md` - Current state

---

## 🔧 Feature 1: LiveBatchCoordinator Integration

### Current State

**✅ Already Implemented**:

- Complete implementation in `src/zebtrack/coordinators/live_batch_coordinator.py` (433 lines)
- Batch tracking logic with `BatchMetadata` dataclass
- Unified report generation via `AnalysisService`
- E2E tests passing (2/2 in `test_live_camera_workflow_e2e.py`)
- Event `BATCH_ANALYSIS_COMPLETED` defined in `UIEvents` enum
- Handler `_on_batch_analysis_completed()` ready in `UICoordinator`

**❌ Not Integrated**:

- Never instantiated in `src/zebtrack/__main__.py` (Composition Root)
- Wizard doesn't collect batch metadata (`group`, `day`, `subject_id`)
- No UI to mark batch completion or trigger reports
- Events never published (dormant code)

### Implementation Tasks

#### Task 1.1: Extend Wizard - Add Experimental Metadata Fields

**File**: `src/zebtrack/ui/wizard/live_config_step.py`

**Add to `__init__()` (around line 85)**:

```python
# Experimental design metadata (v2.3.0)
self.experimental_group_var = StringVar(value="")  # "Controle", "Tratado", etc.
self.experiment_day_var = StringVar(value="")      # "Dia_1", "Dia_2", etc.
self.subject_id_var = StringVar(value="")          # "Peixe_01", "Peixe_02", etc.
self.is_batch_last_session_var = BooleanVar(value=False)  # Mark as final session
```

**Add to `build_ui()` (create new section after recording settings)**:

```python
# === Experimental Design Section ===
experiment_frame = LabelFrame(self, text="Design Experimental (Opcional)",
                              font=("Segoe UI", 10, "bold"))
experiment_frame.pack(fill="x", padx=10, pady=5)

# Group field
Label(experiment_frame, text="Grupo Experimental:").grid(row=0, column=0, sticky="w", padx=5, pady=3)
group_combo = ttk.Combobox(
    experiment_frame,
    textvariable=self.experimental_group_var,
    values=["Controle", "Tratado", "CBD_10mg", "CBD_20mg", "Outro"],
    width=25
)
group_combo.grid(row=0, column=1, sticky="ew", padx=5, pady=3)

# Day field
Label(experiment_frame, text="Dia do Experimento:").grid(row=1, column=0, sticky="w", padx=5, pady=3)
day_combo = ttk.Combobox(
    experiment_frame,
    textvariable=self.experiment_day_var,
    values=[f"Dia_{i}" for i in range(1, 15)],
    width=25
)
day_combo.grid(row=1, column=1, sticky="ew", padx=5, pady=3)

# Subject ID field
Label(experiment_frame, text="ID do Sujeito (Cobaia):").grid(row=2, column=0, sticky="w", padx=5, pady=3)
subject_entry = Entry(experiment_frame, textvariable=self.subject_id_var, width=27)
subject_entry.grid(row=2, column=1, sticky="ew", padx=5, pady=3)
ToolTip(subject_entry, "Ex: Peixe_01, Animal_A, etc.")

# Batch completion checkbox
batch_check = Checkbutton(
    experiment_frame,
    text="Marcar como última sessão deste lote (gera relatório unificado)",
    variable=self.is_batch_last_session_var
)
batch_check.grid(row=3, column=0, columnspan=2, sticky="w", padx=5, pady=5)

experiment_frame.columnconfigure(1, weight=1)
```

**Update `gather_data()` to include new fields**:

```python
def gather_data(self) -> dict:
    """Gather step data including experimental metadata."""
    data = {
        # ... existing fields ...

        # v2.3.0: Experimental design metadata
        "experimental_group": self.experimental_group_var.get() or None,
        "experiment_day": self.experiment_day_var.get() or None,
        "subject_id": self.subject_id_var.get() or None,
        "is_batch_last_session": self.is_batch_last_session_var.get(),
    }
    return data
```

**Validation** (optional but recommended):

```python
def validate(self) -> tuple[bool, str]:
    """Validate live config settings."""
    # ... existing validation ...

    # If batch fields are filled, all must be present
    group = self.experimental_group_var.get()
    day = self.experiment_day_var.get()
    subject_id = self.subject_id_var.get()

    batch_fields_count = sum([bool(group), bool(day), bool(subject_id)])
    if 0 < batch_fields_count < 3:
        return False, "Para rastreamento de lote, preencha Grupo, Dia e ID do Sujeito"

    return True, ""
```

---

#### Task 1.2: Instantiate LiveBatchCoordinator in Composition Root

**File**: `src/zebtrack/__main__.py`

**Location**: Composition Root (around lines 140-280)

**Add after creating `session_coordinator` (around line 230)**:

```python
# ============================================================================
# LiveBatchCoordinator - Unified batch reporting (v2.3.0)
# ============================================================================
from zebtrack.coordinators.live_batch_coordinator import LiveBatchCoordinator

live_batch_coordinator = LiveBatchCoordinator(
    project_manager=project_manager,
    analysis_service=analysis_service,
    state_manager=state_manager,
    settings_obj=settings_obj,
    event_bus=event_bus if settings_obj.ui_features.enable_event_queue else None,
)

log.info(
    "composition_root.live_batch_coordinator_initialized",
    has_event_bus=live_batch_coordinator.event_bus is not None,
)
```

**Pass to SessionCoordinator constructor** (around line 240):

```python
session_coordinator = SessionCoordinator(
    project_manager=project_manager,
    # ... other dependencies ...
    live_batch_coordinator=live_batch_coordinator,  # ← ADD THIS
)
```

**Update SessionCoordinator signature** in `src/zebtrack/coordinators/session_coordinator.py`:

```python
def __init__(
    self,
    # ... existing parameters ...
    live_batch_coordinator: LiveBatchCoordinator | None = None,
):
    # ... existing init ...
    self.live_batch_coordinator = live_batch_coordinator
```

---

#### Task 1.3: Register Sessions in SessionCoordinator

**File**: `src/zebtrack/coordinators/session_coordinator.py`

**Update `_on_live_session_complete()` method** (around line 150):

```python
def _on_live_session_complete(self, output_dir: Path):
    """Handle live session completion - triggers analysis and batch tracking."""
    log.info("session_coordinator.live_session_complete", output_dir=str(output_dir))

    try:
        # 1. Run individual analysis (existing)
        self._trigger_post_analysis(output_dir)

        # 2. Register session for batch tracking (v2.3.0)
        if self.live_batch_coordinator and self.current_experiment_id:
            video_path = self._find_video_in_output_dir(output_dir)

            # Extract metadata from wizard_data
            metadata = {
                "group": self.wizard_data.get("experimental_group"),
                "day": self.wizard_data.get("experiment_day"),
                "subject_id": self.wizard_data.get("subject_id"),
                "timestamp": datetime.now().isoformat(),
                "duration_s": self.wizard_data.get("recording_duration_s"),
                "camera_index": self.wizard_data.get("camera_index"),
            }

            # Only register if batch metadata is present
            if all([metadata["group"], metadata["day"], metadata["subject_id"]]):
                batch_id = self.live_batch_coordinator.register_session(
                    experiment_id=self.current_experiment_id,
                    video_path=video_path,
                    metadata=metadata,
                )

                log.info(
                    "session_coordinator.batch_session_registered",
                    batch_id=batch_id,
                    group=metadata["group"],
                    day=metadata["day"],
                    subject_id=metadata["subject_id"],
                )

                # Check if user marked as last session
                if self.wizard_data.get("is_batch_last_session"):
                    log.info("session_coordinator.batch_marked_complete", batch_id=batch_id)
                    self.live_batch_coordinator.mark_batch_complete(batch_id)
            else:
                log.debug(
                    "session_coordinator.batch_metadata_incomplete",
                    metadata=metadata,
                )

        # 3. Cleanup
        self.current_experiment_id = None

    except Exception as e:
        log.error(
            "session_coordinator.live_session_complete_failed",
            error=str(e),
            exc_info=True,
        )
```

**Add helper method**:

```python
def _find_video_in_output_dir(self, output_dir: Path) -> Path:
    """Find video file in output directory."""
    video_extensions = [".mp4", ".avi", ".mkv"]
    for ext in video_extensions:
        video_files = list(output_dir.glob(f"*{ext}"))
        if video_files:
            return video_files[0]

    # Fallback: return expected path
    return output_dir / "live_recording.mp4"
```

---

#### Task 1.4: Update UICoordinator Handler

**File**: `src/zebtrack/ui/ui_coordinator.py`

**Update `_on_batch_analysis_completed()` handler** (around line 699):

```python
def _on_batch_analysis_completed(self, data: dict):
    """Handle batch analysis completion - show success notification."""
    batch_id = data.get("batch_id")
    report_path = data.get("report_path")
    session_count = data.get("session_count", 0)

    log.info(
        "ui_coordinator.batch_analysis_completed",
        batch_id=batch_id,
        report_path=report_path,
        session_count=session_count,
    )

    # Schedule UI update on main thread
    def _show_notification():
        try:
            from tkinter import messagebox

            message = (
                f"✅ Relatório de Lote Gerado!\n\n"
                f"Lote: {batch_id}\n"
                f"Sessões: {session_count}\n\n"
                f"Relatório salvo em:\n{report_path}"
            )

            messagebox.showinfo(
                title="Análise de Lote Completa",
                message=message,
            )

            # Open file explorer to report location
            if report_path and Path(report_path).exists():
                import subprocess
                import platform

                if platform.system() == "Windows":
                    subprocess.run(["explorer", "/select,", str(report_path)])
                elif platform.system() == "Darwin":  # macOS
                    subprocess.run(["open", "-R", str(report_path)])
                else:  # Linux
                    subprocess.run(["xdg-open", str(Path(report_path).parent)])

        except Exception as e:
            log.error("ui_coordinator.batch_notification_failed", error=str(e))

    if self.root:
        self.root.after(0, _show_notification)
```

---

#### Task 1.5: Testing LiveBatchCoordinator Integration

**Run existing tests**:

```bash
# Tests should already pass (they're isolated)
poetry run pytest tests/test_live_camera_workflow_e2e.py::TestLiveBatchCoordinator -xvs
```

**Add integration smoke test** in `tests/test_live_batch_integration.py`:

```python
"""Integration tests for LiveBatchCoordinator with wizard workflow."""
import pytest
from pathlib import Path
from zebtrack.coordinators.live_batch_coordinator import LiveBatchCoordinator
from zebtrack.coordinators.session_coordinator import SessionCoordinator


def test_wizard_to_batch_coordinator_flow(
    mock_project_manager,
    mock_analysis_service,
    mock_state_manager,
    mock_settings,
):
    """Test complete flow from wizard metadata to batch report."""
    # Setup
    batch_coord = LiveBatchCoordinator(
        project_manager=mock_project_manager,
        analysis_service=mock_analysis_service,
        state_manager=mock_state_manager,
        settings_obj=mock_settings,
    )

    # Simulate 3 sessions from wizard
    wizard_sessions = [
        {
            "experimental_group": "Controle",
            "experiment_day": "Dia_1",
            "subject_id": "Peixe_01",
            "is_batch_last_session": False,
        },
        {
            "experimental_group": "Controle",
            "experiment_day": "Dia_1",
            "subject_id": "Peixe_02",
            "is_batch_last_session": False,
        },
        {
            "experimental_group": "Controle",
            "experiment_day": "Dia_1",
            "subject_id": "Peixe_03",
            "is_batch_last_session": True,  # ← Last session
        },
    ]

    batch_ids = []
    for session in wizard_sessions:
        batch_id = batch_coord.register_session(
            experiment_id=f"exp_{session['subject_id']}",
            video_path=Path(f"data/{session['subject_id']}.mp4"),
            metadata=session,
        )
        batch_ids.append(batch_id)

    # Assert: All sessions in same batch
    assert len(set(batch_ids)) == 1, "All sessions should have same batch_id"

    # Mark batch complete
    batch_coord.mark_batch_complete(batch_ids[0])

    # Assert: Batch marked complete
    batch = batch_coord._active_batches.get("Controle_Dia_1_*")
    assert batch is not None
    assert batch.is_complete
    assert batch.session_count == 3

    # Assert: Analysis service called with correct sessions
    mock_analysis_service.generate_unified_report.assert_called_once()
```

---

## 🎨 Feature 2: Experiment Progress Dashboard

### Requirements Overview

Create an interactive **"Progresso do Experimento"** tab that:

1. **Visual Grid Layout**: Display Day × Group matrix
2. **Interactive Blocks**: Click blocks to see details/take actions
3. **Subject Selection**: Choose which cobaia to test next
4. **Status Tracking**: Show completed vs. pending sessions
5. **Quick Actions**: Start session, view results, generate reports

### UI Mockup (Text-Based)

```text
┌─────────────────────────────────────────────────────────────────────┐
│  Progresso do Experimento                                      [📊] │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  Experimento: Teste Canabidiol - Janeiro 2026                      │
│  Período: 7 dias | Grupos: 2 | Cobaias: 10 (5 por grupo)          │
│                                                                     │
│  ┌────────┬───────────────────┬───────────────────┐                │
│  │        │  Grupo Controle   │  Grupo Tratado    │                │
│  ├────────┼───────────────────┼───────────────────┤                │
│  │ Dia 1  │ [✅ 5/5] 09:00   │ [⏳ 3/5] 10:30   │ ← Click me!    │
│  │        │ Completo          │ Em andamento      │                │
│  ├────────┼───────────────────┼───────────────────┤                │
│  │ Dia 2  │ [⏳ 2/5] 09:00   │ [⏸️ 0/5] Pendente│                │
│  │        │ Em andamento      │                   │                │
│  ├────────┼───────────────────┼───────────────────┤                │
│  │ Dia 3  │ [⏸️ 0/5] Pendente│ [⏸️ 0/5] Pendente│                │
│  └────────┴───────────────────┴───────────────────┘                │
│                                                                     │
│  🔍 Legenda:                                                        │
│  ✅ Completo | ⏳ Em andamento | ⏸️ Pendente | ❌ Com erro          │
│                                                                     │
│  [➕ Adicionar Dia]  [📊 Relatório Geral]  [⚙️ Configurações]      │
└─────────────────────────────────────────────────────────────────────┘
```

### When User Clicks Block (e.g., "Dia 1 - Grupo Tratado")

```text
┌─────────────────────────────────────────────────────────────────────┐
│  Sessões: Dia 1 - Grupo Tratado                            [✖️]     │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  📊 Progresso: 3/5 sessões completas                                │
│  ⏱️ Próxima sessão: Peixe_04                                       │
│                                                                     │
│  ┌─ Cobaias ────────────────────────────────────────────────────┐  │
│  │                                                               │  │
│  │  [✅] Peixe_01  │ 09:00-09:05 | 5min | Ver Resultados       │  │
│  │  [✅] Peixe_02  │ 09:15-09:20 | 5min | Ver Resultados       │  │
│  │  [✅] Peixe_03  │ 09:30-09:35 | 5min | Ver Resultados       │  │
│  │  [ ] Peixe_04   │ Pendente           | ▶️ Iniciar Sessão    │  │
│  │  [ ] Peixe_05   │ Pendente           | ⏸️ Pular             │  │
│  │                                                               │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  🛠️ Ações Rápidas:                                                 │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ [▶️ Iniciar Próxima Sessão (Peixe_04)]                      │   │
│  │ [📊 Gerar Relatório Parcial (3 sessões)]                    │   │
│  │ [📝 Adicionar Nota ao Dia/Grupo]                            │   │
│  │ [⚙️ Editar Configuração do Lote]                            │   │
│  │ [🗑️ Remover Sessão Com Erro]                                │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  📝 Notas do Experimento:                                          │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ - Água trocada antes das sessões                            │   │
│  │ - Temperatura: 26.5°C ±0.5°C                                │   │
│  │ - Todos animais alimentados 2h antes                        │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│          [Fechar]            [Marcar Lote Como Completo]           │
└─────────────────────────────────────────────────────────────────────┘
```

---

### Implementation Tasks - Progress Dashboard

#### Task 2.1: Create ExperimentProgressTab Widget

**New File**: `src/zebtrack/ui/tabs/experiment_progress_tab.py`

```python
"""Experiment progress dashboard tab for tracking live sessions.

Displays Day × Group matrix with interactive blocks for session management.

Architecture:
- Grid layout with clickable Day/Group blocks
- Click block → Opens BlockDetailDialog
- Tracks session status per subject (cobaia)
- Integrates with LiveBatchCoordinator for batch reporting

Version: 2.3.0
"""
from __future__ import annotations
from tkinter import *
from tkinter import ttk
from typing import TYPE_CHECKING
import structlog

if TYPE_CHECKING:
    from zebtrack.core.project_manager import ProjectManager
    from zebtrack.coordinators.session_coordinator import SessionCoordinator
    from zebtrack.coordinators.live_batch_coordinator import LiveBatchCoordinator
    from zebtrack.settings import Settings

log = structlog.get_logger(__name__)


class ExperimentProgressTab(Frame):
    """Experiment progress tracking dashboard."""

    def __init__(
        self,
        parent,
        project_manager: ProjectManager,
        session_coordinator: SessionCoordinator,
        live_batch_coordinator: LiveBatchCoordinator,
        settings_obj: Settings,
    ):
        super().__init__(parent)
        self.project_manager = project_manager
        self.session_coordinator = session_coordinator
        self.live_batch_coordinator = live_batch_coordinator
        self.settings = settings_obj

        # Data model
        self.experiment_data = {
            "name": "Novo Experimento",
            "days": [],      # List of day labels ["Dia_1", "Dia_2", ...]
            "groups": [],    # List of group names ["Controle", "Tratado", ...]
            "subjects": {},  # {group: [subject_ids]}
            "sessions": {},  # {(day, group, subject): session_metadata}
        }

        self.build_ui()
        self.load_experiment_data()

    def build_ui(self):
        """Build progress dashboard UI."""
        # Header
        header_frame = Frame(self, bg="#f0f0f0", height=80)
        header_frame.pack(fill="x", padx=10, pady=10)
        header_frame.pack_propagate(False)

        title_label = Label(
            header_frame,
            text="📊 Progresso do Experimento",
            font=("Segoe UI", 16, "bold"),
            bg="#f0f0f0",
        )
        title_label.pack(side="left", padx=10, pady=10)

        # Experiment info
        self.info_label = Label(
            header_frame,
            text="Experimento: -- | Período: -- | Grupos: --",
            font=("Segoe UI", 10),
            bg="#f0f0f0",
            fg="#555",
        )
        self.info_label.pack(side="left", padx=20, pady=10)

        # Grid container (scrollable)
        grid_container = Frame(self)
        grid_container.pack(fill="both", expand=True, padx=10, pady=10)

        # Canvas + Scrollbar for grid
        canvas = Canvas(grid_container, bg="white")
        scrollbar = ttk.Scrollbar(grid_container, orient="vertical", command=canvas.yview)

        self.grid_frame = Frame(canvas, bg="white")
        self.grid_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=self.grid_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Action buttons
        action_frame = Frame(self)
        action_frame.pack(fill="x", padx=10, pady=10)

        Button(
            action_frame,
            text="➕ Adicionar Dia",
            command=self.add_day,
        ).pack(side="left", padx=5)

        Button(
            action_frame,
            text="📊 Relatório Geral",
            command=self.generate_general_report,
        ).pack(side="left", padx=5)

        Button(
            action_frame,
            text="⚙️ Configurar Experimento",
            command=self.configure_experiment,
        ).pack(side="left", padx=5)

        Button(
            action_frame,
            text="🔄 Atualizar",
            command=self.refresh_grid,
        ).pack(side="right", padx=5)

    def refresh_grid(self):
        """Rebuild grid with current data."""
        # Clear existing grid
        for widget in self.grid_frame.winfo_children():
            widget.destroy()

        days = self.experiment_data["days"]
        groups = self.experiment_data["groups"]

        if not days or not groups:
            Label(
                self.grid_frame,
                text="Configure o experimento para começar",
                font=("Segoe UI", 12),
                fg="#999",
            ).grid(row=0, column=0, padx=50, pady=50)
            return

        # Header row: Group names
        Label(self.grid_frame, text="", width=12).grid(row=0, column=0)
        for col, group in enumerate(groups, start=1):
            Label(
                self.grid_frame,
                text=group,
                font=("Segoe UI", 11, "bold"),
                bg="#e0e0e0",
                relief="raised",
                borderwidth=1,
            ).grid(row=0, column=col, sticky="ew", padx=2, pady=2)

        # Data rows: Day × Group blocks
        for row, day in enumerate(days, start=1):
            # Day label
            Label(
                self.grid_frame,
                text=day,
                font=("Segoe UI", 10, "bold"),
                bg="#e0e0e0",
                relief="raised",
                borderwidth=1,
            ).grid(row=row, column=0, sticky="ew", padx=2, pady=2)

            # Group blocks
            for col, group in enumerate(groups, start=1):
                block = self.create_day_group_block(day, group)
                block.grid(row=row, column=col, sticky="nsew", padx=2, pady=2)

        # Configure weights for responsive layout
        for col in range(len(groups) + 1):
            self.grid_frame.columnconfigure(col, weight=1)

    def create_day_group_block(self, day: str, group: str) -> Frame:
        """Create interactive block for Day × Group."""
        # Calculate status
        subjects = self.experiment_data["subjects"].get(group, [])
        completed_count = 0
        total_count = len(subjects)

        for subject in subjects:
            key = (day, group, subject)
            if key in self.experiment_data["sessions"]:
                completed_count += 1

        # Determine status emoji and color
        if completed_count == 0:
            status = "⏸️ Pendente"
            bg_color = "#f5f5f5"
        elif completed_count < total_count:
            status = f"⏳ {completed_count}/{total_count}"
            bg_color = "#fff3cd"
        else:
            status = f"✅ {completed_count}/{total_count}"
            bg_color = "#d4edda"

        # Create block frame
        block = Frame(
            self.grid_frame,
            bg=bg_color,
            relief="raised",
            borderwidth=2,
            cursor="hand2",
        )

        Label(
            block,
            text=status,
            font=("Segoe UI", 10, "bold"),
            bg=bg_color,
        ).pack(pady=(10, 5))

        Label(
            block,
            text=f"{completed_count}/{total_count}",
            font=("Segoe UI", 9),
            bg=bg_color,
            fg="#555",
        ).pack(pady=(0, 10))

        # Click handler
        block.bind("<Button-1>", lambda e: self.open_block_detail(day, group))

        return block

    def open_block_detail(self, day: str, group: str):
        """Open detail dialog for Day × Group block."""
        from zebtrack.ui.dialogs.block_detail_dialog import BlockDetailDialog

        dialog = BlockDetailDialog(
            parent=self,
            day=day,
            group=group,
            experiment_data=self.experiment_data,
            session_coordinator=self.session_coordinator,
            live_batch_coordinator=self.live_batch_coordinator,
        )
        dialog.wait_window()

        # Refresh grid after dialog closes
        self.refresh_grid()

    def load_experiment_data(self):
        """Load experiment configuration from project."""
        # TODO: Load from project_data.json or settings
        # For now, load from hardcoded defaults
        self.experiment_data = {
            "name": "Experimento Canabidiol - Janeiro 2026",
            "days": [f"Dia_{i}" for i in range(1, 8)],
            "groups": ["Controle", "Tratado"],
            "subjects": {
                "Controle": [f"Peixe_{i:02d}" for i in range(1, 6)],
                "Tratado": [f"Peixe_{i:02d}" for i in range(6, 11)],
            },
            "sessions": {},  # Will be populated from project sessions
        }

        # Update info label
        self.info_label.config(
            text=(
                f"Experimento: {self.experiment_data['name']} | "
                f"Período: {len(self.experiment_data['days'])} dias | "
                f"Grupos: {len(self.experiment_data['groups'])}"
            )
        )

        self.refresh_grid()

    def add_day(self):
        """Add new day to experiment."""
        # TODO: Implement add day dialog
        pass

    def generate_general_report(self):
        """Generate overall experiment report."""
        # TODO: Trigger batch coordinator to generate unified report
        pass

    def configure_experiment(self):
        """Open experiment configuration dialog."""
        # TODO: Implement configuration dialog
        pass
```

---

#### Task 2.2: Create BlockDetailDialog

**New File**: `src/zebtrack/ui/dialogs/block_detail_dialog.py`

```python
"""Block detail dialog for Day × Group session management.

Shows all subjects (cobaias) in the block with status and quick actions.

Version: 2.3.0
"""
from __future__ import annotations
from tkinter import *
from tkinter import ttk, messagebox
from typing import TYPE_CHECKING
import structlog

if TYPE_CHECKING:
    from zebtrack.coordinators.session_coordinator import SessionCoordinator
    from zebtrack.coordinators.live_batch_coordinator import LiveBatchCoordinator

log = structlog.get_logger(__name__)


class BlockDetailDialog(Toplevel):
    """Detail dialog for Day × Group block."""

    def __init__(
        self,
        parent,
        day: str,
        group: str,
        experiment_data: dict,
        session_coordinator: SessionCoordinator,
        live_batch_coordinator: LiveBatchCoordinator,
    ):
        super().__init__(parent)
        self.day = day
        self.group = group
        self.experiment_data = experiment_data
        self.session_coordinator = session_coordinator
        self.live_batch_coordinator = live_batch_coordinator

        # Window config
        self.title(f"Sessões: {day} - {group}")
        self.geometry("700x600")
        self.transient(parent)
        self.grab_set()

        self.build_ui()

    def build_ui(self):
        """Build dialog UI."""
        # Header
        header = Frame(self, bg="#f8f9fa", height=80)
        header.pack(fill="x")
        header.pack_propagate(False)

        Label(
            header,
            text=f"📋 {self.day} - {self.group}",
            font=("Segoe UI", 14, "bold"),
            bg="#f8f9fa",
        ).pack(side="left", padx=20, pady=20)

        # Progress info
        subjects = self.experiment_data["subjects"].get(self.group, [])
        completed = sum(
            1 for s in subjects
            if (self.day, self.group, s) in self.experiment_data["sessions"]
        )

        Label(
            header,
            text=f"📊 Progresso: {completed}/{len(subjects)} sessões",
            font=("Segoe UI", 11),
            bg="#f8f9fa",
            fg="#555",
        ).pack(side="left", padx=10, pady=20)

        # Subject list
        list_frame = LabelFrame(self, text="🐟 Cobaias", font=("Segoe UI", 11, "bold"))
        list_frame.pack(fill="both", expand=True, padx=20, pady=10)

        # Canvas + Scrollbar
        canvas = Canvas(list_frame)
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=canvas.yview)
        subject_container = Frame(canvas)

        subject_container.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=subject_container, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Populate subjects
        for subject in subjects:
            self.create_subject_row(subject_container, subject)

        # Actions frame
        action_frame = LabelFrame(
            self,
            text="🛠️ Ações Rápidas",
            font=("Segoe UI", 11, "bold"),
        )
        action_frame.pack(fill="x", padx=20, pady=10)

        Button(
            action_frame,
            text="▶️ Iniciar Próxima Sessão",
            command=self.start_next_session,
            width=30,
        ).pack(padx=10, pady=5)

        Button(
            action_frame,
            text="📊 Gerar Relatório Parcial",
            command=self.generate_partial_report,
            width=30,
        ).pack(padx=10, pady=5)

        Button(
            action_frame,
            text="📝 Adicionar Nota",
            command=self.add_note,
            width=30,
        ).pack(padx=10, pady=5)

        # Bottom buttons
        button_frame = Frame(self)
        button_frame.pack(fill="x", padx=20, pady=10)

        Button(
            button_frame,
            text="Fechar",
            command=self.destroy,
        ).pack(side="right", padx=5)

        Button(
            button_frame,
            text="✅ Marcar Lote Como Completo",
            command=self.mark_batch_complete,
        ).pack(side="right", padx=5)

    def create_subject_row(self, parent: Frame, subject: str):
        """Create row for single subject."""
        key = (self.day, self.group, subject)
        session = self.experiment_data["sessions"].get(key)

        row = Frame(parent, relief="solid", borderwidth=1, bg="white")
        row.pack(fill="x", padx=5, pady=3)

        # Status indicator
        if session:
            status_label = Label(row, text="✅", font=("Segoe UI", 14), bg="white")
            status_text = f"{session.get('start_time', '--')} | {session.get('duration', '--')}"
        else:
            status_label = Label(row, text="⏸️", font=("Segoe UI", 14), bg="white")
            status_text = "Pendente"

        status_label.pack(side="left", padx=10, pady=10)

        # Subject info
        info_frame = Frame(row, bg="white")
        info_frame.pack(side="left", fill="both", expand=True, padx=10, pady=10)

        Label(
            info_frame,
            text=subject,
            font=("Segoe UI", 11, "bold"),
            bg="white",
        ).pack(anchor="w")

        Label(
            info_frame,
            text=status_text,
            font=("Segoe UI", 9),
            fg="#666",
            bg="white",
        ).pack(anchor="w")

        # Action buttons
        if session:
            Button(
                row,
                text="📊 Ver Resultados",
                command=lambda: self.view_results(subject),
            ).pack(side="right", padx=5, pady=10)
        else:
            Button(
                row,
                text="▶️ Iniciar",
                command=lambda: self.start_session(subject),
            ).pack(side="right", padx=5, pady=10)

    def start_session(self, subject: str):
        """Start live session for subject."""
        log.info("block_detail.start_session", day=self.day, group=self.group, subject=subject)

        # Prepare wizard data
        wizard_data = {
            "experimental_group": self.group,
            "experiment_day": self.day,
            "subject_id": subject,
            "is_batch_last_session": False,  # User can change this later
        }

        # TODO: Trigger live session start via session_coordinator
        # For now, show message
        messagebox.showinfo(
            "Sessão",
            f"Iniciando sessão para {subject}\n{self.day} - {self.group}"
        )

    def start_next_session(self):
        """Start next pending session."""
        subjects = self.experiment_data["subjects"].get(self.group, [])
        for subject in subjects:
            key = (self.day, self.group, subject)
            if key not in self.experiment_data["sessions"]:
                self.start_session(subject)
                return

        messagebox.showinfo("Completo", "Todas as sessões deste bloco foram concluídas!")

    def view_results(self, subject: str):
        """View session results."""
        # TODO: Open results viewer
        messagebox.showinfo("Resultados", f"Visualizando resultados de {subject}")

    def generate_partial_report(self):
        """Generate partial report for completed sessions."""
        # TODO: Trigger batch report generation
        messagebox.showinfo("Relatório", "Gerando relatório parcial...")

    def add_note(self):
        """Add note to day/group block."""
        # TODO: Implement note dialog
        messagebox.showinfo("Nota", "Adicionar nota experimental")

    def mark_batch_complete(self):
        """Mark batch as complete and trigger unified report."""
        result = messagebox.askyesno(
            "Confirmar",
            "Marcar este lote como completo?\n\nIsso irá gerar o relatório unificado final."
        )

        if result:
            # TODO: Call live_batch_coordinator.mark_batch_complete()
            messagebox.showinfo("Sucesso", "Lote marcado como completo!\nGerando relatório...")
            self.destroy()
```

---

#### Task 2.3: Integrate Progress Tab into MainWindow

**File**: `src/zebtrack/ui/gui.py`

**Add import** (around line 40):

```python
from zebtrack.ui.tabs.experiment_progress_tab import ExperimentProgressTab
```

**Update `_create_tabs()` method** (around line 250):

```python
def _create_tabs(self):
    """Create notebook tabs."""
    # ... existing tabs (Processamento, Análise, Relatórios) ...

    # === Experiment Progress Tab (v2.3.0) ===
    self.progress_tab = ExperimentProgressTab(
        parent=self.notebook,
        project_manager=self.project_manager,
        session_coordinator=self.session_coordinator,
        live_batch_coordinator=self.live_batch_coordinator,
        settings_obj=self.settings_obj,
    )
    self.notebook.add(self.progress_tab, text="📊 Progresso do Experimento")
```

**Update MainWindow constructor** to accept `live_batch_coordinator`:

```python
def __init__(
    self,
    # ... existing parameters ...
    live_batch_coordinator: LiveBatchCoordinator,
):
    # ... existing init ...
    self.live_batch_coordinator = live_batch_coordinator
```

**Update `__main__.py` to pass coordinator**:

```python
main_window = MainWindow(
    # ... existing args ...
    live_batch_coordinator=live_batch_coordinator,
)
```

---

#### Task 2.4: Testing Progress Dashboard

**Manual Testing Checklist**:

1. Launch app: `poetry run python -m zebtrack`
2. Navigate to "📊 Progresso do Experimento" tab
3. Verify grid displays with Day × Group blocks
4. Click a block → Detail dialog opens
5. Click subject "▶️ Iniciar" → Confirmation message
6. Click "Marcar Lote Como Completo" → Confirmation dialog

**Unit Tests** in `tests/ui/tabs/test_experiment_progress_tab.py`:

```python
"""Tests for experiment progress dashboard tab."""
import pytest
import tkinter as tk
from zebtrack.ui.tabs.experiment_progress_tab import ExperimentProgressTab


def test_experiment_progress_tab_initialization(
    mock_project_manager,
    mock_session_coordinator,
    mock_live_batch_coordinator,
    mock_settings,
):
    """Test tab initializes without errors."""
    root = tk.Tk()

    tab = ExperimentProgressTab(
        parent=root,
        project_manager=mock_project_manager,
        session_coordinator=mock_session_coordinator,
        live_batch_coordinator=mock_live_batch_coordinator,
        settings_obj=mock_settings,
    )

    assert tab.winfo_exists()
    assert len(tab.experiment_data["days"]) == 7
    assert len(tab.experiment_data["groups"]) == 2

    root.destroy()


def test_grid_refresh_creates_blocks(
    mock_project_manager,
    mock_session_coordinator,
    mock_live_batch_coordinator,
    mock_settings,
):
    """Test grid creates correct number of blocks."""
    root = tk.Tk()

    tab = ExperimentProgressTab(
        parent=root,
        project_manager=mock_project_manager,
        session_coordinator=mock_session_coordinator,
        live_batch_coordinator=mock_live_batch_coordinator,
        settings_obj=mock_settings,
    )

    tab.refresh_grid()

    # Should have 7 days × 2 groups = 14 blocks (+ header row/col)
    grid_widgets = tab.grid_frame.winfo_children()
    assert len(grid_widgets) > 14  # Blocks + labels

    root.destroy()
```

---

## ✅ Success Criteria

### LiveBatchCoordinator Integration

- [ ] Wizard collects `experimental_group`, `experiment_day`, `subject_id`
- [ ] LiveBatchCoordinator instantiated in `__main__.py`
- [ ] SessionCoordinator registers sessions after completion
- [ ] Checkbox "Marcar como última sessão" works
- [ ] Event `BATCH_ANALYSIS_COMPLETED` published when batch completes
- [ ] UICoordinator shows notification with report path
- [ ] Existing tests pass: `poetry run pytest tests/test_live_camera_workflow_e2e.py::TestLiveBatchCoordinator -xvs`
- [ ] New integration test passes

### Experiment Progress Dashboard

- [ ] Tab "📊 Progresso do Experimento" appears in MainWindow
- [ ] Grid displays Day × Group matrix with status colors
- [ ] Blocks show correct completion status (✅/⏳/⏸️)
- [ ] Clicking block opens BlockDetailDialog
- [ ] Dialog lists all subjects with status
- [ ] "▶️ Iniciar" button triggers session start
- [ ] "Marcar Lote Como Completo" triggers batch report
- [ ] UI is responsive and visually consistent with existing tabs

---

## 🏗️ Architecture Considerations

### Dependency Injection

- All new components receive dependencies via constructor
- No singleton imports (`from zebtrack import settings`)
- Follow patterns in `DEPENDENCY_INJECTION_GUIDE.md`

### Event Flow

- LiveBatchCoordinator publishes `BATCH_ANALYSIS_COMPLETED`
- UICoordinator handles event and shows notification
- Progress tab subscribes to session completion events to refresh

### Thread Safety

- All UI updates use `root.after(0, callback)`
- Never update widgets directly from background threads
- Use `StateManager` for cross-thread state updates

### Testing Strategy

- Unit tests for each component
- Integration tests for wizard → coordinator flow
- Manual testing with real camera (if available)
- Smoke tests for UI tab rendering

---

## 📝 Documentation Requirements

After implementation, update:

1. **CHANGELOG.md**: Add v2.3.0 section
2. **docs/guides/user/**: Add experimental workflow guide (Portuguese)
3. **docs/architecture/**: Update with new components
4. **README.md**: Mention batch reporting feature

---

## 🚨 Common Pitfalls to Avoid

1. **Forgetting `root.after()` for UI updates** → Use `UIScheduler` or direct `root.after(0, ...)`
2. **Not passing `settings_obj` to constructors** → All services need settings via DI
3. **Blocking main thread with analysis** → Use `ProcessingWorker` for heavy tasks
4. **Not testing with actual wizard flow** → Integration tests are critical
5. **Hardcoding paths** → Use `Path` objects and respect user's project structure

---

## 🔍 Validation Commands

```bash
# Run all tests
poetry run pytest -q

# Run LiveBatchCoordinator tests
poetry run pytest tests/test_live_camera_workflow_e2e.py::TestLiveBatchCoordinator -xvs

# Run progress tab tests
poetry run pytest tests/ui/tabs/test_experiment_progress_tab.py -xvs

# Run wizard integration test
poetry run pytest tests/test_live_batch_integration.py -xvs

# Launch app
poetry run python -m zebtrack

# Check for DI violations
grep -r "from zebtrack import settings" src/zebtrack/ui/
grep -r "from zebtrack import settings" src/zebtrack/coordinators/

# Lint check
poetry run ruff check .

# Format check
poetry run ruff format . --check
```

---

## 📚 Reference Files

**Must Read Before Starting**:

- `.github/copilot-instructions.md` - Agent playbook
- `docs/architecture/ARCHITECTURE.md` - System design
- `docs/architecture/DEPENDENCY_INJECTION_GUIDE.md` - DI patterns
- `docs/decisions/ADR-006-live-batch-coordinator-future.md` - Why deferred

**Implementation References**:

- `src/zebtrack/coordinators/live_batch_coordinator.py` - Existing implementation
- `src/zebtrack/ui/wizard/live_config_step.py` - Wizard step to extend
- `src/zebtrack/__main__.py` - Composition Root (lines 140-280)
- `src/zebtrack/coordinators/session_coordinator.py` - Session lifecycle
- `src/zebtrack/ui/gui.py` - MainWindow tabs

**Test References**:

- `tests/test_live_camera_workflow_e2e.py` - E2E patterns
- `tests/ui/wizard/test_wizard_live_e2e.py` - Wizard test patterns
- `tests/conftest.py` - Pytest fixtures

---

## 🎯 Final Checklist

Before submitting:

- [ ] All tests pass (`poetry run pytest -q`)
- [ ] No DI violations (grep check)
- [ ] Lint passes (`poetry run ruff check .`)
- [ ] Documentation updated (CHANGELOG, guides)
- [ ] Manual testing completed (wizard → batch → report)
- [ ] Commit messages follow convention (`feat:`, `fix:`, `docs:`)
- [ ] ADR-006 status updated to "Implemented"

---

**Good luck with the implementation! Focus on small, testable increments and validate each component before moving to the next.** 🚀
