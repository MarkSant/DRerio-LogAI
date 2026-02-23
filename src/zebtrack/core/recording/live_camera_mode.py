"""Live camera mode selection based on hardware capability.

Provides fallback options when system resources are insufficient for
desired multi-aquarium real-time processing:

1. Record-Only Mode: Save video without live detection
2. Single-Aquarium Mode: Process one aquarium at a time
3. Adapt Project Mode: Modify project to split aquariums across sessions

Version: 2.2.0
Author: ZebTrack-AI Team
Date: January 2026
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

import structlog

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
        """Human-readable summary."""
        return (
            f"Modo Recomendado: {self.recommended_mode.value}\n"
            f"Aquários Solicitados: {self.requested_aquariums}\n"
            f"Aquários Suportados: {self.max_aquariums_supported}\n"
            f"Razão: {self.reason}\n"
            f"Alternativas: {len(self.alternative_options)}"
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
            reason = (
                f"Sistema suporta {max_supported} aquários simultaneamente. "
                f"Processamento em tempo real habilitado."
            )

            # Still offer record-only as alternative (for better quality)
            alternatives.append(
                (
                    LiveCameraMode.RECORD_ONLY,
                    "Gravar sem detecção (melhor qualidade, processar depois)",
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

            reason = (
                f"Sistema suporta apenas {max_supported} aquário(s) simultaneamente, "
                f"mas {requested_aquariums} foram solicitados. "
            )

            if allow_sequential:
                reason += f"Recomendado: gravar {requested_aquariums} sessões separadas."
            else:
                reason += "Recomendado: processar apenas 1 aquário nesta sessão."

            # Build alternatives
            if allow_sequential:
                alternatives.append(
                    (
                        LiveCameraMode.SINGLE_AQUARIUM_REALTIME,
                        "Processar apenas 1 aquário agora (ignorar demais)",
                    )
                )
            else:
                alternatives.append(
                    (
                        LiveCameraMode.SEQUENTIAL_AQUARIUM,
                        f"Dividir em {requested_aquariums} sessões separadas",
                    )
                )

            alternatives.append(
                (
                    LiveCameraMode.RECORD_ONLY,
                    "Gravar sem detecção (processar offline depois)",
                )
            )

            warnings = [
                f"⚠️ Sistema não suporta {requested_aquariums} aquários simultaneamente.",
                f"Máximo suportado: {max_supported} aquário(s).",
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

            reason = (
                "Sistema insuficiente para processamento em tempo real. "
                "Recomendado: gravar vídeo e processar offline."
            )

            warnings = [
                "⚠️ HARDWARE INSUFICIENTE para detecção em tempo real.",
                f"CPU: {hardware_report.cpu_cores} cores (mínimo 2)",
                f"RAM: {hardware_report.available_memory_gb:.1f}GB disponível (mínimo 4GB)",
            ]

            # Only viable alternative is to abort
            alternatives.append(
                (
                    LiveCameraMode.RECORD_ONLY,
                    "Gravar vídeo sem detecção (única opção viável)",
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
            reason="Modo padrão selecionado.",
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
                "notes": f"Sessão {aq_idx + 1} de {total_aquariums} (aquário individual)",
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
        Portuguese description
    """
    descriptions = {
        LiveCameraMode.MULTI_AQUARIUM_REALTIME: (
            "Processar múltiplos aquários simultaneamente em tempo real"
        ),
        LiveCameraMode.SINGLE_AQUARIUM_REALTIME: "Processar um aquário em tempo real",
        LiveCameraMode.RECORD_ONLY: "Gravar vídeo sem detecção (processar offline depois)",
        LiveCameraMode.SEQUENTIAL_AQUARIUM: "Gravar múltiplas sessões, uma por aquário",
    }
    return descriptions.get(mode, "Modo desconhecido")
