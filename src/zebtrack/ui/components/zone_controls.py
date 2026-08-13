"""Zone controls widget component - zone drawing and management UI."""

import tkinter as tk
from tkinter import Menu, StringVar, ttk
from typing import Any, ClassVar

import structlog

from zebtrack.core.services.roi_rule_resolver import RoiRuleConfig
from zebtrack.i18n import _
from zebtrack.ui import payloads
from zebtrack.ui.components.base import BaseWidget
from zebtrack.ui.dialogs.project_video_import_dialog import VideoMetadataDialog
from zebtrack.ui.event_bus_v2 import EventBusV2, UIEvents

log = structlog.get_logger()


def _hierarchy_labels() -> dict[str, str]:
    """Node-type -> displayed word for the tree context menu.

    A function, not a class-level dict: the latter would translate at import
    time. These are display labels only -- the stored ``Grupo_*``/``Dia_*``/
    ``Sujeito_*`` directory tokens are built elsewhere and never translated.
    """
    return {"group": _("Group"), "day": _("Day"), "subject": _("Subject")}


class ZoneControlsWidget(BaseWidget):
    """
    Reusable zone control widget for drawing and managing zones/ROIs.

    Provides:
    - Drawing action buttons (auto-detect, manual polygon, ROI)
    - Zone list display (Treeview)
    - ROI template management
    - ROI inclusion rule configuration
    - Video selector for loading frames

    Events emitted:
    - zone.auto_detect_clicked: User clicked auto-detect button
    - zone.draw_main_polygon: User wants to draw main arena polygon
    - zone.draw_roi: User wants to draw an ROI
    - zone.template_apply: User wants to apply a template
    - zone.template_save: User wants to save current zones as template
    - zone.template_import: User wants to import a template file
    - zone.video_selected: User selected a video from the tree
    - zone.video_frame_load: User wants to load a frame from selected video
    - zone.list_item_selected: User selected a zone from the list
    - zone.list_item_double_click: User double-clicked a zone
    - zone.list_item_right_click: User right-clicked a zone
    - zone.roi_rule_changed: User changed the ROI inclusion rule
    - zone.roi_settings_apply: User clicked apply ROI settings
    """

    def __init__(
        self,
        parent: tk.Widget,
        event_bus: EventBusV2 | None = None,
        drawing_actions_parent: ttk.Frame | None = None,
        template_actions_parent: ttk.Frame | None = None,
        roi_rule_config: RoiRuleConfig | None = None,
        **kwargs: Any,
    ):
        """
        Initialize the zone controls widget.

        Args:
            parent: Parent Tkinter widget
            event_bus: Optional event bus for emitting events
            drawing_actions_parent: Optional parent frame for drawing actions (default: self)
            template_actions_parent: Optional parent frame for template actions (default: self)
            roi_rule_config: Regra de ROI EFETIVA (já resolvida por
                ``resolve_roi_rule``) com que semear o painel. ``None`` usa o
                default canônico — nunca um literal escrito aqui, que é como o
                painel passou a exibir 0.10 enquanto a análise usava 0.05.
            **kwargs: Additional arguments passed to BaseWidget
        """
        self.drawing_actions_parent = drawing_actions_parent
        self.template_actions_parent = template_actions_parent

        # State variables
        self.roi_choice_var = StringVar(value="none")
        self.analysis_interval_var = StringVar(value="10")
        self.display_interval_var = StringVar(value="10")
        self.stabilization_frames_var = StringVar(value="10")
        self.roi_template_var = StringVar(value="")
        self.video_search_var = StringVar()
        roi_config = roi_rule_config or RoiRuleConfig()
        self.roi_inclusion_rule_var = StringVar(value=roi_config.rule)
        self.roi_buffer_radius_var = StringVar(value=f"{roi_config.buffer_radius_value:g}")
        self.roi_overlap_ratio_var = StringVar(value=f"{roi_config.min_bbox_overlap_ratio:g}")

        # Multi-aquarium state variables
        self.aquarium_count_var = tk.IntVar(value=1)
        self.active_aquarium_var = tk.IntVar(value=0)  # 0 = Aquarium 1, 1 = Aquarium 2
        # False = parallel (1 pass), True = sequential (2 passes) - default True for better accuracy
        self.sequential_processing_var = tk.BooleanVar(value=True)
        # Apply processing mode to all videos (default True)
        self.parent = parent
        self.apply_to_all_var = tk.BooleanVar(value=True)

        # Pending-session banner (live recording handshake).
        self.pending_session_frame: ttk.Frame | None = None
        self.pending_session_label: ttk.Label | None = None
        self._pending_session_payload: payloads.LiveRecordingPendingPayload | None = None

        # Widget references
        self.draw_roi_button: ttk.Button | None = None
        self.toggle_view_btn: ttk.Button | None = None
        self.video_tree_toggle_btn: ttk.Button | None = None
        self.roi_template_combobox: ttk.Combobox | None = None
        self.video_selector_tree: ttk.Treeview | None = None
        self.zone_listbox: ttk.Treeview | None = None
        self.save_arena_btn: ttk.Button | None = None
        self.discard_arena_btn: ttk.Button | None = None
        self.interactive_buttons_frame: ttk.Frame | None = None
        self.controls_canvas_window: int | None = None
        self.roi_rule_combo: ttk.Combobox | None = None
        self.radius_frame: ttk.Frame | None = None
        self.overlap_frame: ttk.Frame | None = None
        self.rule_help_label: ttk.Label | None = None
        self.overlap_hint_label: ttk.Label | None = None
        self._video_tree_expanded = True

        # Multi-aquarium widget references
        self._context_menu_video_path: str | None = None
        self.aquarium_selector_frame: ttk.LabelFrame | None = None
        self.aquarium_radio_1: ttk.Radiobutton | None = None
        self.aquarium_radio_2: ttk.Radiobutton | None = None
        self.processing_mode_frame: ttk.Frame | None = None
        self.parallel_radio: ttk.Radiobutton | None = None
        self.sequential_radio: ttk.Radiobutton | None = None

        if isinstance(parent, ttk.Widget):
            super().__init__(parent, event_bus=event_bus, **kwargs)
        else:
            # Wrap strict typing for base widget if parent is not ttk
            super().__init__(parent, event_bus=event_bus, **kwargs)  # type: ignore[arg-type]

    def _build_ui(self) -> None:
        """Build the zone controls widget UI."""
        # Create a scrollable frame for all controls
        from tkinter import Canvas

        from zebtrack.ui.window_utils import create_scrollbar

        # Create a frame for fixed buttons at the bottom (not scrollable)
        self.fixed_button_frame = ttk.Frame(self)
        self.fixed_button_frame.pack(side="bottom", fill="x", padx=5, pady=5)

        # Container for scrollable content
        self.controls_canvas = Canvas(self, highlightthickness=0)
        scrollbar = create_scrollbar(self, orient="vertical", command=self.controls_canvas.yview)

        self.zone_controls_frame = ttk.Frame(self.controls_canvas)

        # Configure canvas scrolling
        self.controls_canvas.configure(yscrollcommand=scrollbar.set)
        self.controls_canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Create window in canvas for the scrollable frame
        self.controls_canvas_window = self.controls_canvas.create_window(
            (0, 0), window=self.zone_controls_frame, anchor="nw"
        )

        # Bind to configure event to update scrollregion
        self.zone_controls_frame.bind(
            "<Configure>",
            lambda e: self.controls_canvas.configure(scrollregion=self.controls_canvas.bbox("all")),
        )

        # Build individual sections
        # Note: Order matters for the side panel, but external parents are handled independently.

        # 1. Top of Viz Frame (if parent provided) OR Top of Left Panel
        self._build_pending_session_banner()
        self._build_drawing_actions()
        self._build_aquarium_selector()  # Multi-aquarium support
        self._build_interactive_buttons()

        # Subscribe to live-recording handshake events so the banner reflects
        # the current session state. ``BaseWidget.bind_callback`` guards against
        # a missing event_bus.
        self.bind_callback(UIEvents.LIVE_RECORDING_PENDING, self._on_live_recording_pending)  # type: ignore[arg-type]
        self.bind_callback(UIEvents.LIVE_SESSION_STARTED, self._on_live_recording_done)
        self.bind_callback(UIEvents.LIVE_SESSION_STOPPED, self._on_live_recording_done)
        self.bind_callback(UIEvents.LIVE_RECORDING_CANCELLED, self._on_live_recording_done)

        # 2. Left Panel Components (Always in zone_controls_frame)
        self._build_zone_list()
        self._build_roi_inclusion_panel()
        self._build_video_selector()

        # 3. Bottom of Viz Frame (if parent provided) OR Left Panel
        self._build_template_section()

        # Removed unwanted section: self._build_single_analysis_options()

    def _build_pending_session_banner(self) -> None:
        """Build the "pending session" banner shown above the drawing actions.

        Initially hidden. When ``LIVE_RECORDING_PENDING`` is published by
        ``LiveCameraSessionCoordinator``, the banner is unhidden, populated with
        the subject/group/day, and offers "Start Recording" / "Cancel Session"
        buttons. Both buttons publish back to the event bus and the
        coordinator drives the actual resume/cancel logic.
        """
        parent = (
            self.drawing_actions_parent if self.drawing_actions_parent else self.zone_controls_frame
        )

        # Use a plain frame with a colored background so it stands out as a
        # call-to-action without diverging too much from the existing style.
        self.pending_session_frame = ttk.Frame(parent, padding=8)
        # Not packed yet — packed on first LIVE_RECORDING_PENDING.

        self.pending_session_label = ttk.Label(
            self.pending_session_frame,
            text="",
            font=("Segoe UI", 10, "bold"),
            foreground="#7a4d00",
            wraplength=540,
            justify="left",
        )
        self.pending_session_label.pack(side="top", fill="x", pady=(0, 6))

        button_row = ttk.Frame(self.pending_session_frame)
        button_row.pack(side="top", fill="x")

        ttk.Button(
            button_row,
            text=_("▶️ Start Recording"),
            command=self._on_start_pending_recording_clicked,
            style="Accent.TButton",
        ).pack(side="left", padx=(0, 6))

        ttk.Button(
            button_row,
            text=_("✖ Cancel Session"),
            command=self._on_cancel_pending_recording_clicked,
        ).pack(side="left")

    def _show_pending_session_banner(self, payload: payloads.LiveRecordingPendingPayload) -> None:
        """Show the banner and populate it with the subject/group/day."""
        if self.pending_session_frame is None or self.pending_session_label is None:
            return
        self._pending_session_payload = payload

        subject = payload.subject_id or "—"
        group = payload.group or "—"
        day = payload.day or "—"
        source_text = (
            _("Auto-detected polygon")
            if payload.polygon_source == "auto"
            else _("Manually drawn polygon")
        )
        self.pending_session_label.config(
            text=_(
                "⏳ Pending session: Animal {subject} / Group {group} / {day}.\n"
                "{source} — click ▶️ Start Recording when you are ready."
            ).format(subject=subject, group=group, day=day, source=source_text)
        )

        # Pack at the top of the side panel / drawing area.
        try:
            self.pending_session_frame.pack(fill="x", padx=5, pady=(5, 0))
        except tk.TclError:
            # Parent destroyed mid-event — nothing to do.
            log.debug("zone_controls.pending_banner.show.suppressed", exc_info=True)

    def _hide_pending_session_banner(self) -> None:
        """Hide the banner (called on resume/cancel/session-started)."""
        self._pending_session_payload = None
        if self.pending_session_frame is None:
            return
        try:
            self.pending_session_frame.pack_forget()
        except tk.TclError:
            log.debug("zone_controls.pending_banner.hide.suppressed", exc_info=True)

    def _on_live_recording_pending(
        self, payload: payloads.LiveRecordingPendingPayload | None = None
    ) -> None:
        """Handle LIVE_RECORDING_PENDING — schedule banner show on the Tk thread."""
        if payload is None:
            return
        root = self.winfo_toplevel()
        if root is not None:
            root.after(0, lambda p=payload: self._show_pending_session_banner(p))  # type: ignore[misc]
        else:
            self._show_pending_session_banner(payload)

    def _on_live_recording_done(self, payload: Any = None) -> None:
        """Handle LIVE_SESSION_STARTED / STOPPED / LIVE_RECORDING_CANCELLED."""
        root = self.winfo_toplevel()
        if root is not None:
            root.after(0, self._hide_pending_session_banner)
        else:
            self._hide_pending_session_banner()

    def has_pending_live_session(self) -> bool:
        """True if a live recording is deferred awaiting zone confirmation.

        Set when ``LIVE_RECORDING_PENDING`` fires (banner shown) and cleared on
        resume/cancel/session-started. Used by the "Concluir" flow to decide
        whether to prompt the user to start the recording countdown.
        """
        return self._pending_session_payload is not None

    def _on_start_pending_recording_clicked(self) -> None:
        """Publish LIVE_RECORDING_RESUME_REQUESTED for the active pending session."""
        experiment_id = (
            self._pending_session_payload.experiment_id if self._pending_session_payload else None
        )
        self.emit_event(
            UIEvents.LIVE_RECORDING_RESUME_REQUESTED,
            payloads.LiveRecordingResumeRequestedPayload(experiment_id=experiment_id),
        )

    def _on_cancel_pending_recording_clicked(self) -> None:
        """Publish LIVE_RECORDING_CANCELLED for the active pending session."""
        experiment_id = (
            self._pending_session_payload.experiment_id if self._pending_session_payload else None
        )
        self.emit_event(
            UIEvents.LIVE_RECORDING_CANCELLED,
            payloads.LiveRecordingCancelledPayload(experiment_id=experiment_id),
        )
        # Optimistically hide locally — the coordinator's own publish round-trip
        # will arrive shortly and is idempotent.
        self._hide_pending_session_banner()

    def _build_drawing_actions(self) -> None:
        """Build the drawing actions section."""
        # Use external parent if provided, else default to side panel
        parent = (
            self.drawing_actions_parent if self.drawing_actions_parent else self.zone_controls_frame
        )

        actions_frame = ttk.LabelFrame(parent, text=_("Drawing Actions"), padding=5)
        # Kept as an attribute so ``show_aquarium_selector`` can anchor its
        # pack(after=...) on the widget itself. It used to search the parent's
        # children for a LabelFrame whose text contained "Desenho" -- a branch
        # on displayed text, which translation silently defeats.
        self.drawing_actions_frame = actions_frame
        # If in side panel, pack vertically. If in top bar, maybe horizontal?
        # For now, let's keep packing simple.
        actions_frame.pack(fill="x", pady=5, padx=5)

        # Container for buttons to allow grid or side-by-side layout if needed
        btn_container = ttk.Frame(actions_frame)
        btn_container.pack(fill="x")

        # Auto-detect button
        self.auto_detect_button = ttk.Button(
            btn_container,
            text=_("Detect Aquarium (Auto)"),
            command=self._on_auto_detect_clicked,
        )
        self.auto_detect_button.pack(side="left", fill="x", expand=True, padx=2, pady=2)

        # Manual polygon button
        self.draw_arena_button = ttk.Button(
            btn_container,
            text=_("Main Polygon"),
            command=self._on_draw_main_polygon_clicked,
        )
        self.draw_arena_button.pack(side="left", fill="x", expand=True, padx=2, pady=2)

        # ROI button (initially disabled)
        self.draw_roi_button = ttk.Button(
            btn_container,
            text=_("Region of Interest (ROI)"),
            command=self._on_draw_roi_clicked,
            state="disabled",
        )
        self.draw_roi_button.pack(side="left", fill="x", expand=True, padx=2, pady=2)

        # Conclude Video Button (Next to ROI button)
        self.conclude_video_btn = ttk.Button(
            btn_container,
            text=_("✅ Finish"),
            command=self._on_conclude_video_clicked,
            state="disabled",
            style="Accent.TButton",
        )
        self.conclude_video_btn.pack(side="left", fill="x", expand=True, padx=2, pady=2)

        # Stabilization frames entry - compact version
        stabilization_frame = ttk.Frame(actions_frame)
        stabilization_frame.pack(fill="x", pady=2, anchor="w")

        ttk.Label(stabilization_frame, text=_("Smoothing (frames):")).pack(side="left", padx=(0, 5))
        ttk.Entry(stabilization_frame, textvariable=self.stabilization_frames_var, width=5).pack(
            side="left"
        )
        ttk.Label(
            stabilization_frame,
            text=_("(reduces noise in auto-detection)"),
            font=("TkDefaultFont", 8),
            foreground="gray",
        ).pack(side="left", padx=(5, 0))

    def _build_aquarium_selector(self) -> None:
        """Build the multi-aquarium selector section.

        This section allows selecting which aquarium to work with when
        the video has 2 aquariums configured.

        Layout:
        ┌─ Active Aquarium ───────────────────────┐
        │  ○ Aquarium 1 (Left)                    │
        │  ○ Aquarium 2 (Right)                   │
        │  ────────────────────────────────────── │
        │  Processing Mode:                       │
        │  ○ Simultaneous (1 pass)                │
        │  ○ Sequential (2 passes)                │
        └─────────────────────────────────────────┘
        """
        parent = (
            self.drawing_actions_parent if self.drawing_actions_parent else self.zone_controls_frame
        )

        self.aquarium_selector_frame = ttk.LabelFrame(
            parent, text=_("🐟 Active Aquarium"), padding=5
        )
        # Initially hidden - shown only when 2 aquariums are detected
        # self.aquarium_selector_frame.pack(fill="x", pady=5, padx=5)

        # Radio buttons for aquarium selection
        radio_container = ttk.Frame(self.aquarium_selector_frame)
        radio_container.pack(fill="x")

        self.aquarium_radio_1 = ttk.Radiobutton(
            radio_container,
            text=_("Aquarium 1 (Left)"),
            variable=self.active_aquarium_var,
            value=0,
            command=self._on_aquarium_selected,
        )
        self.aquarium_radio_1.pack(side="left", padx=(0, 15))

        self.aquarium_radio_2 = ttk.Radiobutton(
            radio_container,
            text=_("Aquarium 2 (Right)"),
            variable=self.active_aquarium_var,
            value=1,
            command=self._on_aquarium_selected,
        )
        self.aquarium_radio_2.pack(side="left")

        # Separator between aquarium selection and processing mode
        ttk.Separator(self.aquarium_selector_frame, orient="horizontal").pack(
            fill="x", pady=(10, 5)
        )

        # Processing mode section
        self.processing_mode_frame = ttk.Frame(self.aquarium_selector_frame)
        self.processing_mode_frame.pack(fill="x")

        ttk.Label(
            self.processing_mode_frame,
            text=_("Processing Mode:"),
            font=("TkDefaultFont", 9, "bold"),
        ).pack(anchor="w")

        self.parallel_radio = ttk.Radiobutton(
            self.processing_mode_frame,
            text=_("Simultaneous (1 pass, faster)"),
            variable=self.sequential_processing_var,
            value=False,
            command=self._on_processing_mode_changed,
        )
        self.parallel_radio.pack(anchor="w", padx=(10, 0))

        self.sequential_radio = ttk.Radiobutton(
            self.processing_mode_frame,
            text=_("Sequential (2 passes, 1 aquarium at a time)"),
            variable=self.sequential_processing_var,
            value=True,
            command=self._on_processing_mode_changed,
        )
        self.sequential_radio.pack(anchor="w", padx=(10, 0))

        # Apply to all checkbox
        self.apply_to_all_checkbox = ttk.Checkbutton(
            self.processing_mode_frame,
            text=_("Apply to every video"),
            variable=self.apply_to_all_var,
        )
        self.apply_to_all_checkbox.pack(anchor="w", padx=(10, 0), pady=(5, 0))

        # Help text
        ttk.Label(
            self.processing_mode_frame,
            text=_("Sequential: processes the whole video for each aquarium separately"),
            font=("TkDefaultFont", 8),
            foreground="gray",
        ).pack(anchor="w", padx=(10, 0), pady=(2, 0))

    def _build_interactive_buttons(self) -> None:
        """Build the interactive editing buttons (initially hidden)."""
        # If drawing_actions_parent is provided, these buttons likely go there too
        parent = (
            self.drawing_actions_parent if self.drawing_actions_parent else self.zone_controls_frame
        )

        self.interactive_buttons_frame = ttk.Frame(parent)

        self.save_arena_btn = ttk.Button(
            self.interactive_buttons_frame,
            text=_("✅ Save Edit"),
            command=self._on_save_arena_clicked,
        )
        self.save_arena_btn.pack(side="left", fill="x", expand=True, padx=5, pady=5)

        self.discard_arena_btn = ttk.Button(
            self.interactive_buttons_frame,
            text=_("❌ Discard"),
            command=self._on_discard_arena_clicked,
        )
        self.discard_arena_btn.pack(side="left", fill="x", expand=True, padx=5, pady=5)

        # Finish Drawing button - for completing polygon without double-click
        self.finish_drawing_btn = ttk.Button(
            self.interactive_buttons_frame,
            text=_("✓ Finish Drawing"),
            command=self._on_finish_drawing_clicked,
        )
        self.finish_drawing_btn.pack(side="left", fill="x", expand=True, padx=5, pady=5)
        self.discard_arena_btn.pack(side="left", fill="x", expand=True, padx=5, pady=5)

    def _build_single_analysis_options(self) -> None:
        """Build the single analysis options section."""
        self.single_analysis_options_frame = ttk.LabelFrame(
            self.zone_controls_frame,
            text=_("Single Video Analysis Options"),
            padding=10,
        )
        # Initially hidden - packed on demand

        # ROI options
        ttk.Label(self.single_analysis_options_frame, text=_("ROI options:")).pack(anchor="w")
        ttk.Radiobutton(
            self.single_analysis_options_frame,
            text=_("Do not use ROIs"),
            variable=self.roi_choice_var,
            value="none",
        ).pack(anchor="w", padx=10)
        ttk.Radiobutton(
            self.single_analysis_options_frame,
            text=_("Draw ROIs manually"),
            variable=self.roi_choice_var,
            value="manual",
        ).pack(anchor="w", padx=10)
        ttk.Radiobutton(
            self.single_analysis_options_frame,
            text=_("Use ROIs from a template"),
            variable=self.roi_choice_var,
            value="template",
        ).pack(anchor="w", padx=10)

        # Frame intervals
        ttk.Label(self.single_analysis_options_frame, text=_("Analysis Interval (frames):")).pack(
            anchor="w", pady=(10, 0)
        )
        ttk.Entry(
            self.single_analysis_options_frame,
            textvariable=self.analysis_interval_var,
            width=10,
        ).pack(anchor="w", padx=10)

        ttk.Label(self.single_analysis_options_frame, text=_("Display Interval (frames):")).pack(
            anchor="w", pady=(5, 0)
        )
        ttk.Entry(
            self.single_analysis_options_frame,
            textvariable=self.display_interval_var,
            width=10,
        ).pack(anchor="w", padx=10)

    def _build_template_section(self) -> None:
        """Build the ROI template section."""
        # Use external parent if provided, else default to side panel
        parent = (
            self.template_actions_parent
            if self.template_actions_parent
            else self.zone_controls_frame
        )
        is_horizontal = self.template_actions_parent is not None

        template_frame = ttk.LabelFrame(parent, text=_("ROI Templates"), padding=5)
        template_frame.pack(fill="x", pady=5, padx=5)

        # Container for layout
        container = ttk.Frame(template_frame)
        container.pack(fill="x")

        if is_horizontal:
            # Compact Horizontal Layout for Bottom Panel
            ttk.Label(container, text=_("Template:")).pack(side="left", padx=(0, 5))
            self.roi_template_combobox = ttk.Combobox(
                container,
                state="readonly",
                textvariable=self.roi_template_var,
                values=[],
                width=20,
            )
            self.roi_template_combobox.pack(side="left", padx=(0, 5))

            ttk.Button(container, text=_("Apply"), command=self._on_apply_template_clicked).pack(
                side="left", padx=(0, 10)
            )

            ttk.Button(
                container,
                text=_("🧹 Clear drawing"),
                command=self._on_clear_applied_template_clicked,
            ).pack(side="left", padx=(0, 10))

            ttk.Button(
                container,
                text=_("💾 Save"),
                command=self._on_save_template_clicked,
            ).pack(side="left", padx=(0, 5))

            ttk.Button(
                container,
                text=_("📂 Import"),
                command=self._on_import_template_clicked,
            ).pack(side="left")

            # Help icon/tooltip could go here instead of full text
        else:
            # Vertical Layout for Side Panel
            template_selector = ttk.Frame(container)
            template_selector.pack(fill="x", pady=(0, 6))

            ttk.Label(template_selector, text=_("Template:")).pack(side="left", padx=(0, 5))
            self.roi_template_combobox = ttk.Combobox(
                template_selector,
                state="readonly",
                textvariable=self.roi_template_var,
                values=[],
                width=15,
            )
            self.roi_template_combobox.pack(side="left", fill="x", expand=True)

            ttk.Button(
                template_selector, text=_("Apply"), command=self._on_apply_template_clicked
            ).pack(side="left", padx=4)
            ttk.Button(
                template_selector,
                text=_("🧹 Clear drawing"),
                command=self._on_clear_applied_template_clicked,
            ).pack(side="left", padx=4)

            # Template actions
            template_actions = ttk.Frame(container)
            template_actions.pack(fill="x")

            ttk.Button(
                template_actions,
                text=_("💾 Save Current Zones"),
                command=self._on_save_template_clicked,
            ).pack(side="left", padx=(0, 4))
            ttk.Button(
                template_actions,
                text=_("📂 Import and Apply File..."),
                command=self._on_import_template_clicked,
            ).pack(side="left")

            # Help text
            ttk.Label(
                template_frame,
                text=_(
                    "Templates store the main polygon and every ROI so they can be "
                    "reused on other videos of the project."
                ),
                wraplength=200,
                style="Small.TLabel",
            ).pack(anchor="w", pady=(6, 0))

    def _build_video_selector(self) -> None:
        """Build the video selector section."""
        # ALWAYS use side panel for video selector, regardless of other parents
        parent = self.zone_controls_frame

        video_selector_frame = ttk.LabelFrame(
            parent,
            text=_("📹 Select Video for Drawing"),
            padding=5,
        )
        # Allow this frame to expand vertically to fill space
        video_selector_frame.pack(fill="both", expand=True, pady=5, padx=5)

        # Search bar
        search_frame = ttk.Frame(video_selector_frame)
        search_frame.pack(fill="x", pady=(0, 5))

        ttk.Label(search_frame, text=_("🔍 Search:")).pack(side="left", padx=(0, 5))
        self.video_search_var.trace_add("write", lambda *_: self._on_video_search_changed())
        ttk.Entry(search_frame, textvariable=self.video_search_var, width=25).pack(
            side="left", fill="x", expand=True, padx=(0, 5)
        )
        self.video_tree_toggle_btn = ttk.Button(
            search_frame,
            text=_("Collapse all"),
            width=14,
            command=self._toggle_video_tree_nodes,
        )
        self.video_tree_toggle_btn.pack(side="left", padx=(5, 0))

        # Treeview
        tree_container = ttk.Frame(video_selector_frame)
        tree_container.pack(fill="both", expand=True)

        from zebtrack.ui.window_utils import create_scrollbar

        self.video_selector_tree = ttk.Treeview(
            tree_container,
            columns=("status", "filename"),
            show="tree headings",
            height=15,  # Increased height for better vertical distribution
            selectmode="browse",
        )
        self.video_selector_tree.heading("#0", text=_("Hierarchy"))
        self.video_selector_tree.heading("status", text=_("Data"))
        self.video_selector_tree.heading("filename", text=_("File"))

        self.video_selector_tree.column("#0", width=180, minwidth=140, stretch=True)
        self.video_selector_tree.column("status", width=60, anchor="center", stretch=False)
        self.video_selector_tree.column("filename", width=120, stretch=True)

        scrollbar = create_scrollbar(
            tree_container, orient="vertical", command=self.video_selector_tree.yview
        )
        self.video_selector_tree.configure(yscrollcommand=scrollbar.set)
        self.video_selector_tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Configure tag styles
        TAG_STYLES = {
            "ready_full": {"background": "#d4edda", "foreground": "#1e4620"},
            "ready_partial": {"background": "#fff3cd", "foreground": "#5c470b"},
            "ready_missing": {"background": "#f8d7da", "foreground": "#842029"},
        }
        for tag, style in TAG_STYLES.items():
            self.video_selector_tree.tag_configure(tag, **style)  # type: ignore[call-overload]

        # Bind events
        self.video_selector_tree.bind("<Double-Button-1>", self._on_video_tree_double_click)
        self.video_selector_tree.bind("<Button-3>", self._on_video_tree_right_click)

        # Create context menu for video tree
        self._create_video_tree_context_menu()

        # Load frame button
        ttk.Button(
            video_selector_frame,
            text=_("📹 Load Frame from the Selected Video"),
            command=self._on_load_video_frame_clicked,
        ).pack(pady=(5, 0))

        self._update_video_tree_toggle_label()

    def _toggle_video_tree_nodes(self) -> None:
        """Toggle expand/collapse all groups in the video selector."""
        if not self.video_selector_tree:
            return

        self._video_tree_expanded = not self._video_tree_expanded
        self._set_video_tree_open_state(self._video_tree_expanded)
        self._update_video_tree_toggle_label()

    def apply_video_tree_expand_state(self) -> None:
        """Reaplica o estado atual de expansão após repovoar a árvore."""
        self._set_video_tree_open_state(self._video_tree_expanded)
        self._update_video_tree_toggle_label()

    def _set_video_tree_open_state(self, expanded: bool) -> None:
        """Set the open state of top-level nodes."""
        if not self.video_selector_tree:
            return

        for group_id in self.video_selector_tree.get_children(""):
            self.video_selector_tree.item(group_id, open=expanded)
            for day_id in self.video_selector_tree.get_children(group_id):
                self.video_selector_tree.item(day_id, open=expanded)

    def _update_video_tree_toggle_label(self) -> None:
        """Atualiza o texto do botão de expandir/recolher conforme o estado."""
        if not self.video_tree_toggle_btn:
            return

        if self._video_tree_expanded:
            self.video_tree_toggle_btn.config(text=_("Collapse all"))
        else:
            self.video_tree_toggle_btn.config(text=_("Expand all"))

    def _build_zone_list(self) -> None:
        """Build the zone list section."""
        zone_list_frame = ttk.LabelFrame(
            self.zone_controls_frame, text=_("Defined Zones"), padding=10
        )
        zone_list_frame.pack(fill="x", pady=5)

        from zebtrack.ui.window_utils import create_scrollbar

        self.zone_listbox = ttk.Treeview(
            zone_list_frame,
            columns=("name", "type", "color"),
            show="headings",
            height=6,
        )
        self.zone_listbox.heading("name", text=_("Name"))
        self.zone_listbox.heading("type", text=_("Type"))
        self.zone_listbox.heading("color", text=_("Colour"))

        # Configure column widths - Name takes ~60%, Type ~20%, Color ~20%
        self.zone_listbox.column("name", width=200, minwidth=100, stretch=True)
        self.zone_listbox.column("type", width=70, minwidth=50, stretch=True)
        self.zone_listbox.column("color", width=70, minwidth=35, stretch=True)

        self.zone_listbox.pack(side="left", fill="both", expand=True)

        # Scrollbar
        scrollbar = create_scrollbar(
            zone_list_frame, orient="vertical", command=self.zone_listbox.yview
        )
        self.zone_listbox.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")

        # Bind events
        self.zone_listbox.bind("<Button-3>", self._on_zone_right_click)
        self.zone_listbox.bind("<Double-Button-1>", self._on_zone_double_click)

    def _build_roi_inclusion_panel(self) -> None:
        """Build the ROI inclusion rule configuration panel."""
        self.roi_inclusion_frame = ttk.LabelFrame(
            self.zone_controls_frame, text=_("ROI Inclusion Rule"), padding=10
        )
        self.roi_inclusion_frame.pack(fill="x", pady=5)

        # Rule selection
        rule_frame = ttk.Frame(self.roi_inclusion_frame)
        rule_frame.pack(fill="x", pady=2)

        ttk.Label(rule_frame, text=_("Rule:")).pack(side="left", padx=(0, 5))
        self.roi_rule_combo = ttk.Combobox(
            rule_frame,
            textvariable=self.roi_inclusion_rule_var,
            values=[
                "centroid_in",
                "centroid_in_on_buffered_roi",
                "bbox_intersects",
                "seg_overlap",
            ],
            state="readonly",
            width=18,
        )
        self.roi_rule_combo.pack(side="left", fill="x", expand=True)
        self.roi_rule_combo.bind("<<ComboboxSelected>>", self._on_roi_rule_changed)

        # Buffer radius parameter (Initially hidden)
        self.radius_frame = ttk.Frame(self.roi_inclusion_frame)
        # self.radius_frame.pack(fill="x", pady=2) # Logic handles visibility
        ttk.Label(self.radius_frame, text=_("Buffer radius (r):")).pack(side="left", padx=(0, 5))
        ttk.Entry(self.radius_frame, textvariable=self.roi_buffer_radius_var, width=10).pack(
            side="left", padx=(0, 10)
        )
        # Help text below input for compact width
        ttk.Label(
            self.radius_frame,
            text=_("ROI dilation (cm if calibrated, otherwise px)."),
            font=("TkDefaultFont", 8),
            foreground="gray",
        ).pack(side="left")

        # Overlap ratio parameter (Initially hidden)
        self.overlap_frame = ttk.Frame(self.roi_inclusion_frame)
        # self.overlap_frame.pack(fill="x", pady=2) # Logic handles visibility
        ttk.Label(self.overlap_frame, text=_("Min. overlap (0-1):")).pack(side="left", padx=(0, 5))
        ttk.Entry(self.overlap_frame, textvariable=self.roi_overlap_ratio_var, width=10).pack(
            side="left", padx=(0, 10)
        )
        # O texto depende da regra: 0 só vale em ``bbox_intersects``. Fixo, ele
        # induziria ao erro com ``seg_overlap`` selecionada, onde 0 é recusado.
        self.overlap_hint_label = ttk.Label(
            self.overlap_frame,
            text="",
            font=("TkDefaultFont", 8),
            foreground="gray",
        )
        self.overlap_hint_label.pack(side="left")

        # Help text
        self.rule_help_label = ttk.Label(
            self.roi_inclusion_frame,
            text="",
            font=("TkDefaultFont", 8),
            wraplength=200,  # Adjusted for narrower panel
            justify="left",
        )
        self.rule_help_label.pack(fill="x", pady=(5, 0))

        # Apply button
        save_settings_frame = ttk.Frame(self.roi_inclusion_frame)
        save_settings_frame.pack(fill="x", pady=(5, 0))
        ttk.Button(
            save_settings_frame,
            text=_("Apply Settings"),
            command=self._on_apply_roi_settings_clicked,
        ).pack(side="right")

        # Force update visibility based on default value
        self._on_roi_rule_changed(None)

    # Event handlers that emit events to the event bus

    def _on_conclude_video_clicked(self) -> None:
        """Handle conclude video button click."""
        self.emit_event(UIEvents.ZONE_CONCLUDE_VIDEO, payloads.EmptyPayload())

    def _on_auto_detect_clicked(self) -> None:
        """Handle auto-detect button click."""
        self.emit_event(
            UIEvents.ZONE_AUTO_DETECT_CLICKED,
            {"stabilization_frames": self.stabilization_frames_var.get()},
        )

    def _on_aquarium_selected(self) -> None:
        """Handle aquarium selection change."""
        aquarium_id = self.active_aquarium_var.get()
        log.debug("zone_controls.aquarium_selected", aquarium_id=aquarium_id)
        self.emit_event(
            UIEvents.ZONE_AQUARIUM_SELECTED,
            {"aquarium_id": aquarium_id},
        )

    def _on_processing_mode_changed(self) -> None:
        """Handle processing mode change (parallel vs sequential).

        Emits ZONE_PROCESSING_MODE_CHANGED event with the new mode.
        Sequential mode processes each aquarium separately (2 video passes).
        Parallel mode processes both aquariums simultaneously (1 video pass).

        If "apply_to_all" is checked, the mode is applied to all videos in the project.
        """
        sequential = self.sequential_processing_var.get()
        apply_to_all = self.apply_to_all_var.get()
        log.info(
            "zone_controls.processing_mode_changed",
            sequential=sequential,
            apply_to_all=apply_to_all,
            mode="sequential" if sequential else "parallel",
        )
        self.emit_event(
            UIEvents.ZONE_PROCESSING_MODE_CHANGED,
            {"sequential": sequential, "apply_to_all": apply_to_all},
        )

    def _on_draw_main_polygon_clicked(self) -> None:
        """Handle draw main polygon button click."""
        self.emit_event(UIEvents.ZONE_DRAW_ARENA, payloads.EmptyPayload())

    def _on_draw_roi_clicked(self) -> None:
        """Handle draw ROI button click."""
        self.emit_event(UIEvents.ZONE_DRAW_ROI, payloads.EmptyPayload())

    def _on_toggle_view_clicked(self) -> None:
        """Handle toggle view button click."""
        self.emit_event(UIEvents.ZONE_TOGGLE_VIEW, payloads.EmptyPayload())

    def _on_apply_template_clicked(self) -> None:
        """Handle apply template button click."""
        self.emit_event(
            UIEvents.ZONE_TEMPLATE_APPLY,
            payloads.ZoneTemplateApplyPayload(template_name=self.roi_template_var.get()),
        )

    def _on_save_template_clicked(self) -> None:
        """Handle save template button click."""
        self.emit_event(UIEvents.ZONE_TEMPLATE_SAVE, payloads.EmptyPayload())

    def _on_import_template_clicked(self) -> None:
        """Handle import template button click."""
        self.emit_event(UIEvents.ZONE_TEMPLATE_IMPORT, payloads.EmptyPayload())

    def _on_clear_applied_template_clicked(self) -> None:
        """Handle clear applied template drawings from active video."""
        self.emit_event(UIEvents.ZONE_TEMPLATE_CLEAR_APPLIED, payloads.EmptyPayload())

    def _on_video_search_changed(self) -> None:
        """Handle video search text change."""
        self.emit_event(
            UIEvents.ZONE_VIDEO_SEARCH_CHANGED,
            {"search_text": self.video_search_var.get()},
        )

    def _on_video_refresh_clicked(self) -> None:
        """Handle video refresh button click."""
        self.emit_event(UIEvents.ZONE_VIDEO_REFRESH, payloads.EmptyPayload())

    def _on_video_tree_double_click(self, event: tk.Event) -> None:
        """Handle video tree double-click."""
        if not self.video_selector_tree:
            return

        selection = self.video_selector_tree.selection()
        if selection:
            item_id = selection[0]
            self.emit_event(
                UIEvents.ZONE_VIDEO_DOUBLE_CLICK,
                payloads.ZoneVideoDoubleClickPayload(item_id=item_id),
            )

    def _on_video_tree_right_click(self, event) -> None:
        """Handle video tree right-click to show context menu."""
        if not self.video_selector_tree or not hasattr(self, "_video_context_menu"):
            return

        # Identify the item under cursor
        item_id = self.video_selector_tree.identify_row(event.y)
        if not item_id:
            return

        # Select the item
        self.video_selector_tree.selection_set(item_id)

        # Check if this is a hierarchy node (group, day, subject)
        node_info = self._get_hierarchy_node_info(item_id)
        if node_info is not None:
            self._show_hierarchy_context_menu(event, node_info)
            return

        # Check if this is a video item (has a video_path stored)
        video_path = self._get_video_path_from_item(item_id)
        if not video_path:
            return

        # Store the video path for menu commands
        self._context_menu_video_path = video_path

        # Show context menu
        self._video_context_menu.post(event.x_root, event.y_root)

    def _create_video_tree_context_menu(self) -> None:
        """Create context menu for video tree with copy/paste/delete options."""
        self._video_context_menu = Menu(
            self.video_selector_tree, tearoff=0, font=("TkDefaultFont", 9)
        )
        self._video_context_menu.add_command(
            label=_("📋 Copy Zones"), command=self._on_copy_zones_clicked
        )
        self._video_context_menu.add_command(
            label=_("📥 Paste Zones"), command=self._on_paste_zones_clicked
        )
        self._video_context_menu.add_separator()
        self._video_context_menu.add_command(
            label=_("🗑️ Delete Zones"), command=self._on_delete_zones_clicked
        )
        self._video_context_menu.add_separator()
        self._video_context_menu.add_command(
            label=_("🔄 Edit Group / Day / Subjects"),
            command=self._on_reconfigure_subjects_clicked,
        )
        self._context_menu_video_path = None

    # ── Hierarchy context menu (group / day / subject) ────────────────

    _HIERARCHY_EVENT_MAP: ClassVar[dict[str, UIEvents]] = {
        "group": UIEvents.PROJECT_DELETE_GROUP,
        "day": UIEvents.PROJECT_DELETE_DAY,
        "subject": UIEvents.PROJECT_DELETE_SUBJECT,
    }

    def _get_hierarchy_node_info(self, item_id: str) -> tuple[str, tuple[str, ...]] | None:
        """Return ``(node_type, tag_tuple)`` if *item_id* is a hierarchy node.

        Tags for hierarchy nodes have the pattern
        ``("group", gid)``, ``("day", gid, did)``,
        ``("subject", gid, did, sid)``.
        Returns ``None`` for video nodes and nodes with no tags.
        """
        if not self.video_selector_tree:
            return None
        tags = self.video_selector_tree.item(item_id, "tags")
        if not tags:
            return None
        first = str(tags[0])
        if first in self._HIERARCHY_TAG_PREFIXES:
            return first, tuple(str(t) for t in tags)
        return None

    def _show_hierarchy_context_menu(
        self,
        event: Any,
        node_info: tuple[str, tuple[str, ...]],
    ) -> None:
        """Build and show a context menu for a hierarchy node."""
        node_type, tag_tuple = node_info
        label = _hierarchy_labels().get(node_type, node_type)
        # Derive display name from the tree item text
        item_id = self.video_selector_tree.selection()[0]  # type: ignore[union-attr]
        item_text = self.video_selector_tree.item(item_id, "text")  # type: ignore[union-attr]

        menu = Menu(self.video_selector_tree, tearoff=0, font=("TkDefaultFont", 9))
        menu.add_command(
            label=_("🗑️ Delete {label}…").format(label=label),
            command=lambda: self._on_delete_hierarchy_node(node_type, tag_tuple, item_text),
        )
        menu.post(event.x_root, event.y_root)

    def _on_delete_hierarchy_node(
        self,
        node_type: str,
        tag_tuple: tuple[str, ...],
        display_label: str,
    ) -> None:
        """Handle hierarchy node deletion via confirmation + event emission."""
        # Collect affected videos
        videos = self._collect_descendant_videos(self.video_selector_tree.selection()[0])  # type: ignore[union-attr]
        video_names = [v.rsplit("\\", 1)[-1].rsplit("/", 1)[-1] for v in videos]

        if not video_names:
            return

        dm = getattr(self, "dialog_manager", None)
        if dm is None:
            # Fallback: walk up to gui
            gui = getattr(self, "gui", None)
            dm = getattr(gui, "dialog_manager", None) if gui else None
        if dm is None:
            return

        confirmed, delete_files = dm.confirm_delete_hierarchy_node(
            node_type, display_label, len(video_names), video_names
        )
        if not confirmed:
            return

        # Build payload kwargs from structured tags
        kwargs: dict[str, Any] = {"delete_files": delete_files}
        if node_type == "group":
            kwargs["group_id"] = tag_tuple[1]
        elif node_type == "day":
            kwargs["group_id"] = tag_tuple[1]
            kwargs["day_id"] = tag_tuple[2]
        elif node_type == "subject":
            kwargs["group_id"] = tag_tuple[1]
            kwargs["day_id"] = tag_tuple[2]
            kwargs["subject_id"] = tag_tuple[3]

        event_type = self._HIERARCHY_EVENT_MAP.get(node_type)
        if event_type:
            self.emit_event(event_type, kwargs)

    def _collect_descendant_videos(self, item_id: str) -> list[str]:
        """Recursively collect video paths from all descendants of *item_id*."""
        tree = self.video_selector_tree
        result: list[str] = []

        def _walk(node: str) -> None:
            for child in tree.get_children(node):  # type: ignore[union-attr]
                path = self._get_video_path_from_item(child)
                if path:
                    result.append(path)
                else:
                    _walk(child)

        _walk(item_id)
        return result

    # Tags that identify non-video hierarchy nodes (group, day, subject).
    _HIERARCHY_TAG_PREFIXES = frozenset(("group", "day", "subject"))

    def _get_video_path_from_item(self, item_id: str) -> str | None:
        """Get video path from a tree item ID.

        The video path is stored in the item's tags, not values.
        Only leaf nodes (video items) have tags with the path.
        Group, Day, and Subject nodes use structured tuple tags
        (e.g. ``("group", group_id)``) and are skipped.
        """
        if not self.video_selector_tree:
            return None

        # Get item data
        item = self.video_selector_tree.item(item_id)

        # Video path is stored in tags (first tag is the path)
        # Note: tags can be a tuple, list, or string depending on Tk version
        tags = item.get("tags", ())

        if not tags:
            return None

        # Handle case where tags is a string (single tag)
        if isinstance(tags, str):
            # Skip hierarchy nodes whose single tag is a known prefix
            if tags in self._HIERARCHY_TAG_PREFIXES:
                return None
            return tags if tags else None

        # Handle case where tags is a tuple/list
        if len(tags) > 0:
            tag = tags[0]
            # Skip hierarchy nodes (group, day, subject)
            if str(tag) in self._HIERARCHY_TAG_PREFIXES:
                return None
            # Return the tag if it looks like a path (contains path separator or file extension)
            if tag and (
                "/" in str(tag)
                or "\\" in str(tag)
                or any(str(tag).lower().endswith(ext) for ext in (".mp4", ".avi", ".mov", ".mkv"))
            ):
                return str(tag)

        return None

    def _on_copy_zones_clicked(self) -> None:
        """Handle copy zones from context menu."""
        if hasattr(self, "_context_menu_video_path") and self._context_menu_video_path:
            self.emit_event(
                UIEvents.ZONE_COPY_ZONES,
                payloads.VideoPathPayload(video_path=self._context_menu_video_path),
            )

    def _on_paste_zones_clicked(self) -> None:
        """Handle paste zones from context menu."""
        if hasattr(self, "_context_menu_video_path") and self._context_menu_video_path:
            self.emit_event(
                UIEvents.ZONE_PASTE_ZONES,
                payloads.VideoPathPayload(video_path=self._context_menu_video_path),
            )

    def _on_delete_zones_clicked(self) -> None:
        """Handle delete zones from context menu."""
        if hasattr(self, "_context_menu_video_path") and self._context_menu_video_path:
            self.emit_event(
                UIEvents.ZONE_DELETE_ZONES,
                payloads.VideoPathPayload(video_path=self._context_menu_video_path),
            )

    def _on_reconfigure_subjects_clicked(self) -> None:
        """Handle metadata editing from the video tree context menu."""
        if not hasattr(self, "_context_menu_video_path") or not self._context_menu_video_path:
            return

        video_path = self._context_menu_video_path

        # Get current video metadata from project manager
        pm = None
        if hasattr(self.parent, "controller") and hasattr(
            self.parent.controller, "project_manager"
        ):  # type: ignore[attr-defined]
            pm = self.parent.controller.project_manager  # type: ignore[attr-defined]
        if not pm:
            log.warning("zone_controls.reconfigure.no_project_manager")
            return

        video_entry = pm.find_video_entry(video_path)
        if not video_entry:
            log.warning("zone_controls.reconfigure.video_not_found", video=video_path)
            return

        metadata = video_entry.get("metadata", {})
        calibration = pm.project_data.get("calibration", {}) if pm.project_data else {}
        num_aquariums = max(1, int(calibration.get("num_aquariums", 1) or 1))
        animals_per_aquarium = max(1, int(calibration.get("animals_per_aquarium", 1) or 1))

        dialog = VideoMetadataDialog(
            self.winfo_toplevel(),
            video_path=video_path,
            available_groups=pm.get_available_groups(),
            initial_metadata=dict(metadata or {}),
            subject_entry_count=max(1, num_aquariums * animals_per_aquarium),
        )
        if not dialog.result:
            return

        if pm.update_video_metadata(video_path, dialog.result):
            log.info(
                "zone_controls.reconfigure.success",
                video=video_path,
                metadata_keys=list(dialog.result.keys()),
            )
            self.emit_event(
                UIEvents.VIDEO_METADATA_UPDATED,
                payloads.VideoMetadataUpdatedPayload(
                    video_path=video_path,
                    metadata=dialog.result,
                ),
            )
            self.emit_event(
                UIEvents.PROJECT_VIEWS_REFRESH_REQUESTED,
                payloads.ProjectViewsRefreshRequestedPayload(
                    reason=_("Video metadata updated."),
                    immediate=True,
                ),
            )

    def _on_load_video_frame_clicked(self) -> None:
        """Handle load video frame button click."""
        if not self.video_selector_tree:
            return

        selection = self.video_selector_tree.selection()
        if selection:
            item_id = selection[0]
            self.emit_event(
                UIEvents.ZONE_VIDEO_FRAME_LOAD, payloads.ZoneVideoFrameLoadPayload(item_id=item_id)
            )

    def _on_zone_right_click(self, event) -> None:
        """Handle zone list right-click."""
        if not self.zone_listbox:
            return

        selection = self.zone_listbox.selection()
        if selection:
            item_id = selection[0]
            self.emit_event(
                UIEvents.ZONE_LIST_ITEM_RIGHT_CLICK,
                payloads.ZoneListItemRightClickPayload(
                    item_id=item_id, x=event.x_root, y=event.y_root
                ),
            )

    def _on_zone_double_click(self, event) -> None:
        """Handle zone list double-click."""
        if not self.zone_listbox:
            return

        selection = self.zone_listbox.selection()
        if selection:
            item_id = selection[0]
            self.emit_event(
                UIEvents.ZONE_LIST_ITEM_DOUBLE_CLICK, payloads.ZoneListItemPayload(item_id=item_id)
            )

    def _on_save_arena_clicked(self) -> None:
        """Handle save arena button click."""
        self.emit_event(UIEvents.ZONE_SAVE_ARENA, payloads.EmptyPayload())

    def _on_discard_arena_clicked(self) -> None:
        """Handle discard arena button click."""
        self.emit_event(UIEvents.ZONE_DISCARD_ARENA, payloads.EmptyPayload())

    def _on_finish_drawing_clicked(self) -> None:
        """Handle finish drawing button click - completes polygon without double-click."""
        self.emit_event(UIEvents.ZONE_FINISH_DRAWING, payloads.EmptyPayload())
        # Feedback visível: o botão fica esmaecido e indica que o desenho foi
        # finalizado. O botão "Concluir" segue disponível para o caso de o
        # usuário ainda querer ajustar antes de concluir. O botão volta ao
        # normal quando uma nova edição começa (show_interactive_buttons).
        if getattr(self, "finish_drawing_btn", None):
            try:
                self.finish_drawing_btn.config(state="disabled", text=_("✓ Drawing Finished"))
            except tk.TclError:
                log.debug("zone_controls.finish_drawing.feedback_suppressed", exc_info=True)

    def _on_roi_rule_changed(self, event) -> None:
        """Handle ROI rule change — apenas feedback visual.

        Trocar a seleção do combo mostra/esconde o parâmetro daquela regra e
        atualiza a ajuda; nada é aplicado até o botão "Aplicar". Este handler
        publicava ``DETECTOR_UPDATE_PARAMETERS``, cujo pipeline descarta as
        chaves de ROI e ainda loga sucesso — o mesmo no-op que este PR remove
        do "Aplicar", e que aqui não tinha sequer o que fazer.
        """
        rule = self.roi_inclusion_rule_var.get()
        overlap_hint = ""

        # Update visibility based on rule
        if rule == "centroid_in_on_buffered_roi":
            if self.radius_frame and self.roi_rule_combo:
                self.radius_frame.pack(fill="x", pady=2, after=self.roi_rule_combo.master)
            if self.overlap_frame:
                self.overlap_frame.pack_forget()
            help_text = _(
                "Counts as inside if the centroid is in the ROI expanded by the buffer radius."
            )
        elif rule in ("bbox_intersects", "seg_overlap"):
            if self.radius_frame:
                self.radius_frame.pack_forget()
            if self.overlap_frame and self.roi_rule_combo:
                self.overlap_frame.pack(fill="x", pady=2, after=self.roi_rule_combo.master)
            # O 0 é exclusivo de ``bbox_intersects``; em ``seg_overlap`` o
            # validador recusa e o painel não pode sugerir o contrário.
            if rule == "bbox_intersects":
                help_text = _(
                    "Counts as inside if the box (bbox) overlaps the ROI above the "
                    "minimum fraction."
                )
                overlap_hint = _("0 = any real overlap.")
            else:
                # A regra é selecionável mas tem TRÊS pré-requisitos; nomear os
                # dois que não estão neste painel evita o beco sem saída de
                # escolher seg_overlap e só descobrir a degradação no relatório.
                help_text = _(
                    "Counts as inside by the overlap of the MASK with the ROI. "
                    "Also requires recorder.persist_masks enabled (settings editor) "
                    "and model_selection.animal_method = 'seg'. If either is "
                    "missing, the analysis degrades to bbox_intersects and warns in "
                    "the report."
                )
                overlap_hint = _("Must be greater than 0.")
        else:
            # centroid_in or others
            if self.radius_frame:
                self.radius_frame.pack_forget()
            if self.overlap_frame:
                self.overlap_frame.pack_forget()
            help_text = _("Counts as inside if the geometric centroid is strictly inside the ROI.")

        if self.rule_help_label:
            self.rule_help_label.config(text=help_text)
        if self.overlap_hint_label:
            self.overlap_hint_label.config(text=overlap_hint)

    def _on_apply_roi_settings_clicked(self) -> None:
        """Handle apply ROI settings button click.

        Emite ``ZONE_APPLY_ROI_SETTINGS`` (persistido em
        ``project_data["roi_settings"]``) — e não mais
        ``DETECTOR_UPDATE_PARAMETERS``, que descartava as três chaves em
        silêncio e ainda logava sucesso.

        Os campos vão CRUS: ``float()`` aqui estoura com texto inválido dentro
        do callback do Tk e o botão morre sem dizer nada. A validação (e o
        descarte logado) é do ``resolve_roi_rule``.
        """
        self.emit_event(
            UIEvents.ZONE_APPLY_ROI_SETTINGS,
            payloads.RoiSettingsApplyPayload(
                rule=self.roi_inclusion_rule_var.get(),
                buffer_radius=self.roi_buffer_radius_var.get(),
                overlap_ratio=self.roi_overlap_ratio_var.get(),
            ),
        )

    # Public API for controlling widget state

    def set_roi_rule_config(self, config: RoiRuleConfig) -> None:
        """Reexibe a regra de ROI EFETIVA (ex.: depois de abrir um projeto).

        Recebe a config já resolvida — o painel não conhece a precedência
        projeto > global > default, só mostra o resultado dela.
        """
        self.roi_inclusion_rule_var.set(config.rule)
        self.roi_buffer_radius_var.set(f"{config.buffer_radius_value:g}")
        self.roi_overlap_ratio_var.set(f"{config.min_bbox_overlap_ratio:g}")
        # Mostra/esconde o parâmetro da regra recém-exibida.
        self._on_roi_rule_changed(None)

    def set_draw_roi_enabled(self, enabled: bool) -> None:
        """Enable or disable the draw ROI button."""
        state = "normal" if enabled else "disabled"
        if self.draw_roi_button:
            self.draw_roi_button.config(state=state)
        if hasattr(self, "conclude_video_btn") and self.conclude_video_btn:
            self.conclude_video_btn.config(state=state)

    def show_single_analysis_options(self) -> None:
        """Show the single analysis options frame."""
        if hasattr(self, "single_analysis_options_frame"):
            try:
                if self.zone_controls_frame.winfo_exists():
                    children = self.zone_controls_frame.winfo_children()
                    if len(children) > 1:
                        self.single_analysis_options_frame.pack(
                            fill="x", pady=5, before=children[1]
                        )
                    else:
                        self.single_analysis_options_frame.pack(fill="x", pady=5)
            except (tk.TclError, IndexError):
                # Frame destroyed or invalid state
                log.debug("zone_controls.show_single_analysis_options.suppressed", exc_info=True)

    def hide_single_analysis_options(self) -> None:
        """Hide the single analysis options frame."""
        if hasattr(self, "single_analysis_options_frame"):
            self.single_analysis_options_frame.pack_forget()

    def show_interactive_buttons(self) -> None:
        """Show the interactive editing buttons."""
        # Reinicia o botão "Finalizar Desenho" para uma nova sessão de edição
        # (ele é esmaecido após o clique como sinal de conclusão).
        if getattr(self, "finish_drawing_btn", None):
            try:
                self.finish_drawing_btn.config(state="normal", text=_("✓ Finish Drawing"))
            except tk.TclError:
                log.debug("zone_controls.finish_drawing.reset_suppressed", exc_info=True)
        if self.interactive_buttons_frame:
            try:
                if self.interactive_buttons_frame.master == self.roi_inclusion_frame.master:
                    # Pack before ROI inclusion frame if in same container (side panel)
                    self.interactive_buttons_frame.pack(
                        fill="x", pady=5, before=self.roi_inclusion_frame
                    )
                else:
                    # Pack normally if in different container (top toolbar)
                    self.interactive_buttons_frame.pack(fill="x", pady=5)
            except Exception:
                # Fallback to simple pack
                self.interactive_buttons_frame.pack(fill="x", pady=5)

    def hide_interactive_buttons(self) -> None:
        """Hide the interactive editing buttons."""
        if self.interactive_buttons_frame:
            self.interactive_buttons_frame.pack_forget()

    def update_template_list(self, templates: list[str]) -> None:
        """Update the template combobox with available templates."""
        if self.roi_template_combobox:
            self.roi_template_combobox.config(values=templates)

    def clear_zone_list(self) -> None:
        """Clear all items from the zone list."""
        if not self.zone_listbox:
            return

        try:
            if hasattr(self.zone_listbox, "winfo_exists") and self.zone_listbox.winfo_exists():
                for item in self.zone_listbox.get_children():
                    self.zone_listbox.delete(item)
        except Exception:
            # Widget might have been destroyed during teardown
            log.debug("zone_controls.clear_zone_listbox.suppressed", exc_info=True)

    def add_zone_to_list(
        self, zone_id: str, name: str, zone_type: str, color: str, color_hex: str | None = None
    ) -> None:
        """Add a zone to the zone list with optional colored text.

        Args:
            zone_id: Unique identifier for the zone
            name: Display name for the zone
            zone_type: Type of zone (e.g., "Polígono", "ROI")
            color: Color name to display
            color_hex: Optional hex color code for text styling (e.g., "#FF0000")
        """
        if not self.zone_listbox:
            return
        try:
            lb = self.zone_listbox
            if not (hasattr(lb, "winfo_exists") and lb.winfo_exists()):
                return
            lb.insert("", "end", iid=zone_id, values=(name, zone_type, color))
            # Apply colored text styling if hex color is provided
            if color_hex:
                tag_name = f"color_{zone_id}"
                lb.tag_configure(tag_name, foreground=color_hex)
                lb.item(zone_id, tags=(tag_name,))
        except Exception:
            log.debug("zone_controls.add_zone_to_list.suppressed", exc_info=True)

    # Multi-aquarium public API

    def set_aquarium_count(self, count: int) -> None:
        """Set the number of aquariums and show/hide the selector.

        Args:
            count: Number of aquariums (1 or 2).
        """
        count = max(1, min(2, count))  # Clamp to 1-2
        self.aquarium_count_var.set(count)

        if count == 2:
            self.show_aquarium_selector()
        else:
            self.hide_aquarium_selector()
            self.active_aquarium_var.set(0)  # Reset to aquarium 1

        log.debug("zone_controls.aquarium_count_set", count=count)

    def get_aquarium_count(self) -> int:
        """Get the current aquarium count.

        Returns:
            Number of aquariums (1 or 2).
        """
        return self.aquarium_count_var.get()

    def show_aquarium_selector(self) -> None:
        """Show the aquarium selector frame."""
        if self.aquarium_selector_frame:
            try:
                # Pack after drawing actions frame
                parent = self.aquarium_selector_frame.master
                # Anchor on the drawing-actions frame itself. Matching its
                # displayed text used to work only in Portuguese.
                anchor = getattr(self, "drawing_actions_frame", None)
                if anchor is not None and anchor.master is parent:
                    self.aquarium_selector_frame.pack(fill="x", pady=5, padx=5, after=anchor)
                    return
                # Fallback - just pack
                self.aquarium_selector_frame.pack(fill="x", pady=5, padx=5)
            except Exception:
                self.aquarium_selector_frame.pack(fill="x", pady=5, padx=5)

    def hide_aquarium_selector(self) -> None:
        """Hide the aquarium selector frame."""
        if self.aquarium_selector_frame:
            self.aquarium_selector_frame.pack_forget()

    def get_active_aquarium_id(self) -> int:
        """Get the currently selected aquarium ID.

        Returns:
            Aquarium ID (0 for aquarium 1, 1 for aquarium 2).
        """
        return self.active_aquarium_var.get()

    def set_active_aquarium(self, aquarium_id: int) -> None:
        """Set the active aquarium programmatically.

        Args:
            aquarium_id: Aquarium ID (0 or 1).
        """
        aquarium_id = max(0, min(1, aquarium_id))  # Clamp to 0-1
        self.active_aquarium_var.set(aquarium_id)
        log.debug("zone_controls.active_aquarium_set", aquarium_id=aquarium_id)

    def update_aquarium_count(self, count: int) -> None:
        """Update UI based on the number of aquariums.

        Reutiliza ``show_aquarium_selector``/``hide_aquarium_selector`` (a mesma
        lógica robusta de ``set_aquarium_count``), que ancoram o
        ``pack(after=...)`` com fallback e ``try/except``. Isso evita o
        ``TclError: window "..." isn't packed`` que ocorria quando o primeiro
        filho de ``drawing_actions_parent`` ainda não estava empacotado — falha
        que abortava ``on_multi_auto_detect_success`` antes do redraw do
        polígono no fluxo de vídeo único.
        """
        log.info("zone_controls.update_aquarium_count", count=count)
        self.aquarium_count_var.set(count)

        if count >= 2:
            self.show_aquarium_selector()
        else:
            self.hide_aquarium_selector()
