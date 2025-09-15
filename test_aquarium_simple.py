#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Teste simples da detecção automática de aquário
"""

import sys
import os
import warnings
warnings.filterwarnings("ignore")

import cv2
import numpy as np
from ultralytics import YOLO

def simple_aquarium_detection_test():
    """Teste manual da detecção de aquário com debug"""
    print("="*80)
    print("TESTE MANUAL DE DETECÇÃO DE AQUÁRIO")
    print("="*80)

    # Carrega modelo
    print("🔄 Carregando modelo...")
    model = YOLO("best_seg.pt")
    print("✅ Modelo carregado")

    # Carrega vídeo
    print("🔄 Carregando vídeo...")
    cap = cv2.VideoCapture("CECT_8.mp4")
    if not cap.isOpened():
        print("❌ Erro ao abrir vídeo")
        return

    frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    frame_area = frame_width * frame_height

    print(f"✅ Vídeo: {frame_width}x{frame_height} (área={frame_area})")

    good_polygons = []

    # Analisa 10 frames iniciais
    print("\n🔍 Analisando 10 frames iniciais...")
    for i in range(10):
        ret, frame = cap.read()
        if not ret:
            print(f"⚠️ Não conseguiu ler frame {i}")
            break

        # Detecção só da classe 0 (aquário) com conf 0.25
        results = model.predict(frame, verbose=False, classes=[0], conf=0.25)

        print(f"\nFrame {i+1}:")
        print(f"  Resultados: {'✅' if results else '❌'}")

        if results and results[0]:
            result = results[0]
            print(f"  Boxes: {'✅' if result.boxes is not None else '❌'}")
            print(f"  Máscaras: {'✅' if result.masks is not None else '❌'}")

            if result.boxes is not None:
                print(f"  Número de boxes: {len(result.boxes)}")

            if result.masks is not None and result.masks.xy is not None:
                polygons = result.masks.xy
                print(f"  Número de máscaras: {len(polygons)}")

                for j, poly in enumerate(polygons):
                    x_min, y_min = poly[:, 0].min(), poly[:, 1].min()
                    x_max, y_max = poly[:, 0].max(), poly[:, 1].max()
                    poly_area = (x_max - x_min) * (y_max - y_min)
                    area_ratio = poly_area / frame_area

                    # Verifica classe se tem box correspondente
                    class_id = -1
                    conf = 0.0
                    if result.boxes is not None and j < len(result.boxes):
                        class_id = int(result.boxes[j].cls)
                        conf = float(result.boxes[j].conf)

                    print(f"    Máscara {j+1}:")
                    print(f"      Classe: {class_id} ({'aqua' if class_id == 0 else 'zebrafish' if class_id == 1 else 'desconhecida'})")
                    print(f"      Confiança: {conf:.3f}")
                    print(f"      Pontos: {len(poly)}")
                    print(f"      Área: {int(poly_area)} ({area_ratio:.2%} do frame)")
                    print(f"      Bbox: [{int(x_min)}, {int(y_min)}, {int(x_max)}, {int(y_max)}]")

                    # Critério: exatamente 1 máscara, área > 30% do frame
                    if len(polygons) == 1 and area_ratio > 0.3:
                        good_polygons.append(poly.astype(np.int32))
                        print(f"      ✅ POLÍGONO ACEITO (área satisfatória)")
                    elif len(polygons) != 1:
                        print(f"      ❌ Rejeitado: {len(polygons)} máscaras (esperado: 1)")
                    else:
                        print(f"      ❌ Rejeitado: área muito pequena ({area_ratio:.2%} < 30%)")
            else:
                print("  ❌ Nenhuma máscara encontrada")
        else:
            print("  ❌ Nenhum resultado da detecção")

    cap.release()

    print(f"\n📊 RESUMO FINAL:")
    print(f"Polígonos válidos encontrados: {len(good_polygons)}")

    if good_polygons:
        print("✅ Detecção de aquário bem-sucedida!")
        for i, poly in enumerate(good_polygons):
            x_min, y_min = poly[:, 0].min(), poly[:, 1].min()
            x_max, y_max = poly[:, 0].max(), poly[:, 1].max()
            area = (x_max - x_min) * (y_max - y_min)
            print(f"  Polígono {i+1}: {len(poly)} pontos, área={area}")
    else:
        print("❌ Nenhum aquário detectado")
        print("\n🔧 POSSÍVEIS SOLUÇÕES:")
        print("• Reduzir confidence threshold (< 0.25)")
        print("• Verificar se modelo detecta classe 0 (aquário)")
        print("• Reduzir critério de área mínima (< 30%)")
        print("• Aumentar número de frames analisados")

    print("\n" + "="*80)

if __name__ == "__main__":
    simple_aquarium_detection_test()