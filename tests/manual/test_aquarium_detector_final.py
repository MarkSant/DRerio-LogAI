#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Teste final do detector de aquário corrigido
"""

import os
import sys
import warnings
from unittest.mock import MagicMock

warnings.filterwarnings("ignore")


# Mock do structlog para teste
# Injeta mock
sys.modules["structlog"] = MagicMock()

# Agora adiciona src ao path
if os.path.exists("src"):
    sys.path.insert(0, "src")


def test_final_aquarium_detector():
    """Testa o detector de aquário corrigido"""
    print("=" * 80)
    print("TESTE FINAL DO DETECTOR DE AQUÁRIO CORRIGIDO")
    print("=" * 80)

    try:
        from zebtrack.core.aquarium_detector import AquariumDetector

        print("🔄 Inicializando detector...")
        detector = AquariumDetector("best_seg.pt")
        print("✅ Detector inicializado")

        print("\n🔍 Executando detecção automática...")
        print("   - Tentará detectar classe 0 (aquário) com conf=0.01")
        print("   - Se falhar, usará estratégia fallback (maior máscara)")
        print("   - Como último recurso, criará polígono padrão")

        polygons = detector.detect_aquariums("CECT_8.mp4", stabilization_frames=5)

        print("\n📊 RESULTADO:")
        if polygons:
            print(f"✅ {len(polygons)} polígono(s) detectado(s)")
            for i, polygon in enumerate(polygons):
                x_min = polygon[:, 0].min()
                y_min = polygon[:, 1].min()
                x_max = polygon[:, 0].max()
                y_max = polygon[:, 1].max()
                area = (x_max - x_min) * (y_max - y_min)

                print(f"   Polígono {i + 1}:")
                print(f"     Pontos: {len(polygon)}")
                print(f"     Bbox: [{x_min}, {y_min}, {x_max}, {y_max}]")
                print(f"     Área: {area} pixels")

                # Estima se é padrão (retângulo perfeito)
                is_rectangle = len(polygon) == 4
                if is_rectangle:
                    expected_area = (x_max - x_min) * (y_max - y_min)
                    tipo = (
                        "Polígono padrão (80% do frame)"
                        if area == expected_area
                        else "Detectado via modelo"
                    )
                    print(f"     Tipo: {tipo}")
        else:
            print("❌ Nenhum polígono detectado (erro crítico)")

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
    test_final_aquarium_detector()
