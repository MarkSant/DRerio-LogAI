"""Hardware capability detection for live multi-aquarium processing.

This module assesses system resources to determine if real-time multi-aquarium
detection is feasible. It considers CPU cores, available memory, GPU presence,
and current system load.

Architecture Decision:
- Opção A: Auto-detection with fallback options
- Informs user of insufficient capacity
- Offers alternatives: single-aquarium, record-only, or adapt project

Version: 2.2.0
Author: DRerio LogAI Team
Date: January 2026
"""

from __future__ import annotations

import multiprocessing
import platform
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

import psutil
import structlog

from zebtrack.i18n import _

if TYPE_CHECKING:
    from zebtrack.settings import Settings

logger = structlog.get_logger(__name__)


class MultiAquariumCapability(Enum):
    """Multi-aquarium processing capability levels."""

    EXCELLENT = "excellent"  # GPU + 8+ cores + 16GB+ RAM → 4+ aquariums
    GOOD = "good"  # 6+ cores + 8GB+ RAM → 2-3 aquariums
    MODERATE = "moderate"  # 4+ cores + 6GB+ RAM → 2 aquariums
    LIMITED = "limited"  # 2-3 cores or <6GB RAM → 1 aquarium only
    INSUFFICIENT = "insufficient"  # <2 cores or <4GB RAM → record-only


@dataclass
class HardwareCapabilityReport:
    """Detailed hardware capability assessment."""

    capability: MultiAquariumCapability
    max_aquariums_recommended: int
    cpu_cores: int
    available_memory_gb: float
    total_memory_gb: float
    has_gpu: bool
    gpu_name: str | None
    cpu_usage_percent: float
    memory_usage_percent: float
    can_process_realtime: bool
    recommendations: list[str]
    warnings: list[str]
    # v2.2.0: GPU memory tracking
    gpu_memory_total_gb: float | None = None
    gpu_memory_available_gb: float | None = None

    def __str__(self) -> str:
        """Human-readable summary."""
        gpu_str = "No"
        if self.has_gpu:
            gpu_str = f"Yes - {self.gpu_name or 'Unknown'}"
            if self.gpu_memory_total_gb:
                gpu_str += (
                    f" ({self.gpu_memory_available_gb:.1f}GB / "
                    f"{self.gpu_memory_total_gb:.1f}GB free)"
                )

        return (
            f"Capability: {self.capability.value.upper()}\n"
            f"Max Aquariums: {self.max_aquariums_recommended}\n"
            f"CPU: {self.cpu_cores} cores ({self.cpu_usage_percent:.1f}% used)\n"
            f"Memory: {self.available_memory_gb:.1f}GB available / "
            f"{self.total_memory_gb:.1f}GB total\n"
            f"GPU: {gpu_str}\n"
            f"Real-time: {'Yes' if self.can_process_realtime else 'No (record-only)'}"
        )


class HardwareCapabilityDetector:
    """Detects hardware capability for live multi-aquarium processing.

    Uses heuristics based on:
    - CPU core count (logical cores for threading)
    - Available memory (free RAM at detection time)
    - GPU presence (via OpenVINO/CUDA detection)
    - Current system load (CPU/memory usage)

    Recommendations:
    - EXCELLENT: 8+ cores, 16GB+ RAM, GPU → 4+ aquariums
    - GOOD: 6+ cores, 8GB+ RAM → 2-3 aquariums
    - MODERATE: 4+ cores, 6GB+ RAM → 2 aquariums
    - LIMITED: 2-3 cores or <6GB RAM → 1 aquarium
    - INSUFFICIENT: <2 cores or <4GB RAM → record-only mode
    """

    def __init__(self, settings_obj: Settings):
        """Initialize detector.

        Args:
            settings_obj: Application settings for hardware config access
        """
        self.settings = settings_obj
        self.logger = logger.bind(domain="hardware_capability")

    def assess_capability(self) -> HardwareCapabilityReport:
        """Assess current hardware capability for multi-aquarium live processing.

        Returns:
            Detailed capability report with recommendations and warnings
        """
        self.logger.info("hardware_capability.assess.start")

        # Gather metrics
        cpu_cores = multiprocessing.cpu_count()
        memory = psutil.virtual_memory()
        total_memory_gb = memory.total / (1024**3)
        available_memory_gb = memory.available / (1024**3)
        memory_usage_percent = memory.percent

        cpu_percent = psutil.cpu_percent(interval=0.5)

        # GPU detection
        has_gpu, gpu_name, gpu_mem_total, gpu_mem_free = self._detect_gpu()

        # Determine capability tier (use total memory, not available)
        capability = self._calculate_capability_tier(
            cpu_cores=cpu_cores,
            total_memory_gb=total_memory_gb,
            has_gpu=has_gpu,
            cpu_usage=cpu_percent,
            memory_usage=memory_usage_percent,
        )

        # Calculate max recommended aquariums
        max_aquariums = self._calculate_max_aquariums(capability, cpu_cores, total_memory_gb)

        # Check if real-time processing is feasible
        can_process_realtime = capability not in (MultiAquariumCapability.INSUFFICIENT,)

        # Generate recommendations
        recommendations = self._generate_recommendations(
            capability=capability,
            cpu_cores=cpu_cores,
            available_memory_gb=available_memory_gb,
            has_gpu=has_gpu,
            cpu_usage=cpu_percent,
            memory_usage=memory_usage_percent,
        )

        # Generate warnings
        warnings = self._generate_warnings(
            capability=capability,
            cpu_usage=cpu_percent,
            memory_usage=memory_usage_percent,
            available_memory_gb=available_memory_gb,
        )

        report = HardwareCapabilityReport(
            capability=capability,
            max_aquariums_recommended=max_aquariums,
            cpu_cores=cpu_cores,
            available_memory_gb=available_memory_gb,
            total_memory_gb=total_memory_gb,
            has_gpu=has_gpu,
            gpu_name=gpu_name,
            cpu_usage_percent=cpu_percent,
            memory_usage_percent=memory_usage_percent,
            can_process_realtime=can_process_realtime,
            recommendations=recommendations,
            warnings=warnings,
            gpu_memory_total_gb=gpu_mem_total,
            gpu_memory_available_gb=gpu_mem_free,
        )

        self.logger.info(
            "hardware_capability.assess.complete",
            capability=capability.value,
            max_aquariums=max_aquariums,
            can_realtime=can_process_realtime,
        )

        return report

    def _detect_gpu(self) -> tuple[bool, str | None, float | None, float | None]:
        """Detect GPU presence and name.

        Returns:
            (has_gpu, gpu_name, total_memory_gb, available_memory_gb) tuple
        """
        try:
            # Check for NVIDIA GPU via PyTorch/CUDA
            import torch

            if torch.cuda.is_available():
                gpu_name = torch.cuda.get_device_name(0)

                # v2.2.0: Get GPU memory info
                gpu_mem_total = torch.cuda.get_device_properties(0).total_memory / (1024**3)
                gpu_mem_allocated = torch.cuda.memory_allocated(0) / (1024**3)
                gpu_mem_free = gpu_mem_total - gpu_mem_allocated

                self.logger.info(
                    "hardware_capability.gpu_detected",
                    gpu=gpu_name,
                    backend="CUDA",
                    total_memory_gb=f"{gpu_mem_total:.1f}",
                    allocated_gb=f"{gpu_mem_allocated:.1f}",
                    free_gb=f"{gpu_mem_free:.1f}",
                )
                return True, gpu_name, gpu_mem_total, gpu_mem_free
        except (ImportError, Exception):
            logger.debug("hardware_capability.cuda_detection.unavailable", exc_info=True)

        # Check for OpenVINO support (Intel integrated graphics)
        # v2.2.1: Detect Intel GPU directly via OpenVINO Core, not just cached models
        try:
            import openvino as ov

            core = ov.Core()
            available_devices = core.available_devices

            # Check if any GPU device is available in OpenVINO
            gpu_devices = [d for d in available_devices if "GPU" in d]
            if gpu_devices:
                # Try to get more detailed GPU info
                try:
                    gpu_device = gpu_devices[0]
                    gpu_full_name = core.get_property(gpu_device, "FULL_DEVICE_NAME")
                    gpu_name = f"{gpu_full_name} (OpenVINO)"
                except Exception:
                    # Fallback to processor name
                    system_name = platform.processor()
                    gpu_name = f"Intel Graphics ({system_name})"

                self.logger.info(
                    "hardware_capability.gpu_detected",
                    gpu=gpu_name,
                    backend="OpenVINO",
                    devices=gpu_devices,
                )
                # OpenVINO doesn't expose memory info, return None
                return True, gpu_name, None, None
        except ImportError:
            self.logger.debug("hardware_capability.openvino_not_installed")
        except Exception as e:
            self.logger.debug("hardware_capability.openvino_detection_failed", error=str(e))

        self.logger.info("hardware_capability.gpu_not_detected")
        return False, None, None, None

    def _calculate_capability_tier(
        self,
        cpu_cores: int,
        total_memory_gb: float,
        has_gpu: bool,
        cpu_usage: float,
        memory_usage: float,
    ) -> MultiAquariumCapability:
        """Calculate hardware capability tier.

        Args:
            cpu_cores: Number of logical CPU cores
            total_memory_gb: Total RAM in GB (not available, for stable classification)
            has_gpu: Whether GPU is detected
            cpu_usage: Current CPU usage percentage
            memory_usage: Current memory usage percentage

        Returns:
            Capability tier enum
        """
        # Insufficient: Cannot process in real-time
        if cpu_cores < 2 or total_memory_gb < 4:
            return MultiAquariumCapability.INSUFFICIENT

        # Limited: Single aquarium only
        if cpu_cores <= 3 or total_memory_gb < 6:
            return MultiAquariumCapability.LIMITED

        # Moderate: 2 aquariums
        if cpu_cores <= 5 or total_memory_gb < 8:
            return MultiAquariumCapability.MODERATE

        # Good: 2-3 aquariums
        if cpu_cores <= 7 or total_memory_gb < 16:
            return MultiAquariumCapability.GOOD

        # Excellent: 4+ aquariums
        if has_gpu and cpu_cores >= 8 and total_memory_gb >= 16:
            return MultiAquariumCapability.EXCELLENT

        # Default to GOOD if meets all thresholds
        return MultiAquariumCapability.GOOD

    def _calculate_max_aquariums(
        self, capability: MultiAquariumCapability, cpu_cores: int, total_memory_gb: float
    ) -> int:
        """Calculate maximum recommended aquariums for live processing.

        Args:
            capability: Hardware capability tier
            cpu_cores: Number of CPU cores
            total_memory_gb: Total memory in GB

        Returns:
            Maximum recommended aquarium count (0 = record-only)
        """
        if capability == MultiAquariumCapability.INSUFFICIENT:
            return 0  # Record-only mode

        if capability == MultiAquariumCapability.LIMITED:
            return 1

        if capability == MultiAquariumCapability.MODERATE:
            return 2

        if capability == MultiAquariumCapability.GOOD:
            # Scale with CPU cores: 6 cores → 2 aquariums, 8 cores → 3 aquariums
            return min(3, (cpu_cores // 3) + 1)

        if capability == MultiAquariumCapability.EXCELLENT:
            # Scale with CPU cores and memory
            max_from_cpu = cpu_cores // 2  # Conservative: 2 cores per aquarium
            max_from_memory = int(total_memory_gb // 4)  # 4GB per aquarium
            return min(max_from_cpu, max_from_memory, 6)  # Cap at 6 aquariums

        return 1  # Fallback

    def _generate_recommendations(
        self,
        capability: MultiAquariumCapability,
        cpu_cores: int,
        available_memory_gb: float,
        has_gpu: bool,
        cpu_usage: float,
        memory_usage: float,
    ) -> list[str]:
        """Generate actionable recommendations based on hardware.

        Returns:
            List of recommendation strings
        """
        recommendations = []

        if capability == MultiAquariumCapability.INSUFFICIENT:
            recommendations.append(
                _(
                    "System insufficient for real-time processing. "
                    "Recommended: record video only and process offline."
                )
            )
            recommendations.append(
                _(
                    "Suggested upgrade: at least 2 CPU cores and 4GB of available RAM "
                    "(current: {cores} cores, {memory:.1f}GB)"
                ).format(cores=cpu_cores, memory=available_memory_gb)
            )

        elif capability == MultiAquariumCapability.LIMITED:
            recommendations.append(
                _(
                    "System limited to 1 aquarium at a time in real time. "
                    "For multiple aquariums, consider offline recording."
                )
            )
            if cpu_cores <= 3:
                recommendations.append(
                    _(
                        "Limited CPU ({cores} cores). Upgrading to 4+ cores improves "
                        "multi-aquarium performance."
                    ).format(cores=cpu_cores)
                )
            if available_memory_gb < 6:
                recommendations.append(
                    _(
                        "Limited memory ({memory:.1f}GB available). Close background "
                        "applications or upgrade to 8GB+ RAM."
                    ).format(memory=available_memory_gb)
                )

        elif capability == MultiAquariumCapability.MODERATE:
            recommendations.append(_("System supports up to 2 aquariums simultaneously."))
            if not has_gpu:
                recommendations.append(
                    _("No GPU detected. Adding a GPU improves performance significantly.")
                )

        elif capability == MultiAquariumCapability.GOOD:
            recommendations.append(
                _("System supports 2-3 aquariums simultaneously with good performance.")
            )

        elif capability == MultiAquariumCapability.EXCELLENT:
            recommendations.append(
                _("Excellent system! Supports 4+ aquariums simultaneously at high performance.")
            )

        # High load warnings
        if cpu_usage > 70:
            recommendations.append(
                _(
                    "CPU under heavy load ({usage:.1f}%). Close background applications "
                    "before starting capture."
                ).format(usage=cpu_usage)
            )

        if memory_usage > 80:
            recommendations.append(
                _(
                    "Memory heavily used ({usage:.1f}%). Close background applications to free RAM."
                ).format(usage=memory_usage)
            )

        return recommendations

    def _generate_warnings(
        self,
        capability: MultiAquariumCapability,
        cpu_usage: float,
        memory_usage: float,
        available_memory_gb: float,
    ) -> list[str]:
        """Generate warnings about potential issues.

        Returns:
            List of warning strings
        """
        warnings = []

        if capability == MultiAquariumCapability.INSUFFICIENT:
            warnings.append(_("⚠️ REAL-TIME PROCESSING NOT RECOMMENDED. Use record-only mode."))

        if cpu_usage > 80:
            warnings.append(
                _("⚠️ CPU overloaded ({usage:.1f}%). Frames may be dropped.").format(usage=cpu_usage)
            )

        if memory_usage > 90:
            warnings.append(
                _("⚠️ Critical memory ({usage:.1f}%). Risk of system freeze.").format(
                    usage=memory_usage
                )
            )

        if available_memory_gb < 4:
            warnings.append(
                _("⚠️ Available memory is very low. Close other applications immediately.")
            )

        return warnings


def assess_hardware_for_live_multi_aquarium(settings_obj: Settings) -> HardwareCapabilityReport:
    """Convenience function to assess hardware capability.

    Args:
        settings_obj: Application settings

    Returns:
        Hardware capability report
    """
    detector = HardwareCapabilityDetector(settings_obj)
    return detector.assess_capability()
