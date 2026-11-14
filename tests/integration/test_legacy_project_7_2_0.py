"""A frozen 7.2.0 project opens in 8.0 without manual migration (ADR-012/013).

The fixture under ``tests/fixtures/legacy/project_7_2_0/`` is copied to a
temporary folder (loading migrates and re-saves) and opened through the REAL
load path: ``ProjectManager.load_project`` -> ``apply_project_migrations``.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from zebtrack.core.detection.class_aliases import ClassAliases
from zebtrack.core.detection.class_roles import ClassRoleSource, resolve_class_role_map
from zebtrack.core.project.project_manager import ProjectManager
from zebtrack.core.services.weight_manager import WeightManager
from zebtrack.core.services.worker_model_resolution import (
    resolve_project_animal_method,
    resolve_worker_model,
)
from zebtrack.settings import load_settings

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "legacy" / "project_7_2_0"
ZEBRAFISH_NAMES = {0: "aqua", 1: "zebrafish"}


@pytest.fixture
def legacy_project(tmp_path: Path) -> tuple[ProjectManager, Path]:
    project_dir = tmp_path / "Zebrafish_CBD_2026"
    shutil.copytree(FIXTURE, project_dir)
    settings = load_settings()
    settings.model_selection.animal_method = "seg"  # the GLOBAL disagrees on purpose
    manager = ProjectManager(settings_obj=settings)
    manager.load_project(project_dir)
    return manager, project_dir


@pytest.fixture
def legacy_registry(tmp_path: Path) -> WeightManager:
    config_dir = tmp_path / "app"
    weights_dir = config_dir / "weights"
    weights_dir.mkdir(parents=True)
    shutil.copy(FIXTURE / "weights_config.json", config_dir / "weights_config.json")
    for name in json.loads((FIXTURE / "weights_config.json").read_text(encoding="utf-8")):
        (weights_dir / name).write_bytes(f"7.2 weight {name}".encode())
    settings = load_settings()
    settings.behavioral_analysis.aquarium_perspective = "lateral"  # type: ignore[assignment]
    return WeightManager(settings_obj=settings, config_dir=config_dir, weights_dir=weights_dir)


def test_fixture_is_a_genuine_7_2_project():
    raw = json.loads((FIXTURE / "project_config.json").read_text(encoding="utf-8"))
    assert "_integrity_hash" in raw
    assert "analysis_window" not in raw
    assert "model_selection" not in raw
    assert "class_roles" not in raw["model_overrides"]
    assert raw["_wizard_metadata"]["wizard_schema_version"] == 3


def test_opens_through_the_real_load_path_with_additive_migrations(legacy_project):
    manager, project_dir = legacy_project
    data = manager.project_data

    assert data["analysis_window"] is None
    assert data["model_selection"] == {"aquarium_method": "seg", "animal_method": "det"}
    assert data["model_overrides"]["class_roles"] is None
    assert data["model_overrides"]["class_roles_weight_sha256"] is None
    assert data["model_overrides"]["slot_weights"] == {
        "seg:aquarium": "best_seg_lateral.pt",
        "det:zebrafish": "best_det_lateral.pt",
    }
    assert data["external_trigger_mode"] is False
    assert len(manager.get_all_videos()) == 8

    # The migration was persisted and the re-saved file loads cleanly again.
    reopened = ProjectManager(settings_obj=load_settings())
    reopened.load_project(project_dir)
    assert reopened.project_data["model_selection"]["animal_method"] == "det"


def test_external_trigger_mode_survives_the_migration(tmp_path: Path):
    from zebtrack.core.project.project_service import ProjectService

    project_dir = tmp_path / "live_like"
    shutil.copytree(FIXTURE, project_dir)
    service = ProjectService()
    data = service.load_project_config(project_dir)
    data["use_arduino"] = True
    data["external_trigger_mode"] = True
    service.save_project_config(project_dir, data)

    manager = ProjectManager(settings_obj=load_settings())
    manager.load_project(project_dir)

    assert manager.project_data["external_trigger_mode"] is True
    assert manager.project_data["use_arduino"] is True


def test_reopened_project_uses_its_own_method_not_the_global(legacy_project):
    manager, _ = legacy_project
    assert resolve_project_animal_method(manager.project_data, manager.settings) == "det"


def test_roles_resolve_by_aliases_for_the_7_2_weight(legacy_project, legacy_registry):
    manager, _ = legacy_project
    settings = load_settings()
    settings.behavioral_analysis.aquarium_perspective = "lateral"  # type: ignore[assignment]

    spec = resolve_worker_model(legacy_registry, settings, manager.project_data)

    assert spec.weight_name == "best_det_lateral.pt"
    assert spec.class_roles is None
    assert spec.model_type == "yolo"  # the 7.2 OpenVINO export is not provably this .pt
    role_map = resolve_class_role_map(
        ZEBRAFISH_NAMES,
        weight_sha256=spec.weight_sha256,
        aliases=ClassAliases.from_settings(settings),
    )
    assert role_map.source is ClassRoleSource.ALIASES
    assert role_map.to_legacy_tuple() == (0, 1)
    assert role_map.context_ids == frozenset()


def test_7_2_registry_loads_without_class_roles(legacy_registry):
    details = legacy_registry.get_weight_details("best_det_lateral.pt")
    assert details is not None
    assert "class_roles" not in details
    assert details["target"] == "aquarium"
    assert details["is_default_det_zebrafish"] is True
    assert legacy_registry.openvino_cache_is_current("best_det_lateral.pt") is False
