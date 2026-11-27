"""A synthetic Barnes table with known hole centres (shared by the Barnes tests).

The table is the affine image of a circle: a light table on a dark floor, with
``n_holes`` dark disks evenly spaced on a concentric ring. Tests assert against the
true centres (:meth:`SyntheticTable.hole_center`), never against the code's own
prediction.
"""

from __future__ import annotations

import math

import cv2
import numpy as np

from zebtrack.analysis.protocols.barnes.contract import BarnesEllipse
from zebtrack.core.detection import barnes_geometry as g

__all__ = ["HEIGHT", "WIDTH", "SyntheticTable", "affine"]


def affine(rotation_deg: float, sx: float, sy: float, shear: float = 0.0) -> np.ndarray:
    """Rotation x (scale + shear): a mild off-axis camera."""
    theta = math.radians(rotation_deg)
    rot = np.array([[math.cos(theta), -math.sin(theta)], [math.sin(theta), math.cos(theta)]])
    return rot @ np.array([[sx, shear], [0.0, sy]])


WIDTH, HEIGHT = 640, 480


class SyntheticTable:
    """A Barnes table seen through an affine camera, with known hole centres."""

    def __init__(
        self,
        n_holes: int = 20,
        *,
        matrix: np.ndarray | None = None,
        center: tuple[float, float] = (320.0, 240.0),
        table_radius: float = 200.0,
        ring_radius: float = 170.0,
        hole_radius: float = 9.0,
        phase_deg: float = 7.0,
        missing: tuple[int, ...] = (),
        ring_offset: tuple[float, float] = (0.0, 0.0),
    ) -> None:
        self.n_holes = n_holes
        self.matrix = matrix if matrix is not None else affine(0.0, 1.0, 0.85)
        self.center = np.array(center)
        self.table_radius = table_radius
        self.ring_radius = ring_radius
        self.hole_radius = hole_radius
        self.phase = math.radians(phase_deg)
        self.missing = set(missing)
        # Ring centre relative to the table centre, in table units: the
        # holes are not concentric with the outline the user defined.
        self.ring_offset = np.array(ring_offset)

    def map(self, unit_xy: np.ndarray) -> np.ndarray:
        return unit_xy @ self.matrix.T + self.center

    def hole_center(self, index: int) -> tuple[float, float]:
        angle = self.phase + 2.0 * math.pi * index / self.n_holes
        unit = self.ring_radius * np.array([math.cos(angle), math.sin(angle)])
        point = self.map(unit + self.ring_offset)
        return float(point[0]), float(point[1])

    def rim_points(self, count: int = 360) -> list[tuple[float, float]]:
        angles = np.linspace(0.0, 2.0 * math.pi, count, endpoint=False)
        circle = self.table_radius * np.stack([np.cos(angles), np.sin(angles)], axis=1)
        return [(float(x), float(y)) for x, y in self.map(circle)]

    def table_ellipse(self) -> BarnesEllipse:
        return g.ellipse_from_points(self.rim_points())

    def image(self) -> np.ndarray:
        img = np.full((HEIGHT, WIDTH), 40, dtype=np.uint8)
        cv2.fillPoly(img, [np.round(np.array(self.rim_points())).astype(np.int32)], 200)
        angles = np.linspace(0.0, 2.0 * math.pi, 72, endpoint=False)
        disk = self.hole_radius * np.stack([np.cos(angles), np.sin(angles)], axis=1)
        for index in range(self.n_holes):
            if index in self.missing:
                continue
            angle = self.phase + 2.0 * math.pi * index / self.n_holes
            unit = self.ring_radius * np.array([math.cos(angle), math.sin(angle)])
            outline = self.map(unit + self.ring_offset + disk / np.linalg.det(self.matrix) ** 0.5)
            cv2.fillPoly(img, [np.round(outline * 16).astype(np.int32)], 25, shift=4)
        noise = np.random.default_rng(7).normal(0.0, 3.0, img.shape)
        return np.clip(img.astype(np.float64) + noise, 0, 255).astype(np.uint8)
