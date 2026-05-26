"""Analysis, reporting, and configuration widget builders."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import ttk
from typing import Any

import structlog
import yaml
from pydantic import ValidationError

from zebtrack.settings import Settings
from zebtrack.ui import payloads as payloads
from zebtrack.ui.event_bus_v2 import UIEvents

log = structlog.get_logger()


class AnalysisWidgetsBuilder:
    """Builder for analysis and processing/report tabs."""

    def __init__(
        self,
        gui,
        common_builder,
        settings_obj: Settings | None,
        dialog_manager=None,
    ) -> None:
        self.gui = gui
        self.common = common_builder
        self._settings = settings_obj
        self._dialog_manager = dialog_manager

    @property
    def dialog_manager(self):
        return self._dialog_manager or self.gui.dialog_manager

    def create_analysis_tab_widget(self) -> None:
        """Create the analysis tab using the AnalysisDisplayWidget."""
        if not self.gui.notebook:
            return

        from zebtrack.ui.components import AnalysisDisplayWidget

        self.gui.analysis_display_widget = AnalysisDisplayWidget(
            self.gui.notebook,
            event_bus=self.gui.event_bus,
            available_track_options=list(self.gui._available_track_options),
        )

        self.gui.analysis_tab_frame = self.gui.analysis_display_widget

        self.gui.notebook.add(self.gui.analysis_display_widget, text="Análise de Vídeo")

        # Audit Erro 2 round 6 (2026-05-25): drain any payloads that fired
        # BEFORE this widget existed (e.g. live session metadata/stats
        # published at session start while the tab was still being built).
        # Without this drain, the labels stuck on "--" forever.
        event_dispatcher = getattr(self.gui, "event_dispatcher", None)
        if event_dispatcher is not None and hasattr(event_dispatcher, "drain_pending_to_widget"):
            try:
                event_dispatcher.drain_pending_to_widget()
            # except Exception justified: drain is best-effort.
            except Exception:
                import structlog

                structlog.get_logger().debug(
                    "analysis_widgets.drain_pending_failed",
                    exc_info=True,
                )

        if self.gui.event_bus_v2:

            def track_handler(data):
                return self.gui.canvas_manager._render_last_analysis_frame()

            def cancel_handler(data):
                return self.gui.event_dispatcher.publish_event(
                    UIEvents.VIDEO_CANCEL_ANALYSIS,
                    payloads.VideoCancelAnalysisPayload(),
                )

            def video_selected_handler(data) -> None:
                """Refresh analysis-tab metadata (group/day/subject/profile)
                when the user selects a different video in the project tree.

                Without this, switching videos in the tree leaves the analysis
                tab showing metadata from the last *processed* video instead
                of the currently selected one (audit Erro 7b — 2026-05-25).
                """
                video_path = getattr(data, "video_path", None)
                if not video_path:
                    return
                pm = self.gui.controller.project_manager
                entry = (
                    getattr(data, "video_entry", None) or pm.find_video_entry(path=video_path) or {}
                )
                metadata: dict[str, Any] = dict(entry.get("metadata") or {})
                # Promote top-level fields onto the metadata dict so
                # ValidationManager.resolve_* helpers find them.
                for key in ("group", "group_display_name", "day", "subject"):
                    value = entry.get(key)
                    if value not in (None, "") and key not in metadata:
                        metadata[key] = value

                controller = getattr(self.gui, "analysis_view_controller", None)
                if controller is None:
                    return
                # Update metadata strings (group/day/subject).
                controller.update_analysis_metadata(metadata=metadata)
                # Profile follows the project-level setting; reapply so a
                # previous video's profile label doesn't linger.
                project_data = pm.project_data or {}
                profile_name = (
                    metadata.get("profile")
                    or project_data.get("analysis_profile")
                    or project_data.get("active_profile")
                    or "default"
                )
                try:
                    controller.update_analysis_profile(str(profile_name))
                except (AttributeError, tk.TclError):
                    log.debug(
                        "analysis_widgets.video_selected.profile_update_suppressed",
                        exc_info=True,
                    )

            self.gui.event_bus_v2.subscribe(UIEvents.ANALYSIS_TRACK_SELECTED, track_handler)
            self.gui.event_bus_v2.subscribe(UIEvents.ANALYSIS_CANCEL_REQUESTED, cancel_handler)
            self.gui.event_bus_v2.subscribe(UIEvents.PROJECT_VIDEO_SELECTED, video_selected_handler)

            self.gui._event_bus_handlers["analysis.track_selected"] = track_handler
            self.gui._event_bus_handlers["analysis.cancel_requested"] = cancel_handler
            self.gui._event_bus_handlers["analysis.video_selected_metadata"] = (
                video_selected_handler
            )

    def create_processing_reports_tab(self) -> None:
        """Create the unified Processing and Reports tab."""
        if not self.gui.notebook:
            return

        if (
            self.gui.processing_reports_tab_frame
            and self.gui.processing_reports_tab_frame.winfo_exists()
        ):
            try:
                self.gui.processing_reports_tab_frame.destroy()
            except tk.TclError:
                log.debug("widget_factory.reports_tab_destroy.suppressed", exc_info=True)

        self.gui.processing_reports_tab_frame = ttk.Frame(self.gui.notebook, padding="10")
        self.gui.notebook.add(
            self.gui.processing_reports_tab_frame, text="Processamento e Relatórios"
        )

        from zebtrack.ui.components.processing_reports import ProcessingReportsWidget

        self.gui.processing_reports_widget = ProcessingReportsWidget(
            self.gui.processing_reports_tab_frame,
            event_bus=self.gui.event_bus,
            on_generate_trajectories=self.gui.video_selector_manager.trigger_batch_trajectory_processing,
            on_export_summaries=self.gui.video_selector_manager.trigger_parquet_summaries,
            on_generate_partial_report=self.gui.reports_tree_manager.on_processing_reports_generate_partial,
            on_generate_unified_report=self.gui.reports_tree_manager.generate_unified_report,
        )
        self.gui.processing_reports_widget.pack(fill="both", expand=True)

        if self.gui.processing_reports_widget.tree:
            # Abrir relatórios/pastas apenas com duplo-clique — clique simples
            # deve só selecionar o item (Erro 7a do audit de 2026-05-25).
            self.gui.processing_reports_widget.tree.bind(
                "<Double-Button-1>",
                self.gui.reports_tree_manager.on_processing_reports_item_double_click,
                add="+",
            )

        self.gui.reports_tree_manager.refresh_processing_reports_tab()

    # ------------------------------------------------------------------
    # Config editor helpers
    # ------------------------------------------------------------------

    def create_configuration_tab_widget(self) -> None:
        """Create the configuration tab using ConfigEditorWidget."""
        if not self.gui.notebook:
            return

        from zebtrack.ui.components import ConfigEditorWidget

        self.gui.config_editor_widget = ConfigEditorWidget(
            self.gui.notebook,
            event_bus=self.gui.event_bus,
        )

        self.gui.notebook.add(self.gui.config_editor_widget, text="Config. Avançadas")

        if self.gui.event_bus:

            def save_handler(data: payloads.ConfigSaveRequestedPayload) -> None:
                values = dict(data.values or {})
                return self.on_save_global_config_from_widget(values)

            def reset_handler(_: payloads.EmptyPayload) -> None:
                return self.on_reset_global_config_form_widget()

            def roi_rule_handler(data: payloads.ConfigRoiRuleChangedPayload) -> None:
                return self.common.update_roi_rule_ui(data.rule)

            self.gui.event_bus.subscribe(UIEvents.CONFIG_SAVE_REQUESTED, save_handler)
            self.gui.event_bus.subscribe(UIEvents.CONFIG_RESET_REQUESTED, reset_handler)
            self.gui.event_bus.subscribe(UIEvents.CONFIG_ROI_RULE_CHANGED, roi_rule_handler)

            def calibration_handler(_: payloads.EmptyPayload) -> None:
                self.gui._open_global_model_configuration_window()

            self.gui.event_bus.subscribe(
                UIEvents.CONFIG_OPEN_CALIBRATION_DIALOG, calibration_handler
            )

            self.gui._event_bus_handlers["config.save_requested"] = save_handler
            self.gui._event_bus_handlers["config.reset_requested"] = reset_handler
            self.gui._event_bus_handlers["config.roi_rule_changed"] = roi_rule_handler
            self.gui._event_bus_handlers["config.open_calibration_dialog"] = calibration_handler

        self.reload_config_editor_values_widget()

    def reload_config_editor_values_widget(self) -> None:
        """Load current settings into ConfigEditorWidget."""
        if self._settings is None:
            self.dialog_manager.show_error(
                "Erro", "Settings não disponível. Não foi possível carregar."
            )
            return

        current = self._settings

        project_data = self.gui.controller.project_manager.project_data
        processing_interval = self.gui._extract_setting(
            current, ("video_processing", "processing_interval"), 10
        )
        display_interval = self.gui._extract_setting(
            current, ("video_processing", "display_interval"), 10
        )

        if self.gui.controller.project_manager.project_path and project_data:
            processing_interval = project_data.get("analysis_interval_frames", processing_interval)
            display_interval = project_data.get("display_interval_frames", display_interval)

        values = {
            "video_processing": {
                "fps": self.gui._extract_setting(current, ("video_processing", "fps"), 30),
                "processing_interval": processing_interval,
                "display_interval": display_interval,
                "processing_offset": self.gui._extract_setting(
                    current, ("video_processing", "processing_offset"), 0
                ),
            },
            "trajectory_smoothing": {
                "window_length": self.gui._extract_setting(
                    current, ("trajectory_smoothing", "window_length"), 7
                ),
                "polyorder": self.gui._extract_setting(
                    current, ("trajectory_smoothing", "polyorder"), 3
                ),
            },
            "recorder": {
                "flush_interval_seconds": self.gui._extract_setting(
                    current, ("recorder", "flush_interval_seconds"), 5.0
                ),
                "flush_row_threshold": self.gui._extract_setting(
                    current, ("recorder", "flush_row_threshold"), 500
                ),
            },
            "roi_inclusion_rule": self.gui._extract_setting(
                current, ("roi_inclusion_rule",), "centroid_in"
            ),
            "roi_buffer_radius_value": self.gui._extract_setting(
                current, ("roi_buffer_radius_value",), 0.0
            ),
            "roi_min_bbox_overlap_ratio": self.gui._extract_setting(
                current, ("roi_min_bbox_overlap_ratio",), 0.5
            ),
        }

        behavioral_values = {}

        if self.gui.controller.project_manager.project_path:
            project_data = self.gui.controller.project_manager.project_data
            if project_data and "behavioral_config" in project_data:
                bc = project_data["behavioral_config"]
                behavioral_values = {
                    "default_thigmotaxis_distance_cm": bc.get("thigmotaxis_distance_cm"),
                    "default_geotaxis_distance_cm": bc.get("geotaxis_distance_cm"),
                    "default_geotaxis_num_zones": bc.get("geotaxis_num_zones"),
                    "default_geotaxis_bottom_zones": bc.get("geotaxis_bottom_zones"),
                    "aquarium_perspective": bc.get("aquarium_perspective"),
                    "geotaxis_mode": bc.get("geotaxis_mode"),
                }
                behavioral_values = {k: v for k, v in behavioral_values.items() if v is not None}

        if hasattr(current, "behavioral_analysis"):
            ba = current.behavioral_analysis
            defaults = {
                "default_thigmotaxis_distance_cm": ba.default_thigmotaxis_distance_cm,
                "default_geotaxis_distance_cm": ba.default_geotaxis_distance_cm,
                "default_geotaxis_num_zones": ba.default_geotaxis_num_zones,
                "default_geotaxis_bottom_zones": ba.default_geotaxis_bottom_zones,
                "aquarium_perspective": ba.aquarium_perspective,
                "geotaxis_mode": ba.geotaxis_mode,
            }
            for k, v in defaults.items():
                if k not in behavioral_values:
                    behavioral_values[k] = v

        values["behavioral_analysis"] = behavioral_values

        if self.gui.config_editor_widget:
            show_detection_summary = not bool(self.gui.controller.project_manager.project_path)
            self.gui.config_editor_widget.set_detection_summary_visible(show_detection_summary)
            self.gui.config_editor_widget.set_values(values)

    def on_reset_global_config_form_widget(self) -> None:
        """Reset ConfigEditorWidget form fields to reflect current settings object."""
        self.reload_config_editor_values_widget()
        self.dialog_manager.show_info(
            "Formulário recarregado",
            "Valores restaurados para refletir as configurações atuais.",
        )

    def on_save_global_config_from_widget(self, values: dict) -> None:
        """Validate and save config from ConfigEditorWidget values."""
        try:
            self._validate_config_values(values)
        except ValueError as exc:
            self.dialog_manager.show_error("Erro de Validação", str(exc))
            return

        update_payload: dict[str, Any] = values

        if self._settings is None:
            self.dialog_manager.show_error(
                "Erro", "Settings não disponível. Não foi possível salvar."
            )
            return

        from zebtrack.ui.components.validation_manager import ValidationManager

        merged = ValidationManager._deep_merge_dicts(self._settings.model_dump(), update_payload)

        try:
            validated = Settings.model_validate(merged)
        except ValidationError as exc:
            self.dialog_manager.show_error("Erro de Validação", str(exc))
            return

        if self.gui.controller.project_manager.project_path:
            self._update_current_project_settings(validated)
        else:
            self._update_global_settings_file(update_payload, validated)

    def _validate_config_values(self, values: dict) -> None:
        """Validate configuration values."""
        fps = values["video_processing"]["fps"]
        processing_interval = values["video_processing"]["processing_interval"]
        processing_offset = values["video_processing"]["processing_offset"]
        flush_interval = values["recorder"]["flush_interval_seconds"]
        flush_rows = values["recorder"]["flush_row_threshold"]
        window_length = values["trajectory_smoothing"]["window_length"]
        polyorder = values["trajectory_smoothing"]["polyorder"]

        if fps <= 0:
            raise ValueError("FPS deve ser maior que 0.")
        if processing_interval <= 0:
            raise ValueError("O intervalo de processamento deve ser maior que 0.")
        if processing_offset < 0:
            raise ValueError("O offset deve ser maior ou igual a 0.")
        if flush_interval < 0:
            raise ValueError("O intervalo de flush deve ser >= 0.")
        if flush_rows < 1:
            raise ValueError("O limite de linhas para flush deve ser >= 1.")
        if window_length < 3 or window_length % 2 == 0:
            raise ValueError("Window length deve ser ímpar e pelo menos 3.")
        if polyorder < 1:
            raise ValueError("Polyorder deve ser pelo menos 1.")

    def _update_current_project_settings(self, validated: Settings) -> None:
        """Update settings for the currently active project."""
        try:
            for field_name in validated.model_fields:
                setattr(
                    self._settings,
                    field_name,
                    getattr(validated, field_name),
                )

            project_data = self.gui.controller.project_manager.project_data

            project_data["analysis_interval_frames"] = (
                validated.video_processing.processing_interval
            )
            project_data["display_interval_frames"] = validated.video_processing.display_interval
            project_data["video_processing"] = validated.video_processing.model_dump()

            project_data["trajectory_smoothing"] = validated.trajectory_smoothing.model_dump()
            project_data["behavioral_config"] = validated.behavioral_analysis.model_dump()

            if "roi_settings" not in project_data:
                project_data["roi_settings"] = {}
            project_data["roi_settings"]["roi_inclusion_rule"] = validated.roi_inclusion_rule
            project_data["roi_settings"]["roi_buffer_radius_value"] = (
                validated.roi_buffer_radius_value
            )
            project_data["roi_settings"]["roi_min_bbox_overlap_ratio"] = (
                validated.roi_min_bbox_overlap_ratio
            )

            self.gui.controller.project_manager.save_project()

            self.dialog_manager.show_info(
                "Configurações do Projeto Atualizadas",
                "As alterações foram salvas APENAS no projeto atual.\n"
                "O arquivo global (config.local.yaml) NÃO foi alterado.",
            )

            self.reload_config_editor_values_widget()

        except (OSError, ValueError, AttributeError) as e:
            self.dialog_manager.show_error(
                "Erro ao Salvar no Projeto", f"Falha ao atualizar configurações do projeto: {e}"
            )

    def _update_global_settings_file(self, update_payload: dict, validated: Settings) -> None:
        from zebtrack.ui.components.validation_manager import ValidationManager

        """Update global settings file (config.local.yaml)."""
        override_path = Path("config.local.yaml")
        try:
            if override_path.exists():
                with open(override_path, encoding="utf-8") as handle:
                    override_content = yaml.safe_load(handle) or {}
            else:
                override_content = {}

            merged_override = ValidationManager._deep_merge_dicts(override_content, update_payload)
            with open(override_path, "w", encoding="utf-8") as handle:
                yaml.safe_dump(
                    merged_override,
                    handle,
                    sort_keys=False,
                    allow_unicode=True,
                )
        except (OSError, yaml.YAMLError) as exc:
            self.dialog_manager.show_error(
                "Erro", f"Não foi possível salvar config.local.yaml: {exc}"
            )
            return

        for field_name in validated.model_fields:
            setattr(
                self._settings,
                field_name,
                getattr(validated, field_name),
            )

        project_updated = False
        if self.gui.controller.project_manager.project_path:
            project_updated = self._sync_global_to_project(validated)

        self.reload_config_editor_values_widget()

        msg = "Alterações registradas em config.local.yaml."
        if project_updated:
            msg += "\n\nO projeto atual também foi atualizado com estes valores."

        self.dialog_manager.show_info("Configurações Salvas", msg)

    def _sync_global_to_project(self, validated: Settings) -> bool:
        """Sync global settings changes to the active project."""
        try:
            project_data = self.gui.controller.project_manager.project_data

            project_data["analysis_interval_frames"] = (
                validated.video_processing.processing_interval
            )
            project_data["display_interval_frames"] = validated.video_processing.display_interval

            project_data["fps"] = validated.video_processing.fps

            if "behavioral_config" not in project_data:
                project_data["behavioral_config"] = {}

            ba_settings = validated.behavioral_analysis
            project_data["behavioral_config"].update(
                {
                    "aquarium_perspective": ba_settings.aquarium_perspective,
                    "thigmotaxis_distance_cm": ba_settings.default_thigmotaxis_distance_cm,
                    "geotaxis_distance_cm": ba_settings.default_geotaxis_distance_cm,
                    "geotaxis_num_zones": ba_settings.default_geotaxis_num_zones,
                    "geotaxis_bottom_zones": ba_settings.default_geotaxis_bottom_zones,
                    "geotaxis_enabled": ba_settings.aquarium_perspective == "lateral",
                }
            )

            project_data["analysis_offset_frames"] = validated.video_processing.processing_offset

            if "analysis_parameters" not in project_data:
                project_data["analysis_parameters"] = {}

            project_data["analysis_parameters"].update(
                {
                    "smoothing_window_length": validated.trajectory_smoothing.window_length,
                    "smoothing_polyorder": validated.trajectory_smoothing.polyorder,
                }
            )

            if "roi_settings" not in project_data:
                project_data["roi_settings"] = {}

            project_data["roi_settings"].update(
                {
                    "roi_inclusion_rule": validated.roi_inclusion_rule,
                    "roi_buffer_radius_value": validated.roi_buffer_radius_value,
                    "roi_min_bbox_overlap_ratio": validated.roi_min_bbox_overlap_ratio,
                }
            )

            self.gui.controller.project_manager.save_project()
            log.info(
                "config.save.project_synced",
                project=self.gui.controller.project_manager.get_project_name(),
                analysis_interval=project_data["analysis_interval_frames"],
            )
            return True

        except (OSError, ValueError, KeyError, AttributeError) as e:
            log.error("config.save.project_sync_failed", error=str(e))
            self.dialog_manager.show_warning(
                "Aviso",
                f"Configuração global salva, mas erro ao atualizar projeto atual: {e}",
            )
            return False
