"""Deterministic in-process driver for the REAL pre-recorded single-video pipeline.

Why this exists
---------------
``tests/test_integration.py`` composes ``Detector`` + ``Recorder`` +
``AnalysisService`` by hand and feeds them a ``MagicMock`` as ``Settings``. That
shape can prove the pipeline still runs, but it can prove nothing about the
NUMBERS, and a mocked ``Settings`` is structurally incapable of detecting the
defect class that cost a full re-test round in v6.1.0: an ad-hoc dialog writing
into the shared ``Settings`` object and a later flow reading the polluted value
(see ``core.services.project_settings_snapshot`` and PR #524).

This module drives the production path instead — ``_WorkerProcess`` is the loop
that both the single-video and the project-batch flows actually execute — with a
REAL ``Settings`` built from ``config.yaml``. Every threshold that matters is
therefore read from the settings object, so a leak changes the output.

``_WorkerProcess`` is a ``multiprocessing.Process`` subclass, but nothing here
starts a process: the methods are called directly in the test process. That is
deliberate. Spawning would put the detector behind a process boundary, and the
deterministic stand-in plugin below could not be injected across it — the child
re-imports the module tree and never runs ``conftest``.

Determinism
-----------
Verified: two independent runs produce byte-identical reports. Three properties
carry it, and all three are load-bearing.

* ``processing_worker`` timestamps frames with ``cap.get(cv2.CAP_PROP_POS_MSEC)``
  — the video's own position, not a wall clock. (The LIVE pipeline stamps a
  processing clock instead, which is why no equivalent golden is possible for a
  live session; see CLAUDE.md § 5.9.)
* ``GoldenDeterministicPlugin`` finds the drawn square with ``cv2.findContours``,
  so no model weights and no inference non-determinism are involved.
* ``load_pristine_settings`` reads ``config.yaml`` ONLY. Passing the real
  ``config.local.yaml`` would make the golden machine-specific — that file holds
  the camera index and serial port and is git-ignored by design.
"""

from __future__ import annotations

import queue as _queue
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import cv2
import numpy as np
import pandas as pd

from zebtrack.analysis.analysis_service import AnalysisService
from zebtrack.analysis.roi_builder import build_rois_from_zone_polygons
from zebtrack.core.detection import Detector
from zebtrack.core.video.processing_worker import WorkerConfig, _WorkerProcess
from zebtrack.plugins.base import DetectorPlugin
from zebtrack.settings import Settings, load_settings

__all__ = [
    "ARENA_POLYGON",
    "BARNES_FPS",
    "BARNES_ID",
    "BARNES_NAMES",
    "BARNES_ROI_NAMES",
    "BARNES_ROLES",
    "BARNES_TOCA",
    "EXPERIMENT_ID",
    "FPS",
    "ROI_LEFT",
    "ROI_NAMES",
    "ROI_RIGHT",
    "TRAJECTORY_COLUMNS",
    "BarnesDeterministicPlugin",
    "BarnesRun",
    "GoldenDeterministicPlugin",
    "PipelineOutcome",
    "load_pristine_settings",
    "normalize_report",
    "run_barnes_pipeline",
    "run_prerecorded_pipeline",
    "write_barnes_video",
    "write_golden_video",
]

WIDTH = 640
HEIGHT = 480
FPS = 10
DURATION_S = 12
EXPERIMENT_ID = "GOLDEN_01"

#: Arena and the two ROIs, in RAW VIDEO PIXELS — the coordinate contract every
#: pipeline in this repo agrees on (CLAUDE.md, "Parquet Schema"). Vertices are
#: tuples because that is what ``build_rois_from_zone_polygons`` consumes; the
#: zone dict handed to the worker converts them back to lists, which is the
#: shape ``ZoneData`` is serialised in.
ARENA_POLYGON: list[tuple[float, float]] = [(40, 40), (600, 40), (600, 440), (40, 440)]
ROI_LEFT: list[tuple[float, float]] = [(40, 40), (320, 40), (320, 440), (40, 440)]
ROI_RIGHT: list[tuple[float, float]] = [(320, 40), (600, 40), (600, 440), (320, 440)]
ROI_NAMES = ["Esquerda", "Direita"]


def _as_vertex_lists(polygon: list[tuple[float, float]]) -> list[list[float]]:
    """Vertices as plain lists, the way zone data is persisted."""
    return [[x, y] for x, y in polygon]


#: The immutable trajectory schema, in order. Mirrors the contract asserted by
#: ``tests/test_recorder.py::test_immutable_schema_unchanged_by_mask_feature``.
TRAJECTORY_COLUMNS = [
    "timestamp",
    "frame",
    "track_id",
    "x1",
    "y1",
    "x2",
    "y2",
    "confidence",
    "uncertainty",
    "bbox_iou",
    "x_center_px",
    "y_center_px",
]


def normalize_report(value: Any) -> Any:
    """Make an analysis report comparable and diff-friendly.

    Two things need taming. Durations arrive as ``pd.Timedelta`` and as pandas
    index objects whose ``repr`` is unreadable in a diff and free to change
    between pandas releases; they become plain seconds. And raw ``==`` on the
    report is not even well defined — it holds numpy arrays, so comparing two
    reports directly raises "truth value of an array is ambiguous".

    Floats are rounded because the last bits of a float64 are not a behavioural
    contract, and treating them as one would turn every unrelated platform
    difference into a false regression.
    """
    if isinstance(value, dict):
        return {str(k): normalize_report(v) for k, v in value.items()}
    if isinstance(value, pd.Timedelta):
        return round(value.total_seconds(), 9)
    if isinstance(value, pd.Index | pd.Series):
        return [normalize_report(v) for v in value.tolist()]
    if isinstance(value, np.ndarray):
        return [normalize_report(v) for v in value.tolist()]
    if isinstance(value, list | tuple):
        return [normalize_report(v) for v in value]
    if isinstance(value, np.generic):
        return normalize_report(value.item())
    if isinstance(value, bool | int | str) or value is None:
        return value
    if isinstance(value, float):
        return round(value, 9)
    return str(value)


def _repo_root() -> Path:
    """Repository root — ``tests/helpers/x.py`` is two levels below it."""
    return Path(__file__).resolve().parents[2]


def subject_center(frame_index: int) -> tuple[int, int]:
    """Centre of the drawn subject at ``frame_index``.

    The trajectory has three regimes on purpose. Each one keeps a different
    golden metric away from its degenerate value, and a degenerate metric is a
    blind spot: an empty ``episodios_congelamento`` list stays empty no matter
    what ``freezing_velocity_threshold`` becomes, so it could never detect that
    field being overwritten.

    ==============  =======================================================
    0.0 - 4.0 s     travel left to right, crossing the ROI boundary
    4.0 - 7.0 s     perfectly still  -> freezing episode, inactivity period
    7.0 - 12.0 s    zig-zag reversing every 0.8 s -> sharp turns
    ==============  =======================================================
    """
    t = frame_index / FPS
    if t < 4.0:
        return int(100 + 100 * t), 150
    if t < 7.0:
        return 500, 150
    leg = (t - 7.0) % 1.6
    swing = leg if leg < 0.8 else 1.6 - leg
    return int(480 - 40 * (t - 7.0)), int(150 + 220 * (swing / 0.8))


def write_golden_video(path: Path) -> None:
    """Write the deterministic fixture video.

    Raises:
        RuntimeError: if no usable codec is present. Callers skip on this — the
            same accommodation ``tests/test_integration.py`` already makes.
    """
    fourcc = cast(Any, cv2).VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(path), fourcc, FPS, (WIDTH, HEIGHT))
    if not writer.isOpened():
        raise RuntimeError(
            f"Failed to open a VideoWriter for {path}; video codecs (mp4v) are unavailable."
        )
    try:
        for i in range(FPS * DURATION_S):
            frame = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)
            cx, cy = subject_center(i)
            cv2.rectangle(frame, (cx - 12, cy - 12), (cx + 12, cy + 12), (255, 255, 255), -1)
            writer.write(frame)
    finally:
        writer.release()

    probe = cv2.VideoCapture(str(path))
    readable = probe.isOpened()
    probe.release()
    if not readable:
        raise RuntimeError(f"{path} was written but cannot be reopened; codec issue.")


class GoldenDeterministicPlugin(DetectorPlugin):
    """Finds the drawn square geometrically. No weights, no inference variance."""

    def __init__(self, model_path: str = ""):
        self.model_path = model_path

    def detect(
        self, frame: np.ndarray, conf_threshold: float | None = None
    ) -> list[tuple[int, int, int, int, float, int | None, int]]:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        contours, _ = cv2.findContours(gray, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return []
        x, y, w, h = cv2.boundingRect(max(contours, key=cv2.contourArea))
        return [(x, y, x + w, y + h, 0.99, 1, 0)]

    @staticmethod
    def get_name() -> str:
        return "GoldenDeterministicPlugin"

    @property
    def model_input_shape(self) -> tuple[int, int]:
        return (WIDTH, HEIGHT)


class _QueueStub:
    """Stands in for the worker's multiprocessing queues.

    A real ``multiprocessing.Queue`` would work, but it starts a feeder thread
    per instance; the worker only ever ``put``s progress here and polls the
    command queue for ``"cancel"``. ``get_nowait`` must raise ``queue.Empty``
    specifically — ``_check_cancellation`` treats ``OSError``/``EOFError``/
    ``ValueError`` as "the parent died" and cancels the run.
    """

    def __init__(self) -> None:
        self.items: list[Any] = []

    def put(self, item: Any) -> None:
        self.items.append(item)

    def get_nowait(self) -> Any:
        raise _queue.Empty

    def get(self, timeout: float | None = None) -> Any:
        raise _queue.Empty

    def empty(self) -> bool:
        return True


def load_pristine_settings() -> Settings:
    """Load ``config.yaml`` with NO local override.

    ``config.local.yaml`` is per-machine and git-ignored (camera index, serial
    port). Merging it would make every golden value depend on whose machine ran
    the test.
    """
    return load_settings(
        default_config_path=_repo_root() / "config.yaml",
        override_config_path=_repo_root() / "__intentionally_absent__.yaml",
    )


@dataclass(frozen=True)
class PipelineOutcome:
    """What one pre-recorded run produced."""

    trajectory: pd.DataFrame
    report: dict[str, Any]
    output_dir: Path
    analysis_parameters: dict[str, Any]


def run_prerecorded_pipeline(
    workdir: Path,
    settings: Settings,
    *,
    video_path: Path | None = None,
) -> PipelineOutcome:
    """Run the real pre-recorded single-video pipeline and return its output.

    Args:
        workdir: scratch directory; the video and the results land under it.
        settings: the ``Settings`` to run with. Callers pass a POLLUTED object
            on purpose in ``test_flow_isolation.py`` — that is the whole point
            of taking it as an argument rather than loading it here.
        video_path: reuse an already-written fixture video instead of writing a
            new one.

    Returns:
        The trajectory as recorded, and the analysis report keyed exactly as the
        reporters consume it.
    """
    workdir.mkdir(parents=True, exist_ok=True)
    if video_path is None:
        video_path = workdir / f"{EXPERIMENT_ID}.mp4"
        write_golden_video(video_path)

    output_dir = workdir / "results"
    output_dir.mkdir(parents=True, exist_ok=True)

    zone_dict = {
        "polygon": _as_vertex_lists(ARENA_POLYGON),
        "roi_polygons": [_as_vertex_lists(ROI_LEFT), _as_vertex_lists(ROI_RIGHT)],
        "roi_names": list(ROI_NAMES),
        "roi_colors": [[255, 0, 0], [0, 255, 0]],
        "metadata": {"source_width": WIDTH, "source_height": HEIGHT},
    }
    task = {
        "path": str(video_path),
        "experiment_id": EXPERIMENT_ID,
        "zone_data": zone_dict,
    }

    config = WorkerConfig(
        settings=settings,
        output_base_dir=str(output_dir),
        tasks=[task],
        single_video_mode=True,
        # Analyse every frame: sub-sampling would make the golden depend on a
        # frame-skip cadence rather than on the analysis itself.
        analysis_interval_frames=1,
        display_interval_frames=10_000,
        model_path="",
        model_type="yolo",
        zone_data=zone_dict,
    )

    worker = _WorkerProcess(config, cast(Any, _QueueStub()), cast(Any, _QueueStub()))
    detector = Detector(
        plugin=GoldenDeterministicPlugin(),
        base_width=WIDTH,
        base_height=HEIGHT,
        settings_obj=settings,
    )

    succeeded = worker._process_single_video(
        index=0,
        total_videos=1,
        video_path=str(video_path),
        experiment_id=EXPERIMENT_ID,
        detector=detector,
        video_metadata=task,
    )
    if not succeeded:
        raise AssertionError("the pre-recorded worker reported failure for the golden video")

    trajectory = pd.read_parquet(output_dir / f"3_CoordMovimento_{EXPERIMENT_ID}.parquet")

    # The thresholds come from `settings`, never from literals here. That is
    # what makes the outcome sensitive to a polluted settings object.
    service = AnalysisService(settings_obj=settings)
    params = service.collect_analysis_parameters()
    rois = build_rois_from_zone_polygons([ROI_LEFT, ROI_RIGHT], list(ROI_NAMES))

    result = service.run_full_analysis_as_dto(
        trajectory_df=trajectory,
        pixelcm_x=10.0,
        pixelcm_y=10.0,
        video_height_px=HEIGHT,
        arena_polygon_px=ARENA_POLYGON,
        rois=rois,
        fps=float(FPS),
        metadata={"experiment_id": EXPERIMENT_ID},
        roi_colors={"Esquerda": (255, 0, 0), "Direita": (0, 255, 0)},
        freezing_vel_threshold=params["freezing_vel_threshold"],
        freezing_min_duration=params["freezing_min_duration"],
        smoothing_window_length=params["smoothing_window_length"],
        smoothing_polyorder=params["smoothing_polyorder"],
        sharp_turn_threshold=params["analysis"]["sharp_turn_threshold"],
        behavioral_config=params.get("behavioral_config"),
    )

    return PipelineOutcome(
        trajectory=trajectory,
        report=result.report,
        output_dir=output_dir,
        analysis_parameters=params,
    )


# ---------------------------------------------------------------------------
# Barnes maze (ADR-011 acceptance): several classes, context objects, a window
# ---------------------------------------------------------------------------

BARNES_ID = "BARNES_01"
BARNES_FPS = 10
BARNES_DURATION_S = 9
#: Class names of the lab's Barnes weight; ``arena`` is never drawn.
BARNES_NAMES: dict[int, str] = {0: "arena", 1: "experimenter", 2: "rat", 3: "start_box"}
BARNES_ROLES: dict[str, str] = {
    "arena": "arena",
    "experimenter": "context",
    "rat": "subject",
    "start_box": "context",
}
#: The sha the role map is recorded with; no weight file exists.
BARNES_WEIGHT_SHA = "f4b0" + "0" * 60
BARNES_ARENA: list[tuple[float, float]] = [(20, 20), (620, 20), (620, 460), (20, 460)]
#: The escape-hole ROI. Its left edge is where the rat's box arrives at frame 40.
BARNES_TOCA: list[tuple[float, float]] = [(292, 150), (600, 150), (600, 330), (292, 330)]
BARNES_ROI_NAMES = ["toca"]

#: One colour channel per class (BGR), so detection is a channel threshold.
_BARNES_COLOURS: dict[int, tuple[int, int, int]] = {
    1: (255, 0, 0),  # experimenter: blue
    2: (0, 255, 0),  # rat: green
    3: (0, 0, 255),  # start box: red
}

#: Timeline, in frames (10 fps). START (start box and experimenter gone, rat
#: visible) is first true at frame 25; the rat enters ``toca`` at frame 40 and
#: vanishes into the escape box at frame 70.
BARNES_START_BOX_UNTIL = 19
BARNES_EXPERIMENTER_UNTIL = 24
BARNES_RAT_FRAMES = range(15, 70)
BARNES_RAT_SIZE = 60


def barnes_rat_box(frame_index: int) -> tuple[int, int, int, int]:
    """Rat bbox ``(x1, y1, x2, y2)``: 8 px/frame to the right, 60 x 60 px.

    At frame 39 its right edge is ``x = 292`` (it only touches ``toca``); at
    frame 40 it overlaps by 8 px (13 % of the box, above the 10 % default).
    """
    x1 = 40 + 8 * (frame_index - BARNES_RAT_FRAMES.start)
    return x1, 210, x1 + BARNES_RAT_SIZE, 210 + BARNES_RAT_SIZE


def write_barnes_video(path: Path) -> None:
    """Synthetic Barnes trial: experimenter and start box leave, the rat escapes.

    Raises:
        RuntimeError: No usable codec (callers skip).
    """
    fourcc = cast(Any, cv2).VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(path), fourcc, BARNES_FPS, (WIDTH, HEIGHT))
    if not writer.isOpened():
        raise RuntimeError(f"Failed to open a VideoWriter for {path}; mp4v unavailable.")
    try:
        for i in range(BARNES_FPS * BARNES_DURATION_S):
            frame = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)
            if i <= BARNES_START_BOX_UNTIL:
                cv2.rectangle(frame, (40, 340), (139, 439), _BARNES_COLOURS[3], -1)
            if i <= BARNES_EXPERIMENTER_UNTIL:
                cv2.rectangle(frame, (40, 40), (139, 139), _BARNES_COLOURS[1], -1)
            if i in BARNES_RAT_FRAMES:
                x1, y1, x2, y2 = barnes_rat_box(i)
                cv2.rectangle(frame, (x1, y1), (x2 - 1, y2 - 1), _BARNES_COLOURS[2], -1)
            writer.write(frame)
    finally:
        writer.release()
    probe = cv2.VideoCapture(str(path))
    readable = probe.isOpened()
    probe.release()
    if not readable:
        raise RuntimeError(f"{path} was written but cannot be reopened; codec issue.")


class BarnesDeterministicPlugin(GoldenDeterministicPlugin):
    """Several classes per frame, one per colour channel (``findContours``)."""

    class_names = BARNES_NAMES

    def detect(
        self, frame: np.ndarray, conf_threshold: float | None = None
    ) -> list[tuple[int, int, int, int, float, int | None, int]]:
        detections: list[tuple[int, int, int, int, float, int | None, int]] = []
        for class_id, colour in _BARNES_COLOURS.items():
            channel = int(np.argmax(colour))
            others = [c for c in range(3) if c != channel]
            mask = (frame[:, :, channel] > 150) & np.all(frame[:, :, others] < 100, axis=2)
            contours, _ = cv2.findContours(
                mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )
            for contour in contours:
                if cv2.contourArea(contour) < 200:
                    continue
                x, y, w, h = cv2.boundingRect(contour)
                detections.append((x, y, x + w, y + h, 0.95, None, class_id))
        return detections

    @staticmethod
    def get_name() -> str:
        return "BarnesDeterministicPlugin"


@dataclass(frozen=True)
class BarnesRun:
    """Files one Barnes run produced."""

    trajectory_path: Path
    objects_path: Path
    output_dir: Path


def run_barnes_pipeline(workdir: Path, settings: Settings) -> BarnesRun:
    """Run the REAL pre-recorded worker on the synthetic Barnes trial.

    The weight has no file: the detector gets an explicit role map
    (``class_roles`` from the weight registry, F2) with a recorded sha, which
    is what the worker writes into the ``3c`` metadata (F3).
    """
    from zebtrack.core.detection.class_roles import resolve_class_role_map

    workdir.mkdir(parents=True, exist_ok=True)
    video_path = workdir / f"{BARNES_ID}.mp4"
    write_barnes_video(video_path)
    output_dir = workdir / "results"
    output_dir.mkdir(parents=True, exist_ok=True)

    zone_dict = {
        "polygon": _as_vertex_lists(BARNES_ARENA),
        "roi_polygons": [_as_vertex_lists(BARNES_TOCA)],
        "roi_names": list(BARNES_ROI_NAMES),
        "roi_colors": [[255, 255, 0]],
        "metadata": {"source_width": WIDTH, "source_height": HEIGHT},
    }
    task = {"path": str(video_path), "experiment_id": BARNES_ID, "zone_data": zone_dict}
    config = WorkerConfig(
        settings=settings,
        output_base_dir=str(output_dir),
        tasks=[task],
        single_video_mode=True,
        analysis_interval_frames=1,
        display_interval_frames=10_000,
        model_path="",
        model_type="yolo",
        zone_data=zone_dict,
    )
    worker = _WorkerProcess(config, cast(Any, _QueueStub()), cast(Any, _QueueStub()))
    role_map = resolve_class_role_map(
        BARNES_NAMES,
        weight_entry={"class_roles": BARNES_ROLES},
        weight_sha256=BARNES_WEIGHT_SHA,
    )
    detector = Detector(
        plugin=BarnesDeterministicPlugin(),
        base_width=WIDTH,
        base_height=HEIGHT,
        settings_obj=settings,
        class_role_map=role_map,
    )
    succeeded = worker._process_single_video(
        index=0,
        total_videos=1,
        video_path=str(video_path),
        experiment_id=BARNES_ID,
        detector=detector,
        video_metadata=task,
    )
    if not succeeded:
        raise AssertionError("the pre-recorded worker reported failure for the Barnes video")
    return BarnesRun(
        trajectory_path=output_dir / f"3_CoordMovimento_{BARNES_ID}.parquet",
        objects_path=output_dir / f"3c_Objetos_{BARNES_ID}.parquet",
        output_dir=output_dir,
    )
