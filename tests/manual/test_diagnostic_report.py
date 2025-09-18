#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Teste do relatório de diagnóstico com suporte a máscaras de segmentação
"""

import warnings

import cv2
from ultralytics import YOLO

warnings.filterwarnings("ignore")


def mock_diagnostic_report_test():
    """Simula o diagnóstico e testa a formatação do relatório"""
    print("=" * 80)
    print("TESTE DO RELATÓRIO DE DIAGNÓSTICO COM MÁSCARAS")
    print("=" * 80)

    # Configura o modelo
    model = YOLO("best_seg.pt")
    cap = cv2.VideoCapture("CECT_8.mp4")

    if not cap.isOpened():
        print("❌ Erro ao abrir vídeo")
        return

    # Simula configuração de diagnóstico
    config = {
        "video_path": "CECT_8.mp4",
        "frames_to_analyze": 3,
        "confidence_threshold": 0.1,
        "model_to_test": "YOLO (PyTorch)",
    }

    # Coleta resultados de alguns frames
    results = {"YOLO (PyTorch)": []}

    print("🔍 Coletando dados de diagnóstico...")
    for frame_idx in range(3):
        ret, frame = cap.read()
        if not ret:
            break

        # Predição com o modelo
        preds = model.predict(frame, conf=0.1, verbose=False)
        results["YOLO (PyTorch)"].append(preds[0])

        print(
            f"Frame {frame_idx + 1}: "
            f"{len(preds[0].boxes) if preds[0].boxes else 0} detecções"
        )

    cap.release()

    # Testa a formatação do relatório
    print("\n🔄 Gerando relatório...")
    report_str = format_diagnostic_report(config, results)

    # Salva o relatório
    with open("test_diagnostic_report.txt", "w", encoding="utf-8") as f:
        f.write(report_str)

    print("✅ Relatório salvo em: test_diagnostic_report.txt")
    print("\n📊 PRÉVIA DO RELATÓRIO:")
    print("-" * 50)
    print(report_str[:1000] + "..." if len(report_str) > 1000 else report_str)


def format_diagnostic_report(config, results) -> str:
    """Reproduz a lógica do método _format_diagnostic_report atualizado"""
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
                            f", Máscara: {len(preds.masks.xy[j])} pontos"
                            if has_mask
                            else ""
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


if __name__ == "__main__":
    mock_diagnostic_report_test()
