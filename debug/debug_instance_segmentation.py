#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script completo de diagnóstico para Instance Segmentation
Desenvolvido para o projeto ZebTrack-AI - UNESP

Uso: python debug_instance_segmentation.py <modelo.pt> <video.mp4>
"""

import os
import sys
import time
import warnings

import cv2
import numpy as np
from ultralytics import YOLO

warnings.filterwarnings("ignore")

# Adiciona src ao path se existir
if os.path.exists("src"):
    sys.path.insert(0, "src")


def print_separator(title="", char="="):
    """Imprime separador visual"""
    print(char * 80)
    if title:
        print(f"{title:^80}")
        print(char * 80)


def analyze_model_info(model):
    """Analisa informações básicas do modelo"""
    print_separator("INFORMAÇÕES DO MODELO")

    print(f"Tipo de tarefa: {model.task}")
    print(f"Arquivo do modelo: {model.ckpt_path}")

    # Tenta acessar informações adicionais
    try:
        if hasattr(model, "model") and hasattr(model.model, "names"):
            names = model.model.names
            print(f"Classes do modelo: {names}")
            print(f"Número total de classes: {len(names)}")
        else:
            print("Informações de classes não disponíveis diretamente")
    except Exception as e:
        print(f"Erro ao acessar informações do modelo: {e}")

    print()


def analyze_video_info(video_path):
    """Analisa informações básicas do vídeo"""
    print_separator("INFORMAÇÕES DO VÍDEO")

    if not os.path.exists(video_path):
        print(f"ERRO: Vídeo não encontrado: {video_path}")
        return None

    cap = cv2.VideoCapture(video_path)

    if not cap.isOpened():
        print(f"ERRO: Não foi possível abrir o vídeo: {video_path}")
        return None

    # Informações do vídeo
    fps = cap.get(cv2.CAP_PROP_FPS)
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    duration = frame_count / fps if fps > 0 else 0

    print(f"Resolução: {width}x{height}")
    print(f"FPS: {fps:.2f}")
    print(f"Total de frames: {frame_count}")
    print(f"Duração: {duration:.2f} segundos")
    print(f"Codec: {cap.get(cv2.CAP_PROP_FOURCC)}")
    print()

    return cap


def test_single_frame(model, frame, frame_idx, conf_thresholds=[0.1, 0.25, 0.5]):
    """Testa um frame com diferentes configurações"""
    print_separator(f"FRAME {frame_idx + 1}", "-")

    frame_height, frame_width = frame.shape[:2]
    print(f"Dimensões do frame: {frame_width}x{frame_height}")

    for conf_thresh in conf_thresholds:
        print(f"\n🔍 TESTE - Confidence threshold: {conf_thresh}")
        print("-" * 50)

        try:
            # Predição básica
            start_time = time.time()
            results = model.predict(frame, conf=conf_thresh, verbose=False)
            inference_time = time.time() - start_time

            result = results[0]
            print(f"⏱️  Tempo de inferência: {inference_time:.3f}s")
            print(f"📋 Classes disponíveis: {result.names}")

            # Análise de detecções (boxes)
            if result.boxes is not None and len(result.boxes) > 0:
                print(f"📦 BOXES detectados: {len(result.boxes)}")

                for i, box in enumerate(result.boxes):
                    cls = int(box.cls[0])
                    conf = float(box.conf[0])
                    x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                    width_box = x2 - x1
                    height_box = y2 - y1
                    area = width_box * height_box

                    class_name = result.names.get(cls, f"classe_{cls}")
                    print(f"  📦 Box {i + 1}: {class_name} (conf={conf:.3f})")
                    print(f"      Posição: [{int(x1)}, {int(y1)}, {int(x2)}, {int(y2)}]")
                    print(f"      Tamanho: {int(width_box)}x{int(height_box)} (área={int(area)})")

            else:
                print("📦 BOXES: Nenhuma detecção")

            # Análise de máscaras
            if result.masks is not None and len(result.masks) > 0:
                print(f"🎭 MÁSCARAS detectadas: {len(result.masks)}")

                masks_data = result.masks.xy if hasattr(result.masks, "xy") else None

                if masks_data is not None:
                    for i, mask_points in enumerate(masks_data):
                        if len(mask_points) > 0:
                            # Informações da máscara
                            x_coords = mask_points[:, 0]
                            y_coords = mask_points[:, 1]
                            x_min, x_max = x_coords.min(), x_coords.max()
                            y_min, y_max = y_coords.min(), y_coords.max()
                            mask_width = x_max - x_min
                            mask_height = y_max - y_min
                            mask_area = mask_width * mask_height

                            # Tenta obter informações da classe
                            if result.boxes is not None and i < len(result.boxes):
                                cls = int(result.boxes[i].cls[0])
                                conf = float(result.boxes[i].conf[0])
                                class_name = result.names.get(cls, f"classe_{cls}")
                            else:
                                class_name = "desconhecida"
                                conf = 0.0

                            print(f"  🎭 Máscara {i + 1}: {class_name}")
                            print(f"      Pontos: {len(mask_points)}")
                            print(
                                f"      Bbox: [{int(x_min)}, {int(y_min)}, "
                                f"{int(x_max)}, {int(y_max)}]"
                            )
                            print(f"      Área estimada: {int(mask_area)}")
                            if conf > 0:
                                print(f"      Confiança: {conf:.3f}")
                else:
                    print("🎭 MÁSCARAS: Dados não disponíveis")

            else:
                print("🎭 MÁSCARAS: Nenhuma detecção")

            # Teste específico para classe aquário (classe 0)
            print("\n🐠 TESTE ESPECÍFICO - Apenas aquário (classe 0):")
            try:
                results_aquarium = model.predict(
                    frame, conf=conf_thresh, verbose=False, classes=[0]
                )
                result_aquarium = results_aquarium[0]

                if result_aquarium.masks is not None and len(result_aquarium.masks) > 0:
                    aquarium_masks = len(result_aquarium.masks)
                    print(f"    ✅ Máscaras de aquário encontradas: {aquarium_masks}")
                else:
                    print("    ❌ Nenhuma máscara de aquário detectada")

            except Exception as e:
                print(f"    ⚠️ Erro no teste de aquário: {e}")

        except Exception as e:
            print(f"❌ ERRO durante predição: {e}")
            print(f"   Tipo do erro: {type(e).__name__}")


def run_comprehensive_diagnosis(model_path, video_path):
    """Executa diagnóstico completo"""
    print_separator("DIAGNÓSTICO COMPLETO DE INSTANCE SEGMENTATION")
    print(f"Modelo: {model_path}")
    print(f"Vídeo: {video_path}")
    print()

    # Verifica se os arquivos existem
    if not os.path.exists(model_path):
        print(f"❌ ERRO: Modelo não encontrado: {model_path}")
        return

    if not os.path.exists(video_path):
        print(f"❌ ERRO: Vídeo não encontrado: {video_path}")
        return

    try:
        # Carrega o modelo
        print("🔄 Carregando modelo...")
        model = YOLO(model_path)
        analyze_model_info(model)

        # Analisa o vídeo
        print("🔄 Analisando vídeo...")
        cap = analyze_video_info(video_path)

        if cap is None:
            return

        # Testa múltiplos frames
        frames_to_test = min(5, int(cap.get(cv2.CAP_PROP_FRAME_COUNT)))
        print(f"🔍 Testando {frames_to_test} frames...")

        # Pega frames em diferentes posições do vídeo
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        frame_positions = np.linspace(0, total_frames - 1, frames_to_test, dtype=int)

        for i, frame_pos in enumerate(frame_positions):
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_pos)
            ret, frame = cap.read()

            if not ret:
                print(f"⚠️ Não foi possível ler o frame na posição {frame_pos}")
                continue

            test_single_frame(model, frame, i)
            print()

        cap.release()

        print_separator("DIAGNÓSTICO CONCLUÍDO")
        print("✅ Análise completa finalizada!")
        print()
        print("📊 RESUMO DAS RECOMENDAÇÕES:")
        print("• Se não há detecções: reduza o threshold de confiança")
        print("• Se há boxes mas não máscaras: verifique se o modelo suporta segmentação")
        print("• Se há máscaras estranhas: verifique o treinamento do modelo")
        print("• Para zebrafish: considere usar classes=[1] se classe 1 = peixe")
        print("• Para aquário: use classes=[0] se classe 0 = aquário")

    except Exception as e:
        print(f"❌ ERRO FATAL: {e}")
        print(f"Tipo do erro: {type(e).__name__}")


def main():
    """Função principal"""
    if len(sys.argv) != 3:
        print("❌ Uso incorreto!")
        print("📖 Uso correto: python debug_instance_segmentation.py <modelo.pt> <video.mp4>")
        print()
        print("Exemplos:")
        print("  python debug_instance_segmentation.py models/best.pt data/test_video.mp4")
        print("  python debug_instance_segmentation.py yolov8n-seg.pt sample.mp4")
        sys.exit(1)

    model_path = sys.argv[1]
    video_path = sys.argv[2]

    run_comprehensive_diagnosis(model_path, video_path)


if __name__ == "__main__":
    main()
