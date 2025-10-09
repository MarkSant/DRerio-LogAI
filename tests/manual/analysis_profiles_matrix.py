#!/usr/bin/env python3
"""Interactive helper to audit analysis profiles before a release."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_PATH = REPO_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from zebtrack.core.project_manager import ProjectManager  # noqa: E402


def _make_sample_project(pm: ProjectManager) -> None:
    default_profile = pm._default_analysis_profile()  # type: ignore[attr-defined]
    high_sensitivity = {
        **default_profile,
        "name": "HighSensitivity",
        "freezing_velocity_threshold": 0.8,
        "sharp_turn_threshold_deg_s": 150.0,
        "roi_inclusion_rule": "centroid_in_on_buffered_roi",
    }
    tracking_light = {
        **default_profile,
        "name": "TrackingLight",
        "analysis_interval_frames": 20,
        "display_interval_frames": 20,
        "roi_inclusion_rule": "bbox_intersects",
    }
    pm.project_data = {
        "project_name": "Manual QA",
        "analysis_profiles": [default_profile, high_sensitivity, tracking_light],
    }


def verify_resolution_logic(pm: ProjectManager) -> None:
    print("➡️  Resolvendo perfis de análise...")
    metadata = {"analysis_profile": "HighSensitivity"}
    resolved = pm.resolve_analysis_profile(metadata)
    assert resolved["name"] == "HighSensitivity"

    fallback = pm.resolve_analysis_profile({"analysis_profile": "Unknown"})
    assert fallback["name"] == pm.project_data["analysis_profiles"][0]["name"]

    print("   ✅ Resolução de perfis validada")


def display_matrix(pm: ProjectManager) -> None:
    profiles = pm.get_analysis_profiles()
    print("\n📊 Perfis inscritos no projeto QA:")
    for profile in profiles:
        print(
            json.dumps(
                {
                    "name": profile["name"],
                    "analysis_interval": profile.get("analysis_interval_frames"),
                    "display_interval": profile.get("display_interval_frames"),
                    "roi_rule": profile.get("roi_inclusion_rule"),
                    "freezing_threshold": profile.get("freezing_velocity_threshold"),
                },
                ensure_ascii=False,
            )
        )


def print_manual_steps(tmp_path: Path) -> None:
    print("\n📋 Checklist manual sugerido:")
    print("  1. Abra o projeto salvo em: {}".format(tmp_path))
    print(
        "  2. Execute `Project > Preferências deste Projeto...` "
        "e confirme se os perfis aparecem na lista."
    )
    print(
        "  3. Inicie uma análise rápida e valide se o overlay informa "
        "o perfil ativo."
    )
    print(
        "  4. Ajuste a sensibilidade e salve; rode este script "
        "novamente para verificar se os dados persistem."
    )


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        pm = ProjectManager()
        pm.project_path = Path(tmp)
        _make_sample_project(pm)
        verify_resolution_logic(pm)
        display_matrix(pm)
        # Persist snapshot so the UI can be opened manually if desired
        config_path = Path(tmp) / "project_config.json"
        config_path.write_text(json.dumps(pm.project_data, indent=2), encoding="utf-8")
        print_manual_steps(Path(tmp))
        print("\n✅ Auditoria de perfis concluída.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
