"""Synthetic Barnes tables and scripted rats for the barnes-metrics tests.

A plain module (not ``conftest``), imported by its full ``tests.`` path: several
test folders without ``__init__.py`` have their own ``conftest.py``, so
``from conftest import`` would resolve to whichever was imported first.

``BarnesTable`` draws the ROIs exactly as CONTRACTS §3.1 says the assistant writes
them (hole circles of 32 vertices, a quadrant sector, a 64-vertex table), in one
pixel space. ``RatScript`` walks a 20x20 px bbox between points at 10 fps, so a
scripted trial reads like the protocol: "leave the centre, poke +3, poke +2, poke
the target".
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from types import MappingProxyType, SimpleNamespace
from typing import Any

import numpy as np
import pandas as pd
from shapely.geometry import Point, Polygon

from zebtrack.analysis.analysis_window_service import WindowBound, WindowResolution
from zebtrack.analysis.protocols.barnes.contract import (
    QUADRANT_ROI,
    expected_roi_names,
    hole_roi_name,
    max_offset,
)
from zebtrack.analysis.protocols.base import ProtocolContext
from zebtrack.analysis.roi import ROI
from zebtrack.analysis.time_base import TimeBase
from zebtrack.core.services.experiment_profile import resolve_experiment_profile

FPS = 10.0
BOX = 20.0


class BarnesTable:
    """A circular Barnes table with ``n_holes`` holes; offsets clockwise on screen."""

    def __init__(
        self,
        n_holes: int = 20,
        center: tuple[float, float] = (320.0, 214.0),
        ring_radius: float = 150.0,
        hole_radius: float = 10.0,
        table_radius: float = 200.0,
        target_angle_deg: float = -90.0,
    ) -> None:
        self.n_holes = n_holes
        self.center = center
        self.ring_radius = ring_radius
        self.hole_radius = hole_radius
        self.table_radius = table_radius
        self.target_angle = math.radians(target_angle_deg)

    def angle_of(self, offset: float) -> float:
        return self.target_angle + offset * 2.0 * math.pi / self.n_holes

    def ring_xy(self, offset: float, radius: float | None = None) -> tuple[float, float]:
        r = self.ring_radius if radius is None else radius
        angle = self.angle_of(offset)
        return (self.center[0] + r * math.cos(angle), self.center[1] + r * math.sin(angle))

    def hole_xy(self, offset: int) -> tuple[float, float]:
        return self.ring_xy(offset)

    def hole_offsets(self) -> list[int]:
        half = max_offset(self.n_holes)
        low = -half + 1 if self.n_holes % 2 == 0 else -half
        return list(range(low, half + 1))

    def arena(self) -> tuple[tuple[float, float], ...]:
        return tuple(
            (
                self.center[0] + self.table_radius * math.cos(2 * math.pi * k / 64),
                self.center[1] + self.table_radius * math.sin(2 * math.pi * k / 64),
            )
            for k in range(64)
        )

    def quadrant(self, half_holes: int = 2) -> Polygon:
        edge = half_holes + 0.5
        steps = 48
        arc = [
            (
                self.center[0] + self.table_radius * math.cos(self.angle_of(o)),
                self.center[1] + self.table_radius * math.sin(self.angle_of(o)),
            )
            for o in np.linspace(-edge, edge, steps)
        ]
        return Polygon([self.center, *arc])

    def rois(
        self,
        *,
        quadrant: bool = True,
        omit: Iterable[str] = (),
        rename: Mapping[str, str] | None = None,
        extra: Iterable[ROI] = (),
    ) -> list[ROI]:
        """The Barnes ROIs in the stored order of ``expected_roi_names``."""
        skipped = set(omit)
        renames = dict(rename or {})
        by_offset = {hole_roi_name(o, self.n_holes): o for o in self.hole_offsets()}
        rois: list[ROI] = []
        for name in expected_roi_names(self.n_holes):
            if name in skipped or (name == QUADRANT_ROI and not quadrant):
                continue
            if name == QUADRANT_ROI:
                geometry = self.quadrant()
            else:
                geometry = Point(self.hole_xy(by_offset[name])).buffer(
                    self.hole_radius, quad_segs=8
                )
            rois.append(ROI(renames.get(name, name), geometry, coordinate_space="px"))
        rois.extend(extra)
        return rois


class RatScript:
    """A scripted subject: one 20x20 bbox per frame at :data:`FPS`."""

    def __init__(self, start: tuple[float, float], *, track_id: float = 1.0) -> None:
        self._rows: list[tuple[int, tuple[float, float] | None]] = [(0, start)]
        self._xy = start
        self._track_id = track_id

    @property
    def t(self) -> float:
        return self._rows[-1][0] / FPS

    def move(self, xy: tuple[float, float], seconds: float) -> RatScript:
        steps = max(round(seconds * FPS), 1)
        x0, y0 = self._xy
        frame = self._rows[-1][0]
        for k in range(1, steps + 1):
            f = k / steps
            self._rows.append((frame + k, (x0 + (xy[0] - x0) * f, y0 + (xy[1] - y0) * f)))
        self._xy = xy
        return self

    def stay(self, seconds: float) -> RatScript:
        return self.move(self._xy, seconds)

    def vanish(self, seconds: float) -> RatScript:
        """No detection for ``seconds`` (the processed frames still exist)."""
        steps = max(round(seconds * FPS), 1)
        frame = self._rows[-1][0]
        self._rows.extend((frame + k, None) for k in range(1, steps + 1))
        return self

    def poke(self, xy: tuple[float, float], travel_s: float = 1.0, dwell_s: float = 0.6):
        return self.move(xy, travel_s).stay(dwell_s)

    def frame(self, *, with_center_columns: bool = False) -> pd.DataFrame:
        rows = [(f, xy) for f, xy in self._rows if xy is not None]
        x = np.array([xy[0] for _f, xy in rows])
        y = np.array([xy[1] for _f, xy in rows])
        frames = np.array([f for f, _xy in rows])
        data: dict[str, Any] = {
            "timestamp": frames / FPS,
            "frame": frames,
            "track_id": self._track_id,
            "x1": x - BOX / 2,
            "y1": y - BOX / 2,
            "x2": x + BOX / 2,
            "y2": y + BOX / 2,
            "confidence": 0.9,
        }
        if with_center_columns:
            data["x_center_px"] = x
            data["y_center_px"] = y
        return pd.DataFrame(data)


def window(
    start: float | None,
    stop: float | None,
    *,
    reason: str = "burrow_entry",
    spec: Mapping[str, Any] | None = None,
    **fields: Any,
) -> WindowResolution:
    """A resolved window on the 10 fps clock, as ``AnalysisWindowService`` returns it."""
    values: dict[str, Any] = {"status": "complete", "spec_hash": "sha256:" + "b" * 64}
    if start is not None:
        values["start"] = WindowBound(round(start * FPS), start, "persist")
    if stop is not None:
        values["stop"] = WindowBound(round(stop * FPS), stop, reason)
    values["spec"] = spec
    values.update(fields)
    return WindowResolution(**values)


#: The STOP of preset v2, JSON form (only ``kind`` matters to the metrics).
V2_SPEC: Mapping[str, Any] = {
    "start": {"kind": "persist"},
    "stop": {
        "kind": "first_of",
        "of": [
            {"kind": "end_of_stream"},
            {"kind": "burrow_entry", "roi": "toca"},
            {"kind": "delay"},
        ],
    },
}
#: The STOP of preset v1: no entry detection.
V1_SPEC: Mapping[str, Any] = {
    "start": {"kind": "persist"},
    "stop": {"kind": "first_of", "of": [{"kind": "roi_edge", "roi": "toca"}]},
}


class FakeRoiAnalyzer:
    """``get_time_spent_in_rois`` as the report's analyser answers it."""

    def __init__(self, seconds: Mapping[str, float]) -> None:
        self._seconds = dict(seconds)

    def get_time_spent_in_rois(self) -> dict[str, dict[str, float]]:
        return {name: {"seconds": s, "percentage": 0.0} for name, s in self._seconds.items()}


def make_context(
    trajectory: pd.DataFrame,
    rois: list[ROI],
    *,
    table: BarnesTable | None = None,
    window: WindowResolution | None = None,
    inputs: Mapping[str, Any] | None = None,
    params: Mapping[str, Any] | None = None,
    quadrant_s: float | None = 4.0,
    gap_threshold_s: float = float("inf"),
    pixelcm: float = 1.0,
    warnings: list[str] | None = None,
) -> ProtocolContext:
    behavioral_config: dict[str, Any] = {"protocol": "barnes"}
    if params is not None:
        behavioral_config["protocol_params"] = {"barnes": dict(params)}
    seconds = {} if quadrant_s is None else {QUADRANT_ROI: quadrant_s}
    return ProtocolContext(
        profile=resolve_experiment_profile(behavioral_config=behavioral_config),
        trajectory=trajectory,
        rois=tuple(rois),
        arena_polygon_px=(table or BarnesTable()).arena(),
        pixelcm_x=pixelcm,
        pixelcm_y=pixelcm,
        window=window,
        time_base=TimeBase(
            fps_sampling=FPS,
            fps_video=FPS,
            duration_s=None,
            t_first=None,
            t_last=None,
            median_dt=1 / FPS,
            source="pts",
        ),
        behavioral_config=MappingProxyType(behavioral_config),
        inputs=MappingProxyType(dict(inputs or {})),
        behavioral_analyzer=SimpleNamespace(gap_threshold_s=gap_threshold_s),  # type: ignore[arg-type]
        roi_analyzer=FakeRoiAnalyzer(seconds) if rois else None,  # type: ignore[arg-type]
        warnings=[] if warnings is None else warnings,
    )
