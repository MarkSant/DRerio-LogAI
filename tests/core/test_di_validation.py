"""Tests for MainViewModelDependencies.validate() (P0 audit fix).

Validates:
- Returns empty list when all coordinators wired
- Returns missing field names when coordinators are None
"""

from unittest.mock import MagicMock

from zebtrack.core.dependency_container import MainViewModelDependencies


def _make_deps(**overrides) -> MainViewModelDependencies:
    """Create a MainViewModelDependencies with all required fields mocked."""
    defaults = {
        "root": MagicMock(),
        "settings_obj": MagicMock(),
        "event_bus": MagicMock(),
        "state_manager": MagicMock(),
        "ui_coordinator": MagicMock(),
        "project_manager": MagicMock(),
        "project_workflow_service": MagicMock(),
        "weight_manager": MagicMock(),
        "model_service": MagicMock(),
        "detector_service": MagicMock(),
        "video_processing_service": MagicMock(),
    }
    defaults.update(overrides)
    return MainViewModelDependencies(**defaults)


class TestDependenciesValidate:
    """Tests for the validate() method on MainViewModelDependencies."""

    def test_all_none_returns_all_coordinator_names(self):
        deps = _make_deps()
        missing = deps.validate()
        assert len(missing) == 9
        assert "project_lifecycle_coordinator" in missing
        assert "live_batch_coordinator" in missing

    def test_all_wired_returns_empty(self):
        coordinator_fields = {
            "project_lifecycle_coordinator": MagicMock(),
            "detector_setup_coordinator": MagicMock(),
            "model_diagnostics_coordinator": MagicMock(),
            "processing_coordinator": MagicMock(),
            "recording_session_coordinator": MagicMock(),
            "live_camera_session_coordinator": MagicMock(),
            "live_calibration_coordinator": MagicMock(),
            "project_workflow_adapter": MagicMock(),
            "live_batch_coordinator": MagicMock(),
        }
        deps = _make_deps(**coordinator_fields)
        assert deps.validate() == []

    def test_partial_wiring(self):
        deps = _make_deps(
            project_lifecycle_coordinator=MagicMock(),
            processing_coordinator=MagicMock(),
        )
        missing = deps.validate()
        assert "project_lifecycle_coordinator" not in missing
        assert "processing_coordinator" not in missing
        assert "detector_setup_coordinator" in missing
        assert len(missing) == 7
