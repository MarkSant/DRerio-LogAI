"""Shared utility helpers for hashing, reproducibility and geometry."""

from __future__ import annotations

import hashlib
import math
import random
from typing import Iterable, Sequence, Tuple

import numpy as np
import structlog

try:  # pragma: no cover - optional dependency
	import torch

	TORCH_AVAILABLE = True
except ImportError:  # pragma: no cover - graceful degradation
	torch = None
	TORCH_AVAILABLE = False

log = structlog.get_logger()


class IntegrityError(Exception):
	"""Custom exception for file integrity errors."""

	pass


def calculate_sha256(filepath: str) -> str:
	"""Calculate the SHA256 hash of a file."""

	sha256_hash = hashlib.sha256()
	try:
		with open(filepath, "rb") as handle:
			for chunk in iter(lambda: handle.read(4096), b""):
				sha256_hash.update(chunk)
		return sha256_hash.hexdigest()
	except IOError:
		log.error("file.hash.read_error", filepath=filepath)
		return ""


def set_seed(seed: int) -> None:
	"""Seed Python, NumPy and (optionally) PyTorch RNGs."""

	random.seed(seed)
	np.random.seed(seed)

	if TORCH_AVAILABLE and torch is not None:  # pragma: no cover - depends on torch
		torch.manual_seed(seed)
		if torch.cuda.is_available():  # pragma: no cover - GPU specific
			torch.cuda.manual_seed(seed)
			torch.cuda.manual_seed_all(seed)
			torch.backends.cudnn.deterministic = True
			torch.backends.cudnn.benchmark = False

	log.info("reproducibility.seed.set", seed=seed)


Point = Tuple[float, float]


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
	"set_seed",
	"polygon_centroid",
	"snap_point_to_axes",
]
