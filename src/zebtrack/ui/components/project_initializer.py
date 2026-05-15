"""Project initializer — handles project loading, tab creation, and workflow dialogs.

Extracted from ApplicationGUI (Phase 4.4) to isolate all project
initialisation logic: welcome-to-project transition, tab building,
live/pre-recorded component setup, and new/open project dialogs.
"""

from __future__ import annotations

from tkinter import Frame, Label, TclError, ttk
from typing import TYPE_CHECKING, Any

import structlog

from zebtrack.ui.window_utils import reset_geometry_if_not_maximized

if TYPE_CHECKING:
    from zebtrack.ui.gui import ApplicationGUI

log = structlog.get_logger()


class ProjectInitializer:
    """Orchestrates project loading and the welcome → project view transition.

    All methods operate on the host *ApplicationGUI* instance via the ``gui``
    back-reference.  No Tk widgets are owned directly by this class.
    """

    def __init__(self, gui: ApplicationGUI) -> None:
        self.gui = gui

    # ------------------------------------------------------------------
    # Main control frame
    # ------------------------------------------------------------------

    def create_main_control_frame(self) -> None:
        """Create the main UI with tabs for controlling the app."""
        gui = self.gui
        if gui.welcome_frame:
            gui.welcome_frame.destroy()
            gui.welcome_frame = None
        if gui.status_frame:
            gui.status_frame.destroy()
            gui.status_frame = None
        reset_geometry_if_not_maximized(gui.root)

        gui.notebook = ttk.Notebook(gui.root, style="Zebtrack.TNotebook")
        gui.notebook.pack(expand=True, fill="both", padx=5, pady=5)

        # Bind tab change event to hide analysis overlay when switching tabs
        gui.notebook.bind("<<NotebookTabChanged>>", gui.zone_edit_guard.on_tab_changed)

        # Create the tabs
        gui.tab_builder.build_main_controls_tab()
        gui.tab_builder.build_model_configuration_tab()
        gui.tab_builder.build_diagnostics_tab()
        if gui.controller.project_manager.get_project_type() == "live":
            gui.widget_factory.create_progress_grid_tab()
        gui.tab_builder.build_zone_tab()
        gui.tab_builder.build_processing_reports_tab()  # New unified tab
        gui.tab_builder.build_analysis_tab()
        gui.tab_builder.build_configuration_tab()

        gui._last_selected_tab_id = gui.notebook.select()

        # Status frame below the notebook
        project_type_str = gui.controller.project_manager.get_project_type()
        if project_type_str == "live":
            project_type_display = "Ao Vivo"
        elif project_type_str == "pre-recorded":
            project_type_display = "Pré-gravado"
        else:
            project_type_display = project_type_str

        status_text = (
            f"Projeto: {gui.controller.project_manager.get_project_name()} ({project_type_display})"
        )
        gui.status_var.set(status_text)
        gui.status_frame = Frame(gui.root)
        gui.status_frame.pack(pady=5, fill="x", padx=10, side="bottom")
        Label(gui.status_frame, textvariable=gui.status_var).pack()

        # Ensure analysis UI starts hidden
        gui.hide_progress_bar()

        # Populate video selector tree after tabs are built
        if gui.event_bus:
            from zebtrack.ui import payloads
            from zebtrack.ui.event_bus_v2 import Event, UIEvents

            gui.event_bus.publish(
                Event(
                    type=UIEvents.VIDEO_TREE_REFRESH_REQUESTED,
                    data=payloads.VideoTreeRefreshRequestedPayload(filter_text=None),
                    source="ProjectInitializer.create_main_control_frame",
                )
            )

    # ------------------------------------------------------------------
    # Project view loading
    # ------------------------------------------------------------------

    def load_project_view(self) -> None:
        """Transition from the welcome screen to the main control view."""
        gui = self.gui

        # Reset analysis display state from single video workflow
        gui.hide_progress_bar()
        gui.analysis_status_var.set("Nenhuma análise em andamento.")
        if gui.analysis_display_widget and gui.analysis_display_widget.video_label:
            try:
                gui.analysis_display_widget.video_label.configure(image="")
                gui._analysis_overlay_image = None
            except (TclError, AttributeError):
                log.debug("project_initializer.video_label_clear.suppressed", exc_info=True)

        pm = gui.controller.project_manager

        # Update window title with project name
        try:
            project_name = pm.get_project_name() if hasattr(pm, "get_project_name") else None
            self.update_window_title(project_name)
        except (AttributeError, TclError):
            log.debug("project_initializer.update_window_title.suppressed", exc_info=True)

        # Load persisted user preferences if present
        if pm.get_project_type() == "pre-recorded":
            self.restore_persisted_project_settings(pm)

        self.create_main_control_frame()

        project_type = pm.get_project_type()
        if project_type == "live":
            self.initialize_live_components(pm)
        elif project_type == "pre-recorded":
            self.initialize_prerecorded_components(pm)

        if project_type == "live":
            # Auto-calibration for Live projects when no zones are defined
            gui.root.after(1000, gui.validation_manager.check_live_project_calibration)

    # ------------------------------------------------------------------
    # Settings restoration
    # ------------------------------------------------------------------

    def restore_persisted_project_settings(self, pm: Any) -> None:
        """Restore settings from project data."""
        gui = self.gui

        if pm.project_data.get("last_processing_interval") is not None:
            try:
                gui.processing_interval_var.set(
                    str(int(pm.project_data["last_processing_interval"]))
                )
            except (ValueError, TypeError):
                log.debug(
                    "project_initializer.restore_processing_interval.suppressed", exc_info=True
                )
        if pm.project_data.get("last_show_preview") is not None:
            try:
                gui.show_preview_var.set(
                    bool(pm.project_data["last_show_preview"])  # type: ignore[arg-type]
                )
            except (ValueError, TypeError):
                log.debug("project_initializer.restore_show_preview.suppressed", exc_info=True)

        # Restore analysis and display intervals
        if pm.project_data.get("analysis_interval_frames") is not None:
            try:
                gui.analysis_interval_var.set(str(int(pm.project_data["analysis_interval_frames"])))
            except (ValueError, TypeError):
                log.debug("project_initializer.restore_analysis_interval.suppressed", exc_info=True)
        if pm.project_data.get("display_interval_frames") is not None:
            try:
                gui.display_interval_var.set(str(int(pm.project_data["display_interval_frames"])))
            except (ValueError, TypeError):
                log.debug("project_initializer.restore_display_interval.suppressed", exc_info=True)

        # Synchronize num_aquariums from project calibration to settings
        calibration = pm.project_data.get("calibration", {})
        if isinstance(calibration, dict):
            num_aquariums = calibration.get("num_aquariums", 1)
            if gui.settings and hasattr(gui.settings, "analysis_config"):
                try:
                    gui.settings.analysis_config.num_aquariums = int(num_aquariums)
                    log.info(
                        "project_initializer.num_aquariums_synced",
                        num_aquariums=num_aquariums,
                    )
                except (ValueError, TypeError) as e:
                    log.warning(
                        "project_initializer.num_aquariums_sync_failed",
                        error=str(e),
                    )

    # ------------------------------------------------------------------
    # Live / Pre-recorded component setup
    # ------------------------------------------------------------------

    def initialize_live_components(self, pm: Any) -> None:
        """Initialize components for Live project type."""
        gui = self.gui

        # Initial rendering of the progress grid
        gui.root.after(100, gui.widget_factory.render_progress_grid)

        # Only attempt to connect if a port is configured from the dialog
        if gui.controller.settings and gui.controller.settings.arduino.port:
            if not gui.controller.hardware_vm.arduino.connect():
                gui.dialog_manager.show_warning(
                    "Aviso do Arduino",
                    f"Não foi possível conectar ao Arduino na porta "
                    f"{gui.controller.settings.arduino.port}. Executando em modo offline.",
                )
        try:
            from zebtrack.core.services.wizard_service import WizardService
            from zebtrack.io.camera import Camera

            # Use camera_index/friendly_name from project_data (saved by wizard).
            # Resolve via friendly name to recover from DirectShow reordering.
            saved_index = pm.project_data.get("camera_index", 0)
            saved_name = pm.project_data.get("camera_friendly_name", "") or ""
            camera_index, status = WizardService.resolve_camera_index(saved_index, saved_name)

            if status == "MISSING":
                log.warning(
                    "project_initializer.live_camera_setup.missing",
                    saved_index=saved_index,
                    saved_name=saved_name,
                )
                gui.dialog_manager.show_warning(
                    "Câmera não encontrada",
                    (
                        f"A câmera salva no projeto ('{saved_name}') não foi detectada.\n"
                        f"Tentando o índice salvo ({saved_index}) como fallback. "
                        f"Use 'Trocar câmera' ao iniciar uma gravação para escolher outra."
                    ),
                )
            elif status == "SHIFTED":
                log.info(
                    "project_initializer.live_camera_setup.shifted",
                    saved_index=saved_index,
                    actual_index=camera_index,
                    friendly_name=saved_name,
                )

            log.info(
                "project_initializer.live_camera_setup",
                camera_index=camera_index,
                friendly_name=saved_name,
                project_name=pm.get_project_name(),
            )

            # Create temporary settings with correct camera index
            temp_settings = gui.controller.settings.model_copy(deep=True)
            temp_settings.camera.index = camera_index

            # Initialize camera with modified settings
            gui.controller.hardware_vm.camera = Camera(settings_obj=temp_settings)

            gui.controller.hardware_vm.active_frame_source = gui.controller.hardware_vm.camera
            gui.controller.hardware_vm.detector.update_scaling(
                gui.controller.hardware_vm.camera.actual_width,
                gui.controller.hardware_vm.camera.actual_height,
            )
        except OSError as e:
            gui.dialog_manager.show_error("Erro na Câmera", str(e))
            gui.widget_factory.create_welcome_frame()
            return

    def initialize_prerecorded_components(self, pm: Any) -> None:
        """Initialize components for Pre-recorded project type."""
        gui = self.gui

        gui.reports_tree_manager.update_reports_tree()

        if gui.event_bus:
            from zebtrack.ui import payloads
            from zebtrack.ui.event_bus_v2 import Event, UIEvents

            gui.event_bus.publish(
                Event(
                    type=UIEvents.VIDEO_TREE_REFRESH_REQUESTED,
                    data=payloads.VideoTreeRefreshRequestedPayload(filter_text=None),
                    source="ProjectInitializer.initialize_prerecorded",
                )
            )

        ready_message = f"Projeto: {pm.get_project_name()} - Pronto."
        gui.set_status(ready_message)
        gui.video_selector_manager.request_overview_refresh(reason=ready_message)

    # ------------------------------------------------------------------
    # Window title
    # ------------------------------------------------------------------

    def update_window_title(self, project_name: str | None = None) -> None:
        """Update the window title with the project name."""
        base_title = "DRerio LogAI"
        if project_name:
            self.gui.root.title(f"{base_title} - {project_name}")
        else:
            self.gui.root.title(base_title)

    # ------------------------------------------------------------------
    # Tab navigation
    # ------------------------------------------------------------------

    def navigate_to_processing_reports_tab(self) -> None:
        """Navigate to the Processing and Reports tab."""
        if not self.gui.notebook:
            return

        tab_count = self.gui.notebook.index("end")
        for i in range(tab_count):
            tab_text = self.gui.notebook.tab(i, "text")
            if "Processamento e Relatórios" in tab_text:
                self.gui.notebook.select(i)
                return

        log.warning("project_initializer.navigate.processing_reports_tab_not_found")

    # ------------------------------------------------------------------
    # Project workflow dialogs
    # ------------------------------------------------------------------

    def create_project_workflow(self) -> None:
        """Handle the UI part of creating a new project by opening a comprehensive dialog.

        Phase 7: Direct wizard data delegation to ProjectWorkflowService.
        """
        from zebtrack.ui.wizard.wizard_dialog import WizardDialog

        gui = self.gui

        wizard = WizardDialog(
            gui.root,
            settings_obj=gui.controller.settings,
            event_bus=gui.event_bus,
        )
        if not wizard.result:
            return  # User cancelled

        # Validate required fields
        required_fields = ["project_path", "project_name", "project_type"]
        missing = [f for f in required_fields if f not in wizard.result]
        if missing:
            gui.dialog_manager.show_error(
                "Erro no Wizard",
                f"Campos obrigatórios ausentes: {', '.join(missing)}",
            )
            return

        # Pass wizard data directly to controller (via ProjectWorkflowService)
        from zebtrack.ui import payloads
        from zebtrack.ui.event_bus_v2 import UIEvents

        gui.event_dispatcher.publish_event(
            UIEvents.PROJECT_CREATE,
            payloads.ProjectCreatePayload(
                project_path=wizard.result.get("project_path"),
                project_name=wizard.result.get("project_name"),
                project_type=wizard.result.get("project_type"),
                wizard_data=wizard.result,
            ),
        )

    def open_project_workflow(self) -> None:
        """Handle the UI part of opening a project, then call the controller."""
        from zebtrack.ui import payloads
        from zebtrack.ui.event_bus_v2 import UIEvents

        gui = self.gui
        project_path = gui.dialog_manager.ask_directory(
            title="Selecione uma Pasta de Projeto Existente"
        )
        if not project_path:
            return

        gui.event_dispatcher.publish_event(
            UIEvents.PROJECT_OPEN,
            payloads.ProjectOpenPayload(project_path=project_path),
        )
