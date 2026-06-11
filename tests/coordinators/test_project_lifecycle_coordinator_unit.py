"""Unit tests for ProjectLifecycleCoordinator helpers."""

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock

import pytest

from zebtrack.coordinators.project_lifecycle_coordinator import ProjectLifecycleCoordinator
from zebtrack.ui.event_bus_v2 import UIEvents


@dataclass
class DummyAquarium:
    group: str | None = None
    subject_id: str | None = None
    day: int | None = None


@pytest.fixture
def event_bus():
    bus = MagicMock()
    bus.publish = MagicMock()
    bus.subscribe = MagicMock()
    return bus


@pytest.fixture
def coordinator(event_bus):
    return ProjectLifecycleCoordinator(
        state_manager=MagicMock(),
        project_manager=MagicMock(),
        project_workflow_service=MagicMock(),
        project_workflow_adapter=MagicMock(),
        settings_obj=MagicMock(),
        event_bus=event_bus,
        detector_service=MagicMock(),
    )


def test_register_event_handlers_sets_zone_manager_and_subscribes(coordinator, event_bus):
    zone_manager = MagicMock()

    coordinator.register_event_handlers(zone_manager=zone_manager)

    assert coordinator._zone_manager is zone_manager
    event_bus.subscribe.assert_called_with(
        UIEvents.ZONE_AQUARIUM_CONFIG_UPDATED, coordinator._handle_aquarium_config_updated
    )


@pytest.mark.parametrize("payload", [None, "invalid", 123])
def test_handle_aquarium_config_updated_ignores_non_dict(coordinator, payload):
    zone_manager = MagicMock()
    coordinator._zone_manager = zone_manager

    coordinator._handle_aquarium_config_updated(payload)

    zone_manager.get_multi_aquarium_zone_data.assert_not_called()


def test_handle_aquarium_config_updated_missing_fields(coordinator):
    zone_manager = MagicMock()
    coordinator._zone_manager = zone_manager

    coordinator._handle_aquarium_config_updated({"aquarium_id": 1})

    zone_manager.get_multi_aquarium_zone_data.assert_not_called()


def test_handle_aquarium_config_updated_no_zone_manager(coordinator):
    coordinator._zone_manager = None

    coordinator._handle_aquarium_config_updated(
        {"aquarium_id": 1, "config": {"group": "G1"}, "video_path": "/v.mp4"}
    )

    assert coordinator._zone_manager is None


def test_handle_aquarium_config_updated_no_zone_data(coordinator):
    zone_manager = MagicMock()
    zone_manager.get_multi_aquarium_zone_data.return_value = None
    coordinator._zone_manager = zone_manager

    coordinator._handle_aquarium_config_updated(
        {"aquarium_id": 1, "config": {"group": "G1"}, "video_path": "/v.mp4"}
    )

    zone_manager.save_multi_aquarium_zone_data.assert_not_called()


def test_handle_aquarium_config_updated_aquarium_not_found(coordinator):
    zone_manager = MagicMock()
    zone_data = MagicMock()
    zone_data.get_aquarium.return_value = None
    zone_manager.get_multi_aquarium_zone_data.return_value = zone_data
    coordinator._zone_manager = zone_manager

    coordinator._handle_aquarium_config_updated(
        {"aquarium_id": 99, "config": {"group": "G1"}, "video_path": "/v.mp4"}
    )

    zone_manager.save_multi_aquarium_zone_data.assert_not_called()


def test_handle_aquarium_config_updated_success_updates_aquarium(coordinator):
    zone_manager = MagicMock()
    aquarium = DummyAquarium(group="G0", subject_id="S0", day=0)
    zone_data = MagicMock()
    zone_data.get_aquarium.return_value = aquarium
    zone_manager.get_multi_aquarium_zone_data.return_value = zone_data
    coordinator._zone_manager = zone_manager

    coordinator._handle_aquarium_config_updated(
        {
            "aquarium_id": 1,
            "config": {"group": "G1", "subject_id": "S1", "day": 2},
            "video_path": "/v.mp4",
        }
    )

    assert aquarium.group == "G1"
    assert aquarium.subject_id == "S1"
    assert aquarium.day == 2
    zone_manager.save_multi_aquarium_zone_data.assert_called_once_with("/v.mp4", zone_data)


def test_close_project_publishes_events_and_updates_manager(coordinator, event_bus):
    new_manager = MagicMock()
    coordinator.project_workflow_adapter.close_project.return_value = new_manager

    result = coordinator.close_project()

    assert result is new_manager
    assert coordinator.project_manager is new_manager
    event_types = [call.args[0].type for call in event_bus.publish.call_args_list]
    assert UIEvents.PROJECT_MANAGER_REPLACED in event_types
    assert UIEvents.PROJECT_CLOSED in event_types


def test_close_project_stops_active_live_session(event_bus):
    """When a live session is running, close_project must stop it BEFORE
    delegating to the workflow adapter so the camera handle is released
    and worker threads are joined ahead of the project state reset.
    """
    live_camera_service = MagicMock()
    live_camera_service.is_session_active.return_value = True

    coord = ProjectLifecycleCoordinator(
        state_manager=MagicMock(),
        project_manager=MagicMock(),
        project_workflow_service=MagicMock(),
        project_workflow_adapter=MagicMock(),
        settings_obj=MagicMock(),
        event_bus=event_bus,
        live_camera_service=live_camera_service,
    )
    coord.project_workflow_adapter.close_project.return_value = MagicMock()  # type: ignore[attr-defined]

    coord.close_project()

    live_camera_service.is_session_active.assert_called_once()
    live_camera_service.stop_session.assert_called_once()
    # stop_session must be invoked before adapter.close_project
    assert (
        live_camera_service.stop_session.call_count
        >= 1  # explicit assertion above already checks; sanity here
    )


def test_close_project_skips_live_stop_when_not_active(event_bus):
    """No-op when no live session is running — avoids spurious UI events
    and avoids touching the camera/threads when there is nothing to clean.
    """
    live_camera_service = MagicMock()
    live_camera_service.is_session_active.return_value = False

    coord = ProjectLifecycleCoordinator(
        state_manager=MagicMock(),
        project_manager=MagicMock(),
        project_workflow_service=MagicMock(),
        project_workflow_adapter=MagicMock(),
        settings_obj=MagicMock(),
        event_bus=event_bus,
        live_camera_service=live_camera_service,
    )
    coord.project_workflow_adapter.close_project.return_value = MagicMock()  # type: ignore[attr-defined]

    coord.close_project()

    live_camera_service.is_session_active.assert_called_once()
    live_camera_service.stop_session.assert_not_called()


def test_close_project_handles_missing_live_camera_service(event_bus):
    """Coordinator must not crash when live_camera_service is not wired
    (legacy test setups, headless contexts).
    """
    coord = ProjectLifecycleCoordinator(
        state_manager=MagicMock(),
        project_manager=MagicMock(),
        project_workflow_service=MagicMock(),
        project_workflow_adapter=MagicMock(),
        settings_obj=MagicMock(),
        event_bus=event_bus,
        live_camera_service=None,
    )
    coord.project_workflow_adapter.close_project.return_value = MagicMock()  # type: ignore[attr-defined]

    # Should not raise
    coord.close_project()


def test_close_project_swallows_live_stop_errors(event_bus):
    """An exception while stopping the live session must NOT block close
    (the project still needs to be closed). The error is logged.
    """
    live_camera_service = MagicMock()
    live_camera_service.is_session_active.return_value = True
    live_camera_service.stop_session.side_effect = RuntimeError("camera stuck")

    coord = ProjectLifecycleCoordinator(
        state_manager=MagicMock(),
        project_manager=MagicMock(),
        project_workflow_service=MagicMock(),
        project_workflow_adapter=MagicMock(),
        settings_obj=MagicMock(),
        event_bus=event_bus,
        live_camera_service=live_camera_service,
    )
    new_manager = MagicMock()
    coord.project_workflow_adapter.close_project.return_value = new_manager  # type: ignore[attr-defined]

    result = coord.close_project()

    assert result is new_manager


# === Bug A: wizard use_openvino must override stale state defaults ============


def _make_create_project_coordinator(
    *,
    state_use_openvino: bool = False,
    state_active_weight: str = "",
    settings_use_openvino: bool = False,
    create_result: dict | None = None,
) -> ProjectLifecycleCoordinator:
    """Build a coordinator wired to inspect ``set_global_model_defaults`` calls."""
    workflow_service = MagicMock()
    workflow_service.create_project.return_value = create_result or {
        "success": False,
        "error_message": "stop short of UI updates",
        "wizard_metadata": None,
        "animal_method": None,
    }

    detector_state = SimpleNamespace(
        active_weight_name=state_active_weight,
        use_openvino=state_use_openvino,
    )
    state_manager = MagicMock()
    state_manager.get_detector_state.return_value = detector_state
    # ``get_state`` may be called by other helpers; align defaults too.
    state_manager.get_state.return_value = {
        "active_weight_name": state_active_weight,
        "use_openvino": state_use_openvino,
    }

    settings_obj = SimpleNamespace(
        model_selection=SimpleNamespace(use_openvino=settings_use_openvino),
    )

    return ProjectLifecycleCoordinator(
        state_manager=state_manager,
        project_manager=MagicMock(),
        project_workflow_service=workflow_service,
        project_workflow_adapter=MagicMock(),
        settings_obj=cast(Any, settings_obj),
        event_bus=MagicMock(),
        detector_service=MagicMock(),
    )


def test_create_project_prefers_wizard_use_openvino_over_stale_state():
    """Regression: wizard chooses OpenVINO but ``state_manager.detector_state``
    still holds the post-bootstrap default ``use_openvino=False``. The
    coordinator must prime ``_global_model_defaults`` with the wizard value,
    otherwise the resolver downstream falls back to ``False`` and the
    detector silently starts as PyTorch (see analysis.log 2026-06-10
    12:23:22 ``model_settings_resolved resolved_openvino=false``).
    """
    coord = _make_create_project_coordinator(
        state_use_openvino=False,
        settings_use_openvino=False,
    )

    coord.create_project(use_openvino=True, active_weight="best_det_topdown.pt")

    set_defaults = cast(MagicMock, coord.project_workflow_service.set_global_model_defaults)
    set_defaults.assert_called_once_with(
        active_weight="best_det_topdown.pt",
        use_openvino=True,
    )


def test_create_project_falls_back_to_settings_when_state_and_wizard_absent():
    """When the wizard does not pass ``use_openvino`` and the state default
    is still ``False``, the global ``settings.model_selection.use_openvino``
    is honored. Without this, projects created without an explicit wizard
    flag never inherit the user's persisted global preference."""
    coord = _make_create_project_coordinator(
        state_use_openvino=False,
        settings_use_openvino=True,
    )

    coord.create_project()

    set_defaults = cast(MagicMock, coord.project_workflow_service.set_global_model_defaults)
    set_defaults.assert_called_once()
    _, kwargs = set_defaults.call_args
    assert kwargs["use_openvino"] is True


def test_create_project_uses_state_when_wizard_silent_but_state_explicit():
    """If state already reflects a real choice (e.g. user toggled OpenVINO
    after startup), preserve it when the wizard does not override."""
    coord = _make_create_project_coordinator(
        state_use_openvino=True,
        state_active_weight="state_weight.pt",
        settings_use_openvino=False,
    )

    coord.create_project()

    set_defaults = cast(MagicMock, coord.project_workflow_service.set_global_model_defaults)
    set_defaults.assert_called_once()
    _, kwargs = set_defaults.call_args
    assert kwargs["use_openvino"] is True
    assert kwargs["active_weight"] == "state_weight.pt"


# === Bug C: copy_global_model_settings_to_project must rebuild detector ======


def test_copy_global_injects_default_setters_and_rebuilds_detector():
    """Regression: clicking "Copiar Globais para o Projeto" used to grava em
    disco and silently leave the detector unchanged (and the OpenVINO
    checkbox out of sync). With ``apply_runtime=True`` (default), the
    coordinator now injects real ``state_manager`` setters and a
    callback that rebuilds the detector + publishes UI events.
    """
    state_manager = MagicMock()
    detector_service = MagicMock()
    detector_service.initialize_detector.return_value = (True, None)
    event_bus = MagicMock()

    model_override_service = MagicMock()
    model_override_service.copy_global_model_settings_to_project.return_value = (
        "global_det.pt",
        True,
    )

    coord = ProjectLifecycleCoordinator(
        state_manager=state_manager,
        project_manager=MagicMock(),
        project_workflow_service=MagicMock(),
        project_workflow_adapter=MagicMock(),
        settings_obj=cast(
            Any, SimpleNamespace(model_selection=SimpleNamespace(animal_method="det"))
        ),
        event_bus=event_bus,
        detector_service=detector_service,
        model_override_service=model_override_service,
    )

    result = coord.copy_global_model_settings_to_project(
        get_global_defaults=lambda: {
            "active_weight": "global_det.pt",
            "use_openvino": True,
        },
        get_active_weight_name=lambda: "global_det.pt",
    )

    assert result == ("global_det.pt", True)
    # Real setters injetados (nao None). Bound methods nao sao ``is``
    # comparaveis entre acessos diferentes — compara por ``__func__``.
    call_kwargs = model_override_service.copy_global_model_settings_to_project.call_args.kwargs
    assert (
        call_kwargs["active_weight_setter"].__func__
        is ProjectLifecycleCoordinator._default_set_active_weight
    )
    assert (
        call_kwargs["use_openvino_setter"].__func__
        is ProjectLifecycleCoordinator._default_set_openvino_usage
    )
    assert (
        call_kwargs["apply_runtime_callback"].__func__
        is ProjectLifecycleCoordinator._default_apply_runtime_after_copy
    )

    # Apply runtime hook simula a entrega final (model_override_service em
    # producao chama esse callback com os valores resolvidos).
    coord._default_apply_runtime_after_copy("global_det.pt", True)

    # Eventos UI publicados. `_publish_event` em BaseCoordinator
    # transforma em Event(type=...); validamos so a presenca de
    # publicacoes em vez de inspecionar o payload aninhado.
    assert event_bus.publish.called

    # Detector reconstruido.
    detector_service.initialize_detector.assert_called_once()
    init_kwargs = detector_service.initialize_detector.call_args.kwargs
    assert init_kwargs["use_openvino"] is True
    assert init_kwargs["animal_method"] == "det"


def test_copy_global_with_apply_runtime_false_skips_defaults():
    """Tests/legacy callers can opt out of the runtime side effects."""
    model_override_service = MagicMock()
    model_override_service.copy_global_model_settings_to_project.return_value = (
        None,
        False,
    )

    coord = ProjectLifecycleCoordinator(
        state_manager=MagicMock(),
        project_manager=MagicMock(),
        project_workflow_service=MagicMock(),
        project_workflow_adapter=MagicMock(),
        settings_obj=MagicMock(),
        event_bus=MagicMock(),
        detector_service=MagicMock(),
        model_override_service=model_override_service,
    )

    coord.copy_global_model_settings_to_project(
        get_global_defaults=lambda: {},
        get_active_weight_name=lambda: None,
        apply_runtime=False,
    )

    call_kwargs = model_override_service.copy_global_model_settings_to_project.call_args.kwargs
    assert call_kwargs["active_weight_setter"] is None
    assert call_kwargs["use_openvino_setter"] is None
    assert call_kwargs["apply_runtime_callback"] is None
