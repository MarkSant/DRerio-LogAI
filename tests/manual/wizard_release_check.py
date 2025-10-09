#!/usr/bin/env python3
"""Manual smoke test helper for the project creation wizard.

This script performs lightweight automated checks that every release should
execute before going through the interactive verification steps described in the
console output.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_PATH = REPO_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from zebtrack.ui.wizard.templates import TemplateManager  # noqa: E402

TEMPLATES_DIR = REPO_ROOT / "resources" / "wizard_templates"


def _bootstrap_manager(tmp_dir: Path) -> TemplateManager:
    manager = TemplateManager(templates_dir=tmp_dir / "wizard_templates")
    return manager


def verify_curated_templates() -> None:
    print("➡️  Verificando templates curados...")
    if not TEMPLATES_DIR.exists():
        raise SystemExit("Nenhum template de wizard encontrado em resources/.")

    template_files = sorted(TEMPLATES_DIR.glob("*.json"))
    if not template_files:
        raise SystemExit("Pasta de templates está vazia.")

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        manager = _bootstrap_manager(tmp_path)

        for file_path in template_files:
            template_payload = json.loads(file_path.read_text(encoding="utf-8"))
            manager.save_template(
                template_payload.get("name", file_path.stem),
                template_payload,
            )
            loaded = manager.load_template(
                template_payload.get("name", file_path.stem)
            )
            assert loaded is not None, f"Falha ao recarregar template {file_path.name}"
            assert loaded["project_type"] in {"experimental", "exploratory"}

        copied = list((tmp_path / "wizard_templates").glob("*.json"))
        print(
            f"   ✅ {len(copied)} templates validados e copiados em sandbox temporário"
        )


def print_manual_instructions() -> None:
    print("\n📋 Checklist manual sugerido:")
    print(
        "  1. Abra `poetry run zebtrack` e confirme que a aba "
        "'Config. Avançadas' mostra os valores do config atual."
    )
    print(
        "  2. Crie um projeto exploratório com o wizard usando o template "
        "'Baseline Exploratory'."
    )
    print(
        "  3. Repita para 'Baseline Experimental' verificando as ações "
        "automáticas por vídeo."
    )
    print(
        "  4. Gere um relatório rápido e confira se os títulos estão "
        "traduzidos (pt_BR)."
    )
    print(
        "  5. Finalize salvando os novos templates para confirmar permissão de "
        "escrita em ~/.zebtrack."
    )


def main() -> int:
    verify_curated_templates()
    print_manual_instructions()
    print("\n✅ Wizard release helper concluído com sucesso.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
