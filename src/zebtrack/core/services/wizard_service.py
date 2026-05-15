"""
Business logic service layer for wizard operations.

Extracts business logic from wizard UI steps to improve testability
and maintainability. All validation, hardware detection, and calculation
logic should live here instead of in the UI layer.
"""

from __future__ import annotations

import os
import sys
import threading
from collections.abc import Generator
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, Literal

import cv2
import numpy as np
import serial.tools.list_ports
import structlog

from zebtrack.io.arduino import Arduino
from zebtrack.utils.cache import TTLCache

if TYPE_CHECKING:
    from zebtrack.settings import Settings
    from zebtrack.ui.wizard.models import MultiAquariumData

log = structlog.get_logger()


class WizardService:
    """
    Business logic for wizard operations.

    Features performance optimizations:
    - Hardware detection caching with configurable TTL
    - Lazy loading of heavy operations
    """

    # Phase 7.7: Unified hardware cache — replaces 6 class-level attributes
    # with a single TTLCache instance (thread-safe, automatic expiry).
    _hw_cache: TTLCache = TTLCache(ttl_seconds=30.0)

    @staticmethod
    def validate_live_config(data: dict[str, Any]) -> tuple[bool, str]:
        """
        Validate live configuration data.

        Args:
            data: Dictionary with live config keys:
                - camera_index: int
                - use_arduino: bool
                - arduino_port: str | None
                - use_timed_recording: bool
                - recording_duration_s: float
                - use_countdown: bool
                - countdown_duration_s: int
                - external_trigger_mode: bool

        Returns:
            Tuple of (is_valid, error_message)
        """
        # Camera validation
        camera_index = data.get("camera_index")
        if camera_index is None or not isinstance(camera_index, int):
            return (False, "Índice de câmera inválido")

        if camera_index < 0 or camera_index > 10:
            return (False, "Índice de câmera deve estar entre 0 e 10")

        # Arduino validation
        if data.get("use_arduino", False):
            arduino_port = data.get("arduino_port")
            if not arduino_port:
                return (False, "Porta Arduino deve ser especificada quando Arduino está ativado")

        # External trigger validation
        if data.get("external_trigger_mode", False):
            if not data.get("use_arduino", False):
                return (
                    False,
                    "Modo de trigger externo requer Arduino ativado",
                )

        # Timed recording validation
        if data.get("use_timed_recording", False):
            duration = data.get("recording_duration_s", 0)
            if not isinstance(duration, int | float) or duration <= 0:
                return (False, "Duração de gravação deve ser maior que zero")
            if duration > 7200:  # 2 hours max
                return (False, "Duração de gravação não pode exceder 2 horas (7200 segundos)")

        # Countdown validation
        if data.get("use_countdown", False):
            countdown = data.get("countdown_duration_s", 0)
            if not isinstance(countdown, int) or countdown < 1 or countdown > 60:
                return (False, "Contagem regressiva deve estar entre 1 e 60 segundos")

        return (True, "")

    @staticmethod
    @contextmanager
    def suppress_opencv_logs() -> Generator[None, None, None]:
        """
        Context manager to suppress OpenCV verbose output during camera detection.

        Redirects stderr to devnull and sets OpenCV log level to silent.
        """
        old_stderr_fd = None
        old_stderr = sys.stderr

        try:
            # Redirect stderr to devnull
            old_stderr_fd = os.dup(2)
            devnull = os.open(os.devnull, os.O_WRONLY)
            os.dup2(devnull, 2)
            os.close(devnull)
            sys.stderr = open(os.devnull, "w")

            # Also set OpenCV log level to ERROR
            cv2.utils.logging.setLogLevel(0)  # type: ignore[attr-defined]  # LOG_LEVEL_SILENT

            yield

        finally:
            # Restore stderr
            if old_stderr_fd is not None:
                os.dup2(old_stderr_fd, 2)
                os.close(old_stderr_fd)
            sys.stderr.close()
            sys.stderr = old_stderr
            # Restore OpenCV log level
            cv2.utils.logging.setLogLevel(3)  # type: ignore[attr-defined]  # LOG_LEVEL_ERROR

    @classmethod
    def clear_hardware_cache(cls) -> None:
        """Clear all hardware detection caches. Useful for testing or manual refresh."""
        cls._hw_cache.clear()
        log.debug("wizard_service.cache_cleared")

    @staticmethod
    def _get_dshow_friendly_names() -> list[str]:
        """Return DirectShow input device names in enumeration order (Windows only).

        The position of each name in this list matches the index that OpenCV's
        ``cv2.VideoCapture(i, cv2.CAP_DSHOW)`` will open, because both rely on
        the same DirectShow moniker enumeration.

        Returns an empty list on non-Windows platforms or if pygrabber is not
        installed (graceful degradation — caller falls back to resolution-only
        descriptions).
        """
        if sys.platform != "win32":
            return []
        try:
            from pygrabber.dshow_graph import FilterGraph
        except ImportError:
            log.debug("wizard_service.pygrabber_not_available")
            return []

        try:
            names = FilterGraph().get_input_devices()
        # except Exception justified: COM/DirectShow enumeration is hardware-dependent
        except Exception as e:
            log.warning("wizard_service.dshow_friendly_names.failed", error=str(e))
            return []

        # Dedupe identical names (e.g. two webcams of the same model) by appending (#N).
        seen: dict[str, int] = {}
        deduped: list[str] = []
        for name in names:
            count = seen.get(name, 0) + 1
            seen[name] = count
            deduped.append(name if count == 1 else f"{name} (#{count})")
        return deduped

    @classmethod
    def detect_available_cameras(cls, use_cache: bool = True) -> list[dict[str, Any]]:
        """
        Detect available cameras with early stopping optimization and caching.

        Uses DirectShow backend on Windows for better reliability.
        Stops detection after 3 consecutive failures to improve performance.
        Caches results for 30 seconds to avoid repeated detection calls.

        On Windows, friendly device names are obtained via pygrabber's DirectShow
        enumeration (position-correlated with the OpenCV index). On other platforms
        or when pygrabber is unavailable, descriptions fall back to resolution-only.

        Args:
            use_cache: If True, return cached results if available and valid.
                      If False, force fresh detection.

        Returns:
            List of dictionaries with camera information:
            [
                {
                    "index": int,
                    "width": int,
                    "height": int,
                    "fps": float,
                    "friendly_name": str,  # may be "" when pygrabber unavailable
                    "description": str,
                },
                ...
            ]
        """
        # Check cache first (with ghost camera detection, cache is now reliable)
        if use_cache:
            cached = cls._hw_cache.get("cameras")
            if cached is not None:
                log.debug("wizard_service.detect_cameras.cache_hit")
                return cached

        log.info("wizard_service.detect_cameras.start")
        cameras: list[dict[str, Any]] = []
        consecutive_failures = 0
        max_consecutive_failures = 3

        # Friendly DirectShow names (Windows + pygrabber). Position == cv2 DSHOW index.
        # Falls back to [] on other platforms or if pygrabber is unavailable.
        friendly_names = cls._get_dshow_friendly_names()

        with cls.suppress_opencv_logs():
            for i in range(6):  # Scan indices 0-5 instead of 0-9
                try:
                    # Use DirectShow backend on Windows for better reliability
                    if sys.platform == "win32":
                        cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
                    else:
                        cap = cv2.VideoCapture(i)

                    if cap.isOpened():
                        # CRITICAL: Verify camera can actually capture frames with timeout
                        # Some cameras report isOpened=True but never return frames (ghost cameras)
                        test_result: dict[str, Any] = {"success": False, "frame": None}
                        result_lock = threading.Lock()
                        read_event = threading.Event()

                        def try_read(
                            capture=cap,
                            result=test_result,
                            camera_index=i,
                            lock=result_lock,
                            event=read_event,
                        ):
                            try:
                                ret, frame = capture.read()
                                with lock:
                                    result["success"] = ret
                                    result["frame"] = frame
                            # except Exception justified: cv2 camera probe - hardware I/O
                            except Exception as e:
                                log.warning(
                                    "wizard_service.camera_read_exception",
                                    index=camera_index,
                                    error=str(e),
                                )
                                with lock:
                                    result["success"] = False
                            finally:
                                event.set()

                        log.debug("wizard_service.testing_camera_capture", index=i)
                        read_thread = threading.Thread(target=try_read, daemon=True)
                        read_thread.start()
                        read_event.wait(timeout=2.0)  # Wait for completion signal

                        with result_lock:
                            if not test_result["success"] or test_result["frame"] is None:
                                log.warning(
                                    "wizard_service.camera_ghost_detected",
                                    index=i,
                                    reason="isOpened=True but read() failed or timed out",
                                    success=test_result["success"],
                                    frame_is_none=test_result["frame"] is None,
                                )
                                cap.release()
                                consecutive_failures += 1
                                if consecutive_failures >= max_consecutive_failures:
                                    log.info(
                                        "wizard_service.max_consecutive_failures_reached",
                                        index=i,
                                    )
                                    break
                                continue

                            # CRITICAL: Check if frame is completely black
                            # (virtual camera with no content)
                            frame_mean = np.mean(test_result["frame"])
                            if frame_mean < 5.0:  # Nearly black frame
                                log.warning(
                                    "wizard_service.camera_black_frame_detected",
                                    index=i,
                                    frame_mean=frame_mean,
                                    reason="Camera returns black/empty frames",
                                )
                                cap.release()
                                consecutive_failures += 1
                                if consecutive_failures >= max_consecutive_failures:
                                    log.info(
                                        "wizard_service.max_consecutive_failures_reached",
                                        index=i,
                                    )
                                    break
                                continue

                            log.info(
                                "wizard_service.camera_validated",
                                index=i,
                                frame_shape=test_result["frame"].shape
                                if test_result["frame"] is not None
                                else None,
                                frame_mean=frame_mean,
                            )

                        # Reset consecutive failures on success
                        consecutive_failures = 0

                        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                        fps = cap.get(cv2.CAP_PROP_FPS)

                        if width >= 1920 and height >= 1080:
                            resolution_desc = "Full HD (1920x1080)"
                        elif width >= 1280 and height >= 720:
                            resolution_desc = "HD (1280x720)"
                        elif width >= 640 and height >= 480:
                            resolution_desc = "SD (640x480)"
                        else:
                            resolution_desc = f"{width}x{height}"

                        # Friendly name comes from DirectShow enumeration (Windows + pygrabber).
                        # Position in friendly_names matches the DSHOW index `i`.
                        friendly_name = friendly_names[i] if i < len(friendly_names) else ""

                        if friendly_name:
                            description = f"{friendly_name} [índice {i}] - {resolution_desc}"
                        else:
                            # Fallback: numbered description (non-Windows or pygrabber missing)
                            camera_count = len(cameras) + 1
                            description = f"Câmera #{camera_count} [índice {i}] - {resolution_desc}"

                        cameras.append(
                            {
                                "index": i,
                                "width": width,
                                "height": height,
                                "fps": float(fps),
                                "friendly_name": friendly_name,
                                "description": str(description),
                            }
                        )
                        cap.release()
                    else:
                        consecutive_failures += 1
                        # Stop early if we hit too many consecutive failures
                        if consecutive_failures >= max_consecutive_failures:
                            log.debug(
                                "wizard_service.detect_cameras.early_stop",
                                consecutive_failures=consecutive_failures,
                            )
                            break

                # except Exception justified: cv2 VideoCapture probe per index — hardware-dependent
                except Exception as e:
                    log.debug("wizard_service.detect_cameras.error", index=i, error=str(e))
                    consecutive_failures += 1
                    if consecutive_failures >= max_consecutive_failures:
                        break

        log.info(
            "wizard_service.detect_cameras.complete",
            count=len(cameras),
            indices=[c["index"] for c in cameras],
        )

        # Update cache
        if cameras:
            cls._hw_cache.set("cameras", cameras)
        else:
            cls._hw_cache.invalidate("cameras")

        return cameras

    @classmethod
    def resolve_camera_index(
        cls, saved_index: int, saved_name: str
    ) -> tuple[int, Literal["MATCH", "SHIFTED", "MISSING"]]:
        """Resolve a saved camera index against the current DirectShow enumeration.

        Uses the lightweight pygrabber enumeration only — it reads DirectShow
        device monikers without ever opening (and therefore activating) any
        camera. This is critical: the heavier ``detect_available_cameras``
        probe opens ``cv2.VideoCapture`` for every index 0–5, which on some
        drivers leaves the camera LED on or busy for a moment. Calling that
        probe at every session start would unnecessarily wake up every
        connected device.

        DirectShow's index ordering can shift between sessions (USB replug,
        suspend/resume, virtual cameras toggling). The friendly-name lookup
        recovers the current index without touching the hardware.

        Args:
            saved_index: Camera index originally chosen in the wizard.
            saved_name: Friendly DirectShow name saved at wizard time. Empty
                string for legacy projects (predates this feature).

        Returns:
            ``(index_to_use, status)`` where status is:
            - ``"MATCH"``: friendly name matched and index is unchanged
              (or no saved name / no enumeration available — we trust the
              saved index for compatibility).
            - ``"SHIFTED"``: friendly name matched at a *different* index
              (transparent recovery — caller should log).
            - ``"MISSING"``: friendly name not found in the current enumeration
              (caller should prompt the user; do NOT silently fall back to
              ``saved_index``, which may now point to the wrong device).
        """
        if not saved_name:
            # Legacy project (no friendly_name persisted). Trust the saved index.
            return (saved_index, "MATCH")

        friendly_names = cls._get_dshow_friendly_names()
        if not friendly_names:
            # Non-Windows or pygrabber unavailable: nothing to verify against,
            # trust the saved index. Avoids opening cameras just to enumerate.
            return (saved_index, "MATCH")

        for i, name in enumerate(friendly_names):
            if name == saved_name:
                status: Literal["MATCH", "SHIFTED"] = "MATCH" if i == saved_index else "SHIFTED"
                return (i, status)

        return (saved_index, "MISSING")

    @classmethod
    def detect_arduino_ports(
        cls, use_cache: bool = True, settings_obj: Settings | None = None
    ) -> list[dict[str, Any]]:
        """
        Detect available Arduino serial ports with descriptions and caching.

        Uses Arduino.scan_available_ports to identify ports with handshake.
        Caches results for 30 seconds to avoid repeated detection calls.

        Args:
            use_cache: If True, return cached results if available and valid.
                      If False, force fresh detection.
            settings_obj: Settings instance for baud rate (uses 9600 if None).

        Returns:
            List of dictionaries with port information:
            [
                {
                    "device": str,  # e.g., "COM3"
                    "description": str,  # e.g., "Arduino Uno"
                    "has_handshake": bool,
                    "display_name": str,  # e.g., "COM3 - Arduino Uno"
                },
                ...
            ]
        """
        # Check cache first
        if use_cache:
            cached = cls._hw_cache.get("arduino")
            if cached is not None:
                log.debug("wizard_service.detect_arduino.cache_hit")
                return cached

        log.info("wizard_service.detect_arduino.start")
        ports_info = []

        try:
            # Get baud rate from settings or use default
            baud_rate = 9600
            if settings_obj and hasattr(settings_obj, "arduino"):
                baud_rate = getattr(settings_obj.arduino, "baud_rate", 9600)

            handshake_ports, fallback_ports = Arduino.scan_available_ports(baud_rate=baud_rate)

            # Process handshake ports first (these responded to Arduino handshake)
            for port in handshake_ports:
                device_id = getattr(port, "device", None)
                if device_id:
                    description = getattr(port, "description", device_id)
                    display_name = f"{device_id} - {description}"
                    ports_info.append(
                        {
                            "device": device_id,
                            "description": description,
                            "has_handshake": True,
                            "display_name": display_name,
                        }
                    )

            # If we found handshake ports, also add fallback ports with indicator
            if handshake_ports:
                for port in fallback_ports:
                    device_id = getattr(port, "device", None)
                    if device_id:
                        description = getattr(port, "description", device_id)
                        display_name = f"{device_id} - {description} [sem handshake]"
                        ports_info.append(
                            {
                                "device": device_id,
                                "description": description,
                                "has_handshake": False,
                                "display_name": display_name,
                            }
                        )
            else:
                # No handshake ports found, use all fallback ports
                if not fallback_ports:
                    # Ensure we still list raw ports if probe yielded nothing
                    try:
                        fallback_ports = list(serial.tools.list_ports.comports())
                    except OSError:
                        fallback_ports = []

                for port in fallback_ports:
                    device_id = getattr(port, "device", None)
                    if device_id:
                        description = getattr(port, "description", device_id)
                        display_name = f"{device_id} - {description}"
                        ports_info.append(
                            {
                                "device": device_id,
                                "description": description,
                                "has_handshake": False,
                                "display_name": display_name,
                            }
                        )

            log.info(
                "wizard_service.detect_arduino.complete",
                total_ports=len(ports_info),
                handshake_count=len(handshake_ports),
            )

        # except Exception justified: serial probing + handshake — hardware I/O boundary
        except Exception as e:
            log.warning("wizard_service.detect_arduino.error", error=str(e))

        # Update cache
        cls._hw_cache.set("arduino", ports_info)

        return ports_info

    @staticmethod
    def suggest_analysis_interval(camera_fps: float) -> int:
        """
        Suggest analysis interval based on camera FPS.

        Aims for approximately 3 analyses per second.

        Args:
            camera_fps: Camera frames per second

        Returns:
            Suggested interval in frames (minimum 1)
        """
        if camera_fps <= 0:
            return 10  # Default fallback

        # Target ~3 analyses per second
        suggested = max(1, int(camera_fps / 3))
        log.debug(
            "wizard_service.suggest_interval",
            camera_fps=camera_fps,
            suggested_interval=suggested,
        )
        return suggested

    @staticmethod
    def calculate_experiment_structure(
        groups: int, days: int, subjects: int
    ) -> dict[str, int | float]:
        """
        Calculate experiment size and structure metrics.

        Args:
            groups: Number of experimental groups
            days: Number of days in experiment
            subjects: Number of subjects per group

        Returns:
            Dictionary with experiment metrics:
            {
                "total_sessions": int,
                "total_animals": int,
                "sessions_per_day": int,
                "estimated_hours": float,  # Assuming 30min per session
            }
        """
        total_sessions = groups * days * subjects
        total_animals = groups * subjects
        sessions_per_day = groups * subjects

        # Estimate time: assuming 30 minutes per session
        estimated_hours = total_sessions * 0.5

        metrics = {
            "total_sessions": total_sessions,
            "total_animals": total_animals,
            "sessions_per_day": sessions_per_day,
            "estimated_hours": estimated_hours,
        }

        log.debug(
            "wizard_service.calculate_experiment",
            groups=groups,
            days=days,
            subjects=subjects,
            metrics=metrics,
        )

        return metrics

    @staticmethod
    def validate_experimental_design(data: dict[str, Any]) -> tuple[bool, str]:
        """
        Validate experimental design data.

        Args:
            data: Dictionary with experimental design keys:
                - experiment_days: int
                - num_groups: int
                - subjects_per_group: int
                - group_names: list[str]

        Returns:
            Tuple of (is_valid, error_message)
        """
        # Days validation
        days = data.get("experiment_days")
        if not isinstance(days, int) or days < 1 or days > 365:
            return (False, "Número de dias deve estar entre 1 e 365")

        # Groups validation
        num_groups = data.get("num_groups")
        if not isinstance(num_groups, int) or num_groups < 1 or num_groups > 6:
            return (False, "Número de grupos deve estar entre 1 e 6")

        # Subjects validation
        subjects = data.get("subjects_per_group")
        if not isinstance(subjects, int) or subjects < 1 or subjects > 20:
            return (False, "Número de sujeitos por grupo deve estar entre 1 e 20")

        # Group names validation
        group_names = data.get("group_names", [])
        if not isinstance(group_names, list):
            return (False, "Nomes de grupos devem ser uma lista")

        if len(group_names) != num_groups:
            return (False, f"Esperado {num_groups} nomes de grupos, mas recebeu {len(group_names)}")

        # Check for unique names
        if len(set(group_names)) != len(group_names):
            return (False, "Nomes de grupos devem ser únicos")

        # Check for empty names
        if any(not name.strip() for name in group_names):
            return (False, "Nomes de grupos não podem estar vazios")

        return (True, "")

    @staticmethod
    def validate_calibration_data(data: dict[str, Any]) -> tuple[bool, str]:
        """
        Validate calibration step data.

        Args:
            data: Dictionary with calibration keys:
                - num_aquariums: int
                - animals_per_aquarium: int
                - aquarium_width_cm: float
                - aquarium_height_cm: float
                - analysis_interval_frames: int
                - display_interval_frames: int
                - roi_inclusion_rule: str

        Returns:
            Tuple of (is_valid, error_message)
        """
        # Aquariums validation
        num_aquariums = data.get("num_aquariums")
        if not isinstance(num_aquariums, int) or num_aquariums < 1 or num_aquariums > 100:
            return (False, "Número de aquários deve estar entre 1 e 100")

        # Animals per aquarium validation
        animals = data.get("animals_per_aquarium")
        if not isinstance(animals, int) or animals < 1 or animals > 100:
            return (False, "Número de animais por aquário deve estar entre 1 e 100")

        # Dimensions validation
        width = data.get("aquarium_width_cm")
        if not isinstance(width, int | float) or width <= 0:
            return (False, "Largura do aquário deve ser maior que zero")

        height = data.get("aquarium_height_cm")
        if not isinstance(height, int | float) or height <= 0:
            return (False, "Altura do aquário deve ser maior que zero")

        # Intervals validation
        analysis_interval = data.get("analysis_interval_frames")
        if (
            not isinstance(analysis_interval, int)
            or analysis_interval < 1
            or analysis_interval > 30
        ):
            return (False, "Intervalo de análise deve estar entre 1 e 30 frames")

        display_interval = data.get("display_interval_frames")
        if not isinstance(display_interval, int) or display_interval < 1 or display_interval > 30:
            return (False, "Intervalo de exibição deve estar entre 1 e 30 frames")

        # ROI inclusion rule validation
        valid_rules = [
            "bbox_intersects",
            "centroid_in",
            "centroid_in_on_buffered_roi",
            "seg_overlap",
        ]
        roi_rule = data.get("roi_inclusion_rule")
        if roi_rule not in valid_rules:
            return (
                False,
                f"Regra de inclusão ROI inválida. Deve ser uma de: {', '.join(valid_rules)}",
            )

        return (True, "")

    @staticmethod
    def validate_basic_calibration(data: dict[str, Any]) -> tuple[bool, str]:
        """
        Validate basic calibration data (without intervals and ROI rules).

        This is used by the simplified CalibrationStep that only collects
        aquarium dimensions and animal count.

        Args:
            data: Dictionary with basic calibration keys:
                - num_aquariums: int
                - animals_per_aquarium: int
                - aquarium_width_cm: float
                - aquarium_height_cm: float

        Returns:
            Tuple of (is_valid, error_message)
        """
        # Aquariums validation
        num_aquariums = data.get("num_aquariums")
        if not isinstance(num_aquariums, int) or num_aquariums < 1:
            return (False, "O número de aquários deve ser pelo menos 1")

        if num_aquariums > 100:
            return (False, "O número de aquários não pode exceder 100")

        # Animals per aquarium validation
        animals = data.get("animals_per_aquarium")
        if not isinstance(animals, int) or animals < 1:
            return (False, "O número de animais por aquário deve ser pelo menos 1")

        if animals > 100:
            return (False, "O número de animais por aquário não pode exceder 100")

        # Dimensions validation
        width = data.get("aquarium_width_cm")
        if not isinstance(width, int | float) or width <= 0:
            return (False, "A largura do aquário deve ser maior que zero")

        height = data.get("aquarium_height_cm")
        if not isinstance(height, int | float) or height <= 0:
            return (False, "A altura do aquário deve ser maior que zero")

        return (True, "")

    @staticmethod
    def validate_multi_aquarium_config(  # noqa: C901
        config: MultiAquariumData,
        sample_filenames: list[str] | None = None,
    ) -> tuple[bool, list[str], list[str]]:
        """
        Validate multi-aquarium configuration.

        Phase 3.2: Enhanced validation with warnings for potential issues.

        Performs the following checks:
        1. If enabled, must have exactly 2 aquariums configured
        2. If regex is provided, it must be valid
        3. If regex is provided, it must capture expected fields
        4. If sample filenames provided, test regex against them
        5. [Warning] Check for aquarium polygon overlap
        6. [Warning] Check for very small aquarium areas

        Args:
            config: MultiAquariumData configuration to validate
            sample_filenames: Optional list of filenames to test regex against

        Returns:
            Tuple of (is_valid, list of error messages, list of warning messages)
        """
        import re

        from zebtrack.ui.wizard.models import MultiAquariumData

        errors: list[str] = []
        warnings: list[str] = []

        # Type check for proper configuration object
        if not isinstance(config, MultiAquariumData):
            # Try dict-like access for backwards compatibility
            try:
                enabled = (
                    config.get("enabled", False)
                    if hasattr(config, "get")
                    else getattr(config, "enabled", False)
                )
            except (AttributeError, TypeError):
                errors.append("Configuração multi-aquário inválida")
                return False, errors, warnings
        else:
            enabled = config.enabled

        # If not enabled, no validation needed
        if not enabled:
            return True, [], []

        # Check 1: Number of aquariums
        if isinstance(config, MultiAquariumData):
            aquarium_configs = config.aquarium_configs
            regex_pattern = config.regex_pattern
            regex_group_field = config.regex_group_field
            regex_subject_field = config.regex_subject_field
        else:
            aquarium_configs = config.get("aquarium_configs", [])
            regex_pattern = config.get("regex_pattern", "")
            regex_group_field = config.get("regex_group_field", "group")
            regex_subject_field = config.get("regex_subject_field", "subject")

        if len(aquarium_configs) != 2:
            errors.append("Exatamente 2 aquários devem ser configurados")

        # Phase 3.2: Check aquarium configurations for potential issues
        for i, aq_config in enumerate(aquarium_configs):
            polygon = getattr(aq_config, "polygon", None)
            if polygon is None and hasattr(aq_config, "get"):
                polygon = aq_config.get("polygon", [])
            if polygon and len(polygon) >= 3:
                # Calculate approximate area
                import numpy as np

                pts = np.array(polygon)
                # Shoelace formula for polygon area
                n = len(pts)
                if n >= 3:
                    area = 0.5 * abs(
                        sum(
                            pts[i][0] * pts[(i + 1) % n][1] - pts[(i + 1) % n][0] * pts[i][1]
                            for i in range(n)
                        )
                    )
                    if area < 10000:  # Less than ~100x100 pixels
                        warnings.append(
                            f"Aquário {i} tem área muito pequena ({int(area)} px²). "
                            "Pode afetar precisão da detecção."
                        )

        # Check for polygon overlap (only if 2 aquariums)
        if len(aquarium_configs) == 2:
            import numpy as np

            poly1 = getattr(aquarium_configs[0], "polygon", None)
            if poly1 is None and hasattr(aquarium_configs[0], "get"):
                poly1 = aquarium_configs[0].get("polygon", [])
            poly2 = getattr(aquarium_configs[1], "polygon", None)
            if poly2 is None and hasattr(aquarium_configs[1], "get"):
                poly2 = aquarium_configs[1].get("polygon", [])
            if poly1 and poly2:
                import cv2

                pts1 = np.array(poly1, dtype=np.int32)
                pts2 = np.array(poly2, dtype=np.int32)

                # Check if bounding boxes overlap
                x1, y1, w1, h1 = cv2.boundingRect(pts1)
                x2, y2, w2, h2 = cv2.boundingRect(pts2)

                # Check for intersection
                if not (x1 + w1 < x2 or x2 + w2 < x1 or y1 + h1 < y2 or y2 + h2 < y1):
                    warnings.append(
                        "Polígonos dos aquários parecem se sobrepor. "
                        "Isso pode causar detecções duplicadas."
                    )

        # Check 2: Validate regex if provided
        if regex_pattern:
            try:
                compiled = re.compile(regex_pattern)
                groups = set(compiled.groupindex.keys())

                # Check if expected fields are captured
                expected = {regex_group_field, regex_subject_field}
                missing = expected - groups
                if missing:
                    errors.append(f"Regex não captura campos esperados: {missing}")

                # Check 3: Test against sample filenames
                if sample_filenames:
                    unmatched = []
                    for filename in sample_filenames[:3]:  # Test first 3
                        match = compiled.search(filename)
                        if not match:
                            unmatched.append(filename)

                    if unmatched:
                        errors.append(
                            f"Regex não corresponde a arquivos: {', '.join(unmatched[:2])}"
                        )

            except re.error as e:
                errors.append(f"Padrão regex inválido: {e}")

        log.debug(
            "wizard_service.validate_multi_aquarium_config",
            enabled=enabled,
            config_count=len(aquarium_configs),
            has_regex=bool(regex_pattern),
            errors=errors,
            warnings=warnings,
        )

        return len(errors) == 0, errors, warnings
