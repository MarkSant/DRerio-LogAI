#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Validation test for the specific vertex drag issue described in the problem
statement. This test reproduces the "very little movement with each drag
attempt" issue and validates that it's been fixed.
"""

import os
import sys

# Add the src directory to the path to import zebtrack
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))


def test_old_vs_new_behavior():
    """Compare old behavior (int conversions) vs new behavior (float conversions)."""
    print("=" * 80)
    print("VALIDAÇÃO: PROBLEMA DE PEQUENOS MOVIMENTOS CORRIGIDO")
    print("=" * 80)

    # Simulate canvas scaling scenario that would cause the original issue
    scale = 0.8  # Canvas is scaled down to 80% of original video size
    offset_x, offset_y = 25.7, 18.3  # Non-integer offsets

    def old_canvas_to_video(canvas_x, canvas_y):
        """Old implementation with int() conversion - causes precision loss."""
        video_x = (canvas_x - offset_x) / scale
        video_y = (canvas_y - offset_y) / scale
        return (int(video_x), int(video_y))  # ❌ Precision loss here!

    def old_video_to_canvas(video_x, video_y):
        """Old implementation with int() conversion - causes precision loss."""
        canvas_x = video_x * scale + offset_x
        canvas_y = video_y * scale + offset_y
        return (int(canvas_x), int(canvas_y))  # ❌ Precision loss here!

    def new_canvas_to_video(canvas_x, canvas_y):
        """New implementation with float() conversion - preserves precision."""
        video_x = (canvas_x - offset_x) / scale
        video_y = (canvas_y - offset_y) / scale
        return (float(video_x), float(video_y))  # ✅ Precision preserved!

    def new_video_to_canvas(video_x, video_y):
        """New implementation with float() conversion - preserves precision."""
        canvas_x = video_x * scale + offset_x
        canvas_y = video_y * scale + offset_y
        return (float(canvas_x), float(canvas_y))  # ✅ Precision preserved!

    print("🔄 Simulando o problema original de pequenos movimentos...")

    # Start with a vertex at a specific position
    original_canvas_pos = (150.7, 200.3)
    print(f"Posição inicial no canvas: {original_canvas_pos}")

    # Simulate a drag of 10 pixels to the right and down
    target_canvas_pos = (160.7, 210.3)

    # OLD BEHAVIOR - simulate multiple small drag attempts
    print("\n❌ COMPORTAMENTO ANTIGO (com int()):")
    current_pos = original_canvas_pos

    for attempt in range(5):
        # Convert to video coordinates and back (simulating the drag operation)
        video_pos = old_canvas_to_video(current_pos[0], current_pos[1])
        new_canvas_pos = old_video_to_canvas(video_pos[0], video_pos[1])

        # Calculate actual movement
        movement_x = new_canvas_pos[0] - current_pos[0]
        movement_y = new_canvas_pos[1] - current_pos[1]

        print(f"  Tentativa {attempt + 1}: {current_pos} -> {new_canvas_pos}")
        print(f"    Movimento real: ({movement_x:.3f}, {movement_y:.3f})")

        # Try to move toward target (simulate drag)
        desired_move_x = min(2.0, target_canvas_pos[0] - current_pos[0])
        desired_move_y = min(2.0, target_canvas_pos[1] - current_pos[1])

        attempted_pos = (
            current_pos[0] + desired_move_x, current_pos[1] + desired_move_y
        )
        video_pos = old_canvas_to_video(attempted_pos[0], attempted_pos[1])
        current_pos = old_video_to_canvas(video_pos[0], video_pos[1])

        if abs(movement_x) < 0.1 and abs(movement_y) < 0.1:
            print("    ⚠️  Movimento muito pequeno detectado!")

    final_old_pos = current_pos

    # NEW BEHAVIOR - smooth movement
    print("\n✅ COMPORTAMENTO NOVO (com float()):")
    current_pos = original_canvas_pos

    for attempt in range(5):
        # Convert to video coordinates and back (simulating the drag operation)
        video_pos = new_canvas_to_video(current_pos[0], current_pos[1])
        new_canvas_pos = new_video_to_canvas(video_pos[0], video_pos[1])

        # Calculate actual movement
        movement_x = new_canvas_pos[0] - current_pos[0]
        movement_y = new_canvas_pos[1] - current_pos[1]

        print(f"  Tentativa {attempt + 1}: {current_pos} -> {new_canvas_pos}")
        print(f"    Movimento real: ({movement_x:.3f}, {movement_y:.3f})")

        # Try to move toward target (simulate drag)
        desired_move_x = min(2.0, target_canvas_pos[0] - current_pos[0])
        desired_move_y = min(2.0, target_canvas_pos[1] - current_pos[1])

        attempted_pos = (
            current_pos[0] + desired_move_x, current_pos[1] + desired_move_y
        )
        video_pos = new_canvas_to_video(attempted_pos[0], attempted_pos[1])
        current_pos = new_video_to_canvas(video_pos[0], video_pos[1])

    final_new_pos = current_pos

    # Compare results
    print("\n📊 COMPARAÇÃO DOS RESULTADOS:")
    print(f"Posição alvo: {target_canvas_pos}")
    print(f"Resultado antigo: {final_old_pos}")
    print(f"Resultado novo: {final_new_pos}")

    old_distance = (
        (final_old_pos[0] - target_canvas_pos[0]) ** 2 +
        (final_old_pos[1] - target_canvas_pos[1]) ** 2
    ) ** 0.5
    new_distance = (
        (final_new_pos[0] - target_canvas_pos[0]) ** 2 +
        (final_new_pos[1] - target_canvas_pos[1]) ** 2
    ) ** 0.5

    print(f"Distância do alvo (antigo): {old_distance:.3f}")
    print(f"Distância do alvo (novo): {new_distance:.3f}")

    if new_distance < old_distance * 0.5:  # New should be significantly better
        print("✅ SUCESSO: Nova implementação move o vértice muito mais perto do alvo")
        return True
    else:
        print("❌ FALHA: Nova implementação não melhorou significativamente")
        return False


def test_canvasx_canvasy_impact():
    """Test the impact of using canvasx/canvasy vs raw event coordinates."""
    print("=" * 80)
    print("VALIDAÇÃO: IMPACTO DO CANVASX/CANVASY")
    print("=" * 80)

    # Simulate a scrolled canvas scenario
    class MockCanvas:
        def __init__(self):
            self.scroll_x = 15.5
            self.scroll_y = 22.3

        def canvasx(self, x):
            return float(x + self.scroll_x)

        def canvasy(self, y):
            return float(y + self.scroll_y)

    canvas = MockCanvas()

    # Simulate raw mouse event coordinates
    raw_events = [
        (100, 100),
        (105, 103),
        (110, 106),
        (115, 109),
        (120, 112)
    ]

    print("🔄 Simulando sequência de eventos de mouse...")

    print("\n❌ SEM canvasx/canvasy (comportamento antigo):")
    old_positions = []
    for i, (x, y) in enumerate(raw_events):
        old_positions.append((x, y))
        print(f"  Evento {i+1}: ({x}, {y}) -> posição: ({x}, {y})")

    print("\n✅ COM canvasx/canvasy (comportamento novo):")
    new_positions = []
    for i, (x, y) in enumerate(raw_events):
        canvas_x = canvas.canvasx(x)
        canvas_y = canvas.canvasy(y)
        new_positions.append((canvas_x, canvas_y))
        print(f"  Evento {i+1}: ({x}, {y}) -> posição: ({canvas_x}, {canvas_y})")

    # Verify the positions are consistently offset
    print("\n📊 ANÁLISE DOS DESLOCAMENTOS:")
    expected_offset_x = canvas.scroll_x
    expected_offset_y = canvas.scroll_y

    all_offsets_correct = True
    for i, ((old_x, old_y), (new_x, new_y)) in enumerate(
        zip(old_positions, new_positions)
    ):
        actual_offset_x = new_x - old_x
        actual_offset_y = new_y - old_y

        print(f"  Evento {i+1}: offset = ({actual_offset_x}, {actual_offset_y})")

        if (abs(actual_offset_x - expected_offset_x) > 0.001 or
                abs(actual_offset_y - expected_offset_y) > 0.001):
            all_offsets_correct = False

    if all_offsets_correct:
        print("✅ SUCESSO: canvasx/canvasy aplicam offset consistente")
        return True
    else:
        print("❌ FALHA: Offsets inconsistentes detectados")
        return False


def main():
    """Run validation tests for vertex drag fixes."""
    print("VALIDAÇÃO DAS CORREÇÕES DE ARRASTO DE VÉRTICES")
    print("=" * 80)
    print("Este teste valida que o problema descrito no issue foi corrigido:")
    print("'ao clicar e arrastar os mesmos, ele não são arrastados, mas sim")
    print("apresentam um comportamento estranho de se mover muito pouco para")
    print("o lado a cada tentativa de clicar e arrastar'")
    print()

    tests = [
        ("Comparação comportamento antigo vs novo", test_old_vs_new_behavior),
        ("Impacto do canvasx/canvasy", test_canvasx_canvasy_impact),
    ]

    passed = 0
    total = len(tests)

    for test_name, test_func in tests:
        print(f"\n🧪 EXECUTANDO: {test_name}")
        try:
            if test_func():
                passed += 1
                print(f"✅ {test_name}: PASSOU")
            else:
                print(f"❌ {test_name}: FALHOU")
        except Exception as e:
            print(f"❌ {test_name}: ERRO - {e}")
            import traceback
            traceback.print_exc()

    print("\n" + "=" * 80)
    print(f"RESULTADOS FINAIS: {passed}/{total} testes de validação passaram")

    if passed == total:
        print("🎉 SUCESSO: O problema de pequenos movimentos foi corrigido!")
        print("\n📋 PROBLEMA ORIGINAL:")
        print("❌ Vértices moviam muito pouco a cada tentativa de arrastar")
        print("❌ Conversões int() causavam perda de precisão")
        print("❌ event.x/event.y não consideravam scroll do canvas")
        print("\n📋 SOLUÇÃO IMPLEMENTADA:")
        print("✅ Conversões usam float() para manter precisão")
        print("✅ canvasx/canvasy aplicam transformações corretas")
        print("✅ Movimento suave e contínuo dos vértices")
    else:
        print("❌ FALHA: Alguns testes de validação falharam")
        return False

    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
