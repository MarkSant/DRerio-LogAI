"""
Script de teste para identificar câmeras do sistema.

Captura frames de teste de cada câmera e mostra na tela
para você identificar qual índice corresponde a qual dispositivo físico.
"""

import sys

import cv2


def test_camera(index, timeout=2.0):
    """Testa uma câmera específica."""
    print(f"\n{'=' * 60}")
    print(f"Testando Câmera {index}")
    print(f"{'=' * 60}")

    # Usar DirectShow no Windows
    if sys.platform == "win32":
        cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)
    else:
        cap = cv2.VideoCapture(index)

    if not cap.isOpened():
        print(f"❌ Câmera {index}: Não conseguiu abrir")
        return False

    # Tentar capturar frame
    ret, frame = cap.read()

    if not ret or frame is None:
        print(f"❌ Câmera {index}: Abriu mas não captura frames (fantasma)")
        cap.release()
        return False

    # Informações da câmera
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS)

    print(f"✅ Câmera {index}: Funcional")
    print(f"   Resolução: {width}x{height}")
    print(f"   FPS: {fps}")
    print(f"   Frame shape: {frame.shape}")

    # Adicionar texto no frame
    cv2.putText(
        frame,
        f"CAMERA INDEX: {index}",
        (50, 50),
        cv2.FONT_HERSHEY_SIMPLEX,
        1.5,
        (0, 255, 0),
        3,
        cv2.LINE_AA,
    )
    cv2.putText(
        frame,
        f"Resolucao: {width}x{height}",
        (50, 100),
        cv2.FONT_HERSHEY_SIMPLEX,
        1.0,
        (0, 255, 0),
        2,
        cv2.LINE_AA,
    )

    # Mostrar frame
    window_name = f"Camera {index} - Pressione qualquer tecla para continuar"
    cv2.imshow(window_name, frame)
    print(f"\n👁️  Janela aberta mostrando preview da câmera {index}")
    print("   Pressione QUALQUER TECLA para continuar para próxima câmera")
    print("   Pressione ESC para sair do teste")

    # Esperar tecla
    key = cv2.waitKey(0)
    cv2.destroyWindow(window_name)
    cap.release()

    # Se ESC foi pressionado, retornar False para parar
    return key != 27  # 27 = ESC


def main():
    """Testa todas as câmeras de 0 a 5."""
    print("=" * 60)
    print("TESTE DE IDENTIFICAÇÃO DE CÂMERAS")
    print("=" * 60)
    print("\nEste script vai abrir cada câmera e mostrar um preview.")
    print("Anote qual índice corresponde a qual câmera física!")
    print("\nInstruções:")
    print("  - Pressione qualquer tecla para próxima câmera")
    print("  - Pressione ESC para sair")
    print("=" * 60)

    input("\nPressione ENTER para começar...")

    for i in range(6):  # Testa índices 0-5
        continue_testing = test_camera(i)
        if not continue_testing:
            print("\n⚠️  Teste cancelado pelo usuário (ESC pressionado)")
            break

    print("\n" + "=" * 60)
    print("RESUMO DO TESTE")
    print("=" * 60)
    print("\nAgora você sabe qual índice é cada câmera!")
    print("Use essas informações ao selecionar câmera no programa.")


if __name__ == "__main__":
    main()
