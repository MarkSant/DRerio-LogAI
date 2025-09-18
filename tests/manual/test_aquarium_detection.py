#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Teste da detecção automática de aquário com logs detalhados
"""

import logging
import os
import sys
import warnings

import structlog

warnings.filterwarnings("ignore")

# Configura logging para ver os outputs detalhados
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

# Adiciona src ao path se existir
if os.path.exists("src"):
    sys.path.insert(0, "src")

# Configura structlog para output legível
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer(),
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)


def test_aquarium_detection():
    """Testa a detecção automática de aquário"""
    print("=" * 80)
    print("TESTE DA DETECÇÃO AUTOMÁTICA DE AQUÁRIO")
    print("=" * 80)

    try:
        from zebtrack.core.aquarium_detector import AquariumDetector

        print("🔄 Inicializando detector de aquário...")
        detector = AquariumDetector("best_seg.pt")
        print("✅ Detector inicializado com sucesso")

        print("\n🔍 Executando detecção automática...")
        print("   Analisando 10 frames iniciais do vídeo...")
        print("   Usando confidence threshold 0.25...")
        print("   Procurando por classe 0 (aquário)...")

        polygons = detector.detect_aquariums("CECT_8.mp4", stabilization_frames=10)

        print("\n📊 RESULTADO:")
        if polygons:
            print(f"✅ {len(polygons)} polígono(s) de aquário detectado(s)")
            for i, polygon in enumerate(polygons):
                print(f"   Polígono {i + 1}: {len(polygon)} pontos")
                x_min = polygon[:, 0].min()
                y_min = polygon[:, 1].min()
                x_max = polygon[:, 0].max()
                y_max = polygon[:, 1].max()
                print(f"   Bbox: [{x_min}, {y_min}, {x_max}, {y_max}]")
                area = (x_max - x_min) * (y_max - y_min)
                print(f"   Área: {area} pixels")
        else:
            print("❌ Nenhum polígono de aquário detectado")

        print("\n" + "=" * 80)
        print("TESTE CONCLUÍDO")
        print("=" * 80)

        return polygons

    except Exception as e:
        print(f"❌ ERRO: {e}")
        import traceback

        traceback.print_exc()
        return None


if __name__ == "__main__":
    test_aquarium_detection()
