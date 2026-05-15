"""
Pydantic models for wizard data validation.

These models provide type-safe, validated data structures for wizard steps,
replacing plain dictionaries with validated models that ensure data integrity.
"""

import re
from enum import StrEnum
from pathlib import Path
from typing import Literal

import structlog
from pydantic import BaseModel, Field, field_validator, model_validator

log = structlog.get_logger()

# =============================================================================
# Behavioral Analysis Enums and Models
# =============================================================================


class AquariumPerspective(StrEnum):
    """Perspective/view angle of the aquarium camera.

    This affects which behavioral metrics can be calculated:
    - TOP_DOWN: Camera above the aquarium looking down. Thigmotaxis available.
    - LATERAL: Camera on the side of the aquarium. Both thigmotaxis and geotaxis available.
    """

    TOP_DOWN = "top_down"
    LATERAL = "lateral"


class GeotaxisMode(StrEnum):
    """Mode for calculating geotaxis (preference for bottom of aquarium).

    - DISTANCE: Use a fixed distance threshold from the bottom.
    - ZONES: Divide the aquarium height into N equal zones.
    """

    DISTANCE = "distance"
    ZONES = "zones"


class BehavioralAnalysisData(BaseModel):
    """Configuration for behavioral analysis metrics.

    Controls thigmotaxis (wall preference) and geotaxis (bottom preference) parameters.
    Geotaxis is only available for lateral perspective views.
    """

    aquarium_perspective: AquariumPerspective = Field(
        default=AquariumPerspective.TOP_DOWN,
        description="Camera perspective/view angle of the aquarium",
    )
    thigmotaxis_distance_cm: float = Field(
        default=1.5,
        ge=0.1,
        le=10.0,
        description="Distance threshold (cm) for thigmotaxis 'near wall' calculation",
    )
    geotaxis_enabled: bool = Field(
        default=False,
        description="Enable geotaxis analysis (only for lateral perspective)",
    )
    geotaxis_mode: GeotaxisMode = Field(
        default=GeotaxisMode.DISTANCE,
        description="Mode for geotaxis calculation",
    )
    geotaxis_distance_cm: float = Field(
        default=1.5,
        ge=0.1,
        le=10.0,
        description="Distance threshold (cm) for geotaxis 'near bottom' calculation",
    )
    geotaxis_num_zones: int = Field(
        default=3,
        ge=2,
        le=10,
        description="Number of vertical zones to divide the aquarium into",
    )
    geotaxis_bottom_zones: int = Field(
        default=1,
        ge=1,
        le=2,
        description="Number of bottom zones to consider as 'bottom' (1 or 2)",
    )

    @model_validator(mode="after")
    def validate_geotaxis_settings(self) -> "BehavioralAnalysisData":
        """Validate geotaxis settings based on perspective and mode."""
        # Geotaxis requires lateral perspective
        if self.aquarium_perspective == AquariumPerspective.TOP_DOWN:
            # Force disable geotaxis for top-down perspective
            object.__setattr__(self, "geotaxis_enabled", False)

        # Validate zone settings
        if self.geotaxis_enabled and self.geotaxis_mode == GeotaxisMode.ZONES:
            if self.geotaxis_bottom_zones > self.geotaxis_num_zones:
                raise ValueError(
                    f"geotaxis_bottom_zones ({self.geotaxis_bottom_zones}) cannot exceed "
                    f"geotaxis_num_zones ({self.geotaxis_num_zones})"
                )

        return self


# =============================================================================
# Wizard Step Models
# =============================================================================


class LiveConfigData(BaseModel):
    """Live configuration step data with validation."""

    camera_index: int = Field(ge=0, le=10, description="Camera device index")
    camera_friendly_name: str = Field(
        default="",
        description=(
            "DirectShow friendly name of the chosen camera. Used at recording time to "
            "re-resolve the index if DirectShow ordering shifts (USB replug, etc.). "
            "Empty when pygrabber is unavailable or for legacy projects."
        ),
    )
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


class AquariumConfig(BaseModel):
    """Configuration for an aquarium in multi-aquarium mode.

    Stores experimental metadata associated with each individual aquarium
    within a video containing multiple aquariums.
    """

    aquarium_id: int = Field(ge=0, le=1, description="ID do aquário (0 ou 1)")
    group: str = Field(min_length=1, description="Grupo experimental (ex: Controle, Tratamento)")
    subject_id: str = Field(default="", description="Identificador único do sujeito")
    day: int = Field(default=1, ge=1, description="Dia do experimento")

    @field_validator("group")
    @classmethod
    def validate_group_not_empty(cls, v: str) -> str:
        """Group must not be empty or contain only spaces."""
        if not v.strip():
            raise ValueError("Nome do grupo não pode estar vazio")
        return v.strip()


class MultiAquariumData(BaseModel):
    """Configuration data for videos with 2 aquariums.

    Controls whether multi-aquarium mode is enabled and stores
    metadata extraction configurations via regex.
    """

    enabled: bool = Field(default=False, description="Se modo multi-aquário está habilitado")
    aquarium_configs: list[AquariumConfig] = Field(
        default_factory=list,
        max_length=2,
        description="Configurações dos aquários (máximo 2)",
    )
    regex_pattern: str = Field(
        default="",
        description="Padrão regex para extração de metadados do nome do arquivo",
    )
    regex_group_field: str = Field(
        default="group",
        description="Nome do grupo de captura para o grupo experimental",
    )
    regex_subject_field: str = Field(
        default="subject",
        description="Nome do grupo de captura para o identificador do sujeito",
    )
    regex_day_field: str = Field(
        default="day",
        description="Nome do grupo de captura para o dia do experimento",
    )

    @staticmethod
    def build_combined_regex_pattern(
        group_pattern: str | None = None,
        day_pattern: str | None = None,
        subject_pattern: str | None = None,
        *,
        separator: str = r"(?:--|_)",
    ) -> str:
        """Build a combined regex pattern from individual patterns.

        Combines separate group, day, and subject patterns into a single
        pattern with named capture groups that can be used with ``re.finditer``
        to extract multiple subjects from filenames like ``G1_D1_S1--G1_D1_S2``.

        Supports two pattern styles:

        **Atomic** (short, prefix-only):
            ``G(\\d+)`` — captures only the field of interest.
            These are joined with ``_`` to form a combined pattern like
            ``G(?P<group>\\d+)_D(?P<day>\\d+)_S(?P<subject>\\d+)``.

        **Full-context** (each pattern contains separators / other fields):
            ``(G\\d+)_D\\d+_C\\d+`` — already matches the whole block.
            Joining these with ``_`` would produce an invalid pattern.
            In this case we build a single self-contained pattern from
            the **subject** pattern, injecting named groups for all three
            captures so that a single ``finditer`` pass extracts group,
            day **and** subject from each block.

        Args:
            group_pattern: Pattern for capturing group ID
            day_pattern: Pattern for capturing day
            subject_pattern: Pattern for capturing subject
            separator: Regex pattern for block separator (unused for atomic,
                kept for API compatibility)

        Returns:
            Combined regex with named groups, or ``""`` if nothing provided.

        Examples:
            Atomic patterns::

                >>> MultiAquariumData.build_combined_regex_pattern(
                ...     group_pattern=r"G(\\d+)",
                ...     day_pattern=r"D(\\d+)",
                ...     subject_pattern=r"S(\\d+)",
                ... )
                'G(?P<group>\\d+)_D(?P<day>\\d+)_S(?P<subject>\\d+)'

            Full-context patterns::

                >>> MultiAquariumData.build_combined_regex_pattern(
                ...     group_pattern=r"(G\\d+)_D\\d+_C\\d+",
                ...     day_pattern=r"G\\d+_D(\\d+)_C\\d+",
                ...     subject_pattern=r"G\\d+_D\\d+_(C\\d+)",
                ... )
                '(?P<group>G\\d+)_D(?P<day>\\d+)_(?P<subject>C\\d+)'
        """
        if not any([group_pattern, day_pattern, subject_pattern]):
            return ""

        def convert_to_named_group(pattern: str | None, group_name: str) -> str | None:
            """Convert a pattern with capture group to a named group."""
            if not pattern:
                return None

            pattern = pattern.strip()
            if not pattern:
                return None

            # Check if pattern has a capture group - look for (...) that isn't (?:...)
            # or already named (?P<...>)
            has_capture = re.search(r"\((?!\?[:=!<])", pattern)

            if has_capture:
                # Replace first non-named capture group with named group
                # Pattern: G(\d+) -> G(?P<group>\d+)
                def replace_first_group(m: re.Match) -> str:
                    return f"(?P<{group_name}>"

                # Only replace the first occurrence
                result, _count = re.subn(r"\((?!\?[:=!<])", replace_first_group, pattern, count=1)
                return result
            else:
                # No capture group - wrap the whole pattern
                # Pattern: G\d+ -> (?P<group>G\d+)
                return f"(?P<{group_name}>{pattern})"

        def _is_full_context(pattern: str | None) -> bool:
            """Return True if *pattern* contains separators (_, --, etc.).

            Full-context patterns embed the structure of the whole block,
            e.g. ``(G\\d+)_D\\d+_C\\d+``, meaning they already match the
            entire ``group_day_subject`` block on their own.
            """
            if not pattern:
                return False
            # Strip out regex character classes [...] to avoid false positives
            cleaned = re.sub(r"\[.*?\]", "", pattern)
            return bool(re.search(r"[_\-]{2}|(?<![\\])_", cleaned))

        full_context = any(
            _is_full_context(p) for p in [group_pattern, day_pattern, subject_pattern]
        )

        if full_context:
            # Full-context patterns already contain separators and match the
            # entire block structure (e.g. ``(G\d+)_D\d+_C\d+``).
            # Joining them with ``_`` would produce an invalid mega-pattern.
            #
            # Return empty string so the caller falls through to the
            # individual-pattern fallback (``_process_path_with_individual_patterns``)
            # which uses ``finditer`` on each pattern independently and
            # correctly handles multi-subject filenames.
            log.debug(
                "multi_aquarium.build_combined_pattern",
                mode="full_context_skipped",
                group_pattern=group_pattern,
                day_pattern=day_pattern,
                subject_pattern=subject_pattern,
                result="(skipped — patterns are full-context)",
            )
            return ""

        # Atomic strategy: join converted parts with underscore
        group_named = convert_to_named_group(group_pattern, "group")
        day_named = convert_to_named_group(day_pattern, "day")
        subject_named = convert_to_named_group(subject_pattern, "subject")

        parts = []
        if group_named:
            parts.append(group_named)
        if day_named:
            parts.append(day_named)
        if subject_named:
            parts.append(subject_named)

        if not parts:
            return ""

        # Join parts with underscore (common separator within a block)
        # This creates a pattern like: G(?P<group>\d+)_D(?P<day>\d+)_S(?P<subject>\d+)
        combined = "_".join(parts)

        log.debug(
            "multi_aquarium.build_combined_pattern",
            mode="atomic",
            group_pattern=group_pattern,
            day_pattern=day_pattern,
            subject_pattern=subject_pattern,
            result=combined,
        )

        return combined

    @field_validator("aquarium_configs")
    @classmethod
    def validate_configs_count(cls, v: list[AquariumConfig]) -> list[AquariumConfig]:
        """Validate that there are at most 2 configurations."""
        if len(v) > 2:
            raise ValueError("Máximo de 2 aquários suportados")
        return v

    @field_validator("regex_pattern")
    @classmethod
    def validate_regex_pattern(cls, v: str) -> str:
        """Validate that the regex pattern is valid."""
        if v:
            try:
                re.compile(v)
            except re.error as e:
                raise ValueError(f"Padrão regex inválido: {e}") from e
        return v

    @model_validator(mode="after")
    def validate_configs_when_enabled(self) -> "MultiAquariumData":
        """When enabled, must have exactly 2 configurations."""
        if self.enabled and len(self.aquarium_configs) != 2:
            raise ValueError(
                "Modo multi-aquário habilitado requer exatamente 2 configurações de aquário"
            )
        return self

    def extract_metadata(self, filename: str) -> list[dict[str, str]]:
        """Extract metadata from filename using the regex pattern.

        Supports multiple matches (e.g., "G1_S1--G2_S2.mp4").

        Args:
            filename: Video filename.

        Returns:
            List of dictionaries with extracted fields (group, subject, day).
            One dictionary per match found.
        """
        results: list[dict[str, str]] = []

        if not self.regex_pattern:
            return results

        try:
            # Use re.IGNORECASE to match regardless of filename casing
            for match in re.finditer(self.regex_pattern, filename, re.IGNORECASE):
                groups = match.groupdict()

                meta = {
                    "group": groups.get(self.regex_group_field) or "",
                    "subject": groups.get(self.regex_subject_field) or "",
                    "day": groups.get(self.regex_day_field) or "",
                }
                results.append(meta)

        except re.error as e:
            log.warning(
                "extract_metadata.regex_error",
                pattern=self.regex_pattern,
                filename=filename,
                error=str(e),
            )

        return results


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
    multi_aquarium: MultiAquariumData = Field(
        default_factory=MultiAquariumData,
        description="Configurações de modo multi-aquário (2 aquários por vídeo)",
    )
    behavioral_analysis: BehavioralAnalysisData = Field(
        default_factory=BehavioralAnalysisData,
        description="Behavioral analysis settings (thigmotaxis, geotaxis)",
    )


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
        """Validate video file paths: existence, format, and readability.

        Task 2.4: Added path traversal security checks.
        """
        VIDEO_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv", ".flv", ".wmv", ".webm", ".m4v"}

        # Task 2.4: Blocked sensitive system directories (Linux/Mac/Windows)
        FORBIDDEN_DIRS = {
            "/etc",
            "/sys",
            "/proc",
            "/dev",
            "/root",
            "/boot",
            "C:\\Windows",
            "C:\\Windows\\System32",
            "C:\\Program Files",
            "C:\\ProgramData",
        }

        # Check for empty strings
        if any(not vf.strip() for vf in v):
            raise ValueError("Caminhos de vídeo não podem estar vazios")

        missing_files = []
        invalid_formats = []
        not_files = []
        forbidden_paths = []

        for video_path in v:
            path = Path(video_path)

            # Task 2.4: Resolve path to absolute and follow symlinks
            # This prevents bypasses using .. or symlinks
            try:
                resolved_path = path.resolve(strict=False)
            except (OSError, RuntimeError) as e:
                # Path resolution failed (e.g., circular symlink, invalid path)
                forbidden_paths.append(f"{video_path} (path resolution failed: {e})")
                continue

            # Task 2.4: Check if resolved path is in forbidden system directories
            resolved_str = str(resolved_path)
            if any(resolved_str.startswith(forbidden_dir) for forbidden_dir in FORBIDDEN_DIRS):
                forbidden_paths.append(f"{video_path} → {resolved_str} (sistema)")
                continue

            # Use resolved path for all subsequent checks
            path = resolved_path

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

        # Task 2.4: Report forbidden paths FIRST (security priority)
        if forbidden_paths:
            errors.append(
                "⚠️ SEGURANÇA: Caminhos bloqueados (diretórios do sistema):\n  - "
                + "\n  - ".join(forbidden_paths[:5])
                + (f"\n  ... e mais {len(forbidden_paths) - 5}" if len(forbidden_paths) > 5 else "")
            )

        if missing_files:
            errors.append(
                "Arquivos não encontrados:\n  - "
                + "\n  - ".join(missing_files[:5])
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
BehavioralAnalysis = BehavioralAnalysisData
