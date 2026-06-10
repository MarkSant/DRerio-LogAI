"""Project-level widget builders (welcome, tabs, overview, progress)."""

from __future__ import annotations

import re
import tkinter as tk
from tkinter import Frame, Label, ttk

import structlog

from zebtrack.ui.builders.button_factory import ButtonFactory
from zebtrack.ui.builders.panel_builder import PanelBuilder
from zebtrack.ui.event_bus_v2 import UIEvents
from zebtrack.ui.window_utils import reset_geometry_if_not_maximized

log = structlog.get_logger()


class ProjectWidgetsBuilder:
    """Builder for project and navigation widgets."""

    def __init__(self, gui, common_builder, analysis_builder, zone_builder) -> None:
        self.gui = gui
        self.common = common_builder
        self.analysis = analysis_builder
        self.zone = zone_builder

    def build_project_actions(self, parent) -> None:
        """Create the project actions controls in the welcome frame."""
        commands = {
            "model_configuration": self.gui._open_global_model_configuration_window,
            "diagnostics": self.gui._open_global_model_diagnostics_window,
            "single_analysis": self.gui.single_video_workflow.on_analyze_single_video_clicked,
            "live_camera": lambda: self.gui.controller.hardware_vm.start_live_camera_analysis(),
            "create_project": self.gui.project_initializer.create_project_workflow,
            "open_project": self.gui.project_initializer.open_project_workflow,
        }

        ButtonFactory.create_project_action_buttons(parent, commands)

    def build_model_status(self, parent) -> None:
        """Create the model status display in the welcome frame."""
        status_vars = {
            "active_weight": self.gui._active_weight_display_var,
            "openvino_status": self.gui._openvino_display_var,
            "hardware_status": self.gui._gpu_hardware_display_var,
        }

        PanelBuilder.build_model_status_panel(parent, status_vars)

        # Welcome screen = global scope. Trigger an initial render so the
        # 4-slot summary replaces the "Detectando..." placeholder as soon as
        # WeightManager has finished bootstrapping.
        weight_hw = getattr(self.gui, "weight_hardware_manager", None)
        if weight_hw is not None:
            weight_hw.refresh_weights_summary(scope="global")

    def create_progress_grid_tab(self) -> None:
        """Create the tab for viewing the experimental progress grid."""
        self.gui.progress_grid_frame = ttk.Frame(self.gui.notebook, padding="10")
        self.gui.notebook.add(self.gui.progress_grid_frame, text="Progresso do Experimento")

        self.gui.grid_container = ttk.Frame(self.gui.progress_grid_frame)
        self.gui.grid_container.pack(expand=True, fill="both")

        refresh_button = ttk.Button(
            self.gui.progress_grid_frame,
            text="Atualizar Grade",
            command=self.render_progress_grid,
        )
        refresh_button.pack(side="bottom", pady=10)

        # Auto-refresh the progress grid whenever a live recording stops or
        # the project tree is refreshed, so the cell turns green/yellow
        # without requiring the user to click "Atualizar Grade" or reopen the
        # day/group dialog — audit Erro 2 (2026-05-25). Worker threads publish
        # these events, so dispatch through ``root.after(0, ...)``.
        event_bus = getattr(self.gui, "event_bus", None) or getattr(self.gui, "event_bus_v2", None)
        if event_bus is not None:

            def _schedule_refresh(_data=None) -> None:
                root = getattr(self.gui, "root", None)
                if root is None:
                    self.render_progress_grid()
                    return
                try:
                    root.after(0, self.render_progress_grid)
                except tk.TclError:
                    log.debug(
                        "project_widgets.progress_grid.refresh_schedule_suppressed",
                        exc_info=True,
                    )

            event_bus.subscribe(UIEvents.RECORDING_STOPPED, _schedule_refresh)
            event_bus.subscribe(UIEvents.PROJECT_VIEWS_REFRESH_REQUESTED, _schedule_refresh)
            handlers = getattr(self.gui, "_event_bus_handlers", None)
            if isinstance(handlers, dict):
                handlers["progress_grid.recording_stopped"] = _schedule_refresh
                handlers["progress_grid.project_views_refresh"] = _schedule_refresh

        self.render_progress_grid()

    def render_progress_grid(self) -> None:
        """Clear and redraw the experimental progress grid based on project data."""
        from tkinter import Button

        try:
            try:
                if self.gui.grid_container.winfo_exists():
                    for widget in self.gui.grid_container.winfo_children():
                        widget.destroy()
            except tk.TclError:
                return

            pm = self.gui.controller.project_manager
            if not pm or pm.get_project_type() != "live":
                return

            days = pm.project_data.get("experiment_days", 0)
            groups = pm.project_data.get("groups", [])
            subjects_per_group = pm.project_data.get("subjects_per_group", 0)

            if not all([days, groups, subjects_per_group]):
                ttk.Label(
                    self.gui.grid_container,
                    text="O design experimental não está totalmente configurado.",
                ).pack()
                return

            completed_sessions = pm.get_completed_sessions()
            completed_blocks = self._get_completed_blocks(pm)

            ttk.Label(
                self.gui.grid_container, text="Dia/Grupo", font=("Helvetica", 10, "bold")
            ).grid(row=0, column=0, padx=5, pady=5, sticky="nsew")
            for j, group_name in enumerate(groups):
                ttk.Label(
                    self.gui.grid_container,
                    text=group_name,
                    font=("Helvetica", 10, "bold"),
                    anchor="center",
                ).grid(row=0, column=j + 1, padx=5, pady=5, sticky="nsew")

            for i in range(days):
                day = i + 1
                day_title = self.common.build_day_title(day)

                ttk.Label(
                    self.gui.grid_container,
                    text=day_title,
                    font=("Helvetica", 10, "bold"),
                ).grid(row=i + 1, column=0, padx=5, pady=5, sticky="nsew")

                for j, group_name in enumerate(groups):
                    completed_count = sum(
                        1 for (d, g, s) in completed_sessions if d == day and g == group_name
                    )

                    status_text = f"{completed_count}/{subjects_per_group}"

                    # Lote marcado como completo manualmente vence a contagem:
                    # verde mesmo com menos sujeitos que o planejado.
                    if (group_name, day) in completed_blocks:
                        color = "#90EE90"
                    elif completed_count == 0:
                        color = "#E0E0E0"
                    elif completed_count < subjects_per_group:
                        color = "#FFFACD"
                    else:
                        color = "#90EE90"

                    from functools import partial

                    cell_btn = Button(
                        self.gui.grid_container,
                        text=status_text,
                        background=color,
                        width=15,
                        height=3,
                        command=partial(
                            self.gui.dialog_manager.handle_grid_cell_click, day, group_name
                        ),
                    )
                    cell_btn.grid(row=i + 1, column=j + 1, padx=2, pady=2, sticky="nsew")

            for col_index in range(len(groups) + 1):
                self.gui.grid_container.columnconfigure(col_index, weight=1)
            for row_index in range(days + 1):
                self.gui.grid_container.rowconfigure(row_index, weight=1)
        except (tk.TclError, KeyError, AttributeError) as e:
            log.error("widget_factory.render_progress_grid.failed", error=str(e), exc_info=True)
            try:
                ttk.Label(
                    self.gui.grid_container, text=f"Erro ao renderizar grade: {e}", foreground="red"
                ).pack(pady=20)
            except tk.TclError:
                log.debug("widget_factory.error_label.double_fault", exc_info=True)

    @staticmethod
    def _get_completed_blocks(pm) -> set[tuple[str, int]]:
        """Lotes (grupo, dia) marcados como completos em ``batch_reports``.

        Persistidos por ``LiveBatchCoordinator.mark_block_complete``; o dia é
        normalizado por dígitos para casar "1", "Dia 1" e "Dia_1".
        """
        completed: set[tuple[str, int]] = set()
        get_reports = getattr(pm, "get_batch_reports", None)
        if not callable(get_reports):
            return completed
        try:
            reports = get_reports() or {}
        # except Exception justified: leitura defensiva de project_data — a
        # grade deve renderizar mesmo com registros de lote malformados.
        except Exception:
            log.debug("widget_factory.batch_reports.read_failed", exc_info=True)
            return completed

        for info in reports.values():
            if not isinstance(info, dict):
                continue
            group = info.get("group")
            day_match = re.search(r"\d+", str(info.get("day") or ""))
            if group and day_match:
                completed.add((str(group), int(day_match.group(0))))
        return completed

    def create_project_overview_panel(self, parent: ttk.Frame) -> None:
        """Create the project overview panel using ProjectOverviewWidget."""
        if not parent:
            return

        if self.gui.project_overview_frame and self.gui.project_overview_frame.winfo_exists():
            try:
                self.gui.project_overview_frame.destroy()
            except tk.TclError:
                log.debug("widget_factory.overview_frame_destroy.suppressed", exc_info=True)

        self.gui.project_overview_frame = ttk.LabelFrame(
            parent, text="Resumo do Projeto", padding=10
        )
        self.gui.project_overview_frame.pack(fill="both", expand=True, pady=(10, 10))

        from zebtrack.ui.components import ProjectOverviewWidget

        self.gui.project_overview_widget = ProjectOverviewWidget(
            self.gui.project_overview_frame, event_bus=self.gui.event_bus
        )
        self.gui.project_overview_widget.pack(fill="both", expand=True)

        if self.gui.event_bus:
            self.gui.event_bus.subscribe(
                UIEvents.PROJECT_REFRESH_REQUESTED,
                self.gui._handle_project_refresh_requested,
            )
            self.gui.event_bus.subscribe(
                UIEvents.PROJECT_VIDEO_DOUBLE_CLICK_WIDGET,
                self.gui._handle_project_video_double_click,
            )
            self.gui.event_bus.subscribe(
                UIEvents.PROJECT_VIDEO_RIGHT_CLICK_WIDGET,
                self.gui._handle_project_video_right_click,
            )

        ttk.Separator(self.gui.project_overview_frame, orient="horizontal").pack(fill="x", pady=10)

        ttk.Button(
            self.gui.project_overview_frame,
            text="Editar Metadata do Vídeo Selecionado...",
            command=self.gui.menu_manager.edit_selected_project_overview_video_metadata,
        ).pack(fill="x", padx=5, pady=(0, 5))

        ttk.Button(
            self.gui.project_overview_frame,
            text="Ir para Processamento e Relatórios \u2192",
            command=self.gui.video_selector_manager.navigate_to_processing_reports_tab,
        ).pack(fill="x", padx=5, pady=(0, 5))

    def create_welcome_frame(self) -> None:
        """Create the initial UI for project selection and model configuration."""
        self.gui.project_initializer.update_window_title()

        self.gui.analysis_view_controller.cleanup_single_analysis_button()
        self.gui.root.update_idletasks()

        self.gui.analysis_view_controller.reset_analysis_widgets()

        if self.gui.status_frame:
            self.gui.status_frame.destroy()
            self.gui.status_frame = None

        self.gui.status_var.set("")

        self.gui.root.update_idletasks()

        reset_geometry_if_not_maximized(self.gui.root)
        self.gui.welcome_frame = ttk.Frame(self.gui.root, padding="10")
        self.gui.welcome_frame.pack(expand=True, fill="both")

        self.common.display_welcome_logo()

        self.build_project_actions(self.gui.welcome_frame)
        self.build_model_status(self.gui.welcome_frame)

    def create_main_control_frame(self) -> None:
        """Create the main UI with tabs for controlling the app."""
        if self.gui.welcome_frame:
            self.gui.welcome_frame.destroy()
        reset_geometry_if_not_maximized(self.gui.root)

        self.gui.notebook = ttk.Notebook(self.gui.root, style="Zebtrack.TNotebook")
        self.gui.notebook.pack(expand=True, fill="both", padx=5, pady=5)

        self.gui.notebook.bind("<<NotebookTabChanged>>", self.gui.zone_edit_guard.on_tab_changed)

        # Mantém a mesma ordem usada por ProjectInitializer.create_main_control_frame:
        # Controle Principal → Progresso (live) → Processamento → Zonas → Análise → Avançadas
        self.gui.tab_builder.build_main_controls_tab()
        if self.gui.controller.project_manager.get_project_type() == "live":
            self.create_progress_grid_tab()
        self.analysis.create_processing_reports_tab()
        self.gui.tab_builder.build_zone_tab()
        self.analysis.create_analysis_tab_widget()
        self.analysis.create_configuration_tab_widget()

        project_type_str = self.gui.controller.project_manager.get_project_type()
        if project_type_str == "live":
            project_type_display = "Ao Vivo"
        elif project_type_str == "pre-recorded":
            project_type_display = "Pré-gravado"
        else:
            project_type_display = project_type_str

        status_text = (
            f"Projeto: {self.gui.controller.project_manager.get_project_name()} "
            f"({project_type_display})"
        )
        self.gui.status_var.set(status_text)
        status_frame = Frame(self.gui.root)
        status_frame.pack(pady=5, fill="x", padx=10, side="bottom")
        Label(status_frame, textvariable=self.gui.status_var).pack()

        self.gui.hide_progress_bar()
