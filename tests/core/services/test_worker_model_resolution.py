"""Effective weight resolved in the main process for the worker (ADR-009).

The bug these tests pin (AUDIT §1, ``processing_worker.py:171-216``): the batch
worker rebuilt its model from the global settings, never from the project's
``model_overrides`` or the weight registry, so the rat weight chosen for a
project was silently replaced by the zebrafish default.
"""

from __future__ import annotations

import hashlib
import pickle
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from zebtrack.core.services import worker_model_resolution as module
from zebtrack.core.services.weight_manager import WeightManager
from zebtrack.core.services.worker_model_resolution import (
    WorkerModelSpec,
    resolve_project_animal_method,
    resolve_project_class_roles,
    resolve_worker_model,
)
from zebtrack.settings import load_settings

RAT_ROLES = {"arena": "arena", "experimenter": "context", "rat": "subject"}


def _settings(*, method: str = "det", use_openvino: bool = False) -> Any:
    settings = load_settings()
    settings.model_selection.animal_method = method  # type: ignore[assignment]
    settings.model_selection.use_openvino = use_openvino
    settings.behavioral_analysis.aquarium_perspective = "top_down"  # type: ignore[assignment]
    return settings


def _entry(path: Path, *, kind: str, default: bool, **extra: Any) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "path": str(path),
        "type": kind,
        "target": "aquarium" if kind == "det" else "zebrafish",
        "perspective": "top_down",
        "is_default": default,
        f"is_default_{kind}": default,
        "is_default_seg_aquarium": False,
        "is_default_seg_zebrafish": False,
        "is_default_det_aquarium": default and kind == "det",
        "is_default_det_zebrafish": False,
        "openvino_path": "",
        "openvino_hash": "",
        "openvino_status": "not_converted",
        "last_conversion_error": None,
    }
    entry.update(extra)
    return entry


@pytest.fixture
def registry(tmp_path: Path) -> tuple[WeightManager, dict[str, Path]]:
    weights = tmp_path / "weights"
    weights.mkdir()
    files = {
        "zebra": weights / "best_det_topdown.pt",
        "rat": weights / "best_det_topdown_rat_v1.pt",
        "seg": weights / "best_seg_topdown.pt",
    }
    for key, path in files.items():
        path.write_bytes(f"weight {key}".encode())
    wm = WeightManager(settings_obj=_settings(), config_dir=tmp_path, weights_dir=weights)
    wm.weights = {
        files["zebra"].name: _entry(files["zebra"], kind="det", default=True),
        files["rat"].name: _entry(files["rat"], kind="det", default=False),
        files["seg"].name: _entry(files["seg"], kind="seg", default=True),
    }
    return wm, files


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class TestWeightPrecedence:
    def test_project_slot_beats_the_registry_default(self, registry):
        wm, files = registry
        project = {"model_overrides": {"slot_weights": {"det:zebrafish": files["rat"].name}}}

        spec = resolve_worker_model(wm, _settings(), project)

        assert spec.model_path == str(files["rat"])
        assert spec.weight_name == files["rat"].name
        assert spec.weight_sha256 == _sha(files["rat"])
        assert spec.resolved_from == "project_slot"
        assert spec.model_type == "yolo"

    def test_explicit_active_weight_when_no_slot(self, registry):
        wm, files = registry
        project = {"model_overrides": {"active_weight": files["rat"].name, "slot_weights": {}}}

        spec = resolve_worker_model(wm, _settings(), project)

        assert spec.model_path == str(files["rat"])
        assert spec.resolved_from == "project_active_weight"

    def test_pre_overrides_project_uses_its_top_level_active_weight(self, registry):
        wm, files = registry

        spec = resolve_worker_model(wm, _settings(), {"active_weight": files["rat"].name})

        assert spec.model_path == str(files["rat"])

    def test_top_level_active_weight_is_ignored_once_overrides_exist(self, registry):
        wm, files = registry
        project = {"active_weight": files["rat"].name, "model_overrides": {"slot_weights": {}}}

        spec = resolve_worker_model(wm, _settings(), project)

        assert spec.model_path == str(files["zebra"])
        assert spec.resolved_from == "weight_manager"

    def test_without_project_the_registry_default_is_used(self, registry):
        wm, files = registry

        spec = resolve_worker_model(wm, _settings(), None)

        assert spec.model_path == str(files["zebra"])
        assert spec.resolved_from == "weight_manager"

    def test_unregistered_project_weight_degrades_to_the_registry(self, registry):
        wm, files = registry
        project = {"model_overrides": {"slot_weights": {"det:zebrafish": "deleted.pt"}}}

        spec = resolve_worker_model(wm, _settings(), project)

        assert spec.model_path == str(files["zebra"])

    def test_project_method_beats_the_global_method(self, registry):
        wm, files = registry
        project = {"model_selection": {"animal_method": "seg"}}

        spec = resolve_worker_model(wm, _settings(method="det"), project)

        assert spec.animal_method == "seg"
        assert spec.model_path == str(files["seg"])

    def test_slot_of_the_other_method_is_not_used(self, registry):
        wm, files = registry
        project = {"model_overrides": {"slot_weights": {"seg:zebrafish": files["rat"].name}}}

        spec = resolve_worker_model(wm, _settings(method="det"), project)

        assert spec.model_path == str(files["zebra"])

    def test_without_weight_manager_the_settings_path_is_the_last_resort(self, tmp_path: Path):
        pt = tmp_path / "legacy.pt"
        pt.write_bytes(b"legacy")
        settings = SimpleNamespace(
            model_selection=SimpleNamespace(animal_method="det", use_openvino=False),
            behavioral_analysis=SimpleNamespace(aquarium_perspective="lateral"),
            yolo_model=SimpleNamespace(path=str(pt)),
        )

        spec = resolve_worker_model(None, settings, None)

        assert spec.model_path == str(pt)
        assert spec.resolved_from == "settings"
        assert spec.weight_sha256 == _sha(pt)
        assert spec.weight_name is None


class TestAnimalMethod:
    @pytest.mark.parametrize(
        ("project", "settings_method", "expected"),
        [
            ({"model_selection": {"animal_method": "seg"}}, "det", "seg"),
            ({"model_selection": {"animal_method": "bogus"}}, "seg", "seg"),
            ({}, "seg", "seg"),
            (None, None, "det"),
        ],
    )
    def test_project_then_settings_then_det(self, project, settings_method, expected):
        settings = SimpleNamespace(model_selection=SimpleNamespace(animal_method=settings_method))
        assert resolve_project_animal_method(project, settings) == expected

    def test_mock_settings_degrade_to_det(self):
        assert resolve_project_animal_method(None, MagicMock()) == "det"


class TestOpenVINO:
    def test_current_export_is_shipped(self, registry, tmp_path: Path):
        wm, files = registry
        export = tmp_path / "ov"
        export.mkdir()
        wm.weights[files["zebra"].name]["openvino_path"] = str(export)
        wm.openvino_cache_is_current = MagicMock(return_value=True)  # type: ignore[method-assign]

        spec = resolve_worker_model(wm, _settings(use_openvino=True), None)

        assert spec.model_type == "openvino"
        assert spec.model_path == str(export)
        assert spec.openvino_path == str(export)
        assert spec.weight_sha256 == _sha(files["zebra"])

    def test_stale_export_falls_back_to_pytorch(self, registry, monkeypatch):
        wm, files = registry
        wm.openvino_cache_is_current = MagicMock(return_value=False)  # type: ignore[method-assign]
        fake_log = MagicMock()
        monkeypatch.setattr(module, "log", fake_log)

        spec = resolve_worker_model(wm, _settings(use_openvino=True), None)

        assert spec.model_type == "yolo"
        assert spec.model_path == str(files["zebra"])
        assert spec.openvino_path is None
        events = [c.args[0] for c in fake_log.warning.call_args_list]
        assert "worker_model.openvino_not_ready" in events

    def test_project_override_turns_openvino_off(self, registry):
        wm, _files = registry
        wm.openvino_cache_is_current = MagicMock(return_value=True)  # type: ignore[method-assign]
        project = {"model_overrides": {"use_openvino": False}, "use_openvino": True}

        spec = resolve_worker_model(wm, _settings(use_openvino=True), project)

        assert spec.model_type == "yolo"


class TestClassRoles:
    def test_project_roles_for_this_exact_weight_win(self, registry):
        wm, files = registry
        wm.weights[files["rat"].name]["class_roles"] = {"rat": "subject"}
        project = {
            "model_overrides": {
                "slot_weights": {"det:zebrafish": files["rat"].name},
                "class_roles": RAT_ROLES,
                "class_roles_weight_sha256": _sha(files["rat"]),
            }
        }

        spec = resolve_worker_model(wm, _settings(), project)

        assert spec.class_roles == RAT_ROLES
        assert spec.class_roles_source == "project"

    def test_project_roles_for_another_weight_yield_to_the_weight_entry(self, registry):
        wm, files = registry
        wm.weights[files["rat"].name]["class_roles"] = {"rat": "subject"}
        project = {
            "model_overrides": {
                "slot_weights": {"det:zebrafish": files["rat"].name},
                "class_roles": RAT_ROLES,
                "class_roles_weight_sha256": "0" * 64,
            }
        }

        spec = resolve_worker_model(wm, _settings(), project)

        assert spec.class_roles == {"rat": "subject"}
        assert spec.class_roles_source == "weight"

    def test_no_explicit_roles_means_aliases(self, registry):
        wm, _files = registry

        spec = resolve_worker_model(wm, _settings(), None)

        assert spec.class_roles is None
        assert spec.class_roles_source is None

    def test_project_roles_without_a_weight_sha_are_not_trusted(self):
        project = {"model_overrides": {"class_roles": RAT_ROLES, "class_roles_weight_sha256": ""}}
        assert resolve_project_class_roles(project, None, "") == (None, None)


def test_spec_is_pickle_safe(registry):
    wm, files = registry
    spec = resolve_worker_model(
        wm, _settings(), {"model_overrides": {"slot_weights": {"det:zebrafish": files["rat"].name}}}
    )

    restored = pickle.loads(pickle.dumps(spec))

    assert restored == spec
    assert isinstance(restored, WorkerModelSpec)
