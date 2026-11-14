"""Shared utility helpers for hashing, reproducibility and geometry."""

from __future__ import annotations

import hashlib
import math
import random
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import structlog

from zebtrack.utils.validation import validate_calibration

torch: Any | None
TORCH_AVAILABLE: bool


def __getattr__(name: str) -> Any:
    """Resolve ``torch`` / ``TORCH_AVAILABLE`` on first access (#643).

    Every module imports ``zebtrack.utils``; importing torch here made each of
    them pay several seconds. See ``zebtrack.utils.optional_deps``.
    """
    from zebtrack.utils.optional_deps import TORCH_LOADERS, resolve_lazy_attribute

    try:
        return resolve_lazy_attribute(globals(), name, TORCH_LOADERS)
    except AttributeError:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from None


log = structlog.get_logger()


class IntegrityError(Exception):
    """Custom exception for file integrity errors."""

    pass


def calculate_sha256(filepath: Path | str) -> str:
    """Calculate the SHA256 hash of a file."""
    filepath = Path(filepath) if isinstance(filepath, str) else filepath

    sha256_hash = hashlib.sha256()
    try:
        with open(filepath, "rb") as handle:
            for chunk in iter(lambda: handle.read(4096), b""):
                sha256_hash.update(chunk)
        return sha256_hash.hexdigest()
    except OSError:
        log.error("file.hash.read_error", filepath=filepath)
        return ""


def set_seed(seed: int) -> None:
    """Seed Python, NumPy and (optionally) PyTorch RNGs."""

    random.seed(seed)
    np.random.seed(seed)

    torch_available = __getattr__("TORCH_AVAILABLE")
    torch_module = __getattr__("torch")
    if torch_available and torch_module is not None:  # pragma: no cover - depends on torch
        torch_module.manual_seed(seed)
        if torch_module.cuda.is_available():  # pragma: no cover - GPU specific
            torch_module.cuda.manual_seed(seed)
            torch_module.cuda.manual_seed_all(seed)
            torch_module.backends.cudnn.deterministic = True
            torch_module.backends.cudnn.benchmark = False

    log.info("reproducibility.seed.set", seed=seed)


Point = tuple[float, float]


def polygon_centroid(points: Sequence[Point]) -> Point | None:
    """Return the centroid of a polygon using the shoelace formula."""

    if len(points) < 3:
        return None

    area_twice = 0.0
    cx = 0.0
    cy = 0.0
    for idx, (x0, y0) in enumerate(points):
        x1, y1 = points[(idx + 1) % len(points)]
        cross = x0 * y1 - x1 * y0
        area_twice += cross
        cx += (x0 + x1) * cross
        cy += (y0 + y1) * cross

    if math.isclose(area_twice, 0.0):
        return None

    area = area_twice / 2.0
    factor = 1 / (6.0 * area)
    return cx * factor, cy * factor


def snap_point_to_axes(
    point: Point,
    *,
    anchors: Iterable[Point] | None = None,
    centers: Iterable[Point] | None = None,
    threshold: float = 8.0,
) -> Point | None:
    """Snap a point to horizontal/vertical axes of anchors or centers."""

    px, py = point
    best_point: Point | None = None
    best_distance = threshold

    def _consider(candidate: Point) -> None:
        nonlocal best_point, best_distance
        cx, cy = candidate
        distance = math.hypot(cx - px, cy - py)
        if distance < best_distance:
            best_point = (cx, cy)
            best_distance = distance

    for anchor in anchors or []:
        ax, ay = anchor
        _consider((ax, py))
        _consider((px, ay))

    for center in centers or []:
        cx, cy = center
        _consider((cx, cy))
        _consider((cx, py))
        _consider((px, cy))

    return best_point


__all__ = [
    "IntegrityError",
    "calculate_sha256",
    "polygon_centroid",
    "set_seed",
    "snap_point_to_axes",
    "validate_calibration",
]
