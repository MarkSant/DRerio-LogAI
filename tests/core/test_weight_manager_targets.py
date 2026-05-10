"""Tests for the 4-target default-slot architecture and maintenance API.

Covers:
* `target` field migration from legacy weights_config.json
* Path relocation (root → weights/) on first load
* `set_default_weight_for` independence across (method, target) slots
* `clear_openvino_cache` (single + all)
* `rescan_source_folder`
* `reset_registry`
* `validate_weight_files`
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from zebtrack.core.services.weight_manager import (
    DEFAULT_WEIGHTS_DIR,
    OPENVINO_CACHE_DIR,
    OPENVINO_STATUS_NOT_CONVERTED,
    OPENVINO_STATUS_READY,
    TARGET_AQUARIUM,
    TARGET_ZEBRAFISH,
    WeightManager,
    _default_flag_key,
    _default_target_for_type,
)


def _make_settings(weights_dir: str | None = None):
    s = Mock()
    s.yolo_model.path = None
    s.weights.lateral.seg_filename = None
    s.weights.lateral.det_filename = None
    s.weights.top_down.seg_filename = None
    s.weights.top_down.det_filename = None
    # Important: source_dir must be a real string for the defensive resolver.
    s.weights.source_dir = weights_dir or DEFAULT_WEIGHTS_DIR
    return s


@pytest.fixture
def project(tmp_path):
    """Layout: tmp_path acts as project root with a `weights/` folder inside."""
    weights_dir = tmp_path / "weights"
    weights_dir.mkdir()
    return tmp_path, weights_dir


@pytest.fixture
def wm(project):
    root, weights_dir = project
    # Create 2 dummy .pt files inside the weights folder (one seg, one det).
    (weights_dir / "best_seg_lateral.pt").write_bytes(b"FAKE")
    (weights_dir / "best_det_lateral.pt").write_bytes(b"FAKE")
    settings = _make_settings(str(weights_dir))
    return WeightManager(settings_obj=settings, config_dir=str(root))


# ---------------------------------------------------------------------------
# Helpers shipped from the module
# ---------------------------------------------------------------------------


def test_default_target_for_type_convention():
    assert _default_target_for_type("seg") == TARGET_ZEBRAFISH
    assert _default_target_for_type("det") == TARGET_AQUARIUM
    # Unknown type falls back to detection-of-aquarium convention
    assert _default_target_for_type("xyz") == TARGET_AQUARIUM


def test_default_flag_key_format():
    assert _default_flag_key("seg", TARGET_ZEBRAFISH) == "is_default_seg_zebrafish"
    assert _default_flag_key("det", TARGET_AQUARIUM) == "is_default_det_aquarium"


# ---------------------------------------------------------------------------
# Schema migration
# ---------------------------------------------------------------------------


def test_target_field_migrated_from_legacy_registry(project):
    """Legacy weights_config.json (no `target`) gains target by convention."""
    root, weights_dir = project
    weight_path = weights_dir / "best_seg_lateral.pt"
    weight_path.write_bytes(b"FAKE")

    legacy = {
        "best_seg_lateral.pt": {
            "path": str(weight_path),
            "type": "seg",
            "perspective": "lateral",
            "is_default_seg": True,
            "is_default_det": False,
            "is_default": True,
            "openvino_path": "",
            "openvino_hash": "",
            "openvino_status": "not_converted",
            "last_conversion_error": None,
            # NOTE: no `target` field — must be added by migration
        }
    }
    (root / "weights_config.json").write_text(json.dumps(legacy))

    settings = _make_settings(str(weights_dir))
    wm = WeightManager(settings_obj=settings, config_dir=str(root))

    details = wm.get_weight_details("best_seg_lateral.pt")
    assert details["target"] == TARGET_ZEBRAFISH
    # Legacy is_default_seg promoted to slot for current target
    assert details["is_default_seg_zebrafish"] is True
    # Other 3 slots default to False
    assert details["is_default_seg_aquarium"] is False
    assert details["is_default_det_aquarium"] is False
    assert details["is_default_det_zebrafish"] is False


def test_path_relocation_from_project_root(project):
    """An entry pointing to a missing root file is relocated to weights/."""
    root, weights_dir = project
    # The actual file lives in weights/, but the registry points at the old root.
    actual = weights_dir / "best_det_lateral.pt"
    actual.write_bytes(b"FAKE")

    legacy = {
        "best_det_lateral.pt": {
            "path": str(root / "best_det_lateral.pt"),  # stale root path
            "type": "det",
            "perspective": "lateral",
            "is_default_seg": False,
            "is_default_det": True,
            "is_default": True,
            "openvino_path": "",
            "openvino_hash": "",
            "openvino_status": "not_converted",
            "last_conversion_error": None,
        }
    }
    (root / "weights_config.json").write_text(json.dumps(legacy))

    settings = _make_settings(str(weights_dir))
    wm = WeightManager(settings_obj=settings, config_dir=str(root))

    new_path = wm.get_weight_details("best_det_lateral.pt")["path"]
    assert Path(new_path).resolve() == actual.resolve()


# ---------------------------------------------------------------------------
# 4-slot default management
# ---------------------------------------------------------------------------


def test_set_default_for_independent_slots(wm):
    """Each (method, target) slot is tracked independently."""
    assert wm.set_default_weight_for("best_seg_lateral.pt", method="seg", target=TARGET_ZEBRAFISH)
    assert wm.set_default_weight_for("best_det_lateral.pt", method="det", target=TARGET_AQUARIUM)
    seg_zb_name, _ = wm.get_default_weight_for("seg", TARGET_ZEBRAFISH)
    det_aq_name, _ = wm.get_default_weight_for("det", TARGET_AQUARIUM)
    seg_aq_name, _ = wm.get_default_weight_for("seg", TARGET_AQUARIUM)
    det_zb_name, _ = wm.get_default_weight_for("det", TARGET_ZEBRAFISH)
    assert seg_zb_name == "best_seg_lateral.pt"
    assert det_aq_name == "best_det_lateral.pt"
    assert seg_aq_name is None  # untouched slot
    assert det_zb_name is None


def test_set_default_for_rejects_type_mismatch(wm):
    """Cannot mark a det weight as a seg default."""
    assert not wm.set_default_weight_for(
        "best_det_lateral.pt", method="seg", target=TARGET_ZEBRAFISH
    )
    name, _ = wm.get_default_weight_for("seg", TARGET_ZEBRAFISH)
    assert name is None


def test_set_default_for_can_repurpose_target(wm):
    """Setting a seg weight as default for seg-aquarium reclassifies its target."""
    assert wm.set_default_weight_for("best_seg_lateral.pt", method="seg", target=TARGET_AQUARIUM)
    details = wm.get_weight_details("best_seg_lateral.pt")
    assert details["target"] == TARGET_AQUARIUM
    assert details["is_default_seg_aquarium"] is True


def test_get_weight_path_by_method_uses_target(wm):
    """`task` argument (animal/aquarium) drives the lookup precedence."""
    wm.set_default_weight_for("best_seg_lateral.pt", method="seg", target=TARGET_ZEBRAFISH)
    wm.set_default_weight_for("best_det_lateral.pt", method="det", target=TARGET_AQUARIUM)

    p_animal = wm.get_weight_path_by_method("seg", "animal", "lateral")
    p_aquarium = wm.get_weight_path_by_method("det", "aquarium", "lateral")
    assert p_animal and p_animal.endswith("best_seg_lateral.pt")
    assert p_aquarium and p_aquarium.endswith("best_det_lateral.pt")


def test_runtime_slot_override_takes_precedence_over_global_default(wm):
    """Project/runtime overrides must win without mutating persisted defaults."""
    wm.set_default_weight_for("best_det_lateral.pt", method="det", target=TARGET_AQUARIUM)

    extra_weight = Path(wm.weights_dir) / "project_det_aquarium.pt"
    extra_weight.write_bytes(b"FAKE")
    wm.weights["project_det_aquarium.pt"] = {
        "path": str(extra_weight),
        "type": "det",
        "target": TARGET_AQUARIUM,
        "perspective": "lateral",
        "is_default": False,
        "is_default_seg": False,
        "is_default_det": False,
        "is_default_seg_aquarium": False,
        "is_default_seg_zebrafish": False,
        "is_default_det_aquarium": False,
        "is_default_det_zebrafish": False,
        "openvino_path": "",
        "openvino_hash": "",
        "openvino_status": OPENVINO_STATUS_NOT_CONVERTED,
        "last_conversion_error": None,
    }

    wm.set_runtime_slot_overrides({("det", TARGET_AQUARIUM): "project_det_aquarium.pt"})

    runtime_path = wm.get_weight_path_by_method("det", "aquarium", "lateral")
    persisted_default, _ = wm.get_default_weight_for("det", TARGET_AQUARIUM)

    assert runtime_path and runtime_path.endswith("project_det_aquarium.pt")
    assert persisted_default == "best_det_lateral.pt"


def test_clear_runtime_slot_overrides_restores_global_default(wm):
    """Clearing runtime overrides must restore normal default-slot resolution."""
    wm.set_default_weight_for("best_det_lateral.pt", method="det", target=TARGET_AQUARIUM)

    extra_weight = Path(wm.weights_dir) / "project_det_aquarium.pt"
    extra_weight.write_bytes(b"FAKE")
    wm.weights["project_det_aquarium.pt"] = {
        "path": str(extra_weight),
        "type": "det",
        "target": TARGET_AQUARIUM,
        "perspective": "lateral",
        "is_default": False,
        "is_default_seg": False,
        "is_default_det": False,
        "is_default_seg_aquarium": False,
        "is_default_seg_zebrafish": False,
        "is_default_det_aquarium": False,
        "is_default_det_zebrafish": False,
        "openvino_path": "",
        "openvino_hash": "",
        "openvino_status": OPENVINO_STATUS_NOT_CONVERTED,
        "last_conversion_error": None,
    }

    wm.set_runtime_slot_overrides({("det", TARGET_AQUARIUM): "project_det_aquarium.pt"})
    wm.clear_runtime_slot_overrides()

    restored_path = wm.get_weight_path_by_method("det", "aquarium", "lateral")

    assert restored_path and restored_path.endswith("best_det_lateral.pt")


# ---------------------------------------------------------------------------
# Maintenance API
# ---------------------------------------------------------------------------


def test_clear_openvino_cache_single(wm, project):
    """Clearing one weight's cache removes its directory + resets status."""
    root, _ = project
    cache_dir = root / OPENVINO_CACHE_DIR / "best_seg_lateral_openvino_model"
    cache_dir.mkdir(parents=True)
    (cache_dir / "model.xml").write_text("<x/>")
    details = wm.get_weight_details("best_seg_lateral.pt")
    details["openvino_path"] = str(cache_dir)
    details["openvino_status"] = OPENVINO_STATUS_READY
    wm.save_weights()

    report = wm.clear_openvino_cache("best_seg_lateral.pt")
    assert report["cleared"] == ["best_seg_lateral.pt"]
    assert report["locked"] == []
    assert report["orphans_locked"] == []
    assert not cache_dir.exists()
    assert details["openvino_status"] == OPENVINO_STATUS_NOT_CONVERTED
    assert details["openvino_path"] == ""


def test_clear_openvino_cache_all_removes_orphans(wm, project):
    """Clearing all caches also removes orphaned converted folders."""
    root, _ = project
    cache_root = root / OPENVINO_CACHE_DIR
    orphan = cache_root / "deleted_weight_openvino_model"
    orphan.mkdir(parents=True)
    (orphan / "model.xml").write_text("<x/>")

    report = wm.clear_openvino_cache(None)
    assert sorted(report["cleared"]) == sorted(wm.weights.keys())
    assert report["locked"] == []
    assert report["orphans_locked"] == []
    assert not orphan.exists()


def test_clear_openvino_cache_locked_file_reports_in_locked_list(wm, project, monkeypatch):
    """When rmtree fails, the entry shows up in the 'locked' list."""
    root, _ = project
    cache_dir = root / OPENVINO_CACHE_DIR / "best_seg_lateral_openvino_model"
    cache_dir.mkdir(parents=True)
    (cache_dir / "model.xml").write_text("<x/>")
    details = wm.get_weight_details("best_seg_lateral.pt")
    details["openvino_path"] = str(cache_dir)
    details["openvino_status"] = OPENVINO_STATUS_READY
    wm.save_weights()

    # Force the unlock helper to always report failure (simulates an open
    # file handle that even chmod can't release).
    monkeypatch.setattr(
        "zebtrack.core.services.weight_manager.WeightManager._rmtree_with_unlock",
        staticmethod(lambda path, retries=3: False),
    )

    report = wm.clear_openvino_cache("best_seg_lateral.pt")
    assert report["cleared"] == []
    assert report["locked"] == ["best_seg_lateral.pt"]
    # Status should still be reset to "not_converted" so the UI doesn't
    # claim the cache is ready when it's actually mid-deletion.
    assert details["openvino_status"] == OPENVINO_STATUS_NOT_CONVERTED


def test_rescan_source_folder_picks_up_new_file(wm, project):
    _, weights_dir = project
    new_file = weights_dir / "best_det_topdown.pt"
    new_file.write_bytes(b"FAKE")

    added = wm.rescan_source_folder()
    assert added >= 1
    assert "best_det_topdown.pt" in wm.weights
    assert wm.get_weight_details("best_det_topdown.pt")["target"] == TARGET_AQUARIUM


def test_rescan_source_folder_idempotent(wm):
    """Re-running discovery on an unchanged folder adds nothing."""
    first = wm.rescan_source_folder()
    second = wm.rescan_source_folder()
    assert second == 0  # nothing new on the second pass
    # First call may add 0 too (everything already discovered on init)
    assert first >= 0


def test_reset_registry_wipes_and_rebuilds(wm, project):
    """reset_registry removes the JSON and rebuilds from scan + defaults."""
    root, _ = project
    config_path = root / "weights_config.json"
    assert config_path.exists()

    count = wm.reset_registry()
    # File rewritten by re-init + discovery
    assert config_path.exists()
    # Both seed weights re-discovered
    assert count == 2
    assert "best_seg_lateral.pt" in wm.weights
    assert "best_det_lateral.pt" in wm.weights


def test_validate_weight_files_detects_missing(wm, project):
    _, weights_dir = project
    # Delete one file from disk
    (weights_dir / "best_seg_lateral.pt").unlink()

    result = wm.validate_weight_files()
    assert result["best_seg_lateral.pt"] is False
    assert result["best_det_lateral.pt"] is True


# ---------------------------------------------------------------------------
# add_weight + target argument
# ---------------------------------------------------------------------------


def test_add_weight_accepts_explicit_target(project, tmp_path_factory):
    """External .pt (outside project tree) is copied into weights/."""
    root, weights_dir = project
    settings = _make_settings(str(weights_dir))
    wm = WeightManager(settings_obj=settings, config_dir=str(root))

    # Place the source file in a SEPARATE tmp dir so it's outside the project.
    external_dir = tmp_path_factory.mktemp("external_models")
    new_pt = external_dir / "external_seg.pt"
    new_pt.write_bytes(b"FAKE")

    wm.add_weight(str(new_pt), set_as_default=False, target=TARGET_AQUARIUM)

    details = wm.get_weight_details("external_seg.pt")
    assert details is not None
    assert details["target"] == TARGET_AQUARIUM
    # Copied into weights_dir, not project root
    assert Path(details["path"]).parent.resolve() == weights_dir.resolve()


def test_add_weight_inside_project_keeps_original_path(project, tmp_path):
    """A .pt already inside the project tree is registered in-place (no copy)."""
    root, weights_dir = project
    settings = _make_settings(str(weights_dir))
    wm = WeightManager(settings_obj=settings, config_dir=str(root))

    # File lives inside the project tree but outside weights/ (e.g. a custom subdir)
    inside_dir = root / "experiments"
    inside_dir.mkdir()
    inside_pt = inside_dir / "custom_seg.pt"
    inside_pt.write_bytes(b"FAKE")

    wm.add_weight(str(inside_pt), set_as_default=False, target=TARGET_ZEBRAFISH)

    details = wm.get_weight_details("custom_seg.pt")
    assert details is not None
    assert details["target"] == TARGET_ZEBRAFISH
    assert Path(details["path"]).resolve() == inside_pt.resolve()
