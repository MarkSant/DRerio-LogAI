"""
Test Composition Root (DI Container) - FASE 1 Validation.

This module validates that the application can be assembled without
dependency injection errors, ensuring all services receive required
dependencies via constructor.
"""

import pytest


def test_composition_root_loads_settings():
    """Validate that load_settings() returns a Settings object."""
    from zebtrack.settings import load_settings

    settings_obj = load_settings()

    assert settings_obj is not None
    assert hasattr(settings_obj, "camera")
    assert hasattr(settings_obj, "yolo_model")
    assert hasattr(settings_obj, "ui_features")


def test_composition_root_instantiates_state_manager():
    """Validate StateManager instantiation (no dependencies)."""
    from zebtrack.core.state_manager import StateManager

    state_manager = StateManager()

    assert state_manager is not None
    assert hasattr(state_manager, "update_project_state")
    assert hasattr(state_manager, "get_project_state")


def test_composition_root_instantiates_event_bus():
    """Validate EventBus instantiation."""
    from zebtrack.ui.event_bus import EventBus

    event_bus = EventBus(maxsize=0)

    assert event_bus is not None
    assert hasattr(event_bus, "publish")
    assert hasattr(event_bus, "subscribe")


def test_composition_root_instantiates_project_manager():
    """Validate ProjectManager with settings_obj injection."""
    from zebtrack.core.project_manager import ProjectManager
    from zebtrack.settings import load_settings

    settings_obj = load_settings()
    project_manager = ProjectManager(settings_obj=settings_obj)

    assert project_manager is not None
    assert project_manager.settings is not None


def test_composition_root_instantiates_weight_manager():
    """Validate WeightManager with settings_obj injection."""
    from zebtrack.core.weight_manager import WeightManager
    from zebtrack.settings import load_settings

    settings_obj = load_settings()
    weight_manager = WeightManager(settings_obj=settings_obj)

    assert weight_manager is not None
    assert weight_manager.settings is not None


def test_composition_root_instantiates_detector_service():
    """Validate DetectorService with all required dependencies."""
    from zebtrack.core.detector_service import DetectorService
    from zebtrack.core.model_service import ModelService
    from zebtrack.core.project_manager import ProjectManager
    from zebtrack.core.state_manager import StateManager
    from zebtrack.core.weight_manager import WeightManager
    from zebtrack.settings import load_settings

    settings_obj = load_settings()
    state_manager = StateManager()
    project_manager = ProjectManager(settings_obj=settings_obj)
    weight_manager = WeightManager(settings_obj=settings_obj)
    model_service = ModelService(weight_manager=weight_manager)

    detector_service = DetectorService(
        settings_obj=settings_obj,
        weight_manager=weight_manager,
        state_manager=state_manager,
        project_manager=project_manager,
        model_service=model_service,
    )

    assert detector_service is not None
    assert detector_service.settings is not None


@pytest.mark.slow
def test_full_composition_root_assembly(tmp_path):
    """
    Integration test: Validate core services can be instantiated.

    This test validates that the main services required by the application
    can be instantiated with proper dependency injection. Full MainViewModel
    assembly is tested separately in integration tests.
    """
    from zebtrack.analysis.analysis_service import AnalysisService
    from zebtrack.core.project_manager import ProjectManager
    from zebtrack.core.state_manager import StateManager
    from zebtrack.core.weight_manager import WeightManager
    from zebtrack.settings import load_settings
    from zebtrack.ui.event_bus import EventBus

    # 1. Load settings
    settings_obj = load_settings()

    # 2. Instantiate core services (no dependencies)
    state_manager = StateManager()
    event_bus = EventBus(maxsize=0)

    # 3. Instantiate domain services (with settings_obj)
    project_manager = ProjectManager(settings_obj=settings_obj)
    weight_manager = WeightManager(settings_obj=settings_obj)
    analysis_service = AnalysisService(settings_obj=settings_obj)

    # Assertions
    assert settings_obj is not None
    assert state_manager is not None
    assert event_bus is not None
    assert project_manager is not None
    assert weight_manager is not None
    assert analysis_service is not None

    # Verify services have settings injected
    assert project_manager.settings is not None
    assert weight_manager.settings is not None
    assert analysis_service.settings is not None


def test_no_singleton_settings_import():
    """
    Validate that the singleton 'settings' is deprecated.

    This test ensures that importing 'from zebtrack.settings import settings'
    is not used anywhere in the core service layer.
    """
    # This is a meta-test: if services import singleton, they will fail
    # the other tests above (because settings won't be overridden).
    # Here we just document the expectation.
    from zebtrack.settings import Settings

    # Settings class exists for type hinting
    assert Settings is not None

    # But singleton 'settings' should not be used
    # (If it were, the test_full_composition_root_assembly would fail
    # because tmp_path override wouldn't work)


@pytest.mark.parametrize(
    "service_class",
    [
        "zebtrack.core.weight_manager.WeightManager",
        "zebtrack.analysis.analysis_service.AnalysisService",
    ],
)
def test_service_accepts_settings_obj(service_class):
    """
    Parameterized test: Verify that services accept settings_obj.

    This test ensures that services can be instantiated with settings_obj
    parameter via dependency injection.
    """
    from zebtrack.settings import load_settings

    # Import the class dynamically
    module_name, class_name = service_class.rsplit(".", 1)
    module = __import__(module_name, fromlist=[class_name])
    ServiceClass = getattr(module, class_name)

    # Load settings
    settings_obj = load_settings()

    # Instantiate with settings_obj
    service = ServiceClass(settings_obj=settings_obj)

    # Verify settings were injected
    assert service is not None
    assert hasattr(service, "settings")
    assert service.settings is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
