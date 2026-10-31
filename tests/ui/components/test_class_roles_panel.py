"""Tests for the class-role editor (``ui/components/class_roles_panel.py``, ADR-009).

Two layers, two markers:

- Building and validating the map, pre-filling it from the resolver, detecting a
  project map recorded for another weight, persisting each scope (with the undo
  on a failed project save) and the ``CLASS_ROLES_CHANGED`` announcement are
  plain Python. They run in the fast suite and are what the mutation catalogue
  checks.
- The Tk panel (``@pytest.mark.gui``) only shuttles widget values into that model.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from zebtrack.core.detection.class_roles import (
    ClassRole,
    ClassRoleSource,
    resolve_class_role_map,
)
from zebtrack.core.services.weight_manager import WeightManager
from zebtrack.settings import load_settings
from zebtrack.ui import payloads
from zebtrack.ui.components.class_roles_panel import (
    OVERRIDES_KEY,
    PROJECT_ROLES_KEY,
    PROJECT_SHA_KEY,
    ROLE_ORDER,
    ClassNamesCache,
    ClassRolesDialog,
    ClassRolesEditor,
    ClassRolesPanel,
    ClassRolesSaveError,
    ClassRolesScope,
    ConflictingRolesError,
    NoSubjectClassError,
    ProjectClassRolesContext,
    RoleMapError,
    RoleRow,
    SeveralArenaClassesError,
    TargetWeight,
    build_role_mapping,
    build_view,
    coerce_class_names,
    model_service_names_loader,
    named_target_weight,
    overlay_roles_for,
    project_roles_are_stale,
    project_target_weight,
    role_from_label,
    role_labels,
    role_map_error_message,
    rows_from_role_map,
    source_labels,
    store_project_roles,
    store_weight_roles,
    stored_project_roles,
)
from zebtrack.ui.event_bus_v2 import EventBusV2, UIEvents

BARNES_NAMES = {0: "arena", 1: "experimenter", 2: "rat", 3: "start_box"}
BARNES_ROLES = {
    "arena": "arena",
    "experimenter": "context",
    "rat": "subject",
    "start_box": "context",
}
ZEBRA_NAMES = {0: "aqua", 1: "zebrafish"}


def _rows(roles: dict[int, ClassRole], names: dict[int, str] = BARNES_NAMES) -> list[RoleRow]:
    return [RoleRow(class_id=cid, name=names[cid], role=roles[cid]) for cid in sorted(names)]


def _barnes_rows() -> list[RoleRow]:
    return _rows(
        {
            0: ClassRole.ARENA,
            1: ClassRole.CONTEXT,
            2: ClassRole.SUBJECT,
            3: ClassRole.CONTEXT,
        }
    )


def _settings(*, method: str = "det") -> Any:
    settings = load_settings()
    settings.model_selection.animal_method = method  # type: ignore[assignment]
    settings.model_selection.use_openvino = False
    settings.behavioral_analysis.aquarium_perspective = "top_down"  # type: ignore[assignment]
    return settings


def _entry(path: Path, *, default: bool, **extra: Any) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "path": str(path),
        "type": "det",
        "target": "aquarium",
        "perspective": "top_down",
        "is_default": default,
        "is_default_det": default,
        "is_default_seg_aquarium": False,
        "is_default_seg_zebrafish": False,
        "is_default_det_aquarium": default,
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
    }
    for key, path in files.items():
        path.write_bytes(f"weight {key}".encode())
    wm = WeightManager(settings_obj=_settings(), config_dir=tmp_path, weights_dir=weights)
    wm.weights = {
        files["zebra"].name: _entry(files["zebra"], default=True),
        files["rat"].name: _entry(files["rat"], default=False),
    }
    wm.save_weights()
    return wm, files


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _rat_project(files: dict[str, Path], **overrides: Any) -> dict[str, Any]:
    return {
        "model_overrides": {
            "slot_weights": {"det:zebrafish": files["rat"].name},
            **overrides,
        }
    }


def _project_manager(project_data: dict[str, Any] | None, *, path: str | None = "proj") -> Any:
    return SimpleNamespace(project_data=project_data, project_path=path, save_project=MagicMock())


def _recording_bus() -> tuple[EventBusV2, list[Any]]:
    bus = EventBusV2()
    seen: list[Any] = []
    bus.subscribe(UIEvents.CLASS_ROLES_CHANGED, seen.append)
    return bus, seen


# ---------------------------------------------------------------------------
# Labels
# ---------------------------------------------------------------------------


class TestLabels:
    def test_every_role_has_a_label_and_tokens_are_the_contract(self) -> None:
        labels = role_labels()
        assert set(labels) == set(ClassRole)
        assert [role.value for role in ROLE_ORDER] == ["subject", "arena", "context", "ignored"]
        assert labels[ClassRole.SUBJECT] == "Subject (tracked animal)"

    def test_label_round_trips_to_the_token(self) -> None:
        for role, label in role_labels().items():
            assert role_from_label(label) is role
        assert role_from_label("subject") is None
        assert role_from_label("") is None

    def test_every_source_is_described(self) -> None:
        assert set(source_labels()) == set(ClassRoleSource)
        assert source_labels()[ClassRoleSource.PROJECT] == "set in this project"


# ---------------------------------------------------------------------------
# Rows → mapping (validation)
# ---------------------------------------------------------------------------


class TestBuildRoleMapping:
    def test_barnes_rows_become_the_stored_mapping(self) -> None:
        assert build_role_mapping(_barnes_rows()) == BARNES_ROLES

    def test_names_are_normalised(self) -> None:
        rows = [
            RoleRow(0, "Open Field", ClassRole.ARENA),
            RoleRow(1, "Lab Rat", ClassRole.SUBJECT),
        ]
        assert build_role_mapping(rows) == {"open_field": "arena", "lab_rat": "subject"}

    def test_no_subject_is_refused(self) -> None:
        rows = _rows(
            {0: ClassRole.ARENA, 1: ClassRole.CONTEXT, 2: ClassRole.IGNORED, 3: ClassRole.CONTEXT}
        )
        with pytest.raises(NoSubjectClassError):
            build_role_mapping(rows)

    def test_two_arena_names_are_refused_and_named(self) -> None:
        rows = _rows(
            {0: ClassRole.ARENA, 1: ClassRole.CONTEXT, 2: ClassRole.SUBJECT, 3: ClassRole.ARENA}
        )
        with pytest.raises(SeveralArenaClassesError) as caught:
            build_role_mapping(rows)
        assert caught.value.names == ("arena", "start_box")

    def test_one_arena_and_several_subjects_are_fine(self) -> None:
        rows = _rows(
            {0: ClassRole.ARENA, 1: ClassRole.SUBJECT, 2: ClassRole.SUBJECT, 3: ClassRole.IGNORED}
        )
        assert build_role_mapping(rows) == {
            "arena": "arena",
            "experimenter": "subject",
            "rat": "subject",
            "start_box": "ignored",
        }

    def test_no_arena_is_fine(self) -> None:
        rows = [RoleRow(0, "rat", ClassRole.SUBJECT), RoleRow(1, "box", ClassRole.CONTEXT)]
        assert build_role_mapping(rows) == {"rat": "subject", "box": "context"}

    def test_same_name_same_role_is_one_entry(self) -> None:
        rows = [RoleRow(0, "rat", ClassRole.SUBJECT), RoleRow(1, "Rat", ClassRole.SUBJECT)]
        assert build_role_mapping(rows) == {"rat": "subject"}

    def test_same_name_two_roles_is_refused(self) -> None:
        rows = [RoleRow(0, "rat", ClassRole.SUBJECT), RoleRow(1, "Rat", ClassRole.CONTEXT)]
        with pytest.raises(ConflictingRolesError) as caught:
            build_role_mapping(rows)
        assert caught.value.name == "Rat"

    def test_blank_names_are_skipped(self) -> None:
        rows = [RoleRow(0, "  ", ClassRole.ARENA), RoleRow(1, "rat", ClassRole.SUBJECT)]
        assert build_role_mapping(rows) == {"rat": "subject"}


class TestErrorMessages:
    def test_message_comes_from_the_type_not_the_text(self) -> None:
        assert role_map_error_message(NoSubjectClassError("whatever")) == (
            "Choose at least one class as the subject (the animal to track)."
        )
        assert role_map_error_message(SeveralArenaClassesError(["a", "b"])) == (
            "Only one class can be the arena; 'a', 'b' are all marked as arena."
        )
        assert role_map_error_message(ConflictingRolesError("Rat")) == (
            "Classes named 'Rat' must share one role: roles are stored by class name."
        )
        assert role_map_error_message(RoleMapError("no subject")) == (
            "The class roles are not valid."
        )


# ---------------------------------------------------------------------------
# Pre-fill
# ---------------------------------------------------------------------------


class TestRowsFromRoleMap:
    def test_explicit_map_rows(self) -> None:
        role_map = resolve_class_role_map(BARNES_NAMES, weight_entry={"class_roles": BARNES_ROLES})
        assert rows_from_role_map(role_map) == _barnes_rows()

    def test_positional_ids_show_what_the_detector_does(self) -> None:
        role_map = resolve_class_role_map({0: "foo", 1: "bar"})
        rows = rows_from_role_map(role_map)
        assert [row.role for row in rows] == [ClassRole.ARENA, ClassRole.SUBJECT]

    def test_by_name_only_drops_the_positional_guess(self) -> None:
        role_map = resolve_class_role_map({0: "foo", 1: "bar"})
        rows = rows_from_role_map(role_map, by_name_only=True)
        assert [row.role for row in rows] == [ClassRole.IGNORED, ClassRole.IGNORED]

    def test_second_alias_animal_is_ignored_like_the_detector(self) -> None:
        role_map = resolve_class_role_map({0: "aqua", 1: "fish", 2: "rat"})
        assert [row.role for row in rows_from_role_map(role_map)] == [
            ClassRole.ARENA,
            ClassRole.SUBJECT,
            ClassRole.IGNORED,
        ]


class TestCoerceClassNames:
    def test_shapes(self) -> None:
        assert coerce_class_names(["a", "b"]) == {0: "a", 1: "b"}
        assert coerce_class_names({"0": "a", 2: "c", "x": "d", 3: 4}) == {0: "a", 2: "c"}
        assert coerce_class_names(None) == {}
        assert coerce_class_names("abc") == {}


class TestOverlayRoles:
    def test_explicit_map_gives_roles_by_id(self) -> None:
        role_map = resolve_class_role_map(BARNES_NAMES, weight_entry={"class_roles": BARNES_ROLES})
        assert overlay_roles_for(role_map) == {
            0: "arena",
            1: "context",
            2: "subject",
            3: "context",
        }

    def test_alias_map_keeps_the_legacy_overlay(self) -> None:
        assert overlay_roles_for(resolve_class_role_map(ZEBRA_NAMES)) is None
        assert overlay_roles_for(None) is None


# ---------------------------------------------------------------------------
# Stale project map
# ---------------------------------------------------------------------------


class TestStaleProjectRoles:
    def _data(self, roles: Any, sha: Any) -> dict[str, Any]:
        return {OVERRIDES_KEY: {PROJECT_ROLES_KEY: roles, PROJECT_SHA_KEY: sha}}

    def test_no_project_map_is_never_stale(self) -> None:
        assert project_roles_are_stale({}, "abc") is False
        assert project_roles_are_stale(None, "abc") is False
        assert project_roles_are_stale(self._data(None, "abc"), "abc") is False

    def test_invalid_map_is_not_reported_as_stale(self) -> None:
        assert project_roles_are_stale(self._data({"rat": "boss"}, "old"), "new") is False

    def test_matching_sha_is_current(self) -> None:
        assert project_roles_are_stale(self._data(BARNES_ROLES, "abc"), "abc") is False

    def test_other_sha_is_stale(self) -> None:
        assert project_roles_are_stale(self._data(BARNES_ROLES, "old"), "new") is True

    def test_unknown_effective_sha_is_stale(self) -> None:
        assert project_roles_are_stale(self._data(BARNES_ROLES, "abc"), "") is True

    def test_stored_roles_are_parsed(self) -> None:
        roles, sha = stored_project_roles(self._data(BARNES_ROLES, "abc"))
        assert roles is not None and roles["rat"] is ClassRole.SUBJECT
        assert sha == "abc"
        assert stored_project_roles(self._data(BARNES_ROLES, 7)) == (roles, None)


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


class TestStoreProjectRoles:
    def test_writes_map_and_sha_then_saves(self) -> None:
        data: dict[str, Any] = {OVERRIDES_KEY: {"active_weight": None}}
        manager = _project_manager(data)
        assert store_project_roles(manager, BARNES_ROLES, "abc") is True
        assert data[OVERRIDES_KEY] == {
            "active_weight": None,
            PROJECT_ROLES_KEY: BARNES_ROLES,
            PROJECT_SHA_KEY: "abc",
        }
        manager.save_project.assert_called_once_with()

    def test_clearing_sets_both_keys_to_none(self) -> None:
        data = {OVERRIDES_KEY: {PROJECT_ROLES_KEY: BARNES_ROLES, PROJECT_SHA_KEY: "abc"}}
        store_project_roles(_project_manager(data), None, "abc")
        assert data[OVERRIDES_KEY] == {PROJECT_ROLES_KEY: None, PROJECT_SHA_KEY: None}

    def test_missing_overrides_block_is_created(self) -> None:
        data: dict[str, Any] = {}
        store_project_roles(_project_manager(data), BARNES_ROLES, "abc")
        assert data[OVERRIDES_KEY][PROJECT_SHA_KEY] == "abc"

    def test_project_without_path_keeps_the_edit_in_memory(self) -> None:
        data: dict[str, Any] = {}
        manager = _project_manager(data, path=None)
        assert store_project_roles(manager, BARNES_ROLES, "abc") is False
        assert data[OVERRIDES_KEY][PROJECT_ROLES_KEY] == BARNES_ROLES
        manager.save_project.assert_not_called()

    def test_failed_save_restores_previous_values(self) -> None:
        previous = {"rat": "subject"}
        data = {OVERRIDES_KEY: {PROJECT_ROLES_KEY: previous, PROJECT_SHA_KEY: "old", "x": 1}}
        manager = _project_manager(data)
        manager.save_project.side_effect = OSError("disk full")
        with pytest.raises(ClassRolesSaveError):
            store_project_roles(manager, BARNES_ROLES, "new")
        assert data == {
            OVERRIDES_KEY: {PROJECT_ROLES_KEY: previous, PROJECT_SHA_KEY: "old", "x": 1}
        }

    def test_failed_save_removes_keys_that_did_not_exist(self) -> None:
        data: dict[str, Any] = {OVERRIDES_KEY: {"x": 1}}
        manager = _project_manager(data)
        manager.save_project.side_effect = OSError("disk full")
        with pytest.raises(ClassRolesSaveError):
            store_project_roles(manager, BARNES_ROLES, "new")
        assert data == {OVERRIDES_KEY: {"x": 1}}

    def test_failed_save_removes_a_created_block(self) -> None:
        data: dict[str, Any] = {"name": "p"}
        manager = _project_manager(data)
        manager.save_project.side_effect = OSError("disk full")
        with pytest.raises(ClassRolesSaveError):
            store_project_roles(manager, BARNES_ROLES, "new")
        assert data == {"name": "p"}

    def test_no_project_is_an_error(self) -> None:
        with pytest.raises(ClassRolesSaveError):
            store_project_roles(_project_manager(None), BARNES_ROLES, "abc")


class TestStoreWeightRoles:
    def test_roles_reach_weights_config_json(self, registry) -> None:
        wm, files = registry
        store_weight_roles(wm, files["rat"].name, BARNES_ROLES)
        stored = json.loads(Path(wm.config_path).read_text(encoding="utf-8"))
        assert stored[files["rat"].name]["class_roles"] == BARNES_ROLES

    def test_none_removes_the_key(self, registry) -> None:
        wm, files = registry
        store_weight_roles(wm, files["rat"].name, BARNES_ROLES)
        store_weight_roles(wm, files["rat"].name, None)
        assert "class_roles" not in wm.weights[files["rat"].name]

    def test_unknown_weight_is_an_error(self, registry) -> None:
        wm, _files = registry
        with pytest.raises(ClassRolesSaveError):
            store_weight_roles(wm, "nope.pt", BARNES_ROLES)

    def test_invalid_map_refused_by_the_registry_is_an_error(self, registry) -> None:
        wm, files = registry
        with pytest.raises(ClassRolesSaveError):
            store_weight_roles(wm, files["rat"].name, {"rat": "boss"})
        assert "class_roles" not in wm.weights[files["rat"].name]

    def test_failed_save_restores_the_entry(self, registry, monkeypatch) -> None:
        wm, files = registry
        name = files["rat"].name
        wm.weights[name]["class_roles"] = {"rat": "subject"}

        def _boom() -> None:
            raise OSError("read-only")

        monkeypatch.setattr(wm, "save_weights", _boom)
        with pytest.raises(ClassRolesSaveError):
            store_weight_roles(wm, name, BARNES_ROLES)
        assert wm.weights[name]["class_roles"] == {"rat": "subject"}

    def test_failed_save_removes_a_new_key(self, registry, monkeypatch) -> None:
        wm, files = registry
        name = files["rat"].name

        def _boom() -> None:
            raise OSError("read-only")

        monkeypatch.setattr(wm, "save_weights", _boom)
        with pytest.raises(ClassRolesSaveError):
            store_weight_roles(wm, name, BARNES_ROLES)
        assert "class_roles" not in wm.weights[name]


# ---------------------------------------------------------------------------
# Target weight
# ---------------------------------------------------------------------------


class TestTargetWeight:
    def test_named_weight(self, registry) -> None:
        wm, files = registry
        target = named_target_weight(wm, files["rat"].name)
        assert target.name == files["rat"].name
        assert target.sha256 == _sha(files["rat"])
        assert target.details is wm.weights[files["rat"].name]
        assert target.cache_key == (files["rat"].name, _sha(files["rat"]))

    def test_no_name_is_no_target(self, registry) -> None:
        wm, _files = registry
        assert named_target_weight(wm, None) == TargetWeight(name=None)
        assert named_target_weight(None, "x") == TargetWeight(name=None)
        assert TargetWeight(name="x").cache_key is None

    def test_project_target_is_the_worker_weight(self, registry) -> None:
        wm, files = registry
        target = project_target_weight(wm, _settings(), _rat_project(files))
        assert target.name == files["rat"].name
        assert target.sha256 == _sha(files["rat"])

    def test_project_target_without_registry(self) -> None:
        assert project_target_weight(None, None, {}) == TargetWeight(name=None)


# ---------------------------------------------------------------------------
# View (resolution for display)
# ---------------------------------------------------------------------------


class TestBuildView:
    def test_project_map_for_this_weight_wins(self) -> None:
        target = TargetWeight(name="rat.pt", sha256="abc", details={})
        project = {OVERRIDES_KEY: {PROJECT_ROLES_KEY: BARNES_ROLES, PROJECT_SHA_KEY: "abc"}}
        view = build_view(
            BARNES_NAMES, scope=ClassRolesScope.PROJECT, target=target, project_data=project
        )
        assert view.role_map is not None and view.role_map.source is ClassRoleSource.PROJECT
        assert list(view.rows) == _barnes_rows()
        assert view.stale_project_roles is False
        assert view.unresolved is False

    def test_weight_scope_ignores_the_project_map(self) -> None:
        target = TargetWeight(name="rat.pt", sha256="abc", details={})
        project = {OVERRIDES_KEY: {PROJECT_ROLES_KEY: BARNES_ROLES, PROJECT_SHA_KEY: "abc"}}
        view = build_view(
            BARNES_NAMES, scope=ClassRolesScope.WEIGHT, target=target, project_data=project
        )
        assert view.role_map is not None and view.role_map.source is ClassRoleSource.ALIASES
        assert view.stale_project_roles is False

    def test_project_map_for_another_weight_is_stale_and_ignored(self) -> None:
        target = TargetWeight(name="rat.pt", sha256="new", details={"class_roles": BARNES_ROLES})
        project = {OVERRIDES_KEY: {PROJECT_ROLES_KEY: {"rat": "subject"}, PROJECT_SHA_KEY: "old"}}
        view = build_view(
            BARNES_NAMES, scope=ClassRolesScope.PROJECT, target=target, project_data=project
        )
        assert view.stale_project_roles is True
        assert view.role_map is not None and view.role_map.source is ClassRoleSource.WEIGHT

    def test_unresolved_weight_is_flagged_without_a_positional_subject(self) -> None:
        names = {0: "car", 1: "bicycle", 2: "person"}
        view = build_view(names, scope=ClassRolesScope.WEIGHT, target=TargetWeight(name="coco.pt"))
        assert view.unresolved is True
        assert all(row.role is not ClassRole.SUBJECT for row in view.rows)

    def test_resolved_weight_is_not_flagged(self) -> None:
        view = build_view(
            ZEBRA_NAMES, scope=ClassRolesScope.WEIGHT, target=TargetWeight(name="z.pt")
        )
        assert view.unresolved is False
        assert [row.role for row in view.rows] == [ClassRole.ARENA, ClassRole.SUBJECT]

    def test_no_names_means_no_map(self) -> None:
        target = TargetWeight(name="rat.pt", sha256="new")
        project = {OVERRIDES_KEY: {PROJECT_ROLES_KEY: BARNES_ROLES, PROJECT_SHA_KEY: "old"}}
        view = build_view({}, scope=ClassRolesScope.PROJECT, target=target, project_data=project)
        assert view.role_map is None and view.rows == ()
        assert view.stale_project_roles is True


# ---------------------------------------------------------------------------
# Editor (both scopes) and the event
# ---------------------------------------------------------------------------


class TestEditorProjectScope:
    def _editor(self, registry, data: dict[str, Any], bus: Any = None) -> ClassRolesEditor:
        wm, _files = registry
        return ClassRolesEditor(
            scope=ClassRolesScope.PROJECT,
            weight_manager=wm,
            project_manager=_project_manager(data),
            settings_obj=_settings(),
            event_bus=bus,
        )

    def test_save_records_the_effective_weight_sha_and_announces(self, registry) -> None:
        _wm, files = registry
        data = _rat_project(files)
        bus, seen = _recording_bus()
        editor = self._editor(registry, data, bus)
        editor.view(BARNES_NAMES)

        view = editor.save(_barnes_rows())

        overrides = data[OVERRIDES_KEY]
        assert overrides[PROJECT_ROLES_KEY] == BARNES_ROLES
        assert overrides[PROJECT_SHA_KEY] == _sha(files["rat"])
        assert view.role_map is not None and view.role_map.source is ClassRoleSource.PROJECT
        assert seen == [
            payloads.ClassRolesChangedPayload(
                scope="project",
                weight_name=files["rat"].name,
                weight_sha256=_sha(files["rat"]),
                class_roles=BARNES_ROLES,
                source="project",
            )
        ]

    def test_invalid_rows_store_nothing_and_announce_nothing(self, registry) -> None:
        _wm, files = registry
        data = _rat_project(files)
        bus, seen = _recording_bus()
        editor = self._editor(registry, data, bus)
        editor.view(BARNES_NAMES)
        rows = _rows(
            {0: ClassRole.ARENA, 1: ClassRole.CONTEXT, 2: ClassRole.IGNORED, 3: ClassRole.CONTEXT}
        )
        with pytest.raises(NoSubjectClassError):
            editor.save(rows)
        assert PROJECT_ROLES_KEY not in data[OVERRIDES_KEY]
        assert seen == []

    def test_restore_automatic_clears_and_announces_none(self, registry) -> None:
        _wm, files = registry
        data = _rat_project(
            files,
            **{PROJECT_ROLES_KEY: BARNES_ROLES, PROJECT_SHA_KEY: _sha(files["rat"])},
        )
        bus, seen = _recording_bus()
        editor = self._editor(registry, data, bus)
        assert editor.view(BARNES_NAMES).role_map.source is ClassRoleSource.PROJECT  # type: ignore[union-attr]

        view = editor.restore_automatic()

        assert data[OVERRIDES_KEY][PROJECT_ROLES_KEY] is None
        assert data[OVERRIDES_KEY][PROJECT_SHA_KEY] is None
        assert view.role_map is not None and view.role_map.source is ClassRoleSource.ALIASES
        assert len(seen) == 1
        assert seen[0].class_roles is None and seen[0].source == "aliases"

    def test_save_without_a_weight_is_refused(self, registry) -> None:
        editor = ClassRolesEditor(scope=ClassRolesScope.WEIGHT, weight_manager=registry[0])
        with pytest.raises(ClassRolesSaveError):
            editor.save(_barnes_rows())

    def test_failed_project_save_announces_nothing(self, registry) -> None:
        _wm, files = registry
        data = _rat_project(files)
        bus, seen = _recording_bus()
        editor = self._editor(registry, data, bus)
        editor.project_manager.save_project.side_effect = OSError("disk full")
        editor.view(BARNES_NAMES)
        with pytest.raises(ClassRolesSaveError):
            editor.save(_barnes_rows())
        assert seen == []
        assert PROJECT_ROLES_KEY not in data[OVERRIDES_KEY]


class TestEditorWeightScope:
    def test_save_writes_the_registry_and_announces(self, registry) -> None:
        wm, files = registry
        bus, seen = _recording_bus()
        editor = ClassRolesEditor(
            scope=ClassRolesScope.WEIGHT,
            weight_manager=wm,
            event_bus=bus,
            weight_name=files["rat"].name,
        )
        editor.view(BARNES_NAMES)
        view = editor.save(_barnes_rows())
        assert wm.weights[files["rat"].name]["class_roles"] == BARNES_ROLES
        assert view.role_map is not None and view.role_map.source is ClassRoleSource.WEIGHT
        assert seen[0].scope == "weight" and seen[0].source == "weight"
        assert seen[0].weight_name == files["rat"].name

    def test_restore_automatic_falls_back_to_aliases(self, registry) -> None:
        wm, files = registry
        wm.weights[files["rat"].name]["class_roles"] = BARNES_ROLES
        editor = ClassRolesEditor(
            scope=ClassRolesScope.WEIGHT, weight_manager=wm, weight_name=files["rat"].name
        )
        assert editor.view(BARNES_NAMES).role_map.source is ClassRoleSource.WEIGHT  # type: ignore[union-attr]
        view = editor.restore_automatic()
        assert "class_roles" not in wm.weights[files["rat"].name]
        assert view.role_map is not None and view.role_map.source is ClassRoleSource.ALIASES


# ---------------------------------------------------------------------------
# Class names: cache and loader
# ---------------------------------------------------------------------------


class TestClassNamesCache:
    def test_put_and_get_by_weight_and_sha(self) -> None:
        cache = ClassNamesCache()
        target = TargetWeight(name="rat.pt", sha256="abc")
        assert cache.get(target) is None
        cache.put(target, BARNES_NAMES)
        assert cache.get(target) == BARNES_NAMES
        assert cache.get(TargetWeight(name="rat.pt", sha256="other")) is None

    def test_empty_names_and_unhashed_weights_are_not_cached(self) -> None:
        cache = ClassNamesCache()
        cache.put(TargetWeight(name="rat.pt", sha256="abc"), {})
        cache.put(TargetWeight(name="rat.pt"), BARNES_NAMES)
        assert cache.get(TargetWeight(name="rat.pt", sha256="abc")) is None
        assert cache.get(TargetWeight(name="rat.pt")) is None

    def test_get_returns_a_copy(self) -> None:
        cache = ClassNamesCache()
        target = TargetWeight(name="rat.pt", sha256="abc")
        cache.put(target, BARNES_NAMES)
        copy = cache.get(target)
        assert copy is not None
        copy[9] = "x"
        assert cache.get(target) == BARNES_NAMES


class TestModelServiceLoader:
    def test_reads_class_names(self) -> None:
        service = MagicMock()
        service.inspect_model.return_value = {"class_names": {"0": "arena", 1: "rat"}}
        assert model_service_names_loader(service)("rat.pt") == {0: "arena", 1: "rat"}
        service.inspect_model.assert_called_once_with("rat.pt")

    @pytest.mark.parametrize("error", [ValueError("unknown"), ImportError("no ultralytics")])
    def test_known_failures_mean_no_names(self, error: Exception) -> None:
        service = MagicMock()
        service.inspect_model.side_effect = error
        assert model_service_names_loader(service)("rat.pt") == {}


# ---------------------------------------------------------------------------
# Project context (zone tab)
# ---------------------------------------------------------------------------


class TestProjectClassRolesContext:
    def _context(self, registry, data: dict[str, Any], loader: Any, **kwargs: Any) -> Any:
        wm, _files = registry
        return ProjectClassRolesContext(
            weight_manager=wm,
            settings_obj=_settings(),
            project_manager_getter=lambda: SimpleNamespace(project_data=data),
            names_loader=loader,
            schedule=lambda fn: fn(),
            cache=ClassNamesCache(),
            background=False,
            **kwargs,
        )

    def test_explicit_project_map_colours_the_overlay(self, registry) -> None:
        _wm, files = registry
        data = _rat_project(
            files, **{PROJECT_ROLES_KEY: BARNES_ROLES, PROJECT_SHA_KEY: _sha(files["rat"])}
        )
        changes: list[int] = []
        context = self._context(
            registry, data, lambda _n: BARNES_NAMES, on_change=lambda: changes.append(1)
        )
        context.refresh()
        assert context.class_names() == ["arena", "experimenter", "rat", "start_box"]
        assert context.class_names_by_id() == BARNES_NAMES
        assert context.overlay_roles() == {0: "arena", 1: "context", 2: "subject", 3: "context"}
        assert changes == [1]

    def test_alias_resolution_keeps_legacy_colours(self, registry) -> None:
        _wm, files = registry
        context = self._context(registry, _rat_project(files), lambda _n: ZEBRA_NAMES)
        context.refresh()
        assert context.class_names() == ["aqua", "zebrafish"]
        assert context.overlay_roles() is None

    def test_cached_names_do_not_reload_the_model(self, registry) -> None:
        _wm, files = registry
        loader = MagicMock(return_value=BARNES_NAMES)
        context = self._context(registry, _rat_project(files), loader)
        context.refresh()
        context.refresh()
        loader.assert_called_once_with(files["rat"].name)

    def test_loader_failure_leaves_no_names(self, registry) -> None:
        _wm, files = registry

        def _boom(_name: str) -> dict[int, str]:
            raise RuntimeError("torch exploded")

        context = self._context(registry, _rat_project(files), _boom)
        context.refresh()
        assert context.class_names() == []
        assert context.overlay_roles() is None

    def test_superseded_load_is_dropped(self, registry) -> None:
        _wm, files = registry
        scheduled: list[Any] = []
        wm = registry[0]
        context = ProjectClassRolesContext(
            weight_manager=wm,
            settings_obj=_settings(),
            project_manager_getter=lambda: SimpleNamespace(project_data=_rat_project(files)),
            names_loader=lambda _n: BARNES_NAMES,
            schedule=scheduled.append,
            cache=ClassNamesCache(),
            background=False,
        )
        context.refresh()  # load 1 → delivery queued
        context._pending = TargetWeight(name="other.pt")  # a newer refresh started
        scheduled.pop()()
        assert context.class_names() == []


# ---------------------------------------------------------------------------
# Tk panel
# ---------------------------------------------------------------------------


@pytest.mark.gui
class TestClassRolesPanel:
    def _panel(
        self, root: Any, editor: ClassRolesEditor, names: dict[int, str], **kwargs: Any
    ) -> Any:
        panel = ClassRolesPanel(
            root,
            editor=editor,
            names_loader=lambda _n: names,
            cache=ClassNamesCache(),
            background=False,
            **kwargs,
        )
        panel.pack()
        root.update()
        return panel

    def _project_editor(self, registry, data: dict[str, Any], bus: Any = None) -> Any:
        return ClassRolesEditor(
            scope=ClassRolesScope.PROJECT,
            weight_manager=registry[0],
            project_manager=_project_manager(data),
            settings_obj=_settings(),
            event_bus=bus,
        )

    def test_rows_show_id_name_and_role_label(self, tkinter_root, registry) -> None:
        _wm, files = registry
        panel = self._panel(
            tkinter_root, self._project_editor(registry, _rat_project(files)), BARNES_NAMES
        )
        tree = panel._tree
        assert [tree.item(i, "values")[1] for i in tree.get_children()] == list(
            BARNES_NAMES.values()
        )
        assert tree.item("2", "values")[2] == role_labels()[ClassRole.SUBJECT]
        assert tree.item("1", "values")[2] == role_labels()[ClassRole.IGNORED]
        assert "automatic, recognised by class name" in panel._source_label.cget("text")
        assert files["rat"].name in panel._weight_label.cget("text")

    def test_choosing_a_role_and_saving_writes_the_project(self, tkinter_root, registry) -> None:
        _wm, files = registry
        data = _rat_project(files)
        bus, seen = _recording_bus()
        panel = self._panel(tkinter_root, self._project_editor(registry, data, bus), BARNES_NAMES)

        panel._tree.selection_set(["1", "3"])
        panel.role_choice.set(role_labels()[ClassRole.CONTEXT])
        panel._on_role_chosen()
        assert panel.save() is True

        assert data[OVERRIDES_KEY][PROJECT_ROLES_KEY] == BARNES_ROLES
        assert len(seen) == 1
        assert "set in this project" in panel._source_label.cget("text")
        assert panel._status.cget("text") == "Class roles saved."

    def test_invalid_map_shows_a_friendly_message(self, tkinter_root, registry) -> None:
        _wm, files = registry
        data = _rat_project(files)
        panel = self._panel(tkinter_root, self._project_editor(registry, data), BARNES_NAMES)
        panel.set_role([2], ClassRole.CONTEXT)
        assert panel.save() is False
        assert panel._status.cget("text") == role_map_error_message(NoSubjectClassError(""))
        assert PROJECT_ROLES_KEY not in data[OVERRIDES_KEY]

    def test_role_without_selection_is_refused(self, tkinter_root, registry) -> None:
        _wm, files = registry
        panel = self._panel(
            tkinter_root, self._project_editor(registry, _rat_project(files)), BARNES_NAMES
        )
        panel.role_choice.set(role_labels()[ClassRole.ARENA])
        panel._on_role_chosen()
        assert panel._status.cget("text") == "Select one or more classes first."

    def test_selection_shows_its_common_role(self, tkinter_root, registry) -> None:
        _wm, files = registry
        panel = self._panel(
            tkinter_root, self._project_editor(registry, _rat_project(files)), BARNES_NAMES
        )
        panel._tree.selection_set(["2"])
        panel._on_select()
        assert panel.role_choice.get() == role_labels()[ClassRole.SUBJECT]
        panel._tree.selection_set(["0", "2"])
        panel._on_select()
        assert panel.role_choice.get() == ""

    def test_stale_project_map_is_warned(self, tkinter_root, registry) -> None:
        _wm, files = registry
        data = _rat_project(files, **{PROJECT_ROLES_KEY: BARNES_ROLES, PROJECT_SHA_KEY: "old"})
        panel = self._panel(tkinter_root, self._project_editor(registry, data), BARNES_NAMES)
        assert "different weight file" in panel._warning.cget("text")
        assert panel._warning.winfo_manager() == "pack"

    def test_unreadable_model_disables_editing(self, tkinter_root, registry) -> None:
        _wm, files = registry
        panel = self._panel(tkinter_root, self._project_editor(registry, _rat_project(files)), {})
        assert "Could not read the classes" in panel._warning.cget("text")
        assert str(panel._save_button.cget("state")) == "disabled"

    def test_restore_automatic_clears_the_project_map(self, tkinter_root, registry) -> None:
        _wm, files = registry
        data = _rat_project(
            files, **{PROJECT_ROLES_KEY: BARNES_ROLES, PROJECT_SHA_KEY: _sha(files["rat"])}
        )
        panel = self._panel(tkinter_root, self._project_editor(registry, data), BARNES_NAMES)
        assert panel.restore_automatic() is True
        assert data[OVERRIDES_KEY][PROJECT_ROLES_KEY] is None
        assert "automatic" in panel._source_label.cget("text")

    def test_failed_save_is_reported(self, tkinter_root, registry) -> None:
        _wm, files = registry
        editor = self._project_editor(registry, _rat_project(files))
        panel = self._panel(tkinter_root, editor, BARNES_NAMES)
        editor.project_manager.save_project.side_effect = OSError("disk full")
        assert panel.save() is False
        assert panel.restore_automatic() is False
        assert panel._status.cget("text") == "The class roles could not be saved; nothing changed."

    def test_draft_mode_returns_none_until_edited(self, tkinter_root, registry) -> None:
        wm, files = registry
        editor = ClassRolesEditor(
            scope=ClassRolesScope.WEIGHT, weight_manager=wm, weight_name=files["rat"].name
        )
        panel = self._panel(tkinter_root, editor, BARNES_NAMES, persist=False)
        assert panel._save_button is None
        assert panel.draft_mapping() is None
        assert panel.draft_weight_sha256() == _sha(files["rat"])

        panel.set_role([1, 3], ClassRole.CONTEXT)
        assert panel.draft_mapping() == BARNES_ROLES

        panel.restore_automatic()
        assert panel.draft_mapping() is None
        assert "class_roles" not in wm.weights[files["rat"].name]

    def test_draft_mode_raises_on_invalid_rows(self, tkinter_root, registry) -> None:
        wm, files = registry
        editor = ClassRolesEditor(
            scope=ClassRolesScope.WEIGHT, weight_manager=wm, weight_name=files["rat"].name
        )
        panel = self._panel(tkinter_root, editor, BARNES_NAMES, persist=False)
        panel.set_role([0, 3], ClassRole.ARENA)
        with pytest.raises(SeveralArenaClassesError):
            panel.draft_mapping()

    def test_set_weight_name_reloads(self, tkinter_root, registry) -> None:
        wm, files = registry
        editor = ClassRolesEditor(
            scope=ClassRolesScope.WEIGHT, weight_manager=wm, weight_name=files["rat"].name
        )
        loader = MagicMock(side_effect=lambda name: BARNES_NAMES if "rat" in name else ZEBRA_NAMES)
        panel = ClassRolesPanel(
            tkinter_root,
            editor=editor,
            names_loader=loader,
            cache=ClassNamesCache(),
            background=False,
        )
        panel.set_weight_name(files["zebra"].name)
        assert [row.name for row in panel.rows()] == ["aqua", "zebrafish"]
        panel.set_weight_name(files["zebra"].name)
        assert loader.call_count == 2

    def test_lazy_panel_waits_until_shown(self, tkinter_root, registry) -> None:
        wm, files = registry
        editor = ClassRolesEditor(
            scope=ClassRolesScope.WEIGHT, weight_manager=wm, weight_name=files["rat"].name
        )
        loader = MagicMock(return_value=BARNES_NAMES)
        panel = ClassRolesPanel(
            tkinter_root,
            editor=editor,
            names_loader=loader,
            cache=ClassNamesCache(),
            background=False,
            load_when_mapped=True,
        )
        panel.set_weight_name(files["zebra"].name)
        loader.assert_not_called()
        panel.event_generate("<Map>")
        loader.assert_called_once_with(files["zebra"].name)
        panel.event_generate("<Map>")
        loader.assert_called_once_with(files["zebra"].name)

    def test_background_load_comes_back_on_the_tk_thread(self, tkinter_root, registry) -> None:
        wm, files = registry
        editor = ClassRolesEditor(
            scope=ClassRolesScope.WEIGHT, weight_manager=wm, weight_name=files["rat"].name
        )
        loader_threads: list[str] = []

        def _loader(_name: str) -> dict[int, str]:
            loader_threads.append(threading.current_thread().name)
            return BARNES_NAMES

        panel = ClassRolesPanel(
            tkinter_root, editor=editor, names_loader=_loader, cache=ClassNamesCache()
        )
        deadline = time.monotonic() + 10

        def _wait() -> None:
            if panel.rows() or time.monotonic() > deadline:
                tkinter_root.quit()
            else:
                tkinter_root.after(20, _wait)

        tkinter_root.after(20, _wait)
        tkinter_root.mainloop()  # ``after`` from a worker thread needs a running loop
        assert loader_threads == ["ClassRolesNames"]
        assert [row.name for row in panel.rows()] == list(BARNES_NAMES.values())

    def test_weight_dialog_edits_the_registry(self, tkinter_root, registry) -> None:
        wm, files = registry
        service = MagicMock()
        service.inspect_model.return_value = {"class_names": BARNES_NAMES}
        bus, seen = _recording_bus()
        dialog = ClassRolesDialog(
            tkinter_root,
            weight_name=files["rat"].name,
            weight_manager=wm,
            model_service=service,
            event_bus=bus,
            background=False,
        )
        try:
            dialog.panel.set_role([1, 3], ClassRole.CONTEXT)
            assert dialog.panel.save() is True
            assert wm.weights[files["rat"].name]["class_roles"] == BARNES_ROLES
            assert seen[0].scope == "weight"
        finally:
            dialog.destroy()

    def test_compact_layout_for_the_wizard(self, tkinter_root, registry) -> None:
        wm, files = registry
        editor = ClassRolesEditor(
            scope=ClassRolesScope.WEIGHT, weight_manager=wm, weight_name=files["rat"].name
        )
        panel = self._panel(tkinter_root, editor, BARNES_NAMES, persist=False, compact=True)
        assert panel._weight_label.winfo_manager() == ""
        assert panel._restore_button.master is panel._role_combo.master
        assert panel._status.winfo_manager() == ""
        panel._on_role_chosen()  # nothing selected → message shown
        assert panel._status.winfo_manager() == "pack"
        panel._set_status("")
        assert panel._status.winfo_manager() == ""
