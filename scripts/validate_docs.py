#!/usr/bin/env python3
"""
Validate documentation consistency with codebase.

Checks:
1. Settings fields documented in REFERENCE_GUIDE.md
2. Key classes have docstrings
3. Anti-patterns listed in copilot-instructions.md are caught
4. File index in .copilot-context.yaml is up-to-date

Usage:
    poetry run python scripts/validate_docs.py
    Exit code 0 = OK, 1 = Issues found
"""

import ast
import re
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
SRC_DIR = BASE_DIR / "src" / "zebtrack"
DOCS_DIR = BASE_DIR / "docs"


def check_settings_documentation() -> list[str]:
    """Verifica se campos de settings.py estão documentados."""
    issues: list[str] = []
    settings_file = SRC_DIR / "settings.py"
    ref_guide = DOCS_DIR / "REFERENCE_GUIDE.md"

    if not settings_file.exists() or not ref_guide.exists():
        return issues

    # Extrai classes Pydantic de settings.py
    with open(settings_file, encoding="utf-8") as f:
        tree = ast.parse(f.read())

    config_classes = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            # Verifica se herda de BaseModel
            for base in node.bases:
                if isinstance(base, ast.Name) and "Model" in base.id:
                    config_classes.append(node.name)
                    break

    # Verifica se estão no REFERENCE_GUIDE
    with open(ref_guide, encoding="utf-8") as f:
        ref_content = f.read()

    for class_name in config_classes:
        if class_name not in ref_content:
            issues.append(
                f"[WARN] Settings class '{class_name}' not documented in REFERENCE_GUIDE.md"
            )

    return issues


def check_singleton_imports() -> list[str]:
    """Detecta importações singleton proibidas."""
    issues: list[str] = []
    forbidden_pattern = re.compile(r"from\s+zebtrack\s+import\s+settings")

    for py_file in SRC_DIR.rglob("*.py"):
        # Ignora settings.py em si
        if py_file.name == "settings.py":
            continue

        with open(py_file, encoding="utf-8") as f:
            content = f.read()

        if forbidden_pattern.search(content):
            rel_path = py_file.relative_to(BASE_DIR)
            issues.append(
                f"[FAIL] Singleton import found in {rel_path} (use constructor injection)"
            )

    return issues


def check_key_docstrings() -> list[str]:
    """Verifica se classes principais têm docstrings."""
    issues: list[str] = []
    key_files = [
        SRC_DIR / "core" / "detector_service.py",
        SRC_DIR / "core" / "project_manager.py",
        SRC_DIR / "core" / "state_manager.py",
        SRC_DIR / "ui" / "gui.py",
    ]

    for file_path in key_files:
        if not file_path.exists():
            continue

        with open(file_path, encoding="utf-8") as f:
            tree = ast.parse(f.read(), filename=str(file_path))

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                if not ast.get_docstring(node):
                    rel_path = file_path.relative_to(BASE_DIR)
                    issues.append(f"[INFO] Class '{node.name}' in {rel_path} missing docstring")

    return issues


def check_context_file_freshness() -> list[str]:
    """Verifica se .copilot-context.yaml está atualizado."""
    issues: list[str] = []
    context_file = BASE_DIR / ".copilot-context.yaml"

    if not context_file.exists():
        issues.append("[WARN] .copilot-context.yaml not found - run generate_copilot_context.py")
        return issues

    # Verifica se é mais antigo que arquivos principais
    context_mtime = context_file.stat().st_mtime
    key_files = [
        SRC_DIR / "__main__.py",
        SRC_DIR / "settings.py",
        SRC_DIR / "core" / "detector_service.py",
    ]

    for key_file in key_files:
        if key_file.exists() and key_file.stat().st_mtime > context_mtime:
            issues.append(
                "[WARN] .copilot-context.yaml outdated - run: "
                "poetry run python scripts/generate_copilot_context.py"
            )
            break

    return issues


def main():
    """Executa todas as validações."""
    print("Validating documentation consistency...\n")

    all_issues = []
    all_issues.extend(check_settings_documentation())
    all_issues.extend(check_singleton_imports())
    all_issues.extend(check_key_docstrings())
    all_issues.extend(check_context_file_freshness())

    if all_issues:
        print("[FAIL] Documentation issues found:\n")
        for issue in all_issues:
            print(f"  {issue}")
        print(f"\nTotal issues: {len(all_issues)}")
        sys.exit(1)
    else:
        print("[OK] All documentation checks passed!")
        sys.exit(0)


if __name__ == "__main__":
    main()
