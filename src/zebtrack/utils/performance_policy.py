"""The one rule for how much concurrency the analysis may use (#725, A7-02).

Two ``performance`` settings decide it, and until #725 nothing read either:

* ``performance.enable_parallel_analysis`` -- ``False`` makes the analysis
  genuinely sequential: every analysis-side pool runs with one worker.
* ``performance.memory_mode`` -- ``"low"`` is the economy mode the startup
  benchmark selects on a machine with less than 8 GB of RAM. It implies the
  sequential rule above even when ``enable_parallel_analysis`` was left
  ``True`` by hand, and it caps the OpenVINO batch-inference request pool
  (``openvino.batch_nireq``) at one request.

The benchmark WRITES these values; the readers are the call sites that ask this
module. Never re-derive the rule at a call site: a second reading of
``memory_mode`` that forgets the ``enable_parallel_analysis`` half (or the other
way round) is how an operator ends up believing they are in economy mode while
the app runs at full width.

The module is pure: no I/O, no settings singleton. ``settings_obj`` is the
injected ``Settings`` instance (or a stub, or ``None``); missing sections fall
back to the defaults of ``PerformanceSettings``.
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "LOW_MEMORY_MODE",
    "analysis_max_workers",
    "effective_batch_nireq",
    "is_low_memory_mode",
    "parallel_analysis_enabled",
]

LOW_MEMORY_MODE = "low"


def is_low_memory_mode(settings_obj: Any) -> bool:
    """Whether ``performance.memory_mode`` asks for the low-memory economy mode."""
    performance = getattr(settings_obj, "performance", None)
    return getattr(performance, "memory_mode", "normal") == LOW_MEMORY_MODE


def parallel_analysis_enabled(settings_obj: Any) -> bool:
    """Whether analysis-side work may run on more than one worker.

    ``False`` when ``memory_mode`` is ``"low"`` (whatever
    ``enable_parallel_analysis`` says) or when ``enable_parallel_analysis`` is
    ``False``. Without settings the default (parallel) applies.
    """
    if is_low_memory_mode(settings_obj):
        return False
    performance = getattr(settings_obj, "performance", None)
    return bool(getattr(performance, "enable_parallel_analysis", True))


def analysis_max_workers(settings_obj: Any, requested: int) -> int:
    """How many workers an analysis-side pool may use.

    Args:
        settings_obj: injected ``Settings`` (or ``None``).
        requested: the width the call site would use on its own (for example
            ``performance.max_parallel_plots``).

    Returns:
        ``1`` when parallel analysis is off (see
        :func:`parallel_analysis_enabled`); otherwise ``requested``, never
        below ``1``. A call site that gets ``1`` runs inline, without a pool.
    """
    if not parallel_analysis_enabled(settings_obj):
        return 1
    return max(1, int(requested))


def effective_batch_nireq(settings_obj: Any, configured: int) -> int:
    """OpenVINO batch-inference request pool size after the low-memory rule.

    Each in-flight request holds its own input and output tensors, so the
    low-memory mode keeps a single one regardless of ``openvino.batch_nireq``.
    """
    if is_low_memory_mode(settings_obj):
        return 1
    return int(configured)
