"""
Script para gerar arquivos Parquet de teste para os cenários 5 e 7.
Não requer vídeos reais - cria dados sintéticos mínimos.

Uso:
    poetry run python generate_test_parquets.py
"""

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from pathlib import Path


def create_arena_parquet(base_name: str, folder: Path, width=640, height=480):
    """Cria parquet de arena (polígono retangular)."""
    path = folder / f"1_ProcessingArea_{base_name}.parquet"
    df = pd.DataFrame({
        'x': [0, width, width, 0],
        'y': [0, 0, height, height]
    })
    pq.write_table(pa.Table.from_pandas(df), str(path))
    print(f"   ✓ Criado: {path.name}")
    return path


def create_rois_parquet(base_name: str, folder: Path, roi_names=None, width=640, height=480):
    """Cria parquet de ROIs."""
    if roi_names is None:
        roi_names = ['Top', 'Bottom']

    path = folder / f"2_AreasOfInterest_{base_name}.parquet"
    data = []

    num_rois = len(roi_names)
    roi_height = height // num_rois

    for i, roi_name in enumerate(roi_names):
        y_start = i * roi_height
        y_end = y_start + roi_height

        # Retângulo para cada ROI
        points = [
            (0, y_start),
            (width, y_start),
            (width, y_end),
            (0, y_end)
        ]

        for idx, (x, y) in enumerate(points):
            data.append({
                'roi_name': roi_name,
                'point_index': idx,
                'x': x,
                'y': y
            })

    df = pd.DataFrame(data)
    pq.write_table(pa.Table.from_pandas(df), str(path))
    print(f"   ✓ Criado: {path.name}")
    return path


def create_trajectory_parquet(base_name: str, folder: Path, num_frames=10):
    """Cria parquet de trajetória com dados sintéticos."""
    path = folder / f"3_CoordMovimento_{base_name}.parquet"

    # Trajetória simples: animal se movendo da esquerda para direita
    data = []
    for frame in range(num_frames):
        x_center = 100 + (frame * 50)  # Movimento horizontal
        y_center = 240  # Altura fixa

        data.append({
            'timestamp': frame * 0.033,  # ~30 fps
            'frame': frame,
            'track_id': 1,
            'x1': x_center - 25,
            'y1': y_center - 25,
            'x2': x_center + 25,
            'y2': y_center + 25,
            'confidence': 0.90 + (frame % 10) * 0.01
        })

    df = pd.DataFrame(data)
    pq.write_table(pa.Table.from_pandas(df), str(path))
    print(f"   ✓ Criado: {path.name}")
    return path


def create_invalid_rois_parquet(base_name: str, folder: Path):
    """Cria parquet de ROI com schema INVÁLIDO (para teste de erro)."""
    path = folder / f"2_AreasOfInterest_{base_name}.parquet"

    # Schema inválido: faltam colunas obrigatórias
    df = pd.DataFrame({
        'apenas_x': [1, 2, 3, 4, 5],
        'coluna_errada': ['a', 'b', 'c', 'd', 'e']
    })

    pq.write_table(pa.Table.from_pandas(df), str(path))
    print(f"   ⚠ Criado (INVÁLIDO): {path.name}")
    return path


def generate_scenario_5():
    """
    CENÁRIO 5: Múltiplos vídeos com estados mistos
    - video_novo.mp4 → Sem parquets
    - video_completo.mp4 → 3 parquets
    - video_so_arena.mp4 → Só arena
    - video_sem_traj.mp4 → Arena + ROIs
    """
    print("\n📁 CENÁRIO 5: Múltiplos vídeos com estados mistos")
    print("=" * 60)

    # Assumindo que o usuário já criou a pasta e os .mp4
    folder = Path("TestFolder5_Mixed")

    if not folder.exists():
        print(f"❌ Pasta {folder} não encontrada!")
        print(f"   Crie a pasta e adicione os arquivos .mp4 primeiro.")
        return False

    print(f"📂 Trabalhando em: {folder.absolute()}\n")

    # video_novo.mp4 → SEM parquets (não fazer nada)
    print("1. video_novo.mp4 → Nenhum parquet (OK)")

    # video_completo.mp4 → 3 parquets
    print("2. video_completo.mp4 → Gerando 3 parquets...")
    create_arena_parquet("video_completo", folder)
    create_rois_parquet("video_completo", folder, ['Top', 'Center', 'Bottom'])
    create_trajectory_parquet("video_completo", folder, num_frames=20)

    # video_so_arena.mp4 → Só arena
    print("3. video_so_arena.mp4 → Gerando apenas arena...")
    create_arena_parquet("video_so_arena", folder)

    # video_sem_traj.mp4 → Arena + ROIs
    print("4. video_sem_traj.mp4 → Gerando arena + ROIs...")
    create_arena_parquet("video_sem_traj", folder)
    create_rois_parquet("video_sem_traj", folder, ['Left', 'Right'])

    print("\n✅ Cenário 5 concluído!")
    return True


def generate_scenario_7():
    """
    CENÁRIO 7: Schema inválido
    - video_invalido.mp4 → Arena válida + ROI inválida
    """
    print("\n📁 CENÁRIO 7: Parquet com schema inválido")
    print("=" * 60)

    folder = Path("TestFolder7_Invalid")

    if not folder.exists():
        print(f"❌ Pasta {folder} não encontrada!")
        print(f"   Crie a pasta e adicione video_invalido.mp4 primeiro.")
        return False

    print(f"📂 Trabalhando em: {folder.absolute()}\n")

    print("1. video_invalido.mp4 → Arena VÁLIDA...")
    create_arena_parquet("video_invalido", folder)

    print("2. video_invalido.mp4 → ROI INVÁLIDA (teste de erro)...")
    create_invalid_rois_parquet("video_invalido", folder)

    print("\n✅ Cenário 7 concluído!")
    print("   ⚠ ROI tem schema inválido propositalmente para testar erro handling")
    return True


def main():
    """Gera parquets para os cenários pendentes."""
    print("🔧 GERADOR DE PARQUETS DE TESTE")
    print("=" * 60)
    print("Este script cria arquivos .parquet sintéticos para testes.")
    print("Certifique-se de ter criado as pastas e arquivos .mp4 antes!\n")

    # Tentar gerar cada cenário
    scenarios_ok = []

    if generate_scenario_5():
        scenarios_ok.append("Cenário 5")

    if generate_scenario_7():
        scenarios_ok.append("Cenário 7")

    # Sumário
    print("\n" + "=" * 60)
    print("📊 RESUMO:")
    if scenarios_ok:
        print(f"✅ Cenários gerados com sucesso: {', '.join(scenarios_ok)}")
    else:
        print("⚠ Nenhum cenário foi gerado.")
        print("   Verifique se as pastas TestFolder5_Mixed e TestFolder7_Invalid existem.")

    print("\n📋 PRÓXIMO PASSO:")
    print("   1. Abra o ZebTrack")
    print("   2. Crie um projeto novo")
    print("   3. Selecione as pastas de teste")
    print("   4. Observe os logs para validar detecção granular")
    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()
