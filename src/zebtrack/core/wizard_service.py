"""
Business logic service layer for wizard operations.

Extracts business logic from wizard UI steps to improve testability
and maintainability. All validation, hardware detection, and calculation
logic should live here instead of in the UI layer.
"""

import os
import sys
from contextlib import contextmanager

import cv2
import serial.tools.list_ports
import structlog

from zebtrack.io.arduino import Arduino
from zebtrack.settings import settings

log = structlog.get_logger()


class WizardService:
    """Business logic for wizard operations."""

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

    @staticmethod
    def detect_available_cameras() -> list[dict]:
        """
        Detect available cameras with early stopping optimization.

        Uses DirectShow backend on Windows for better reliability.
        Stops detection after 3 consecutive failures to improve performance.

        Returns:
            List of dictionaries with camera information:
            [
                {
                    "index": int,
                    "width": int,
                    "height": int,
                    "fps": float,
                },
                ...
            ]
        """
        log.info("wizard_service.detect_cameras.start")
        cameras = []
        consecutive_failures = 0
        max_consecutive_failures = 3

        with WizardService.suppress_opencv_logs():
            for i in range(10):
                try:
                    # Use DirectShow backend on Windows for better reliability
                    if sys.platform == "win32":
                        cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
                    else:
                        cap = cv2.VideoCapture(i)

                    if cap.isOpened():
                        cameras.append(
                            {
                                "index": i,
                                "width": int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                                "height": int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
                                "fps": cap.get(cv2.CAP_PROP_FPS),
                            }
                        )
                        cap.release()
                        consecutive_failures = 0  # Reset failure counter
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
        return cameras

    @staticmethod
    def detect_arduino_ports() -> list[dict]:
        """
        Detect available Arduino serial ports with descriptions.

        Uses Arduino.scan_available_ports to identify ports with handshake.

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
        log.info("wizard_service.detect_arduino.start")
        ports_info = []

        try:
            baud_rate = (
                getattr(getattr(settings, "arduino", None), "baud_rate", 9600) if settings else 9600
            )

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
        if not isinstance(animals, int) or animals < 1 or animals > 20:
            return (False, "Número de animais por aquário deve estar entre 1 e 20")

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

        if animals > 20:
            return (False, "O número de animais por aquário não pode exceder 20")

        # Dimensions validation
        width = data.get("aquarium_width_cm")
        if not isinstance(width, (int, float)) or width <= 0:
            return (False, "A largura do aquário deve ser maior que zero")

        height = data.get("aquarium_height_cm")
        if not isinstance(height, (int, float)) or height <= 0:
            return (False, "A altura do aquário deve ser maior que zero")

        return (True, "")
