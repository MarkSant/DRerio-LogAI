"""Live camera mode selection based on hardware capability.

Provides fallback options when system resources are insufficient for
desired multi-aquarium real-time processing:

1. Record-Only Mode: Save video without live detection
2. Single-Aquarium Mode: Process one aquarium at a time
3. Adapt Project Mode: Modify project to split aquariums across sessions

Version: 2.2.0
Author: DRerio LogAI Team
Date: January 2026
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

import structlog

from zebtrack.i18n import _

if TYPE_CHECKING:
    from zebtrack.settings import Settings
    from zebtrack.utils.hardware_capability import HardwareCapabilityReport

logger = structlog.get_logger(__name__)


class LiveCameraMode(Enum):
    """Live camera processing modes."""

    MULTI_AQUARIUM_REALTIME = "multi_aquarium_realtime"  # Process all aquariums simultaneously
    SINGLE_AQUARIUM_REALTIME = "single_aquarium_realtime"  # Process one aquarium only
    RECORD_ONLY = "record_only"  # Record video, process offline later
    SEQUENTIAL_AQUARIUM = "sequential_aquarium"  # Record multiple sessions, one per aquarium


@dataclass
class LiveCameraModeRecommendation:
    """Recommendation for live camera mode based on hardware."""

    recommended_mode: LiveCameraMode
    requested_aquariums: int
    max_aquariums_supported: int
    can_process_realtime: bool
    reason: str
    alternative_options: list[tuple[LiveCameraMode, str]]  # (mode, description)
    warnings: list[str]

    def __str__(self) -> str:
        """Developer-facing summary for logs and debugging.

        Deliberately NOT translated: no call site renders it, and the first
        line prints ``recommended_mode.value`` — a persisted enum value that
        must stay readable next to the raw log records.
        """
        return (
            f"Recommended mode: {self.recommended_mode.value}\n"
            f"Aquariums requested: {self.requested_aquariums}\n"
            f"Aquariums supported: {self.max_aquariums_supported}\n"
            f"Reason: {self.reason}\n"
            f"Alternatives: {len(self.alternative_options)}"
        )


class LiveCameraModeSelector:
    """Selects appropriate live camera mode based on hardware capability.

    Decision Tree:
    1. User requests N aquariums for live processing
    2. Check hardware capability (HardwareCapabilityDetector)
    3. If capable: Recommend MULTI_AQUARIUM_REALTIME
    4. If limited: Offer fallbacks (SINGLE_AQUARIUM, RECORD_ONLY, SEQUENTIAL)
    5. If insufficient: Force RECORD_ONLY or abort

    User Options When Insufficient:
    - Adapt Project: Split aquariums into separate sessions (SEQUENTIAL_AQUARIUM)
    - Single Aquarium: Process only one aquarium in current session
    - Record Only: Save video for offline processing later
    - Abort: Cancel session and adjust project/hardware
    """

    def __init__(self, settings_obj: Settings):
        """Initialize mode selector.

        Args:
            settings_obj: Application settings
        """
        self.settings = settings_obj
        self.logger = logger.bind(domain="live_camera_mode_selector")

    def recommend_mode(
        self,
        requested_aquariums: int,
        hardware_report: HardwareCapabilityReport,
        allow_sequential: bool = True,
    ) -> LiveCameraModeRecommendation:
        """Recommend live camera mode based on hardware and request.

        Args:
            requested_aquariums: Number of aquariums user wants to process
            hardware_report: Hardware capability assessment
            allow_sequential: Whether sequential mode is acceptable

        Returns:
            Mode recommendation with alternatives
        """
        self.logger.info(
            "live_camera_mode.recommend.start",
            requested_aquariums=requested_aquariums,
            max_supported=hardware_report.max_aquariums_recommended,
            capability=hardware_report.capability.value,
        )

        can_realtime = hardware_report.can_process_realtime
        max_supported = hardware_report.max_aquariums_recommended

        # Build alternatives list
        alternatives: list[tuple[LiveCameraMode, str]] = []

        # Case 1: System can handle requested aquariums
        if can_realtime and requested_aquariums <= max_supported:
            recommended_mode = (
                LiveCameraMode.MULTI_AQUARIUM_REALTIME
                if requested_aquariums > 1
                else LiveCameraMode.SINGLE_AQUARIUM_REALTIME
            )
            reason = _(
                "The system supports {count} aquariums simultaneously. "
                "Real-time processing enabled."
            ).format(count=max_supported)

            # Still offer record-only as alternative (for better quality)
            alternatives.append(
                (
                    LiveCameraMode.RECORD_ONLY,
                    _("Record without detection (better quality, process later)"),
                )
            )

            return LiveCameraModeRecommendation(
                recommended_mode=recommended_mode,
                requested_aquariums=requested_aquariums,
                max_aquariums_supported=max_supported,
                can_process_realtime=True,
                reason=reason,
                alternative_options=alternatives,
                warnings=[],
            )

        # Case 2: Can process in realtime, but not all aquariums
        if can_realtime and requested_aquariums > max_supported > 0:
            recommended_mode = (
                LiveCameraMode.SEQUENTIAL_AQUARIUM
                if allow_sequential
                else LiveCameraMode.SINGLE_AQUARIUM_REALTIME
            )

            # Two COMPLETE sentences, never fragments: the original built this
            # by appending half a clause, which leaves a translator unable to
            # reorder. "aquário(s)" is gone for the same reason — see the
            # singular/plural pair in the warnings below.
            reason = _(
                "The system supports only {supported} of the {requested} aquariums "
                "requested for simultaneous processing. "
            ).format(supported=max_supported, requested=requested_aquariums)

            if allow_sequential:
                reason += _("Recommended: record {count} separate sessions.").format(
                    count=requested_aquariums
                )
            else:
                reason += _("Recommended: process only 1 aquarium in this session.")

            # Build alternatives
            if allow_sequential:
                alternatives.append(
                    (
                        LiveCameraMode.SINGLE_AQUARIUM_REALTIME,
                        _("Process only 1 aquarium now (ignore the rest)"),
                    )
                )
            else:
                alternatives.append(
                    (
                        LiveCameraMode.SEQUENTIAL_AQUARIUM,
                        _("Split into {count} separate sessions").format(count=requested_aquariums),
                    )
                )

            alternatives.append(
                (
                    LiveCameraMode.RECORD_ONLY,
                    _("Record without detection (process offline later)"),
                )
            )

            warnings = [
                _("⚠️ The system does not support {count} aquariums simultaneously.").format(
                    count=requested_aquariums
                ),
                # Two msgids instead of "aquário(s)": max_supported is 1 in the
                # common case, which is exactly when the parenthetical reads
                # worst. No ngettext — the pair files carry no plural forms.
                _("Maximum supported: 1 aquarium.")
                if max_supported == 1
                else _("Maximum supported: {count} aquariums.").format(count=max_supported),
            ]

            return LiveCameraModeRecommendation(
                recommended_mode=recommended_mode,
                requested_aquariums=requested_aquariums,
                max_aquariums_supported=max_supported,
                can_process_realtime=True,
                reason=reason,
                alternative_options=alternatives,
                warnings=warnings,
            )

        # Case 3: Cannot process in realtime at all
        if not can_realtime:
            recommended_mode = LiveCameraMode.RECORD_ONLY

            reason = _(
                "The system is not sufficient for real-time processing. "
                "Recommended: record the video and process it offline."
            )

            warnings = [
                _("⚠️ INSUFFICIENT HARDWARE for real-time detection."),
                _("CPU: {cores} cores (minimum 2)").format(cores=hardware_report.cpu_cores),
                _("RAM: {gb:.1f}GB available (minimum 4GB)").format(
                    gb=hardware_report.available_memory_gb
                ),
            ]

            # Only viable alternative is to abort
            alternatives.append(
                (
                    LiveCameraMode.RECORD_ONLY,
                    _("Record video without detection (only viable option)"),
                )
            )

            return LiveCameraModeRecommendation(
                recommended_mode=recommended_mode,
                requested_aquariums=requested_aquariums,
                max_aquariums_supported=0,
                can_process_realtime=False,
                reason=reason,
                alternative_options=alternatives,
                warnings=warnings,
            )

        # Fallback (should not reach here)
        return LiveCameraModeRecommendation(
            recommended_mode=LiveCameraMode.RECORD_ONLY,
            requested_aquariums=requested_aquariums,
            max_aquariums_supported=max_supported,
            can_process_realtime=can_realtime,
            reason=_("Default mode selected."),
            alternative_options=[],
            warnings=[],
        )

    def create_sequential_session_plan(
        self,
        total_aquariums: int,
        base_experiment_id: str,
    ) -> list[dict]:
        """Create plan for sequential aquarium sessions.

        Args:
            total_aquariums: Number of aquariums to split
            base_experiment_id: Base experiment ID for naming

        Returns:
            List of session configs, one per aquarium
        """
        plan = []
        for aq_idx in range(total_aquariums):
            session = {
                "experiment_id": f"{base_experiment_id}_aquarium_{aq_idx}",
                "aquarium_index": aq_idx,
                "aquarium_count_total": total_aquariums,
                "mode": LiveCameraMode.SINGLE_AQUARIUM_REALTIME,
                "notes": _("Session {index} of {total} (individual aquarium)").format(
                    index=aq_idx + 1, total=total_aquariums
                ),
            }
            plan.append(session)

        self.logger.info(
            "live_camera_mode.sequential_plan_created",
            total_aquariums=total_aquariums,
            sessions=len(plan),
        )

        return plan


def get_mode_description(mode: LiveCameraMode) -> str:
    """Get human-readable description of mode.

    Args:
        mode: Live camera mode

    Returns:
        Description in the active interface language
    """
    # Built inside the function, never at module level: a dict of _() calls in
    # a module body freezes the translation at import time.
    descriptions = {
        LiveCameraMode.MULTI_AQUARIUM_REALTIME: _(
            "Process multiple aquariums simultaneously in real time"
        ),
        LiveCameraMode.SINGLE_AQUARIUM_REALTIME: _("Process one aquarium in real time"),
        LiveCameraMode.RECORD_ONLY: _("Record video without detection (process offline later)"),
        LiveCameraMode.SEQUENTIAL_AQUARIUM: _("Record multiple sessions, one per aquarium"),
    }
    return descriptions.get(mode, _("Unknown mode"))
