#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Teste de diferentes thresholds para detecção de aquário
"""

import sys
import os
import warnings
warnings.filterwarnings("ignore")

import cv2
import numpy as np
from ultralytics import YOLO

def test_aquarium_thresholds():
    """Testa diferentes confidence thresholds para encontrar aquários"""
    print("="*80)
    print("TESTE DE THRESHOLDS PARA DETECÇÃO DE AQUÁRIO")
    print("="*80)

    model = YOLO("best_seg.pt")
    cap = cv2.VideoCapture("CECT_8.mp4")

    if not cap.isOpened():
        print("❌ Erro ao abrir vídeo")
        return

    # Pega um frame do meio do vídeo (pode ter melhor qualidade)
    cap.set(cv2.CAP_PROP_POS_FRAMES, 2000)
    ret, frame = cap.read()
    cap.release()

    if not ret:
        print("❌ Erro ao ler frame")
        return

    frame_area = frame.shape[0] * frame.shape[1]
    print(f"Frame: {frame.shape[1]}x{frame.shape[0]} (área={frame_area})")

    # Testa diferentes thresholds
    thresholds = [0.01, 0.05, 0.1, 0.15, 0.2, 0.25, 0.3]

    for conf_thresh in thresholds:
        print(f"\n🔍 THRESHOLD {conf_thresh}:")
        print("-" * 40)

        # Teste 1: Todas as classes
        results_all = model.predict(frame, verbose=False, conf=conf_thresh)
        print(f"  Todas classes:")
        if results_all and results_all[0]:
            result = results_all[0]
            boxes_count = len(result.boxes) if result.boxes else 0
            masks_count = len(result.masks.xy) if result.masks and result.masks.xy else 0
            print(f"    Boxes: {boxes_count}, Máscaras: {masks_count}")

            if result.boxes:
                for i, box in enumerate(result.boxes):
                    cls_id = int(box.cls)
                    cls_name = result.names.get(cls_id, 'unknown')
                    conf = float(box.conf)
                    print(f"    Box {i+1}: classe {cls_id} ({cls_name}), conf={conf:.3f}")
        else:
            print("    Nenhuma detecção")

        # Teste 2: Só classe 0 (aquário)
        results_aqua = model.predict(frame, verbose=False, conf=conf_thresh, classes=[0])
        print(f"  Só aquário (classe 0):")
        if results_aqua and results_aqua[0]:
            result = results_aqua[0]
            boxes_count = len(result.boxes) if result.boxes else 0
            masks_count = len(result.masks.xy) if result.masks and result.masks.xy else 0
            print(f"    Boxes: {boxes_count}, Máscaras: {masks_count}")

            if result.masks and result.masks.xy:
                for i, mask in enumerate(result.masks.xy):
                    x_min, y_min = mask[:, 0].min(), mask[:, 1].min()
                    x_max, y_max = mask[:, 0].max(), mask[:, 1].max()
                    area = (x_max - x_min) * (y_max - y_min)
                    area_ratio = area / frame_area
                    print(f"    Máscara {i+1}: {len(mask)} pontos, área={int(area)} ({area_ratio:.1%})")
        else:
            print("    Nenhuma detecção de aquário")

    print("\n" + "="*80)
    print("ANÁLISE CONCLUÍDA")
    print("="*80)

if __name__ == "__main__":
    test_aquarium_thresholds()