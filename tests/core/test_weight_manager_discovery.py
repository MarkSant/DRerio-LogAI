"""Discovery of weight files in the weights folder.

``WeightManager.discover_weights()`` used to glob only ``best_*_lateral.pt`` and
``best_*_topdown.pt``. The two generalists shipped in the same release --
``best_oi.pt`` and ``best_seg.pt`` -- matched neither pattern, so they were
invisible to the catalogue even when present on disk. That is why the installer
did not download them: fetching a file nothing could select was pointless.

These tests pin both halves of the fix: everything named ``best_*.pt`` is
registered, and a generalist never takes a default slot away from a
perspective-trained specialist.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import Mock

import pytest

from zebtrack.core.services.weight_manager import WeightManager

SPECIALISTS = (
    "best_seg_lateral.pt",
    "best_det_lateral.pt",
    "best_seg_topdown.pt",
    "best_det_topdown.pt",
)
GENERALISTS = ("best_oi.pt", "best_seg.pt")


def _blank_settings() -> Mock:
    """Settings that name no weight, so only discovery populates the catalogue."""
    settings = Mock()
    settings.yolo_model.path = None
    settings.weights.lateral.seg_filename = None
    settings.weights.lateral.det_filename = None
    settings.weights.top_down.seg_filename = None
    settings.weights.top_down.det_filename = None
    return settings


@pytest.fixture
def populated_weights_dir():
    """A weights folder holding all six published models."""
    with tempfile.TemporaryDirectory() as temp_dir:
        for name in SPECIALISTS + GENERALISTS:
            with open(os.path.join(temp_dir, name), "w", encoding="utf-8") as handle:
                handle.write("mock checkpoint")
        yield temp_dir


def test_all_six_published_models_are_registered(populated_weights_dir):
    manager = WeightManager(settings_obj=_blank_settings(), config_dir=populated_weights_dir)

    for name in SPECIALISTS + GENERALISTS:
        assert name in manager.weights, f"{name} was not discovered"


def test_generalists_never_claim_a_default_slot(populated_weights_dir):
    """A generalist must not displace a perspective-trained specialist.

    The specialists are trained for one camera angle; a lateral model on a
    top-down scene returns nothing. Auto-promoting the generic weight to the
    default would degrade every run that never opened the model panel.
    """
    manager = WeightManager(settings_obj=_blank_settings(), config_dir=populated_weights_dir)

    for name in GENERALISTS:
        entry = manager.weights[name]
        assert entry["is_default"] is False
        assert entry["is_default_seg"] is False
        assert entry["is_default_det"] is False
        assert entry["perspective"] is None


def test_specialists_keep_their_type_defaults(populated_weights_dir):
    manager = WeightManager(settings_obj=_blank_settings(), config_dir=populated_weights_dir)

    assert manager.weights["best_seg_lateral.pt"]["is_default_seg"] is True
    assert manager.weights["best_det_lateral.pt"]["is_default_det"] is True
    assert manager.weights["best_seg_lateral.pt"]["perspective"] == "lateral"
    assert manager.weights["best_det_topdown.pt"]["perspective"] == "top_down"


def test_generalists_are_classified_by_type_not_ignored(populated_weights_dir):
    """Registering them is only useful if the type is right.

    ``best_seg.pt`` is segmentation and ``best_oi.pt`` is detection; a
    misclassified entry would offer the wrong model in the wrong slot.
    """
    manager = WeightManager(settings_obj=_blank_settings(), config_dir=populated_weights_dir)

    assert manager.weights["best_seg.pt"]["type"] == "seg"
    assert manager.weights["best_oi.pt"]["type"] == "det"


def test_a_generalist_can_be_promoted_by_hand(populated_weights_dir):
    """Opting in is the point: discovery makes them selectable, not default."""
    manager = WeightManager(settings_obj=_blank_settings(), config_dir=populated_weights_dir)

    manager.set_default_weight_by_type("best_seg.pt", "seg")

    name, _details = manager.get_default_seg_weight()
    assert name == "best_seg.pt"


def test_discovery_counts_only_new_files(populated_weights_dir):
    """A second sweep must not re-register what is already catalogued."""
    manager = WeightManager(settings_obj=_blank_settings(), config_dir=populated_weights_dir)

    assert manager.discover_weights() == 0


def test_discovered_path_points_at_the_file_that_was_found(populated_weights_dir):
    """Identity, asserted by resolution rather than by string equality.

    The registered path is built from the directory listing, which need not
    spell the directory the way the caller did -- on Windows a temp folder is
    listed in its 8.3 short form while tempfile reports the long one. Callers
    that compare these as strings are asserting a spelling, not a file.
    """
    manager = WeightManager(settings_obj=_blank_settings(), config_dir=populated_weights_dir)

    for name in SPECIALISTS + GENERALISTS:
        registered = Path(manager.weights[name]["path"])
        assert registered.is_absolute()
        assert registered.resolve() == (Path(populated_weights_dir) / name).resolve()


def test_unrelated_pt_files_are_left_alone(populated_weights_dir):
    """The glob is ``best_*.pt``; a stray checkpoint is not a catalogued model."""
    with open(os.path.join(populated_weights_dir, "yolov8n.pt"), "w", encoding="utf-8") as handle:
        handle.write("mock checkpoint")

    manager = WeightManager(settings_obj=_blank_settings(), config_dir=populated_weights_dir)

    assert "yolov8n.pt" not in manager.weights
