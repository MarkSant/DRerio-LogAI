"""Validation logic for ApplicationGUI.

Extracted from gui.py to reduce God Object complexity.
Handles field validation, form validation, requirement checks, pre-conditions,
data preparation, and formatting helpers.
"""

import copy
import os
import re
from collections import Counter
from pathlib import Path
from typing import Any

import structlog
import yaml
from pydantic import ValidationError

from zebtrack import settings as settings_module
from zebtrack.core.detector import ZoneData

log = structlog.get_logger()

# Status symbols and metadata (shared constants)
STATUS_SYMBOLS = {
    "arena": "\U0001f3df",  # 🏟
    "rois": "\U0001f3af",  # 🎯
    "trajectory": "\U0001f9ed",  # 🧭
    "summary": "\u03a3",  # Σ
}

PROJECT_STATUS_META: dict[str, tuple[str, str]] = {
    "pending": ("⏳", "Pendentes"),
    "processing": ("🔁", "Processando"),
    "processed": ("📦", "Com dados"),
    "complete": ("✅", "Concluídos"),
    "failed": ("⚠️", "Com falha"),
}


class ValidationManager:
    """Manages validation logic for ApplicationGUI."""

    def __init__(self, gui):
        """Initialize ValidationManager.

        Args:
            gui: Reference to ApplicationGUI instance
        """
        self.gui = gui

    # ========================================================================
    # Main Validation and Preparation Methods
    # ========================================================================

    @staticmethod
    def _deep_merge_dicts(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
        """Deep merge two dictionaries.

        Args:
            base: Base dictionary
            override: Override dictionary

        Returns:
            Merged dictionary
        """
        result = copy.deepcopy(base)
        for key, value in override.items():
            if isinstance(value, dict) and key in result and isinstance(result[key], dict):
                result[key] = ValidationManager._deep_merge_dicts(result[key], value)
            else:
                result[key] = value
        return result

    def save_global_config_from_widget(self, values: dict) -> None:
        """Validate and save config from ConfigEditorWidget values.

        Args:
            values: Configuration values from widget
        """
        try:
            # Extract values (already parsed by widget)
            fps = values["video_processing"]["fps"]
            processing_interval = values["video_processing"]["processing_interval"]
            processing_offset = values["video_processing"]["processing_offset"]
            flush_interval = values["recorder"]["flush_interval_seconds"]
            flush_rows = values["recorder"]["flush_row_threshold"]
            window_length = values["trajectory_smoothing"]["window_length"]
            polyorder = values["trajectory_smoothing"]["polyorder"]

            # Validate
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

        except ValueError as exc:
            self.gui.show_error("Erro de Validação", str(exc))
            return

        update_payload: dict[str, Any] = values

        active_settings = settings_module.settings
        if active_settings is None:
            try:
                active_settings = settings_module.load_settings()
                settings_module.settings = active_settings
            except Exception as exc:
                self.gui.show_error("Erro", f"Não foi possível carregar config.yaml: {exc}")
                return

        merged = self._deep_merge_dicts(active_settings.model_dump(), update_payload)

        try:
            validated = settings_module.Settings.model_validate(merged)
        except ValidationError as exc:
            self.gui.show_error("Erro de Validação", str(exc))
            return

        override_path = Path("config.local.yaml")
        try:
            if override_path.exists():
                with open(override_path, encoding="utf-8") as handle:
                    override_content = yaml.safe_load(handle) or {}
            else:
                override_content = {}

            merged_override = self._deep_merge_dicts(override_content, update_payload)
            with open(override_path, "w", encoding="utf-8") as handle:
                yaml.safe_dump(
                    merged_override,
                    handle,
                    sort_keys=False,
                    allow_unicode=True,
                )
        except Exception as exc:
            self.gui.show_error("Erro", f"Não foi possível salvar config.local.yaml: {exc}")
            return

        if settings_module.settings is None:
            settings_module.settings = validated
        else:
            for field_name in validated.model_fields:
                setattr(
                    settings_module.settings,
                    field_name,
                    getattr(validated, field_name),
                )

        self.gui._reload_config_editor_values_widget()
        self.gui.show_info(
            "Configurações salvas",
            "Alterações registradas em config.local.yaml e aplicadas ao aplicativo.",
        )

    def compose_overview_status_line(self, total: int, counts: Counter) -> str:
        """Compose status line for project overview.

        Args:
            total: Total number of videos
            counts: Counter of videos by status

        Returns:
            Formatted status string
        """
        if total <= 0:
            return "Nenhum vídeo cadastrado."

        parts: list[str] = [f"🧮 {total} vídeo(s)"]
        for key in ("pending", "processing", "processed", "complete", "failed"):
            value = counts.get(key, 0)
            if value:
                icon, _ = PROJECT_STATUS_META.get(key, ("•", key.title()))
                parts.append(f"{icon} {value}")

        others = sum(count for status, count in counts.items() if status not in PROJECT_STATUS_META)
        if others:
            parts.append(f"➕ {others}")

        return " • ".join(parts)

    def prepare_overview_hierarchy_for_widget(self, all_videos: list[dict]) -> dict:
        """Prepare hierarchy data in the format expected by ProjectOverviewWidget.

        Args:
            all_videos: List of video dictionaries with metadata

        Returns:
            Dictionary with 'groups' list containing formatted hierarchy
        """
        hierarchy = self._build_video_hierarchy_data(all_videos, "")

        groups_list = []

        for group_id, group_data in sorted(
            hierarchy.items(), key=lambda item: str(item[1]["display"]).lower()
        ):
            days_dict = group_data.get("days") or {}
            group_entries = [entry for videos in days_dict.values() for entry in videos or []]
            if not group_entries:
                continue

            # Calculate group-level summaries
            group_counts: Counter = Counter(
                (str(entry.get("status") or "pending")).strip().lower() for entry in group_entries
            )
            status_summary = self.format_status_summary(group_counts)
            data_summary = self.summarize_batch_data(group_entries)

            # Prepare days list for this group
            days_list = []
            for day_id, entries in sorted(
                days_dict.items(), key=lambda item: self._video_sort_key(item[0])
            ):
                entries = entries or []
                if not entries:
                    continue

                # Calculate day-level summaries
                day_counts: Counter = Counter(
                    (str(entry.get("status") or "pending")).strip().lower() for entry in entries
                )
                day_status = self.format_status_summary(day_counts)
                day_data = self.summarize_batch_data(entries)
                sample_metadata = entries[0].get("metadata") if entries else None
                day_title = self._build_day_title(day_id, sample_metadata)

                # Prepare videos list for this day
                videos_list = []
                for entry in sorted(
                    entries,
                    key=lambda item: self._video_sort_key(item.get("subject")),
                ):
                    path = entry.get("path") or ""
                    filename = entry.get("filename") or (
                        os.path.basename(path) if path else "(sem arquivo)"
                    )
                    metadata = entry.get("metadata") or {}
                    meta_snippet = self.format_video_metadata(metadata)

                    subject_label = self.format_subject_label(entry.get("subject"))
                    display_name = f"🐟 Sujeito {subject_label}"
                    if filename:
                        display_name = f"{display_name} ({filename})"
                    if meta_snippet:
                        display_name = f"{display_name} [{meta_snippet}]"

                    status_key = str(entry.get("status") or "pending").strip().lower()
                    status_display = self.format_status_label(status_key)
                    data_badges = self.format_data_badges(entry)

                    # Generate unique video ID
                    video_id = (
                        f"video_{path}"
                        if path
                        else f"video_{group_id}_{day_id}_{len(self.gui._overview_video_index)}"
                    )

                    videos_list.append(
                        {
                            "id": video_id,
                            "display_name": display_name,
                            "status": status_display,
                            "data_badges": data_badges,
                            "path": path,
                        }
                    )

                    # Store in video index for lookups
                    if path:
                        self.gui._overview_video_index[path] = dict(entry)

                # Add day to list
                days_list.append(
                    {
                        "id": day_id,
                        "title": day_title,
                        "status": day_status,
                        "data": day_data,
                        "videos": videos_list,
                    }
                )

            # Add group to list
            groups_list.append(
                {
                    "id": group_id,
                    "display": group_data["display"],
                    "status_summary": status_summary,
                    "data_summary": data_summary,
                    "days": days_list,
                }
            )

        return {"groups": groups_list}

    def check_live_project_calibration(self) -> None:
        """Check if Live project needs calibration and prompt user automatically.

        This is called when opening a Live project to ensure zone configuration
        is set up before analysis.
        """
        if self.gui.controller.project_manager.get_project_type() != "live":
            return

        zone_data = self.get_zone_data_for_active_context()
        if not zone_data or not zone_data.polygon:
            log.info("ui.live_calibration.auto_prompt")

            response = self.gui.ask_ok_cancel(
                "Calibração Automática",
                "Nenhuma arena principal foi definida para este projeto ao vivo.\n\n"
                "Deseja configurar a calibração automaticamente agora?\n\n"
                "• Será aberta a aba de Configuração de Zonas\n"
                "• Você pode usar 'Detectar Aquário (Auto)' ou desenhar manualmente\n"
                "• A configuração será salva automaticamente",
            )

            if response:
                log.info("ui.live_calibration.auto_accepted")
                # Switch to zone configuration tab
                if hasattr(self.gui, "notebook") and hasattr(self.gui, "zone_tab_frame"):
                    self.gui.notebook.select(self.gui.zone_tab_frame)

                # Show guidance message
                self.gui.show_info(
                    "Configuração de Arena Principal",
                    "Configure a arena principal usando:\n\n"
                    "1. 'Detectar Aquário (Auto)' - Para detecção automática\n"
                    "2. 'Desenhar Polígono Principal' - Para desenho manual\n\n"
                    "A configuração será salva automaticamente.",
                )
            else:
                log.info("ui.live_calibration.auto_declined")

    def prepare_single_video_ui_state(self, config: dict | None) -> None:
        """Ensure zone controls reflect the incoming single-video configuration.

        Args:
            config: Configuration dictionary with analysis parameters
        """
        zone_controls = getattr(self.gui, "zone_controls", None)
        if not zone_controls:
            return

        try:
            zone_controls.show_single_analysis_options()
        except Exception:
            pass

        analysis_interval = None
        display_interval = None
        roi_choice = None
        stabilization_frames = None

        if config:
            analysis_interval = config.get("analysis_interval_frames")
            display_interval = config.get("display_interval_frames")
            roi_choice = config.get("roi_choice")
            stabilization_frames = config.get("stabilization_frames")

        if analysis_interval is None:
            analysis_interval = self.gui.analysis_interval_var.get()
        if display_interval is None:
            display_interval = self.gui.display_interval_var.get()
        if stabilization_frames is None:
            stabilization_frames = self.gui.stabilization_frames_var.get()

        # Share the same StringVar instances so edits from either side stay in sync
        self.gui.analysis_interval_var = zone_controls.analysis_interval_var
        self.gui.display_interval_var = zone_controls.display_interval_var
        self.gui.roi_choice_var = zone_controls.roi_choice_var
        self.gui.stabilization_frames_var = zone_controls.stabilization_frames_var

        self.gui.analysis_interval_var.set(str(analysis_interval or "10"))
        self.gui.display_interval_var.set(str(display_interval or "10"))
        self.gui.roi_choice_var.set(roi_choice or "none")
        self.gui.stabilization_frames_var.set(str(stabilization_frames or "10"))

    def compose_single_video_runtime_config(self) -> dict | None:
        """Collect the latest single-video settings before starting processing.

        Validates that intervals are positive integers.

        Returns:
            Configuration dictionary, or None if validation fails
        """
        if not self.gui.pending_single_video_config:
            return None

        config = dict(self.gui.pending_single_video_config)

        # Prefer values from the new zone controls component when available
        zone_controls = getattr(self.gui, "zone_controls", None)
        if zone_controls:
            analysis_var = zone_controls.analysis_interval_var.get()
            display_var = zone_controls.display_interval_var.get()
            roi_choice = zone_controls.roi_choice_var.get()
            stabilization_var = zone_controls.stabilization_frames_var.get()
        else:
            analysis_var = self.gui.analysis_interval_var.get()
            display_var = self.gui.display_interval_var.get()
            roi_choice = config.get("roi_choice", "none")
            stabilization_var = self.gui.stabilization_frames_var.get()

        try:
            analysis_interval = int(analysis_var)
            display_interval = int(display_var)
            if analysis_interval <= 0 or display_interval <= 0:
                raise ValueError
            stabilization_frames = int(stabilization_var)
            if stabilization_frames <= 0:
                raise ValueError
        except (TypeError, ValueError):
            self.gui.show_error(
                "Erro",
                (
                    "Os intervalos devem ser números inteiros positivos "
                    "(análise, exibição e estabilização)."
                ),
            )
            return None

        config["analysis_interval_frames"] = analysis_interval
        config["display_interval_frames"] = display_interval
        config["roi_choice"] = roi_choice
        config["stabilization_frames"] = stabilization_frames

        return config

    # ========================================================================
    # Zone and Template Validation
    # ========================================================================

    def get_zone_data_for_active_context(self) -> ZoneData:
        """Get zone data for the currently active context (video or global).

        Returns:
            ZoneData object, potentially empty if no zone data exists
        """
        pm = getattr(self.gui.controller, "project_manager", None)
        if pm is None:
            return ZoneData()

        active_video = pm.get_active_zone_video()
        if not active_video:
            pending_video = getattr(self.gui, "pending_single_video_path", None)
            active_video = pending_video

        if active_video:
            try:
                zone_data = pm.get_zone_data(
                    video_path=active_video,
                    fallback_to_global=False,
                )
            except Exception:
                zone_data = ZoneData()

            if zone_data and (zone_data.polygon or zone_data.roi_polygons):
                return zone_data

        return pm.get_zone_data()

    def get_selected_roi_template(self) -> dict[str, Any] | None:
        """Get the currently selected template from the dropdown.

        Returns:
            Template dictionary, or None if no template selected
        """
        if not self.gui._roi_templates_cache:
            log.debug("gui.get_selected_roi_template.empty_cache")
            return None

        current_display = self.gui.roi_template_var.get().strip()
        if not current_display:
            log.debug("gui.get_selected_roi_template.no_selection")
            return None

        log.debug(
            "gui.get_selected_roi_template.searching",
            current_display=current_display,
            cache_size=len(self.gui._roi_templates_cache),
            available_names=[e.get("display_name") for e in self.gui._roi_templates_cache],
        )

        for entry in self.gui._roi_templates_cache:
            if entry.get("display_name") == current_display:
                log.info(
                    "gui.get_selected_roi_template.found",
                    display_name=current_display,
                    template_name=entry.get("name"),
                )
                return entry

        log.warning(
            "gui.get_selected_roi_template.not_found",
            current_display=current_display,
            cache_entries=[e.get("display_name") for e in self.gui._roi_templates_cache],
        )
        return None

    def validate_roi_template_data(self, zone_data: ZoneData | None) -> tuple[bool, str]:
        """Validate that zone data contains sufficient information for a template.

        Args:
            zone_data: ZoneData object to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        if not zone_data or (not zone_data.polygon and not (zone_data.roi_polygons or [])):
            return False, "Desenhe a arena ou pelo menos uma ROI antes de salvar um template."
        return True, ""

    def validate_arena_for_analysis(self, arena_id: str | None) -> tuple[bool, str]:
        """Validate that an arena ID is selected and valid.

        Args:
            arena_id: Arena identifier to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        if not arena_id:
            return False, "Selecione um aquário ativo primeiro."
        return True, ""

    def validate_arena_polygon_data(
        self, arena_data: dict | None
    ) -> tuple[bool, str, dict | None]:
        """Validate that arena data contains polygon information.

        Args:
            arena_data: Arena data dictionary

        Returns:
            Tuple of (is_valid, error_message, arena_data)
        """
        if not arena_data or "polygon_px" not in arena_data:
            return False, "Não foi possível obter os dados do polígono do aquário.", None
        return True, "", arena_data

    def validate_positive_integer(
        self, value: Any, field_name: str = "valor"
    ) -> tuple[bool, str, int | None]:
        """Validate that a value is a positive integer.

        Args:
            value: Value to validate
            field_name: Name of the field for error message

        Returns:
            Tuple of (is_valid, error_message, parsed_value)
        """
        try:
            int_value = int(value)
            if int_value <= 0:
                raise ValueError
            return True, "", int_value
        except (ValueError, TypeError):
            return (
                False,
                f"O {field_name} deve ser um número inteiro positivo.",
                None,
            )

    def validate_active_video_selection(self, active_video: str | None) -> tuple[bool, str]:
        """Validate that a video is selected for operations requiring active video.

        Args:
            active_video: Video path or identifier

        Returns:
            Tuple of (is_valid, error_message)
        """
        if not active_video:
            return False, "Selecione um vídeo antes de aplicar o template."
        return True, ""

    # ========================================================================
    # Formatting and Display Methods
    # ========================================================================

    def format_status_label(self, status_key: str) -> str:
        """Format status key into display label with icon.

        Args:
            status_key: Status identifier

        Returns:
            Formatted status string with icon
        """
        icon, label = self._get_status_meta(status_key)
        return f"{icon} {label}"

    def format_status_summary(self, counts: Counter) -> str:
        """Format status counts into summary string.

        Args:
            counts: Counter of items by status

        Returns:
            Formatted summary string
        """
        parts: list[str] = []
        for key in PROJECT_STATUS_META:
            value = counts.get(key, 0)
            if value:
                icon, _ = PROJECT_STATUS_META[key]
                parts.append(f"{icon} {value}")

        others = sum(count for status, count in counts.items() if status not in PROJECT_STATUS_META)
        if others:
            parts.append(f"➕ {others}")

        return " | ".join(parts) if parts else "-"

    @staticmethod
    def format_status_ratio(symbol_key: str, completed: int, total: int) -> str:
        """Format completion ratio with status symbol.

        Args:
            symbol_key: Key for STATUS_SYMBOLS
            completed: Number completed
            total: Total number

        Returns:
            Formatted ratio string
        """
        symbol = STATUS_SYMBOLS[symbol_key]
        safe_total = max(total, 0)
        clamped_completed = max(0, min(completed, safe_total)) if safe_total else 0
        if safe_total:
            return f"{symbol} {clamped_completed}/{safe_total}"
        return f"{symbol} 0/0"

    def summarize_batch_data(self, videos: list[dict]) -> str:
        """Summarize data availability across a batch of videos.

        Args:
            videos: List of video dictionaries

        Returns:
            Formatted summary string with data badges
        """
        if not videos:
            return "-"

        total = len(videos)
        arena_count = sum(1 for video in videos if video.get("has_arena"))
        roi_count = sum(1 for video in videos if video.get("has_rois"))
        traj_count = sum(1 for video in videos if video.get("has_trajectory"))
        complete_count = sum(
            1
            for video in videos
            if video.get("has_complete_data")
            or (video.get("has_arena") and video.get("has_rois") and video.get("has_trajectory"))
        )

        return (
            f"{self.format_status_ratio('arena', arena_count, total)}  "
            f"{self.format_status_ratio('rois', roi_count, total)}  "
            f"{self.format_status_ratio('trajectory', traj_count, total)}  "
            f"{self.format_status_ratio('summary', complete_count, total)}"
        )

    def format_data_badges(self, video: dict) -> str:
        """Format data availability badges for a video.

        Args:
            video: Video dictionary with data flags

        Returns:
            Formatted badges string
        """
        has_arena = bool(video.get("has_arena"))
        has_rois = bool(video.get("has_rois"))
        has_trajectory = bool(video.get("has_trajectory"))
        has_complete = bool(video.get("has_complete_data")) or (
            has_arena and has_rois and has_trajectory
        )

        markers = [
            self.format_status_token(has_arena, "arena"),
            self.format_status_token(has_rois, "rois"),
            self.format_status_token(has_trajectory, "trajectory"),
            self.format_status_token(has_complete, "summary"),
        ]
        return "  ".join(markers)

    def format_video_metadata(self, metadata: dict) -> str:
        """Format video metadata into compact display string.

        Args:
            metadata: Metadata dictionary

        Returns:
            Formatted metadata string (e.g., "G:1 D:03 S:05")
        """
        if not metadata:
            return ""

        parts: list[str] = []
        group = metadata.get("group")
        if group not in (None, ""):
            parts.append(f"G:{group}")

        day = metadata.get("day")
        if day not in (None, ""):
            day_display = metadata.get("day_label") or self._format_day_display(day)
            parts.append(f"D:{day_display or day}")

        subject = metadata.get("subject")
        if subject not in (None, ""):
            parts.append(f"S:{self.format_subject_label(subject)}")

        return " ".join(parts)

    @staticmethod
    def format_status_token(has_parquet: bool, symbol_key: str) -> str:
        """Format status token with checkmark or X.

        Args:
            has_parquet: Whether data exists
            symbol_key: Key for STATUS_SYMBOLS

        Returns:
            Formatted token string
        """
        symbol = STATUS_SYMBOLS[symbol_key]
        return f"{symbol} ✓" if has_parquet else f"{symbol} ✗"

    @staticmethod
    def format_subject_label(value) -> str:
        """Format subject value into consistent label.

        Args:
            value: Subject identifier (int, float, or string)

        Returns:
            Formatted subject label (e.g., "05" or "??")
        """
        if value is None:
            return "??"
        if isinstance(value, int):
            return f"{value:02d}"
        if isinstance(value, float) and value.is_integer():
            return f"{int(value):02d}"
        value_str = str(value).strip()
        if not value_str:
            return "??"
        if value_str.isdigit():
            try:
                return f"{int(value_str):02d}"
            except ValueError:
                return value_str
        return value_str

    @staticmethod
    def format_day_display(value) -> str:
        """Format day value into consistent display format.

        Args:
            value: Day identifier (int, float, or string)

        Returns:
            Formatted day label (e.g., "03" or "Sem Dia")
        """
        if value in (None, ""):
            return ""
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            try:
                return f"{int(value):02d}"
            except (TypeError, ValueError):
                return str(value)
        value_str = str(value).strip()
        if not value_str:
            return ""
        lower_value = value_str.lower()
        if lower_value == "sem dia":
            return "Sem Dia"
        match = re.search(r"(\d+)", value_str)
        if match:
            try:
                return f"{int(match.group(1)):02d}"
            except ValueError:
                return value_str
        return value_str

    def format_roi_template_display(self, template: dict[str, Any]) -> str:
        """Format ROI template metadata into display string.

        Args:
            template: Template metadata dictionary

        Returns:
            Formatted display string
        """
        base_name = template.get("name", "")
        location = template.get("location", "project")

        content_parts: list[str] = []
        if template.get("includes_arena"):
            content_parts.append("Arena")
        if template.get("includes_rois"):
            content_parts.append("ROIs")

        if not content_parts:
            content_label = "Sem dados"
        elif len(content_parts) == 2:
            content_label = "Arena + ROIs"
        else:
            content_label = content_parts[0]

        location_label: str | None = None
        if location == "global":
            location_label = "Global"
        elif location not in {"project", "global", None}:
            location_label = str(location)

        suffix_parts = [content_label] if content_label else []
        if location_label:
            suffix_parts.append(location_label)

        suffix = f" ({'; '.join(suffix_parts)})" if suffix_parts else ""

        if base_name:
            return f"{base_name}{suffix}"

        return suffix.lstrip() or "Template"

    def build_roi_template_identifier(self, template: dict[str, Any]) -> str:
        """Build unique identifier for ROI template.

        Args:
            template: Template metadata dictionary

        Returns:
            Unique identifier string
        """
        location = template.get("location", "project")
        slug = template.get("slug") or ""
        file_ref = template.get("file") or ""

        if location == "project" and slug:
            return f"{location}:{slug}"

        if file_ref:
            return f"{location}:{file_ref}"

        return f"{location}:{template.get('name', '')}"

    @staticmethod
    def format_time(seconds: float) -> str:
        """Format seconds into human-readable time string.

        Args:
            seconds: Time in seconds

        Returns:
            Formatted time string (e.g., "1h 23m 45s")
        """
        if seconds is None or seconds < 0:
            return "-"
        m, s = divmod(int(seconds), 60)
        h, m = divmod(m, 60)
        if h:
            return f"{h:d}h {m:02d}m {s:02d}s"
        if m:
            return f"{m:d}m {s:02d}s"
        return f"{s:d}s"

    @staticmethod
    def format_subject_for_reports(value) -> str:
        """Format subject value for reports (alias for format_subject_label).

        This is a duplicate method that exists in gui.py for historical reasons.
        It is identical to format_subject_label.

        Args:
            value: Subject identifier (int, float, or string)

        Returns:
            Formatted subject label (e.g., "05" or "??")
        """
        return ValidationManager.format_subject_label(value)

    # ========================================================================
    # Internal Helper Methods
    # ========================================================================

    @staticmethod
    def _get_status_meta(status_key: str) -> tuple[str, str]:
        """Get status icon and label for a status key.

        Args:
            status_key: Status identifier

        Returns:
            Tuple of (icon, label)
        """
        if status_key == "total":
            return "🧮", "Total"
        if status_key == "arena":
            return STATUS_SYMBOLS["arena"], "Arena"
        if status_key == "rois":
            return STATUS_SYMBOLS["rois"], "ROIs"
        if status_key == "trajectory":
            return STATUS_SYMBOLS["trajectory"], "Trajetória"
        if status_key == "summary":
            return STATUS_SYMBOLS["summary"], "Sumário"
        return PROJECT_STATUS_META.get(status_key, ("•", status_key.title()))

    @staticmethod
    def _video_sort_key(value):
        """Generate sort key for video/subject identifiers.

        Args:
            value: Identifier to sort

        Returns:
            Tuple of (type_priority, sort_value)
        """
        try:
            return (0, int(value))
        except (TypeError, ValueError):
            value_str = str(value) if value is not None else ""
            return (1, value_str.lower())

    def _format_day_display(self, value) -> str:
        """Format day value (wrapper for static method).

        Args:
            value: Day identifier

        Returns:
            Formatted day label
        """
        return self.format_day_display(value)

    def _build_day_title(self, day_value, metadata: dict | None = None) -> str:
        """Build day title with proper formatting.

        Args:
            day_value: Day identifier
            metadata: Optional metadata dictionary

        Returns:
            Formatted day title (e.g., "Dia 03")
        """
        metadata = metadata or {}
        candidate = metadata.get("day_label") or ""
        if not candidate and metadata.get("day") is not None:
            candidate = self._format_day_display(metadata.get("day"))
        if not candidate:
            candidate = self._format_day_display(day_value)
        if not candidate:
            base_value = day_value if day_value not in (None, "") else None
            candidate = str(base_value) if base_value is not None else "Sem Dia"
        candidate_str = str(candidate).strip()
        if not candidate_str:
            candidate_str = "Sem Dia"
        if candidate_str.lower() == "sem dia":
            return "Sem Dia"
        return f"Dia {candidate_str}"

    def _build_video_hierarchy_data(
        self,
        all_videos: list[dict],
        search_text: str,
    ) -> dict[str, dict]:
        """Build hierarchical data structure for videos grouped by group and day.

        Args:
            all_videos: List of video dictionaries
            search_text: Optional search filter

        Returns:
            Nested dictionary: {group_id: {display, days: {day_id: [videos]}}}
        """
        hierarchy: dict[str, dict] = {}

        normalized = search_text.strip().lower()

        for video in all_videos:
            metadata = video.get("metadata") or {}
            group_id = metadata.get("group") or "Sem Grupo"
            group_display = metadata.get("group_display_name") or group_id
            day_id = metadata.get("day") or "Sem Dia"
            day_display = metadata.get("day_label") or self._format_day_display(day_id)
            subject_id = metadata.get("subject")
            filename = os.path.basename(video.get("path", ""))
            status_label = video.get("status", "")

            searchable_values = (
                str(group_id),
                str(group_display),
                str(day_id),
                str(day_display),
                str(subject_id) if subject_id is not None else "",
                filename,
                status_label,
            )

            if normalized and not any(
                normalized in str(value).lower() for value in searchable_values
            ):
                continue

            group_data = hierarchy.setdefault(
                group_id,
                {"display": group_display, "days": {}},
            )
            days_dict = group_data["days"]

            has_arena = bool(video.get("has_arena"))
            has_rois = bool(video.get("has_rois"))
            has_trajectory = bool(video.get("has_trajectory"))
            has_complete = bool(video.get("has_complete_data")) or (
                has_arena and has_rois and has_trajectory
            )
            has_summary = bool(video.get("has_summary")) or bool(video.get("has_summary_parquet"))

            video_entry = {
                "path": video.get("path"),
                "metadata": metadata,
                "day_label": day_display,
                "has_arena": has_arena,
                "has_rois": has_rois,
                "has_trajectory": has_trajectory,
                "has_complete_data": has_complete,
                "has_summary": has_summary,
                "filename": filename,
                "status": status_label,
                "subject": subject_id,
            }

            days_dict.setdefault(day_id, []).append(video_entry)

        return hierarchy

    def build_video_hierarchy_snapshot(self) -> list[dict]:
        """Build hierarchical snapshot of videos for display."""
        controller = getattr(self.gui, "controller", None)
        if not controller or not controller.project_manager:
            return []

        pm = controller.project_manager
        all_videos = pm.get_all_videos() or []
        hierarchy = self._build_video_hierarchy_data(all_videos, "")

        snapshot: list[dict] = []
        for group_id, group_data in sorted(
            hierarchy.items(), key=lambda item: str(item[1]["display"]).lower()
        ):
            group_entry = {
                "label": f"🏷️ {group_data['display']} ({group_id})",
                "status_label": "",
                "filename_display": "",
                "children": [],
            }
            for day_id, videos in sorted(
                group_data["days"].items(),
                key=lambda item: self._video_sort_key(item[0]),
            ):
                sample_metadata = videos[0].get("metadata") if videos else None
                day_title = self._build_day_title(day_id, sample_metadata)
                day_entry = {
                    "label": f"📅 {day_title}",
                    "status_label": "",
                    "children": [],
                }
                for video_entry in sorted(
                    videos,
                    key=lambda entry: self._video_sort_key(entry.get("subject")),
                ):
                    subject_label = self.format_subject_label(video_entry.get("subject"))
                    has_arena = video_entry.get("has_arena", False)
                    has_rois = video_entry.get("has_rois", False)
                    has_traj = video_entry.get("has_trajectory", False)
                    status_tokens = " ".join(
                        [
                            self.format_status_token(has_arena, "arena"),
                            self.format_status_token(has_rois, "rois"),
                            self.format_status_token(has_traj, "trajectory"),
                        ]
                    )
                    day_entry["children"].append(
                        {
                            "path": video_entry.get("path"),
                            "label": f"🐟 Sujeito {subject_label}",
                            "filename": video_entry.get("filename", ""),
                            "status_label": status_tokens,
                        }
                    )
                group_entry["children"].append(day_entry)
            snapshot.append(group_entry)

        return snapshot
