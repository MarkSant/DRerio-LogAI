"""Shared utility helpers for hashing, reproducibility and geometry."""

from __future__ import annotations

import hashlib
import random
from pathlib import Path
from typing import Any

import numpy as np
import structlog

from zebtrack.utils.geometry import Point, polygon_centroid, snap_point_to_axes
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
    if torch_available and torch_module is not None:
        torch_module.manual_seed(seed)
        if torch_module.cuda.is_available():
            torch_module.cuda.manual_seed(seed)
            torch_module.cuda.manual_seed_all(seed)
            torch_module.backends.cudnn.deterministic = True
            torch_module.backends.cudnn.benchmark = False

    log.info("reproducibility.seed.set", seed=seed)


__all__ = [
    "IntegrityError",
    "Point",
    "calculate_sha256",
    "polygon_centroid",
    "set_seed",
    "snap_point_to_axes",
    "validate_calibration",
]
