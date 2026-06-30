"""Project initializer — handles project loading, tab creation, and workflow dialogs.

Extracted from ApplicationGUI (Phase 4.4) to isolate all project
initialisation logic: welcome-to-project transition, tab building,
live/pre-recorded component setup, and new/open project dialogs.
"""

from __future__ import annotations

from tkinter import Label, TclError, ttk
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
        # Idempotência: se já existe um notebook (ex.: fluxo de vídeo único ao
        # vivo SEM projeto, que monta a view tardiamente via
        # ``switch_to_analysis_view``), derruba notebook + controles + status
        # ANTES de reconstruir. Sem isto, uma 2ª chamada empilha um SEGUNDO
        # ``ttk.Notebook`` no ``root``: o antigo fica órfão-mas-mapeado, gerando
        # uma fileira de abas fantasma (não-clicável) colada no rodapé, e
        # ``create_processing_reports_tab`` move a aba "Processamento e
        # Relatórios" para o notebook novo — fazendo-a "sumir" da fileira visível.
        if gui.notebook is not None:
            gui.state_synchronizer._destroy_notebook_and_main_controls()
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

        # Create the tabs in the user-facing workflow order:
        # 1) Controle Principal → 2) Progresso (live) → 3) Processamento e Relatório →
        # 4) Configuração de Zonas → 5) Análise de Vídeo →
        # 6) Config. Modelo IA → 7) Diagnóstico Modelo IA → 8) Config. Avançadas
        gui.tab_builder.build_main_controls_tab()
        if gui.controller.project_manager.get_project_type() == "live":
            gui.widget_factory.create_progress_grid_tab()
        gui.tab_builder.build_processing_reports_tab()  # New unified tab
        gui.tab_builder.build_zone_tab()
        gui.tab_builder.build_analysis_tab()
        gui.tab_builder.build_model_configuration_tab()
        gui.tab_builder.build_diagnostics_tab()
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
        status_frame = ttk.Frame(gui.root)
        gui.status_frame = status_frame
        status_frame.pack(pady=5, fill="x", padx=10, side="bottom")
        Label(status_frame, textvariable=gui.status_var).pack()

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

        # Sincroniza a contagem de aquários (var de UI + settings) com o projeto
        # recém-carregado. Sem isto, o estado multi-aquário de um teste anterior
        # (ex.: vídeo pré-gravado com 2 aquários) VAZAVA para um novo projeto de
        # 1 aquário, fazendo o save da arena entrar no caminho multi-aquário e
        # disparar os prompts de "segundo aquário"/"sequencial". Roda DEPOIS de
        # create_main_control_frame (onde zone_controls é criado).
        self._sync_aquarium_count_from_project(pm)

        project_type = pm.get_project_type()
        if project_type == "live":
            self.initialize_live_components(pm)
        elif project_type == "pre-recorded":
            self.initialize_prerecorded_components(pm)

        # Note: live projects no longer auto-prompt for arena calibration at
        # project-open time. The previous behaviour scheduled
        # ``validation_manager.check_live_project_calibration`` 1 second after
        # the project loaded, which (a) implied the project had a single
        # global arena (wrong — each recording can have its own aquarium
        # position/shape) and (b) blocked the user with a yes/no prompt
        # before they'd had a chance to even look at the new project. The
        # correct calibration trigger is ``LiveCalibrationCoordinator
        # .ensure_zones_before_recording``, which fires per-session when the
        # user clicks "Iniciar Sessão" on a specific subject in the batch
        # grid. The ``check_live_project_calibration`` method is preserved
        # for explicit invocation but no longer scheduled automatically.

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
                preview_value = pm.project_data["last_show_preview"]
                if isinstance(preview_value, str):
                    normalized_preview = preview_value.strip().lower() in {
                        "1",
                        "true",
                        "yes",
                        "on",
                    }
                elif isinstance(preview_value, bool):
                    normalized_preview = preview_value
                elif isinstance(preview_value, int | float):
                    normalized_preview = bool(preview_value)
                else:
                    raise TypeError(
                        f"Unsupported persisted preview value: {type(preview_value).__name__}"
                    )
                gui.show_preview_var.set(normalized_preview)
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

    def _sync_aquarium_count_from_project(self, pm: Any) -> None:
        """Reset a contagem de aquários da UI para o projeto recém-carregado.

        Vale para TODOS os tipos de projeto (criar e abrir). Lê o número de
        aquários canônico do projeto (``calibration.num_aquariums``, default 1) e
        ressincroniza tanto a var de UI (``zone_controls.aquarium_count_var`` via
        ``set_aquarium_count`` — que também mostra/esconde o seletor e zera o
        aquário ativo) quanto o cache ``settings.analysis_config.num_aquariums``.

        Isto evita o vazamento do estado multi-aquário entre projetos: sem o
        reset, um teste pré-gravado de 2 aquários deixava ``aquarium_count_var``
        em 2 e o save da arena de um novo projeto de 1 aquário ia para o caminho
        multi-aquário.
        """
        gui = self.gui

        num_aquariums = 1
        try:
            calibration = pm.project_data.get("calibration", {})
            if isinstance(calibration, dict):
                num_aquariums = int(calibration.get("num_aquariums", 1))
        except (AttributeError, TypeError, ValueError):
            log.debug("project_initializer.aquarium_count.parse_skipped", exc_info=True)
            num_aquariums = 1

        if num_aquariums < 1:
            num_aquariums = 1

        zone_controls = getattr(gui, "zone_controls", None)
        if zone_controls is not None and hasattr(zone_controls, "set_aquarium_count"):
            try:
                zone_controls.set_aquarium_count(num_aquariums)
            except Exception:
                log.debug("project_initializer.aquarium_count.set_skipped", exc_info=True)

        if gui.settings and hasattr(gui.settings, "analysis_config"):
            try:
                gui.settings.analysis_config.num_aquariums = num_aquariums
            except (ValueError, TypeError):
                log.debug("project_initializer.aquarium_count.settings_skipped", exc_info=True)

        log.info(
            "project_initializer.aquarium_count_synced",
            num_aquariums=num_aquariums,
            project_type=pm.get_project_type() if hasattr(pm, "get_project_type") else None,
        )

    # ------------------------------------------------------------------
    # Live / Pre-recorded component setup
    # ------------------------------------------------------------------

    def initialize_live_components(self, pm: Any) -> None:
        """Initialize components for Live project type."""
        gui = self.gui

        # Initial rendering of the progress grid
        gui.root.after(100, gui.widget_factory.render_progress_grid)

        # Only attempt to connect if the user opted-in to Arduino in the wizard
        # AND an ArduinoManager is wired (the bootstrapper creates it eagerly,
        # so it is normally present). The manager lives on
        # ``hardware_vm.arduino_manager`` — the legacy ``hardware_vm.arduino``
        # attribute is deprecated and stays None, which previously made this
        # branch never fire. ``ArduinoManager.connect`` requires (port, baud_rate);
        # we resolve the port from the project (saved by the wizard) and fall
        # back to ``settings.arduino.port``.
        use_arduino = bool(pm.project_data.get("use_arduino", False))
        arduino_manager = getattr(gui.controller.hardware_vm, "arduino_manager", None)
        settings = gui.controller.settings
        project_port = (pm.project_data.get("arduino_port") or "").strip()
        port = project_port or (settings.arduino.port if settings else "")
        baud_rate = settings.arduino.baud_rate if settings else 9600
        handshake = settings.arduino.handshake if settings else "none"
        ack = settings.arduino.ack if settings else "none"
        if use_arduino and arduino_manager is not None and port:
            if not arduino_manager.connect(port, baud_rate, handshake=handshake, ack=ack):
                gui.dialog_manager.show_warning(
                    "Aviso do Arduino",
                    f"Não foi possível conectar ao Arduino na porta "
                    f"{port}. Executando em modo offline.",
                )
        elif use_arduino and arduino_manager is None:
            log.warning(
                "project_initializer.arduino_enabled_but_no_manager",
                port=port or None,
            )
        try:
            from zebtrack.core.services.wizard_service import WizardService

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
                        f"A câmera salva no projeto ('{saved_name}') não foi detectada.\n\n"
                        f"As gravações irão falhar até você selecionar outra câmera. "
                        f"Use 'Trocar câmera...' no bloco do animal antes de iniciar a "
                        f"sessão para escolher um dispositivo conectado."
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

            # Historical note: this block used to open a Camera, feed its
            # ``actual_width``/``actual_height`` into a now-deleted
            # ``detector.update_scaling(w, h)`` API, and stash the handle on
            # ``hardware_vm.camera`` for an old preview feature. All three
            # parts are vestigial in the current architecture:
            #
            #  - ``Detector.update_scaling(w, h)`` was renamed to
            #    ``set_zones(zones, w, h)`` and the right place to call it is
            #    when zones are actually defined (auto-detect / manual draw),
            #    not at project init when zones are still empty.
            #  - Nothing reads frames from ``hardware_vm.camera`` before the
            #    user hits record — ``LiveCameraService.start_session`` opens
            #    its own Camera with the per-session index. Keeping a handle
            #    open here left the physical device powered on (LED-on) and
            #    conflicted with the calibration camera during auto-detect.
            #  - ``WizardService.resolve_camera_index`` above already verifies
            #    the saved device is present (status="MISSING" surfaces a
            #    user-visible warning), so we don't need to probe the device
            #    by opening it.
            #
            # Net effect: do nothing here. The bookkeeping below just keeps
            # the legacy attributes in a known-clean state for downstream
            # consumers (e.g. ``_release_preview_camera_if_any``).
            gui.controller.hardware_vm.camera = None
            gui.controller.hardware_vm.active_frame_source = None
        except OSError as e:
            gui.dialog_manager.show_error("Erro na Câmera", str(e))
            gui.widget_factory.create_welcome_frame()
            return

        # Mirror the pre-recorded path: publish VIDEO_TREE_REFRESH_REQUESTED
        # so the zone tab's "Selecionar Vídeo para Desenho" tree populates
        # with any sessions that have already been recorded in this project
        # (group/day/subject hierarchy). For brand-new live projects with no
        # recordings yet the tree will still be empty — that's expected
        # because the tree is fed by ``ProjectManager.get_all_videos`` which
        # only returns registered recordings. The pending session banner
        # above the canvas covers the "which subject am I configuring now"
        # use case via the LIVE_RECORDING_PENDING payload.
        if gui.event_bus:
            from zebtrack.ui import payloads
            from zebtrack.ui.event_bus_v2 import Event, UIEvents

            gui.event_bus.publish(
                Event(
                    type=UIEvents.VIDEO_TREE_REFRESH_REQUESTED,
                    data=payloads.VideoTreeRefreshRequestedPayload(filter_text=None),
                    source="ProjectInitializer.initialize_live",
                )
            )

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
