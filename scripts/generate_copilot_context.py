#!/usr/bin/env python3
"""
Generate optimized context maps for GitHub Copilot.

This script analyzes the codebase and generates:
1. A compact navigation map with file indices
2. Architectural patterns and entry points
3. Quick decision trees for common tasks

Usage:
    poetry run python scripts/generate_copilot_context.py
"""

import ast
import json
from pathlib import Path
from typing import Any

# Diretório base do projeto
BASE_DIR = Path(__file__).parent.parent
SRC_DIR = BASE_DIR / "src" / "zebtrack"
DOCS_DIR = BASE_DIR / "docs"
OUTPUT_FILE = BASE_DIR / ".copilot-context.yaml"


def analyze_file(file_path: Path) -> dict[str, Any]:
    """Analisa um arquivo Python e extrai informações chave."""
    try:
        with open(file_path, encoding="utf-8") as f:
            tree = ast.parse(f.read(), filename=str(file_path))

        classes = []
        functions = []
        imports = []

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                methods = [m.name for m in node.body if isinstance(m, ast.FunctionDef)]
                classes.append({"name": node.name, "methods": methods[:5]})  # Top 5
            elif isinstance(node, ast.FunctionDef) and node.col_offset == 0:
                functions.append(node.name)
            elif isinstance(node, ast.Import | ast.ImportFrom):
                if isinstance(node, ast.Import):
                    imports.extend([alias.name for alias in node.names])
                elif node.module:
                    imports.append(node.module)

        return {
            "classes": classes[:3],  # Top 3 classes
            "functions": functions[:5],  # Top 5 functions
            "imports": list(set(imports))[:10],  # Top 10 unique imports
        }
    except Exception:
        return {"classes": [], "functions": [], "imports": []}


def build_architecture_map() -> dict[str, Any]:
    """Constrói mapa arquitetural do projeto."""
    architecture = {
        "entry_points": {
            "main": "src/zebtrack/__main__.py (Composition Root, lines 140-280)",
            "gui": "src/zebtrack/ui/gui.py (MainWindow + MainViewModel)",
            "wizard": "src/zebtrack/ui/wizard/wizard_dialog.py",
        },
        "core_services": {
            "detector": "src/zebtrack/core/detector_service.py (DetectorService)",
            "project_manager": "src/zebtrack/core/project_manager.py",
            "project_workflow": "src/zebtrack/core/project_workflow_service.py",
            "state": "src/zebtrack/core/state_manager.py (thread-safe)",
            "processing": "src/zebtrack/core/processing_worker.py",
        },
        "data_pipeline": [
            "io/video_source.py → VideoReader",
            "core/detector_service.py → DetectorService (plugins/)",
            "core/processing_worker.py → ProcessingWorker",
            "io/recorder.py → Recorder (Parquet/MP4)",
        ],
        "ui_components": {
            "main_window": "ui/gui.py (MainWindow, MainViewModel)",
            "wizard": "ui/wizard/wizard_dialog.py (5 steps)",
            "controls": "ui/widgets/ (ControlPanel, AnalysisControls, etc.)",
        },
        "config": {
            "settings": "settings.py (Pydantic v2, extra='forbid')",
            "loading": "__main__.py load_settings() → constructor injection",
            "precedence": "config.yaml < config.local.yaml",
        },
    }
    return architecture


def build_decision_trees() -> dict[str, Any]:
    """Cria árvores de decisão para tarefas comuns."""
    return {
        "adding_new_feature": {
            "ui_change": [
                "1. Check ui/widgets/ for existing components",
                "2. Update MainViewModel if state needed (constructor injection)",
                "3. Use root.after(0, ...) for async updates",
                "4. Add tests in tests/test_*_integration.py",
            ],
            "processing_change": [
                "1. Check core/detector_service.py or plugins/",
                "2. Inject settings_obj via constructor",
                "3. Update core/processing_worker.py if needed",
                "4. Validate output schema in io/recorder.py",
            ],
            "config_change": [
                "1. Update settings.py Pydantic model",
                "2. Update config.yaml with new field",
                "3. Pass via constructor injection from __main__.py",
                "4. Never import singleton 'from zebtrack import settings'",
            ],
        },
        "debugging": {
            "ui_issue": [
                "1. Check logs: structlog with domain.action.result",
                "2. Verify StateManager updates",
                "3. Check root.after() scheduling",
                "4. Run: poetry run pytest -m gui -n0",
            ],
            "processing_issue": [
                "1. Check detector_service.py zone scaling",
                "2. Verify ProcessingWorker thread state",
                "3. Check Recorder schema: tests/test_recorder.py",
                "4. Run: poetry run pytest -q",
            ],
            "config_issue": [
                "1. Verify settings.py Pydantic validation",
                "2. Check config.local.yaml overrides",
                "3. Trace __main__.py load_settings()",
                "4. Search for singleton imports (forbidden)",
            ],
        },
        "testing": {
            "fast_feedback": "poetry run pytest -q (fast suite)",
            "gui_tests": "poetry run pytest -m gui -n0 (single thread)",
            "specific_file": "poetry run pytest tests/test_<name>.py -v",
            "coverage": "poetry run pytest --cov=zebtrack --cov-report=html",
            "slow_tests": "poetry run pytest -m slow",
        },
    }


def scan_key_files() -> dict[str, Any]:
    """Escaneia arquivos chave e extrai informações."""
    key_files = {
        "composition_root": SRC_DIR / "__main__.py",
        "main_viewmodel": SRC_DIR / "ui" / "gui.py",
        "settings": SRC_DIR / "settings.py",
        "detector_service": SRC_DIR / "core" / "detector_service.py",
        "project_manager": SRC_DIR / "core" / "project_manager.py",
        "state_manager": SRC_DIR / "core" / "state_manager.py",
        "recorder": SRC_DIR / "io" / "recorder.py",
    }

    file_index = {}
    for key, path in key_files.items():
        if path.exists():
            rel_path = path.relative_to(BASE_DIR)
            analysis = analyze_file(path)
            file_index[key] = {
                "path": str(rel_path),
                "classes": [c["name"] for c in analysis["classes"]],
                "key_methods": [m for c in analysis["classes"] for m in c.get("methods", [])],
            }

    return file_index


def generate_yaml_context() -> str:
    """Gera contexto em formato YAML otimizado."""
    architecture = build_architecture_map()
    _ = build_decision_trees()  # Reserved for future use
    file_index = scan_key_files()

    yaml_content = f"""# ZebTrack-AI Copilot Context Map (Auto-generated)
# Generated: {Path(__file__).name}
# Purpose: Fast navigation and decision making for GitHub Copilot

# === QUICK START ===
product: "DRerio LogAI (zebtrack package)"
runtime: "Python 3.12+, Poetry, Tkinter"
launch: "poetry run zebtrack OR poetry run python -m zebtrack"

# === ARCHITECTURE PATTERN ===
pattern: "MVVM with Dependency Injection"
composition_root: "{architecture["entry_points"]["main"]}"
settings_injection: "Constructor injection ONLY, never singleton"

# === KEY FILE INDEX ===
# Direct paths to critical files - use these to minimize searches
files:
  main_entry: "{file_index.get("composition_root", {}).get("path", "N/A")}"
  main_viewmodel: "{file_index.get("main_viewmodel", {}).get("path", "N/A")}"
  settings: "{file_index.get("settings", {}).get("path", "N/A")}"
  detector_service: "{file_index.get("detector_service", {}).get("path", "N/A")}"
  project_manager: "{file_index.get("project_manager", {}).get("path", "N/A")}"
  state_manager: "{file_index.get("state_manager", {}).get("path", "N/A")}"
  recorder: "{file_index.get("recorder", {}).get("path", "N/A")}"

# === DECISION TREES ===
# Fast decision paths for common tasks - follow these instead of searching

adding_ui_feature:
  - "1. Check ui/widgets/ for reusable components"
  - "2. Update MainViewModel with constructor injection"
  - "3. Use root.after(0, ...) for async updates"
  - "4. Add integration test in tests/test_*_integration.py"

adding_processing_feature:
  - "1. Check core/detector_service.py or plugins/"
  - "2. Add settings_obj param to constructor"
  - "3. Update processing_worker.py if needed"
  - "4. Validate schema in io/recorder.py"

adding_config_option:
  - "1. Edit settings.py Pydantic model"
  - "2. Add field to config.yaml"
  - "3. Pass from __main__.py constructor"
  - "4. NEVER use singleton import"

debugging_ui:
  - "1. Check structlog output (domain.action.result)"
  - "2. Verify StateManager.update_state() calls"
  - "3. Check root.after() scheduling"
  - "4. Run: poetry run pytest -m gui -n0"

debugging_processing:
  - "1. Verify detector_service zone scaling"
  - "2. Check ProcessingWorker thread state"
  - "3. Validate Recorder output schema"
  - "4. Run: poetry run pytest -q"

# === QUICK COMMANDS ===
# Copy-paste ready commands for common tasks
commands:
  run_app: "poetry run zebtrack"
  fast_tests: "poetry run pytest -q"
  gui_tests: "poetry run pytest -m gui -n0"
  coverage: "poetry run pytest --cov=zebtrack --cov-report=html"
  lint: "poetry run ruff check ."
  format: "poetry run ruff format ."
  precommit: "poetry run pre-commit run --all-files"

# === ANTI-PATTERNS ===
# NEVER do these - they break the architecture
forbidden:
  - "from zebtrack import settings  # Use constructor injection"
  - "Direct state mutation  # Use StateManager.update_state()"
  - "Blocking UI thread  # Use root.after() or UICoordinator"
  - "New columns in Recorder  # Schema is fixed"
  - "Skip zone rescaling  # Always call Detector.set_zones()"

# === DATA FLOW ===
# Follow this pipeline for processing changes
pipeline:
  - "VideoReader (io/video_source.py)"
  - "→ DetectorService (core/detector_service.py)"
  - "→ ProcessingWorker (core/processing_worker.py)"
  - "→ Recorder (io/recorder.py) → Parquet + MP4"

# === TESTING STRATEGY ===
testing:
  fast_feedback: "pytest -q (< 30s)"
  gui_validation: "pytest -m gui -n0 (single thread)"
  full_coverage: "pytest --cov=zebtrack"
  minimum_coverage: "70%"
  scenario_tests: "tests/test_scenarios/"

# === DOCS PRIORITY ===
# Read these docs first before making architectural changes
critical_docs:
  - "docs/ARCHITECTURE.md"
  - "docs/DEPENDENCY_INJECTION_GUIDE.md"
  - "docs/REFERENCE_GUIDE.md"
  - ".github/copilot-instructions.md"

# === FILE STATS ===
# Auto-discovered classes and entry points
discovered_classes:
{json.dumps(file_index, indent=2)}
"""
    return yaml_content


def main():
    """Gera arquivo de contexto otimizado."""
    print("🔍 Analisando codebase do ZebTrack-AI...")

    context = generate_yaml_context()

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(context)

    print(f"✅ Contexto gerado: {OUTPUT_FILE}")
    print(f"📊 Tamanho: {len(context)} chars")
    print("\n💡 Use este arquivo para navegação rápida com GitHub Copilot")


if __name__ == "__main__":
    main()
