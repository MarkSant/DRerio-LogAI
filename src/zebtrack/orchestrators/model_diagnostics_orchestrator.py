"""Model diagnostics orchestration logic extracted from MainViewModel.

Sprint 29 - Extracted to reduce MainViewModel complexity.
"""

from __future__ import annotations

import glob
import os
import shutil
import threading
from typing import TYPE_CHECKING, Any, cast

import cv2
import structlog

try:
    from ultralytics import YOLO

    ULTRALYTICS_AVAILABLE = True
except ImportError:
    YOLO = None
    ULTRALYTICS_AVAILABLE = False

from zebtrack.core.processing_mode import ProcessingMode
from zebtrack.plugins import DETECTOR_PLUGINS
from zebtrack.ui.events import Events

if TYPE_CHECKING:
    from zebtrack.core.main_view_model import MainViewModel

logger = structlog.get_logger()


def _is_valid_openvino_directory(path: str | None) -> bool:
    """
    Validate if an OpenVINO model directory exists and contains required .xml files.

    Args:
        path: Path to the OpenVINO model directory

    Returns:
        True if the directory exists and contains at least one .xml file, False otherwise
    """
    if not path or not os.path.exists(path):
        return False

    if not os.path.isdir(path):
        return False

    xml_files = glob.glob(os.path.join(path, "*.xml"))
    return len(xml_files) > 0


class DiagnosticAbortError(RuntimeError):
    """Signal used to stop diagnostic workflow without surfacing duplicate dialogs."""


class ModelDiagnosticsOrchestrator:
    """Orchestrates model diagnostic workflows.

    Extracted from MainViewModel in Sprint 29 to reduce its size.
    Maintains reference to MainViewModel for delegation during gradual extraction.

    This class handles:
    - Model diagnostic test execution
    - YOLO and OpenVINO model initialization for diagnostics
    - Frame-by-frame diagnostic processing
    - Diagnostic report generation and formatting
    """

    def __init__(self, main_view_model: MainViewModel):
        """Initialize with MainViewModel reference.

        Args:
            main_view_model: Reference to MainViewModel for delegation
        """
        self.main_view_model = main_view_model

        # Cache frequently used attributes from MainViewModel
        self.view = main_view_model.view
        self.root = main_view_model.root
        self.settings = main_view_model.settings
        self.weight_manager = main_view_model.weight_manager
        self.model_service = main_view_model.model_service
        self.ui_event_bus = main_view_model.ui_event_bus
        self.ui_state_controller = main_view_model.ui_state_controller
        self.cancel_event = main_view_model.cancel_event
        # Note: active_weight_name is a property, not cached

    def run_model_diagnostic(self, config: dict):
        """
        Prepare for and launches the diagnostic test in a background thread.

        Now shows a progress dialog during execution.
        """
        logger.info("controller.diagnostic.start", config=config)

        # Close the CalibrationDialog if passed
        parent_dialog = config.pop("parent_dialog", None)
        if parent_dialog:
            parent_dialog.destroy()

        self.view.set_status("Iniciando diagnóstico do modelo...")
        self.view.update_idletasks()

        model_to_test = config["model_to_test"]
        active_weight_details = self.weight_manager.get_weight_details(
            self.main_view_model.active_weight_name
        )
        logger.info(
            "controller.diagnostic.active_weight",
            active_weight_name=self.main_view_model.active_weight_name,
            pytorch_path=(active_weight_details.get("path") if active_weight_details else None),
            openvino_path=(
                active_weight_details.get("openvino_path") if active_weight_details else None
            ),
        )
        if not active_weight_details:
            self.ui_event_bus.publish_event(
                Events.UI_SHOW_ERROR,
                {"title": "Erro", "message": "Nenhum peso ativo selecionado."},
            )
            return

        # --- Pre-flight checks (OpenVINO conversion) ---
        if model_to_test in ["OpenVINO", "Ambos"]:
            ov_path = active_weight_details.get("openvino_path")
            # Validate that the OpenVINO directory exists AND contains .xml files
            if not _is_valid_openvino_directory(ov_path):
                logger.warning(
                    "diagnostic.openvino.invalid_directory",
                    path=ov_path,
                    exists=os.path.exists(ov_path) if ov_path else False,
                )
                # Clean up corrupted/empty directory if it exists
                if ov_path and os.path.exists(ov_path) and os.path.isdir(ov_path):
                    try:
                        shutil.rmtree(ov_path, ignore_errors=True)
                        logger.info("diagnostic.openvino.corrupted_directory_removed", path=ov_path)
                    except Exception as e:
                        logger.warning(
                            "diagnostic.openvino.cleanup_failed", path=ov_path, error=str(e)
                        )

                if self.view.ask_ok_cancel(
                    "Converter Modelo?",
                    (
                        "O modelo OpenVINO não foi encontrado ou está incompleto. "
                        "Deseja convertê-lo agora?"
                    ),
                ):
                    self.main_view_model.convert_active_weight_to_openvino(dialog=None)
                    # Refresh details after conversion
                    active_weight_details = self.weight_manager.get_weight_details(
                        self.main_view_model.active_weight_name
                    )
                    if not _is_valid_openvino_directory(active_weight_details.get("openvino_path")):
                        self.ui_event_bus.publish_event(
                            Events.UI_SHOW_ERROR,
                            {"title": "Erro", "message": "A conversão para OpenVINO falhou."},
                        )
                        return
                else:
                    logger.warning("diagnostic.openvino.conversion_skipped")
                    # If user skips conversion, modify config to only run YOLO if
                    # possible
                    if model_to_test == "Ambos":
                        config["model_to_test"] = "YOLO (PyTorch)"
                    else:  # model_to_test was 'OpenVINO'
                        self.ui_event_bus.publish_event(
                            Events.UI_SET_STATUS, {"message": "Diagnóstico cancelado."}
                        )
                        return

        # --- Create and show progress dialog ---
        from zebtrack.ui.dialogs import DiagnosticProgressDialog

        progress_dialog = DiagnosticProgressDialog(self.root)
        config["progress_dialog"] = progress_dialog

        # --- Launch background thread ---
        self.cancel_event.clear()
        self.main_view_model._publish_processing_mode(
            source="diagnostic.start",
            force=True,
            mode_override=ProcessingMode.SINGLE_SUBJECT,
        )
        thread = threading.Thread(
            target=self._diagnostic_processing_thread,
            args=(config, active_weight_details),
            daemon=True,
        )
        thread.start()

    def _diagnostic_processing_thread(self, config: dict, weight_details: dict):
        """
        Run actual diagnostic processing logic in a background thread.

        Updates progress dialog during execution.
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
            self.root.after(0, self._finish_diagnostic_and_save_report, config, results)
        except DiagnosticAbortError:
            # DiagnosticAbortError is raised to abort diagnostics (e.g., user cancellation).
            # No further action needed; abort is intentional and handled gracefully.
            pass
        except Exception as e:
            logger.error("diagnostic.thread.load_error", exc_info=True)
            self._finish_progress_dialog(progress_dialog)
            self.ui_event_bus.publish_event(
                Events.UI_SHOW_ERROR,
                {"title": "Erro ao Carregar Modelo", "message": f"Falha: {e}"},
            )
        finally:
            self.main_view_model._publish_processing_mode(
                source="diagnostic.thread_exit",
                force=True,
            )

    def _update_diagnostic_progress(
        self,
        progress_dialog,
        message: str,
        current: int | None = None,
        total: int | None = None,
    ) -> None:
        """Thread-safe progress dialog update helper.

        Facade - delegates to UIStateController (Sprint 28).
        """
        return self.ui_state_controller._update_diagnostic_progress(
            progress_dialog=progress_dialog,
            message=message,
            current=current,
            total=total,
        )

    def _finish_progress_dialog(self, progress_dialog) -> None:
        """Safely close the diagnostic progress dialog.

        Facade - delegates to UIStateController (Sprint 28).
        """
        return self.ui_state_controller._finish_progress_dialog(progress_dialog=progress_dialog)

    def _initialize_diagnostic_yolo_model(
        self,
        model_to_test: str,
        weight_details: dict,
        results: dict[str, list],
        progress_dialog,
    ) -> Any | None:
        """Set up YOLO model for diagnostics."""
        if model_to_test not in ["YOLO (PyTorch)", "Ambos"]:
            return None

        bus = self.ui_event_bus

        if not ULTRALYTICS_AVAILABLE:
            logger.error("diagnostic.yolo.unavailable")
            self._finish_progress_dialog(progress_dialog)
            if bus:
                bus.publish_event(
                    Events.UI_SHOW_ERROR,
                    {
                        "title": "Erro",
                        "message": "YOLO não está disponível (ultralytics não instalado)",
                    },
                )
            raise DiagnosticAbortError from None

        if YOLO is None:  # Defensive guard for type checkers.
            raise DiagnosticAbortError from None

        yolo_ctor = cast(Any, YOLO)
        yolo_model = yolo_ctor(weight_details["path"])
        if hasattr(yolo_model, "set_context"):
            yolo_model.set_context("diagnostic")
            logger.info("diagnostic.thread.yolo_context_set", context="diagnostic")
        results["YOLO (PyTorch)"] = []
        return yolo_model

    def _initialize_diagnostic_openvino_model(
        self,
        model_to_test: str,
        weight_details: dict,
        results: dict[str, list],
        progress_dialog,
    ) -> Any | None:
        """Set up OpenVINO model for diagnostics."""
        if model_to_test not in ["OpenVINO", "Ambos"]:
            return None

        ov_path = weight_details.get("openvino_path")
        bus = self.ui_event_bus

        if not _is_valid_openvino_directory(ov_path):
            logger.error(
                "diagnostic.thread.openvino_invalid",
                path=ov_path,
                exists=os.path.exists(ov_path) if ov_path else False,
            )
            self._finish_progress_dialog(progress_dialog)
            if bus:
                bus.publish_event(
                    Events.UI_SHOW_ERROR,
                    {
                        "title": "Erro de Modelo",
                        "message": (
                            "O diretório do modelo OpenVINO não contém arquivos "
                            ".xml necessários. Por favor, reconverta o modelo."
                        ),
                    },
                )
            raise DiagnosticAbortError from None

        plugin_class = DETECTOR_PLUGINS.get("OpenVINO")
        if not plugin_class:
            logger.error("diagnostic.thread.openvino_plugin_missing")
            self._finish_progress_dialog(progress_dialog)
            if bus:
                bus.publish_event(
                    Events.UI_SHOW_ERROR,
                    {
                        "title": "Erro de Plugin",
                        "message": "Plugin OpenVINO não encontrado para diagnóstico.",
                    },
                )
            raise DiagnosticAbortError from None

        openvino_model = plugin_class(ov_path)
        if not hasattr(openvino_model, "predict"):
            logger.error(
                "diagnostic.thread.missing_predict_method",
                plugin_class=str(plugin_class),
            )
            self._finish_progress_dialog(progress_dialog)
            if bus:
                bus.publish_event(
                    Events.UI_SHOW_ERROR,
                    {
                        "title": "Erro de Plugin",
                        "message": "O plugin OpenVINO não possui o método predict necessário.",
                    },
                )
            raise DiagnosticAbortError from None

        if hasattr(openvino_model, "set_context"):
            openvino_model.set_context("diagnostic")
            logger.info("diagnostic.thread.openvino_context_set", context="diagnostic")

        results["OpenVINO"] = []
        logger.info("diagnostic.thread.openvino_loaded", path=ov_path)
        return openvino_model

    def _run_diagnostic_frame_loop(
        self,
        video_path: str,
        frames_to_analyze: int,
        conf_threshold: float,
        yolo_model,
        openvino_model,
        results: dict[str, list],
        progress_dialog,
    ) -> None:
        """Process video frames for the diagnostic routine."""
        cap = cv2.VideoCapture(video_path)
        bus = self.ui_event_bus

        if not cap.isOpened():
            self._finish_progress_dialog(progress_dialog)
            if bus:
                bus.publish_event(
                    Events.UI_SHOW_ERROR,
                    {
                        "title": "Erro",
                        "message": f"Não foi possível abrir o vídeo: {video_path}",
                    },
                )
            raise DiagnosticAbortError from None

        try:
            for frame_count in range(frames_to_analyze):
                if self.cancel_event.is_set() or (
                    progress_dialog and getattr(progress_dialog, "user_cancelled", False)
                ):
                    logger.info("diagnostic.thread.cancelled_by_user")
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

                if bus:
                    bus.publish_event(Events.UI_SET_STATUS, {"message": status_msg})

                if yolo_model is not None:
                    preds = yolo_model.predict(frame, conf=conf_threshold, verbose=False)
                    results.setdefault("YOLO (PyTorch)", []).append(preds[0])

                if openvino_model is not None:
                    try:
                        logger.debug(
                            "diagnostic.thread.openvino_predict_start",
                            frame=frame_count + 1,
                        )
                        preds = openvino_model.predict(frame, conf_threshold)
                        logger.debug(
                            "diagnostic.thread.openvino_predict_success",
                            frame=frame_count + 1,
                            detections=len(preds),
                        )
                        results.setdefault("OpenVINO", []).append(preds)
                    except Exception as exc:  # pragma: no cover - plugin specific
                        logger.error(
                            "diagnostic.thread.openvino_predict_error",
                            frame=frame_count + 1,
                            exc_info=True,
                        )
                        self._finish_progress_dialog(progress_dialog)
                        if bus:
                            bus.publish_event(
                                Events.UI_SHOW_ERROR,
                                {
                                    "title": "Erro de Inferência OpenVINO",
                                    "message": (
                                        f"Falha na inferência do frame {frame_count + 1}: {exc}"
                                    ),
                                },
                            )
                        raise DiagnosticAbortError from None
        finally:
            cap.release()

    def _finish_diagnostic_and_save_report(self, config, results):
        """Format and saves the report. Runs on the main UI thread."""
        report_str = self._format_diagnostic_report(config, results)
        save_path = self.view.ask_save_filename(
            title="Salvar Relatório de Diagnóstico",
            defaultextension=".txt",
            initialfile="diagnostic_report.txt",
            filetypes=[("Arquivos de Texto", "*.txt")],
        )

        if save_path:
            try:
                with open(save_path, "w", encoding="utf-8") as f:
                    f.write(report_str)
                self.ui_event_bus.publish_event(
                    Events.UI_SHOW_INFO,
                    {
                        "title": "Sucesso",
                        "message": f"Relatório de diagnóstico salvo em:\n{save_path}",
                    },
                )
            except OSError as e:
                self.ui_event_bus.publish_event(
                    Events.UI_SHOW_ERROR,
                    {
                        "title": "Erro ao Salvar",
                        "message": f"Não foi possível salvar o arquivo: {e}",
                    },
                )

        self.main_view_model._publish_processing_mode(
            source="diagnostic.complete",
            force=True,
        )
        self.ui_event_bus.publish_event(
            Events.UI_SET_STATUS, {"message": "Diagnóstico concluído. Pronto."}
        )

    def _format_diagnostic_report(self, config, results) -> str:
        """Format the collected diagnostic data into a string."""
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
                    # Processa boxes com suas máscaras
                    if preds.boxes is not None:
                        for j, box in enumerate(preds.boxes):
                            class_id = int(box.cls)
                            class_name = preds.names.get(class_id, "desconhecido")
                            conf = float(box.conf)
                            bbox = [int(coord) for coord in box.xyxy[0]]

                            # Verifica se tem máscara
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

                    # Processa máscaras sem boxes (órfãs)
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

                # Adiciona detecções ao relatório
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
