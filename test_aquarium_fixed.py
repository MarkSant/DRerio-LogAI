#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Teste da detecção de aquário corrigida
"""

import sys
import os
import warnings
warnings.filterwarnings("ignore")

import cv2
import numpy as np
from ultralytics import YOLO

def test_manual_aquarium_strategy():
    """Testa manualmente a estratégia de fallback da detecção de aquário"""
    print("="*80)
    print("TESTE DA ESTRATÉGIA DE FALLBACK PARA AQUÁRIO")
    print("="*80)

    model = YOLO("best_seg.pt")
    cap = cv2.VideoCapture("CECT_8.mp4")

    if not cap.isOpened():
        print("❌ Erro ao abrir vídeo")
        return

    frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    frame_area = frame_width * frame_height

    print(f"Vídeo: {frame_width}x{frame_height} (área={frame_area})")

    good_polygons = []

    # Testa alguns frames
    for i in range(5):
        ret, frame = cap.read()
        if not ret:
            break

        print(f"\nFrame {i+1}:")

        # Estratégia 1: Só aquário (classe 0)
        results_aqua = model.predict(frame, verbose=False, classes=[0], conf=0.01)
        aqua_found = False

        if results_aqua and results_aqua[0].masks and results_aqua[0].masks.xy:
            polygons = results_aqua[0].masks.xy
            print(f"  Estratégia 1 (aquário): {len(polygons)} máscaras")

            if len(polygons) == 1:
                polygon = polygons[0]
                x_min, y_min = polygon[:, 0].min(), polygon[:, 1].min()
                x_max, y_max = polygon[:, 0].max(), polygon[:, 1].max()
                poly_area = (x_max - x_min) * (y_max - y_min)
                area_ratio = poly_area / frame_area

                if area_ratio > 0.3:
                    good_polygons.append(polygon.astype(np.int32))
                    print(f"    ✅ Aquário aceito (área={area_ratio:.2%})")
                    aqua_found = True
                else:
                    print(f"    ❌ Aquário muito pequeno (área={area_ratio:.2%})")
        else:
            print("  Estratégia 1: Nenhum aquário detectado")

        # Estratégia 2: Fallback - todas as classes
        if not aqua_found:
            print("  Tentando estratégia fallback...")
            results_all = model.predict(frame, verbose=False, conf=0.01)

            if results_all and results_all[0].masks and results_all[0].masks.xy:
                all_polygons = results_all[0].masks.xy
                print(f"  Estratégia 2 (todas): {len(all_polygons)} máscaras")

                largest_area = 0
                largest_polygon = None

                for j, poly in enumerate(all_polygons):
                    x_min, y_min = poly[:, 0].min(), poly[:, 1].min()
                    x_max, y_max = poly[:, 0].max(), poly[:, 1].max()
                    area = (x_max - x_min) * (y_max - y_min)
                    area_ratio = area / frame_area

                    print(f"    Máscara {j+1}: área={int(area)} ({area_ratio:.2%})")

                    if area > largest_area:
                        largest_area = area
                        largest_polygon = poly

                if largest_polygon is not None:
                    largest_ratio = largest_area / frame_area
                    if largest_ratio > 0.1:  # Pelo menos 10%
                        good_polygons.append(largest_polygon.astype(np.int32))
                        print(f"    ✅ Maior máscara aceita (área={largest_ratio:.2%})")
                    else:
                        print(f"    ❌ Maior máscara muito pequena (área={largest_ratio:.2%})")
            else:
                print("  Estratégia 2: Nenhuma máscara encontrada")

    cap.release()

    print(f"\n📊 RESULTADO FINAL:")
    print(f"Polígonos válidos: {len(good_polygons)}")

    if good_polygons:
        print("✅ Sucesso! Aquário detectado via:")
        print("  - Detecção direta de classe aquário, ou")
        print("  - Estratégia fallback (maior máscara)")
    else:
        print("❌ Falha na detecção")
        print("🔧 Gerando polígono padrão...")

        # Estratégia 3: Polígono padrão
        margin_x = int(frame_width * 0.1)
        margin_y = int(frame_height * 0.1)

        default_polygon = np.array([
            [margin_x, margin_y],
            [frame_width - margin_x, margin_y],
            [frame_width - margin_x, frame_height - margin_y],
            [margin_x, frame_height - margin_y]
        ], dtype=np.int32)

        print(f"  Polígono padrão: bbox=[{margin_x}, {margin_y}, {frame_width - margin_x}, {frame_height - margin_y}]")
        print(f"  Área: {(frame_width - 2*margin_x) * (frame_height - 2*margin_y)} (80% do frame)")
        good_polygons = [default_polygon]

    print("\n" + "="*80)
    return good_polygons

if __name__ == "__main__":
    test_manual_aquarium_strategy()