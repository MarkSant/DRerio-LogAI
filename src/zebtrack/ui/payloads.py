"""Typed event payload dataclasses for EventBusV2."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


class EventPayload(Protocol):
    """Marker protocol for typed event payloads."""


type EventPayloadType = EventPayload


@dataclass(frozen=True)
class EmptyPayload:
    """Payload for events with no data."""


# ---------------------------------------------------------------------------
# Common payloads
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MessagePayload:
    title: str | None = None
    message: str = ""


@dataclass(frozen=True)
class StatusPayload:
    message: str
    status_type: str | None = None
    level: str | None = None


@dataclass(frozen=True)
class VideoPathPayload:
    video_path: str


@dataclass(frozen=True)
class VideoPathsPayload:
    video_paths: Sequence[str]


@dataclass(frozen=True)
class SelectionPayload:
    selection: Sequence[str]


@dataclass(frozen=True)
class ItemIdPayload:
    item_id: str


@dataclass(frozen=True)
class TrackIdPayload:
    track_id: int


@dataclass(frozen=True)
class FramePayload:
    frame: Any
    frame_number: int | None = None


@dataclass(frozen=True)
class FrameDisplayPayload:
    frame: Any
    detections: Sequence[Any] | None = None
    frame_number: int | None = None
    info: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class ProcessingStatsPayload:
    total_frames: int
    processed_frames: int
    detected_frames: int
    start_time: float | None = None
    current_frame: int | None = None


@dataclass(frozen=True)
class ProcessingStatsWrapperPayload:
    stats: Mapping[str, Any]


@dataclass(frozen=True)
class DetectionOverlayPayload:
    detections: Sequence[Any]
    report: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class AnalysisMetadataPayload:
    metadata: Mapping[str, Any]


@dataclass(frozen=True)
class SocialSummaryPayload:
    profile: str | None = None
    stats: Mapping[str, Any] | None = None
    tracks: Sequence[Any] | None = None


@dataclass(frozen=True)
class AnalysisTaskStatusPayload:
    index: int | None = None
    total: int | None = None
    experiment_id: str | None = None
    step: str | None = None
    progress: float | None = None
    progress_fraction: float | None = None


@dataclass(frozen=True)
class UpdateButtonStatePayload:
    button_name: str | None = None
    state: str | None = None
    text: str | None = None


@dataclass(frozen=True)
class UpdateProcessingModePayload:
    report: Any | None = None
    mode: str | None = None
    single_subject_overlay_locked: bool | None = None


@dataclass(frozen=True)
class UISelectTabPayload:
    tab_name: str


@dataclass(frozen=True)
class UpdateAquariumSelectorPayload:
    aquariums: Sequence[int]
    active_aquarium_id: int | None = None


@dataclass(frozen=True)
class SetAquariumSelectorVisiblePayload:
    visible: bool


@dataclass(frozen=True)
class VideoLoadedPayload:
    video_path: str
    frame_count: int | None = None
    fps: float | None = None


@dataclass(frozen=True)
class ErrorOccurredPayload:
    title: str | None = None
    message: str = ""
    category: str | None = None


@dataclass(frozen=True)
class ExternalTriggerNoticePayload:
    folder_name: str | None = None
    session_label: str | None = None
    day: str | int | None = None
    group: str | None = None
    cobaia: str | None = None
    port: str | None = None
    level: str | None = None


@dataclass(frozen=True)
class CameraDisconnectPayload:
    camera_index: int = 0
    action: str | None = None
    gap_duration_s: float | None = None
    gap_start_time: float | None = None
    experiment_id: str | None = None
    total_gaps: int | None = None


@dataclass(frozen=True)
class AquariumDetectionProgressPayload:
    current_aquarium: int = 0
    total_aquariums: int = 0
    message: str = ""
    frame_number: int | None = None
    max_frames: int | None = None
    frame_image: Any | None = None
    detected_bbox: tuple[int, ...] | None = None
    is_valid: bool | None = None
    experiment_id: str | None = None
    valid_count: int | None = None


@dataclass(frozen=True)
class ZoneDisplayClearedPayload:
    deleted_video_path: str | None = None
    asset: str | None = None


@dataclass(frozen=True)
class LiveBatchCompletedPayload:
    batch_id: str | None = None
    session_count: int = 0
    group: str | None = None
    day: str | int | None = None
    subject_id: str | None = None


# ---------------------------------------------------------------------------
# Project payloads
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ProjectCreatePayload:
    project_path: str | Path | None = None
    project_name: str | None = None
    project_type: str | None = None
    wizard_data: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class ProjectCreatedPayload:
    project: Any
    path: str | None = None


@dataclass(frozen=True)
class ProjectOpenPayload:
    project_path: str


@dataclass(frozen=True)
class ProjectOpenedPayload:
    project_path: str
    project: Any | None = None


@dataclass(frozen=True)
class ProjectManagerReplacedPayload:
    new_manager: Any


@dataclass(frozen=True)
class ProjectProcessVideosPayload:
    video_paths: Sequence[str]
    analysis_config: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class ProjectGenerateSummariesPayload:
    video_paths: Sequence[str] | None = None


@dataclass(frozen=True)
class ProjectApplySettingsPayload:
    settings: Mapping[str, Any]


@dataclass(frozen=True)
class ProjectDeleteAssetPayload:
    video_path: str
    asset: str


@dataclass(frozen=True)
class ProjectDeleteGroupPayload:
    group_id: str
    delete_files: bool = True


@dataclass(frozen=True)
class ProjectDeleteDayPayload:
    group_id: str
    day_id: str
    delete_files: bool = True


@dataclass(frozen=True)
class ProjectDeleteSubjectPayload:
    group_id: str
    day_id: str
    subject_id: str
    delete_files: bool = True


@dataclass(frozen=True)
class ProjectVideoSelectedPayload:
    video_path: str
    video_entry: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class ProjectSelectionChangedPayload:
    selection: Sequence[str]


@dataclass(frozen=True)
class ProjectViewsRefreshRequestedPayload:
    reason: str | None = None
    imm: bool | None = None
    append_summary: bool | None = None
    immediate: bool | None = None


@dataclass(frozen=True)
class ProjectRefreshRequestedPayload:
    reason: str | None = None
    imm: bool | None = None


@dataclass(frozen=True)
class WizardCreateProjectPayload:
    wizard_data: Mapping[str, Any]


# ---------------------------------------------------------------------------
# Zone payloads
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DetectorSetupPayload:
    animal_method: str | None = None
    use_openvino: bool | None = None
    active_weight_name: str | None = None
    detector_plugins: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class DetectorSetupZonesPayload:
    zone_data: Any


@dataclass(frozen=True)
class DetectorUpdateParametersPayload:
    rule: str | None = None
    buffer_radius: float | None = None
    overlap_ratio: float | None = None
    confidence: float | None = None
    iou: float | None = None
    track_threshold: float | None = None


@dataclass(frozen=True)
class DetectorUpdateZonesPayload:
    zone_data: Any


@dataclass(frozen=True)
class ZoneTemplateApplyPayload:
    template_name: str | None = None


@dataclass(frozen=True)
class ZoneApplyRoiSettingsPayload:
    settings: Mapping[str, Any]


@dataclass(frozen=True)
class ZoneAutoDetectClickedPayload:
    stabilization_frames: int = 10


@dataclass(frozen=True)
class ZoneAutoDetectPayload:
    video_path: str
    stabilization_frames: int = 10
    expected_count: int | None = None


@dataclass(frozen=True)
class ZoneVideoSearchChangedPayload:
    search_text: str


@dataclass(frozen=True)
class ZoneVideoDoubleClickPayload:
    item_id: str


@dataclass(frozen=True)
class ZoneVideoFrameLoadPayload:
    item_id: str


@dataclass(frozen=True)
class ZoneListItemPayload:
    item_id: str


@dataclass(frozen=True)
class ZoneListItemRightClickPayload:
    item_id: str
    x: int | None = None
    y: int | None = None


@dataclass(frozen=True)
class ZonesUpdatedPayload:
    zone_data: Any | None = None


@dataclass(frozen=True)
class PolygonEditRequestedPayload:
    polygon: Any


@dataclass(frozen=True)
class ZoneMultiAutoDetectPayload:
    video_path: str
    stabilization_frames: int = 10
    expected_count: int | None = None


@dataclass(frozen=True)
class ZoneMultiAutoDetectSuccessPayload:
    video_path: str
    polygons: Sequence[Any]
    count: int
    method: str | None = None
    source_video_width: int | None = None
    source_video_height: int | None = None


@dataclass(frozen=True)
class ZoneMultiAutoDetectFailedPayload:
    video_path: str
    reason: str


@dataclass(frozen=True)
class ZoneMultiDetectCompletedPayload:
    count: int
    aquariums: Sequence[int] | None = None


@dataclass(frozen=True)
class ZoneAquariumSelectedPayload:
    aquarium_id: int


@dataclass(frozen=True)
class ZoneAquariumConfigConfirmedPayload:
    configs: Sequence[Mapping[str, Any]]


@dataclass(frozen=True)
class ZoneAquariumConfigUpdatedPayload:
    aquarium_id: int
    config: Mapping[str, Any]
    video_path: str


@dataclass(frozen=True)
class ZoneAquariumCountConfirmedPayload:
    count: int


@dataclass(frozen=True)
class ZoneAquariumAssignmentCompletedPayload:
    configs: Sequence[Mapping[str, Any]]
    apply_to_all: bool
    video_path: str = ""


@dataclass(frozen=True)
class ZoneShowAquariumAssignmentDialogPayload:
    video_path: str
    polygons: Sequence[Any]
    count: int
    entry_metadata: Mapping[str, Any] | None = None
    multi_aquarium_config: Any | None = None


@dataclass(frozen=True)
class ZoneProcessingModeChangedPayload:
    sequential: bool
    apply_to_all: bool | None = None
    video_path: str | None = None


@dataclass(frozen=True)
class SetupInteractivePolygonPayload:
    polygon: Any


# ---------------------------------------------------------------------------
# Processing and report payloads
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VideoAnalyzeSinglePayload:
    video_path: str
    config: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class VideoStartSingleProcessingPayload:
    video_path: str
    config: Mapping[str, Any] | None = None
    zone_data: Any | None = None


@dataclass(frozen=True)
class SetupZoneDefinitionPayload:
    video_path: str
    config: Mapping[str, Any]


@dataclass(frozen=True)
class VideoCancelAnalysisPayload:
    video_path: str | None = None


@dataclass(frozen=True)
class VideoMetadataUpdatedPayload:
    video_path: str
    metadata: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class VideoReconfigureSubjectsPayload:
    video_path: str
    current_entries: Sequence[Mapping[str, Any]]


@dataclass(frozen=True)
class VideoTreeRefreshRequestedPayload:
    filter_text: str | None = None


@dataclass(frozen=True)
class VideoHierarchySnapshotUpdatedPayload:
    snapshot: Mapping[str, Any]


@dataclass(frozen=True)
class ReadinessSnapshotUpdatedPayload:
    ready_with_trajectory: Sequence[Mapping[str, Any]]
    ready_with_zones: Sequence[Mapping[str, Any]]
    arena_only: Sequence[Mapping[str, Any]]
    without_arena: Sequence[Mapping[str, Any]]


@dataclass(frozen=True)
class ProcessingGenerateTrajectoriesPayload:
    selection: Sequence[str]


@dataclass(frozen=True)
class ProcessingExportSummariesPayload:
    selection: Sequence[str]
    format: str | None = None


@dataclass(frozen=True)
class ReportsGeneratePartialPayload:
    selection: Sequence[str] | None = None
    video_path: str | None = None
    roi_ids: Sequence[Any] | None = None


@dataclass(frozen=True)
class ReportsGenerateUnifiedPayload:
    selection: Sequence[str] | None = None
    video_paths: Sequence[str] | None = None
    multi_aquarium: bool | None = None


@dataclass(frozen=True)
class ReportsDeleteUnifiedPayload:
    video_path: str | None = None


@dataclass(frozen=True)
class ReportGeneratePayload:
    video_path: str | None = None
    format: str | None = None
    videos: Sequence[Mapping[str, Any]] | None = None
    report_type: str | None = None
    report_scope: str | None = None
    replace_existing: bool | None = None


@dataclass(frozen=True)
class ProcessingProgressPayload:
    total_frames: int
    processed_frames: int
    current_frame: int | None = None
    detected_frames: int | None = None
    start_time: float | None = None


@dataclass(frozen=True)
class TrackingCompletePayload:
    video_path: str
    total_tracks: int | None = None
    avg_track_length: int | None = None


@dataclass(frozen=True)
class AnalysisStartedPayload:
    video_path: str
    roi_count: int | None = None


@dataclass(frozen=True)
class AnalysisCompletedPayload:
    video_path: str
    roi_results: Sequence[Mapping[str, Any]] | None = None
    metadata: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class BatchAnalysisCompletedPayload:
    total_videos: int
    successful_count: int
    failed_count: int
    results_summary: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class FrameErrorPayload:
    error: str
    frame_number: int | None = None
    video_path: str | None = None


# ---------------------------------------------------------------------------
# Model and weights payloads
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ModelSetWeightPayload:
    name: str | None = None
    weight_name: str | None = None
    dialog: Any | None = None


@dataclass(frozen=True)
class ModelSetOpenVinoPayload:
    use_openvino: bool
    device: str | None = None
    dialog: Any | None = None


@dataclass(frozen=True)
class ModelConvertOpenVinoPayload:
    weight_name: str
    format: str | None = None


@dataclass(frozen=True)
class ModelUpdateOpenVinoStatusPayload:
    message: str
    progress_pct: float | None = None


@dataclass(frozen=True)
class ModelAddWeightPayload:
    weight_path: str | Path
    name: str | None = None


@dataclass(frozen=True)
class ModelDeleteWeightPayload:
    name: str


@dataclass(frozen=True)
class ModelRunDiagnosticPayload:
    config: dict[str, Any] | None = None
    weight_name: str | None = None
    test_video: str | None = None


@dataclass(frozen=True)
class ModelLoadNewWeightPayload:
    weight_path: str | Path
    weight_type: str | None = None


@dataclass(frozen=True)
class UIUpdateWeightsListPayload:
    weights: Sequence[str]


@dataclass(frozen=True)
class UIRequestWeightFilePayload:
    filepath: str | None = None


@dataclass(frozen=True)
class UIRequestWeightTypePayload:
    filepath: str | None = None


@dataclass(frozen=True)
class UIRequestWeightActionPayload:
    weight_type: str
    filepath: str


@dataclass(frozen=True)
class UISetActiveWeightPayload:
    weight_name: str


@dataclass(frozen=True)
class UIUpdateOpenVinoCheckboxPayload:
    is_checked: bool


@dataclass(frozen=True)
class UIUpdateOpenVinoStatusPayload:
    status: str | None = None
    message: str | None = None
    progress: float | None = None


# ---------------------------------------------------------------------------
# Calibration and Arduino payloads
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CalibrationRunLivePayload:
    camera_index: int
    duration_sec: float | None = None


@dataclass(frozen=True)
class CalibrationCopyToProjectPayload:
    calibration_data: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class CalibrationSaveToProjectPayload:
    calibration_data: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class ArduinoSetupPayload:
    port: str
    baudrate: int | None = None


@dataclass(frozen=True)
class ArduinoLogEventPayload:
    event: str
    timestamp: float | None = None


@dataclass(frozen=True)
class ArduinoPortUpdateRequestedPayload:
    ports: Sequence[str]


@dataclass(frozen=True)
class UIUpdateArduinoStatusPayload:
    connected: bool
    port: str | None = None


@dataclass(frozen=True)
class UIAppendArduinoLogPayload:
    message: str
    level: str | None = None


# ---------------------------------------------------------------------------
# Recording and live payloads
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RecordingStartPayload:
    camera_index: int | None = None
    output_config: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class RecordingStartedPayload:
    folder_name: str | None = None
    output_folder: str | None = None
    trigger_source: str | None = None
    duration: float | None = None


@dataclass(frozen=True)
class RecordingStoppedPayload:
    session_id: str | None = None
    duration_sec: float | None = None
    frames_recorded: int | None = None


@dataclass(frozen=True)
class RecordingTriggerPayload:
    trigger_signal: str
    source: str | None = None


@dataclass(frozen=True)
class LiveSessionStartedPayload:
    session_id: str
    video_path: str
    config: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class LiveSessionStoppedPayload:
    session_id: str
    output_path: str
    frame_count: int


@dataclass(frozen=True)
class UIUpdateLiveFramePayload:
    frame: Any
    detections: Sequence[Any] | None = None
    frame_number: int | None = None
    fps: float | None = None


# ---------------------------------------------------------------------------
# Config and control payloads
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ConfigSaveRequestedPayload:
    values: Mapping[str, Any] | None = None
    config_dict: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class ConfigValidationErrorPayload:
    error: str


@dataclass(frozen=True)
class ConfigRoiRuleChangedPayload:
    rule: str
    roi_settings: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class BehavioralConfigPerspectiveChangedPayload:
    perspective: str
    config: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class BehavioralConfigValuesChangedPayload:
    config: Mapping[str, Any]


@dataclass(frozen=True)
class BehavioralConfigGeotaxisToggledPayload:
    enabled: bool
    zone_count: int | None = None


@dataclass(frozen=True)
class ControlPreviewToggledPayload:
    preview_enabled: bool


@dataclass(frozen=True)
class ControlIntervalChangedPayload:
    interval: int | None = None
    analysis_interval: int | None = None
    display_interval: int | None = None


# ---------------------------------------------------------------------------
# Fallback payload for unexpected events
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class UnknownPayload:
    data: Mapping[str, Any]
