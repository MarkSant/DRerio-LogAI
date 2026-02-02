import sys
import time
from pathlib import Path

import cv2

# Add src to path to allow imports from zebtrack
sys.path.append(str(Path(__file__).parent.parent / "src"))

try:
    from zebtrack.core.weight_manager import WeightManager
    from zebtrack.plugins.ultralytics_detector import UltralyticsDetectorPlugin
    from zebtrack.settings import load_settings
except ImportError as e:
    print(
        "Erro: Não foi possível importar os módulos do ZebTrack. "
        "Certifique-se de que está executando a partir da raiz do projeto."
    )
    print(f"Detalhe: {e}")
    sys.exit(1)


def discover_cameras(max_to_test=5):
    """Descobre câmeras disponíveis no sistema."""
    available_cameras = []
    print(f"Procurando câmeras (0-{max_to_test - 1})...")
    for i in range(max_to_test):
        cap = cv2.VideoCapture(i, cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY)
        if cap.isOpened():
            ret, _ = cap.read()
            if ret:
                available_cameras.append(i)
                print(f"  [+] Câmera {i} encontrada.")
            cap.release()
    return available_cameras


def run_test():
    print("=== ZebTrack-AI: Teste de Detecção Não Filtrada ===")

    # 1. Carregar configurações e pesos
    try:
        settings = load_settings()
        weight_manager = WeightManager(settings_obj=settings)

        # Obter caminhos dos modelos
        seg_model_path = weight_manager.get_weight_path_by_method("seg", "animal")
        det_model_path = weight_manager.get_weight_path_by_method("det", "animal")

        print("Modelos carregados:")
        print(f"  - Segmentação: {seg_model_path}")
        print(f"  - Detecção: {det_model_path}")

        # Inicializar plugins (usaremos segmentação para mostrar tudo)
        if seg_model_path is None:
            raise RuntimeError("Modelo de segmentação não encontrado")
        plugin = UltralyticsDetectorPlugin(model_path=seg_model_path, settings_obj=settings)

        # Reduzir threshold para ver TUDO mesmo
        plugin.conf_threshold = 0.1

        print("\nModelos carregados com sucesso.")
        print(f"Classes que este modelo consegue detectar: {plugin.class_names}")
        print(
            "GARANTIA: O script está configurado para mostrar TODAS as classes "
            "acima sem nenhum filtro."
        )
    except Exception as e:
        print(f"Erro ao inicializar modelos: {e}")
        return

    # 2. Descobrir câmeras
    cams = discover_cameras()
    if not cams:
        print("Erro: Nenhuma câmera encontrada.")
        return

    print(f"Câmeras detectadas: {cams}")

    # 3. Loop principal para cada câmera
    for cam_idx in cams:
        print("\n" + "=" * 40)
        print(f"Iniciando teste na Câmera {cam_idx}...")
        print("=" * 40)
        cap = cv2.VideoCapture(cam_idx, cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY)

        if not cap.isOpened():
            print(f"Erro ao abrir câmera {cam_idx}")
            continue

        # Warmup
        print(f"Aguardando warmup da Câmera {cam_idx} (30 frames)...")
        for _ in range(30):
            cap.read()
            time.sleep(0.01)

        print(f"Câmera {cam_idx} PRONTA.")
        print("CONTROLES:")
        print("  - Q: Sair do script")
        print("  - N: Próxima câmera")

        try:
            while True:
                ret, frame = cap.read()
                if not ret:
                    print(f"Falha ao ler frame da Câmera {cam_idx}")
                    break

                # Rodar predição sem NENHUM filtro de zona/ROI
                results = plugin.predict(frame)

                # Desenhar resultados no frame manualmente (sem filtros)
                display_frame = frame.copy()
                for res in results:
                    box = res["box"]
                    conf = res["confidence"]
                    cls_name = res["class_name"]

                    cv2.rectangle(display_frame, (box[0], box[1]), (box[2], box[3]), (0, 255, 0), 2)
                    label = f"{cls_name} {conf:.2f}"
                    cv2.putText(
                        display_frame,
                        label,
                        (box[0], box[1] - 10),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.5,
                        (0, 255, 0),
                        2,
                    )

                cv2.imshow("ZebTrack Test - Raw Detection", display_frame)

                key = cv2.waitKey(1) & 0xFF
                # Aceitar tanto minúsculo quanto maiúsculo
                if key == ord("q") or key == ord("Q"):
                    print("Encerrando script...")
                    cap.release()
                    cv2.destroyAllWindows()
                    return
                elif key == ord("n") or key == ord("N"):
                    print("Pulando para próxima câmera...")
                    break

        finally:
            cap.release()
            cv2.destroyAllWindows()
            # Pequena pausa para garantir que o Windows processe o fechamento da janela
            cv2.waitKey(100)

    print("\nTodos os testes de câmera concluídos.")


if __name__ == "__main__":
    run_test()
