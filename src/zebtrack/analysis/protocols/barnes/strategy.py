"""Search strategy of a Barnes trial: direct / serial / random (ADR-014, CONTRACTS §6).

Deterministic and explainable: the classifier reads four features, all exposed in
``report["protocol_metrics"]["strategy_features"]``, against the thresholds of
``BarnesParams``. The features are measured on the SEARCH: the visits up to and
including the first target visit (every visit of the trial when the target is
never found), and the centre crossings over the same span.

* **direct** — the target was found, with at most ``strategy_direct_max_errors``
  errors before it and no centre crossing;
* **serial** — at least one transition, at least
  ``strategy_serial_min_adjacent_fraction`` of them between adjacent holes
  (circular step ``<= strategy_adjacent_max_step``) and at most
  ``strategy_serial_max_center_crossings`` crossings;
* **random** — anything else; ``None`` when the trial has no visit.

A manual correction (``BarnesVideoInputs.strategy_override``) always wins and is
reported as ``strategy_source="manual"``; ``strategy_auto`` keeps the classifier's
answer.

Pure: no Tk, no I/O.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from itertools import pairwise
from typing import Any

import numpy as np

from zebtrack.analysis.protocols.barnes.contract import (
    BarnesParams,
    SearchStrategy,
    StrategySource,
)

__all__ = [
    "StrategyFeatures",
    "circular_step",
    "classify_strategy",
    "count_center_crossings",
    "resolve_strategy",
    "strategy_features",
]


@dataclass(frozen=True, slots=True)
class StrategyFeatures:
    """What the classifier reads (``report["protocol_metrics"]["strategy_features"]``)."""

    errors_before_target: int
    center_crossings: int
    adjacent_transition_fraction: float | None
    n_transitions: int

    def as_dict(self) -> dict[str, Any]:
        """Report form, keys in contract order."""
        return {
            "errors_before_target": self.errors_before_target,
            "center_crossings": self.center_crossings,
            "adjacent_transition_fraction": self.adjacent_transition_fraction,
            "n_transitions": self.n_transitions,
        }


def circular_step(offset_a: int, offset_b: int, n_holes: int) -> int:
    """Holes between two offsets going the short way round: ``min(|a-b|, n-|a-b|)``."""
    delta = abs(offset_a - offset_b) % n_holes
    return min(delta, n_holes - delta)


def count_center_crossings(inside: np.ndarray) -> int:
    """Outside → inside entries into the centre disk.

    Starting inside (the start box sits at the centre) is not a crossing: only a
    sample inside that follows a sample outside counts.
    """
    flags = np.asarray(inside, dtype=bool)
    if len(flags) < 2:
        return 0
    return int(np.count_nonzero(flags[1:] & ~flags[:-1]))


def strategy_features(
    search_offsets: Sequence[int],
    *,
    errors_before_target: int,
    center_crossings: int,
    params: BarnesParams,
) -> StrategyFeatures:
    """Features of the search whose visited hole offsets are ``search_offsets``."""
    n_transitions = max(len(search_offsets) - 1, 0)
    fraction: float | None = None
    if n_transitions:
        adjacent = sum(
            1
            for a, b in pairwise(search_offsets)
            if circular_step(a, b, params.n_holes) <= params.strategy_adjacent_max_step
        )
        fraction = adjacent / n_transitions
    return StrategyFeatures(
        errors_before_target=errors_before_target,
        center_crossings=center_crossings,
        adjacent_transition_fraction=fraction,
        n_transitions=n_transitions,
    )


def classify_strategy(
    features: StrategyFeatures,
    *,
    found_target: bool,
    n_visits: int,
    params: BarnesParams,
) -> SearchStrategy | None:
    """The automatic strategy (module docstring); ``None`` without a visit."""
    if n_visits == 0:
        return None
    if (
        found_target
        and features.errors_before_target <= params.strategy_direct_max_errors
        and features.center_crossings == 0
    ):
        return SearchStrategy.DIRECT
    if (
        features.n_transitions >= 1
        and features.adjacent_transition_fraction is not None
        and features.adjacent_transition_fraction >= params.strategy_serial_min_adjacent_fraction
        and features.center_crossings <= params.strategy_serial_max_center_crossings
    ):
        return SearchStrategy.SERIAL
    return SearchStrategy.RANDOM


def resolve_strategy(
    automatic: SearchStrategy | None, override: SearchStrategy | None
) -> tuple[SearchStrategy | None, StrategySource | None]:
    """``(strategy, strategy_source)``: the manual override wins over the classifier."""
    if override is not None:
        return override, StrategySource.MANUAL
    if automatic is None:
        return None, None
    return automatic, StrategySource.AUTO
