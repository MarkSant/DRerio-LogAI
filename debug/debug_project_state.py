import json
import sys
from pathlib import Path


def check_project_state(project_path):
    """Verifica o estado do projeto salvo"""
    json_path = Path(project_path) / "project.json"

    if not json_path.exists():
        print(f"❌ Arquivo não encontrado: {json_path}")
        return

    with open(json_path) as f:
        data = json.load(f)

    print("\n=== ESTADO DO PROJETO ===")
    print(f"Nome: {data.get('project_name', 'N/A')}")
    print(f"Tipo: {data.get('project_type', 'N/A')}")

    zones = data.get("detection_zones", {})
    print("\n=== DETECTION ZONES ===")
    print(f"Tem detection_zones? {bool(zones)}")

    if zones:
        polygon = zones.get("polygon", [])
        print(f"Polygon principal: {len(polygon)} pontos")
        if polygon:
            print(f"  Primeiros 3 pontos: {polygon[:3]}")

        roi_polygons = zones.get("roi_polygons", [])
        print(f"ROI polygons: {len(roi_polygons)}")

        roi_names = zones.get("roi_names", [])
        print(f"ROI names: {roi_names}")

    print("\n=== ARQUIVO COMPLETO ===")
    print(json.dumps(data, indent=2)[:500])  # Primeiros 500 chars


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Uso: python debug_project_state.py <caminho_do_projeto>")
        sys.exit(1)

    check_project_state(sys.argv[1])
