"""Block detail dialog for Day x Group session management (v2.3.0).

Shows all subjects (cobaias) in the block with status and quick actions.

Version: 2.3.1
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path
from tkinter import Button, Canvas, Frame, Label, Toplevel, messagebox, simpledialog, ttk
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from zebtrack.coordinators.live_batch_coordinator import LiveBatchCoordinator
    from zebtrack.coordinators.session_coordinator import SessionCoordinator

log = structlog.get_logger(__name__)


class BlockDetailDialog(Toplevel):
    """Detail dialog for Day x Group block."""

    def __init__(
        self,
        parent,
        day: int | str,
        group: str,
        project_manager,
        session_coordinator: SessionCoordinator,
        live_batch_coordinator: LiveBatchCoordinator,
    ):
        """Initialize block detail dialog.

        Args:
            parent: Parent widget
            day: Day number (int) or label (str, e.g., "Dia_1")
            group: Group name (e.g., "Controle")
            project_manager: ProjectManager instance for project data access
            session_coordinator: SessionCoordinator for session management
            live_batch_coordinator: LiveBatchCoordinator for batch tracking
        """
        super().__init__(parent)
        # v2.3.1: Handle both int and str day formats
        self.day_num = (
            day if isinstance(day, int) else int(day.replace("Dia_", "").replace("D", ""))
        )
        self.day = f"Dia_{self.day_num}" if isinstance(day, int) else str(day)
        self.group_name = group
        self.project_manager = project_manager
        self.session_coordinator = session_coordinator
        self.live_batch_coordinator = live_batch_coordinator

        # Extract experiment data from project_manager
        project_data = (
            project_manager.project_data if hasattr(project_manager, "project_data") else {}
        )
        self.subjects_per_group = project_data.get("subjects_per_group", 0)
        self.completed_sessions = (
            set(project_manager.get_completed_sessions())
            if hasattr(project_manager, "get_completed_sessions")
            else set()
        )

        # v2.3.1: Debug log for session detection
        log.info(
            "block_detail.init",
            day=self.day_num,
            group=self.group_name,
            subjects_per_group=self.subjects_per_group,
            completed_sessions=list(self.completed_sessions),
            project_path=str(project_manager.project_path)
            if project_manager.project_path
            else None,
        )

        # Window config
        self.title(f"Sessões: Dia {self.day_num} - {group}")
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
            text=f"📋 Dia {self.day_num} - {self.group_name}",
            font=("Segoe UI", 14, "bold"),
            bg="#f8f9fa",
        ).pack(side="left", padx=20, pady=20)

        # Progress info - v2.3.1: Use subjects_per_group and completed_sessions
        subjects = [str(i + 1) for i in range(self.subjects_per_group)]
        completed = sum(
            1 for s in subjects if (self.day_num, self.group_name, s) in self.completed_sessions
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

        subject_container.bind(
            "<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

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

    def _find_session_folder(self, subject: str) -> Path | None:
        """Find the session folder for a specific day/group/subject.

        Args:
            subject: Subject ID (e.g., "1", "2")

        Returns:
            Path to session folder if found, None otherwise
        """
        if not self.project_manager.project_path:
            return None

        project_path = Path(self.project_manager.project_path)

        # Pattern 1: New format - day{day}_{group}_{subject}_{timestamp}
        # Example: "day1_Controle_1_20260103_142530"
        pattern_new = re.compile(
            rf"^day{self.day_num}_{re.escape(self.group_name)}_{subject}_\d{{8}}_\d{{6}}$"
        )

        # Pattern 2: Legacy format - D{day}_G{group}_S{subject}
        pattern_legacy = re.compile(rf"^D{self.day_num}_G{re.escape(self.group_name)}_S{subject}$")

        for item in project_path.iterdir():
            if not item.is_dir():
                continue
            if pattern_new.match(item.name) or pattern_legacy.match(item.name):
                return item

        return None

    def _get_session_files_status(self, folder: Path) -> dict[str, bool]:
        """Check which output files exist in a session folder.

        Args:
            folder: Path to session folder

        Returns:
            Dict with file type as key and existence as value
        """
        status = {
            "video": False,
            "trajectory": False,  # 3_CoordMovimento
            "arena": False,  # 1_ProcessingArea
            "rois": False,  # 2_AreasOfInterest or 2_ZonasROI
            "summary": False,  # 4_Resumo or similar
        }

        if not folder or not folder.exists():
            return status

        for file in folder.iterdir():
            name = file.name.lower()
            if file.suffix == ".mp4":
                status["video"] = True
            elif "coordmovimento" in name or "trajectory" in name:
                status["trajectory"] = True
            elif "processingarea" in name or "arena" in name:
                status["arena"] = True
            elif "areasofinterest" in name or "zonasroi" in name or "zonas" in name:
                status["rois"] = True
            elif "resumo" in name or "summary" in name:
                status["summary"] = True

        return status

    def create_subject_row(self, parent: Frame, subject: str):
        """Create row for single subject.

        Args:
            parent: Parent frame to contain the row
            subject: Subject ID (e.g., "1", "2", etc.)
        """
        # v2.3.1: Use day_num (int) for session lookup
        is_completed = (self.day_num, self.group_name, subject) in self.completed_sessions

        # v2.3.1: Get session folder and file status
        session_folder = self._find_session_folder(subject)
        files_status = self._get_session_files_status(session_folder) if session_folder else {}

        row = Frame(parent, relief="solid", borderwidth=1, bg="white")
        row.pack(fill="x", padx=5, pady=3)

        # Status indicator
        if is_completed:
            status_label = Label(row, text="✅", font=("Segoe UI", 14), bg="white")
            status_text = "Gravado"
        else:
            status_label = Label(row, text="⏸️", font=("Segoe UI", 14), bg="white")
            status_text = "Pendente"

        status_label.pack(side="left", padx=10, pady=10)

        # Subject info
        info_frame = Frame(row, bg="white")
        info_frame.pack(side="left", fill="both", expand=True, padx=10, pady=10)

        Label(
            info_frame,
            text=f"Animal {subject}",
            font=("Segoe UI", 11, "bold"),
            bg="white",
        ).pack(anchor="w")

        # v2.3.1: Show file status icons for completed sessions
        if is_completed and files_status:
            file_icons = []
            if files_status.get("video"):
                file_icons.append("🎬")  # Video
            if files_status.get("arena"):
                file_icons.append("🏟️")  # Arena
            if files_status.get("trajectory"):
                file_icons.append("🧭")  # Trajectory
            if files_status.get("rois"):
                file_icons.append("🎯")  # ROIs
            if files_status.get("summary"):
                file_icons.append("Σ")  # Summary

            files_text = " ".join(file_icons) if file_icons else "⚠️ Sem arquivos"
            status_detail = f"{status_text} | {files_text}"
        else:
            status_detail = status_text

        Label(
            info_frame,
            text=status_detail,
            font=("Segoe UI", 9),
            fg="#666",
            bg="white",
        ).pack(anchor="w")

        # v2.3.1: Show folder name if exists
        if session_folder:
            Label(
                info_frame,
                text=f"📁 {session_folder.name}",
                font=("Segoe UI", 8),
                fg="#999",
                bg="white",
            ).pack(anchor="w")

        # Action buttons
        if is_completed:
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
        log.info(
            "block_detail.start_session", day=self.day_num, group=self.group_name, subject=subject
        )

        # v2.3.1: Actually start the session using session_coordinator
        try:
            # Close dialog first so it doesn't block
            self.destroy()

            # Start the live project session
            success = self.session_coordinator.start_live_project_session(
                day=self.day_num,
                group=str(self.group_name),
                subject=subject,
            )

            if not success:
                messagebox.showerror(
                    "Erro",
                    f"Falha ao iniciar sessão para Animal {subject}\n"
                    f"Dia {self.day_num} - {self.group_name}",
                )
        except Exception as e:
            log.error("block_detail.start_session.failed", error=str(e), exc_info=True)
            messagebox.showerror("Erro", f"Erro ao iniciar sessão: {e!s}")

    def start_next_session(self):
        """Start next pending session."""
        # v2.3.1: Use subjects_per_group and completed_sessions
        subjects = [str(i + 1) for i in range(self.subjects_per_group)]
        for subject in subjects:
            if (self.day_num, self.group_name, subject) not in self.completed_sessions:
                self.start_session(subject)
                return

        messagebox.showinfo("Completo", "Todas as sessões deste bloco foram concluídas!")

    def view_results(self, subject: str):
        """View session results by opening the session folder.

        Args:
            subject: Subject ID to view results for
        """
        session_folder = self._find_session_folder(subject)

        if not session_folder or not session_folder.exists():
            messagebox.showwarning(
                "Pasta não encontrada",
                f"Não foi possível encontrar a pasta de resultados para Animal {subject}.\n"
                f"Dia {self.day_num} - {self.group_name}",
            )
            return

        try:
            # Open folder in system file explorer
            if sys.platform == "win32":
                os.startfile(session_folder)
            elif sys.platform == "darwin":
                subprocess.run(["open", str(session_folder)], check=True)
            else:
                subprocess.run(["xdg-open", str(session_folder)], check=True)

            log.info(
                "block_detail.view_results.opened",
                folder=str(session_folder),
            )
        except Exception as e:
            log.error("block_detail.view_results.failed", error=str(e), exc_info=True)
            messagebox.showerror(
                "Erro",
                f"Falha ao abrir pasta de resultados:\n{e!s}",
            )

    def generate_partial_report(self):
        """Generate partial report for completed sessions in this block.

        Collects all summary Excel files from completed sessions and aggregates
        them into a single Excel file for the day/group block.
        """
        log.info(
            "block_detail.generate_partial_report",
            day=self.day_num,
            group=self.group_name,
        )

        # Collect completed session folders for this block
        subjects = [str(i + 1) for i in range(self.subjects_per_group)]
        completed_in_block = [
            s for s in subjects if (self.day_num, self.group_name, s) in self.completed_sessions
        ]

        if not completed_in_block:
            messagebox.showwarning(
                "Sem Sessões",
                f"Nenhuma sessão concluída encontrada para\nDia {self.day_num} - {self.group_name}",
            )
            return

        # Find summary files in each session folder
        import pandas as pd

        summary_files = []
        for subject in completed_in_block:
            session_folder = self._find_session_folder(subject)
            if not session_folder or not session_folder.exists():
                continue

            # Look for summary Excel files
            for file in session_folder.iterdir():
                name = file.name.lower()
                if (file.suffix in [".xlsx", ".xls"]) and ("resumo" in name or "summary" in name):
                    summary_files.append((subject, file))
                    break

        if not summary_files:
            messagebox.showwarning(
                "Sem Relatórios",
                f"Nenhum arquivo de resumo encontrado nas sessões de\n"
                f"Dia {self.day_num} - {self.group_name}\n\n"
                f"Execute a análise das sessões primeiro.",
            )
            return

        try:
            # Create output directory and file
            project_path = Path(self.project_manager.project_path)
            reports_dir = project_path / "partial_reports"
            reports_dir.mkdir(parents=True, exist_ok=True)

            output_filename = f"PartialReport_Dia{self.day_num}_{self.group_name}.xlsx"
            output_path = reports_dir / output_filename

            # Aggregate summaries
            all_data = []
            for subject, summary_path in summary_files:
                try:
                    df = pd.read_excel(summary_path)
                    df["animal"] = subject
                    df["dia"] = self.day_num
                    df["grupo"] = self.group_name
                    df["source_file"] = summary_path.name
                    all_data.append(df)
                except Exception as e:
                    log.warning(
                        "block_detail.partial_report.read_failed",
                        summary_path=str(summary_path),
                        error=str(e),
                    )

            if not all_data:
                raise ValueError("Nenhum dado válido encontrado nos arquivos de resumo")

            # Concatenate all data
            non_empty_dfs = [df for df in all_data if not df.empty]
            if not non_empty_dfs:
                raise ValueError("Nenhum dado válido encontrado (todos os arquivos estavam vazios)")

            import warnings

            with warnings.catch_warnings():
                warnings.filterwarnings(
                    "ignore",
                    category=FutureWarning,
                    message=".*concatenation with empty or all-NA entries.*",
                )
                unified_df = pd.concat(non_empty_dfs, ignore_index=True)

            # Write to Excel with multiple sheets
            with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
                # Sheet 1: All sessions combined
                unified_df.to_excel(writer, sheet_name="Dados Consolidados", index=False)

                # Sheet 2: Summary by animal
                if len(all_data) > 1 and "total_distance_cm" in unified_df.columns:
                    # Create summary stats
                    stats_cols = [
                        col
                        for col in unified_df.columns
                        if any(kw in col.lower() for kw in ["distance", "speed", "time", "entries"])
                    ]
                    if stats_cols:
                        summary_stats = unified_df.groupby("animal")[stats_cols].mean()
                        summary_stats.to_excel(writer, sheet_name="Resumo por Animal")

            log.info(
                "block_detail.partial_report.success",
                output=str(output_path),
                session_count=len(all_data),
            )

            # Show success and offer to open
            result = messagebox.askyesno(
                "Relatório Gerado",
                f"Relatório parcial gerado com sucesso!\n\n"
                f"📄 {output_filename}\n"
                f"📊 {len(all_data)} sessões agregadas\n\n"
                f"Deseja abrir o arquivo?",
            )

            if result:
                try:
                    if sys.platform == "win32":
                        os.startfile(output_path)
                    elif sys.platform == "darwin":
                        subprocess.run(["open", str(output_path)], check=True)
                    else:
                        subprocess.run(["xdg-open", str(output_path)], check=True)
                except Exception as e:
                    log.warning("block_detail.partial_report.open_failed", error=str(e))
                    messagebox.showwarning(
                        "Aviso",
                        f"O arquivo foi gerado, mas não foi possível abri-lo:\n{output_path}",
                    )

        except Exception as e:
            log.error("block_detail.generate_partial_report.failed", error=str(e), exc_info=True)
            messagebox.showerror(
                "Erro",
                f"Falha ao gerar relatório parcial:\n{e!s}",
            )

    def add_note(self):
        """Add note to day/group block."""
        log.info("block_detail.add_note", day=self.day_num, group=self.group_name)

        # Get existing notes from project data
        project_data = (
            self.project_manager.project_data
            if hasattr(self.project_manager, "project_data")
            else {}
        )

        # Notes are stored in experiment_notes dict with block key
        experiment_notes = project_data.get("experiment_notes", {})
        block_key = f"Dia_{self.day_num}_{self.group_name}"
        existing_note = experiment_notes.get(block_key, "")

        # Show input dialog
        note = simpledialog.askstring(
            "Adicionar Nota Experimental",
            f"Nota para Dia {self.day_num} - {self.group_name}:\n\n(deixe vazio para limpar)",
            initialvalue=existing_note,
            parent=self,
        )

        if note is None:
            # User cancelled
            return

        try:
            # Save note
            if "experiment_notes" not in project_data:
                project_data["experiment_notes"] = {}

            if note.strip():
                project_data["experiment_notes"][block_key] = note.strip()
                log.info("block_detail.add_note.saved", block_key=block_key, note=note[:50])
                messagebox.showinfo("Nota Salva", "Nota experimental salva com sucesso!")
            else:
                # Remove note if empty
                if block_key in project_data["experiment_notes"]:
                    del project_data["experiment_notes"][block_key]
                log.info("block_detail.add_note.cleared", block_key=block_key)
                messagebox.showinfo("Nota Removida", "Nota experimental removida.")

            # Save project
            if hasattr(self.project_manager, "save_project"):
                self.project_manager.save_project()

        except Exception as e:
            log.error("block_detail.add_note.failed", error=str(e), exc_info=True)
            messagebox.showerror("Erro", f"Falha ao salvar nota:\n{e!s}")

    def mark_batch_complete(self):
        """Mark batch as complete and trigger unified report."""
        result = messagebox.askyesno(
            "Confirmar",
            "Marcar este lote como completo?\n\nIsso irá gerar o relatório unificado final.",
        )

        if result:
            # v2.3.1: Use day_num in batch_id
            batch_id = f"{self.group_name}_Dia_{self.day_num}_*"

            try:
                self.live_batch_coordinator.mark_batch_complete(batch_id)
                messagebox.showinfo("Sucesso", "Lote marcado como completo!\nGerando relatório...")
                self.destroy()
            except Exception as e:
                log.error("block_detail.mark_batch_complete_failed", error=str(e))
                messagebox.showerror("Erro", f"Falha ao marcar lote: {e!s}")
