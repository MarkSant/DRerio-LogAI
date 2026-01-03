"""Block detail dialog for Day × Group session management (v2.3.0).

Shows all subjects (cobaias) in the block with status and quick actions.

Version: 2.3.0
"""

from __future__ import annotations

import structlog
from tkinter import Button, Canvas, Checkbutton, Frame, Label, Toplevel, messagebox
from tkinter import ttk
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from zebtrack.coordinators.live_batch_coordinator import LiveBatchCoordinator
    from zebtrack.coordinators.session_coordinator import SessionCoordinator

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
        """Initialize block detail dialog.

        Args:
            parent: Parent widget
            day: Day label (e.g., "Dia_1")
            group: Group name (e.g., "Controle")
            experiment_data: Experiment configuration dictionary
            session_coordinator: SessionCoordinator for session management
            live_batch_coordinator: LiveBatchCoordinator for batch tracking
        """
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
            1 for s in subjects if (self.day, self.group, s) in self.experiment_data["sessions"]
        )

        Label(
            header,
            text=f"📊 Progresso: {completed}/{len(subjects)} sessões",
            font=("Segoe UI", 11),
            bg="#f8f9fa",
            fg="#555",
        ).pack(side="left", padx=10, pady=20)

        # Subject list
        list_frame = Frame(self)
        list_frame.pack(fill="both", expand=True, padx=20, pady=10)

        Label(
            list_frame,
            text="🐟 Cobaias",
            font=("Segoe UI", 11, "bold"),
        ).pack(anchor="w", pady=(0, 10))

        # Canvas + Scrollbar
        canvas = Canvas(list_frame)
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=canvas.yview)
        subject_container = Frame(canvas)

        subject_container.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))

        canvas.create_window((0, 0), window=subject_container, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Populate subjects
        for subject in subjects:
            self.create_subject_row(subject_container, subject)

        # Actions frame
        action_frame = Frame(self)
        action_frame.pack(fill="x", padx=20, pady=10)

        Label(
            action_frame,
            text="🛠️ Ações Rápidas",
            font=("Segoe UI", 11, "bold"),
        ).pack(anchor="w", pady=(0, 10))

        Button(
            action_frame,
            text="▶️ Iniciar Próxima Sessão",
            command=self.start_next_session,
            width=30,
        ).pack(fill="x", pady=5)

        Button(
            action_frame,
            text="📊 Gerar Relatório Parcial",
            command=self.generate_partial_report,
            width=30,
        ).pack(fill="x", pady=5)

        Button(
            action_frame,
            text="📝 Adicionar Nota",
            command=self.add_note,
            width=30,
        ).pack(fill="x", pady=5)

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
        """Create row for single subject.

        Args:
            parent: Parent frame to contain the row
            subject: Subject ID (e.g., "Peixe_01")
        """
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
        """Start live session for subject.

        Args:
            subject: Subject ID to start session for
        """
        log.info("block_detail.start_session", day=self.day, group=self.group, subject=subject)

        # TODO: Trigger live session start via session_coordinator
        # For now, show message
        messagebox.showinfo("Sessão", f"Iniciando sessão para {subject}\n{self.day} - {self.group}")

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
        """View session results.

        Args:
            subject: Subject ID to view results for
        """
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
            "Marcar este lote como completo?\n\n"
            "Isso irá gerar o relatório unificado final.",
        )

        if result:
            # TODO: Call live_batch_coordinator.mark_batch_complete()
            # Need to construct batch_id from group/day
            batch_id = f"{self.group}_{self.day}_*"

            try:
                self.live_batch_coordinator.mark_batch_complete(batch_id)
                messagebox.showinfo("Sucesso", "Lote marcado como completo!\nGerando relatório...")
                self.destroy()
            except Exception as e:
                log.error("block_detail.mark_batch_complete_failed", error=str(e))
                messagebox.showerror("Erro", f"Falha ao marcar lote: {e!s}")
