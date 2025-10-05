#!/usr/bin/env python3
"""
Script para criar cenrios de teste do Wizard v1.5

Gera estruturas de pastas com vdeos mock e parquets para testar:
1. Projeto experimental com design detectvel
2. Projeto com parquets para importao
3. Projeto exploratrio simples

Uso:
    poetry run python scripts/create_test_scenarios.py

Sada:
    test_scenarios/
     scenario_1_experimental/  (design experimental)
     scenario_2_with_parquets/ (parquets existentes)
     scenario_3_exploratory/   (exploratrio simples)
"""

import shutil
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq


def create_mock_video(output_path: Path, duration_seconds: float = 5, fps: int = 30):
    """
    Cria um vdeo mock com frames coloridos e texto.

    Args:
        output_path: Caminho para salvar o vdeo (.mp4)
        duration_seconds: Durao do vdeo em segundos
        fps: Frames por segundo
    """
    width, height = 640, 480
    total_frames = int(duration_seconds * fps)

    # Codec H264
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(str(output_path), fourcc, fps, (width, height))

    for frame_num in range(total_frames):
        # Frame com gradiente de cor
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        color_shift = int((frame_num / total_frames) * 255)
        frame[:, :] = [color_shift, 100, 255 - color_shift]

        # Adicionar texto identificador
        text = f"{output_path.stem} - Frame {frame_num}"
        cv2.putText(frame, text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX,
                    0.7, (255, 255, 255), 2)

        # Desenhar "fish" simulado (crculo branco se movendo)
        fish_x = int(width * (0.2 + 0.6 * (frame_num / total_frames)))
        fish_y = height // 2
        cv2.circle(frame, (fish_x, fish_y), 15, (255, 255, 255), -1)

        out.write(frame)

    out.release()
    print(f"  Video criado: {output_path.name} ({total_frames} frames)")


def create_mock_parquet(video_path: Path, parquet_type: str = "trajectory"):
    """
    Cria um arquivo Parquet mock prximo ao vdeo.

    Args:
        video_path: Caminho do vdeo de referncia
        parquet_type: "arena", "rois", ou "trajectory"
    """
    video_stem = video_path.stem
    results_dir = video_path.parent / f"{video_stem}_results"
    results_dir.mkdir(exist_ok=True)

    if parquet_type == "arena":
        # Mock de arena (polgono retangular)
        parquet_path = results_dir / f"{video_stem}_arena.parquet"
        data = {
            "arena_polygon_px": [[[50, 50], [590, 50], [590, 430], [50, 430]]],
            "arena_width_cm": [10.0],
            "arena_height_cm": [10.0],
        }
        df = pd.DataFrame(data)

    elif parquet_type == "rois":
        # Mock de ROIs (2 ROIs: Center e Edge)
        parquet_path = results_dir / f"{video_stem}_rois.parquet"
        data = {
            "roi_name": ["Center", "Edge"],
            "roi_polygon_px": [
                [[200, 200], [440, 200], [440, 280], [200, 280]],  # Center
                [[50, 50], [150, 50], [150, 100], [50, 100]]       # Edge
            ],
            "roi_color_bgr": [[0, 255, 0], [255, 0, 0]],
        }
        df = pd.DataFrame(data)

    else:  # trajectory
        # Mock de trajetria (30 frames, 1 animal)
        parquet_path = results_dir / f"3_CoordMovimento_{video_stem}.parquet"
        frames = list(range(0, 300, 10))  # 30 frames
        data = {
            "timestamp": [i * 0.033 for i in frames],
            "frame": frames,
            "track_id": [1] * len(frames),
            "x1": [100 + i * 5 for i in range(len(frames))],
            "y1": [240] * len(frames),
            "x2": [130 + i * 5 for i in range(len(frames))],
            "y2": [270] * len(frames),
            "confidence": [0.95] * len(frames),
        }
        df = pd.DataFrame(data)

    df.to_parquet(parquet_path, index=False)
    print(f"  Parquet criado: {parquet_path.name}")


def create_scenario_1_experimental(base_dir: Path):
    """
    Cenrio 1: Projeto Experimental com Design Detectvel

    Estrutura:
        Control/
            Day01/S01.mp4, S02.mp4, S03.mp4
            Day02/S01.mp4, S02.mp4, S03.mp4
        Treatment/
            Day01/S01.mp4, S02.mp4, S03.mp4
            Day02/S01.mp4, S02.mp4, S03.mp4

    O wizard deve detectar:
    - 2 grupos (Control, Treatment)
    - 2 dias (Day01, Day02)
    - 3 sujeitos por grupo
    """
    print("\nCENARIO 1: Projeto Experimental (Design Detectavel)")
    print("=" * 60)

    scenario_dir = base_dir / "scenario_1_experimental"
    scenario_dir.mkdir(parents=True, exist_ok=True)

    groups = ["Control", "Treatment"]
    days = ["Day01", "Day02"]
    subjects = ["S01", "S02", "S03"]

    for group in groups:
        for day in days:
            day_dir = scenario_dir / group / day
            day_dir.mkdir(parents=True, exist_ok=True)

            for subject in subjects:
                video_name = f"{subject}.mp4"
                video_path = day_dir / video_name
                create_mock_video(video_path, duration_seconds=3, fps=30)

    print(f"\nCenario 1 criado em: {scenario_dir}")
    print(f"   Total de videos: 12 (2 grupos x 2 dias x 3 sujeitos)")
    print(f"   Padrao esperado: groups_as_folders")


def create_scenario_2_with_parquets(base_dir: Path):
    """
    Cenrio 2: Projeto com Parquets Existentes para Importao

    Estrutura:
        video1.mp4 + video1_results/
             video1_arena.parquet
             video1_rois.parquet
             3_CoordMovimento_video1.parquet
        video2.mp4 + video2_results/
             video2_arena.parquet
             video2_rois.parquet
        video3.mp4 (sem parquets)

    O wizard deve detectar:
    - video1: arena + rois + trajectory  opo "Full" ou "Import Zones"
    - video2: arena + rois  opo "Import Zones"
    - video3: nenhum parquet  opo "Skip" ou processar normalmente
    """
    print("\n CENRIO 2: Projeto com Parquets para Importao")
    print("=" * 60)

    scenario_dir = base_dir / "scenario_2_with_parquets"
    scenario_dir.mkdir(parents=True, exist_ok=True)

    # Video 1: Com arena, ROIs e trajetria
    print("\n Video 1 (arena + rois + trajectory):")
    video1 = scenario_dir / "video1.mp4"
    create_mock_video(video1, duration_seconds=4)
    create_mock_parquet(video1, "arena")
    create_mock_parquet(video1, "rois")
    create_mock_parquet(video1, "trajectory")

    # Video 2: Com arena e ROIs apenas
    print("\n Video 2 (arena + rois):")
    video2 = scenario_dir / "video2.mp4"
    create_mock_video(video2, duration_seconds=4)
    create_mock_parquet(video2, "arena")
    create_mock_parquet(video2, "rois")

    # Video 3: Sem parquets
    print("\n Video 3 (sem parquets):")
    video3 = scenario_dir / "video3.mp4"
    create_mock_video(video3, duration_seconds=4)

    print(f"\n Cenrio 2 criado em: {scenario_dir}")
    print(f"   Total de vdeos: 3")
    print(f"   Parquets disponveis:")
    print(f"     - video1:  arena,  rois,  trajectory")
    print(f"     - video2:  arena,  rois")
    print(f"     - video3: (nenhum)")


def create_scenario_3_exploratory(base_dir: Path):
    """
    Cenrio 3: Projeto Exploratrio Simples

    Estrutura:
        Videos/
            experiment_2025_01_15.mp4
            experiment_2025_01_16.mp4
            experiment_2025_01_17.mp4

    O wizard deve:
    - NO detectar design experimental (apenas datas)
    - Tipo de projeto: Exploratrio
    """
    print("\n CENRIO 3: Projeto Exploratrio Simples")
    print("=" * 60)

    scenario_dir = base_dir / "scenario_3_exploratory" / "Videos"
    scenario_dir.mkdir(parents=True, exist_ok=True)

    video_names = [
        "experiment_2025_01_15.mp4",
        "experiment_2025_01_16.mp4",
        "experiment_2025_01_17.mp4",
    ]

    for video_name in video_names:
        video_path = scenario_dir / video_name
        create_mock_video(video_path, duration_seconds=3)

    print(f"\n Cenrio 3 criado em: {scenario_dir.parent}")
    print(f"   Total de vdeos: 3")
    print(f"   Padro esperado: Nenhum design detectado (exploratrio)")


def create_readme(base_dir: Path):
    """Cria README com instrues de teste."""
    readme_content = """# Test Scenarios para Wizard v1.5

Este diretrio contm cenrios de teste gerados automaticamente para o wizard.

##  Estrutura

### Cenrio 1: Experimental (Design Detectvel)
**Caminho**: `scenario_1_experimental/`
**Design**:
- 2 grupos: Control, Treatment
- 2 dias: Day01, Day02
- 3 sujeitos por grupo (S01, S02, S03)

**Como testar**:
1. No wizard, selecione "Experimental"
2. Em "File Selection", clique em "Add Folder" e escolha `scenario_1_experimental/`
3. Na etapa "Detection", verifique se detectou:
   - Pattern: "groups_as_folders"
   - Groups: ["Control", "Treatment"]
   - Days: ["Day01", "Day02"]
   - Subjects: 3
   - Confidence: ~0.85+

---

### Cenrio 2: Com Parquets Existentes
**Caminho**: `scenario_2_with_parquets/`
**Parquets**:
- `video1`: arena + rois + trajectory (completo)
- `video2`: arena + rois
- `video3`: nenhum parquet

**Como testar**:
1. No wizard, selecione "Experimental" ou "Exploratory"
2. Em "File Selection", clique em "Add Files" e selecione os 3 vdeos
3. Na etapa "Detection", verifique se mostra:
   - " Found 2 arena parquets"
   - " Found 2 rois parquets"
   - " Found 1 trajectory parquets"
4. Na etapa "Import Configuration", veja as opes por vdeo:
   - video1: IMPORT_ZONES ou FULL (tem tudo)
   - video2: IMPORT_ZONES (tem arena+rois)
   - video3: SKIP ou processar normalmente

---

### Cenrio 3: Exploratrio
**Caminho**: `scenario_3_exploratory/Videos/`
**Vdeos**: 3 arquivos com datas nos nomes

**Como testar**:
1. No wizard, selecione "Exploratory"
2. Em "File Selection", clique em "Add Folder" e escolha `scenario_3_exploratory/Videos/`
3. Na etapa "Detection", verifique:
   - Nenhum design detectado (ou confiana baixa)
   - Opo de importar parquets no aparece (no h parquets)

---

##  Checklist de Testes Manuais

### Step 1: Discovery
- [ ] Selecionar "Experimental"  prossegue para File Selection
- [ ] Selecionar "Exploratory"  prossegue para File Selection
- [ ] Voltar (Back)  retorna ao Discovery

### Step 2: File Selection
- [ ] "Add Files"  dialog de seleo de arquivos
- [ ] "Add Folder"  dialog de seleo de pasta, scan recursivo funciona
- [ ] Remove vdeo da lista  vdeo removido
- [ ] Clear All  lista fica vazia
- [ ] Next sem vdeos  mensagem de erro
- [ ] Next com vdeos  prossegue para Detection

### Step 3: Detection
- [ ] Cenrio 1: Design experimental detectado corretamente
- [ ] Cenrio 2: Parquets detectados e contados corretamente
- [ ] Cenrio 3: Nenhum design detectado (ou baixa confiana)
- [ ] Progress bar aparece durante scan
- [ ] Cancel interrompe o scan

### Step 4: Import Configuration (s aparece se h parquets)
- [ ] Cenrio 2 video1: Opes "Skip", "Import Zones", "Partial", "Full"
- [ ] Cenrio 2 video2: Opes "Skip", "Import Zones"
- [ ] Cenrio 2 video3: Opes "Skip" (sem import)
- [ ] Alterar action de um vdeo  persiste ao navegar Back/Next
- [ ] ROI Merge Strategy: "Replace" vs "Merge"  tooltip explica

### Step 5: Confirmation
- [ ] Mostra resumo correto (nome, tipo, vdeos, design)
- [ ] "Create Project"  projeto criado com sucesso
- [ ] Validao: nome vazio  erro
- [ ] Validao: pasta existente  erro

---

##  Comandos

### Gerar cenrios
```powershell
poetry run python scripts/create_test_scenarios.py
```

### Executar ZebTrack com wizard ativado
1. Certifique-se que `config.local.yaml` tem:
   ```yaml
   ui_features:
     use_wizard_for_project_creation: true
   ```
2. Execute:
   ```powershell
   poetry run zebtrack
   ```

### Limpar cenrios
```powershell
Remove-Item -Recurse -Force test_scenarios
```

---

##  Arquivos Gerados

Cada vdeo mock tem:
- **Durao**: 3-5 segundos
- **Resoluo**: 640x480
- **FPS**: 30
- **Contedo**: Gradiente de cor + texto + "fish" simulado (crculo branco se movendo)

Cada parquet mock tem:
- **Arena**: Polgono retangular 640x480
- **ROIs**: 2 ROIs (Center, Edge)
- **Trajectory**: 30 frames, 1 animal, track_id=1

---

**Gerado por**: `scripts/create_test_scenarios.py`
**Verso**: Wizard v1.5
"""

    readme_path = base_dir / "README.md"
    readme_path.write_text(readme_content, encoding="utf-8")
    print(f"\n README criado: {readme_path}")


def main():
    """Funo principal - cria todos os cenrios."""
    print("\n" + "=" * 60)
    print("  GERADOR DE CENARIOS DE TESTE - Wizard v1.5")
    print("=" * 60)

    # Diretrio base (test_scenarios/ na raiz do projeto)
    base_dir = Path(__file__).parent.parent / "test_scenarios"

    # Limpar diretrio anterior se existir
    if base_dir.exists():
        print(f"\n  Removendo cenrios anteriores em: {base_dir}")
        shutil.rmtree(base_dir)

    base_dir.mkdir(parents=True, exist_ok=True)

    # Criar os 3 cenrios
    create_scenario_1_experimental(base_dir)
    create_scenario_2_with_parquets(base_dir)
    create_scenario_3_exploratory(base_dir)

    # Criar README com instrues
    create_readme(base_dir)

    print("\n" + "=" * 60)
    print("  TODOS OS CENARIOS CRIADOS COM SUCESSO!")
    print("=" * 60)
    print(f"\nLocalizacao: {base_dir.absolute()}")
    print(f"\nLeia as instrucoes em: {base_dir / 'README.md'}")
    print("\nPara testar:")
    print("   1. Certifique-se que config.local.yaml tem:")
    print("      ui_features:")
    print("        use_wizard_for_project_creation: true")
    print("   2. Execute: poetry run zebtrack")
    print("   3. Clique em 'New Project' e siga o wizard")
    print("\n" + "=" * 60 + "\n")


if __name__ == "__main__":
    main()

