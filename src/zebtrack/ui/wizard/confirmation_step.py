"""
Step 5: Confirmation & Summary Dialog.

Shows final summary of all wizard steps and allows project name/location configuration.
Validates all settings before enabling project creation.
"""

import copy
import os
import re
from pathlib import Path
from tkinter import (
    Button,
    Entry,
    Frame,
    Label,
    LabelFrame,
    StringVar,
    Text,
    filedialog,
    messagebox,
    simpledialog,
)
from tkinter import (
    font as tkfont,
)

import structlog

from zebtrack.i18n import _
from zebtrack.ui.window_utils import create_scrollbar
from zebtrack.ui.wizard.base import WizardStep
from zebtrack.ui.wizard.enums import ImportAction, ProjectType, WizardStepID
from zebtrack.ui.wizard.templates import (
    TemplateManager,
    format_template_banner,
    format_template_banner_details,
)

log = structlog.get_logger()


class ConfirmationStep(WizardStep):
    """
    Confirmation step - final review and project creation.

    Processing:
        1. Load all wizard data from previous steps
        2. Generate summary
        3. Allow project name/location editing
        4. Validate before enabling creation
        5. Return final project configuration

    Output:
        {
            "project_name": str,
            "project_path": str,  # Full path including project name
            # All previous wizard data is preserved
        }
    """

    def __init__(self, parent, wizard_data: dict):
        """Initialize confirmation step."""
        super().__init__(parent, wizard_data)
        self.step_id = WizardStepID.CONFIRMATION

        # State
        self.project_name_var = StringVar(value="")
        self.project_location_var = StringVar(value=str(Path.home() / "Documents"))
        self.summary_text = ""
        self.template_manager = TemplateManager()
        self.template_info_var = StringVar(value="")
        self.template_info_label: Label | None = None
        self._responsive_labels: list[Label] = []

    def build_ui(self):
        """Build confirmation step UI with scrollable summary text."""
        background_color = self.cget("background")

        # Main container (fixed header + scrollable summary + fixed buttons)
        self.content_container = Frame(self, bg=background_color)
        self.content_container.pack(fill="both", expand=True, padx=16, pady=12)

        # Title
        title_font = tkfont.Font(size=14, weight="bold")
        title = Label(
            self.content_container,
            text=_("Project Confirmation and Creation"),
            font=title_font,
            bg=background_color,
        )
        title.pack(pady=(0, 10))

        subtitle = Label(
            self.content_container,
            text=_("Review the settings and create your project."),
            fg="gray",
            wraplength=720,
            bg=background_color,
        )
        subtitle.pack(pady=(0, 20))
        self._responsive_labels.append(subtitle)

        self.template_info_label = Label(
            self.content_container,
            textvariable=self.template_info_var,
            fg="#555555",
            wraplength=720,
            justify="left",
            bg=background_color,
        )
        self.template_info_label.pack_forget()
        if self.template_info_label:  # Conditional append for type safety
            self._responsive_labels.append(self.template_info_label)
        self._update_template_banner()

        # Project name
        name_frame = Frame(self.content_container, bg=background_color)
        name_frame.pack(fill="x", pady=(0, 10))

        Label(
            name_frame,
            text=_("Project Name:"),
            width=20,
            anchor="w",
        ).pack(side="left")
        Entry(name_frame, textvariable=self.project_name_var, width=40).pack(
            side="left",
            padx=(5, 0),
            fill="x",
            expand=True,
        )

        # Project location
        location_frame = Frame(self.content_container, bg=background_color)
        location_frame.pack(fill="x", pady=(0, 15))

        Label(
            location_frame,
            text=_("Location:"),
            width=20,
            anchor="w",
        ).pack(side="left")
        Entry(location_frame, textvariable=self.project_location_var, width=30).pack(
            side="left",
            padx=(5, 5),
            fill="x",
            expand=True,
        )
        Button(
            location_frame,
            text=_("Browse..."),
            command=self._browse_location,
        ).pack(side="left")

        # Summary (with controlled height to prevent button occlusion)
        summary_frame = LabelFrame(
            self.content_container, text=_("Project Summary"), padx=10, pady=10
        )
        summary_frame.pack(fill="both", expand=True, pady=(0, 10), padx=4)

        summary_container = Frame(summary_frame)
        summary_container.pack(fill="both", expand=True)

        self.summary_textbox = Text(
            summary_container,
            height=20,
            wrap="word",
            state="disabled",
            relief="flat",
        )
        self.summary_textbox.configure(width=0)
        self.summary_textbox.pack(side="left", fill="both", expand=True)

        summary_scrollbar = create_scrollbar(
            summary_container,
            orient="vertical",
            command=self.summary_textbox.yview,
        )
        self.summary_textbox.configure(yscrollcommand=summary_scrollbar.set)
        summary_scrollbar.pack(side="right", fill="y")

        # Template button
        template_btn_frame = Frame(self.content_container, bg=background_color)
        template_btn_frame.pack(fill="x", pady=(10, 0))

        Button(
            template_btn_frame,
            text=_("💾 Save as Template"),
            command=self._save_as_template,
            width=25,
        ).pack(side="right")

        # Help text
        help_text = Label(
            self.content_container,
            text=_(
                "💡 Tip: Review every setting before creating the project. "
                "You can save it as a template to reuse later."
            ),
            fg="gray",
            wraplength=720,
            justify="left",
            bg=background_color,
        )
        help_text.pack(pady=(10, 0))
        self._responsive_labels.append(help_text)

        self.after(0, self._initial_wrap_refresh)

    def on_show(self):
        """Execute actions when step becomes visible - generate summary."""
        self._generate_default_project_name()
        self._generate_summary()
        self._update_template_banner()

    def _initial_wrap_refresh(self) -> None:
        """Refresh wraplengths based on current widget width."""
        if not self.winfo_exists():
            return
        width = self.winfo_width()
        if width:
            self._update_wraplengths(width)

    def _update_wraplengths(self, canvas_width: int) -> None:
        usable = max(canvas_width - 60, 480)
        for label in self._responsive_labels:
            if label and label.winfo_exists():
                label.configure(wraplength=usable)

    def _generate_default_project_name(self):
        """Generate default project name based on project type."""
        if self.project_name_var.get():
            return  # Already has a name

        project_type = self.wizard_data.get("project_type", ProjectType.EXPERIMENTAL.value)

        if project_type == ProjectType.EXPERIMENTAL.value:
            # Use detected groups if available
            detected_design = self.wizard_data.get("detected_design")
            if detected_design and detected_design.get("groups"):
                groups = detected_design["groups"]
                name = _("Experiment_{group}").format(group=groups[0])
            else:
                name = _("Experimental_Project")
        else:
            name = _("Exploratory_Project")

        # Add timestamp to make unique
        from datetime import datetime

        timestamp = datetime.now().strftime("%Y%m%d")
        name = f"{name}_{timestamp}"

        self.project_name_var.set(name)

    def _browse_location(self):
        """Open directory browser for project location."""
        directory = filedialog.askdirectory(
            title=_("Select the Project Folder"),
            initialdir=self.project_location_var.get(),
        )
        if directory:
            self.project_location_var.set(directory)

    def _generate_summary(self):
        """Generate summary text from all wizard data (refactored)."""
        lines: list[str] = []

        # Template metadata
        self._append_template_info(lines)

        # Project type
        project_type = self.wizard_data.get("project_type", "experimental")
        is_live = project_type == ProjectType.LIVE.value
        self._append_project_type(lines, project_type)

        # Live-specific configuration
        if is_live:
            self._append_live_configuration(lines)
        else:
            # Pre-recorded specifics
            self._append_detected_design(lines)
            self._append_custom_regex_info(lines)
            self._append_detection_settings(lines)
            self._append_folder_preview(lines)

        # Calibration
        self._append_calibration(lines)

        # Processing plan and parquet/import summaries (pre-recorded only)
        if not is_live:
            self._append_processing_plan(lines)
            self._append_parquet_summary(lines)
            self._append_import_configuration(lines)
            self._append_roi_strategy(lines)

        self.summary_text = "\n".join(lines)
        if hasattr(self, "summary_textbox") and self.summary_textbox:
            self.summary_textbox.configure(state="normal")
            self.summary_textbox.delete("1.0", "end")
            self.summary_textbox.insert("1.0", self.summary_text)
            self.summary_textbox.configure(state="disabled")
            self.summary_textbox.yview_moveto(0.0)

    def on_hide(self):
        """Execute actions when step is hidden (no special cleanup needed now)."""
        pass

    # ------------------------------------------------------------------
    # Summary helper methods (split from _generate_summary)
    # ------------------------------------------------------------------
    def _append_template_info(self, lines: list[str]) -> None:
        metadata = self.wizard_data.get("template_metadata")
        if not metadata:
            return

        lines.append(_("📝 Template Loaded:"))
        details = format_template_banner_details(metadata)
        if details:
            lines.append(f"  • {details}")
        if metadata.get("created_at"):
            lines.append(_("  • Created at: {value}").format(value=metadata["created_at"]))
        if metadata.get("schema_version"):
            lines.append(
                _("  • Template version: {value}").format(value=metadata["schema_version"])
            )
        lines.append("")

    def _append_project_type(self, lines: list[str], project_type: str) -> None:
        lines.append(_("📋 Project Type:"))
        type_names = {
            ProjectType.EXPERIMENTAL.value: _("Experimental (pre-recorded)"),
            ProjectType.EXPLORATORY.value: _("Exploratory (pre-recorded)"),
            ProjectType.LIVE.value: _("Live (real time)"),
        }
        lines.append(f"  • {type_names.get(project_type, project_type.capitalize())}")

    def _append_live_configuration(self, lines: list[str]) -> None:
        # Experimental Design
        experiment_days = self.wizard_data.get("experiment_days")
        num_groups = self.wizard_data.get("num_groups")
        subjects_per_group = self.wizard_data.get("subjects_per_group")
        group_names = self.wizard_data.get("group_names", [])

        if experiment_days or num_groups or subjects_per_group:
            lines.append("")
            lines.append(_("🔬 Experimental Design:"))
            if num_groups and subjects_per_group and experiment_days:
                total_sessions = num_groups * subjects_per_group * experiment_days
                total_animals = num_groups * subjects_per_group
                lines.append(
                    _("  • {groups} groups x {days} days x {subjects} animals/group").format(
                        groups=num_groups,
                        days=experiment_days,
                        subjects=subjects_per_group,
                    )
                )
                lines.append(
                    _("  • Total: {sessions} recordings ({animals} animals)").format(
                        sessions=total_sessions, animals=total_animals
                    )
                )
            if group_names:
                group_list = ", ".join(group_names)
                lines.append(_("  • Groups: {groups}").format(groups=group_list))

        # Camera & Hardware
        lines.append("")
        lines.append(_("📹 Hardware:"))
        camera_index = self.wizard_data.get("camera_index", 0)
        camera_friendly_name = self.wizard_data.get("camera_friendly_name", "")
        if camera_friendly_name:
            lines.append(
                _("  • Camera: {name} (index {index})").format(
                    name=camera_friendly_name, index=camera_index
                )
            )
        else:
            lines.append(_("  • Camera: index {index}").format(index=camera_index))

        if self.wizard_data.get("use_arduino"):
            arduino_port = self.wizard_data.get("arduino_port", "N/A")
            lines.append(_("  • Arduino: {port}").format(port=arduino_port))
            if self.wizard_data.get("external_trigger_mode"):
                lines.append(_("  • Mode: External Trigger ✓"))

        # Recording Settings
        if self.wizard_data.get("use_timed_recording") or self.wizard_data.get("use_countdown"):
            lines.append("")
            lines.append(_("⏱️ Recording Settings:"))
            if self.wizard_data.get("use_timed_recording"):
                duration = self.wizard_data.get("recording_duration_s", 0)
                minutes = int(duration // 60)
                seconds = int(duration % 60)
                lines.append(
                    _("  • Timed recording: {minutes}min {seconds}s").format(
                        minutes=minutes, seconds=seconds
                    )
                )
            if self.wizard_data.get("use_countdown"):
                countdown = self.wizard_data.get("countdown_duration_s", 0)
                lines.append(_("  • Countdown: {seconds}s").format(seconds=countdown))

        # Processing Intervals
        analysis_interval = self.wizard_data.get("analysis_interval_frames")
        display_interval = self.wizard_data.get("display_interval_frames")
        if analysis_interval or display_interval:
            lines.append("")
            lines.append(_("⚙️ Processing Intervals:"))
            if analysis_interval:
                lines.append(
                    _("  • Analysis: every {count} frames").format(count=analysis_interval)
                )
            if display_interval:
                lines.append(_("  • Display: every {count} frames").format(count=display_interval))

        # Model Selection
        weight_assignments = self.wizard_data.get("weight_assignments")
        detector_params = self.wizard_data.get("detector_parameters")
        if weight_assignments or detector_params:
            lines.append("")
            lines.append(_("🎯 Detection Configuration:"))
            if weight_assignments:
                aquarium_weight = weight_assignments.get("aquarium")
                animal_weight = weight_assignments.get("animal")
                if aquarium_weight:
                    lines.append(_("  • Aquarium weight: {weight}").format(weight=aquarium_weight))
                if animal_weight:
                    lines.append(_("  • Animal weight: {weight}").format(weight=animal_weight))
            if detector_params:
                conf = detector_params.get("confidence_threshold")
                nms = detector_params.get("nms_threshold")
                track = detector_params.get("track_threshold")
                match = detector_params.get("match_threshold")
                if conf is not None:
                    lines.append(
                        f"  • Thresholds: conf={conf:.2f}, NMS={nms:.2f}, "
                        f"track={track:.2f}, match={match:.2f}"
                    )

    def _append_detected_design(self, lines: list[str]) -> None:
        detected_design = self.wizard_data.get("detected_design")
        if not detected_design:
            return

        lines.append("")
        lines.append(_("🔍 Detected Design:"))
        groups = detected_design.get("groups", [])
        days = detected_design.get("days", [])
        confidence = detected_design.get("confidence", 0)

        if groups:
            preview = ", ".join(groups[:3])
            suffix = "..." if len(groups) > 3 else ""
            lines.append(
                _("  • Groups: {count} ({preview}{suffix})").format(
                    count=len(groups), preview=preview, suffix=suffix
                )
            )

        if days:
            lines.append(_("  • Days: {count}").format(count=len(days)))

        lines.append(_("  • Confidence: {value}").format(value=f"{confidence:.0%}"))

    def _append_custom_regex_info(self, lines: list[str]) -> None:
        patterns = self.wizard_data.get("custom_regex_patterns") or {}
        if not any(patterns.values()):
            return

        label_map = {
            "group_pattern": _("Groups"),
            "day_pattern": _("Days"),
            "subject_pattern": _("Subjects"),
        }

        lines.append("")
        lines.append(_("🧩 Custom Regex:"))
        for key, label in label_map.items():
            value = patterns.get(key)
            if value:
                lines.append(f"  • {label}: {value}")
            else:
                lines.append(f"  • {label}: —")

    def _append_detection_settings(self, lines: list[str]) -> None:
        model_selection = self.wizard_data.get("model_selection") or {}
        weight_assignments = self.wizard_data.get("weight_assignments") or {}
        detector_params = self.wizard_data.get("detector_parameters") or {}
        use_openvino = self.wizard_data.get("use_openvino")

        if not (
            model_selection or weight_assignments or detector_params or use_openvino is not None
        ):
            return

        method_labels = {
            "seg": _("Segmentation (seg)"),
            "det": _("Detection (det)"),
        }

        lines.append("")
        lines.append(_("🎯 Detection Settings:"))

        aquarium_method = model_selection.get("aquarium_method")
        animal_method = model_selection.get("animal_method")
        if aquarium_method or animal_method:
            if aquarium_method:
                aquarium_label = method_labels.get(aquarium_method, aquarium_method)
                lines.append(_("  • Aquarium method: {method}").format(method=aquarium_label))
            if animal_method:
                animal_label = method_labels.get(animal_method, animal_method)
                lines.append(_("  • Animal method: {method}").format(method=animal_label))

        if weight_assignments:
            aquarium_weight = weight_assignments.get("aquarium")
            animal_weight = weight_assignments.get("animal")
            if aquarium_weight:
                lines.append(_("  • Aquarium weight: {weight}").format(weight=aquarium_weight))
            if animal_weight:
                lines.append(_("  • Animal weight: {weight}").format(weight=animal_weight))

        if use_openvino is not None:
            status = _("Enabled") if use_openvino else _("Disabled")
            lines.append(_("  • OpenVINO: {status}").format(status=status))

        if detector_params:
            conf = detector_params.get("confidence_threshold")
            nms = detector_params.get("nms_threshold")
            track = detector_params.get("track_threshold")
            match = detector_params.get("match_threshold")
            if all(value is not None for value in (conf, nms, track, match)):
                lines.append(
                    f"  • Thresholds: conf={conf:.2f}, NMS={nms:.2f}, "
                    f"track={track:.2f}, match={match:.2f}"
                )
            else:
                threshold_bits = []
                if conf is not None:
                    threshold_bits.append(f"conf={conf:.2f}")
                if nms is not None:
                    threshold_bits.append(f"NMS={nms:.2f}")
                if track is not None:
                    threshold_bits.append(f"track={track:.2f}")
                if match is not None:
                    threshold_bits.append(f"match={match:.2f}")
                if threshold_bits:
                    lines.append(f"  • Thresholds: {', '.join(threshold_bits)}")

    def _append_folder_preview(self, lines: list[str]) -> None:
        video_count = self.wizard_data.get("video_count", 0)
        if video_count > 0:
            lines.append(_("  • Total videos: {count}").format(count=video_count))

        folder_preview = self.wizard_data.get("folder_preview") or []
        if folder_preview:
            lines.append("")
            lines.append(_("🌳 Folder Structure (preview):"))
            for entry in folder_preview[:2]:
                lines.extend(self._render_folder_preview(entry))

            remaining = len(folder_preview) - 2
            if remaining > 0:
                lines.append(
                    _("  • (+ 1 additional selection)")
                    if remaining == 1
                    else _("  • (+ {count} additional selections)").format(count=remaining)
                )

    def _append_calibration(self, lines: list[str]) -> None:
        lines.append("")
        lines.append(_("📏 Physical Calibration:"))
        num_aquariums = self.wizard_data.get("num_aquariums", 1)
        animals_per_aquarium = self.wizard_data.get("animals_per_aquarium", 1)
        width = self.wizard_data.get("aquarium_width_cm", 10.0)
        height = self.wizard_data.get("aquarium_height_cm", 10.0)

        lines.append(_("  • Aquariums: {count}").format(count=num_aquariums))
        lines.append(_("  • Animals per aquarium: {count}").format(count=animals_per_aquarium))
        lines.append(_("  • Dimensions: {width} x {height} cm").format(width=width, height=height))

    def _append_processing_plan(self, lines: list[str]) -> None:
        lines.append("")
        lines.append(_("⚙️ Processing Plan:"))
        import_config = self.wizard_data.get("import_config", [])

        if not import_config:
            return

        action_counts: dict[str, int] = {}
        for config in import_config:
            action = config.get("action", ImportAction.FULL.value)
            action_counts[action] = action_counts.get(action, 0) + 1

        action_names = {
            ImportAction.SKIP.value: _("Skip (complete data)"),
            ImportAction.IMPORT_ZONES.value: _("Import Zones + track"),
            ImportAction.PARTIAL.value: _("Partial (arena only)"),
            ImportAction.FULL.value: _("Full (process from scratch)"),
        }

        for action, count in sorted(action_counts.items()):
            name = action_names.get(action, action)
            lines.append(
                _("  • 1 video: {name}").format(name=name)
                if count == 1
                else _("  • {count} videos: {name}").format(count=count, name=name)
            )

        # Estimate processing time (rough estimate: 5 min per video to process)
        videos_to_process = sum(
            1 for c in import_config if c.get("action") not in [ImportAction.SKIP.value]
        )

        if videos_to_process > 0:
            estimated_minutes = videos_to_process * 5
            lines.append("")
            lines.append(
                _("⏱️ Estimated time: ~{minutes} minutes").format(minutes=estimated_minutes)
            )
            lines.append(
                _("  (1 video to process)")
                if videos_to_process == 1
                else _("  ({count} videos to process)").format(count=videos_to_process)
            )

    def _append_parquet_summary(self, lines: list[str]) -> None:
        # Show parquet summary whenever data exists (scope optional for legacy flows)
        parquet_summary = self.wizard_data.get("parquet_summary", {})
        if not parquet_summary:
            return

        parquet_import_scope = self.wizard_data.get("parquet_import_scope")

        lines.append("")
        lines.append(_("📦 Existing Parquets:"))
        if parquet_import_scope:
            lines.append(_("  • Scope: {scope}").format(scope=parquet_import_scope))
        arena_total = parquet_summary.get("total_arena", 0)
        rois_total = parquet_summary.get("total_rois", 0)
        trajectory_total = parquet_summary.get("total_trajectory", 0)
        complete_total = parquet_summary.get("total_complete", 0)
        lines.append(_("  • Arena: {count}").format(count=arena_total))
        lines.append(_("  • ROIs: {count}").format(count=rois_total))
        lines.append(_("  • Trajectory: {count}").format(count=trajectory_total))
        lines.append(_("  • Complete: {count}").format(count=complete_total))

    def _append_import_configuration(self, lines: list[str]) -> None:
        import_config = self.wizard_data.get("import_config", [])
        if not import_config:
            return

        importing_arena = any(cfg.get("import_arena", False) for cfg in import_config)
        importing_rois = any(cfg.get("import_rois", False) for cfg in import_config)
        importing_trajectory = any(cfg.get("import_trajectory", False) for cfg in import_config)

        if importing_arena or importing_rois or importing_trajectory:
            lines.append("")
            lines.append(_("📥 Import Configuration:"))
            if importing_arena:
                arena_count = sum(1 for c in import_config if c.get("import_arena"))
                lines.append(
                    _("  ✅ Arena: 1 video")
                    if arena_count == 1
                    else _("  ✅ Arena: {count} videos").format(count=arena_count)
                )
            if importing_rois:
                rois_count = sum(1 for c in import_config if c.get("import_rois"))
                lines.append(
                    _("  ✅ ROIs: 1 video")
                    if rois_count == 1
                    else _("  ✅ ROIs: {count} videos").format(count=rois_count)
                )
            if importing_trajectory:
                traj_count = sum(1 for c in import_config if c.get("import_trajectory"))
                lines.append(
                    _("  ✅ Trajectory: 1 video")
                    if traj_count == 1
                    else _("  ✅ Trajectory: {count} videos").format(count=traj_count)
                )

    def _append_roi_strategy(self, lines: list[str]) -> None:
        import_config = self.wizard_data.get("import_config", [])
        if import_config:
            importing_rois = any(cfg.get("import_rois", False) for cfg in import_config)
        else:
            importing_rois = False

        if not importing_rois:
            return

        roi_strategy = self.wizard_data.get("roi_merge_strategy", "replace")
        strategy_names = {
            "replace": _("Replace existing ROIs"),
            "merge": _("Merge (keep both)"),
            "manual": _("Manual conflict resolution"),
        }
        lines.append("")
        lines.append(_("🔀 ROI Strategy:"))
        lines.append(f"  • {strategy_names.get(roi_strategy, roi_strategy)}")

    def _render_folder_preview(self, entry: dict) -> list[str]:
        """Convert folder preview structure into formatted summary lines."""
        label = entry.get("label") or entry.get("path") or _("(selection)")
        counts = entry.get("counts", {})
        folders = counts.get("folders", 0)
        files = counts.get("files", 0)

        summary_bits: list[str] = []
        if folders:
            summary_bits.append(
                _("1 folder") if folders == 1 else _("{count} folders").format(count=folders)
            )
        if files:
            summary_bits.append(
                _("1 file") if files == 1 else _("{count} files").format(count=files)
            )

        summary_text = ", ".join(summary_bits) if summary_bits else _("empty")
        lines = [f"  • {label}: {summary_text}"]

        def walk(nodes: list[dict], depth: int) -> None:
            if depth >= 2:
                return

            max_children = 2 if depth == 0 else 1
            child_count = len(nodes)
            for index, node in enumerate(nodes[:max_children]):
                prefix = "    " * (depth + 1)
                node_label = node.get("label") or node.get("path") or "(item)"
                lines.append(f"{prefix}- {node_label}")
                walk(node.get("children", []), depth + 1)

                if index == max_children - 1 and child_count > max_children:
                    lines.append(f"{prefix}…")

        walk(entry.get("nodes", []), 0)

        if entry.get("truncated"):
            lines.append(_("    … Preview truncated (full details in step 2)"))

        return lines

    def _save_as_template(self):
        """Save current wizard configuration as a template."""
        # Ask for template name
        template_name = simpledialog.askstring(
            _("Save Template"),
            _("Enter a name for the template:"),
            parent=self,
        )

        if not template_name:
            return  # User cancelled

        suggested_filename = (
            self.template_manager._sanitize_name(template_name) or "template"
        ) + ".json"

        file_path = filedialog.asksaveasfilename(
            title=_("Save Wizard Template"),
            defaultextension=".json",
            filetypes=[(_("Wizard Templates"), "*.json"), ("JSON", "*.json")],
            initialdir=str(self.template_manager.templates_dir),
            initialfile=suggested_filename,
        )

        if not file_path:
            return

        # Save template
        success = self.template_manager.save_template(
            template_name,
            self.wizard_data,
            destination_path=file_path,
        )

        if success:
            template_message = _(
                "Template '{name}' saved successfully!\n\n"
                "File: {path}\n\n"
                "You will be able to load this template later to create "
                "similar projects quickly."
            ).format(name=template_name, path=file_path)
            messagebox.showinfo(
                _("Template Saved"),
                template_message,
                parent=self,
            )
            log.info("wizard.template_saved", name=template_name)
        else:
            messagebox.showerror(
                _("Error Saving"),
                _(
                    "Could not save the template '{name}'.\n\nCheck the logs for more details."
                ).format(name=template_name),
                parent=self,
            )

    def validate(self) -> tuple[bool, str]:
        """
        Validate confirmation step.

        Returns:
            tuple[bool, str]: (True, "") if all validations pass
        """
        # Validate project name
        project_name = self.project_name_var.get().strip()

        if not project_name:
            return (False, _("Please enter a name for the project."))

        # Check valid characters (alphanumeric, underscore, hyphen, space)
        if not re.match(r"^[A-Za-z0-9_\- ]+$", project_name):
            message = _(
                "The project name contains invalid characters. "
                "Use only letters, digits, spaces, '_' and '-'."
            )
            return (False, message)

        # Validate location
        location = self.project_location_var.get().strip()

        if not location:
            return (False, _("Please select a location for the project."))

        if not os.path.exists(location):
            return (False, _("Location does not exist: {location}").format(location=location))

        if not os.access(location, os.W_OK):
            return (
                False,
                _("No write permission at the location: {location}").format(location=location),
            )

        # Check if project directory already exists
        project_path = Path(location) / project_name
        try:
            project_exists = project_path.exists()
        except OSError:
            return (False, _("The project name is too long for the file system."))

        if project_exists:
            try:
                if project_path.is_file():
                    return (
                        False,
                        _("A file with that name already exists at: {location}").format(
                            location=location
                        ),
                    )
            except OSError:
                return (False, _("The project name is too long for the file system."))

            # Allow reusing an empty directory so long as it has no content
            try:
                has_contents = any(project_path.iterdir())
            except OSError:
                has_contents = True

            if has_contents:
                return (
                    False,
                    _("A project with that name already exists at: {location}").format(
                        location=location
                    ),
                )

        # Validate sources: prerecorded projects require selected videos;
        # live projects require camera config
        project_type = self.wizard_data.get("project_type", ProjectType.EXPERIMENTAL.value)

        if project_type != ProjectType.LIVE.value:
            video_count = self.wizard_data.get("video_count", 0)
            if video_count == 0:
                return (False, _("No video selected. Go back and select videos."))
        else:
            if "camera_index" not in self.wizard_data:
                return (
                    False,
                    _("Configure the camera in the previous step before creating the project."),
                )

        return (True, "")

    def get_data(self) -> dict:
        """
        Extract confirmation data.

        Returns:
            dict: Final project configuration with keys:
                - project_name (str)
                - project_path (str): Full path including project name
        """
        project_name = self.project_name_var.get().strip()
        location = self.project_location_var.get().strip()
        project_path = str(Path(location) / project_name)

        base_data: dict = {}
        if isinstance(self.wizard_data, dict):
            base_data = copy.deepcopy(self.wizard_data)

        base_data.update(
            {
                "project_name": project_name,
                "project_path": project_path,
                "project_location": location,
            }
        )

        return base_data

    def set_data(self, data: dict):
        """
        Restore UI from data (for back navigation).

        Args:
            data: Previously collected confirmation data
        """
        if "project_name" in data:
            self.project_name_var.set(data["project_name"])

        if "project_path" in data:
            # Extract location from full path
            project_path = Path(data["project_path"])
            if project_path.parent.exists():
                self.project_location_var.set(str(project_path.parent))

        # Regenerate summary
        self._generate_summary()
        self._update_template_banner()

    def _update_template_banner(self):
        metadata = self.wizard_data.get("template_metadata")
        banner_text = format_template_banner(metadata)

        if banner_text:
            self.template_info_var.set(banner_text)
            if self.template_info_label and not self.template_info_label.winfo_ismapped():
                self.template_info_label.pack(pady=(0, 15))
        else:
            self.template_info_var.set("")
            if self.template_info_label and self.template_info_label.winfo_ismapped():
                self.template_info_label.pack_forget()
