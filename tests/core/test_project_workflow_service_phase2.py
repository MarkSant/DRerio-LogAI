"""Phase 2 tests for ProjectWorkflowService.

Covers the new helpers introduced to migrate the wizard's legacy
``weight_assignments`` payload into the 4-slot WeightManager dict and
to persist detector hyperparameter overrides at project creation time.
"""

from __future__ import annotations

from unittest.mock import Mock

import pytest

from zebtrack.core.project.project_workflow_service import ProjectWorkflowService


@pytest.fixture
def service() -> ProjectWorkflowService:
    return ProjectWorkflowService(
        project_manager=Mock(),
        model_service=Mock(),
        state_manager=Mock(),
        ui_coordinator=None,
    )


# ---------------------------------------------------------------------------
# _build_initial_slot_weights
# ---------------------------------------------------------------------------


def test_build_initial_slot_weights_emits_4slot_keys_for_animal_and_aquarium(
    service: ProjectWorkflowService,
) -> None:
    slot_weights = service._build_initial_slot_weights(
        weight_assignments={"aquarium": "tank.pt", "animal": "fish.pt"},
        animal_method="det",
        aquarium_method="seg",
    )

    assert slot_weights == {"det:zebrafish": "fish.pt", "seg:aquarium": "tank.pt"}


def test_build_initial_slot_weights_skips_missing_entries(
    service: ProjectWorkflowService,
) -> None:
    slot_weights = service._build_initial_slot_weights(
        weight_assignments={"aquarium": None, "animal": "fish.pt"},
        animal_method="det",
        aquarium_method="seg",
    )

    assert slot_weights == {"det:zebrafish": "fish.pt"}


def test_build_initial_slot_weights_handles_invalid_methods(
    service: ProjectWorkflowService,
) -> None:
    """Bad method names should not produce slot keys with garbage."""
    slot_weights = service._build_initial_slot_weights(
        weight_assignments={"aquarium": "tank.pt", "animal": "fish.pt"},
        animal_method="bogus",
        aquarium_method=None,
    )

    assert slot_weights == {}


def test_build_initial_slot_weights_returns_empty_for_non_dict_input(
    service: ProjectWorkflowService,
) -> None:
    assert (
        service._build_initial_slot_weights(
            weight_assignments=None,
            animal_method="det",
            aquarium_method="seg",
        )
        == {}
    )


# ---------------------------------------------------------------------------
# _build_detector_hyperparam_overrides
# ---------------------------------------------------------------------------


def test_build_detector_hyperparam_overrides_keeps_in_band_values(
    service: ProjectWorkflowService,
) -> None:
    overrides = service._build_detector_hyperparam_overrides(
        {
            "confidence_threshold": 0.35,
            "nms_threshold": 0.55,
            "ignored_extra_field": "should-not-leak",
        }
    )

    assert overrides == {"confidence_threshold": 0.35, "nms_threshold": 0.55}


def test_build_detector_hyperparam_overrides_drops_out_of_range(
    service: ProjectWorkflowService,
) -> None:
    overrides = service._build_detector_hyperparam_overrides(
        {"confidence_threshold": 1.5, "nms_threshold": -0.1}
    )

    assert overrides == {}


def test_build_detector_hyperparam_overrides_handles_string_floats(
    service: ProjectWorkflowService,
) -> None:
    overrides = service._build_detector_hyperparam_overrides(
        {"confidence_threshold": "0.4", "nms_threshold": "abc"}
    )

    assert overrides == {"confidence_threshold": 0.4}


def test_build_detector_hyperparam_overrides_returns_empty_for_non_dict(
    service: ProjectWorkflowService,
) -> None:
    assert service._build_detector_hyperparam_overrides(None) == {}
    assert service._build_detector_hyperparam_overrides("not-a-dict") == {}


# ---------------------------------------------------------------------------
# _persist_initial_project_overrides
# ---------------------------------------------------------------------------


def test_persist_initial_project_overrides_writes_slot_weights_and_hyperparams(
    service: ProjectWorkflowService,
) -> None:
    project_data: dict = {}
    service.project_manager.project_data = project_data
    service.project_manager.project_path = "/tmp/p"

    service._persist_initial_project_overrides(
        slot_weights={"det:zebrafish": "fish.pt", "seg:aquarium": "tank.pt"},
        detector_hyperparams={"confidence_threshold": 0.4, "nms_threshold": 0.5},
    )

    overrides = project_data["model_overrides"]
    assert overrides["slot_weights"] == {
        "det:zebrafish": "fish.pt",
        "seg:aquarium": "tank.pt",
    }
    assert overrides["confidence_threshold"] == 0.4
    assert overrides["nms_threshold"] == 0.5
    service.project_manager.save_project.assert_called_once()


def test_persist_initial_project_overrides_no_op_when_inputs_empty(
    service: ProjectWorkflowService,
) -> None:
    service.project_manager.project_data = {}
    service.project_manager.project_path = "/tmp/p"

    service._persist_initial_project_overrides(
        slot_weights={},
        detector_hyperparams={},
    )

    # Nothing to persist → save_project not called
    service.project_manager.save_project.assert_not_called()


def test_persist_initial_project_overrides_skips_when_no_project_path(
    service: ProjectWorkflowService,
) -> None:
    project_data: dict = {}
    service.project_manager.project_data = project_data
    service.project_manager.project_path = None

    service._persist_initial_project_overrides(
        slot_weights={"det:zebrafish": "fish.pt"},
        detector_hyperparams=None,
    )

    # Slot weights still mutate the in-memory record but no save is triggered
    # (no project on disk to write to).
    assert project_data["model_overrides"]["slot_weights"] == {"det:zebrafish": "fish.pt"}
    service.project_manager.save_project.assert_not_called()
