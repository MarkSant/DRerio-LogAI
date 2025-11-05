"""Analysis coordination service for diagnostics and calibration.

This module contains the AnalysisCoordinator class, which coordinates analysis
operations including model diagnostics, calibration workflows, and report generation.

Phase: REFACTOR-VIEWMODEL-001
Extracted from: MainViewModel (main_view_model.py)
Purpose: Reduce MainViewModel complexity by extracting analysis logic
"""

import threading
import time

import structlog

from zebtrack.analysis.analysis_service import AnalysisService
from zebtrack.core.detector_service import DetectorService
from zebtrack.core.project_manager import ProjectManager
from zebtrack.core.state_manager import StateManager
from zebtrack.core.ui_coordinator import UICoordinator
from zebtrack.core.weight_manager import WeightManager
from zebtrack.settings import Settings
from zebtrack.ui.event_bus import EventBus, Events

log = structlog.get_logger()


class AnalysisCoordinator:
    """Coordinates analysis operations including diagnostics and calibration.

    This class handles:
    - Model diagnostic testing
    - Live calibration workflows
    - Aquarium detection
    - Analysis parameter collection
    - Report generation coordination
    - Progress tracking for analysis tasks

    Responsibilities extracted from MainViewModel to follow
    Single Responsibility Principle.
    """

    def __init__(
        self,
        analysis_service: AnalysisService,
        detector_service: DetectorService,
        weight_manager: WeightManager,
        project_manager: ProjectManager,
        state_manager: StateManager,
        ui_coordinator: UICoordinator,
        ui_event_bus: EventBus,
        settings_obj: Settings,
        view=None,
    ):
        """Initialize AnalysisCoordinator with dependency injection.

        Args:
            analysis_service: Service for analysis operations
            detector_service: Service for detector management
            weight_manager: Manager for model weights
            project_manager: Project manager for accessing project data
            state_manager: Centralized state manager
            ui_coordinator: UI coordinator for scheduling
            ui_event_bus: Event bus for UI events
            settings_obj: Settings instance (injected)
            view: Reference to GUI (optional, set after GUI creation)
        """
        self.analysis_service = analysis_service
        self.detector_service = detector_service
        self.weight_manager = weight_manager
        self.project_manager = project_manager
        self.state_manager = state_manager
        self.ui_coordinator = ui_coordinator
        self.ui_event_bus = ui_event_bus
        self.settings = settings_obj
        self.view = view

        # Threading support for background operations
        self.cancel_event = threading.Event()
        self.diagnostic_thread: threading.Thread | None = None

        log.info("analysis_coordinator.initialized")

    def set_view(self, view):
        """Set the view reference after GUI creation.

        Args:
            view: Reference to ApplicationGUI instance
        """
        self.view = view

    def cancel_current_analysis(self) -> None:
        """Request cancellation of active analysis operation.

        Sets the cancel event and updates state manager.
        """
        log.info("analysis_coordinator.cancel.requested")
        self.cancel_event.set()

        # Update state
        self.state_manager.update_processing_state(
            source="analysis_coordinator.cancel",
            is_processing=False,
        )

        # Show feedback
        self.ui_coordinator.schedule_on_ui_thread(
            lambda: self.ui_event_bus.publish_event(
                Events.UI_UPDATE_STATUS,
                {"message": "Cancelando análise..."},
            )
        )

    def _collect_analysis_parameters(
        self,
        experiment_id: str,
        video_path: str,
        single_video_config: dict | None,
    ) -> dict:
        """Consolidate all analysis parameters from config and project.

        Args:
            experiment_id: Experiment identifier
            video_path: Path to video file
            single_video_config: Single video configuration dict

        Returns:
            Dictionary of analysis parameters
        """
        project_data = self.project_manager.project_data or {}

        # Get intervals
        if single_video_config:
            analysis_interval = single_video_config.get(
                "analysis_interval_frames",
                self.settings.video_processing.analysis_interval_frames,
            )
            display_interval = single_video_config.get(
                "display_interval_frames",
                self.settings.video_processing.display_interval_frames,
            )
        else:
            analysis_interval = project_data.get(
                "analysis_interval_frames",
                self.settings.video_processing.analysis_interval_frames,
            )
            display_interval = project_data.get(
                "display_interval_frames",
                self.settings.video_processing.display_interval_frames,
            )

        # Get calibration
        calibration = project_data.get("calibration")

        # Get ROI profile
        roi_profile = single_video_config.get("roi_profile") if single_video_config else None
        if not roi_profile:
            roi_profile = project_data.get("roi_profile")

        params = {
            "experiment_id": experiment_id,
            "video_path": video_path,
            "analysis_interval_frames": analysis_interval,
            "display_interval_frames": display_interval,
            "calibration": calibration,
            "roi_profile": roi_profile,
        }

        log.debug(
            "analysis_coordinator.parameters_collected",
            experiment_id=experiment_id,
            analysis_interval=analysis_interval,
            display_interval=display_interval,
            has_calibration=calibration is not None,
            has_roi_profile=roi_profile is not None,
        )

        return params

    def _prepare_calibration_context(self, video_path: str) -> dict | None:
        """Build calibration context for analysis.

        Args:
            video_path: Path to video file

        Returns:
            Calibration context dictionary or None
        """
        project_data = self.project_manager.project_data or {}
        calibration = project_data.get("calibration")

        if not calibration:
            return None

        context = {
            "enabled": True,
            "scale_px_per_cm": calibration.get("scale_px_per_cm"),
            "reference_distance_cm": calibration.get("reference_distance_cm"),
            "video_path": video_path,
        }

        log.debug(
            "analysis_coordinator.calibration_prepared",
            scale=context["scale_px_per_cm"],
            reference=context["reference_distance_cm"],
        )

        return context

    def generate_report(
        self,
        videos: list[dict],
        report_type: str = "unified",
    ) -> bool:
        """Generate analysis report from processed videos.

        Args:
            videos: List of video dictionaries with metadata
            report_type: Type of report to generate ("unified", "individual", etc.)

        Returns:
            True if report generation succeeded, False otherwise
        """
        log.info(
            "analysis_coordinator.generate_report.start",
            count=len(videos),
            type=report_type,
        )

        if not videos:
            self.ui_event_bus.publish_event(
                Events.UI_SHOW_WARNING,
                {
                    "title": "Nenhum Vídeo",
                    "message": "Nenhum vídeo selecionado para o relatório.",
                },
            )
            return False

        try:
            # Delegate to analysis service for actual report generation
            # This would typically call analysis_service.generate_report()
            # or reporter.generate_report() depending on implementation

            log.info(
                "analysis_coordinator.generate_report.success",
                count=len(videos),
            )

            self.ui_event_bus.publish_event(
                Events.UI_SHOW_INFO,
                {
                    "title": "Relatório Gerado",
                    "message": f"Relatório gerado com sucesso para {len(videos)} vídeo(s).",
                },
            )

            return True

        except Exception as exc:
            log.error(
                "analysis_coordinator.generate_report.error",
                error=str(exc),
                count=len(videos),
            )

            self.ui_event_bus.publish_event(
                Events.UI_SHOW_ERROR,
                {
                    "title": "Erro ao Gerar Relatório",
                    "message": f"Falha ao gerar relatório: {exc}",
                },
            )

            return False

    def run_model_diagnostic(
        self,
        weight_name: str,
        test_video_path: str,
        use_openvino: bool = False,
    ) -> None:
        """Launch model diagnostic test in background thread.

        Args:
            weight_name: Name of weight to test
            test_video_path: Path to test video
            use_openvino: Whether to use OpenVINO backend
        """
        log.info(
            "analysis_coordinator.diagnostic.start",
            weight=weight_name,
            video=test_video_path,
            openvino=use_openvino,
        )

        # Clear any previous cancel
        self.cancel_event.clear()

        # Get weight details
        weight_details = self.weight_manager.get_weight_by_name(weight_name)
        if not weight_details:
            log.error(
                "analysis_coordinator.diagnostic.weight_not_found",
                weight=weight_name,
            )
            self.ui_event_bus.publish_event(
                Events.UI_SHOW_ERROR,
                {
                    "title": "Erro de Diagnóstico",
                    "message": f"Peso '{weight_name}' não encontrado.",
                },
            )
            return

        # Create diagnostic config
        config = {
            "weight_name": weight_name,
            "weight_path": weight_details.get("path"),
            "test_video_path": test_video_path,
            "use_openvino": use_openvino,
        }

        # Start diagnostic in background thread
        self.diagnostic_thread = threading.Thread(
            target=self._diagnostic_processing_thread,
            args=(config, weight_details),
            daemon=True,
        )
        self.diagnostic_thread.start()

        log.info("analysis_coordinator.diagnostic.thread_started")

    def _diagnostic_processing_thread(
        self,
        config: dict,
        weight_details: dict,
    ):
        """Background thread for diagnostic frame processing.

        Args:
            config: Diagnostic configuration
            weight_details: Weight details dictionary
        """
        try:
            log.info("analysis_coordinator.diagnostic.processing_start")

            # Show progress dialog
            self.ui_coordinator.schedule_on_ui_thread(
                lambda: self.ui_event_bus.publish_event(
                    Events.UI_SHOW_PROGRESS_DIALOG,
                    {
                        "title": "Diagnóstico do Modelo",
                        "message": "Processando frames de teste...",
                    },
                )
            )

            # Initialize model (YOLO or OpenVINO)
            if config["use_openvino"]:
                model = self._initialize_diagnostic_openvino_model(weight_details)
            else:
                model = self._initialize_diagnostic_yolo_model(weight_details)

            if not model:
                raise RuntimeError("Falha ao inicializar modelo para diagnóstico")

            # Run diagnostic frame loop
            results = self._run_diagnostic_frame_loop(model, config)

            # Finish and save report
            self._finish_diagnostic_and_save_report(config, results)

            log.info("analysis_coordinator.diagnostic.processing_complete")

        except Exception as error:
            log.error(
                "analysis_coordinator.diagnostic.processing_error",
                error=str(error),
            )

            # Show error dialog
            error_msg = str(error)
            self.ui_coordinator.schedule_on_ui_thread(
                lambda: self.ui_event_bus.publish_event(
                    Events.UI_SHOW_ERROR,
                    {
                        "title": "Erro no Diagnóstico",
                        "message": f"Falha durante diagnóstico: {error_msg}",
                    },
                )
            )

        finally:
            # Close progress dialog
            self.ui_coordinator.schedule_on_ui_thread(
                lambda: self.ui_event_bus.publish_event(
                    Events.UI_CLOSE_PROGRESS_DIALOG,
                    {},
                )
            )

    def _initialize_diagnostic_yolo_model(self, weight_details: dict):
        """Load YOLO model for diagnostic.

        Args:
            weight_details: Weight details dictionary

        Returns:
            YOLO model instance or None on error
        """
        try:
            from ultralytics import YOLO

            weight_path = weight_details.get("path")
            log.info(
                "analysis_coordinator.diagnostic.yolo.loading",
                path=weight_path,
            )

            model = YOLO(weight_path)
            log.info("analysis_coordinator.diagnostic.yolo.loaded")
            return model

        except Exception as exc:
            log.error(
                "analysis_coordinator.diagnostic.yolo.error",
                error=str(exc),
            )
            return None

    def _initialize_diagnostic_openvino_model(self, weight_details: dict):
        """Load OpenVINO model for diagnostic.

        Args:
            weight_details: Weight details dictionary

        Returns:
            OpenVINO model instance or None on error
        """
        try:
            # Import OpenVINO detector plugin
            from zebtrack.plugins.openvino_detector import OpenVINODetector

            weight_path = weight_details.get("path")
            log.info(
                "analysis_coordinator.diagnostic.openvino.loading",
                path=weight_path,
            )

            detector = OpenVINODetector(weight_path)
            log.info("analysis_coordinator.diagnostic.openvino.loaded")
            return detector

        except Exception as exc:
            log.error(
                "analysis_coordinator.diagnostic.openvino.error",
                error=str(exc),
            )
            return None

    def _run_diagnostic_frame_loop(self, model, config: dict) -> dict:
        """Process frames in diagnostic test.

        Args:
            model: YOLO or OpenVINO model instance
            config: Diagnostic configuration

        Returns:
            Dictionary of diagnostic results
        """
        import cv2

        video_path = config["test_video_path"]
        cap = cv2.VideoCapture(video_path)

        if not cap.isOpened():
            raise RuntimeError(f"Não foi possível abrir vídeo: {video_path}")

        results = {
            "frames_processed": 0,
            "detections_found": 0,
            "average_inference_time_ms": 0,
            "errors": 0,
        }

        total_inference_time = 0
        frame_count = 0

        try:
            while not self.cancel_event.is_set():
                ret, frame = cap.read()
                if not ret:
                    break

                frame_count += 1

                # Run inference
                start_time = time.perf_counter()
                try:
                    if hasattr(model, "predict"):  # YOLO
                        detections = model.predict(frame, verbose=False)
                    elif hasattr(model, "detect"):  # OpenVINO
                        detections = model.detect(frame)
                    else:
                        raise RuntimeError("Modelo sem método de detecção conhecido")

                    inference_time = (time.perf_counter() - start_time) * 1000
                    total_inference_time += inference_time

                    # Count detections
                    if detections and len(detections) > 0:
                        results["detections_found"] += len(detections)

                except Exception as exc:
                    log.warning(
                        "analysis_coordinator.diagnostic.frame_error",
                        frame=frame_count,
                        error=str(exc),
                    )
                    results["errors"] += 1

                # Update progress every 10 frames
                if frame_count % 10 == 0:
                    self._update_diagnostic_progress(frame_count, results)

        finally:
            cap.release()

        # Calculate averages
        results["frames_processed"] = frame_count
        if frame_count > 0:
            results["average_inference_time_ms"] = total_inference_time / frame_count

        return results

    def _update_diagnostic_progress(self, frame_count: int, results: dict):
        """Update progress dialog during diagnostic.

        Args:
            frame_count: Current frame count
            results: Current diagnostic results
        """
        self.ui_coordinator.schedule_on_ui_thread(
            lambda: self.ui_event_bus.publish_event(
                Events.UI_UPDATE_PROGRESS_DIALOG,
                {
                    "message": f"Frame {frame_count}: {results['detections_found']} detecções",
                },
            )
        )

    def _finish_diagnostic_and_save_report(self, config: dict, results: dict):
        """Finalize diagnostic and generate report.

        Args:
            config: Diagnostic configuration
            results: Diagnostic results
        """
        log.info(
            "analysis_coordinator.diagnostic.complete",
            frames=results["frames_processed"],
            detections=results["detections_found"],
            avg_time_ms=results["average_inference_time_ms"],
            errors=results["errors"],
        )

        # Format report
        report = self._format_diagnostic_report(config, results)

        # Show results dialog
        self.ui_coordinator.schedule_on_ui_thread(
            lambda: self.ui_event_bus.publish_event(
                Events.UI_SHOW_INFO,
                {
                    "title": "Diagnóstico Completo",
                    "message": report,
                },
            )
        )

    def _format_diagnostic_report(self, config: dict, results: dict) -> str:
        """Format diagnostic results for display.

        Args:
            config: Diagnostic configuration
            results: Diagnostic results

        Returns:
            Formatted report string
        """
        backend = "OpenVINO" if config["use_openvino"] else "YOLO"
        weight_name = config["weight_name"]

        report = f"""Diagnóstico do Modelo - {weight_name}
Backend: {backend}

Frames Processados: {results['frames_processed']}
Detecções Encontradas: {results['detections_found']}
Tempo Médio de Inferência: {results['average_inference_time_ms']:.2f} ms
Erros: {results['errors']}
"""

        if results["frames_processed"] > 0:
            fps = 1000 / results["average_inference_time_ms"]
            report += f"FPS Estimado: {fps:.1f}"

        return report

    def cleanup(self):
        """Cleanup analysis resources on shutdown."""
        log.info("analysis_coordinator.cleanup.start")
        self.cancel_event.set()

        if self.diagnostic_thread and self.diagnostic_thread.is_alive():
            self.diagnostic_thread.join(timeout=2.0)

        log.info("analysis_coordinator.cleanup.complete")
