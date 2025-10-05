"""
Script simplificado para criar cenarios de teste do Wizard v1.5

Execucao:
    poetry run python create_wizard_test_scenarios.py

Gera 3 cenarios em test_scenarios/:
    1. scenario_1_experimental (design detectavel)
    2. scenario_2_with_parquets (parquets existentes)
    3. scenario_3_exploratory (exploratório simples)
"""

from pathlib import Path
import cv2
import numpy as np
import pandas as pd

def create_mock_video(path: Path, duration_sec: int = 3):
    """Cria video mock de 640x480, 30fps"""
    print(f"  Criando video: {path.name}")
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(str(path), fourcc, 30, (640, 480))

    total_frames = duration_sec * 30
    for i in range(total_frames):
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        color = int((i / total_frames) * 255)
        frame[:, :] = [color, 100, 255 - color]

        # Texto identificador
        cv2.putText(frame, path.stem, (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

        # "Fish" simulado (circulo branco)
        fish_x = int(320 + 200 * np.sin(i * 0.1))
        fish_y = int(240 + 100 * np.cos(i * 0.1))
        cv2.circle(frame, (fish_x, fish_y), 15, (255, 255, 255), -1)

        out.write(frame)

    out.release()

def create_arena_parquet(video_path: Path):
    """Cria *_arena.parquet"""
    stem = video_path.stem
    res_dir = video_path.parent / f"{stem}_results"
    res_dir.mkdir(exist_ok=True)

    parquet_path = res_dir / f"{stem}_arena.parquet"
    df = pd.DataFrame({
        'arena_polygon_px': [[[50, 50], [590, 50], [590, 430], [50, 430]]],
        'arena_width_cm': [10.0],
        'arena_height_cm': [10.0]
    })
    df.to_parquet(parquet_path, index=False)
    print(f"    + {parquet_path.name}")

def create_rois_parquet(video_path: Path):
    """Cria *_rois.parquet"""
    stem = video_path.stem
    res_dir = video_path.parent / f"{stem}_results"
    res_dir.mkdir(exist_ok=True)

    parquet_path = res_dir / f"{stem}_rois.parquet"
    df = pd.DataFrame({
        'roi_name': ['Center', 'Edge'],
        'roi_polygon_px': [
            [[200, 200], [440, 200], [440, 280], [200, 280]],
            [[50, 50], [150, 50], [150, 100], [50, 100]]
        ],
        'roi_color_bgr': [[0, 255, 0], [255, 0, 0]]
    })
    df.to_parquet(parquet_path, index=False)
    print(f"    + {parquet_path.name}")

def create_trajectory_parquet(video_path: Path):
    """Cria 3_CoordMovimento_*.parquet"""
    stem = video_path.stem
    res_dir = video_path.parent / f"{stem}_results"
    res_dir.mkdir(exist_ok=True)

    parquet_path = res_dir / f"3_CoordMovimento_{stem}.parquet"
    frames = list(range(0, 300, 10))  # 30 frames
    df = pd.DataFrame({
        'timestamp': [i * 0.033 for i in frames],
        'frame': frames,
        'track_id': [1] * len(frames),
        'x1': [100 + i * 5 for i in range(len(frames))],
        'y1': [240] * len(frames),
        'x2': [130 + i * 5 for i in range(len(frames))],
        'y2': [270] * len(frames),
        'confidence': [0.95] * len(frames)
    })
    df.to_parquet(parquet_path, index=False)
    print(f"    + {parquet_path.name}")

def create_scenario_1(base_dir: Path):
    """Cenario 1: Experimental com design detectavel"""
    print("\n[CENARIO 1] Projeto Experimental")
    print("Estrutura: Control/Day01/S01.mp4, Treatment/Day02/S03.mp4, etc.")

    scenario_dir = base_dir / "scenario_1_experimental"

    for group in ['Control', 'Treatment']:
        for day in ['Day01', 'Day02']:
            day_dir = scenario_dir / group / day
            day_dir.mkdir(parents=True, exist_ok=True)

            for subj in ['S01', 'S02', 'S03']:
                video_path = day_dir / f"{subj}.mp4"
                create_mock_video(video_path)

    print(f"Criado: {scenario_dir.absolute()}")
    print("Total: 12 videos (2 grupos x 2 dias x 3 sujeitos)")
    print("Design esperado: groups_as_folders, confidence > 80%")

def create_scenario_2(base_dir: Path):
    """Cenario 2: Com parquets existentes"""
    print("\n[CENARIO 2] Projeto com Parquets para Importacao")

    scenario_dir = base_dir / "scenario_2_with_parquets"
    scenario_dir.mkdir(parents=True, exist_ok=True)

    # Video 1: Arena + ROIs + Trajectory (completo)
    print("Video 1 (arena + rois + trajectory):")
    v1 = scenario_dir / "video1.mp4"
    create_mock_video(v1, duration_sec=4)
    create_arena_parquet(v1)
    create_rois_parquet(v1)
    create_trajectory_parquet(v1)

    # Video 2: Arena + ROIs apenas
    print("\nVideo 2 (arena + rois):")
    v2 = scenario_dir / "video2.mp4"
    create_mock_video(v2, duration_sec=4)
    create_arena_parquet(v2)
    create_rois_parquet(v2)

    # Video 3: Sem parquets
    print("\nVideo 3 (sem parquets):")
    v3 = scenario_dir / "video3.mp4"
    create_mock_video(v3, duration_sec=4)

    print(f"\nCriado: {scenario_dir.absolute()}")
    print("Total: 3 videos")
    print("  video1: SKIP ou IMPORT_ZONES (tem tudo)")
    print("  video2: IMPORT_ZONES (arena + rois)")
    print("  video3: FULL (processar do zero)")

def create_scenario_3(base_dir: Path):
    """Cenario 3: Exploratorio simples"""
    print("\n[CENARIO 3] Projeto Exploratorio")

    scenario_dir = base_dir / "scenario_3_exploratory" / "Videos"
    scenario_dir.mkdir(parents=True, exist_ok=True)

    for date in ['2025_01_15', '2025_01_16', '2025_01_17']:
        video_path = scenario_dir / f"experiment_{date}.mp4"
        create_mock_video(video_path)

    print(f"Criado: {scenario_dir.parent.absolute()}")
    print("Total: 3 videos")
    print("Design esperado: Nenhum (exploratorio)")

def create_readme(base_dir: Path):
    """Cria README com instrucoes"""
    content = """# Cenarios de Teste do Wizard v1.5

## Estrutura

### Cenario 1: Experimental (Design Detectavel)
**Caminho**: `scenario_1_experimental/`
**Estrutura**:
```
Control/Day01/S01.mp4, S02.mp4, S03.mp4
Control/Day02/S01.mp4, S02.mp4, S03.mp4
Treatment/Day01/S01.mp4, S02.mp4, S03.mp4
Treatment/Day02/S01.mp4, S02.mp4, S03.mp4
```

**Como testar**:
1. No wizard, selecione "Experimental"
2. Clique "Add Folder" e escolha `scenario_1_experimental/`
3. Na etapa Detection, verifique:
   - Pattern: "groups_as_folders"
   - Groups: ["Control", "Treatment"]
   - Days: ["Day01", "Day02"]
   - Subjects: 3 por grupo
   - Confidence: > 80%

---

### Cenario 2: Com Parquets Existentes
**Caminho**: `scenario_2_with_parquets/`
**Parquets**:
- video1: arena + rois + trajectory (completo)
- video2: arena + rois
- video3: nenhum parquet

**Como testar**:
1. Selecione "Experimental" ou "Exploratory"
2. Clique "Add Files" e escolha os 3 videos
3. Na etapa Detection, verifique:
   - "Found 2 arena parquets"
   - "Found 2 rois parquets"
   - "Found 1 trajectory parquets"
4. Na etapa Import Configuration:
   - video1: Opcoes SKIP / IMPORT_ZONES / FULL
   - video2: Opcoes IMPORT_ZONES / FULL
   - video3: Apenas FULL

---

### Cenario 3: Exploratorio
**Caminho**: `scenario_3_exploratory/Videos/`
**Videos**: 3 arquivos com datas nos nomes

**Como testar**:
1. Selecione "Exploratory"
2. Clique "Add Folder" e escolha `scenario_3_exploratory/Videos/`
3. Na etapa Detection:
   - Nenhum design detectado (ou confidence baixa)

---

## Ativacao do Wizard

Certifique-se que `config.local.yaml` existe na raiz do projeto com:

```yaml
ui_features:
  use_wizard_for_project_creation: true
```

## Executar ZebTrack

```powershell
poetry run zebtrack
```

Clique em "New Project" e veja o wizard de 5 etapas!

---

**Gerado por**: create_wizard_test_scenarios.py
**Versao**: Wizard v1.5
"""

    readme_path = base_dir / "README.md"
    readme_path.write_text(content, encoding='utf-8')
    print(f"\nREADME criado: {readme_path}")

def main():
    """Funcao principal"""
    print("=" * 60)
    print("GERADOR DE CENARIOS DE TESTE - Wizard v1.5")
    print("=" * 60)

    base_dir = Path(__file__).parent / "test_scenarios"

    # Limpar cenarios anteriores
    if base_dir.exists():
        import shutil
        print(f"\nRemovendo cenarios anteriores: {base_dir}")
        shutil.rmtree(base_dir)

    base_dir.mkdir(parents=True, exist_ok=True)

    # Criar os 3 cenarios
    create_scenario_1(base_dir)
    create_scenario_2(base_dir)
    create_scenario_3(base_dir)
    create_readme(base_dir)

    print("\n" + "=" * 60)
    print("CONCLUIDO! Todos os cenarios criados")
    print("=" * 60)
    print(f"\nLocalizacao: {base_dir.absolute()}")
    print(f"Leia: {base_dir / 'README.md'}")
    print("\nPara testar:")
    print("  1. Verifique config.local.yaml (wizard ativado)")
    print("  2. Execute: poetry run zebtrack")
    print("  3. Clique 'New Project'")
    print("=" * 60 + "\n")

if __name__ == "__main__":
    main()
