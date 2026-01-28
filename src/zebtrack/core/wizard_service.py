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
import time
from contextlib import contextmanager
from typing import TYPE_CHECKING

import cv2
import numpy as np
import serial.tools.list_ports
import structlog

from zebtrack.io.arduino import Arduino

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

    # Class-level cache for hardware detection results
    _camera_cache: dict | None = None
    _camera_cache_time: float = 0.0
    _arduino_cache: dict | None = None
    _arduino_cache_time: float = 0.0
    _cache_ttl_seconds: float = 30.0  # Cache results for 30 seconds

    @staticmethod
    def validate_live_config(data: dict) -> tuple[bool, str]:
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
            if not isinstance(duration, (int, float)) or duration <= 0:
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
    def suppress_opencv_logs():
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
            cv2.setLogLevel(0)  # LOG_LEVEL_SILENT

            yield

        finally:
            # Restore stderr
            if old_stderr_fd is not None:
                os.dup2(old_stderr_fd, 2)
                os.close(old_stderr_fd)
            sys.stderr.close()
            sys.stderr = old_stderr
            # Restore OpenCV log level
            cv2.setLogLevel(3)  # LOG_LEVEL_ERROR

    @classmethod
    def clear_hardware_cache(cls):
        """Clear all hardware detection caches. Useful for testing or manual refresh."""
        cls._camera_cache = None
        cls._camera_cache_time = 0.0
        cls._arduino_cache = None
        cls._arduino_cache_time = 0.0
        log.debug("wizard_service.cache_cleared")

    @classmethod
    def _is_cache_valid(cls, cache_time: float) -> bool:
        """Check if cache is still valid based on TTL."""
        if cache_time == 0.0:
            return False
        elapsed = time.time() - cache_time
        return elapsed < cls._cache_ttl_seconds

    @classmethod
    def detect_available_cameras(cls, use_cache: bool = True) -> list[dict]:
        """
        Detect available cameras with early stopping optimization and caching.

        Uses DirectShow backend on Windows for better reliability.
        Stops detection after 3 consecutive failures to improve performance.
        Caches results for 30 seconds to avoid repeated detection calls.

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
                    "description": str,
                },
                ...
            ]
        """
        # Check cache first (with ghost camera detection, cache is now reliable)
        cache_is_valid = cls._is_cache_valid(cls._camera_cache_time)
        if use_cache and cls._camera_cache is not None and cache_is_valid:
            log.debug("wizard_service.detect_cameras.cache_hit")
            return cls._camera_cache

        log.info("wizard_service.detect_cameras.start")
        cameras = []
        consecutive_failures = 0
        max_consecutive_failures = 3

        # NOTE: Windows PnP camera name mapping disabled due to unreliable index
        # correlation between DirectShow and PnP device enumeration.
        # Using resolution-based descriptions instead.

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
                        test_result = {"success": False, "frame": None}
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
                                frame_shape=test_result["frame"].shape,
                                frame_mean=frame_mean,
                            )

                        # Reset consecutive failures on success
                        consecutive_failures = 0

                        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                        fps = cap.get(cv2.CAP_PROP_FPS)

                        # Generate descriptive name based on resolution
                        # Add camera counter to differentiate cameras with same resolution
                        camera_count = len(cameras) + 1  # 1-based counter

                        if width >= 1920 and height >= 1080:
                            resolution_desc = "Full HD (1920x1080)"
                        elif width >= 1280 and height >= 720:
                            resolution_desc = "HD (1280x720)"
                        elif width >= 640 and height >= 480:
                            resolution_desc = "SD (640x480)"
                        else:
                            resolution_desc = f"{width}x{height}"

                        description = f"Câmera #{camera_count} [índice {i}] - {resolution_desc}"

                        cameras.append(
                            {
                                "index": i,
                                "width": width,
                                "height": height,
                                "fps": fps,
                                "description": description,
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
        cls._camera_cache = cameras if cameras else None
        cls._camera_cache_time = time.time()

        return cameras

    @classmethod
    def detect_arduino_ports(
        cls, use_cache: bool = True, settings_obj: Settings | None = None
    ) -> list[dict]:
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
        cache_is_valid = cls._is_cache_valid(cls._arduino_cache_time)
        if use_cache and cls._arduino_cache is not None and cache_is_valid:
            log.debug("wizard_service.detect_arduino.cache_hit")
            return cls._arduino_cache

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
                    except Exception:
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

        except Exception as e:
            log.warning("wizard_service.detect_arduino.error", error=str(e))

        # Update cache
        cls._arduino_cache = ports_info
        cls._arduino_cache_time = time.time()

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
    def calculate_experiment_structure(groups: int, days: int, subjects: int) -> dict:
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
    def validate_experimental_design(data: dict) -> tuple[bool, str]:
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
    def validate_calibration_data(data: dict) -> tuple[bool, str]:
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
        if not isinstance(width, (int, float)) or width <= 0:
            return (False, "Largura do aquário deve ser maior que zero")

        height = data.get("aquarium_height_cm")
        if not isinstance(height, (int, float)) or height <= 0:
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
    def validate_basic_calibration(data: dict) -> tuple[bool, str]:
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
        if not isinstance(width, (int, float)) or width <= 0:
            return (False, "A largura do aquário deve ser maior que zero")

        height = data.get("aquarium_height_cm")
        if not isinstance(height, (int, float)) or height <= 0:
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
            except Exception:
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
