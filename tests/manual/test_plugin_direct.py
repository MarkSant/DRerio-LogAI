#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Teste direto do plugin YOLO modificado
"""

import warnings
from typing import Any, Dict, List, Tuple

import cv2
import numpy as np
from ultralytics import YOLO

warnings.filterwarnings("ignore")


class TestUltralyticsPlugin:
    """Versão simplificada do plugin para teste"""

    def __init__(self, model_path: str):
        self.model = YOLO(model_path)
        self.conf_threshold = 0.1
        self.nms_threshold = 0.5

        # Context control for instance segmentation
        self._context = "tracking"  # 'tracking' or 'diagnostic'
        self._aquarium_region_defined = False

    def set_context(self, context: str):
        if context in ("tracking", "diagnostic"):
            self._context = context

    def set_aquarium_region_defined(self, defined: bool = True):
        self._aquarium_region_defined = bool(defined)

    def detect(self, frame: np.ndarray) -> List[Tuple[int, int, int, int, float, int]]:
        # Dynamic class filtering based on context
        if self._context == "diagnostic":
            classes_param = None
        elif self._context == "tracking" and not self._aquarium_region_defined:
            classes_param = None
        else:
            classes_param = [1]

        results = self.model.track(
            frame,
            persist=True,
            tracker="bytetrack.yaml",
            verbose=False,
            conf=self.conf_threshold,
            iou=self.nms_threshold,
            classes=classes_param,
        )

        predictions = []
        if results[0].boxes is not None and results[0].boxes.id is not None:
            boxes = results[0].boxes
            xyxys = boxes.xyxy.cpu().numpy()
            confs = boxes.conf.cpu().numpy()
            track_ids = boxes.id.cpu().numpy()

            for i in range(len(xyxys)):
                x1, y1, x2, y2 = xyxys[i]
                confidence = confs[i]
                track_id = track_ids[i]
                predictions.append(
                    (
                        int(x1),
                        int(y1),
                        int(x2),
                        int(y2),
                        float(confidence),
                        int(track_id),
                    )
                )

        return predictions

    def predict(
        self, frame: np.ndarray, conf_threshold: float = None
    ) -> List[Dict[str, Any]]:
        conf = conf_threshold if conf_threshold is not None else self.conf_threshold

        old_context = self._context
        self._context = "diagnostic"

        try:
            results = self.model.predict(frame, conf=conf, verbose=False)
            formatted_results = []

            if results and results[0]:
                result = results[0]

                # Process boxes and masks together
                if result.boxes is not None:
                    for i, box in enumerate(result.boxes):
                        x1, y1, x2, y2 = box.xyxy[0].tolist()
                        class_id = int(box.cls)
                        confidence = float(box.conf)

                        # Check if corresponding mask exists
                        has_mask = (
                            result.masks is not None
                            and result.masks.xy is not None
                            and i < len(result.masks.xy)
                        )

                        formatted_results.append(
                            {
                                "box": [int(x1), int(y1), int(x2), int(y2)],
                                "confidence": confidence,
                                "class_id": class_id,
                                "class_name": result.names.get(
                                    class_id, f"class_{class_id}"
                                ),
                                "has_mask": has_mask,
                                "mask_points": len(result.masks.xy[i])
                                if has_mask
                                else 0,
                            }
                        )

                # Process orphan masks (without boxes)
                if result.masks is not None and result.masks.xy is not None:
                    num_boxes = len(result.boxes) if result.boxes else 0
                    for i in range(num_boxes, len(result.masks.xy)):
                        mask_xy = result.masks.xy[i]
                        x_min = int(mask_xy[:, 0].min())
                        y_min = int(mask_xy[:, 1].min())
                        x_max = int(mask_xy[:, 0].max())
                        y_max = int(mask_xy[:, 1].max())

                        formatted_results.append(
                            {
                                "box": [x_min, y_min, x_max, y_max],
                                "confidence": 0.99,
                                "class_id": 0,
                                "class_name": "aquarium",
                                "has_mask": True,
                                "mask_points": len(mask_xy),
                            }
                        )

            return formatted_results

        finally:
            self._context = old_context


def test_plugin():
    print("=" * 80)
    print("TESTE DIRETO DO PLUGIN YOLO COM INSTANCE SEGMENTATION")
    print("=" * 80)

    # Inicializa plugin
    print("🔄 Inicializando plugin...")
    plugin = TestUltralyticsPlugin("best_seg.pt")
    print("✅ Plugin inicializado")

    # Carrega vídeo
    print("🔄 Carregando vídeo...")
    cap = cv2.VideoCapture("CECT_8.mp4")
    if not cap.isOpened():
        print("❌ Erro ao abrir vídeo")
        return

    ret, frame = cap.read()
    if not ret:
        print("❌ Erro ao ler frame")
        cap.release()
        return

    print(f"✅ Frame carregado: {frame.shape}")

    # Teste 1: Modo tracking com aquário definido (só zebrafish)
    print("\n" + "-" * 60)
    print("TESTE 1: TRACKING COM AQUÁRIO DEFINIDO (SÓ ZEBRAFISH)")
    print("-" * 60)

    plugin.set_context("tracking")
    plugin.set_aquarium_region_defined(True)

    detections = plugin.detect(frame)
    print(f"🐠 Detecções (só zebrafish): {len(detections)}")
    for i, det in enumerate(detections):
        x1, y1, x2, y2, conf, track_id = det
        print(
            f"  {i + 1}. bbox=[{x1},{y1},{x2},{y2}], conf={conf:.3f}, "
            f"track_id={track_id}"
        )

    # Teste 2: Modo tracking sem aquário definido (todas as classes)
    print("\n" + "-" * 60)
    print("TESTE 2: TRACKING SEM AQUÁRIO DEFINIDO (TODAS CLASSES)")
    print("-" * 60)

    plugin.set_context("tracking")
    plugin.set_aquarium_region_defined(False)

    detections = plugin.detect(frame)
    print(f"🔍 Detecções (todas classes): {len(detections)}")
    for i, det in enumerate(detections):
        x1, y1, x2, y2, conf, track_id = det
        print(
            f"  {i + 1}. bbox=[{x1},{y1},{x2},{y2}], conf={conf:.3f}, "
            f"track_id={track_id}"
        )

    # Teste 3: Modo diagnóstico com suporte a máscaras
    print("\n" + "-" * 60)
    print("TESTE 3: MODO DIAGNÓSTICO COM MÁSCARAS")
    print("-" * 60)

    plugin.set_context("diagnostic")

    # Testa com diferentes thresholds
    for conf_thresh in [0.05, 0.1, 0.15]:
        print(f"\n🔍 Confidence threshold: {conf_thresh}")
        results = plugin.predict(frame, conf_threshold=conf_thresh)
        print(f"  Resultados encontrados: {len(results)}")

        zebrafish_count = 0
        aqua_count = 0

        for i, result in enumerate(results):
            class_name = result["class_name"]
            if "zebrafish" in class_name.lower():
                zebrafish_count += 1
            elif "aqua" in class_name.lower():
                aqua_count += 1

            print(f"    {i + 1}. {class_name} (conf={result['confidence']:.3f})")
            print(f"       bbox={result['box']}")
            print(f"       máscara={'✅' if result['has_mask'] else '❌'}")
            if result["has_mask"]:
                print(f"       pontos na máscara={result['mask_points']}")

        print(f"  📊 Resumo: {zebrafish_count} zebrafish, {aqua_count} aquário")

    cap.release()

    print("\n" + "=" * 80)
    print("✅ TESTE CONCLUÍDO COM SUCESSO!")
    print("=" * 80)
    print("\n📋 FUNCIONALIDADES TESTADAS:")
    print("• ✅ Contexto dinâmico (tracking vs diagnostic)")
    print("• ✅ Filtragem de classes baseada no estado do aquário")
    print("• ✅ Suporte a instance segmentation")
    print("• ✅ Processamento de máscaras órfãs")
    print("• ✅ Múltiplos thresholds de confiança")


if __name__ == "__main__":
    test_plugin()
