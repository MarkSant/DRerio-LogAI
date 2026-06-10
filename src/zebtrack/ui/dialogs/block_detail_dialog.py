"""Block detail dialog for Day x Group session management (v2.3.0).

Shows all subjects (cobaias) in the block with status and quick actions.

Version: 2.3.1
"""

from __future__ import annotations

import re
import threading
from datetime import datetime
from pathlib import Path
from tkinter import Button, Canvas, Frame, Label, Toplevel, messagebox, simpledialog, ttk
from typing import TYPE_CHECKING

import structlog

from zebtrack.utils.report_files import find_summary_excel_file, has_summary_excel_output

if TYPE_CHECKING:
    from zebtrack.coordinators.live_batch_coordinator import LiveBatchCoordinator
    from zebtrack.coordinators.live_camera_session_coordinator import LiveCameraSessionCoordinator

log = structlog.get_logger(__name__)


class BlockDetailDialog(Toplevel):
    """Detail dialog for Day x Group block."""

    def __init__(
        self,
        parent,
        day: int | str,
        group: str,
        project_manager,
        session_coordinator: LiveCameraSessionCoordinator,
        live_batch_coordinator: LiveBatchCoordinator,
    ):
        """Initialize block detail dialog.

        Args:
            parent: Parent widget
            day: Day number (int) or label (str, e.g., "Dia_1")
            group: Group name (e.g., "Controle")
            project_manager: ProjectManager instance for project data access
            session_coordinator: LiveCameraSessionCoordinator for session management
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

        # Cache project polygon status for the header indicator + per-subject
        # "reused" badge. Read once at dialog init so per-row rendering doesn't
        # re-walk the zone data structures.
        try:
            zone_data = (
                project_manager.get_zone_data()
                if hasattr(project_manager, "get_zone_data")
                else None
            )
            self._project_has_polygon = bool(zone_data and getattr(zone_data, "polygon", None))
        except Exception:
            self._project_has_polygon = False

        # v2.3.1: Debug log for session detection
        log.info(
            "block_detail.init",
            day=self.day_num,
            group=self.group_name,
            subjects_per_group=self.subjects_per_group,
            completed_sessions=list(self.completed_sessions),
            project_has_polygon=self._project_has_polygon,
            project_path=str(project_manager.project_path)
            if project_manager.project_path
            else None,
        )

        # Window config
        self.title(f"Sessões: Dia {self.day_num} - {group}")
        self.geometry("700x640")
        self.transient(parent)
        self.grab_set()

        # Per-block camera override (None = use project default).
        self._camera_index_override: int | None = None
        self._camera_friendly_name_override: str | None = None
        self._camera_label: Label | None = None

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

        # Project-level polygon indicator: shows whether the project already has
        # an arena polygon defined (which gets reused across subjects in live
        # projects). Helps users know whether the first session of the block
        # will trigger zone calibration or jump straight to recording.
        polygon_text = (
            "🏟️ Polígono do projeto: ✅ Definido"
            if self._project_has_polygon
            else "🏟️ Polígono do projeto: ⚠️ Não definido"
        )
        polygon_color = "#0a7" if self._project_has_polygon else "#a23"
        Label(
            header,
            text=polygon_text,
            font=("Segoe UI", 10),
            bg="#f8f9fa",
            fg=polygon_color,
        ).pack(side="right", padx=20, pady=20)

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

        # Camera section: shows project default + optional override for this block.
        camera_frame = Frame(self)
        camera_frame.pack(fill="x", padx=20, pady=(0, 10))

        Label(
            camera_frame,
            text="📷 Câmera:",
            font=("Segoe UI", 10, "bold"),
        ).pack(side="left")

        self._camera_label = Label(
            camera_frame,
            text=self._format_current_camera(),
            font=("Segoe UI", 10),
            anchor="w",
        )
        self._camera_label.pack(side="left", padx=(5, 10))

        Button(
            camera_frame,
            text="Trocar...",
            command=self._open_camera_chooser,
        ).pack(side="left")

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

    def _publish_project_views_refresh(self, reason: str) -> None:
        """Publish a project-views refresh if an event bus is available."""
        event_bus = getattr(self.session_coordinator, "event_bus", None)
        if event_bus is None:
            event_bus = getattr(self.live_batch_coordinator, "event_bus", None)
        if event_bus is None:
            return

        from zebtrack.ui import payloads
        from zebtrack.ui.event_bus_v2 import Event, UIEvents

        event_bus.publish(
            Event(
                type=UIEvents.PROJECT_VIEWS_REFRESH_REQUESTED,
                data=payloads.ProjectViewsRefreshRequestedPayload(
                    reason=reason,
                    append_summary=True,
                    immediate=True,
                ),
            )
        )

    @staticmethod
    def _open_generated_report_file(path: Path) -> None:
        """Open a generated report file using the platform opener."""
        from zebtrack.utils.os_opener import open_path

        open_path(path)

    def _find_session_folder(self, subject: str) -> Path | None:
        """Find the session folder for a specific day/group/subject.

        Lookup strategy (first match wins):
        1. ``project_data["batches"][*]["videos"][*].results_dir`` — preferred
           path that handles both legacy flat layouts and the new
           ``Grupo_X/Dia_Y/Sujeito_Z/live_{ts}/`` hierarchy uniformly.
        2. Legacy filesystem scan for ``day{N}_{group}_{subject}_*`` and
           ``D{N}_G{group}_S{subject}`` folders at the project root (used by
           older recordings made before the hierarchical layout was adopted).

        Args:
            subject: Subject ID (e.g., "1", "2")

        Returns:
            Path to session folder if found, None otherwise
        """
        if not self.project_manager.project_path:
            return None

        project_path = Path(self.project_manager.project_path)

        # Strategy 1 — read results_dir registered in project_data.
        results_dir = self._results_dir_for_subject(subject)
        if results_dir is not None:
            return results_dir

        # Strategy 2 — legacy filesystem scan at project root (pre-hierarchical
        # recordings whose results_dir was never stamped on the video entry).
        pattern_new = re.compile(
            rf"^day{self.day_num}_{re.escape(self.group_name)}_{subject}_\d{{8}}_\d{{6}}$"
        )
        pattern_legacy = re.compile(rf"^D{self.day_num}_G{re.escape(self.group_name)}_S{subject}$")

        for item in project_path.iterdir():
            if not item.is_dir():
                continue
            if pattern_new.match(item.name) or pattern_legacy.match(item.name):
                return item

        return None

    def _results_dir_for_subject(self, subject: str) -> Path | None:
        """Return the registered ``results_dir`` for the (day, group, subject) entry."""
        project_data = (
            self.project_manager.project_data
            if hasattr(self.project_manager, "project_data")
            else {}
        )
        target_day = f"Dia_{self.day_num}"
        for batch in project_data.get("batches", []):
            for video in batch.get("videos", []):
                metadata = video.get("metadata") or {}
                meta_day = str(metadata.get("day", "")).strip()
                if meta_day and meta_day not in (target_day, str(self.day_num)):
                    continue
                if str(metadata.get("group", "")).strip() != str(self.group_name).strip():
                    continue
                if str(metadata.get("subject", "")).strip() != str(subject).strip():
                    continue
                results_dir = video.get("results_dir")
                if results_dir:
                    candidate = Path(results_dir)
                    if candidate.exists() and candidate.is_dir():
                        return candidate
        return None

    def _get_polygon_source_for_subject(self, subject: str) -> str | None:
        """Return the polygon source ("auto" / "manual" / None) recorded for a subject.

        Scans the project's videos for an entry whose metadata matches the
        block's (group, day, subject) tuple. Returns the ``polygon_source``
        field stamped by ``OutputRegistrationManager.register_processing_outputs``
        after the live recording completes, or ``None`` for sessions recorded
        before the field existed.
        """
        project_data = (
            self.project_manager.project_data
            if hasattr(self.project_manager, "project_data")
            else {}
        )
        target_day = f"Dia_{self.day_num}"
        for batch in project_data.get("batches", []):
            for video in batch.get("videos", []):
                metadata = video.get("metadata") or {}
                # Day field uses both "Dia_N" and bare int formats across the codebase
                meta_day = str(metadata.get("day", "")).strip()
                if meta_day and meta_day not in (target_day, str(self.day_num)):
                    continue
                if str(metadata.get("group", "")).strip() != str(self.group_name).strip():
                    continue
                if str(metadata.get("subject", "")).strip() != str(subject).strip():
                    continue
                source = metadata.get("polygon_source")
                if source:
                    return str(source)
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

        status["summary"] = has_summary_excel_output(folder)

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

        # Polygon-source badge: shows whether the polygon used for this
        # subject was auto-detected or manually drawn. For completed sessions
        # we read the value stamped by ``register_processing_outputs``; for
        # pending subjects we hint that the project polygon will be reused.
        if is_completed:
            polygon_source = self._get_polygon_source_for_subject(subject)
            if polygon_source == "auto":
                Label(
                    info_frame,
                    text="🏟️ Auto-detectado",
                    font=("Segoe UI", 8, "bold"),
                    fg="#0a7",
                    bg="white",
                ).pack(anchor="w")
            elif polygon_source == "manual":
                Label(
                    info_frame,
                    text="✏️ Desenhado manualmente",
                    font=("Segoe UI", 8, "bold"),
                    fg="#666",
                    bg="white",
                ).pack(anchor="w")
        elif self._project_has_polygon:
            Label(
                info_frame,
                text="🏟️ Polígono do projeto pronto (será reutilizado)",
                font=("Segoe UI", 8),
                fg="#0a7",
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

    def _format_current_camera(self) -> str:
        """Render the camera label: override (if set) or project default."""
        if self._camera_index_override is not None:
            name = self._camera_friendly_name_override or ""
            suffix = f" — {name}" if name else ""
            return f"[Sessão] Índice {self._camera_index_override}{suffix}"

        project_data = (
            self.project_manager.project_data
            if hasattr(self.project_manager, "project_data")
            else {}
        )
        saved_index = project_data.get("camera_index", 0)
        saved_name = project_data.get("camera_friendly_name", "") or ""
        if saved_name:
            return f"{saved_name} (índice {saved_index})"
        return f"Índice {saved_index}"

    def _open_camera_chooser(self) -> None:
        """Modal sub-dialog: detect + pick a camera (and optionally persist)."""
        # Local imports keep dialog cold-import light.
        from tkinter import BooleanVar, Checkbutton, StringVar

        from zebtrack.core.services.wizard_service import WizardService

        try:
            cameras = WizardService.detect_available_cameras(use_cache=False)
        # except Exception justified: camera enumeration is hardware I/O
        except Exception as exc:
            messagebox.showerror(
                "Falha na detecção",
                f"Não foi possível detectar câmeras:\n\n{exc}",
                parent=self,
            )
            return

        if not cameras:
            messagebox.showwarning(
                "Nenhuma câmera",
                "Nenhuma câmera foi detectada no sistema.",
                parent=self,
            )
            return

        chooser = Toplevel(self)
        chooser.title("Trocar câmera para esta sessão")
        chooser.transient(self)
        chooser.grab_set()

        Label(chooser, text="Selecione a câmera:").grid(
            row=0, column=0, sticky="w", padx=10, pady=(10, 0)
        )

        descriptions = [c.get("description", f"Câmera {c['index']}") for c in cameras]
        index_map = {desc: int(cameras[i]["index"]) for i, desc in enumerate(descriptions)}
        name_map = {
            desc: cameras[i].get("friendly_name", "") for i, desc in enumerate(descriptions)
        }

        selection_var = StringVar(value=descriptions[0])
        combo = ttk.Combobox(
            chooser,
            values=descriptions,
            textvariable=selection_var,
            state="readonly",
            width=60,
        )
        combo.grid(row=1, column=0, columnspan=2, sticky="ew", padx=10, pady=5)

        persist_var = BooleanVar(value=False)
        Checkbutton(
            chooser,
            text="Salvar como câmera padrão deste projeto",
            variable=persist_var,
        ).grid(row=2, column=0, columnspan=2, sticky="w", padx=10, pady=5)

        confirmed = {"ok": False}

        def _on_ok() -> None:
            confirmed["ok"] = True
            chooser.destroy()

        def _on_cancel() -> None:
            chooser.destroy()

        button_row = Frame(chooser)
        button_row.grid(row=3, column=0, columnspan=2, pady=(5, 10))
        Button(button_row, text="OK", command=_on_ok, width=10).pack(side="left", padx=5)
        Button(button_row, text="Cancelar", command=_on_cancel, width=10).pack(side="left", padx=5)

        chooser.wait_window()

        if not confirmed["ok"]:
            return

        chosen = selection_var.get()
        new_index = index_map.get(chosen, 0)
        new_name = name_map.get(chosen, "")

        if persist_var.get():
            try:
                self.project_manager.project_data["camera_index"] = int(new_index)
                self.project_manager.project_data["camera_friendly_name"] = new_name
                if hasattr(self.project_manager, "save_project"):
                    self.project_manager.save_project()
                # Persisted: clear any previous override so the label shows the new default.
                self._camera_index_override = None
                self._camera_friendly_name_override = None
            except (OSError, AttributeError, ValueError) as exc:
                messagebox.showwarning(
                    "Falha ao salvar câmera",
                    f"Não foi possível salvar a câmera como padrão:\n{exc}",
                    parent=self,
                )
                # Fall back to per-session override on save failure.
                self._camera_index_override = int(new_index)
                self._camera_friendly_name_override = new_name
        else:
            self._camera_index_override = int(new_index)
            self._camera_friendly_name_override = new_name

        if self._camera_label is not None:
            self._camera_label.config(text=self._format_current_camera())

    def start_session(self, subject: str):
        """Start live session for subject.

        Args:
            subject: Subject ID to start session for
        """
        log.info(
            "block_detail.start_session",
            day=self.day_num,
            group=self.group_name,
            subject=subject,
            camera_override=self._camera_index_override,
        )

        # v2.3.1: Actually start the session using session_coordinator
        try:
            # Snapshot the override before destroying (instance attrs survive, but be explicit).
            override_index = self._camera_index_override
            override_name = self._camera_friendly_name_override

            # Close dialog first so it doesn't block
            self.destroy()

            # Start the live project session
            success = self.session_coordinator.start_live_project_session(
                day=self.day_num,
                group=str(self.group_name),
                subject=subject,
                camera_index_override=override_index,
                camera_friendly_name_override=override_name,
            )

            if not success:
                # ``start_live_project_session`` returns False in two distinct
                # situations: a genuine failure (camera missing, bad project
                # type) AND the legitimate "deferred awaiting zone confirmation"
                # case after the auto-detect flow approves a polygon. In the
                # deferred case the user has been routed to the zone tab and
                # the LIVE_RECORDING_PENDING banner offers "▶️ Iniciar Gravação"
                # — surfacing an error popup here would be a lie. Probe the
                # calibration coordinator's pending flag to differentiate.
                cal_coord = getattr(self.session_coordinator, "live_calibration_coordinator", None)
                deferred = bool(
                    cal_coord is not None and getattr(cal_coord, "pending_zone_confirmation", False)
                )
                if deferred:
                    log.info(
                        "block_detail.start_session.deferred_for_zones",
                        subject=subject,
                        day=self.day_num,
                        group=self.group_name,
                    )
                else:
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
            from zebtrack.utils.os_opener import open_path

            open_path(session_folder)

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

    def _get_completed_subjects_for_partial_report(self) -> list[str]:
        subjects = [str(i + 1) for i in range(self.subjects_per_group)]
        return [
            subject
            for subject in subjects
            if (self.day_num, self.group_name, subject) in self.completed_sessions
        ]

    def _collect_partial_report_summary_files(
        self, completed_subjects: list[str]
    ) -> list[tuple[str, Path]]:
        summary_files = []
        for subject in completed_subjects:
            session_folder = self._find_session_folder(subject)
            if not session_folder or not session_folder.exists():
                continue

            summary_file = find_summary_excel_file(session_folder)
            if summary_file is not None:
                summary_files.append((subject, summary_file))

        return summary_files

    def _build_partial_report_dataset(self, summary_files: list[tuple[str, Path]]):
        import warnings

        import pandas as pd

        all_data = []
        parsed_summary_files = []
        for subject, summary_path in summary_files:
            try:
                df = pd.read_excel(summary_path)
                df["animal"] = subject
                df["dia"] = self.day_num
                df["grupo"] = self.group_name
                df["source_file"] = summary_path.name
                all_data.append(df)
                parsed_summary_files.append((subject, summary_path))
            except Exception as e:
                log.warning(
                    "block_detail.partial_report.read_failed",
                    summary_path=str(summary_path),
                    error=str(e),
                )

        if not all_data:
            raise ValueError("Nenhum dado válido encontrado nos arquivos de resumo")

        non_empty_dfs = [df for df in all_data if not df.empty]
        if not non_empty_dfs:
            raise ValueError("Nenhum dado válido encontrado (todos os arquivos estavam vazios)")

        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                category=FutureWarning,
                message=".*concatenation with empty or all-NA entries.*",
            )
            unified_df = pd.concat(non_empty_dfs, ignore_index=True)

        return all_data, unified_df, parsed_summary_files

    @staticmethod
    def _get_partial_report_stats_columns(unified_df) -> list[str]:
        import pandas as pd

        return [
            col
            for col in unified_df.columns
            if col != "analysis_timestamp"
            and any(keyword in col.lower() for keyword in ["distance", "speed", "time", "entries"])
            and pd.api.types.is_numeric_dtype(unified_df[col])
        ]

    @staticmethod
    def _format_partial_report_cell_value(value) -> str:
        import pandas as pd

        if pd.isna(value):
            return "-"
        if isinstance(value, int):
            return str(value)
        if isinstance(value, float):
            return str(int(value)) if value.is_integer() else f"{value:.2f}"
        return str(value)

    @staticmethod
    def _build_partial_report_output_paths(
        reports_dir: Path, base_output_name: str
    ) -> tuple[str, Path, str, Path]:
        excel_output_name = f"{base_output_name}.xlsx"
        word_output_name = f"{base_output_name}.docx"
        return (
            excel_output_name,
            reports_dir / excel_output_name,
            word_output_name,
            reports_dir / word_output_name,
        )

    def _write_partial_report_excel(self, path: Path, all_data, unified_df) -> None:
        import pandas as pd

        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            unified_df.to_excel(writer, sheet_name="Dados Consolidados", index=False)

            stats_cols = self._get_partial_report_stats_columns(unified_df)
            if len(all_data) > 1 and stats_cols:
                summary_stats = unified_df.groupby("animal")[stats_cols].mean()
                summary_stats.to_excel(writer, sheet_name="Resumo por Animal")

    def _write_partial_report_word(
        self,
        path: Path,
        excel_name: str,
        parsed_summary_files: list[tuple[str, Path]],
        all_data,
        unified_df,
    ) -> None:
        from docx import Document

        document = Document()
        document.add_heading(
            f"Relatório Parcial - Dia {self.day_num} - {self.group_name}",
            level=1,
        )
        document.add_paragraph(f"Gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
        document.add_paragraph(f"Sessões agregadas: {len(all_data)}")
        document.add_paragraph(f"Planilha consolidada: {excel_name}")

        document.add_heading("Sessões incluídas", level=2)
        session_table = document.add_table(rows=1, cols=2)
        session_table.style = "Table Grid"
        session_table.rows[0].cells[0].text = "Animal"
        session_table.rows[0].cells[1].text = "Arquivo-fonte"

        for subject, summary_path in parsed_summary_files:
            row_cells = session_table.add_row().cells
            row_cells[0].text = str(subject)
            row_cells[1].text = summary_path.name

        stats_cols = self._get_partial_report_stats_columns(unified_df)
        if stats_cols:
            summary_stats = unified_df.groupby("animal")[stats_cols].mean().reset_index()
            document.add_heading("Resumo por Animal", level=2)
            summary_table = document.add_table(rows=1, cols=len(summary_stats.columns))
            summary_table.style = "Table Grid"
            header_cells = summary_table.rows[0].cells
            for idx, column_name in enumerate(summary_stats.columns):
                header_cells[idx].text = str(column_name)

            for _, row_data in summary_stats.iterrows():
                row_cells = summary_table.add_row().cells
                for idx, column_name in enumerate(summary_stats.columns):
                    row_cells[idx].text = self._format_partial_report_cell_value(
                        row_data[column_name]
                    )

        document.save(str(path))

    def _write_partial_report_outputs(
        self,
        reports_dir: Path,
        parsed_summary_files: list[tuple[str, Path]],
        all_data,
        unified_df,
    ) -> tuple[str, Path, str, Path, bool]:
        base_output_name = f"PartialReport_Dia{self.day_num}_{self.group_name}"
        (
            excel_output_name,
            excel_output_path,
            word_output_name,
            word_output_path,
        ) = self._build_partial_report_output_paths(reports_dir, base_output_name)

        write_fallback_used = False
        try:
            self._write_partial_report_excel(excel_output_path, all_data, unified_df)
            self._write_partial_report_word(
                word_output_path,
                excel_output_name,
                parsed_summary_files,
                all_data,
                unified_df,
            )
        except PermissionError:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            fallback_output_name = f"{base_output_name}_{timestamp}"
            (
                excel_output_name,
                excel_output_path,
                word_output_name,
                word_output_path,
            ) = self._build_partial_report_output_paths(reports_dir, fallback_output_name)
            self._write_partial_report_excel(excel_output_path, all_data, unified_df)
            self._write_partial_report_word(
                word_output_path,
                excel_output_name,
                parsed_summary_files,
                all_data,
                unified_df,
            )
            write_fallback_used = True

        return (
            excel_output_name,
            excel_output_path,
            word_output_name,
            word_output_path,
            write_fallback_used,
        )

    def _notify_partial_report_success(
        self,
        excel_output_name: str,
        word_output_name: str,
        session_count: int,
        write_fallback_used: bool,
    ) -> None:
        if write_fallback_used:
            messagebox.showwarning(
                "Arquivo em uso",
                "O arquivo padrão estava bloqueado por outro programa/serviço "
                "de sincronização.\n"
                "Os relatórios foram salvos com novos nomes:\n"
                f"{excel_output_name}\n{word_output_name}",
            )

        messagebox.showinfo(
            "Relatórios Gerados",
            f"Relatórios parciais gerados com sucesso!\n\n"
            f"📊 Excel: {excel_output_name}\n"
            f"📝 Word: {word_output_name}\n"
            f"🐟 {session_count} sessões agregadas",
        )

    def _prompt_open_partial_report_files(
        self,
        excel_output_path: Path,
        excel_output_name: str,
        word_output_path: Path,
        word_output_name: str,
    ) -> None:
        if messagebox.askyesno(
            "Abrir Relatório Parcial",
            f"Deseja abrir a planilha parcial em Excel?\n\n📊 {excel_output_name}",
        ):
            try:
                self._open_generated_report_file(excel_output_path)
            except Exception as e:
                log.warning("block_detail.partial_report.open_failed", error=str(e))
                messagebox.showwarning(
                    "Aviso",
                    "O relatório Excel foi gerado, mas não foi possível abri-lo:\n"
                    f"{excel_output_path}",
                )

        if messagebox.askyesno(
            "Abrir Relatório Parcial",
            f"Deseja abrir o relatório parcial em Word?\n\n📝 {word_output_name}",
        ):
            try:
                self._open_generated_report_file(word_output_path)
            except Exception as e:
                log.warning("block_detail.partial_report.open_failed", error=str(e))
                messagebox.showwarning(
                    "Aviso",
                    "O relatório Word foi gerado, mas não foi possível abri-lo:\n"
                    f"{word_output_path}",
                )

    def generate_partial_report(self):
        """Generate partial report for completed sessions in this block.

        Collects all summary Excel files from completed sessions and aggregates
        them into Excel and Word outputs for the day/group block.
        """
        log.info(
            "block_detail.generate_partial_report",
            day=self.day_num,
            group=self.group_name,
        )

        completed_in_block = self._get_completed_subjects_for_partial_report()

        if not completed_in_block:
            messagebox.showwarning(
                "Sem Sessões",
                f"Nenhuma sessão concluída encontrada para\nDia {self.day_num} - {self.group_name}",
            )
            return

        summary_files = self._collect_partial_report_summary_files(completed_in_block)

        if not summary_files:
            messagebox.showwarning(
                "Sem Relatórios",
                f"Nenhum arquivo de resumo encontrado nas sessões de\n"
                f"Dia {self.day_num} - {self.group_name}\n\n"
                f"Execute a análise das sessões primeiro.",
            )
            return

        try:
            reports_dir = Path(self.project_manager.project_path) / "partial_reports"
            reports_dir.mkdir(parents=True, exist_ok=True)

            all_data, unified_df, parsed_summary_files = self._build_partial_report_dataset(
                summary_files
            )
            (
                excel_output_name,
                excel_output_path,
                word_output_name,
                word_output_path,
                write_fallback_used,
            ) = self._write_partial_report_outputs(
                reports_dir,
                parsed_summary_files,
                all_data,
                unified_df,
            )

            log.info(
                "block_detail.partial_report.success",
                excel_output=str(excel_output_path),
                word_output=str(word_output_path),
                session_count=len(all_data),
            )

            self._publish_project_views_refresh(
                f"Relatórios parciais atualizados: Dia {self.day_num} - {self.group_name}"
            )

            self._notify_partial_report_success(
                excel_output_name,
                word_output_name,
                len(all_data),
                write_fallback_used,
            )
            self._prompt_open_partial_report_files(
                excel_output_path,
                excel_output_name,
                word_output_path,
                word_output_name,
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
        """Mark batch as complete and generate the block partial report.

        Reusa o mesmo gerador do botão "Gerar Relatório Parcial" (Excel +
        Word em ``partial_reports/``), rodando em thread de fundo para
        honrar a promessa de "segundo plano", e persiste a completude do
        lote via ``LiveBatchCoordinator.mark_block_complete`` — o que pinta
        o quadrado do grid de verde e sobrevive ao reinício do app. O
        caminho antigo montava um ``batch_id`` com ``*`` literal que nunca
        casava com os IDs reais e ignorava o retorno, mostrando sucesso sem
        gerar nada.
        """
        # Audit Erro 6 (2026-05-25): make the scope explicit so the user
        # knows exactly which sessions are being consolidated. A "lote" here
        # is all sessions of THIS group on THIS day (one row of the grid),
        # not the whole project.
        result = messagebox.askyesno(
            "Confirmar — Marcar lote como completo",
            (
                f"Marcar o lote do Grupo '{self.group_name}' no Dia {self.day_num} "
                "como completo?\n\n"
                "Escopo: TODAS as sessões já gravadas deste grupo neste dia serão "
                "consolidadas no relatório parcial do bloco (Excel + Word) e o "
                "quadrado correspondente na grade do Progresso ficará verde.\n\n"
                "Esta ação NÃO afeta outros grupos, outros dias, nem encerra o projeto "
                "como um todo. Você poderá continuar gravando novos sujeitos em outros "
                "dias/grupos normalmente.\n\n"
                "Deseja continuar?"
            ),
        )
        if not result:
            return

        # Pré-checagens rápidas na thread da UI — feedback honesto quando não
        # há sessões ou resumos (mesmos textos do "Gerar Relatório Parcial").
        completed_in_block = self._get_completed_subjects_for_partial_report()
        if not completed_in_block:
            messagebox.showwarning(
                "Sem Sessões",
                f"Nenhuma sessão concluída encontrada para\nDia {self.day_num} - {self.group_name}",
            )
            return

        summary_files = self._collect_partial_report_summary_files(completed_in_block)
        if not summary_files:
            messagebox.showwarning(
                "Sem Relatórios",
                f"Nenhum arquivo de resumo encontrado nas sessões de\n"
                f"Dia {self.day_num} - {self.group_name}\n\n"
                f"Execute a análise das sessões primeiro.",
            )
            return

        master = self.master  # root Tk — sobrevive ao destroy deste Toplevel
        day_num = self.day_num
        group_name = self.group_name

        def _worker() -> None:
            try:
                all_data, unified_df, parsed_summary_files = self._build_partial_report_dataset(
                    summary_files
                )
                reports_dir = Path(self.project_manager.project_path) / "partial_reports"
                reports_dir.mkdir(parents=True, exist_ok=True)
                (
                    excel_output_name,
                    excel_output_path,
                    word_output_name,
                    _word_output_path,
                    write_fallback_used,
                ) = self._write_partial_report_outputs(
                    reports_dir,
                    parsed_summary_files,
                    all_data,
                    unified_df,
                )

                persisted = self.live_batch_coordinator.mark_block_complete(
                    group_name,
                    day_num,
                    unified_excel=excel_output_path,
                    session_count=len(all_data),
                )

                log.info(
                    "block_detail.mark_batch_complete.success",
                    day=day_num,
                    group=group_name,
                    excel_output=str(excel_output_path),
                    session_count=len(all_data),
                    persisted=persisted,
                )

                def _on_done() -> None:
                    # _publish_project_views_refresh só publica eventos via
                    # coordinators (não toca Tk), seguro após o destroy.
                    self._publish_project_views_refresh(
                        f"Lote concluído: Dia {day_num} - {group_name}"
                    )
                    message = (
                        f"Lote 'Dia {day_num} - {group_name}' marcado como completo.\n\n"
                        f"📊 Excel: {excel_output_name}\n"
                        f"📝 Word: {word_output_name}\n"
                        f"🐟 {len(all_data)} sessões agregadas\n\n"
                        f"Relatórios em: {reports_dir}"
                    )
                    if write_fallback_used:
                        message += (
                            "\n\n⚠️ O arquivo padrão estava em uso; os relatórios "
                            "foram salvos com sufixo de data/hora."
                        )
                    if not persisted:
                        message += (
                            "\n\n⚠️ Não foi possível registrar a completude no "
                            "projeto; verifique o log."
                        )
                    messagebox.showinfo("Lote Completo", message, parent=master)

                master.after(0, _on_done)
            # except Exception justified: pipeline pandas/docx em thread de
            # fundo — qualquer falha deve virar feedback honesto na UI.
            except Exception as e:
                # O Python apaga ``e`` ao sair do except; a closure roda
                # depois (via after), então captura o texto agora.
                error_text = str(e)
                log.error(
                    "block_detail.mark_batch_complete.worker_failed",
                    day=day_num,
                    group=group_name,
                    error=error_text,
                    exc_info=True,
                )

                def _on_error() -> None:
                    messagebox.showerror(
                        "Erro — Lote não concluído",
                        (
                            f"Falha ao gerar o relatório do lote "
                            f"'Dia {day_num} - {group_name}':\n{error_text}\n\n"
                            "O lote NÃO foi marcado como completo."
                        ),
                        parent=master,
                    )

                master.after(0, _on_error)

        threading.Thread(target=_worker, name="MarkBatchComplete", daemon=True).start()
        messagebox.showinfo(
            "Lote em processamento",
            (
                f"Lote 'Dia {self.day_num} - {self.group_name}': o relatório "
                "consolidado (Excel + Word) está sendo gerado em segundo plano.\n\n"
                "Você será avisado quando terminar."
            ),
        )
        self.destroy()
