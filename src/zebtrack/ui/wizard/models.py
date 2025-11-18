"""
Pydantic models for wizard data validation.

These models provide type-safe, validated data structures for wizard steps,
replacing plain dictionaries with validated models that ensure data integrity.
"""

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class LiveConfigData(BaseModel):
    """Live configuration step data with validation."""

    camera_index: int = Field(ge=0, le=10, description="Camera device index")
    use_arduino: bool = Field(default=False, description="Enable Arduino integration")
    arduino_port: str | None = Field(default=None, description="Arduino serial port")
    use_timed_recording: bool = Field(
        default=False, description="Enable automatic recording duration limit"
    )
    recording_duration_s: float = Field(
        default=0, ge=0, le=7200, description="Recording duration in seconds (max 2 hours)"
    )
    use_countdown: bool = Field(default=False, description="Enable countdown before recording")
    countdown_duration_s: int = Field(
        default=0, ge=0, le=60, description="Countdown duration in seconds"
    )
    external_trigger_mode: bool = Field(
        default=False, description="Wait for external trigger signal from Arduino"
    )

    @field_validator("external_trigger_mode")
    @classmethod
    def validate_external_trigger(cls, v, info):
        """External trigger requires Arduino to be enabled."""
        if v and not info.data.get("use_arduino"):
            raise ValueError("Modo de trigger externo requer Arduino ativado")
        return v

    @field_validator("arduino_port")
    @classmethod
    def validate_arduino_port(cls, v, info):
        """Arduino port is required when Arduino is enabled."""
        if info.data.get("use_arduino") and not v:
            raise ValueError("Porta Arduino é obrigatória quando Arduino está ativado")
        return v

    @field_validator("countdown_duration_s")
    @classmethod
    def validate_countdown(cls, v, info):
        """Countdown duration must be >= 1 when countdown is enabled."""
        if info.data.get("use_countdown") and v < 1:
            raise ValueError("Duração de contagem regressiva deve ser >= 1 segundo quando ativada")
        return v

    @field_validator("recording_duration_s")
    @classmethod
    def validate_recording_duration(cls, v, info):
        """Validate that recording duration is > 0 when timed recording is enabled."""
        if info.data.get("use_timed_recording") and v <= 0:
            raise ValueError("Duração de gravação deve ser > 0 quando gravação temporizada ativada")
        return v


class ExperimentalDesignData(BaseModel):
    """Experimental design step data with validation."""

    experiment_days: int = Field(ge=1, le=365, description="Number of experiment days")
    num_groups: int = Field(ge=1, le=6, description="Number of experimental groups")
    subjects_per_group: int = Field(ge=1, le=20, description="Number of subjects per group")
    group_names: list[str] = Field(
        min_length=1, max_length=6, description="Names of experimental groups"
    )

    @field_validator("group_names")
    @classmethod
    def validate_unique_names(cls, v, info):
        """Group names must be unique and match num_groups."""
        num_groups = info.data.get("num_groups")

        # Check length matches
        if num_groups and len(v) != num_groups:
            raise ValueError(f"Esperado {num_groups} nomes de grupos, mas recebeu {len(v)}")

        # Check uniqueness
        if len(v) != len(set(v)):
            raise ValueError("Nomes de grupos devem ser únicos")

        # Check for empty names
        if any(not name.strip() for name in v):
            raise ValueError("Nomes de grupos não podem estar vazios")

        return v


class CalibrationData(BaseModel):
    """Calibration step data with validation."""

    num_aquariums: int = Field(ge=1, le=100, description="Number of aquariums/arenas")
    animals_per_aquarium: int = Field(ge=1, le=100, description="Number of animals per aquarium")
    aquarium_width_cm: float = Field(gt=0, description="Aquarium width in centimeters")
    aquarium_height_cm: float = Field(gt=0, description="Aquarium height in centimeters")
    analysis_interval_frames: int = Field(
        default=10, ge=1, le=30, description="Detection interval in frames"
    )
    display_interval_frames: int = Field(
        default=10, ge=1, le=30, description="Overlay update interval in frames"
    )
    roi_inclusion_rule: Literal[
        "bbox_intersects",
        "centroid_in",
        "centroid_in_on_buffered_roi",
        "seg_overlap",
    ] = Field(default="bbox_intersects", description="Rule for determining ROI inclusion")


class ModelSelectionData(BaseModel):
    """Model selection step data with validation."""

    detector_name: str = Field(min_length=1, description="Name of the detector to use")
    confidence_threshold: float | None = Field(
        default=None, ge=0.0, le=1.0, description="Detection confidence threshold"
    )
    nms_threshold: float | None = Field(
        default=None, ge=0.0, le=1.0, description="Non-maximum suppression threshold"
    )
    track_threshold: float | None = Field(
        default=None, ge=0.0, le=1.0, description="Tracking confidence threshold"
    )
    match_threshold: float | None = Field(
        default=None, ge=0.0, le=1.0, description="Track matching threshold"
    )

    @field_validator("detector_name")
    @classmethod
    def validate_detector_name(cls, v: str) -> str:
        """Validate detector name against available plugins."""
        try:
            from zebtrack.plugins import DETECTOR_PLUGINS

            available_detectors = list(DETECTOR_PLUGINS.keys())

            if v not in available_detectors:
                raise ValueError(
                    f"Detector '{v}' não encontrado.\n"
                    f"Detectores disponíveis: {', '.join(sorted(available_detectors))}"
                )
        except ImportError:
            # If plugins module not available, skip validation (e.g., during testing)
            pass

        return v


class FileSelectionData(BaseModel):
    """File selection step data with validation."""

    video_files: list[str] = Field(min_length=1, description="List of video file paths")

    @field_validator("video_files")
    @classmethod
    def validate_video_files(cls, v):
        """Validate video file paths: existence, format, and readability."""
        VIDEO_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv", ".flv", ".wmv", ".webm", ".m4v"}

        # Check for empty strings
        if any(not vf.strip() for vf in v):
            raise ValueError("Caminhos de vídeo não podem estar vazios")

        missing_files = []
        invalid_formats = []
        not_files = []

        for video_path in v:
            path = Path(video_path)

            # Check if file exists
            if not path.exists():
                missing_files.append(str(path))
                continue

            # Check if it's a file (not directory or special file)
            if not path.is_file():
                not_files.append(str(path))
                continue

            # Check file extension
            if path.suffix.lower() not in VIDEO_EXTENSIONS:
                invalid_formats.append(f"{path.name} ({path.suffix})")

        # Build comprehensive error message
        errors = []
        if missing_files:
            errors.append(
                "Arquivos não encontrados:\n  - " + "\n  - ".join(missing_files[:5])
                + (f"\n  ... e mais {len(missing_files) - 5}" if len(missing_files) > 5 else "")
            )

        if not_files:
            errors.append("Caminhos não são arquivos:\n  - " + "\n  - ".join(not_files[:5]))

        if invalid_formats:
            errors.append(
                "Formatos de vídeo inválidos:\n  - "
                + "\n  - ".join(invalid_formats[:5])
                + f"\n\nFormatos aceitos: {', '.join(sorted(VIDEO_EXTENSIONS))}"
            )

        if errors:
            raise ValueError("\n\n".join(errors))

        return v


class WizardData(BaseModel):
    """
    Complete wizard data with validation.

    This is the top-level model that aggregates all step data.
    """

    project_type: Literal["live", "pre-recorded", "exploratory"] = Field(
        description="Type of project being created"
    )
    wizard_mode: Literal["express", "advanced"] = Field(
        default="express", description="Wizard complexity mode"
    )

    # Step data (some are optional depending on project_type)
    live_config: LiveConfigData | None = Field(
        default=None, description="Live configuration (for live projects only)"
    )
    experimental_design: ExperimentalDesignData | None = Field(
        default=None, description="Experimental design (for live projects)"
    )
    calibration: CalibrationData = Field(description="Calibration settings")
    model_selection: ModelSelectionData | None = Field(
        default=None, description="Model selection (advanced mode only)"
    )
    file_selection: FileSelectionData | None = Field(
        default=None, description="File selection (for pre-recorded projects)"
    )

    @field_validator("live_config")
    @classmethod
    def validate_live_config_required(cls, v, info):
        """Live config is required for live projects."""
        if info.data.get("project_type") == "live" and v is None:
            raise ValueError("Configuração ao vivo é obrigatória para projetos live")
        return v

    @field_validator("file_selection")
    @classmethod
    def validate_file_selection_required(cls, v, info):
        """File selection is required for pre-recorded projects."""
        if info.data.get("project_type") == "pre-recorded" and v is None:
            raise ValueError("Seleção de arquivos é obrigatória para projetos pré-gravados")
        return v


# Type aliases for convenience
LiveConfig = LiveConfigData
ExperimentalDesign = ExperimentalDesignData
Calibration = CalibrationData
ModelSelection = ModelSelectionData
FileSelection = FileSelectionData
