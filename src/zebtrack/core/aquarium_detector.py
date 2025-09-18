import cv2
import numpy as np
import structlog
from shapely.geometry import Polygon
from ultralytics import YOLO

from zebtrack.io.video_source import VideoFileSource

log = structlog.get_logger()


class AquariumDetector:
    """
    Detects aquariums in a video using a YOLO segmentation model.
    """

    def __init__(self, model_path: str):
        """
        Initializes the AquariumDetector.

        Args:
            model_path (str): Path to the YOLO segmentation model (.pt file).
        """
        try:
            self.model = YOLO(model_path)
            log.info("aquarium_detector.init.success", model_path=model_path)
        except Exception as e:
            log.error(
                "aquarium_detector.init.failed", model_path=model_path, error=str(e)
            )
            raise

    def _calculate_iou(self, poly1_points, poly2_points) -> float:
        """Calculates the Intersection over Union (IoU) of two polygons."""
        try:
            poly1 = Polygon(poly1_points)
            poly2 = Polygon(poly2_points)

            if not poly1.is_valid or not poly2.is_valid:
                return 0.0

            intersection_area = poly1.intersection(poly2).area
            union_area = poly1.union(poly2).area

            if union_area == 0:
                return 0.0

            return intersection_area / union_area
        except Exception as e:
            log.warning(
                "aquarium_detector.iou_calculation_failed",
                error=str(e),
                exc_info=True,
            )
            return 0.0

    def detect_aquariums(self, video_path: str, stabilization_frames: int = 10) -> list:
        """
        Analyzes initial frames of a video to find the most stable aquarium polygon
        using a consensus-based approach.

        This method collects polygons from frames where only one object is detected,
        then uses the Intersection over Union (IoU) metric to find the most
        representative (stable) polygon among them.

        Args:
            video_path (str): The path to the video file.
            stabilization_frames (int): The number of initial frames to analyze.

        Returns:
            A list containing the single most stable polygon, or an empty list if
            no stable polygon could be found.
        """
        log.info("aquarium_detector.detect.start", video_path=video_path)
        source = None
        try:
            source = VideoFileSource(video_path)
            good_polygons = []
            for i in range(stabilization_frames):
                ret, frame = source.get_frame()
                if not ret:
                    log.warning("aquarium_detector.detect.frame_read_failed", frame=i)
                    break

                # Primeiro tenta detectar aquário (classe 0) com threshold otimizado
                results = self.model.predict(
                    frame, verbose=False, classes=[0], conf=0.05
                )

                # Debug detalhado
                log.info("aquarium_detector.frame_analysis",
                    frame=i,
                    has_results=bool(results),
                    has_masks=bool(results and results[0].masks),
                    has_boxes=bool(results and results[0].boxes)
                )

                if results and results[0].masks:
                    log.info("aquarium_detector.masks_detail",
                        frame=i,
                        masks_xy_exists=bool(results[0].masks.xy),
                        num_masks=len(results[0].masks.xy) if results[0].masks.xy else 0
                    )

                # Melhora a lógica de detecção
                if results and results[0].masks and results[0].masks.xy:
                    polygons = results[0].masks.xy

                    # Coleta informações de confiança para logging
                    confidences = []
                    if results[0].boxes:
                        confidences = [float(box.conf) for box in results[0].boxes]

                    # Log informações de confiança
                    if confidences:
                        avg_conf = sum(confidences) / len(confidences)
                        max_conf = max(confidences)
                        log.info("aquarium_detector.confidence_check",
                            frame=i,
                            num_detections=len(polygons),
                            confidences=[f"{c:.3f}" for c in confidences],
                            avg_conf=f"{avg_conf:.3f}",
                            max_conf=f"{max_conf:.3f}"
                        )

                    # Log todas as máscaras encontradas
                    for j, poly in enumerate(polygons):
                        x_min, y_min = poly[:, 0].min(), poly[:, 1].min()
                        x_max, y_max = poly[:, 0].max(), poly[:, 1].max()
                        area = (x_max - x_min) * (y_max - y_min)

                        # Verifica se tem box correspondente para saber a classe
                        class_id = -1
                        if results[0].boxes and j < len(results[0].boxes):
                            class_id = int(results[0].boxes[j].cls)

                        log.info("aquarium_detector.mask_found",
                            frame=i,
                            mask_index=j,
                            class_id=class_id,
                            num_points=len(poly),
                            area=int(area),
                            bbox=[int(x_min), int(y_min), int(x_max), int(y_max)]
                        )

                    # Aceita frames com exatamente uma máscara grande
                    if len(polygons) == 1:
                        polygon = polygons[0].astype(np.int32)

                        # Valida que é grande o suficiente (mais de 30% do frame)
                        frame_area = frame.shape[0] * frame.shape[1]
                        x_min, y_min = polygon[:, 0].min(), polygon[:, 1].min()
                        x_max, y_max = polygon[:, 0].max(), polygon[:, 1].max()
                        poly_area = (x_max - x_min) * (y_max - y_min)

                        area_valid = poly_area > frame_area * 0.3

                        # Validação adicional de confiança (se houver boxes)
                        # Mas não bloqueia se não houver - mantém robustez
                        conf_valid = True
                        conf_info = "sem_box"
                        if confidences:
                            max_conf = max(confidences)
                            conf_valid = max_conf > 0.05  # Threshold baixo mas presente
                            conf_info = f"{max_conf:.3f}"

                        if area_valid and conf_valid:
                            good_polygons.append(polygon)
                            log.info("aquarium_detector.good_polygon",
                                frame=i,
                                area_ratio=poly_area/frame_area,
                                confidence=conf_info
                            )
                        elif not area_valid:
                            log.warning("aquarium_detector.polygon_too_small",
                                frame=i,
                                area_ratio=poly_area/frame_area,
                                confidence=conf_info
                            )
                        elif not conf_valid:
                            log.warning("aquarium_detector.confidence_too_low",
                                frame=i,
                                area_ratio=poly_area/frame_area,
                                confidence=conf_info,
                                threshold=0.05
                            )
                    else:
                        log.warning("aquarium_detector.wrong_mask_count",
                            frame=i,
                            num_masks=len(polygons),
                            expected=1
                        )
                else:
                    # Se não encontrou aquário, tenta estratégia alternativa
                    log.info("aquarium_detector.trying_fallback", frame=i)
                    results_all = self.model.predict(frame, verbose=False, conf=0.01)

                    if results_all and results_all[0].masks and results_all[0].masks.xy:
                        all_polygons = results_all[0].masks.xy
                        log.info("aquarium_detector.fallback_masks_found",
                                frame=i, num_masks=len(all_polygons))

                        # Procura pela maior máscara (provável aquário)
                        if all_polygons:
                            largest_area = 0
                            largest_polygon = None

                            for j, poly in enumerate(all_polygons):
                                x_min, y_min = poly[:, 0].min(), poly[:, 1].min()
                                x_max, y_max = poly[:, 0].max(), poly[:, 1].max()
                                area = (x_max - x_min) * (y_max - y_min)

                                if area > largest_area:
                                    largest_area = area
                                    largest_polygon = poly

                                log.info("aquarium_detector.fallback_mask",
                                        frame=i, mask_index=j, area=int(area))

                            # Se a maior máscara é grande o suficiente, aceita
                            if largest_polygon is not None:
                                frame_area = frame.shape[0] * frame.shape[1]
                                area_ratio = largest_area / frame_area

                                if area_ratio > 0.1:  # Pelo menos 10% do frame
                                    good_polygons.append(largest_polygon.astype(np.int32))
                                    log.info("aquarium_detector.fallback_polygon_accepted",
                                            frame=i, area_ratio=area_ratio)
                                else:
                                    log.warning("aquarium_detector.fallback_polygon_too_small",
                                               frame=i, area_ratio=area_ratio)

            if not good_polygons:
                log.warning("aquarium_detector.detect.no_good_polygons_found")
                log.info("aquarium_detector.generating_default_polygon")

                # Como último recurso, cria um polígono padrão baseado no tamanho
                # do frame
                # Assume aquário no centro com 80% da área do frame
                try:
                    cap_temp = source._cap if hasattr(source, '_cap') else None
                    if cap_temp:
                        w = int(cap_temp.get(cv2.CAP_PROP_FRAME_WIDTH))
                        h = int(cap_temp.get(cv2.CAP_PROP_FRAME_HEIGHT))

                        margin_x = int(w * 0.1)  # 10% de margem
                        margin_y = int(h * 0.1)

                        default_polygon = np.array([
                            [margin_x, margin_y],
                            [w - margin_x, margin_y],
                            [w - margin_x, h - margin_y],
                            [margin_x, h - margin_y]
                        ], dtype=np.int32)

                        log.info("aquarium_detector.default_polygon_created",
                                bbox=[margin_x, margin_y, w - margin_x, h - margin_y])
                        return [default_polygon]
                except Exception as e:
                    log.error("aquarium_detector.default_polygon_failed", error=str(e))

                return []

            if len(good_polygons) == 1:
                log.info("aquarium_detector.detect.only_one_good_polygon")
                return [good_polygons[0]]

            # Find the most stable polygon by consensus (average IoU)
            best_polygon = None
            max_avg_iou = -1.0

            for i, poly_a in enumerate(good_polygons):
                total_iou = 0.0
                for j, poly_b in enumerate(good_polygons):
                    if i == j:
                        continue
                    total_iou += self._calculate_iou(poly_a, poly_b)

                avg_iou = total_iou / (len(good_polygons) - 1)
                log.debug(
                    "aquarium_detector.detect.iou_check",
                    polygon_index=i,
                    avg_iou=avg_iou,
                )

                if avg_iou > max_avg_iou:
                    max_avg_iou = avg_iou
                    best_polygon = poly_a

            if best_polygon is not None:
                log.info(
                    "aquarium_detector.detect.finished",
                    best_polygon_iou=max_avg_iou,
                )
                return [best_polygon]
            else:
                log.warning("aquarium_detector.detect.consensus_failed")
                return []

        except Exception as e:
            log.error(
                "aquarium_detector.detect.failed", video_path=video_path, error=str(e)
            )
            return []
        finally:
            if source:
                source.release()
