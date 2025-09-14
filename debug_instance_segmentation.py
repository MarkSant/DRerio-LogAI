import os
import sys

# Add src path for ZebTrack modules
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'src'))

import cv2
from ultralytics import YOLO


def debug_model(model_path, video_path):
    """Debug completo para modelo de instance segmentation"""
    print("="*60)
    print("DIAGNÓSTICO DE INSTANCE SEGMENTATION")
    print("="*60)

    # Valida se os arquivos existem
    if not os.path.exists(model_path):
        print(f"ERRO: Modelo não encontrado: {model_path}")
        return False

    if not os.path.exists(video_path):
        print(f"ERRO: Vídeo não encontrado: {video_path}")
        return False

    try:
        model = YOLO(model_path)
        print(f"Modelo carregado: {model_path}")
        print(f"Tarefa do modelo: {model.task}")

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            print(f"ERRO: Não foi possível abrir o vídeo: {video_path}")
            return False

        # Info do vídeo
        fps = cap.get(cv2.CAP_PROP_FPS)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

        print(f"Vídeo: {video_path}")
        video_info = (
            f"Dimensões: {width}x{height}, "
            f"FPS: {fps:.2f}, Total frames: {total_frames}"
        )
        print(video_info)
    except Exception as e:
        print(f"ERRO ao inicializar: {e}")
        return False

    # Analisa 5 frames
    for frame_idx in range(5):
        ret, frame = cap.read()
        if not ret:
            break

        print(f"\n--- FRAME {frame_idx + 1} ---")

        # Testa com diferentes thresholds
        for conf_thresh in [0.1, 0.25, 0.5]:
            print(f"\nConf threshold: {conf_thresh}")

            # Teste 1: Sem filtro de classes
            results = model.predict(frame, conf=conf_thresh, verbose=False)
            result = results[0]

            print(f"  Tipo de tarefa: {model.task}")
            print(f"  Classes disponíveis: {result.names}")

            # Análise de boxes
            if result.boxes is not None:
                print(f"  BOXES detectados: {len(result.boxes)}")
                for i, box in enumerate(result.boxes):
                    cls = int(box.cls)
                    conf = float(box.conf)
                    x1, y1, x2, y2 = box.xyxy[0].tolist()
                    box_info = (
                        f"    Box {i}: classe={cls}({result.names[cls]}), "
                        f"conf={conf:.3f}, "
                        f"bbox=[{int(x1)},{int(y1)},{int(x2)},{int(y2)}]"
                    )
                    print(box_info)
            else:
                print("  Nenhum BOX detectado")

            # Análise de máscaras
            if result.masks is not None and result.masks.xy is not None:
                print(f"  MÁSCARAS detectadas: {len(result.masks.xy)}")
                for i, mask in enumerate(result.masks.xy):
                    # Tenta obter classe da máscara
                    if result.boxes is not None and i < len(result.boxes):
                        cls = int(result.boxes[i].cls)
                        cls_name = result.names[cls]
                    else:
                        cls = -1
                        cls_name = "SEM_BOX"

                    # Calcula bbox da máscara
                    x_min, y_min = mask[:, 0].min(), mask[:, 1].min()
                    x_max, y_max = mask[:, 0].max(), mask[:, 1].max()
                    area = (x_max - x_min) * (y_max - y_min)

                    mask_info = (
                        f"    Máscara {i}: classe={cls}({cls_name}), "
                        f"pontos={len(mask)}, área={int(area)}, "
                        f"bbox=[{int(x_min)},{int(y_min)},{int(x_max)},{int(y_max)}]"
                    )
                    print(mask_info)
            else:
                print("  Nenhuma MÁSCARA detectada")

            # Teste 2: Com filtro específico para classe 0 (aquário)
            print("\n  Teste com classes=[0] (só aquário):")
            results_aqua = model.predict(
                frame, conf=conf_thresh, verbose=False, classes=[0]
            )
            if results_aqua[0].masks is not None:
                print(f"    Máscaras de aquário: {len(results_aqua[0].masks.xy)}")
            else:
                print("    Nenhuma máscara de aquário")

    cap.release()
    print("\n" + "="*60)
    print("FIM DO DIAGNÓSTICO")
    print("="*60)
    return True

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Uso: python debug_instance_segmentation.py <modelo.pt> <video.mp4>")
        print(
            "Exemplo: python debug_instance_segmentation.py "
            "best_seg.pt meu_video.mp4"
        )
        sys.exit(1)

    success = debug_model(sys.argv[1], sys.argv[2])
    if not success:
        sys.exit(1)
