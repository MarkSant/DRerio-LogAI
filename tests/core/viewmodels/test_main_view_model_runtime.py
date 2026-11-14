"""Tests for MainViewModelRuntime: event routing, state bridges and shutdown.

The runtime is real in every test; only its collaborators (the sub-view-models,
the bus, the threads) are faked, and the fakes record what they were asked to
do so each assertion is on a routed argument or a published payload.

Not covered on purpose: ``RECORDING_TOGGLE``, ``MODEL_ADD_WEIGHT``,
``MODEL_CLEAR_OPENVINO_CACHE``, ``MODEL_VALIDATE_WEIGHTS``,
``CALIBRATION_COPY_TO_PROJECT`` and ``CALIBRATION_SAVE_TO_PROJECT``: the event
audit says nothing publishes them.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, cast

import pytest

from zebtrack.core.state_manager import StateCategory
from zebtrack.core.viewmodels.main_view_model_runtime import (
    MainViewModelRuntime,
    _payload_get,
    _payload_to_dict,
)
from zebtrack.ui import payloads
from zebtrack.ui.event_bus_v2 import Event, UIEvents


class Spy:
    """Records every method call as ``(name, args, kwargs)``; returns ``returns[name]``."""

    camera: Any = None  # a real attribute, so a Spy never invents a callable camera

    def __init__(self, **returns: Any) -> None:
        self.calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []
        self._returns = returns

    def __getattr__(self, name: str) -> Any:
        if name.startswith("__"):
            raise AttributeError(name)

        def method(*args: Any, **kwargs: Any) -> Any:
            self.calls.append((name, args, kwargs))
            return self._returns.get(name)

        # Cache so ``spy.name == spy.name`` (a Thread target is compared by identity).
        self.__dict__[name] = method
        return method

    def names(self) -> list[str]:
        return [c[0] for c in self.calls]

    def only(self, name: str) -> tuple[tuple[Any, ...], dict[str, Any]]:
        matching = [c for c in self.calls if c[0] == name]
        assert len(matching) == 1, f"{name!r} called {len(matching)} times: {self.calls}"
        return matching[0][1], matching[0][2]


class FakeBus:
    def __init__(self) -> None:
        self.subscriptions: list[tuple[Any, Any]] = []
        self.published: list[Event] = []

    def subscribe(self, event: Any, handler: Any) -> None:
        self.subscriptions.append((event, handler))

    def publish(self, event: Event) -> None:
        self.published.append(event)


def _vm(**overrides: Any) -> SimpleNamespace:
    base: dict[str, Any] = {
        "hardware_vm": Spy(),
        "project_vm": Spy(),
        "analysis_vm": Spy(),
        "ui_event_bus": FakeBus(),
        "ui_state_controller": Spy(),
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _runtime(vm: SimpleNamespace) -> MainViewModelRuntime:
    return MainViewModelRuntime(cast(Any, vm))


@dataclass
class DummyPayload:
    video_path: str
    flag: bool


# --------------------------------------------------------------------------- helpers


def test_payload_to_dict_handles_none_dict_dataclass_and_foreign_objects() -> None:
    assert _payload_to_dict(None) == {}
    assert _payload_to_dict({"a": 1}) == {"a": 1}
    assert _payload_to_dict(DummyPayload("vid.mp4", True)) == {
        "video_path": "vid.mp4",
        "flag": True,
    }
    # A dataclass CLASS is not an instance: it must not be introspected.
    assert _payload_to_dict(cast(Any, DummyPayload)) == {}
    assert _payload_to_dict(cast(Any, "not-a-payload")) == {}


def test_payload_get_handles_none_dict_dataclass_and_foreign_objects() -> None:
    assert _payload_get(None, "key", default=10) == 10
    assert _payload_get({"key": 20}, "key") == 20
    assert _payload_get({}, "key", "fallback") == "fallback"
    payload = DummyPayload("vid.mp4", True)
    assert _payload_get(payload, "video_path") == "vid.mp4"
    assert _payload_get(payload, "missing", default="none") == "none"
    assert _payload_get(cast(Any, DummyPayload), "video_path", "cls") == "cls"
    assert _payload_get(cast(Any, 42), "video_path", "int") == "int"


# ------------------------------------------------------------------------ registration


def test_register_event_handlers_without_bus_is_a_noop() -> None:
    vm = _vm(ui_event_bus=None)
    _runtime(vm).register_event_handlers()  # must not raise


def test_register_event_handlers_subscribes_every_event_once_plus_manager_replaced() -> None:
    vm = _vm()
    runtime = _runtime(vm)

    runtime.register_event_handlers()

    subscribed = [event for event, _ in vm.ui_event_bus.subscriptions]
    assert subscribed[:-1] == list(MainViewModelRuntime._EVENTS_TO_HANDLE)
    assert subscribed[-1] is UIEvents.PROJECT_MANAGER_REPLACED
    assert vm.ui_event_bus.subscriptions[-1][1] == runtime.handle_project_manager_replaced


def test_handler_created_by_registration_forwards_the_event_name() -> None:
    vm = _vm()
    runtime = _runtime(vm)
    runtime.register_event_handlers()
    handler = dict(vm.ui_event_bus.subscriptions)[UIEvents.RECORDING_START]

    handler(cast(Any, None))

    assert vm.hardware_vm.names() == ["start_recording"]


def test_unhandled_event_is_ignored() -> None:
    vm = _vm()

    _runtime(vm).handle_event(UIEvents.SET_STATUS, cast(Any, {"message": "x"}))

    assert vm.hardware_vm.calls == vm.project_vm.calls == vm.analysis_vm.calls == []


# -------------------------------------------------------------------------- recording


@pytest.mark.parametrize(
    ("event", "expected"),
    [
        (UIEvents.RECORDING_START, "start_recording"),
        (UIEvents.RECORDING_STOP, "stop_recording"),
    ],
)
def test_recording_events_route_to_hardware_vm(event: UIEvents, expected: str) -> None:
    vm = _vm()

    _runtime(vm).handle_event(event, cast(Any, None))

    assert vm.hardware_vm.names() == [expected]


# --------------------------------------------------------------------------- project


def test_project_create_merges_nested_wizard_data_over_flat_fields() -> None:
    vm = _vm()
    payload = payloads.ProjectCreatePayload(
        project_path="/top/path",
        project_name="TopName",
        project_type="experimental",
        wizard_data={
            "project_name": "NestedName",
            "video_count": 3,
            "scanned_videos": [{"path": "/videos/a.mp4"}],
        },
    )

    _runtime(vm).handle_event(UIEvents.PROJECT_CREATE, payload)

    _, kwargs = vm.project_vm.only("create_project_workflow")
    assert kwargs == {
        "project_name": "NestedName",  # nested wins: setdefault
        "project_path": "/top/path",
        "project_type": "experimental",
        "video_count": 3,
        "scanned_videos": [{"path": "/videos/a.mp4"}],
    }


def test_project_create_accepts_flat_payload_and_skips_none_fields() -> None:
    vm = _vm()
    payload = payloads.ProjectCreatePayload(
        project_path="/flat/path",
        project_name="FlatProject",
        project_type=None,
        wizard_data=None,
    )

    _runtime(vm).handle_event(UIEvents.PROJECT_CREATE, payload)

    _, kwargs = vm.project_vm.only("create_project_workflow")
    assert kwargs == {"project_path": "/flat/path", "project_name": "FlatProject"}


def test_project_create_ignores_non_dict_wizard_data() -> None:
    vm = _vm()

    _runtime(vm).handle_event(
        UIEvents.PROJECT_CREATE,
        cast(Any, {"project_name": "P", "wizard_data": "garbage"}),
    )

    assert vm.project_vm.only("create_project_workflow")[1] == {"project_name": "P"}


def test_project_open_routes_the_path_and_ignores_an_empty_one() -> None:
    vm = _vm()
    runtime = _runtime(vm)

    runtime.handle_event(UIEvents.PROJECT_OPEN, payloads.ProjectOpenPayload(project_path=""))
    assert vm.project_vm.calls == []

    runtime.handle_event(UIEvents.PROJECT_OPEN, payloads.ProjectOpenPayload(project_path="/p"))
    assert vm.project_vm.only("open_project_workflow") == (("/p",), {})


def test_project_close_routes_to_project_vm() -> None:
    vm = _vm()

    _runtime(vm).handle_event(UIEvents.PROJECT_CLOSE, cast(Any, None))

    assert vm.project_vm.names() == ["close_project"]


# ----------------------------------------------------------------------------- models


def test_model_set_openvino_splats_the_payload_fields() -> None:
    vm = _vm()
    payload = payloads.ModelSetOpenVinoPayload(use_openvino=True, dialog=None, device="GPU")

    _runtime(vm).handle_event(UIEvents.MODEL_SET_OPENVINO, payload)

    assert vm.hardware_vm.only("set_openvino_usage") == (
        (),
        {"use_openvino": True, "dialog": None, "device": "GPU"},
    )


def test_model_set_weight_accepts_legacy_weight_name_field() -> None:
    vm = _vm()
    dialog = object()

    _runtime(vm).handle_event(
        UIEvents.MODEL_SET_WEIGHT,
        payloads.ModelSetWeightPayload(weight_name="legacy.pt", dialog=dialog),
    )

    assert vm.hardware_vm.only("set_active_weight") == (("legacy.pt",), {"dialog": dialog})


def test_model_set_weight_prefers_name_over_legacy_field() -> None:
    vm = _vm()

    _runtime(vm).handle_event(
        UIEvents.MODEL_SET_WEIGHT,
        payloads.ModelSetWeightPayload(name="current.pt", weight_name="legacy.pt", dialog=None),
    )

    assert vm.hardware_vm.only("set_active_weight") == (("current.pt",), {"dialog": None})


def test_model_run_diagnostic_passes_config_and_defaults_missing_to_empty() -> None:
    vm = _vm()
    runtime = _runtime(vm)

    runtime.handle_event(UIEvents.MODEL_RUN_DIAGNOSTIC, cast(Any, {"config": {"n": 3}}))
    runtime.handle_event(UIEvents.MODEL_RUN_DIAGNOSTIC, cast(Any, {"config": None}))

    assert [c[1] for c in vm.hardware_vm.calls] == [({"n": 3},), ({},)]


def test_request_weight_file_routes_to_the_file_dialog_handler() -> None:
    vm = _vm()

    _runtime(vm).handle_event(UIEvents.UI_REQUEST_WEIGHT_FILE, cast(Any, None))

    assert vm.hardware_vm.names() == ["handle_request_weight_file"]


def test_model_delete_and_load_splat_their_payloads() -> None:
    vm = _vm()
    runtime = _runtime(vm)

    runtime.handle_event(UIEvents.MODEL_DELETE_WEIGHT, cast(Any, {"name": "old.pt"}))
    runtime.handle_event(UIEvents.MODEL_LOAD_NEW_WEIGHT, cast(Any, {"filepath": "/w/new.pt"}))

    assert vm.hardware_vm.calls == [
        ("delete_weight", (), {"name": "old.pt"}),
        ("load_new_weight", (), {"filepath": "/w/new.pt"}),
    ]


def test_model_set_default_for_maps_name_method_target() -> None:
    vm = _vm()

    _runtime(vm).handle_event(
        UIEvents.MODEL_SET_DEFAULT_FOR,
        cast(Any, {"name": "a.pt", "method": "seg", "target": "aquarium"}),
    )

    assert vm.hardware_vm.only("set_default_weight_for") == (
        ("a.pt",),
        {"method": "seg", "target": "aquarium"},
    )


def test_model_reclassify_maps_name_and_target() -> None:
    vm = _vm()

    _runtime(vm).handle_event(
        UIEvents.MODEL_RECLASSIFY_TARGET, cast(Any, {"name": "a.pt", "target": "zebrafish"})
    )

    assert vm.hardware_vm.only("reclassify_weight_target") == (("a.pt", "zebrafish"), {})


def test_model_rescan_and_reset_registry_route_without_arguments() -> None:
    vm = _vm()
    runtime = _runtime(vm)

    runtime.handle_event(UIEvents.MODEL_RESCAN_WEIGHTS, cast(Any, None))
    runtime.handle_event(UIEvents.MODEL_RESET_REGISTRY, cast(Any, None))

    assert vm.hardware_vm.calls == [
        ("rescan_weights_folder", (), {}),
        ("reset_weights_registry", (), {}),
    ]


class _ThreadProbe:
    """Records the target/name/daemon of a thread started by the runtime."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.started: list[dict[str, Any]] = []
        probe = self

        class FakeThread:
            def __init__(self, target: Any = None, args: Any = (), **kwargs: Any) -> None:
                self.record = {"target": target, "args": args, **kwargs}

            def start(self) -> None:
                probe.started.append(self.record)

        monkeypatch.setattr(threading, "Thread", FakeThread)


def test_force_benchmark_runs_on_a_named_daemon_thread(monkeypatch: pytest.MonkeyPatch) -> None:
    probe = _ThreadProbe(monkeypatch)
    vm = _vm()

    _runtime(vm).handle_event(UIEvents.MODEL_FORCE_BENCHMARK, cast(Any, None))

    assert len(probe.started) == 1
    record = probe.started[0]
    assert record["target"] == vm.hardware_vm.force_benchmark
    assert record["name"] == "force-benchmark"
    assert record["daemon"] is True
    assert vm.hardware_vm.calls == []  # the UI thread itself never runs the benchmark


def test_convert_openvino_prefers_weight_name_then_name(monkeypatch: pytest.MonkeyPatch) -> None:
    probe = _ThreadProbe(monkeypatch)
    vm = _vm()
    runtime = _runtime(vm)

    runtime.handle_event(
        UIEvents.MODEL_CONVERT_OPENVINO, cast(Any, {"weight_name": "w.pt", "name": "n.pt"})
    )
    runtime.handle_event(UIEvents.MODEL_CONVERT_OPENVINO, cast(Any, {"name": "n.pt"}))

    assert [(r["args"], r["name"], r["daemon"]) for r in probe.started] == [
        (("w.pt",), "openvino-convert-w.pt", True),
        (("n.pt",), "openvino-convert-n.pt", True),
    ]
    assert probe.started[0]["target"] == vm.hardware_vm.convert_weight_to_openvino


def test_convert_openvino_without_a_name_starts_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    probe = _ThreadProbe(monkeypatch)

    _runtime(_vm()).handle_event(UIEvents.MODEL_CONVERT_OPENVINO, cast(Any, {"name": ""}))

    assert probe.started == []


# ------------------------------------------------------------------------ video / zone


def test_video_analyze_single_routes_path_and_config_with_the_hardware_vm() -> None:
    vm = _vm()
    payload = payloads.VideoAnalyzeSinglePayload(video_path="/v.mp4", config={"fps": 5})

    _runtime(vm).handle_event(UIEvents.VIDEO_ANALYZE_SINGLE, payload)

    args, kwargs = vm.analysis_vm.only("start_single_video_workflow")
    assert args == ("/v.mp4", {"fps": 5})
    assert kwargs == {"detector_vm": vm.hardware_vm}


def test_video_analyze_single_without_config_passes_an_empty_dict() -> None:
    vm = _vm()

    _runtime(vm).handle_event(
        UIEvents.VIDEO_ANALYZE_SINGLE, payloads.VideoAnalyzeSinglePayload(video_path="/v.mp4")
    )

    assert vm.analysis_vm.only("start_single_video_workflow")[0] == ("/v.mp4", {})


def test_video_analyze_single_without_a_path_does_nothing() -> None:
    vm = _vm()

    _runtime(vm).handle_event(
        UIEvents.VIDEO_ANALYZE_SINGLE, cast(Any, {"video_path": "", "config": {}})
    )

    assert vm.analysis_vm.calls == []


def test_video_cancel_analysis_routes_to_analysis_vm() -> None:
    vm = _vm()

    _runtime(vm).handle_event(UIEvents.VIDEO_CANCEL_ANALYSIS, cast(Any, None))

    assert vm.analysis_vm.names() == ["cancel_current_analysis"]


def test_zone_save_manual_arena_routes_points_and_skips_a_missing_polygon() -> None:
    vm = _vm()
    runtime = _runtime(vm)

    runtime.handle_event(UIEvents.ZONE_SAVE_MANUAL_ARENA, cast(Any, {}))
    assert vm.analysis_vm.calls == []

    runtime.handle_event(
        UIEvents.ZONE_SAVE_MANUAL_ARENA, cast(Any, {"polygon_points": [(0, 0), (4, 0), (4, 4)]})
    )
    assert vm.analysis_vm.only("save_manual_arena") == (([(0, 0), (4, 0), (4, 4)],), {})


# ----------------------------------------------------------------------- project misc


def test_delete_asset_splats_the_payload() -> None:
    vm = _vm()

    _runtime(vm).handle_event(
        UIEvents.PROJECT_DELETE_ASSET,
        payloads.ProjectDeleteAssetPayload(video_path="/v.mp4", asset="trajectory"),
    )

    assert vm.project_vm.only("handle_delete_project_asset") == (
        (),
        {"video_path": "/v.mp4", "asset": "trajectory"},
    )


def test_delete_aquarium_splats_the_payload() -> None:
    vm = _vm()

    _runtime(vm).handle_event(
        UIEvents.PROJECT_DELETE_AQUARIUM,
        payloads.ProjectDeleteAquariumPayload(
            video_path="/v.mp4", aquarium_id=1, delete_files=False, delete_zone=True
        ),
    )

    assert vm.project_vm.only("handle_delete_aquarium") == (
        (),
        {"video_path": "/v.mp4", "aquarium_id": 1, "delete_files": False, "delete_zone": True},
    )


def test_clear_aquarium_subject_and_reset_analysis_data_splat_their_payloads() -> None:
    vm = _vm()
    runtime = _runtime(vm)

    runtime.handle_event(
        UIEvents.PROJECT_CLEAR_AQUARIUM_SUBJECT,
        cast(Any, {"video_path": "/v.mp4", "aquarium_id": 2}),
    )
    runtime.handle_event(
        UIEvents.PROJECT_RESET_ANALYSIS_DATA,
        cast(Any, {"video_path": "/v.mp4", "aquarium_id": None}),
    )

    assert vm.project_vm.calls == [
        ("handle_clear_aquarium_subject", (), {"video_path": "/v.mp4", "aquarium_id": 2}),
        ("handle_reset_analysis_data", (), {"video_path": "/v.mp4", "aquarium_id": None}),
    ]


@pytest.mark.parametrize(
    "event",
    [
        UIEvents.PROJECT_DELETE_ASSET,
        UIEvents.PROJECT_DELETE_AQUARIUM,
        UIEvents.PROJECT_CLEAR_AQUARIUM_SUBJECT,
        UIEvents.PROJECT_RESET_ANALYSIS_DATA,
        UIEvents.PROJECT_DELETE_GROUP,
        UIEvents.PROJECT_DELETE_DAY,
        UIEvents.PROJECT_DELETE_SUBJECT,
    ],
)
def test_deletion_events_with_an_empty_payload_delete_nothing(event: UIEvents) -> None:
    vm = _vm()

    _runtime(vm)._handle_project_deletion_events(event, {})
    _runtime(vm).handle_event(event, cast(Any, {}))

    assert vm.project_vm.calls == []


def test_delete_group_routes_to_hierarchy_deletion() -> None:
    vm = _vm()

    _runtime(vm).handle_event(
        UIEvents.PROJECT_DELETE_GROUP,
        payloads.ProjectDeleteGroupPayload(group_id="Grupo_A", delete_files=False),
    )

    assert vm.project_vm.only("handle_delete_hierarchy_node") == (
        ("group",),
        {"group_id": "Grupo_A", "delete_files": False},
    )


def test_delete_day_routes_to_hierarchy_deletion() -> None:
    vm = _vm()

    _runtime(vm).handle_event(
        UIEvents.PROJECT_DELETE_DAY,
        payloads.ProjectDeleteDayPayload(group_id="Grupo_A", day_id="Dia_2"),
    )

    assert vm.project_vm.only("handle_delete_hierarchy_node") == (
        ("day",),
        {"group_id": "Grupo_A", "day_id": "Dia_2", "delete_files": True},
    )


def test_delete_subject_routes_to_hierarchy_deletion() -> None:
    vm = _vm()

    _runtime(vm).handle_event(
        UIEvents.PROJECT_DELETE_SUBJECT,
        payloads.ProjectDeleteSubjectPayload(
            group_id="Grupo_A", day_id="Dia_2", subject_id="Sujeito_3"
        ),
    )

    assert vm.project_vm.only("handle_delete_hierarchy_node") == (
        ("subject",),
        {
            "group_id": "Grupo_A",
            "day_id": "Dia_2",
            "subject_id": "Sujeito_3",
            "delete_files": True,
        },
    )


def test_deletion_helper_reports_unrelated_events_as_not_handled() -> None:
    vm = _vm()

    handled = _runtime(vm)._handle_project_deletion_events(
        UIEvents.PROJECT_VIDEO_SELECTED, {"video_path": "/v.mp4"}
    )

    assert handled is False
    assert vm.project_vm.calls == []


def test_generate_summaries_routes_a_list_copy_and_skips_none() -> None:
    vm = _vm()
    runtime = _runtime(vm)

    runtime.handle_event(
        UIEvents.PROJECT_GENERATE_SUMMARIES, payloads.ProjectGenerateSummariesPayload()
    )
    assert vm.analysis_vm.calls == []

    runtime.handle_event(
        UIEvents.PROJECT_GENERATE_SUMMARIES,
        payloads.ProjectGenerateSummariesPayload(video_paths=("/a.mp4", "/b.mp4")),
    )
    args, _ = vm.analysis_vm.only("generate_parquet_summaries")
    assert args == (["/a.mp4", "/b.mp4"],)
    assert isinstance(args[0], list)  # tuples from the UI are normalised


def test_generate_summaries_with_an_empty_selection_still_routes() -> None:
    """``[]`` is "nothing to do" for the VM, but it is not the same as ``None``."""
    vm = _vm()

    _runtime(vm).handle_event(
        UIEvents.PROJECT_GENERATE_SUMMARIES,
        payloads.ProjectGenerateSummariesPayload(video_paths=[]),
    )

    assert vm.analysis_vm.only("generate_parquet_summaries")[0] == ([],)


def test_video_selected_routes_the_path_and_ignores_an_empty_one() -> None:
    vm = _vm()
    runtime = _runtime(vm)

    runtime.handle_event(
        UIEvents.PROJECT_VIDEO_SELECTED, payloads.ProjectVideoSelectedPayload(video_path="")
    )
    assert vm.project_vm.calls == []

    runtime.handle_event(
        UIEvents.PROJECT_VIDEO_SELECTED, payloads.ProjectVideoSelectedPayload(video_path="/v.mp4")
    )
    assert vm.project_vm.only("on_video_selected") == (("/v.mp4",), {})


def test_selection_changed_uses_the_first_selected_item() -> None:
    vm = _vm()

    _runtime(vm).handle_event(
        UIEvents.PROJECT_SELECTION_CHANGED,
        payloads.ProjectSelectionChangedPayload(selection=["/first.mp4", "/second.mp4"]),
    )

    assert vm.project_vm.only("on_video_selected") == (("/first.mp4",), {})


def test_selection_changed_prefers_an_explicit_video_path() -> None:
    vm = _vm()

    _runtime(vm).handle_event(
        UIEvents.PROJECT_SELECTION_CHANGED,
        cast(Any, {"video_path": "/explicit.mp4", "selection": ["/first.mp4"]}),
    )

    assert vm.project_vm.only("on_video_selected") == (("/explicit.mp4",), {})


def test_selection_changed_with_nothing_selected_does_nothing() -> None:
    vm = _vm()

    _runtime(vm).handle_event(
        UIEvents.PROJECT_SELECTION_CHANGED, payloads.ProjectSelectionChangedPayload(selection=[])
    )

    assert vm.project_vm.calls == []


# ------------------------------------------------------------------------ state bridges


def test_project_state_change_republishes_zones_for_the_two_zone_keys() -> None:
    zones = object()
    vm = _vm(project_manager=Spy(get_zone_data=zones))
    runtime = _runtime(vm)

    runtime.on_project_state_changed(StateCategory.PROJECT, "active_zone_video", None, "/v.mp4")

    assert [e.type for e in vm.ui_event_bus.published] == [
        UIEvents.UI_REDRAW_ZONES,
        UIEvents.UI_UPDATE_ZONE_LIST,
    ]
    assert all(
        e.data == payloads.ZonesUpdatedPayload(zone_data=zones) for e in vm.ui_event_bus.published
    )


def test_project_state_change_also_reacts_to_project_data() -> None:
    vm = _vm(project_manager=Spy(get_zone_data=None))

    _runtime(vm).on_project_state_changed(StateCategory.PROJECT, "project_data", {}, {"a": 1})

    assert len(vm.ui_event_bus.published) == 2


def test_project_state_change_ignores_other_keys_and_a_missing_bus() -> None:
    vm = _vm(project_manager=Spy())
    _runtime(vm).on_project_state_changed(StateCategory.PROJECT, "something_else", 1, 2)
    assert vm.ui_event_bus.published == []
    assert vm.project_manager.calls == []

    vm.ui_event_bus = None
    _runtime(vm).on_project_state_changed(StateCategory.PROJECT, "project_data", 1, 2)
    assert vm.project_manager.calls == []  # bus missing: the zones are not even fetched


def test_detector_state_change_publishes_the_active_weight() -> None:
    vm = _vm()

    _runtime(vm).on_detector_state_changed(
        StateCategory.DETECTOR, "active_weight_name", "old.pt", "new.pt"
    )

    assert vm.ui_event_bus.published == [
        Event(
            UIEvents.UI_SET_ACTIVE_WEIGHT, payloads.UISetActiveWeightPayload(weight_name="new.pt")
        )
    ]
    assert vm.ui_state_controller.calls == []


def test_detector_state_change_updates_checkbox_and_refreshes_openvino_status() -> None:
    vm = _vm()

    _runtime(vm).on_detector_state_changed(StateCategory.DETECTOR, "use_openvino", False, True)

    assert vm.ui_event_bus.published == [
        Event(
            UIEvents.UI_UPDATE_OPENVINO_CHECKBOX,
            payloads.UIUpdateOpenVinoCheckboxPayload(is_checked=True),
        )
    ]
    assert vm.ui_state_controller.names() == ["update_openvino_status"]


def test_detector_state_change_ignores_other_keys_and_a_missing_bus() -> None:
    vm = _vm()
    runtime = _runtime(vm)
    runtime.on_detector_state_changed(StateCategory.DETECTOR, "detector_initialized", 0, 1)
    assert vm.ui_event_bus.published == []

    vm.ui_event_bus = None
    runtime.on_detector_state_changed(StateCategory.DETECTOR, "use_openvino", 0, 1)
    assert vm.ui_state_controller.calls == []


def test_processing_start_navigates_to_the_analysis_view() -> None:
    vm = _vm()

    _runtime(vm).on_processing_state_changed(StateCategory.PROCESSING, "is_processing", False, True)

    assert vm.ui_event_bus.published == [Event(UIEvents.UI_NAVIGATE_TO_ANALYSIS_VIEW)]


def test_processing_start_without_a_bus_publishes_nothing() -> None:
    vm = _vm(ui_event_bus=None)

    _runtime(vm).on_processing_state_changed(StateCategory.PROCESSING, "is_processing", False, True)

    assert vm.ui_state_controller.calls == []


def test_processing_end_does_not_navigate() -> None:
    vm = _vm()

    _runtime(vm).on_processing_state_changed(StateCategory.PROCESSING, "is_processing", True, False)

    assert vm.ui_event_bus.published == []


def test_cancel_requested_shows_feedback_only_when_set() -> None:
    vm = _vm()
    runtime = _runtime(vm)

    runtime.on_processing_state_changed(StateCategory.PROCESSING, "cancel_requested", True, False)
    assert vm.ui_state_controller.calls == []

    runtime.on_processing_state_changed(StateCategory.PROCESSING, "cancel_requested", False, True)
    assert vm.ui_state_controller.names() == ["_show_cancel_feedback"]


# ----------------------------------------------------------- project manager replaced


class _Replaceable:
    """A service with the hook; records the payload it was handed."""

    def __init__(self) -> None:
        self.seen: list[Any] = []

    def _on_project_manager_replaced(self, data: Any) -> None:
        self.seen.append(data)


class _Exploding:
    def _on_project_manager_replaced(self, data: Any) -> None:
        raise RuntimeError("boom")


class _ReadOnlyManager:
    """Assigning ``project_manager`` raises, as a property without a setter does."""

    @property
    def project_manager(self) -> Any:
        return None


def _replacement_vm(**overrides: Any) -> SimpleNamespace:
    base = {
        "project_manager": "old",
        "project_workflow_service": None,
        "detector_service": None,
        "video_processing_service": None,
        "recording_service": None,
        "processing_coordinator": None,
    }
    base.update(overrides)
    return _vm(**base)


def test_manager_replaced_without_a_new_manager_changes_nothing() -> None:
    vm = _replacement_vm()

    _runtime(vm).handle_project_manager_replaced(
        payloads.ProjectManagerReplacedPayload(new_manager=None)
    )

    assert vm.project_manager == "old"


def test_manager_replaced_rebinds_the_vm_adapter_and_sub_view_models() -> None:
    adapter = SimpleNamespace(project_manager="old")
    project_vm = SimpleNamespace(project_manager="old")
    analysis_vm = SimpleNamespace(project_manager="old")
    no_attr_vm = SimpleNamespace()
    vm = _replacement_vm(
        project_workflow_adapter=adapter, project_vm=project_vm, analysis_vm=analysis_vm
    )
    new = object()

    _runtime(vm).handle_project_manager_replaced(
        payloads.ProjectManagerReplacedPayload(new_manager=new)
    )

    assert vm.project_manager is new
    assert adapter.project_manager is new
    assert project_vm.project_manager is new
    assert analysis_vm.project_manager is new
    assert not hasattr(no_attr_vm, "project_manager")


def test_manager_replaced_uses_the_hook_when_present_else_assigns_the_attribute() -> None:
    hooked = _Replaceable()
    plain = SimpleNamespace(project_manager="old")
    vm = _replacement_vm(detector_service=hooked, video_processing_service=plain)
    payload = payloads.ProjectManagerReplacedPayload(new_manager="new")

    _runtime(vm).handle_project_manager_replaced(payload)

    assert hooked.seen == [payload]
    assert plain.project_manager == "new"


def test_manager_replaced_isolates_a_failing_hook_from_the_next_service() -> None:
    later = _Replaceable()
    vm = _replacement_vm(detector_service=_Exploding(), recording_service=later)

    _runtime(vm).handle_project_manager_replaced(
        payloads.ProjectManagerReplacedPayload(new_manager="new")
    )

    assert len(later.seen) == 1


def test_manager_replaced_survives_read_only_attributes() -> None:
    later = _Replaceable()
    vm = _replacement_vm(
        project_vm=_ReadOnlyManager(),
        detector_service=_ReadOnlyManager(),
        recording_service=later,
    )

    _runtime(vm).handle_project_manager_replaced(
        payloads.ProjectManagerReplacedPayload(new_manager="new")
    )

    assert len(later.seen) == 1


# ------------------------------------------------------------------------ join_threads


class _FakeThread:
    def __init__(self, alive: bool) -> None:
        self.alive = alive
        self.joined_with: list[float | None] = []

    def is_alive(self) -> bool:
        return self.alive

    def join(self, timeout: float | None = None) -> None:
        self.joined_with.append(timeout)


class _FakeCamera:
    def __init__(self, result: Any = True, raises: bool = False) -> None:
        self.result = result
        self.raises = raises
        self.released = 0

    def release(self) -> Any:
        self.released += 1
        if self.raises:
            raise OSError("device busy")
        return self.result


def _shutdown_vm(**overrides: Any) -> SimpleNamespace:
    base: dict[str, Any] = {
        "program_exit_event": threading.Event(),
        "processing_coordinator": None,
        "processing_thread": None,
        "hardware_vm": _hardware_without_camera(),
    }
    base.update(overrides)
    return _vm(**base)


def _hardware_without_camera() -> Spy:
    hardware = Spy()
    hardware.camera = None  # a Spy would otherwise invent a callable "camera"
    return hardware


def test_join_threads_signals_exit_cancels_analysis_and_shuts_arduino() -> None:
    vm = _shutdown_vm()

    _runtime(vm).join_threads()

    assert vm.program_exit_event.is_set()
    assert vm.analysis_vm.names() == ["cancel_current_analysis"]
    assert vm.hardware_vm.names() == ["_shutdown_arduino_manager"]
    assert vm.ui_event_bus.published == []


def test_join_threads_joins_only_the_threads_that_are_alive() -> None:
    coordinator_thread = _FakeThread(alive=True)
    legacy_thread = _FakeThread(alive=True)
    capture_thread = _FakeThread(alive=True)
    vm = _shutdown_vm(
        processing_coordinator=SimpleNamespace(processing_thread=coordinator_thread),
        processing_thread=legacy_thread,
        capture_thread=capture_thread,
    )

    _runtime(vm).join_threads()

    assert coordinator_thread.joined_with == [5.0]
    assert legacy_thread.joined_with == [5.0]
    assert capture_thread.joined_with == [5.0]


def test_join_threads_skips_dead_threads() -> None:
    dead = [_FakeThread(alive=False) for _ in range(3)]
    vm = _shutdown_vm(
        processing_coordinator=SimpleNamespace(processing_thread=dead[0]),
        processing_thread=dead[1],
        capture_thread=dead[2],
    )

    _runtime(vm).join_threads()

    assert [t.joined_with for t in dead] == [[], [], []]


def test_join_threads_releases_the_camera_quietly_on_success() -> None:
    camera = _FakeCamera(result=True)
    vm = _shutdown_vm(hardware_vm=Spy())
    vm.hardware_vm.camera = camera

    _runtime(vm).join_threads()

    assert camera.released == 1
    assert vm.ui_event_bus.published == []


def test_join_threads_falls_back_to_the_view_model_camera() -> None:
    camera = _FakeCamera(result=True)
    vm = _shutdown_vm(camera=camera)

    _runtime(vm).join_threads()

    assert camera.released == 1


def test_join_threads_reports_a_zombie_camera_when_release_returns_false() -> None:
    vm = _shutdown_vm()
    vm.hardware_vm.camera = _FakeCamera(result=False)

    _runtime(vm).join_threads()

    (event,) = vm.ui_event_bus.published
    assert event.type is UIEvents.ERROR_OCCURRED
    assert event.data == payloads.ErrorOccurredPayload(
        title="Critical Error",
        message="The camera thread did not shut down correctly. The application will close.",
    )
    assert vm.hardware_vm.names() == ["_shutdown_arduino_manager"]  # still shuts down


def test_join_threads_reports_a_zombie_camera_when_release_raises() -> None:
    vm = _shutdown_vm()
    vm.hardware_vm.camera = _FakeCamera(raises=True)

    _runtime(vm).join_threads()

    assert [e.type for e in vm.ui_event_bus.published] == [UIEvents.ERROR_OCCURRED]
    assert vm.hardware_vm.names() == ["_shutdown_arduino_manager"]


def test_join_threads_zombie_camera_without_a_bus_does_not_raise() -> None:
    vm = _shutdown_vm(ui_event_bus=None)
    vm.hardware_vm.camera = _FakeCamera(result=False)

    _runtime(vm).join_threads()

    assert vm.hardware_vm.names() == ["_shutdown_arduino_manager"]
