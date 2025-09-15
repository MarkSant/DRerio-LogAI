#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Teste do plugin YOLO modificado com suporte a instance segmentation
"""

import sys
import os
import warnings
warnings.filterwarnings("ignore")

# Adiciona src ao path
if os.path.exists('src'):
    sys.path.insert(0, 'src')

import cv2
import numpy as np

def test_plugin():
    """Testa o plugin YOLO modificado"""
    from zebtrack.plugins.ultralytics_detector import UltralyticsDetectorPlugin

    print("="*80)
    print("TESTE DO PLUGIN YOLO COM INSTANCE SEGMENTATION")
    print("="*80)

    # Inicializa plugin
    print("🔄 Inicializando plugin...")
    plugin = UltralyticsDetectorPlugin("best_seg.pt")
    print(f"✅ Plugin inicializado: {plugin.get_name()}")

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

    # Teste 1: Modo tracking padrão (só zebrafish)
    print("\n" + "-"*60)
    print("TESTE 1: MODO TRACKING PADRÃO (SÓ ZEBRAFISH)")
    print("-"*60)

    plugin.set_context('tracking')
    plugin.set_aquarium_region_defined(True)  # Aquário já definido

    detections = plugin.detect(frame)
    print(f"🐠 Detecções em modo tracking: {len(detections)}")
    for i, det in enumerate(detections):
        x1, y1, x2, y2, conf, track_id = det
        print(f"  Det {i+1}: bbox=[{x1},{y1},{x2},{y2}], conf={conf:.3f}, track_id={track_id}")

    # Teste 2: Modo tracking sem aquário definido (todas as classes)
    print("\n" + "-"*60)
    print("TESTE 2: MODO TRACKING SEM AQUÁRIO (TODAS CLASSES)")
    print("-"*60)

    plugin.set_context('tracking')
    plugin.set_aquarium_region_defined(False)  # Aquário não definido

    detections = plugin.detect(frame)
    print(f"🔍 Detecções sem aquário definido: {len(detections)}")
    for i, det in enumerate(detections):
        x1, y1, x2, y2, conf, track_id = det
        print(f"  Det {i+1}: bbox=[{x1},{y1},{x2},{y2}], conf={conf:.3f}, track_id={track_id}")

    # Teste 3: Modo diagnóstico com suporte a máscaras
    print("\n" + "-"*60)
    print("TESTE 3: MODO DIAGNÓSTICO COM MÁSCARAS")
    print("-"*60)

    plugin.set_context('diagnostic')

    # Testa com diferentes thresholds
    for conf_thresh in [0.05, 0.1, 0.25]:
        print(f"\n🔍 Threshold: {conf_thresh}")
        results = plugin.predict(frame, conf_threshold=conf_thresh)
        print(f"  Resultados: {len(results)}")

        for i, result in enumerate(results):
            print(f"    {i+1}. {result['class_name']} (conf={result['confidence']:.3f})")
            print(f"       bbox={result['box']}")
            print(f"       máscara={'SIM' if result['has_mask'] else 'NÃO'}")
            if result['has_mask']:
                print(f"       pontos={result['mask_points']}")

    # Teste 4: Múltiplos frames
    print("\n" + "-"*60)
    print("TESTE 4: ANÁLISE DE MÚLTIPLOS FRAMES")
    print("-"*60)

    plugin.set_context('diagnostic')
    frame_positions = [0, 1000, 2000, 3000, 4000]

    for pos in frame_positions:
        cap.set(cv2.CAP_PROP_POS_FRAMES, pos)
        ret, test_frame = cap.read()
        if not ret:
            continue

        results = plugin.predict(test_frame, conf_threshold=0.1)
        zebrafish_count = sum(1 for r in results if r['class_name'] == 'zebrafish')
        aqua_count = sum(1 for r in results if r['class_name'] == 'aqua')

        print(f"  Frame {pos}: {zebrafish_count} zebrafish, {aqua_count} aquário")

    cap.release()

    print("\n" + "="*80)
    print("✅ TESTES CONCLUÍDOS")
    print("="*80)

if __name__ == "__main__":
    test_plugin()