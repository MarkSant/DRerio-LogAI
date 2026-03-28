"""Dialog management for ApplicationGUI.

Extracted from gui.py to reduce God Object complexity.
Handles messagebox wrappers, file dialogs, custom dialogs, and user confirmations.
"""

from __future__ import annotations

import os
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog
from typing import TYPE_CHECKING, Any, Literal

import structlog

# Dialogs are imported locally within methods to avoid circular dependencies

log = structlog.get_logger()

if TYPE_CHECKING:
    from zebtrack.core.services.zone_context_service import ZoneContextService

if not hasattr(os, "startfile"):
    os.startfile = None  # type: ignore[attr-defined,assignment]


class DialogManager:
    """Manages dialogs and user interactions for ApplicationGUI."""

    def __init__(
        self, gui, event_bus_v2=None, *, zone_context_service: ZoneContextService | None = None
    ):
        """Initialize DialogManager.

        Args:
            gui: Reference to ApplicationGUI instance
            event_bus_v2: EventBusV2 instance for v4.0 Event-Driven Architecture (optional)
            zone_context_service: Optional ZoneContextService for dependency injection.
        """
        self.gui = gui
        self.event_bus_v2 = event_bus_v2
        self._zone_context_service = zone_context_service
        self._suppress_batch_dialogs: bool = False

    @property
    def zone_context_service(self):
        """ZoneContextService instance (injected or resolved from gui)."""
        if self._zone_context_service is not None:
            return self._zone_context_service
        return getattr(self.gui, "_zone_context_service", None)

    # =========================================================================
    # Batch Dialog Suppression
    # =========================================================================

    def set_dialog_suppression(self, suppress: bool) -> None:
        """Enable or disable batch dialog suppression.

        When suppressed, show_info/show_warning/show_error will log the
        message and update the status bar instead of opening a modal
        messagebox.  This prevents blocking dialogs during batch
        video processing.

        Args:
            suppress: True to suppress dialogs, False to restore normal behavior.
        """
        self._suppress_batch_dialogs = suppress
        log.info(
            "dialog_manager.suppression_changed",
            suppress=suppress,
        )

    # =========================================================================
    # MessageBox Wrappers
    # =========================================================================

    def show_error(self, title: str, message: str) -> None:
        """Show an error message box.

        When batch dialog suppression is active, logs the error and
        updates the status bar instead of opening a modal dialog.

        Args:
            title: Dialog title
            message: Error message to display
        """
        if self._suppress_batch_dialogs:
            log.warning(
                "dialog_manager.show_error.suppressed",
                title=title,
                message=message,
            )
            self._update_status_bar(f"[Erro] {title}: {message}")
            return
        messagebox.showerror(title, message)

    def show_warning(self, title: str, message: str) -> None:
        """Show a warning message box.

        When batch dialog suppression is active, logs the warning and
        updates the status bar instead of opening a modal dialog.

        Args:
            title: Dialog title
            message: Warning message to display
        """
        if self._suppress_batch_dialogs:
            log.warning(
                "dialog_manager.show_warning.suppressed",
                title=title,
                message=message,
            )
            self._update_status_bar(f"[Aviso] {title}: {message}")
            return
        messagebox.showwarning(title, message)

    def show_info(self, title: str, message: str) -> None:
        """Show an info message box.

        When batch dialog suppression is active, logs the info and
        updates the status bar instead of opening a modal dialog.

        Args:
            title: Dialog title
            message: Info message to display
        """
        if self._suppress_batch_dialogs:
            log.info(
                "dialog_manager.show_info.suppressed",
                title=title,
                message=message,
            )
            self._update_status_bar(f"{title}: {message}")
            return
        messagebox.showinfo(title, message)

    def _update_status_bar(self, text: str) -> None:
        """Update the GUI status bar with a message (truncated to 200 chars).

        Used as a non-blocking alternative to modal dialogs during batch
        processing.
        """
        truncated = text[:200] if len(text) > 200 else text
        try:
            if self.gui and hasattr(self.gui, "status_var"):
                self.gui.status_var.set(truncated)
        except Exception:
            log.debug("dialog_manager._update_status_bar.failed", text=truncated)

    def ask_ok_cancel(self, title: str, message: str) -> bool:
        """Show a confirmation dialog with OK/Cancel buttons.

        Args:
            title: Dialog title
            message: Confirmation message

        Returns:
            True if OK was clicked, False otherwise
        """
        return messagebox.askokcancel(title, message)

    def ask_yes_no(
        self,
        title: str,
        message: str,
        *,
        icon: Literal["error", "info", "question", "warning"] = "question",
    ) -> bool:
        """Show a confirmation dialog with Yes/No buttons.

        Args:
            title: Dialog title
            message: Confirmation message
            icon: Icon type (question, warning, info, error)

        Returns:
            True if Yes was clicked, False otherwise
        """
        return messagebox.askyesno(title, message, icon=icon)

    def ask_yes_no_cancel(
        self,
        title: str,
        message: str,
        *,
        icon: Literal["error", "info", "question", "warning"] = "question",
    ) -> bool | None:
        """Show a confirmation dialog with Yes/No/Cancel buttons.

        Args:
            title: Dialog title
            message: Confirmation message
            icon: Icon type (question, warning, info, error)

        Returns:
            True if Yes, False if No, None if Cancel
        """
        return messagebox.askyesnocancel(title, message, icon=icon)

    # =========================================================================
    # File Dialogs
    # =========================================================================

    def ask_directory(self, title: str, initial_dir: Path | str | None = None) -> str:
        """Show a dialog to select a directory.

        Args:
            title: Dialog title
            initial_dir: Initial directory to open (optional)

        Returns:
            Selected directory path or empty string if cancelled
        """
        kwargs: dict[str, Any] = {"title": title}
        if initial_dir:
            kwargs["initialdir"] = initial_dir
        return filedialog.askdirectory(**kwargs)

    def ask_open_filename(
        self,
        title: str,
        filetypes: list[tuple[str, str]],
        initial_dir: Path | str | None = None,
    ) -> str:
        """Show a dialog to select a single file.

        Args:
            title: Dialog title
            filetypes: List of (description, pattern) tuples
            initial_dir: Initial directory to open (optional)

        Returns:
            Selected file path or empty string if cancelled
        """
        kwargs: dict[str, Any] = {"title": title, "filetypes": filetypes}
        if initial_dir:
            kwargs["initialdir"] = initial_dir
        return filedialog.askopenfilename(**kwargs)

    def ask_open_filenames(
        self,
        title: str,
        filetypes: list[tuple[str, str]],
        initial_dir: Path | str | None = None,
    ) -> tuple[str, ...]:
        """Show a dialog to select one or more files.

        Args:
            title: Dialog title
            filetypes: List of (description, pattern) tuples
            initial_dir: Initial directory to open (optional)

        Returns:
            Tuple of selected file paths or empty tuple if cancelled
        """
        kwargs: dict[str, Any] = {"title": title, "filetypes": filetypes}
        if initial_dir:
            kwargs["initialdir"] = initial_dir
        result = filedialog.askopenfilenames(**kwargs)
        if isinstance(result, str) and not result:
            return ()
        return result

    def ask_save_filename(self, **options) -> str:
        """Show a dialog to select a save file path.

        Args:
            **options: Keyword arguments passed to asksaveasfilename
                      (title, filetypes, initialdir, defaultextension, etc.)

        Returns:
            Selected file path or empty string if cancelled
        """
        return filedialog.asksaveasfilename(**options)

    def ask_string(self, title: str, prompt: str, initialvalue: str | None = None) -> str | None:
        """Show a dialog for string input.

        Args:
            title: Dialog title
            prompt: Prompt message
            initialvalue: Initial value (optional)

        Returns:
            Input string or None if cancelled
        """
        return simpledialog.askstring(title, prompt, initialvalue=initialvalue)

        # =========================================================================
        # Custom Dialogs - Calibration
        # =========================================================================

    def open_global_calibration_window(self) -> None:
        """Open the global calibration dialog."""
        from zebtrack.ui.dialogs.calibration_dialog import CalibrationDialog

        with self.gui.controller.global_calibration_session():
            CalibrationDialog(self.gui.root, self.gui.controller)

    def open_project_calibration_window(self) -> None:
        """Open the project-specific calibration dialog.

        Shows warning if no project is loaded.
        """
        if not getattr(self.gui.controller.project_manager, "project_path", None):
            self.show_warning(
                "Nenhum Projeto",
                "Abra um projeto antes de ajustar a calibração específica.",
            )
            return

        from zebtrack.ui.dialogs.calibration_dialog import CalibrationDialog

        with self.gui.controller.project_calibration_session():
            CalibrationDialog(self.gui.root, self.gui.controller)
        self.gui.weight_hardware_manager.update_openvino_checkbox(
            self.gui.controller.hardware_vm.use_openvino
        )
        self.gui.weight_hardware_manager.set_active_weight_in_dropdown(
            self.gui.controller.hardware_vm.active_weight_name
        )
        self.gui.weight_hardware_manager.update_openvino_status_display(
            self.gui.controller.hardware_vm.get_openvino_status()
        )

    # =========================================================================
    # Custom Dialogs - ROI Templates
    # =========================================================================

    def show_template_save_dialog(
        self,
        *,
        has_arena: bool,
        has_rois: bool,
        allow_project: bool,
        initial_name: str,
    ) -> dict[str, Any] | None:
        """Show dialog to save ROI template.

        Args:
            has_arena: Whether current context has arena
            has_rois: Whether current context has ROIs
            allow_project: Whether to allow project-level save
            initial_name: Initial name suggestion

        Returns:
            Dialog result dict with user choices, or None if cancelled
        """
        from zebtrack.ui.dialogs.save_roi_template_dialog import SaveROITemplateDialog

        dialog = SaveROITemplateDialog(
            self.gui.root,
            default_name=initial_name,
            has_arena=has_arena,
            has_rois=has_rois,
            allow_project=allow_project,
        )

        if not dialog.result:
            return None

        return dialog.result

    def import_roi_template(self) -> None:
        """Import a template file into the library (does not apply it)."""
        pm = getattr(self.gui.controller, "project_manager", None)
        if pm is None:
            return

        file_path = self.ask_open_filename(
            title="Importar Template de ROI para Biblioteca",
            filetypes=[("Templates de ROI", "*.json"), ("Todos os arquivos", "*.*")],
        )
        if not file_path:
            return

        try:
            metadata = pm.import_roi_template(file_path)
        except Exception as exc:  # pragma: no cover - defensive
            log.error("gui.roi_templates.import_failed", error=str(exc), file=file_path)
            self.show_error("Erro ao importar", str(exc))
            return

        self.gui.roi_template_manager.refresh_templates()
        self.gui.roi_template_manager.select_template_by_metadata(metadata)
        template_name = metadata.get("name", Path(file_path).stem)
        message = (
            f"Template '{template_name}' adicionado à biblioteca.\n\n"
            "Use o botão 'Aplicar' para usar este template."
        )
        self.show_info("Template importado", message)

    def import_and_apply_roi_template(self) -> None:
        """Import a template file and immediately apply it to current video."""
        pm = getattr(self.gui.controller, "project_manager", None)
        if pm is None:
            return

        file_path = self.ask_open_filename(
            title="Importar e Aplicar Template de ROI",
            filetypes=[("Templates de ROI", "*.json"), ("Todos os arquivos", "*.*")],
        )
        if not file_path:
            return

        # Get active video context
        active_video = pm.get_active_zone_video()
        if not active_video:
            pending_video = getattr(self.gui, "pending_single_video_path", None)
            if pending_video:
                try:
                    pm.set_active_zone_video(pending_video)
                except Exception as exc:  # pragma: no cover - defensive
                    log.warning(
                        "gui.roi_templates.activate_pending_failed",
                        error=str(exc),
                        video=pending_video,
                    )
                active_video = pm.get_active_zone_video() or pending_video

        if not active_video:
            self.show_warning(
                "Vídeo não selecionado",
                "Selecione um vídeo antes de aplicar o template.",
            )
            return

        try:
            # Load template directly from file
            import json

            with open(file_path, encoding="utf-8") as f:
                template_data = json.load(f)

            # Convert to ZoneData
            from zebtrack.core.detection import ZoneData

            template_zone = ZoneData(
                polygon=template_data.get("polygon"),
                roi_polygons=template_data.get("roi_polygons", []),
                roi_names=template_data.get("roi_names", []),
                roi_colors=template_data.get("roi_colors", []),
            )

            # Save to project
            pm.save_zone_data(
                template_zone,
                video_path=active_video,
                persist=bool(pm.project_path),
            )

            if active_video:
                pm.set_active_zone_video(active_video)

            self.gui.controller.setup_detector_zones()

            log.info(
                "gui.roi_templates.imported_and_applied",
                video=active_video,
                file=file_path,
                polygon_points=len(template_zone.polygon or []),
                roi_count=len(template_zone.roi_polygons or []),
            )

        except Exception as exc:  # pragma: no cover - defensive
            log.error(
                "gui.roi_templates.import_and_apply_failed",
                error=str(exc),
                file=file_path,
            )
            self.show_error("Erro ao importar e aplicar", str(exc))
            return

        # NEW PATH - Event-Driven Architecture v4.0
        if self.event_bus_v2:
            from zebtrack.ui.event_bus_v2 import Event, UIEvents

            self.event_bus_v2.publish(
                Event(
                    type=UIEvents.ZONES_UPDATED,
                    data={"zone_data": None},
                    source="DialogManager.import_and_apply_template",
                )
            )
        else:
            log.warning("gui.roi_templates.import_and_apply.no_event_bus")
            # Fallback for legacy mode if event bus is missing
            if hasattr(self.gui, "canvas_manager"):
                self.gui.canvas_manager.redraw_zones_from_project_data()
            if hasattr(self.gui, "canvas_manager"):
                self.gui.canvas_manager.redraw_zones_from_project_data()
            if hasattr(self.gui, "canvas_manager"):
                self.gui.canvas_manager.update_roi_button_state()

        # Import to library and update dropdown
        template_name = Path(file_path).stem
        try:
            metadata = pm.import_roi_template(file_path)
            self.gui.roi_template_manager.refresh_templates()
            self.gui.roi_template_manager.select_template_by_metadata(metadata)
            template_name = metadata.get("name", template_name)
            log.info(
                "gui.roi_templates.import_and_apply.library_updated",
                template_name=template_name,
            )
        except Exception as exc:  # pragma: no cover - if import fails, we still applied
            log.warning(
                "gui.roi_templates.import_and_apply.library_import_failed",
                error=str(exc),
                template_name=template_name,
            )
            # Still refresh templates to update display
            self.gui.roi_template_manager.refresh_templates()

        self.show_info(
            "Template aplicado",
            f"As zonas foram atualizadas com o template '{template_name}'.",
        )

    # =========================================================================
    # Custom Dialogs - Analysis
    # =========================================================================

    def open_center_periphery_dialog(self) -> dict[str, Any] | None:
        """Open the center-periphery analysis dialog.

        Returns:
            Dialog result with method and value, or None if cancelled
        """
        from zebtrack.ui.dialogs.center_periphery_dialog import CenterPeripheryDialog

        dialog = CenterPeripheryDialog(self.gui.root)
        return dialog.result if dialog.result else None

    def open_template_rois_dialog(self) -> dict[str, Any] | None:
        """Open the dialog to create ROIs from a template.

        Returns:
            Dialog result with template type and parameters, or None if cancelled
        """
        from zebtrack.ui.dialogs.template_dialog import TemplateDialog

        dialog = TemplateDialog(self.gui.root)
        return dialog.result if dialog.result else None

    def open_single_video_config_dialog(self) -> dict[str, Any] | None:
        """Open the single video configuration dialog.

        Returns:
            Dialog result with video config, or None if cancelled
        """
        from zebtrack.ui.dialogs.single_video_config_dialog import SingleVideoConfigDialog

        dialog = SingleVideoConfigDialog(
            self.gui.root,
            settings_obj=self.gui.controller.settings,
            event_bus=self.gui.event_bus,
        )
        return dialog.result if dialog.result else None

    def show_aquarium_assignment_dialog(
        self,
        *,
        available_groups: list[str],
        video_path: str | None = None,
        multi_aquarium_config: Any = None,
        on_confirm: Any = None,
        on_cancel: Any = None,
    ) -> tuple[Any, bool]:
        """Show dialog for assigning groups to aquariums.

        Returns:
            Tuple of (configs, apply_to_all) or (None, False) if cancelled.
        """
        from zebtrack.ui.dialogs.aquarium_assignment_dialog import AquariumAssignmentDialog

        dialog = AquariumAssignmentDialog(
            parent=self.gui.root,
            available_groups=available_groups,
            video_path=video_path,
            multi_aquarium_config=multi_aquarium_config,
            on_confirm=on_confirm,
            on_cancel=on_cancel,
        )
        return dialog.get_result()

    # =========================================================================
    # Custom Dialogs - Project & Recording
    # =========================================================================

    def show_pending_videos_dialog(
        self,
        *,
        ready_with_trajectory: list[dict],
        ready_with_zones: list[dict],
        arena_only: list[dict],
        without_arena: list[dict],
    ) -> dict | None:
        """Show the hierarchical pending videos dialog.

        Args:
            ready_with_trajectory: Videos with complete trajectory data
            ready_with_zones: Videos with zones but no trajectory
            arena_only: Videos with arena only
            without_arena: Videos without arena

        Returns:
            Dialog result with selected videos, or None if cancelled
        """
        # NEW PATH - Event-Driven Architecture v4.0
        if self.event_bus_v2:
            from zebtrack.ui.event_bus_v2 import Event, UIEvents

            self.event_bus_v2.publish(
                Event(
                    type=UIEvents.READINESS_SNAPSHOT_UPDATED,
                    data={
                        "ready_with_trajectory": ready_with_trajectory,
                        "ready_with_zones": ready_with_zones,
                        "arena_only": arena_only,
                        "without_arena": without_arena,
                    },
                    source="DialogManager.ask_reuse_zones",
                )
            )
        else:
            log.warning("dialog_manager.readiness_snapshot.no_event_bus")

        from zebtrack.ui.dialogs.pending_videos_dialog import PendingVideosDialog

        dialog = PendingVideosDialog(
            self.gui.root,
            hierarchy_builder=self.gui.validation_manager.build_video_hierarchy_snapshot,
            ready_with_trajectory=ready_with_trajectory,
            ready_with_zones=ready_with_zones,
            arena_only=arena_only,
            without_arena=without_arena,
        )

        return dialog.result

    def ask_recording_details_unified(self) -> dict[str, Any] | None:
        """Show a unified dialog to get day, group, and subject.

        Returns:
            Dialog result with recording metadata, or None if cancelled
        """
        # Check if it's a live project with the necessary config
        pm = self.gui.controller.project_manager
        if not pm.project_data.get("experiment_days"):
            self.show_error(
                "Error",
                "This project is not configured for live experimental tracking.",
            )
            return None

        from zebtrack.ui.dialogs.start_recording_dialog import StartRecordingDialog

        dialog = StartRecordingDialog(self.gui.root, pm)
        return dialog.result

    def ask_missing_metadata(self, experiment_id: str) -> dict[str, Any] | None:
        """Show a dialog to get missing metadata from the user.

        Args:
            experiment_id: The experiment ID needing metadata

        Returns:
            Dialog result with metadata, or None if cancelled
        """
        from zebtrack.ui.dialogs.missing_metadata_dialog import MissingMetadataDialog

        dialog = MissingMetadataDialog(self.gui.root, experiment_id)
        return dialog.result

    def open_project_workflow(self) -> None:
        """Handle the UI part of opening a project, then call the controller."""
        project_path = self.ask_directory(title="Selecione uma Pasta de Projeto Existente")
        if not project_path:
            return

        from zebtrack.ui.event_bus_v2 import UIEvents

        self.gui.event_dispatcher.publish_event(
            UIEvents.PROJECT_OPEN,
            {"project_path": project_path},
        )

    def handle_grid_cell_click(self, day: int, group_name: str) -> None:
        """Handle click on a cell in the experimental progress grid.

        Args:
            day: Day number
            group_name: Group name
        """
        # v2.3.0: Use BlockDetailDialog for batch-aware session management
        from zebtrack.ui.dialogs.block_detail_dialog import BlockDetailDialog

        live_batch_coordinator = getattr(self.gui.controller, "live_batch_coordinator", None)
        # Phase 4.7: Use live_camera_session_coordinator instead of session_coordinator
        session_coordinator = getattr(self.gui.controller, "live_camera_session_coordinator", None)

        if not live_batch_coordinator or not session_coordinator:
            # Fallback to legacy SubjectSelectionDialog if coordinators not available
            pm = self.gui.controller.project_manager
            subjects_per_group = pm.project_data.get("subjects_per_group", 0)
            completed_sessions = pm.get_completed_sessions()
            completed_subjects = {
                s for (d, g, s) in completed_sessions if d == day and g == group_name
            }

            from zebtrack.ui.dialogs.subject_selection_dialog import SubjectSelectionDialog

            dialog: Any = SubjectSelectionDialog(
                self.gui.root, day, group_name, subjects_per_group, completed_subjects
            )

            if dialog.result:
                subject_id = dialog.result
                project_type = pm.get_project_type()

                if project_type == "live":
                    success = self.gui.controller.hardware_vm.start_live_project_session(
                        day=day,
                        group=group_name,
                        subject=str(subject_id),
                    )

                    if not success:
                        self.show_error(
                            "Erro na Gravação",
                            f"Falha ao iniciar sessão de gravação para {group_name}/{subject_id}.",
                        )
                else:
                    # Legacy path for pre-recorded projects
                    self.gui.controller.hardware_vm.start_recording(
                        day=day, group=group_name, cobaia=str(subject_id)
                    )

                self.gui.widget_factory.render_progress_grid()
            return

        # New v2.3.0 path: Open BlockDetailDialog with batch integration
        dialog = BlockDetailDialog(
            self.gui.root,
            day,
            group_name,
            self.gui.controller.project_manager,
            session_coordinator,
            live_batch_coordinator,
        )

        # Dialog handles all session start/stop/batch actions internally
        # Refresh grid after dialog closes to reflect any changes
        self.gui.widget_factory.render_progress_grid()

    # =========================================================================
    # Confirmation Dialogs
    # =========================================================================

    def confirm_delete_roi_template(
        self, template_name: str, template_file: str, template_location: str
    ) -> bool:
        """Confirm deletion of an ROI template.

        Args:
            template_name: Name of the template
            template_file: File path of the template
            template_location: Location description (global/project)

        Returns:
            True if user confirmed deletion, False otherwise
        """
        return self.ask_yes_no(
            "Confirmar Deleção",
            f"Tem certeza que deseja deletar o template '{template_name}'?\n\n"
            f"Localização: {template_location}\n"
            f"Arquivo: {template_file}\n\n"
            f"Esta ação não pode ser desfeita.",
            icon="warning",
        )

    def confirm_remove_roi(self, roi_name: str) -> bool:
        """Confirm removal of an ROI.

        Args:
            roi_name: Name of the ROI to remove

        Returns:
            True if user confirmed removal, False otherwise
        """
        return self.ask_yes_no(
            "Confirmar Remoção",
            f"Tem certeza que deseja remover a ROI '{roi_name}'?\n\n"
            "Esta ação não pode ser desfeita.",
            icon="warning",
        )

    def confirm_save_polygon_before_analysis(self) -> bool | None:
        """Confirm whether to save polygon changes before starting analysis.

        Returns:
            True to save and proceed, False to discard and proceed, None to cancel
        """
        return self.ask_yes_no_cancel(
            "Salvar Polígono?",
            "Você deseja salvar as alterações no polígono antes de iniciar a "
            "análise?\n\n"
            "Sim: Salvar e iniciar análise\n"
            "Não: Descartar alterações e iniciar análise\n"
            "Cancelar: Voltar para edição",
        )

    def confirm_pending_zone_edit_before_navigation(self, *, context: str) -> bool | None:
        """Confirm whether to save pending zone edits before navigation.

        Args:
            context: Human-readable navigation context (e.g., "abrir outro vídeo")

        Returns:
            True to save and proceed, False to discard and proceed, None to cancel navigation
        """
        return self.ask_yes_no_cancel(
            "Salvar edição de zonas?",
            "Há um desenho/edição de zona em andamento.\n\n"
            f"Deseja salvar antes de {context}?\n\n"
            "Sim: Salvar alterações e continuar\n"
            "Não: Descartar alterações e continuar\n"
            "Cancelar: Permanecer no vídeo atual",
            icon="warning",
        )

    # =========================================================================
    # Notification Dialogs
    # =========================================================================

    def show_external_trigger_notice(self, session_label: str, **details) -> None:
        """Show a notice that the system is waiting for external trigger.

        Args:
            session_label: Label for the session (e.g., "gravação")
            **details: Additional details (day, group, cobaia, port)
        """
        if not self.gui.external_trigger_notice_label:
            return

        day = details.get("day")
        group = details.get("group")
        cobaia = details.get("cobaia")
        port = details.get("port")

        descriptors = []
        if day is not None and group is not None and cobaia is not None:
            day_display = day
            formatted_day = None
            if getattr(self.gui, "validation_manager", None):
                try:
                    formatted_day = self.gui.validation_manager._format_day_display(day)
                except Exception:
                    formatted_day = None
            if isinstance(formatted_day, str) and formatted_day.strip():
                day_display = formatted_day
            else:
                try:
                    day_display = f"{int(day):02d}"
                except (TypeError, ValueError):
                    day_display = str(day)
            descriptors.append(f"Dia {day_display}, Grupo {group}, Sujeito {cobaia}")
        if port:
            descriptors.append(f"Porta {port}")

        message = f"Aguardando sinal externo para iniciar {session_label}."
        if descriptors:
            message += f" ({' • '.join(descriptors)})"

        self.gui.external_trigger_notice_var.set(message)

        highlight_bg = "#FFF7ED"
        highlight_fg = "#92400e"
        try:
            self.gui.external_trigger_notice_label.config(
                background=highlight_bg,
                foreground=highlight_fg,
            )
        except Exception:
            log.debug("dialog_manager.trigger_notice_highlight.suppressed", exc_info=True)

    def clear_external_trigger_notice(self) -> None:
        """Clear the external trigger notice."""
        if not self.gui.external_trigger_notice_label:
            return

        self.gui.external_trigger_notice_var.set("")

        try:
            bg = (
                self.gui._external_notice_default_bg
                if self.gui._external_notice_default_bg is not None
                else self.gui.external_trigger_notice_label.cget("background")
            )
            fg = (
                self.gui._external_notice_default_fg
                if self.gui._external_notice_default_fg is not None
                else self.gui.external_trigger_notice_label.cget("foreground")
            )
            self.gui.external_trigger_notice_label.config(background=bg, foreground=fg)
        except Exception:
            log.debug("dialog_manager.trigger_notice_clear.suppressed", exc_info=True)

    # =========================================================================
    # Utility Dialogs & Helpers
    # =========================================================================

    def show_progress_bar(self) -> None:
        """Show the progress bar frame and cancel button."""
        if (
            self.gui.analysis_display_widget
            and self.gui.analysis_display_widget.progress_frame
            and not self.gui.analysis_display_widget.progress_frame.winfo_viewable()
        ):
            # Pack progress_frame BEFORE video_container to ensure it stays visible
            if self.gui.analysis_display_widget.video_container and hasattr(
                self.gui.analysis_display_widget, "video_container"
            ):
                self.gui.analysis_display_widget.progress_frame.pack(
                    before=self.gui.analysis_display_widget.video_container,
                    pady=5,
                    fill="x",
                    padx=10,
                )
                # Force layout recalculation after showing progress bar
                self.gui.root.update_idletasks()
            else:
                self.gui.analysis_display_widget.progress_frame.pack(pady=5, fill="x", padx=10)
            self.gui.analysis_display_widget.progress_bar["value"] = 0
        if self.gui.analysis_display_widget and self.gui.analysis_display_widget.cancel_btn:
            self.gui.analysis_display_widget.cancel_btn.config(state="normal")

    def open_path_in_explorer(self, target_path: Path | str) -> None:
        """Open the given directory in the user's file explorer.

        Args:
            target_path: Path to open in file explorer
        """
        try:
            from zebtrack.utils.os_opener import open_path

            open_path(target_path)
        except Exception as exc:  # pragma: no cover - GUI feedback
            self.show_error(
                "Erro ao abrir pasta",
                (
                    "Não foi possível abrir o diretório de resultados.\n"
                    f"Caminho: {target_path}\n\nDetalhes: {exc}"
                ),
            )

    def offer_zone_reuse(self, video_path: Path | str) -> None:
        """Prompt user to reuse the last zones when the current video has none.

        Args:
            video_path: Path to the video that needs zone data
        """
        if not video_path:
            return

        if video_path in self.gui._zone_prompt_history:
            return

        pm = self.gui.controller.project_manager
        if pm.has_zone_data(video_path):
            return

        last_video_with_zones = pm.get_last_zone_video(exclude=video_path)
        if not last_video_with_zones or not pm.has_zone_data(last_video_with_zones):
            return

        self.gui._zone_prompt_history.add(video_path)

        current_name = os.path.basename(video_path)
        last_name = os.path.basename(last_video_with_zones)

        reuse = messagebox.askyesno(
            "Reutilizar zonas existentes?",
            (
                f'O vídeo "{current_name}" não possui arena ou ROIs salvas.\n\n'
                f'Deseja reutilizar as zonas desenhadas para "{last_name}"?\n'
                'Escolha "Sim" para reutilizar ou "Não" para começar do zero.'
            ),
            icon="question",
        )

        if reuse:
            cloned_zone_data = pm.clone_zone_data_from_video(last_video_with_zones)
            pm.save_zone_data(cloned_zone_data, video_path=video_path, persist=False)
            copied_files = pm.copy_zone_parquet_files(
                last_video_with_zones, video_path, persist=False
            )
            pm.save_project()

            status_message = f'Zonas reutilizadas de "{last_name}" para "{current_name}".'
            self.gui.set_status(status_message)
            self.show_warning(
                "Zonas reutilizadas",
                (
                    f'As zonas de "{last_name}" foram aplicadas em "{current_name}".\n\n'
                    "Revise os contornos antes de iniciar a análise para garantir que "
                    "correspondem ao vídeo atual."
                ),
            )

            if self.event_bus_v2:
                from zebtrack.ui.event_bus_v2 import Event, UIEvents

                self.event_bus_v2.publish(
                    Event(
                        type=UIEvents.ZONES_UPDATED,
                        data={"zone_data": None},
                        source="DialogManager.offer_zone_reuse",
                    )
                )
                self.event_bus_v2.publish(
                    Event(
                        type=UIEvents.VIDEO_TREE_REFRESH_REQUESTED,
                        data={"filter_text": None},
                        source="DialogManager.offer_zone_reuse",
                    )
                )
                self.event_bus_v2.publish(
                    Event(
                        type=UIEvents.PROJECT_VIEWS_REFRESH_REQUESTED,
                        data={"reason": status_message, "append_summary": True},
                        source="DialogManager.offer_zone_reuse",
                    )
                )

            if not copied_files:
                self.show_warning(
                    "Arquivos Parquet Indisponíveis",
                    (
                        "As zonas foram copiadas, mas não encontramos os arquivos "
                        "Parquet originais para duplicar. Caso necessário, redesenhe "
                        "as zonas e salve-as manualmente para gerar novos arquivos."
                    ),
                )
        else:
            pm.clear_zone_data_for_video(video_path, persist=False)
            status_message = "Comece a desenhar a arena e as ROIs para este vídeo."
            self.gui.set_status(status_message)

            if self.event_bus_v2:
                from zebtrack.ui.event_bus_v2 import Event, UIEvents

                self.event_bus_v2.publish(
                    Event(
                        type=UIEvents.PROJECT_VIEWS_REFRESH_REQUESTED,
                        data={"reason": status_message, "append_summary": True},
                        source="DialogManager.offer_zone_reuse",
                    )
                )
                self.event_bus_v2.publish(
                    Event(
                        type=UIEvents.VIDEO_TREE_REFRESH_REQUESTED,
                        data={"filter_text": None},
                        source="DialogManager.offer_zone_reuse",
                    )
                )

    def change_roi_color(self):
        """Change the color of the selected ROI."""
        from zebtrack.ui.dialogs.color_selection_dialog import ColorSelectionDialog

        selected = self.gui.zone_listbox.selection()
        if not selected:
            return

        item = self.gui.zone_listbox.item(selected[0])
        old_name = item["values"][0].replace("📍 ", "")

        # Use custom color dialog
        color_dialog = ColorSelectionDialog(self.gui.root, "Mudar Cor da ROI")
        if not color_dialog.result:
            return

        selected_color = color_dialog.result
        new_color = selected_color["rgb"]
        color_name = selected_color["name"]

        # Update in project
        zone_data = self.zone_context_service.get_zone_data_for_active_context()
        try:
            idx = zone_data.roi_names.index(old_name)
            zone_data.roi_colors[idx] = new_color

            # Persist color change
            self.gui.controller.project_manager.save_zone_data(zone_data)

            # Update visualization
            status_message = f"Cor da ROI '{old_name}' alterada para {color_name}."
            self.gui.set_status(status_message)
            self.show_info("Sucesso", status_message)

            if self.event_bus_v2:
                from zebtrack.ui.event_bus_v2 import Event, UIEvents

                self.event_bus_v2.publish(
                    Event(
                        type=UIEvents.ZONES_UPDATED,
                        data={"zone_data": zone_data},
                        source="DialogManager.change_roi_color",
                    )
                )
                self.event_bus_v2.publish(
                    Event(
                        type=UIEvents.PROJECT_VIEWS_REFRESH_REQUESTED,
                        data={"reason": status_message, "append_summary": True},
                        source="DialogManager.change_roi_color",
                    )
                )

        except ValueError:
            self.show_error("Erro", "ROI não encontrada")
        except IndexError:
            self.show_error("Erro", "Dados de cor da ROI não encontrados")

    def rename_selected_roi(self):
        """Rename the selected ROI."""
        selected = self.gui.zone_listbox.selection()
        if not selected:
            return

        item = self.gui.zone_listbox.item(selected[0])
        old_name = item["values"][0].replace("📍 ", "")

        new_name = self.ask_string(
            "Renomear ROI", f"Novo nome para '{old_name}':", initialvalue=old_name
        )

        if new_name and new_name != old_name:
            # Update in project
            zone_data = self.zone_context_service.get_zone_data_for_active_context()
            try:
                idx = zone_data.roi_names.index(old_name)
                zone_data.roi_names[idx] = new_name

                # Persist updated ROI name
                self.gui.controller.project_manager.save_zone_data(zone_data)

                # Update visualization
                status_message = f"ROI renomeada para '{new_name}'."
                self.gui.set_status(status_message)
                self.show_info("Sucesso", status_message)

                if self.event_bus_v2:
                    from zebtrack.ui.event_bus_v2 import Event, UIEvents

                    self.event_bus_v2.publish(
                        Event(
                            type=UIEvents.ZONES_UPDATED,
                            data={"zone_data": zone_data},
                            source="DialogManager.rename_selected_roi",
                        )
                    )
                    self.event_bus_v2.publish(
                        Event(
                            type=UIEvents.PROJECT_VIEWS_REFRESH_REQUESTED,
                            data={"reason": status_message, "append_summary": True},
                            source="DialogManager.rename_selected_roi",
                        )
                    )

            except ValueError:
                self.show_error("Erro", "ROI não encontrada")
