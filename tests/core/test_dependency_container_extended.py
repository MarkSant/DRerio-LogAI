"""
Extended unit tests for LazyRef and MainViewModelDependencies in dependency_container.py.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from zebtrack.core.dependency_container import LazyRef, MainViewModelDependencies


class DummyTarget:
    def __init__(self, value: int = 42) -> None:
        self.value = value
        self.called = False

    def do_something(self, msg: str) -> str:
        self.called = True
        return f"result: {msg}"


class TestLazyRefExtended:
    """Test LazyRef transparent proxy behavior and lifecycle errors."""

    def test_lazy_ref_initial_state(self):
        ref: LazyRef[DummyTarget] = LazyRef("TestRef")
        assert not ref.is_resolved
        assert "[unresolved]" in repr(ref)

    def test_get_before_set_raises_runtime_error(self):
        ref: LazyRef[DummyTarget] = LazyRef("TestRef")
        with pytest.raises(RuntimeError, match="instance not yet set"):
            ref.get()

    def test_getattr_before_set_raises_runtime_error(self):
        ref: LazyRef[DummyTarget] = LazyRef("TestRef")
        with pytest.raises(RuntimeError, match="cannot access 'do_something' before set"):
            _ = ref.do_something

    def test_setattr_before_set_raises_runtime_error(self):
        ref: LazyRef[DummyTarget] = LazyRef("TestRef")
        with pytest.raises(RuntimeError, match="cannot set 'value' before set"):
            ref.value = 100

    def test_set_twice_raises_runtime_error(self):
        ref: LazyRef[DummyTarget] = LazyRef("TestRef")
        target = DummyTarget()
        ref.set(target)
        with pytest.raises(RuntimeError, match="instance already set"):
            ref.set(DummyTarget())

    def test_successful_resolution_and_proxying(self):
        ref: LazyRef[DummyTarget] = LazyRef("TargetRef")
        target = DummyTarget(value=99)
        ref.set(target)

        assert ref.is_resolved
        assert ref.get() is target
        assert "DummyTarget" in repr(ref)

        # Attribute access forwarded
        assert ref.value == 99

        # Method call forwarded
        result = ref.do_something("hello")
        assert result == "result: hello"
        assert target.called is True

        # Attribute writing forwarded
        ref.value = 200
        assert target.value == 200


class TestMainViewModelDependenciesValidation:
    """Test MainViewModelDependencies.validate() for missing coordinators."""

    def test_validate_with_all_none_coordinators(self):
        deps = MainViewModelDependencies(
            root=MagicMock(),
            settings_obj=MagicMock(),
            event_bus=MagicMock(),
            state_manager=MagicMock(),
            ui_coordinator=MagicMock(),
            project_manager=MagicMock(),
            project_workflow_service=MagicMock(),
            weight_manager=MagicMock(),
            model_service=MagicMock(),
            detector_service=MagicMock(),
            video_processing_service=MagicMock(),
        )
        missing = deps.validate()
        assert len(missing) == 9
        assert "project_lifecycle_coordinator" in missing
        assert "detector_setup_coordinator" in missing
        assert "processing_coordinator" in missing

    def test_validate_with_all_coordinators_provided(self):
        deps = MainViewModelDependencies(
            root=MagicMock(),
            settings_obj=MagicMock(),
            event_bus=MagicMock(),
            state_manager=MagicMock(),
            ui_coordinator=MagicMock(),
            project_manager=MagicMock(),
            project_workflow_service=MagicMock(),
            weight_manager=MagicMock(),
            model_service=MagicMock(),
            detector_service=MagicMock(),
            video_processing_service=MagicMock(),
            project_lifecycle_coordinator=MagicMock(),
            detector_setup_coordinator=MagicMock(),
            model_diagnostics_coordinator=MagicMock(),
            processing_coordinator=MagicMock(),
            recording_session_coordinator=MagicMock(),
            live_camera_session_coordinator=MagicMock(),
            live_calibration_coordinator=MagicMock(),
            project_workflow_adapter=MagicMock(),
            live_batch_coordinator=MagicMock(),
        )
        assert deps.validate() == []
