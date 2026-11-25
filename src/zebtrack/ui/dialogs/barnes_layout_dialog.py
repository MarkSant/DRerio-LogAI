"""Barnes arena assistant (#633): "define the table + click the escape hole" → ROIs.

The dialog shows the frame the Zones tab shows (a video frame or the live camera
snapshot) and walks the researcher through CONTRACTS §4:

1. the table ellipse — from the arena auto-detection, or from five or more clicks
   on the rim;
2. a click on the escape hole;
3. a live preview, snapped to the dark holes of a background where the rat and
   the experimenter vanished;
4. adjustments — drag a hole, move the escape hole one hole either way;
5. the trial type of this video (``training`` / ``probe``);
6. Apply, for this video, and optionally for other videos of the project.

Everything geometric lives in ``core/detection/barnes_geometry.py``; this module
only collects clicks, draws, and publishes ``ZONE_BARNES_LAYOUT_APPLY`` (one per
video), which ``MultiAquariumCoordinator`` turns into zones. Coordinates are RAW
pixels of the frame shown: the dialog's canvas scales the frame for display and
converts every click back (``_canvas_to_video``) the same way
``CanvasManager._canvas_to_video`` does for the Zones tab.

Slow work (reading ~30 frames of a video, the YOLO table detection) runs on a
daemon worker; results come back to Tk with ``after(0, ...)``. The runner is
injectable so tests stay synchronous.
"""

from __future__ import annotations

import math
import os
import queue
import threading
import tkinter as tk
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any, TypeVar

import numpy as np
import structlog
from PIL import Image, ImageTk

from zebtrack.analysis.protocols.barnes.contract import (
    QUADRANT_ROI,
    BarnesEllipse,
    BarnesLayout,
    BarnesParams,
    TrialType,
)
from zebtrack.core.detection import barnes_geometry as geometry
from zebtrack.i18n import _
from zebtrack.ui.event_bus_v2 import BarnesLayoutApplyPayload, EventBusV2, UIEvents

__all__ = [
    "AssistantMode",
    "BarnesAssistantInputs",
    "BarnesLayoutDialog",
    "OtherVideo",
    "OtherVideosChoice",
    "OtherVideosDialog",
]

log = structlog.get_logger()

T = TypeVar("T")
Point = tuple[float, float]
Runner = Callable[[Callable[[], Any], Callable[[Any], None]], None]

#: Largest canvas the frame is scaled into (small frames are enlarged up to 2x).
MAX_CANVAS_WIDTH = 900
MAX_CANVAS_HEIGHT = 620
MAX_UPSCALE = 2.0
#: How often the Tk thread looks for a worker's result (ms).
RESULT_POLL_MS = 50
#: A press closer than this (video px, at least) to a hole centre grabs the hole.
GRAB_RADIUS_PX = 8.0

_TABLE_COLOR = "#00b7ff"
_QUADRANT_COLOR = "#ffc800"
_TARGET_COLOR = "#ff2020"
_SNAPPED_COLOR = "#20d020"
_PREDICTED_COLOR = "#ff9900"
_MANUAL_COLOR = "#4080ff"
_RIM_COLOR = "#ff00ff"


class AssistantMode(StrEnum):
    """What a click on the canvas means."""

    #: Clicks are rim points of the table.
    RIM = "rim"
    #: The next click is the escape hole.
    TARGET = "target"
    #: A layout exists: presses drag holes.
    ADJUST = "adjust"


@dataclass(frozen=True, slots=True)
class OtherVideo:
    """Another video of the project. ``path`` is its identity; ``label`` is display only."""

    path: str
    label: str


@dataclass(slots=True)
class BarnesAssistantInputs:
    """Everything the assistant needs, resolved by its opener (EventDispatcher).

    Attributes:
        video_path: Where the zones are written (video, or live reference snapshot).
        frame: The frame the Zones tab shows (RGB), in raw pixels.
        params: The project's Barnes parameters.
        background_source: File to build the snapping background from (the video,
            or the snapshot); ``None`` snaps on ``frame`` itself.
        initial_table: Table ellipse to start from (an existing arena outline).
        cached_layout: The video's cached layout (``metadata["barnes_layout"]``).
        trial_type: The video's declared trial type, if any.
        trial_type_editable: ``False`` when the video has no project entry to hold
            a per-video input (the project default then applies).
        other_videos: The project's other videos, for "Apply to other videos".
        can_detect_table: Offer the arena auto-detection (pre-recorded videos only).
    """

    video_path: str
    frame: Image.Image
    params: BarnesParams
    background_source: str | None = None
    initial_table: BarnesEllipse | None = None
    cached_layout: BarnesLayout | None = None
    trial_type: str | None = None
    trial_type_editable: bool = True
    other_videos: tuple[OtherVideo, ...] = ()
    can_detect_table: bool = False


@dataclass(frozen=True, slots=True)
class OtherVideosChoice:
    """What "Apply to other videos" was asked to do.

    Attributes:
        paths: Selected videos, by path.
        same_escape_hole: ``True``: copy the layout and re-snap it on each video;
            ``False``: show each video and ask for its escape hole.
        trial_type: Trial type written to every selected video (``None`` = keep).
    """

    paths: tuple[str, ...]
    same_escape_hole: bool
    trial_type: str | None


@dataclass
class _QueueState:
    paths: list[str] = field(default_factory=list)
    trial_type: str | None = None
    total: int = 0


def _gray_to_image(gray: np.ndarray) -> Image.Image:
    return Image.fromarray(gray).convert("RGB")


class BarnesLayoutDialog(tk.Toplevel):
    """Modal Barnes arena assistant. See the module docstring."""

    def __init__(
        self,
        parent: tk.Misc,
        event_bus: EventBusV2,
        inputs: BarnesAssistantInputs,
        *,
        detect_table: Callable[[str], Sequence[Point] | None] | None = None,
        load_background: Callable[[str], np.ndarray | None] = geometry.read_background,
        run_async: Runner | None = None,
    ) -> None:
        super().__init__(parent)
        self._event_bus = event_bus
        self._inputs = inputs
        self._params = inputs.params
        self._detect_table = detect_table if inputs.can_detect_table else None
        self._load_background = load_background
        self._run_async: Runner = run_async or self._thread_runner

        self.video_path = inputs.video_path
        self._frame = inputs.frame.convert("RGB")
        self._background: np.ndarray | None = None
        self._table: BarnesEllipse | None = inputs.initial_table
        self._rim_points: list[Point] = []
        self._click: Point | None = None
        self._model: geometry.RingModel | None = None
        self._manual: dict[int, Point] = {}
        self._layout: BarnesLayout | None = None
        self._drag_k: int | None = None
        self._drag_point: Point | None = None
        self._queue = _QueueState()
        self._busy = False
        self._results: queue.Queue[tuple[Callable[[Any], None], Any]] = queue.Queue()
        self._polling = False
        self._outstanding = 0
        self._photo: ImageTk.PhotoImage | None = None
        self._scale = 1.0
        self.applied_paths: list[str] = []

        self.trial_type_var = tk.StringVar(
            value=inputs.trial_type or self._params.default_trial_type.value
        )

        self.title(_("Barnes assistant"))
        self.transient(parent.winfo_toplevel())
        self.protocol("WM_DELETE_WINDOW", self.cancel)
        self.bind("<Escape>", lambda _e: self.cancel())
        self._build()
        self._show_frame(self._frame)

        cached = inputs.cached_layout
        if cached is not None and cached.n_holes == self._params.n_holes:
            self._table = cached.table
            self._model = geometry.ring_model_of_layout(cached)
            self._layout = cached
            self.mode = AssistantMode.ADJUST
        elif self._table is not None:
            self.mode = AssistantMode.TARGET
        else:
            self.mode = AssistantMode.RIM
        self._refresh()
        self._start_background(inputs.background_source)
        self.grab_set()
        log.info(
            "barnes_layout_dialog.opened",
            video=Path(self.video_path).name,
            mode=self.mode.value,
            n_holes=self._params.n_holes,
            cached=cached is not None,
        )

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def _build(self) -> None:
        body = ttk.Frame(self, padding=8)
        body.pack(fill="both", expand=True)

        self.canvas = tk.Canvas(body, highlightthickness=0, background="black", cursor="crosshair")
        self.canvas.grid(row=0, column=0, sticky="nw")
        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_motion)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)

        side = ttk.Frame(body, padding=(10, 0, 0, 0))
        side.grid(row=0, column=1, sticky="ns")

        table_box = ttk.LabelFrame(side, text=_("1. Table"), padding=6)
        table_box.pack(fill="x", pady=(0, 6))
        self.detect_button = ttk.Button(
            table_box, text=_("Detect table (auto)"), command=self.detect_table
        )
        self.detect_button.pack(fill="x", pady=2)
        if self._detect_table is None:
            self.detect_button.state(["disabled"])
        self.rim_button = ttk.Button(
            table_box, text=_("Click the rim (5+ points)"), command=self.start_rim
        )
        self.rim_button.pack(fill="x", pady=2)
        self.fit_button = ttk.Button(table_box, text=_("Fit ellipse"), command=self.fit_rim)
        self.fit_button.pack(fill="x", pady=2)

        hole_box = ttk.LabelFrame(side, text=_("2. Escape hole"), padding=6)
        hole_box.pack(fill="x", pady=6)
        self.target_button = ttk.Button(
            hole_box, text=_("Click the escape hole"), command=self.start_target
        )
        self.target_button.pack(fill="x", pady=2)

        adjust_box = ttk.LabelFrame(side, text=_("3. Check and adjust"), padding=6)
        adjust_box.pack(fill="x", pady=6)
        rotate_row = ttk.Frame(adjust_box)
        rotate_row.pack(fill="x")
        self.rotate_ccw_button = ttk.Button(
            rotate_row, text=_("◀ 1 hole"), command=lambda: self.rotate(-1)
        )
        self.rotate_ccw_button.pack(side="left", expand=True, fill="x", padx=(0, 2))
        self.rotate_cw_button = ttk.Button(
            rotate_row, text=_("1 hole ▶"), command=lambda: self.rotate(1)
        )
        self.rotate_cw_button.pack(side="left", expand=True, fill="x", padx=(2, 0))
        self.reset_button = ttk.Button(
            adjust_box, text=_("Undo hole drags"), command=self.reset_adjustments
        )
        self.reset_button.pack(fill="x", pady=(4, 2))
        self.quality_label = ttk.Label(adjust_box, text="", wraplength=260, justify="left")
        self.quality_label.pack(fill="x", pady=(4, 0))
        self.warning_label = ttk.Label(
            adjust_box, text="", wraplength=260, justify="left", foreground="#b05000"
        )
        self.warning_label.pack(fill="x")

        trial_box = ttk.LabelFrame(side, text=_("4. Trial type of this video"), padding=6)
        trial_box.pack(fill="x", pady=6)
        self.training_radio = ttk.Radiobutton(
            trial_box,
            text=_("Training"),
            variable=self.trial_type_var,
            value=TrialType.TRAINING.value,
        )
        self.training_radio.pack(anchor="w")
        self.probe_radio = ttk.Radiobutton(
            trial_box, text=_("Probe"), variable=self.trial_type_var, value=TrialType.PROBE.value
        )
        self.probe_radio.pack(anchor="w")
        if not self._inputs.trial_type_editable:
            self.training_radio.state(["disabled"])
            self.probe_radio.state(["disabled"])
            ttk.Label(
                trial_box,
                text=_(
                    "This frame has no project video: the project's default trial type applies."
                ),
                wraplength=260,
                foreground="gray",
            ).pack(anchor="w")

        actions = ttk.Frame(side)
        actions.pack(fill="x", pady=(10, 0))
        self.apply_button = ttk.Button(
            actions, text=_("Apply"), command=self.apply_layout, style="Accent.TButton"
        )
        self.apply_button.pack(fill="x", pady=2)
        self.apply_others_button = ttk.Button(
            actions, text=_("Apply to other videos…"), command=self.apply_to_other_videos
        )
        self.apply_others_button.pack(fill="x", pady=2)
        if not self._inputs.other_videos:
            self.apply_others_button.state(["disabled"])
        ttk.Button(actions, text=_("Cancel"), command=self.cancel).pack(fill="x", pady=2)

        self.status_label = ttk.Label(body, text="", wraplength=MAX_CANVAS_WIDTH, justify="left")
        self.status_label.grid(row=1, column=0, columnspan=2, sticky="we", pady=(6, 0))

    # ------------------------------------------------------------------
    # Coordinates and drawing
    # ------------------------------------------------------------------

    def _show_frame(self, image: Image.Image) -> None:
        width, height = image.size
        self._scale = min(MAX_CANVAS_WIDTH / width, MAX_CANVAS_HEIGHT / height, MAX_UPSCALE)
        shown = image.resize(
            (max(1, round(width * self._scale)), max(1, round(height * self._scale))),
            Image.Resampling.LANCZOS,
        )
        self._photo = ImageTk.PhotoImage(shown, master=self)
        self.canvas.configure(width=shown.width, height=shown.height)
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, image=self._photo, anchor="nw", tags=("frame",))

    def _canvas_to_video(self, canvas_x: float, canvas_y: float) -> Point:
        """Canvas → raw frame pixels (the frame is drawn at the origin, uniformly scaled)."""
        return (float(canvas_x) / self._scale, float(canvas_y) / self._scale)

    def _video_to_canvas(self, video_x: float, video_y: float) -> Point:
        return (float(video_x) * self._scale, float(video_y) * self._scale)

    def _draw_polygon(self, points: Sequence[Point], color: str, *, dash: tuple = ()) -> None:
        flat: list[float] = []
        for x, y in points:
            flat.extend(self._video_to_canvas(x, y))
        if len(flat) >= 6:
            self.canvas.create_polygon(
                *flat, outline=color, fill="", width=2, dash=dash, tags=("overlay",)
            )

    def _redraw(self) -> None:
        self.canvas.delete("overlay")
        for x, y in self._rim_points:
            cx, cy = self._video_to_canvas(x, y)
            self.canvas.create_oval(
                cx - 3, cy - 3, cx + 3, cy + 3, fill=_RIM_COLOR, outline="", tags=("overlay",)
            )
        if self._table is not None:
            self._draw_polygon(geometry.ellipse_polygon(self._table, 96), _TABLE_COLOR)
        layout = self._layout
        if layout is None:
            return
        try:
            _arena, rois = geometry.build_barnes_rois(layout, self._params)
        except geometry.BarnesGeometryError:
            rois = []
        quadrant = dict(rois).get(QUADRANT_ROI)
        if quadrant:
            self._draw_polygon(quadrant, _QUADRANT_COLOR, dash=(4, 3))
        radii = geometry.hole_roi_radii(layout, self._params)
        for hole in layout.holes:
            k = (hole.abs_index - layout.target_abs_index) % layout.n_holes
            if self._drag_k == k and self._drag_point is not None:
                center = self._drag_point
            else:
                center = hole.center_px
            if hole.offset == 0:
                color = _TARGET_COLOR
            elif k in self._manual:
                color = _MANUAL_COLOR
            elif hole.snapped:
                color = _SNAPPED_COLOR
            else:
                color = _PREDICTED_COLOR
            cx, cy = self._video_to_canvas(*center)
            radius = max(radii[hole.abs_index], 2.0) * self._scale
            self.canvas.create_oval(
                cx - radius,
                cy - radius,
                cx + radius,
                cy + radius,
                outline=color,
                width=2,
                tags=("overlay", "hole"),
            )
            self.canvas.create_text(
                cx,
                cy - radius - 7,
                text=f"{hole.offset:+d}" if hole.offset else "0",
                fill=color,
                font=("TkDefaultFont", 8, "bold"),
                tags=("overlay",),
            )

    def _refresh(self) -> None:
        """Redraw and bring every button and label in line with the state."""
        self._redraw()
        has_layout = self._layout is not None
        self._set_enabled(self.fit_button, len(self._rim_points) >= 5 and not self._busy)
        self._set_enabled(self.target_button, self._table is not None and not self._busy)
        self._set_enabled(self.rim_button, not self._busy)
        self._set_enabled(self.detect_button, self._detect_table is not None and not self._busy)
        for button in (self.rotate_ccw_button, self.rotate_cw_button, self.apply_button):
            self._set_enabled(button, has_layout and not self._busy)
        self._set_enabled(self.reset_button, bool(self._manual) and not self._busy)
        self._set_enabled(
            self.apply_others_button,
            has_layout
            and bool(self._inputs.other_videos)
            and not self._busy
            and not self._queue.paths,
        )
        self._refresh_quality()
        self._refresh_status()

    @staticmethod
    def _set_enabled(widget: ttk.Widget, enabled: bool) -> None:
        widget.state(["!disabled"] if enabled else ["disabled"])

    def _refresh_quality(self) -> None:
        layout = self._layout
        if layout is None:
            self.quality_label.configure(text="")
            self.warning_label.configure(text="")
            return
        quality = geometry.layout_quality(layout)
        if quality.mean_residual_px is None or quality.max_residual_px is None:
            text = _("{total} holes placed without snapping (no dark hole found).").format(
                total=quality.n_holes
            )
        else:
            text = _(
                "{snapped}/{total} holes snapped · mean residual {mean:.1f} px "
                "(max {maximum:.1f} px)"
            ).format(
                snapped=quality.snapped,
                total=quality.n_holes,
                mean=quality.mean_residual_px,
                maximum=quality.max_residual_px,
            )
        self.quality_label.configure(text=text)
        if quality.suspicious:
            self.warning_label.configure(
                text=_(
                    "Some holes were not found or sit far from an evenly spaced ring. "
                    "Check the escape-hole click and the number of holes ({n})."
                ).format(n=quality.n_holes)
            )
        else:
            self.warning_label.configure(text="")

    def _refresh_status(self, override: str | None = None) -> None:
        if override is not None:
            text = override
        elif self._busy:
            text = _("Working…")
        elif self.mode is AssistantMode.RIM:
            text = _(
                "Click at least 5 points on the table's rim, then press “Fit ellipse” "
                "(or detect the table automatically)."
            )
        elif self.mode is AssistantMode.TARGET:
            text = _("Click the centre of the escape hole.")
        else:
            text = _(
                "Drag a hole to move it; “◀ 1 hole” / “1 hole ▶” move the escape hole. "
                "Red = escape hole, green = snapped, orange = not found, blue = moved."
            )
        if self._queue.total:
            done = self._queue.total - len(self._queue.paths)
            text = (
                _("Video {index} of {total}: {name}").format(
                    index=done, total=self._queue.total, name=Path(self.video_path).name
                )
                + "\n"
                + text
            )
        self.status_label.configure(text=text)

    # ------------------------------------------------------------------
    # Background and async work
    # ------------------------------------------------------------------

    def _thread_runner(self, work: Callable[[], Any], done: Callable[[Any], None]) -> None:
        """Run ``work`` on a daemon thread; ``done(result)`` runs on the Tk thread.

        The worker never touches Tk: it hands its result to a queue that the Tk
        thread polls with ``after``. ``None`` is delivered when ``work`` raised.
        """

        def target() -> None:
            try:
                result = work()
            # except Exception justified: a worker must always hand control back to Tk.
            except Exception as exc:
                log.error("barnes_layout_dialog.worker_failed", error=str(exc), exc_info=True)
                result = None
            self._results.put((done, result))

        self._outstanding += 1
        threading.Thread(target=target, daemon=True, name="barnes-assistant").start()
        self._schedule_poll()

    def _schedule_poll(self) -> None:
        if not self._polling:
            self._polling = True
            self.after(RESULT_POLL_MS, self._poll_results)

    def _poll_results(self) -> None:
        self._polling = False
        if not self.winfo_exists():
            return
        while True:
            try:
                done, result = self._results.get_nowait()
            except queue.Empty:
                break
            self._outstanding -= 1
            done(result)
            if not self.winfo_exists():
                return
        if self._outstanding > 0:
            self._schedule_poll()

    def _start_background(self, source: str | None) -> None:
        if source is None:
            self._set_background(np.asarray(self._frame.convert("L")))
            return
        self._busy = True
        self._refresh()
        self._run_async(lambda: self._load_background(source), self._on_background_ready)

    def _on_background_ready(self, background: np.ndarray | None) -> None:
        self._busy = False
        if background is None:
            log.warning("barnes_layout_dialog.background_unavailable", video=self.video_path)
            background = np.asarray(self._frame.convert("L"))
        self._set_background(background)

    def _set_background(self, background: np.ndarray) -> None:
        self._background = background
        # Only a layout placed from a click BEFORE the background was ready is
        # re-placed: a cached layout keeps the holes the user dragged last time.
        if self._click is not None and not self._manual and self._table is not None:
            self._place_from_click(self._click)
            return
        self._refresh()

    # ------------------------------------------------------------------
    # Steps
    # ------------------------------------------------------------------

    def detect_table(self) -> None:
        """Step 1 (auto): the arena detection's outline → table ellipse.

        Runs on the Tk thread, like the Zones tab's own "Detect" button: the
        existing detection path publishes UI events whose handlers assume it.
        The status line is painted first so the wait is not a frozen window.
        """
        detector = self._detect_table
        if detector is None or self._busy:
            return
        self._busy = True
        self._refresh()
        video = self.video_path

        def run() -> None:
            try:
                polygon = detector(video)
            # except Exception justified: YOLO + cv2; the dialog must stay usable.
            except Exception as exc:
                log.error("barnes_layout_dialog.detect_failed", error=str(exc), exc_info=True)
                polygon = None
            if self.winfo_exists():
                self._on_table_detected(polygon)

        self.after(10, run)

    def _on_table_detected(self, polygon: Sequence[Point] | None) -> None:
        self._busy = False
        if not polygon:
            self.mode = AssistantMode.RIM
            self._refresh()
            self._refresh_status(_("The table was not detected: click its rim instead."))
            return
        try:
            table = geometry.ellipse_from_polygon([(float(x), float(y)) for x, y in polygon])
        except geometry.BarnesGeometryError as exc:
            log.warning("barnes_layout_dialog.table_unusable", error=str(exc))
            self.mode = AssistantMode.RIM
            self._refresh()
            self._refresh_status(_("The detected outline is not usable: click the rim instead."))
            return
        self.set_table(table)

    def start_rim(self) -> None:
        """Step 1 (manual): collect rim clicks."""
        self._rim_points = []
        self.mode = AssistantMode.RIM
        self._refresh()

    def fit_rim(self) -> None:
        """Fit the table ellipse through the rim clicks."""
        try:
            table = geometry.ellipse_from_points(self._rim_points)
        except geometry.BarnesGeometryError as exc:
            log.warning("barnes_layout_dialog.rim_fit_failed", error=str(exc))
            self._refresh_status(
                _("Could not fit an ellipse to these points: {error}").format(error=exc)
            )
            return
        self._rim_points = []
        self.set_table(table)

    def set_table(self, table: BarnesEllipse) -> None:
        """Use ``table``; an existing escape-hole click is placed again on it."""
        self._table = table
        self._manual = {}
        if self._click is not None:
            self._place_from_click(self._click)
            return
        self._layout = None
        self._model = None
        self.mode = AssistantMode.TARGET
        self._refresh()

    def start_target(self) -> None:
        """Step 2: the next click is the escape hole."""
        if self._table is None:
            return
        self.mode = AssistantMode.TARGET
        self._refresh()

    def handle_click(self, x: float, y: float) -> None:
        """A click at raw frame pixel ``(x, y)`` (rim point or escape hole)."""
        if self._busy:
            return
        if self.mode is AssistantMode.RIM:
            self._rim_points.append((x, y))
            self._refresh()
        elif self.mode is AssistantMode.TARGET:
            self._manual = {}
            self._place_from_click((x, y))

    def _place_from_click(self, click: Point) -> None:
        if self._table is None:
            return
        try:
            layout, model = geometry.layout_from_click(
                self._table, click, self._params.n_holes, self._background
            )
        except geometry.BarnesGeometryError as exc:
            log.info("barnes_layout_dialog.click_refused", error=str(exc))
            self._refresh()
            self._refresh_status(str(exc))
            return
        self._click = click
        self._layout = layout
        self._model = model
        self.mode = AssistantMode.ADJUST
        self._refresh()

    def _relayout(self) -> None:
        if self._table is None or self._model is None:
            return
        try:
            self._layout = geometry.relayout(
                self._table, self._model, self._background, self._manual
            )
        except geometry.BarnesGeometryError as exc:
            log.warning("barnes_layout_dialog.relayout_failed", error=str(exc))
        self._refresh()

    def rotate(self, holes: int) -> None:
        """Step 3: move the escape hole ``holes`` holes clockwise (negative = back)."""
        if self._model is None:
            return
        self._model = self._model.rotated(holes * self._model.step)
        self._manual = {}
        self._click = None
        self._relayout()

    def reset_adjustments(self) -> None:
        """Forget every dragged hole."""
        self._manual = {}
        self._relayout()

    # -- dragging ----------------------------------------------------------

    def _hole_k_near(self, point: Point) -> int | None:
        layout = self._layout
        if layout is None:
            return None
        best: tuple[float, int] | None = None
        for hole in layout.holes:
            distance = math.hypot(hole.center_px[0] - point[0], hole.center_px[1] - point[1])
            reach = max(GRAB_RADIUS_PX, 1.5 * hole.radius_px)
            if distance <= reach and (best is None or distance < best[0]):
                best = (distance, (hole.abs_index - layout.target_abs_index) % layout.n_holes)
        return None if best is None else best[1]

    def begin_drag(self, x: float, y: float) -> bool:
        """Grab the hole under raw pixel ``(x, y)``; ``False`` when there is none."""
        if self.mode is not AssistantMode.ADJUST or self._busy:
            return False
        k = self._hole_k_near((x, y))
        if k is None:
            return False
        self._drag_k = k
        self._drag_point = (x, y)
        return True

    def drag_to(self, x: float, y: float) -> None:
        if self._drag_k is None:
            return
        self._drag_point = (x, y)
        self._redraw()

    def end_drag(self, x: float, y: float) -> None:
        if self._drag_k is None:
            return
        self._manual[self._drag_k] = (x, y)
        self._drag_k = None
        self._drag_point = None
        self._relayout()

    def _on_press(self, event: tk.Event) -> None:
        x, y = self._canvas_to_video(event.x, event.y)
        if not self.begin_drag(x, y):
            self.handle_click(x, y)

    def _on_motion(self, event: tk.Event) -> None:
        self.drag_to(*self._canvas_to_video(event.x, event.y))

    def _on_release(self, event: tk.Event) -> None:
        self.end_drag(*self._canvas_to_video(event.x, event.y))

    # ------------------------------------------------------------------
    # Apply
    # ------------------------------------------------------------------

    def _payload_for(
        self, video_path: Path | str, layout: BarnesLayout, trial_type: str | None
    ) -> BarnesLayoutApplyPayload:
        arena, rois = geometry.build_barnes_rois(layout, self._params)
        return BarnesLayoutApplyPayload(
            video_path=os.fspath(video_path),
            arena_polygon=tuple(arena),
            rois=tuple((name, tuple(points)) for name, points in rois),
            layout_metadata=layout.to_metadata(),
            trial_type=trial_type,
        )

    def _current_trial_type(self) -> str | None:
        if self._queue.total:
            return self._queue.trial_type or self.trial_type_var.get()
        return self.trial_type_var.get() if self._inputs.trial_type_editable else None

    def apply_layout(self) -> None:
        """Step 6: write this video's zones (then go to the next queued video)."""
        layout = self._layout
        if layout is None or self._busy:
            return
        if geometry.layout_quality(layout).suspicious and not messagebox.askyesno(
            _("Barnes assistant"),
            _("Some holes were not found or look misplaced. Apply this layout anyway?"),
            parent=self,
        ):
            return
        try:
            payload = self._payload_for(self.video_path, layout, self._current_trial_type())
        except geometry.BarnesGeometryError as exc:
            messagebox.showerror(_("Barnes assistant"), str(exc), parent=self)
            return
        self._event_bus.publish(UIEvents.ZONE_BARNES_LAYOUT_APPLY, payload)
        self.applied_paths.append(self.video_path)
        log.info(
            "barnes_layout_dialog.applied",
            video=Path(self.video_path).name,
            trial_type=payload.trial_type,
            source=layout.source,
        )
        if self._queue.paths:
            self._next_queued_video()
            return
        self.destroy()

    def cancel(self) -> None:
        """Close without writing anything more."""
        log.info("barnes_layout_dialog.closed", applied=len(self.applied_paths))
        self.destroy()

    # -- other videos -----------------------------------------------------

    def choose_other_videos(self) -> OtherVideosChoice | None:
        """Ask which videos and how (overridable in tests)."""
        dialog = OtherVideosDialog(
            self,
            self._inputs.other_videos,
            default_trial_type=self.trial_type_var.get(),
        )
        self.wait_window(dialog)
        return dialog.result

    def apply_to_other_videos(self) -> None:
        """Copy this layout to other videos (re-snapped) or ask for each escape hole."""
        if self._layout is None or self._model is None or self._table is None or self._busy:
            return
        choice = self.choose_other_videos()
        if choice is None or not choice.paths:
            return
        if choice.same_escape_hole:
            self._apply_same_escape_hole(choice)
        else:
            self._queue = _QueueState(
                paths=list(choice.paths), trial_type=choice.trial_type, total=len(choice.paths)
            )
            self._next_queued_video()

    def _apply_same_escape_hole(self, choice: OtherVideosChoice) -> None:
        table = self._table
        model = self._model
        if table is None or model is None:
            return
        loader = self._load_background
        params = self._params

        def work() -> list[tuple[str, BarnesLayout | None]]:
            results: list[tuple[str, BarnesLayout | None]] = []
            for path in choice.paths:
                background = loader(path)
                if background is None:
                    results.append((path, None))
                    continue
                refined, snaps = geometry.snap_layout(background, model, table)
                layout = geometry.assemble_layout(table, refined, snaps)
                try:
                    geometry.build_barnes_rois(layout, params)
                except geometry.BarnesGeometryError:
                    results.append((path, None))
                    continue
                results.append((path, layout))
            return results

        self._busy = True
        self._refresh()
        self._run_async(work, lambda results: self._on_others_ready(choice, results))

    def _on_others_ready(
        self, choice: OtherVideosChoice, results: list[tuple[str, BarnesLayout | None]] | None
    ) -> None:
        self._busy = False
        written: list[str] = []
        failed: list[str] = list(choice.paths) if results is None else []
        suspicious: list[str] = []
        for path, layout in results or []:
            if layout is None:
                failed.append(path)
                continue
            if geometry.layout_quality(layout).suspicious:
                suspicious.append(path)
            self._event_bus.publish(
                UIEvents.ZONE_BARNES_LAYOUT_APPLY,
                self._payload_for(path, layout, choice.trial_type),
            )
            written.append(path)
        self.applied_paths.extend(written)
        log.info(
            "barnes_layout_dialog.others_applied",
            written=len(written),
            failed=len(failed),
            suspicious=len(suspicious),
        )
        lines = [_("Layout applied to {count} video(s).").format(count=len(written))]
        if suspicious:
            lines.append(
                _("Check these, some holes were not found: {names}").format(
                    names=", ".join(Path(p).name for p in suspicious)
                )
            )
        if failed:
            lines.append(
                _("Could not read: {names}").format(names=", ".join(Path(p).name for p in failed))
            )
        messagebox.showinfo(_("Barnes assistant"), "\n".join(lines), parent=self)
        self._refresh()

    def _next_queued_video(self) -> None:
        path = self._queue.paths.pop(0)
        self.video_path = path
        self._layout = None
        self._model = None
        self._click = None
        self._manual = {}
        self._busy = True
        self.mode = AssistantMode.TARGET
        if self._queue.trial_type:
            self.trial_type_var.set(self._queue.trial_type)
        self._refresh()
        loader = self._load_background
        self._run_async(lambda: loader(path), self._on_queued_background)

    def _on_queued_background(self, background: np.ndarray | None) -> None:
        self._busy = False
        if background is None:
            messagebox.showwarning(
                _("Barnes assistant"),
                _("Could not read {name}; it is skipped.").format(name=Path(self.video_path).name),
                parent=self,
            )
            if self._queue.paths:
                self._next_queued_video()
            else:
                self.destroy()
            return
        self._show_frame(_gray_to_image(background))
        self._background = background
        self._refresh()


class OtherVideosDialog(tk.Toplevel):
    """Pick the videos the layout goes to, and how. ``result`` is ``None`` on cancel."""

    def __init__(
        self,
        parent: tk.Misc,
        videos: Sequence[OtherVideo],
        *,
        default_trial_type: str = TrialType.TRAINING.value,
    ) -> None:
        super().__init__(parent)
        self.result: OtherVideosChoice | None = None
        self._videos = list(videos)
        self.title(_("Apply to other videos"))
        self.transient(parent.winfo_toplevel())
        self.protocol("WM_DELETE_WINDOW", self.cancel)

        body = ttk.Frame(self, padding=10)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text=_("Videos (same camera, same table):")).pack(anchor="w")
        self.video_list = tk.Listbox(body, selectmode="extended", height=12, width=70)
        for video in self._videos:
            self.video_list.insert("end", video.label)
        self.video_list.pack(fill="both", expand=True, pady=4)
        ttk.Button(body, text=_("Select all"), command=self.select_all).pack(anchor="w")

        self.same_hole_var = tk.BooleanVar(value=True)
        ttk.Radiobutton(
            body,
            text=_("Same escape hole: copy the layout and re-snap it on each video"),
            variable=self.same_hole_var,
            value=True,
        ).pack(anchor="w", pady=(8, 0))
        ttk.Radiobutton(
            body,
            text=_("Different escape hole: show each video and click its escape hole"),
            variable=self.same_hole_var,
            value=False,
        ).pack(anchor="w")

        self.trial_type_var = tk.StringVar(value=default_trial_type)
        trial_row = ttk.Frame(body)
        trial_row.pack(anchor="w", pady=(8, 0))
        ttk.Label(trial_row, text=_("Trial type:")).pack(side="left")
        for value, label in (
            (TrialType.TRAINING.value, _("Training")),
            (TrialType.PROBE.value, _("Probe")),
            ("", _("Keep each video's")),
        ):
            ttk.Radiobutton(trial_row, text=label, variable=self.trial_type_var, value=value).pack(
                side="left", padx=4
            )

        buttons = ttk.Frame(body)
        buttons.pack(fill="x", pady=(10, 0))
        ttk.Button(buttons, text=_("Cancel"), command=self.cancel).pack(side="right")
        ttk.Button(buttons, text=_("Apply"), command=self.confirm).pack(side="right", padx=4)
        self.grab_set()

    def select_all(self) -> None:
        self.video_list.selection_set(0, "end")

    def confirm(self) -> None:
        indices = self.video_list.curselection()
        trial = self.trial_type_var.get() or None
        self.result = OtherVideosChoice(
            paths=tuple(self._videos[int(i)].path for i in indices),
            same_escape_hole=bool(self.same_hole_var.get()),
            trial_type=trial,
        )
        self.destroy()

    def cancel(self) -> None:
        self.result = None
        self.destroy()
