"""
Configuration Validator.

Handles validation of application configuration settings and UI form values.
"""

from typing import Any
from pydantic import ValidationError
from zebtrack.settings import Settings

class ConfigValidator:
    """Validator for configuration settings."""

    @staticmethod
    def validate_form_values(values: dict) -> tuple[bool, str]:
        """
        Validate raw configuration values from UI form.

        Args:
            values: Dictionary of config values from widget

        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            # Extract values
            fps = values["video_processing"]["fps"]
            processing_interval = values["video_processing"]["processing_interval"]
            processing_offset = values["video_processing"]["processing_offset"]
            flush_interval = values["recorder"]["flush_interval_seconds"]
            flush_rows = values["recorder"]["flush_row_threshold"]
            window_length = values["trajectory_smoothing"]["window_length"]
            polyorder = values["trajectory_smoothing"]["polyorder"]

            # Validate ranges
            if fps <= 0:
                raise ValueError("FPS deve ser maior que 0.")
            if processing_interval <= 0:
                raise ValueError("O intervalo de processamento deve ser maior que 0.")
            if processing_offset < 0:
                raise ValueError("O offset deve ser maior ou igual a 0.")
            if flush_interval < 0:
                raise ValueError("O intervalo de flush deve ser >= 0.")
            if flush_rows < 1:
                raise ValueError("O limite de linhas para flush deve ser >= 1.")
            if window_length < 3 or window_length % 2 == 0:
                raise ValueError("Window length deve ser ímpar e pelo menos 3.")
            if polyorder < 1:
                raise ValueError("Polyorder deve ser pelo menos 1.")

            return True, ""

        except (KeyError, ValueError, TypeError) as exc:
            return False, str(exc)

    @staticmethod
    def validate_pydantic_model(settings_dict: dict) -> tuple[bool, str, Settings | None]:
        """
        Validate configuration dictionary against Pydantic Settings model.

        Args:
            settings_dict: Dictionary matching Settings model structure

        Returns:
            Tuple of (is_valid, error_message, validated_settings_object)
        """
        try:
            validated = Settings.model_validate(settings_dict)
            return True, "", validated
        except ValidationError as exc:
            return False, str(exc), None

    @staticmethod
    def validate_roi_settings(buffer_radius: float, overlap_ratio: float) -> tuple[bool, str]:
        """
        Validate ROI inclusion rule settings.

        Args:
            buffer_radius: Radius for ROI buffer
            overlap_ratio: Minimum overlap ratio (0-1)

        Returns:
            Tuple of (is_valid, error_message)
        """
        if buffer_radius < 0:
            return False, "Raio de buffer deve ser >= 0"
        if not (0 <= overlap_ratio <= 1):
            return False, "Fração de sobreposição deve estar entre 0 e 1"
        return True, ""
