"""Model Diagnostics Coordinator — Phase 4.9 Extraction.

Orchestrates model diagnostic workflows: YOLO/OpenVINO inference tests,
progress dialog management, and diagnostic report generation.

Phase 4.9: Extracted from HardwareCoordinator Group B.
"""

from __future__ import annotations

import glob
import os
import shutil
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import cv2
import structlog

from zebtrack.coordinators.base_coordinator import BaseCoordinator, CoordinatorValidationError
from zebtrack.plugins import DETECTOR_PLUGINS
from zebtrack.ui.event_bus_v2 import Event, EventBusV2, UIEvents

try:
    from ultralytics import YOLO

    ULTRALYTICS_AVAILABLE = True
except ImportError:
    YOLO = None  # type: ignore[misc,assignment]
    ULTRALYTICS_AVAILABLE = False

if TYPE_CHECKING:
    import threading as _threading

    from zebtrack.core.services.weight_manager import WeightManager
    from zebtrack.core.state_manager import StateManager

log = structlog.get_logger()


# =============================================================================
# EXCEPTIONS
# =============================================================================


class ModelDiagnosticsCoordinatorError(Exception):
    """Base exception for ModelDiagnosticsCoordinator errors."""

    def __init__(self, message: str, context: dict[str, Any] | None = None):
        """Initialize exception with message and optional context.

        Args:
            message: Error message
            context: Optional context dictionary
        """
        super().__init__(message)
        self.context = context or {}


class DiagnosticAbortError(RuntimeError):
    """Signal used to stop diagnostic workflow without surfacing duplicate dialogs."""


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def _is_valid_openvino_directory(path: Path | str | None) -> bool:
    """Validate if an OpenVINO model directory exists and contains required .xml files.

    Args:
        path: Path to the OpenVINO model directory

    Returns:
        True if the directory exists and contains at least one .xml file, False otherwise
    """
    if not path or not os.path.exists(path) or not os.path.isdir(path):
        return False
    xml_files = glob.glob(os.path.join(str(path), "*.xml"))
    return len(xml_files) > 0


# =============================================================================
# COORDINATOR
# =============================================================================


class ModelDiagnosticsCoordinator(BaseCoordinator):
    """Coordinator for model diagnostic test workflows.

    Orchestrates:
    - YOLO (PyTorch) and OpenVINO model diagnostic tests
    - Progress dialog management (thread-safe UI updates)
    - Diagnostic report generation and saving
    - OpenVINO model validation and conversion preflight

    Delegates to:
    - WeightManager: Active weight resolution
    - StateManager: Diagnostic state persistence
    - EventBus: UI notifications (errors, status, info)
    - DiagnosticProgressDialog: Progress display (lazy-imported)

    Phase 4.9: Extracted from HardwareCoordinator Group B (model diagnostics).
    """

    def __init__(
        self,
        state_manager: StateManager,
        weight_manager: WeightManager,
        event_bus: EventBusV2 | None = None,
        cancel_event: _threading.Event | None = None,
        root: Any | None = None,
        view: Any | None = None,
    ):
        """Initialize ModelDiagnosticsCoordinator with dependency injection.

        Args:
            state_manager: StateManager for centralized state tracking
            weight_manager: WeightManager for active weight resolution
            event_bus: EventBus for UI notifications (optional)
            cancel_event: Threading event for cancellation support (optional)
            root: Tkinter root for thread-safe UI scheduling (optional)
            view: MainWindow reference for dialog access (optional)
        """
        super().__init__(state_manager=state_manager, event_bus=event_bus)
        self.weight_manager = weight_manager
        self.cancel_event = cancel_event
        self.root = root
        self.view = view

        log.info(
            "model_diagnostics.initialized",
            has_weight_manager=weight_manager is not None,
            has_cancel_event=cancel_event is not None,
            has_root=root is not None,
            has_view=view is not None,
        )

    def validate_dependencies(self) -> bool:
        """Validate that required dependencies are present.

        Returns:
            bool: True if all required dependencies are present

        Raises:
            CoordinatorValidationError: If required dependencies are missing
        """
        if self.weight_manager is None:
            raise CoordinatorValidationError(
                "WeightManager is required but was None",
                context={
                    "coordinator": "ModelDiagnosticsCoordinator",
                    "missing_dependency": "weight_manager",
                },
            )
        return True

    def run_model_diagnostic(self, config: dict) -> None:
        """Prepare for and launch the diagnostic test in a background thread.

        Shows a progress dialog during execution.

        Args:
            config: Diagnostic configuration dictionary with:
                - video_path: Path to test video
                - frames_to_analyze: Number of frames to analyze
                - confidence_threshold: Detection confidence threshold
                - model_to_test: 'YOLO (PyTorch)', 'OpenVINO', or 'Ambos'
                - parent_dialog: Optional dialog to close after launching
                - active_weight_name: Optional weight name override

        Note:
            This method validates dependencies, handles OpenVINO conversion
            if needed, creates a progress dialog, and launches the diagnostic
            in a background thread.

        Raises:
            CoordinatorValidationError: If required dependencies are missing
        """
        # Validate dependencies
        if not self.validate_dependencies():
            raise CoordinatorValidationError(
                "Cannot run diagnostic - dependencies invalid",
                context={"config": config},
            )

        log.info("model_diagnostics.diagnostic.start", config=config)

        # Close the CalibrationDialog if passed
        parent_dialog = config.pop("parent_dialog", None)
        if parent_dialog:
            parent_dialog.destroy()

        if self.view:
            self.view.set_status("Iniciando diagnóstico do modelo...")
            self.view.update_idletasks()

        model_to_test = config["model_to_test"]

        # Get active weight details
        # 1. Try from config (passed by ViewModel)
        active_weight_name = config.get("active_weight_name")

        # 2. Fallback to WeightManager (if available, though typically stateless)
        if not active_weight_name:
            active_weight_name = getattr(self.weight_manager, "active_weight_name", None)

        if not active_weight_name and hasattr(self.weight_manager, "get_active_weight_name"):
            active_weight_name = self.weight_manager.get_active_weight_name()

        active_weight_details = (
            self.weight_manager.get_weight_details(active_weight_name)
            if self.weight_manager and active_weight_name
            else None
        )

        log.info(
            "model_diagnostics.diagnostic.active_weight",
            active_weight_name=active_weight_name,
            pytorch_path=(active_weight_details.get("path") if active_weight_details else None),
            openvino_path=(
                active_weight_details.get("openvino_path") if active_weight_details else None
            ),
        )

        if not active_weight_details:
            if self.event_bus:
                self.event_bus.publish(
                    Event(
                        type=UIEvents.UI_SHOW_ERROR,
                        data={"title": "Erro", "message": "Nenhum peso ativo selecionado."},
                    )
                )
            return

        # --- Pre-flight checks (OpenVINO conversion) ---
        if model_to_test in ["OpenVINO", "Ambos"]:
            ov_path = active_weight_details.get("openvino_path")
            # Validate that the OpenVINO directory exists AND contains .xml files
            if not _is_valid_openvino_directory(ov_path):
                log.warning(
                    "diagnostic.openvino.invalid_directory",
                    path=ov_path,
                    exists=os.path.exists(ov_path) if ov_path else False,
                )
                # Clean up corrupted/empty directory if it exists
                if ov_path and os.path.exists(ov_path) and os.path.isdir(ov_path):
                    try:
                        shutil.rmtree(ov_path, ignore_errors=True)
                        log.info("diagnostic.openvino.corrupted_directory_removed", path=ov_path)
                    except OSError as e:
                        log.warning(
                            "diagnostic.openvino.cleanup_failed", path=ov_path, error=str(e)
                        )

                if self.view and self.view.dialog_manager.ask_ok_cancel(
                    "Converter Modelo?",
                    (
                        "O modelo OpenVINO não foi encontrado ou está incompleto. "
                        "Deseja convertê-lo agora?"
                    ),
                ):
                    # Delegate to conversion callback if set
                    if hasattr(self, "_convert_weight_callback"):
                        self._convert_weight_callback(active_weight_name)
                    else:
                        log.error(
                            "model_diagnostics.diagnostic.no_convert_callback",
                            message="Conversion callback not set",
                        )

                    # Refresh details after conversion
                    if active_weight_name:
                        active_weight_details = self.weight_manager.get_weight_details(
                            str(active_weight_name)
                        )
                    else:
                        active_weight_details = None

                    if not active_weight_details or not _is_valid_openvino_directory(
                        active_weight_details.get("openvino_path")
                    ):
                        if self.event_bus:
                            self.event_bus.publish(
                                Event(
                                    type=UIEvents.UI_SHOW_ERROR,
                                    data={
                                        "title": "Erro",
                                        "message": "A conversão para OpenVINO falhou.",
                                    },
                                )
                            )
                        return
                else:
                    log.warning("diagnostic.openvino.conversion_skipped")
                    # If user skips conversion, modify config to only run YOLO if possible
                    if model_to_test == "Ambos":
                        config["model_to_test"] = "YOLO (PyTorch)"
                    else:  # model_to_test was 'OpenVINO'
                        if self.event_bus:
                            self.event_bus.publish(
                                Event(
                                    type=UIEvents.UI_SET_STATUS,
                                    data={"message": "Diagnóstico cancelado."},
                                )
                            )
                        return

        # --- Create and show progress dialog ---
        from zebtrack.ui.dialogs import DiagnosticProgressDialog

        progress_dialog = DiagnosticProgressDialog(self.root) if self.root else None
        config["progress_dialog"] = progress_dialog

        # --- Launch background thread ---
        if self.cancel_event:
            self.cancel_event.clear()

        thread = threading.Thread(
            target=self._diagnostic_processing_thread,
            args=(config, active_weight_details),
            daemon=True,
        )
        thread.start()

    def _diagnostic_processing_thread(self, config: dict, weight_details: dict) -> None:
        """Run actual diagnostic processing logic in a background thread.

        Updates progress dialog during execution.

        Args:
            config: Diagnostic configuration
            weight_details: Active weight details from WeightManager
        """
        video_path = config["video_path"]
        frames_to_analyze = config["frames_to_analyze"]
        conf_threshold = config["confidence_threshold"]
        model_to_test = config["model_to_test"]
        progress_dialog = config.get("progress_dialog")
        results: dict[str, list] = {}

        try:
            self._update_diagnostic_progress(progress_dialog, "Carregando modelos...")

            yolo_model = self._initialize_diagnostic_yolo_model(
                model_to_test, weight_details, results, progress_dialog
            )

            openvino_model = self._initialize_diagnostic_openvino_model(
                model_to_test, weight_details, results, progress_dialog
            )

            self._run_diagnostic_frame_loop(
                video_path,
                frames_to_analyze,
                conf_threshold,
                yolo_model,
                openvino_model,
                results,
                progress_dialog,
            )

            self._finish_progress_dialog(progress_dialog)

            # --- Schedule report generation on main thread ---
            if self.root:
                self.root.after(0, self._finish_diagnostic_and_save_report, config, results)
            else:
                self._finish_diagnostic_and_save_report(config, results)

        except DiagnosticAbortError:
            # DiagnosticAbortError is raised to abort diagnostics (e.g., user cancellation).
            # No further action needed; abort is intentional and handled gracefully.
            pass
        except Exception as e:  # except Exception justified: ML inference heterogeneous errors
            log.error("diagnostic.thread.load_error", exc_info=True)
            self._finish_progress_dialog(progress_dialog)
            if self.event_bus:
                self.event_bus.publish(
                    Event(
                        type=UIEvents.UI_SHOW_ERROR,
                        data={"title": "Erro ao Carregar Modelo", "message": f"Falha: {e}"},
                    )
                )

    def _update_diagnostic_progress(
        self,
        progress_dialog: Any,
        message: str,
        current: int | None = None,
        total: int | None = None,
    ) -> None:
        """Thread-safe progress dialog update helper.

        Args:
            progress_dialog: DiagnosticProgressDialog instance
            message: Status message to display
            current: Current progress value
            total: Total progress value
        """
        if not progress_dialog or not self.root:
            return

        def _update():
            if hasattr(progress_dialog, "update_progress"):
                progress_dialog.update_progress(message, current, total)

        self.root.after(0, _update)

    def _finish_progress_dialog(self, progress_dialog: Any) -> None:
        """Safely close the diagnostic progress dialog.

        Args:
            progress_dialog: DiagnosticProgressDialog instance
        """
        if not progress_dialog or not self.root:
            return

        def _finish():
            if hasattr(progress_dialog, "destroy"):
                try:
                    progress_dialog.destroy()
                except Exception as e:  # except Exception justified: cross-platform Tk teardown
                    log.warning("model_diagnostics.finish_progress.error", error=str(e))

        self.root.after(0, _finish)

    def _initialize_diagnostic_yolo_model(
        self,
        model_to_test: str,
        weight_details: dict,
        results: dict[str, list],
        progress_dialog: Any,
    ) -> Any | None:
        """Set up YOLO model for diagnostics.

        Args:
            model_to_test: Model type to test
            weight_details: Active weight details
            results: Results dictionary to populate
            progress_dialog: Progress dialog instance

        Returns:
            YOLO model instance or None

        Raises:
            DiagnosticAbortError: If YOLO setup fails
        """
        if model_to_test not in ["YOLO (PyTorch)", "Ambos"]:
            return None

        if not ULTRALYTICS_AVAILABLE:
            log.error("diagnostic.yolo.unavailable")
            self._finish_progress_dialog(progress_dialog)
            if self.event_bus:
                self.event_bus.publish(
                    Event(
                        type=UIEvents.UI_SHOW_ERROR,
                        data={
                            "title": "Erro",
                            "message": "YOLO não está disponível (ultralytics não instalado)",
                        },
                    )
                )
            raise DiagnosticAbortError from None

        if YOLO is None:  # Defensive guard for type checkers.
            raise DiagnosticAbortError from None

        yolo_ctor = cast(Any, YOLO)
        yolo_model = yolo_ctor(weight_details["path"])
        if hasattr(yolo_model, "set_context"):
            yolo_model.set_context("diagnostic")
            log.info("diagnostic.thread.yolo_context_set", context="diagnostic")
        results["YOLO (PyTorch)"] = []
        return yolo_model

    def _initialize_diagnostic_openvino_model(
        self,
        model_to_test: str,
        weight_details: dict,
        results: dict[str, list],
        progress_dialog: Any,
    ) -> Any | None:
        """Set up OpenVINO model for diagnostics.

        Args:
            model_to_test: Model type to test
            weight_details: Active weight details
            results: Results dictionary to populate
            progress_dialog: Progress dialog instance

        Returns:
            OpenVINO model instance or None

        Raises:
            DiagnosticAbortError: If OpenVINO setup fails
        """
        if model_to_test not in ["OpenVINO", "Ambos"]:
            return None

        ov_path = weight_details.get("openvino_path")

        if not _is_valid_openvino_directory(ov_path):
            log.error(
                "diagnostic.thread.openvino_invalid",
                path=ov_path,
                exists=os.path.exists(ov_path) if ov_path else False,
            )
            self._finish_progress_dialog(progress_dialog)
            if self.event_bus:
                self.event_bus.publish(
                    Event(
                        type=UIEvents.UI_SHOW_ERROR,
                        data={
                            "title": "Erro de Modelo",
                            "message": (
                                "O diretório do modelo OpenVINO não contém arquivos "
                                ".xml necessários. Por favor, reconverta o modelo."
                            ),
                        },
                    )
                )
            raise DiagnosticAbortError from None

        plugin_class = DETECTOR_PLUGINS.get("OpenVINO")
        if not plugin_class:
            log.error("diagnostic.thread.openvino_plugin_missing")
            self._finish_progress_dialog(progress_dialog)
            if self.event_bus:
                self.event_bus.publish(
                    Event(
                        type=UIEvents.UI_SHOW_ERROR,
                        data={
                            "title": "Erro de Plugin",
                            "message": "Plugin OpenVINO não encontrado para diagnóstico.",
                        },
                    )
                )
            raise DiagnosticAbortError from None

        assert ov_path is not None  # guaranteed by _is_valid_openvino_directory check above
        openvino_model = plugin_class(ov_path)
        if not hasattr(openvino_model, "predict"):
            log.error(
                "diagnostic.thread.missing_predict_method",
                plugin_class=str(plugin_class),
            )
            self._finish_progress_dialog(progress_dialog)
            if self.event_bus:
                self.event_bus.publish(
                    Event(
                        type=UIEvents.UI_SHOW_ERROR,
                        data={
                            "title": "Erro de Plugin",
                            "message": "O plugin OpenVINO não possui o método predict necessário.",
                        },
                    )
                )
            raise DiagnosticAbortError from None

        if hasattr(openvino_model, "set_context"):
            openvino_model.set_context("diagnostic")
            log.info("diagnostic.thread.openvino_context_set", context="diagnostic")

        results["OpenVINO"] = []
        log.info("diagnostic.thread.openvino_loaded", path=ov_path)
        return openvino_model

    def _run_diagnostic_frame_loop(
        self,
        video_path: Path | str,
        frames_to_analyze: int,
        conf_threshold: float,
        yolo_model: Any,
        openvino_model: Any,
        results: dict[str, list],
        progress_dialog: Any,
    ) -> None:
        """Process video frames for the diagnostic routine.

        Args:
            video_path: Path to video file
            frames_to_analyze: Number of frames to process
            conf_threshold: Confidence threshold for detections
            yolo_model: YOLO model instance or None
            openvino_model: OpenVINO model instance or None
            results: Results dictionary to populate
            progress_dialog: Progress dialog instance

        Raises:
            DiagnosticAbortError: If processing is cancelled or fails
        """
        cap = cv2.VideoCapture(video_path)

        if not cap.isOpened():
            self._finish_progress_dialog(progress_dialog)
            if self.event_bus:
                self.event_bus.publish(
                    Event(
                        type=UIEvents.UI_SHOW_ERROR,
                        data={
                            "title": "Erro",
                            "message": f"Não foi possível abrir o vídeo: {video_path}",
                        },
                    )
                )
            raise DiagnosticAbortError from None

        try:
            for frame_count in range(frames_to_analyze):
                if self.cancel_event and self.cancel_event.is_set():
                    log.info("diagnostic.thread.cancelled_by_event")
                    self._finish_progress_dialog(progress_dialog)
                    return

                if progress_dialog and getattr(progress_dialog, "user_cancelled", False):
                    log.info("diagnostic.thread.cancelled_by_user")
                    self._finish_progress_dialog(progress_dialog)
                    return

                ret, frame = cap.read()
                if not ret:
                    break

                status_msg = f"Analisando frame {frame_count + 1}/{frames_to_analyze}..."
                self._update_diagnostic_progress(
                    progress_dialog,
                    status_msg,
                    frame_count + 1,
                    frames_to_analyze,
                )

                if self.event_bus:
                    self.event_bus.publish(
                        Event(
                            type=UIEvents.UI_SET_STATUS,
                            data={"message": status_msg},
                        )
                    )

                if yolo_model is not None:
                    preds = yolo_model.predict(frame, conf=conf_threshold, verbose=False)
                    results.setdefault("YOLO (PyTorch)", []).append(preds[0])

                if openvino_model is not None:
                    try:
                        log.debug(
                            "diagnostic.thread.openvino_predict_start",
                            frame=frame_count + 1,
                        )
                        preds = openvino_model.predict(frame, conf_threshold)
                        log.debug(
                            "diagnostic.thread.openvino_predict_success",
                            frame=frame_count + 1,
                            detections=len(preds),
                        )
                        results.setdefault("OpenVINO", []).append(preds)
                    except Exception as exc:  # pragma: no cover - plugin specific
                        log.error(
                            "diagnostic.thread.openvino_predict_error",
                            frame=frame_count + 1,
                            exc_info=True,
                        )
                        self._finish_progress_dialog(progress_dialog)
                        if self.event_bus:
                            self.event_bus.publish(
                                Event(
                                    type=UIEvents.UI_SHOW_ERROR,
                                    data={
                                        "title": "Erro de Inferência OpenVINO",
                                        "message": (
                                            f"Falha na inferência do frame {frame_count + 1}: {exc}"
                                        ),
                                    },
                                )
                            )
                        raise DiagnosticAbortError from None
        finally:
            cap.release()

    def _finish_diagnostic_and_save_report(self, config: dict, results: dict) -> None:
        """Format and save the report. Runs on the main UI thread.

        Args:
            config: Diagnostic configuration
            results: Diagnostic results from processing
        """
        report_str = self._format_diagnostic_report(config, results)

        if not self.view:
            log.warning("model_diagnostics.diagnostic.no_view_for_save")
            return

        save_path = self.view.dialog_manager.ask_save_filename(
            title="Salvar Relatório de Diagnóstico",
            defaultextension=".txt",
            initialfile="diagnostic_report.txt",
            filetypes=[("Arquivos de Texto", "*.txt")],
        )

        if save_path:
            try:
                with open(save_path, "w", encoding="utf-8") as f:
                    f.write(report_str)
                if self.event_bus:
                    self.event_bus.publish(
                        Event(
                            type=UIEvents.UI_SHOW_INFO,
                            data={
                                "title": "Sucesso",
                                "message": f"Relatório de diagnóstico salvo em:\n{save_path}",
                            },
                        )
                    )
            except OSError as e:
                if self.event_bus:
                    self.event_bus.publish(
                        Event(
                            type=UIEvents.UI_SHOW_ERROR,
                            data={
                                "title": "Erro ao Salvar",
                                "message": f"Não foi possível salvar o arquivo: {e}",
                            },
                        )
                    )

        if self.event_bus:
            self.event_bus.publish(
                Event(
                    type=UIEvents.UI_SET_STATUS, data={"message": "Diagnóstico concluído. Pronto."}
                )
            )

    def _format_diagnostic_report(self, config: dict, results: dict) -> str:
        """Format the collected diagnostic data into a string.

        Args:
            config: Diagnostic configuration
            results: Diagnostic results from processing

        Returns:
            Formatted report string
        """
        report_lines = [
            "Relatório de Diagnóstico do Modelo",
            "-----------------------------------",
            f"- Vídeo: {config['video_path']}",
            f"- Frames Analisados: {config['frames_to_analyze']}",
            f"- Limiar de Confiança: {config['confidence_threshold']}",
            "-----------------------------------",
            "",
        ]

        for model_name, preds_list in results.items():
            report_lines.append(f"--- [ RESULTADOS {model_name.upper()} ] ---")
            report_lines.append("")

            for i, preds in enumerate(preds_list):
                frame_num = i + 1
                report_lines.append(f"Frame {frame_num}:")

                detections = []
                mask_only_detections = []

                # Handle ultralytics results object
                if hasattr(preds, "boxes") or hasattr(preds, "masks"):
                    # Process boxes with their masks
                    if preds.boxes is not None:
                        for j, box in enumerate(preds.boxes):
                            class_id = int(box.cls)
                            class_name = preds.names.get(class_id, "desconhecido")
                            conf = float(box.conf)
                            bbox = [int(coord) for coord in box.xyxy[0]]

                            # Check if mask is present
                            has_mask = (
                                preds.masks is not None
                                and preds.masks.xy is not None
                                and j < len(preds.masks.xy)
                            )
                            mask_info = (
                                f", Máscara: {len(preds.masks.xy[j])} pontos" if has_mask else ""
                            )

                            detections.append(
                                f"  - Classe {class_id} ('{class_name}'), "
                                f"Conf: {conf:.2f}, BBox: {bbox}{mask_info}"
                            )

                    # Process orphan masks (without boxes)
                    if preds.masks is not None and preds.masks.xy is not None:
                        num_boxes = len(preds.boxes) if preds.boxes else 0
                        for j in range(num_boxes, len(preds.masks.xy)):
                            mask = preds.masks.xy[j]
                            x_min = int(mask[:, 0].min())
                            y_min = int(mask[:, 1].min())
                            x_max = int(mask[:, 0].max())
                            y_max = int(mask[:, 1].max())
                            area = (x_max - x_min) * (y_max - y_min)

                            mask_only_detections.append(
                                f"  - [MÁSCARA SEM BOX] Provável Aquário, "
                                f"BBox aprox: [{x_min}, {y_min}, {x_max}, {y_max}], "
                                f"Área: {area}, Pontos: {len(mask)}"
                            )

                # Handle OpenVINO plugin format
                elif isinstance(preds, list):
                    for det in preds:
                        class_id = det["class_id"]
                        class_name = det["class_name"]
                        conf = det["confidence"]
                        bbox = det["box"]
                        mask_info = (
                            f", Máscara: {det.get('mask_points', 0)} pontos"
                            if det.get("has_mask")
                            else ""
                        )

                        detections.append(
                            f"  - Classe {class_id} ('{class_name}'), "
                            f"Conf: {conf:.2f}, BBox: {bbox}{mask_info}"
                        )

                # Add detections to report
                if detections:
                    report_lines.extend(detections)
                if mask_only_detections:
                    report_lines.append("  Máscaras sem bounding box (possíveis aquários):")
                    report_lines.extend(mask_only_detections)
                if not detections and not mask_only_detections:
                    report_lines.append("  - Nenhuma detecção encontrada.")

                report_lines.append("")

            report_lines.append("")  # Spacer between models

        return "\n".join(report_lines)

    def __repr__(self) -> str:
        """Return string representation of ModelDiagnosticsCoordinator."""
        return (
            f"<ModelDiagnosticsCoordinator("
            f"has_weight_manager={self.weight_manager is not None}, "
            f"has_view={self.view is not None}, "
            f"has_root={self.root is not None}"
            f")>"
        )
