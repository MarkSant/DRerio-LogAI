"""No zebtrack module loads torch/ultralytics/openvino at import time (#643).

Until v8.0 importing any module of ``core.services`` or ``core.detection`` (even
pure-logic ones), ``zebtrack.utils`` or ``zebtrack.plugins.base`` pulled in the
deep-learning stack, several seconds per process: app startup, every batch
worker and every mutant of ``scripts/mutation_check.py`` paid for it.

Each import runs in a FRESH interpreter: the test process itself has long since
imported torch, so checking ``sys.modules`` here would prove nothing.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

HEAVY = ("torch", "torchvision", "ultralytics", "openvino")
SRC = Path(__file__).resolve().parents[1] / "src"

LIGHT_ENTRY_POINTS = [
    "zebtrack.core.services.external_trigger_gate",
    "zebtrack.core.services",
    "zebtrack.core.detection",
    "zebtrack.core.video.video_processing_service",
    "zebtrack.coordinators.model_diagnostics_coordinator",
    "zebtrack.plugins.base",
    "zebtrack.plugins.ultralytics_detector",
    "zebtrack.utils",
]


def _heavy_modules_loaded_by(code: str) -> list[str]:
    env = dict(os.environ)
    # This worktree's sources first: the venv's .pth points at the main repo.
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(SRC), env.get("PYTHONPATH")]))
    report = f"print(json.dumps([m for m in {HEAVY!r} if m in sys.modules]))"
    probe = f"{code}\nimport json, sys\n{report}"
    result = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True,
        env=env,
        timeout=300,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout.strip().splitlines()[-1])


@pytest.mark.parametrize("module", LIGHT_ENTRY_POINTS)
def test_importing_the_module_loads_no_deep_learning_stack(module):
    assert _heavy_modules_loaded_by(f"import {module}") == []


def test_the_registry_still_finds_the_plugins_on_first_access():
    pytest.importorskip("ultralytics")
    loaded = _heavy_modules_loaded_by(
        "import zebtrack.plugins as p\n"
        "assert 'YOLO (Ultralytics)' in p.DETECTOR_PLUGINS, p.DETECTOR_PLUGINS\n"
        "assert p.ULTRALYTICS_PLUGIN_AVAILABLE is True\n"
        "assert p.UltralyticsDetectorPlugin is p.DETECTOR_PLUGINS['YOLO (Ultralytics)']"
    )
    # Reading the registry is what is allowed to load the stack.
    assert "openvino" in loaded or "torch" in loaded


def test_reading_yolo_resolves_the_real_class():
    ultralytics = pytest.importorskip("ultralytics")
    from zebtrack.core.services import weight_manager

    assert weight_manager.YOLO is ultralytics.YOLO
    assert weight_manager.ULTRALYTICS_AVAILABLE is True


def test_a_patched_flag_still_drives_the_behaviour(tmp_path):
    """A test that patches the module attribute keeps control of the code path."""
    from zebtrack.core.detection import aquarium_detector

    with (
        patch.object(aquarium_detector, "ULTRALYTICS_AVAILABLE", False),
        pytest.raises(ImportError, match="Ultralytics is not available"),
    ):
        aquarium_detector.AquariumDetector(tmp_path / "w.pt")


def test_unknown_attributes_still_raise_attribute_error():
    import zebtrack.plugins as plugins_pkg
    import zebtrack.utils as utils_pkg
    from zebtrack.core.services import weight_manager

    for module in (plugins_pkg, utils_pkg, weight_manager):
        with pytest.raises(AttributeError):
            module.does_not_exist  # noqa: B018
