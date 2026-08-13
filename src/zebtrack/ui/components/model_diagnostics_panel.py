"""Reusable diagnostics panel for global and project model workflows."""

from __future__ import annotations

import os
from tkinter import BooleanVar, StringVar, filedialog, messagebox, ttk
from typing import Any

import structlog
from pydantic import ValidationError

from zebtrack.i18n import _
from zebtrack.ui import payloads
from zebtrack.ui.event_bus_v2 import Event, UIEvents
from zebtrack.ui.payloads import ModelRunDiagnosticPayload, ModelSetWeightPayload
from zebtrack.ui.sentinels import both_models_label
from zebtrack.ui.wizard.tooltip import create_help_label

log = structlog.get_logger()

# The two engine names are proper nouns and are never translated; only the
# "test both" entry is, through the shared sentinel the coordinator also reads.
YOLO_ENGINE = "YOLO (PyTorch)"
OPENVINO_ENGINE = "OpenVINO"


class ModelDiagnosticsPanel(ttk.Frame):
    """Focused diagnostics controls reusable across dialogs and tabs."""

    SLOT_SEPARATOR = ":"

    def __init__(
        self,
        parent,
        controller,
        *,
        scope: str = "global",
        parent_dialog: Any | None = None,
    ) -> None:
        super().__init__(parent, padding=10)
        self.controller = controller
        self.project_manager = controller.project_manager
        self.scope = scope
        self.parent_dialog = parent_dialog

        self.active_weight_var = StringVar(master=self)
        self.frames_to_analyze_var = StringVar(master=self, value="10")
        self.confidence_threshold_var = StringVar(master=self, value="0.25")
        self.nms_threshold_var = StringVar(master=self, value="0.50")
        self.use_bytetrack_var = BooleanVar(master=self, value=True)
        self.track_threshold_var = StringVar(master=self, value="0.25")
        self.match_threshold_var = StringVar(master=self, value="0.95")
        self.track_buffer_var = StringVar(master=self, value="90")
        self.max_center_dist_var = StringVar(master=self, value="400.0")
        self.iou_threshold_var = StringVar(master=self, value="0.05")
        self.video_path_label_var = StringVar(master=self, value=_("No video selected."))
        self.model_test_var = StringVar(master=self, value=YOLO_ENGINE)
        self.project_weight_summary_var = StringVar(master=self)
        self.project_weight_options: dict[str, str] = {}

        self.diagnostic_video_path = ""
        self.weights_dropdown: ttk.Combobox | None = None
        self.model_test_dropdown: ttk.Combobox | None = None
        self.bytetrack_hint_var = StringVar(master=self)
        self.bytetrack_hint_label: ttk.Label | None = None
        self.track_entry: ttk.Entry | None = None
        self.match_entry: ttk.Entry | None = None
        self.buffer_entry: ttk.Entry | None = None
        self.dist_entry: ttk.Entry | None = None
        self.iou_entry: ttk.Entry | None = None

        self._prefill_detector_parameters()
        self._build()

    def refresh_weight_options(self) -> None:
        """Refresh the global weight dropdown after catalog changes elsewhere."""
        if self.scope == "global":
            self._populate_weights_dropdown()
            return
        self._refresh_project_weight_summary()
        self._populate_project_weights_dropdown()

    def _build(self) -> None:
        self.columnconfigure(0, weight=1)

        title = _("Global Diagnostics") if self.scope == "global" else _("Project Diagnostics")
        ttk.Label(self, text=title, font=("Segoe UI", 11, "bold")).pack(anchor="w")

        if self.scope == "global":
            ttk.Label(
                self,
                text=_(
                    "Use this panel to validate weights, tune detector parameters "
                    "and run quick video tests outside the context of a project."
                ),
                justify="left",
                wraplength=760,
                foreground="#555555",
            ).pack(anchor="w", pady=(2, 10))
            self._build_weight_selector()
        else:
            self._refresh_project_weight_summary()
            ttk.Label(
                self,
                text=_(
                    "Changes made here affect only this project's detector parameters. "
                    "Choose below which effective project weight you want to diagnose."
                ),
                justify="left",
                wraplength=760,
                foreground="#555555",
            ).pack(anchor="w", pady=(2, 2))
            self._build_project_weight_selector()
            ttk.Label(
                self,
                textvariable=self.project_weight_summary_var,
                justify="left",
                wraplength=760,
            ).pack(anchor="w", pady=(0, 10))

        self._build_video_selector()
        self._create_detector_params_section(include_model_test=True, include_frame_count=True)
        self._build_actions()

        ttk.Button(
            self,
            text=_("Test Model on Video..."),
            command=self._run_diagnostic_test,
        ).pack(fill="x", pady=(6, 0))

    def _build_weight_selector(self) -> None:
        row = ttk.Frame(self)
        row.pack(fill="x", pady=(0, 6))
        row.columnconfigure(1, weight=1)

        ttk.Label(row, text=_("Weight for diagnostics:")).grid(row=0, column=0, sticky="w")
        self.weights_dropdown = ttk.Combobox(
            row,
            textvariable=self.active_weight_var,
            state="readonly",
        )
        self.weights_dropdown.grid(row=0, column=1, sticky="ew", padx=(6, 0))
        self.weights_dropdown.bind("<<ComboboxSelected>>", self._on_weight_selected_local)

        ttk.Label(
            self,
            text=_(
                "The weight chosen here is applied temporarily as the active weight for "
                "the test. The permanent global configuration is still controlled by the "
                "Global Model Configuration window."
            ),
            font=("Segoe UI", 8),
            foreground="#555555",
            wraplength=760,
            justify="left",
        ).pack(anchor="w", pady=(0, 10))

        self._populate_weights_dropdown()

    def _build_project_weight_selector(self) -> None:
        row = ttk.Frame(self)
        row.pack(fill="x", pady=(0, 6))
        row.columnconfigure(1, weight=1)

        ttk.Label(row, text=_("Project weight for diagnostics:")).grid(
            row=0,
            column=0,
            sticky="w",
        )
        self.weights_dropdown = ttk.Combobox(
            row,
            textvariable=self.active_weight_var,
            state="readonly",
        )
        self.weights_dropdown.grid(row=0, column=1, sticky="ew", padx=(6, 0))
        self._populate_project_weights_dropdown()

    def _build_video_selector(self) -> None:
        row = ttk.Frame(self)
        row.pack(fill="x", pady=(0, 6))
        row.columnconfigure(1, weight=1)

        ttk.Button(
            row,
            text=_("Select Video..."),
            command=self._select_diagnostic_video,
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            row,
            textvariable=self.video_path_label_var,
            wraplength=700,
            justify="left",
        ).grid(row=0, column=1, sticky="ew", padx=(8, 0))

    def _build_actions(self) -> None:
        actions_frame = ttk.Frame(self)
        actions_frame.pack(fill="x", pady=(6, 0))

        if self.scope == "project":
            for col in range(3):
                actions_frame.columnconfigure(col, weight=1, uniform="diag_project_actions")

            ttk.Button(
                actions_frame,
                text=_("Save to Project"),
                command=self._apply_detector_parameters,
            ).grid(row=0, column=0, sticky="ew")
            ttk.Button(
                actions_frame,
                text=_("Reload Saved Values"),
                command=self._reload_project_parameters,
            ).grid(row=0, column=1, sticky="ew", padx=8)
            ttk.Button(
                actions_frame,
                text=_("Restore Global Defaults"),
                command=self._restore_detector_defaults,
            ).grid(row=0, column=2, sticky="ew")
            return

        actions_frame.columnconfigure(0, weight=1, uniform="diag_global_actions")
        actions_frame.columnconfigure(1, weight=1, uniform="diag_global_actions")
        ttk.Button(
            actions_frame,
            text=_("Apply Parameters"),
            command=self._apply_detector_parameters,
        ).grid(row=0, column=0, sticky="ew")
        ttk.Button(
            actions_frame,
            text=_("Restore Defaults"),
            command=self._restore_detector_defaults,
        ).grid(row=0, column=1, sticky="ew", padx=(8, 0))

    def _create_detector_params_section(
        self,
        *,
        include_model_test: bool,
        include_frame_count: bool,
    ) -> None:
        params_frame = ttk.Frame(self, padding=5)
        params_frame.pack(fill="x", pady=5)

        params_frame.columnconfigure(0, weight=0)
        params_frame.columnconfigure(1, weight=0)
        params_frame.columnconfigure(2, weight=1)
        params_frame.columnconfigure(3, weight=0)
        params_frame.columnconfigure(4, weight=0)
        params_frame.columnconfigure(5, weight=1)

        row_idx = 0
        if include_frame_count:
            ttk.Label(params_frame, text=_("No. Frames (Test):")).grid(
                row=row_idx, column=0, sticky="w", padx=(5, 2), pady=2
            )
            create_help_label(
                params_frame,
                _(
                    "Number of video frames to process in the diagnostic test.\n"
                    "Use a low value (e.g. 100) for quick tests."
                ),
            ).grid(row=row_idx, column=1, padx=2)
            ttk.Entry(params_frame, textvariable=self.frames_to_analyze_var, width=8).grid(
                row=row_idx, column=2, sticky="ew", padx=5
            )
            row_idx += 1

        ttk.Label(params_frame, text=_("Confidence Threshold:")).grid(
            row=row_idx, column=0, sticky="w", padx=(5, 2), pady=2
        )
        create_help_label(
            params_frame,
            _(
                "Confidence Threshold\n\n"
                "Minimum probability (0.0 to 1.0) for a detection to count as valid.\n"
                "• Raise it (e.g. 0.50) if there are many 'false positives' (noise/ghosts).\n"
                "• Lower it (e.g. 0.15) if the fish is not detected in some frames.\n"
                "• Recommended default: 0.25"
            ),
        ).grid(row=row_idx, column=1, padx=2)
        ttk.Entry(params_frame, textvariable=self.confidence_threshold_var, width=8).grid(
            row=row_idx, column=2, sticky="ew", padx=5
        )

        ttk.Label(params_frame, text=_("NMS Threshold:")).grid(
            row=row_idx, column=3, sticky="w", padx=(15, 2), pady=2
        )
        create_help_label(
            params_frame,
            _(
                "NMS Threshold (Non-Maximum Suppression)\n\n"
                "Controls the removal of duplicate boxes for the same object.\n"
                "• Low values (e.g. 0.4) merge overlapping boxes aggressively.\n"
                "• High values (e.g. 0.7) allow more overlap.\n"
                "• Recommended default: 0.50"
            ),
        ).grid(row=row_idx, column=4, padx=2)
        ttk.Entry(params_frame, textvariable=self.nms_threshold_var, width=8).grid(
            row=row_idx, column=5, sticky="ew", padx=5
        )

        row_idx += 1

        ttk.Checkbutton(
            params_frame,
            text=_("Use ByteTrack (Advanced Tracking)"),
            variable=self.use_bytetrack_var,
            command=self._toggle_bytetrack_options,
        ).grid(row=row_idx, column=0, columnspan=6, sticky="w", padx=5, pady=(15, 5))
        row_idx += 1

        self.bytetrack_hint_label = ttk.Label(
            params_frame,
            textvariable=self.bytetrack_hint_var,
            font=("Segoe UI", 8, "italic"),
            foreground="#555555",
            wraplength=450,
            justify="left",
        )
        self.bytetrack_hint_label.grid(
            row=row_idx, column=0, columnspan=6, sticky="w", padx=10, pady=(0, 10)
        )
        row_idx += 1

        tracking_frame = ttk.Frame(params_frame)
        tracking_frame.grid(row=row_idx, column=0, columnspan=6, sticky="ew")
        tracking_frame.columnconfigure(0, weight=0)
        tracking_frame.columnconfigure(1, weight=0)
        tracking_frame.columnconfigure(2, weight=1)
        tracking_frame.columnconfigure(3, weight=0)
        tracking_frame.columnconfigure(4, weight=0)
        tracking_frame.columnconfigure(5, weight=1)

        t_row = 0
        ttk.Label(tracking_frame, text=_("Track Thresh:")).grid(
            row=t_row, column=0, sticky="w", padx=(5, 2)
        )
        create_help_label(
            tracking_frame,
            _(
                "Track Threshold (Tracking)\n\n"
                "Minimum confidence to START or KEEP a track.\n"
                "• Defines how 'sure' the detector must be to create a new ID.\n"
                "• Raise it to avoid junk/noise tracks.\n"
                "• Lower it to keep the ID of fish that are hard to detect.\n"
                "• Recommended default: 0.25"
            ),
        ).grid(row=t_row, column=1, padx=2)
        self.track_entry = ttk.Entry(tracking_frame, textvariable=self.track_threshold_var, width=8)
        self.track_entry.grid(row=t_row, column=2, sticky="ew", padx=5)

        ttk.Label(tracking_frame, text=_("Match Thresh:")).grid(
            row=t_row, column=3, sticky="w", padx=(15, 2)
        )
        create_help_label(
            tracking_frame,
            _(
                "Match Threshold\n\n"
                "Tolerance for associating a new detection with an existing track.\n"
                "• High values (e.g. 0.8+) are more permissive (good for fast movement).\n"
                "• Low values (<0.5) are restrictive "
                "(avoids identity swaps, but may lose the track).\n"
                "• Recommended default: 0.95"
            ),
        ).grid(row=t_row, column=4, padx=2)
        self.match_entry = ttk.Entry(tracking_frame, textvariable=self.match_threshold_var, width=8)
        self.match_entry.grid(row=t_row, column=5, sticky="ew", padx=5)

        t_row += 1
        ttk.Label(tracking_frame, text=_("Track Buffer:")).grid(
            row=t_row, column=0, sticky="w", padx=(5, 2), pady=5
        )
        create_help_label(
            tracking_frame,
            _(
                "Track Buffer (Memory)\n\n"
                "How many frames the system 'remembers' a fish after it disappears "
                "(occlusion/miss).\n"
                "• Raise it (e.g. 120) if the fish vanishes for a long time.\n"
                "• Lower it to drop lost tracks quickly.\n"
                "• Default: 90 frames (~3s at 30fps)"
            ),
        ).grid(row=t_row, column=1, padx=2)
        self.buffer_entry = ttk.Entry(tracking_frame, textvariable=self.track_buffer_var, width=8)
        self.buffer_entry.grid(row=t_row, column=2, sticky="ew", padx=5)

        ttk.Label(tracking_frame, text=_("Max Dist. (px):")).grid(
            row=t_row, column=3, sticky="w", padx=(15, 2)
        )
        create_help_label(
            tracking_frame,
            _(
                "Maximum Distance (pixels)\n\n"
                "How far the centre of the fish may move between processed frames.\n"
                "• Prevents impossible associations (teleporting).\n"
                "• Raise it if the fish is fast or the frame rate is low.\n"
                "• Lower it if IDs are swapped between distant fish.\n"
                "• Default: 400.0 px"
            ),
        ).grid(row=t_row, column=4, padx=2)
        self.dist_entry = ttk.Entry(tracking_frame, textvariable=self.max_center_dist_var, width=8)
        self.dist_entry.grid(row=t_row, column=5, sticky="ew", padx=5)

        t_row += 1
        ttk.Label(tracking_frame, text=_("IoU Thresh:")).grid(
            row=t_row, column=0, sticky="w", padx=(5, 2)
        )
        create_help_label(
            tracking_frame,
            _(
                "IoU Threshold (Tracking)\n\n"
                "Minimum overlap (Intersection over Union) to associate boxes.\n"
                "• Default: 0.05 (undemanding).\n"
                "• Raise it (e.g. 0.3) to require the fish to stay in almost the same "
                "position.\n"
                "• Lower it to allow abrupt movements that change the box area."
            ),
        ).grid(row=t_row, column=1, padx=2)
        self.iou_entry = ttk.Entry(tracking_frame, textvariable=self.iou_threshold_var, width=8)
        self.iou_entry.grid(row=t_row, column=2, sticky="ew", padx=5)

        row_idx += 1
        if include_model_test:
            ttk.Label(params_frame, text=_("Model(s) to Test:")).grid(
                row=row_idx, column=0, sticky="w", padx=5, pady=(15, 2)
            )
            self.model_test_dropdown = ttk.Combobox(
                params_frame,
                textvariable=self.model_test_var,
                state="readonly",
                values=[YOLO_ENGINE, OPENVINO_ENGINE, both_models_label()],
                width=15,
            )
            self.model_test_dropdown.grid(
                row=row_idx, column=1, columnspan=5, sticky="ew", padx=5, pady=(15, 2)
            )

        self._toggle_bytetrack_options()

    def _toggle_bytetrack_options(self) -> None:
        if not self.track_entry:
            return

        enabled = self.use_bytetrack_var.get()
        state = "normal" if enabled else "disabled"
        for widget in [
            self.track_entry,
            self.match_entry,
            self.buffer_entry,
            self.dist_entry,
            self.iou_entry,
        ]:
            if widget is None:
                continue
            widget.configure(state=state)

        if not enabled:
            self.bytetrack_hint_var.set(
                _(
                    "ℹ️ ByteTrack disabled. Using simple (Hybrid) tracking, which relies "
                    "only on 'Maximum Distance' and 'IoU Threshold' to keep the ID."
                )
            )
            for widget in [self.dist_entry, self.iou_entry]:
                if widget is not None:
                    widget.configure(state="normal")
            return

        self.bytetrack_hint_var.set(
            _("💡 ByteTrack active (Kalman filter). Recommended for greater stability.")
        )

    def _prefill_detector_parameters(self) -> None:
        resolved_params, _project_params = self._collect_prefill_detector_params()
        if resolved_params:
            self._set_parameter_fields(resolved_params)

    def _collect_prefill_detector_params(self) -> tuple[dict[str, Any], dict[str, Any]]:
        def _extract_params(source: dict | None) -> dict[str, Any]:
            mapping = {
                "confidence_threshold": "confidence_threshold",
                "conf_threshold": "confidence_threshold",
                "nms_threshold": "nms_threshold",
                "track_threshold": "track_threshold",
                "match_threshold": "match_threshold",
                "track_buffer": "track_buffer",
                "max_center_distance": "max_center_distance",
                "iou_threshold": "iou_threshold",
                "use_bytetrack": "use_bytetrack",
            }
            resolved: dict[str, Any] = {}
            if not source:
                return resolved
            for key, target in mapping.items():
                if key not in source:
                    continue
                try:
                    if target == "use_bytetrack":
                        resolved[target] = bool(source[key])
                    elif target == "track_buffer":
                        resolved[target] = int(source[key])
                    else:
                        resolved[target] = float(source[key])
                except (TypeError, ValueError):
                    log.warning(
                        "ui.model_diagnostics.prefill.invalid_param",
                        key=key,
                        value=source[key],
                    )
            return resolved

        project_data = getattr(self.project_manager, "project_data", {}) or {}
        overrides = project_data.get("model_overrides") or {}

        project_params = _extract_params(overrides.get("detector_parameters"))
        if not project_params:
            project_params = _extract_params(project_data.get("detector_config"))
        if not project_params:
            project_params = _extract_params(project_data.get("detector_state"))

        try:
            params = self.controller.hardware_vm.get_current_detector_parameters()
        except Exception:
            log.debug("model_diagnostics_panel.get_detector_params.fallback", exc_info=True)
            params = {}

        resolved_params = _extract_params(params)
        if self.scope == "project" and project_params:
            resolved_params.update(project_params)

        return resolved_params, project_params

    def _set_parameter_fields(self, values: dict[str, Any]) -> None:
        field_map = {
            "confidence_threshold": self.confidence_threshold_var,
            "nms_threshold": self.nms_threshold_var,
            "track_threshold": self.track_threshold_var,
            "match_threshold": self.match_threshold_var,
            "track_buffer": self.track_buffer_var,
            "max_center_distance": self.max_center_dist_var,
            "iou_threshold": self.iou_threshold_var,
        }
        for key, var in field_map.items():
            raw_value = values.get(key)
            if raw_value is None:
                continue
            try:
                if key == "track_buffer":
                    var.set(str(int(raw_value)))
                else:
                    var.set(
                        f"{float(raw_value):.2f}"
                        if isinstance(raw_value, float)
                        else str(raw_value)
                    )
            except (TypeError, ValueError):
                log.warning(
                    "ui.model_diagnostics.prefill.coerce_failed",
                    key=key,
                    value=raw_value,
                )

        if "use_bytetrack" in values:
            self.use_bytetrack_var.set(bool(values["use_bytetrack"]))
            self._toggle_bytetrack_options()

    def _reload_project_parameters(self) -> None:
        _resolved_params, project_params = self._collect_prefill_detector_params()
        if not project_params:
            messagebox.showinfo(
                _("No overrides"),
                _(
                    "This project has no saved overrides yet. "
                    "The current global values will be kept."
                ),
                parent=self,
            )
            return

        self._set_parameter_fields(project_params)

    def _apply_detector_parameters(self) -> None:
        try:
            conf = float(self.confidence_threshold_var.get())
            nms = float(self.nms_threshold_var.get())
            use_bytetrack = self.use_bytetrack_var.get()
            track_thresh = float(self.track_threshold_var.get())
            match_thresh = float(self.match_threshold_var.get())
            track_buffer = int(self.track_buffer_var.get())
            max_dist = float(self.max_center_dist_var.get())
            iou_thresh = float(self.iou_threshold_var.get())
        except (TypeError, ValueError):
            messagebox.showerror(
                _("Error"),
                _("Enter valid numeric values for the detector parameters."),
                parent=self,
            )
            return

        for label, value in (
            (_("confidence threshold"), conf),
            (_("NMS threshold"), nms),
            (_("track threshold"), track_thresh),
            (_("match threshold"), match_thresh),
            (_("IoU threshold"), iou_thresh),
        ):
            if not 0.0 < value < 1.0:
                messagebox.showerror(
                    _("Error"),
                    _("The {label} must be between 0 and 1.").format(label=label),
                    parent=self,
                )
                return

        if track_buffer < 1:
            messagebox.showerror(
                _("Error"),
                _("Track Buffer must be at least 1 frame."),
                parent=self,
            )
            return
        if max_dist <= 0:
            messagebox.showerror(
                _("Error"),
                _("Maximum Distance must be greater than 0."),
                parent=self,
            )
            return

        try:
            updated = self.controller.hardware_vm.update_detector_parameters(
                {
                    "confidence_threshold": conf,
                    "nms_threshold": nms,
                    "use_bytetrack": use_bytetrack,
                    "track_threshold": track_thresh,
                    "match_threshold": match_thresh,
                    "track_buffer": track_buffer,
                    "max_center_distance": max_dist,
                    "iou_threshold": iou_thresh,
                    "scope": self.scope,
                }
            )
        except ValidationError as exc:
            messagebox.showerror(_("Error"), str(exc), parent=self)
            return

        if updated:
            success_message = (
                _("The detector settings were saved for this project.")
                if self.scope == "project"
                else _("The detector settings were applied successfully.")
            )
            messagebox.showinfo(_("Parameters Updated"), success_message, parent=self)
        else:
            messagebox.showwarning(
                _("No changes"),
                _("The parameters given were already in use."),
                parent=self,
            )

    def _restore_detector_defaults(self) -> None:
        try:
            restored = self.controller.hardware_vm.restore_detector_defaults(scope=self.scope)
        except Exception as exc:
            messagebox.showerror(_("Error"), str(exc), parent=self)
            return

        if restored:
            resolved_params, _project_params = self._collect_prefill_detector_params()
            self._set_parameter_fields(resolved_params)
            messagebox.showinfo(
                _("Detector Parameters"),
                _("Default parameters restored."),
                parent=self,
            )

    def _populate_weights_dropdown(self) -> None:
        if not self.weights_dropdown:
            return
        weights_list = self.controller.hardware_vm.get_all_weight_names()
        self.weights_dropdown["values"] = weights_list
        if not weights_list:
            self.active_weight_var.set(_("No weights found."))
            self.weights_dropdown.config(state="disabled")
            return

        self.weights_dropdown.config(state="readonly")
        current_weight = self.controller.hardware_vm.active_weight_name
        if current_weight in weights_list:
            self.active_weight_var.set(current_weight)
        else:
            self.active_weight_var.set(weights_list[0])

    @classmethod
    def _slot_key(cls, method: str, target: str) -> str:
        return f"{method}{cls.SLOT_SEPARATOR}{target}"

    def _get_project_slot_entries(self) -> list[dict[str, str | None]]:
        summary_getter = getattr(self.controller.hardware_vm, "get_default_weights_summary", None)
        if not callable(summary_getter):
            return []

        overrides = getattr(self.project_manager, "project_data", {}) or {}
        model_overrides = overrides.get("model_overrides") or {}
        slot_weights = model_overrides.get("slot_weights") or {}
        normalized_slot_weights: dict[str, str] = {}
        if isinstance(slot_weights, dict):
            for key, value in slot_weights.items():
                if isinstance(key, str) and isinstance(value, str) and value.strip():
                    normalized_slot_weights[key] = value.strip()

        legacy_weight = model_overrides.get("active_weight")
        entries: list[dict[str, str | None]] = []
        for label, method, target, global_weight in summary_getter(scope="project"):
            slot_key = self._slot_key(method, target)
            if target == "zebrafish" and isinstance(legacy_weight, str) and legacy_weight.strip():
                normalized_slot_weights.setdefault(slot_key, legacy_weight.strip())
            project_override = normalized_slot_weights.get(slot_key)
            entries.append(
                {
                    "key": slot_key,
                    "label": label,
                    "effective_weight": project_override or global_weight,
                    "project_override": project_override,
                }
            )
        return entries

    def _populate_project_weights_dropdown(self) -> None:
        if not self.weights_dropdown:
            return

        self.project_weight_options = {}
        for entry in self._get_project_slot_entries():
            effective_weight = entry.get("effective_weight")
            if not effective_weight:
                continue
            display = f"{entry['label']}: {effective_weight}"
            self.project_weight_options[display] = effective_weight

        values = list(self.project_weight_options.keys())
        self.weights_dropdown["values"] = values
        if not values:
            self.weights_dropdown.config(state="disabled")
            self.active_weight_var.set(_("No effective weight available."))
            return

        self.weights_dropdown.config(state="readonly")
        current_selection = self.active_weight_var.get()
        if current_selection in self.project_weight_options:
            return
        self.active_weight_var.set(values[0])

    def _refresh_project_weight_summary(self) -> None:
        entries = self._get_project_slot_entries()
        try:
            _resolved_weight, resolved_openvino = (
                self.controller.project_vm.resolve_project_model_settings({})
            )
        except Exception:
            resolved_openvino = False

        lines = [_("Effective weights for this project:")]
        for entry in entries:
            label = entry.get("label") or _("Slot")
            effective_weight = entry.get("effective_weight") or _("None")
            if entry.get("project_override"):
                lines.append(
                    _("{label}: {weight} (project override)").format(
                        label=label, weight=effective_weight
                    )
                )
            else:
                lines.append(
                    _("{label}: {weight} (global default)").format(
                        label=label, weight=effective_weight
                    )
                )
        status = _("Enabled") if resolved_openvino else _("Disabled")
        lines.append(_("OpenVINO: {status}").format(status=status))
        self.project_weight_summary_var.set("\n".join(lines))

    def _on_weight_selected_local(self, _event=None) -> None:
        selected_weight = self.active_weight_var.get()
        self._publish_event(
            UIEvents.MODEL_SET_WEIGHT,
            ModelSetWeightPayload(name=selected_weight, dialog=None),
        )

    def _select_diagnostic_video(self) -> None:
        path = filedialog.askopenfilename(
            title=_("Select the Video for Diagnostics"),
            filetypes=[(_("Video files"), "*.mp4 *.avi *.mov")],
            parent=self,
        )
        if not path:
            return

        self.diagnostic_video_path = path
        self.video_path_label_var.set(os.path.basename(path))

    def _run_diagnostic_test(self) -> None:
        if not self.diagnostic_video_path:
            messagebox.showerror(
                _("Error"),
                _("Please select a video file."),
                parent=self,
            )
            return

        try:
            frames = int(self.frames_to_analyze_var.get())
            if frames <= 0:
                messagebox.showerror(
                    _("Error"),
                    _("The number of frames must be a positive integer."),
                    parent=self,
                )
                return
        except ValueError:
            messagebox.showerror(
                _("Error"),
                _("The number of frames must be a whole number."),
                parent=self,
            )
            return

        try:
            conf = float(self.confidence_threshold_var.get())
            if not 0.0 <= conf <= 1.0:
                messagebox.showerror(
                    _("Error"),
                    _("The confidence threshold must be a number between 0.0 and 1.0."),
                    parent=self,
                )
                return
        except ValueError:
            messagebox.showerror(
                _("Error"),
                _("The confidence threshold must be a valid number."),
                parent=self,
            )
            return

        config = {
            "video_path": self.diagnostic_video_path,
            "frames_to_analyze": frames,
            "confidence_threshold": conf,
            "model_to_test": self.model_test_var.get(),
        }
        if self.scope == "project":
            selected_weight = self.project_weight_options.get(self.active_weight_var.get())
            if not selected_weight:
                messagebox.showerror(
                    _("Error"),
                    _("Select one of the project's effective weights for diagnostics."),
                    parent=self,
                )
                return
            config["active_weight_name"] = selected_weight
        if self.parent_dialog is not None:
            config["parent_dialog"] = self.parent_dialog

        self._publish_event(
            UIEvents.MODEL_RUN_DIAGNOSTIC,
            ModelRunDiagnosticPayload(config=config),
        )

    def _publish_event(self, event_type: UIEvents, payload: payloads.EventPayload) -> None:
        bus = getattr(self.controller, "ui_event_bus", None)
        if bus is None:
            log.error("model_diagnostics_panel.no_event_bus", event=event_type.name)
            return
        bus.publish(Event(type=event_type, data=payload))
