#!/usr/bin/env python3
"""Round-trip checks for ROI template workflows."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_PATH = REPO_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from zebtrack.core.detector import ZoneData  # noqa: E402
from zebtrack.core.project_manager import ProjectManager  # noqa: E402


def _sample_zone() -> ZoneData:
    return ZoneData(
        polygon=[[100, 100], [540, 100], [540, 380], [100, 380]],
        roi_polygons=[
            [[150, 150], [250, 150], [250, 250], [150, 250]],
            [[300, 160], [420, 160], [420, 280], [300, 280]],
        ],
        roi_names=["Zona Centro", "Zona Direita"],
        roi_colors=[(255, 0, 0), (0, 255, 0)],
    )


def verify_roundtrip(pm: ProjectManager) -> None:
    zone = _sample_zone()
    metadata = pm.save_roi_template("Template QA", zone, persist=False)
    assert metadata["roi_count"] == len(zone.roi_polygons)

    assert pm.project_path is not None
    source_template = Path(pm.project_path) / metadata["file"]
    data = json.loads(source_template.read_text(encoding="utf-8"))
    tmp_import = Path(pm.project_path) / "import_copy.json"
    tmp_import.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    imported = pm.import_roi_template(str(tmp_import), persist=False)
    assert imported["name"] == "Template QA"

    print("   ✅ Round-trip concluído com sucesso")


def print_manual_steps(tmp_path: Path) -> None:
    print("\n📋 Checklist manual sugerido:")
    print(
        "  1. Copie o diretório '{}' para sua pasta de testes temporária.".format(
            tmp_path
        )
    )
    print(
        "  2. Abra o app e use 'Templates de ROI' > 'Importar...' para carregar "
        "'import_copy.json'."
    )
    print("  3. Aplique o template em um vídeo e confirme as cores/nome das ROIs.")
    print("  4. Exclua e reimporte para validar o fluxo de sobrescrita.")


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        pm = ProjectManager()
        pm.project_path = tmp_path
        pm.project_data = {"roi_templates": []}
        (tmp_path / "roi_templates").mkdir(exist_ok=True)

        print("➡️  Validando round-trip de templates de ROI...")
        verify_roundtrip(pm)
        print_manual_steps(tmp_path)
        print("\n✅ Fluxo de templates de ROI validado.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
