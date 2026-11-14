"""Class roles resolved by NAME (``core/detection/class_roles``, ADR-009).

What these tests pin:

- an explicit map (project or weight) decides the role of every class by its
  normalised name, so a retrain that inserts a class never shifts a role;
- the precedence project > weight > aliases > positional, and the project map
  is only trusted while it was made for the weight actually loaded (sha);
- without an explicit map the resolution is LITERALLY the 7.2 one: the legacy
  ``(arena, animal)`` tuple equals ``class_aliases.resolve_class_ids`` for every
  name set, aliases never produce ``context``.
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import ValidationError

from zebtrack.core.detection.class_aliases import (
    DEFAULT_ANIMAL_ALIASES,
    DEFAULT_ARENA_ALIASES,
    ClassAliases,
    resolve_class_ids,
)
from zebtrack.core.detection.class_roles import (
    ClassRole,
    ClassRoleMap,
    ClassRoleSource,
    ClassRolesUnresolvedError,
    fit_class_roles,
    overlay_class_roles,
    resolve_class_role_map,
)
from zebtrack.core.exceptions import DetectorError

BARNES = {0: "arena", 1: "experimenter", 2: "rat", 3: "start_box"}
BARNES_ROLES = {
    "arena": "arena",
    "experimenter": "context",
    "rat": "subject",
    "start_box": "context",
}
SHA = "a" * 64
OTHER_SHA = "b" * 64


class TestBarnesWeight:
    def test_explicit_map_gives_subject_arena_and_context(self):
        role_map = resolve_class_role_map(BARNES, weight_entry={"class_roles": BARNES_ROLES})

        assert role_map.subject_ids == frozenset({2})
        assert role_map.arena_id == 0
        assert role_map.context_ids == frozenset({1, 3})
        assert role_map.source is ClassRoleSource.WEIGHT
        assert role_map.has_context is True
        assert role_map.to_legacy_tuple() == (0, 2)

    def test_aliases_only_track_the_rat_and_ignore_the_rest(self):
        role_map = resolve_class_role_map(BARNES)

        assert role_map.subject_ids == frozenset({2})
        assert role_map.arena_id == 0
        assert role_map.context_ids == frozenset()
        assert role_map.has_context is False
        assert role_map.source is ClassRoleSource.ALIASES
        assert role_map.role_of_id(1) is ClassRole.IGNORED
        assert role_map.role_of_id(3) is ClassRole.IGNORED
        assert role_map.to_legacy_tuple() == (0, 2)

    def test_class_absent_from_explicit_map_is_ignored(self):
        partial = {"arena": "arena", "rat": "subject"}
        role_map = resolve_class_role_map(BARNES, weight_entry={"class_roles": partial})

        assert role_map.role_of_id(1) is ClassRole.IGNORED
        assert role_map.role_of_id(3) is ClassRole.IGNORED
        assert role_map.roles_by_name["experimenter"] is ClassRole.IGNORED
        assert role_map.context_ids == frozenset()

    def test_several_subject_classes_share_the_subject_role(self):
        names = {0: "arena", 1: "mouse", 2: "rat"}
        roles = {"arena": "arena", "mouse": "subject", "rat": "subject"}
        role_map = resolve_class_role_map(names, weight_entry={"class_roles": roles})

        assert role_map.subject_ids == frozenset({1, 2})
        assert role_map.to_legacy_tuple() == (0, 1)


class TestPrecedence:
    def test_project_beats_weight_when_sha_matches(self):
        project = {"arena": "arena", "experimenter": "subject", "rat": "context"}
        role_map = resolve_class_role_map(
            BARNES,
            project_override=project,
            project_override_sha=SHA,
            weight_entry={"class_roles": BARNES_ROLES},
            weight_sha256=SHA,
        )

        assert role_map.source is ClassRoleSource.PROJECT
        assert role_map.subject_ids == frozenset({1})
        assert role_map.weight_sha256 == SHA

    def test_project_map_for_another_weight_is_discarded(self, monkeypatch):
        from unittest.mock import MagicMock

        from zebtrack.core.detection import class_roles as module

        fake_log = MagicMock()
        monkeypatch.setattr(module, "log", fake_log)
        project = {"arena": "arena", "experimenter": "subject"}
        role_map = resolve_class_role_map(
            BARNES,
            project_override=project,
            project_override_sha=OTHER_SHA,
            weight_entry={"class_roles": BARNES_ROLES},
            weight_sha256=SHA,
        )

        assert role_map.source is ClassRoleSource.WEIGHT
        assert role_map.subject_ids == frozenset({2})
        events = [call.args[0] for call in fake_log.warning.call_args_list]
        assert "class_roles.project_override.sha_mismatch" in events

    def test_project_map_without_any_sha_is_not_trusted(self):
        project = {"arena": "arena", "experimenter": "subject"}
        role_map = resolve_class_role_map(BARNES, project_override=project)

        assert role_map.source is ClassRoleSource.ALIASES
        assert role_map.subject_ids == frozenset({2})

    def test_weight_beats_aliases(self):
        roles = {"arena": "arena", "experimenter": "subject"}
        role_map = resolve_class_role_map(BARNES, weight_entry={"class_roles": roles})

        assert role_map.source is ClassRoleSource.WEIGHT
        assert role_map.subject_ids == frozenset({1})

    def test_invalid_explicit_map_falls_through_to_the_next_level(self):
        two_arenas = {"arena": "arena", "start_box": "arena", "rat": "subject"}
        role_map = resolve_class_role_map(BARNES, weight_entry={"class_roles": two_arenas})

        assert role_map.source is ClassRoleSource.ALIASES

    def test_unknown_role_token_falls_through(self):
        bad = {"arena": "arena", "rat": "animal"}
        role_map = resolve_class_role_map(BARNES, weight_entry={"class_roles": bad})

        assert role_map.source is ClassRoleSource.ALIASES

    def test_explicit_map_without_subject_falls_through(self):
        no_subject = {"arena": "arena", "rat": "context"}
        role_map = resolve_class_role_map(BARNES, weight_entry={"class_roles": no_subject})

        assert role_map.source is ClassRoleSource.ALIASES
        assert role_map.subject_ids == frozenset({2})

    def test_settings_aliases_are_honoured(self):
        aliases = ClassAliases.with_extra(arena_extra=["caixa"], animal_extra=["gerbil"])
        role_map = resolve_class_role_map({0: "caixa", 1: "gerbil"}, aliases=aliases)

        assert role_map.to_legacy_tuple() == (0, 1)


class TestNoNames:
    @pytest.mark.parametrize("names", [None, {}, [], "garbage"])
    def test_model_without_names_is_legacy_positional(self, names):
        role_map = resolve_class_role_map(names)

        assert role_map.source is ClassRoleSource.LEGACY_POSITIONAL
        assert role_map.to_legacy_tuple() == (0, 1)
        assert role_map.subject_ids == frozenset({1})
        assert role_map.arena_id == 0

    def test_explicit_map_is_ignored_without_names(self):
        role_map = resolve_class_role_map(None, weight_entry={"class_roles": BARNES_ROLES})

        assert role_map.source is ClassRoleSource.LEGACY_POSITIONAL


class TestUnresolved:
    def test_three_unknown_classes_raise_a_typed_error(self):
        names = {0: "person", 1: "bicycle", 2: "car"}
        with pytest.raises(ClassRolesUnresolvedError) as info:
            resolve_class_role_map(names)

        assert isinstance(info.value, DetectorError)
        assert info.value.class_names == names
        assert str(info.value)

    def test_non_strict_degrades_to_the_legacy_positional_ids(self):
        names = {0: "person", 1: "bicycle", 2: "car"}
        role_map = resolve_class_role_map(names, strict=False)

        assert role_map.to_legacy_tuple() == resolve_class_ids(names).as_tuple() == (0, 1)

    def test_two_unknown_classes_keep_the_7_2_positional_guess(self):
        names = {0: "foo", 1: "bar"}
        role_map = resolve_class_role_map(names)

        assert role_map.to_legacy_tuple() == (0, 1)
        assert role_map.source is ClassRoleSource.ALIASES


class TestModelValidation:
    def test_more_than_one_arena_is_rejected(self):
        with pytest.raises(ValidationError):
            ClassRoleMap(
                names={0: "a", 1: "b", 2: "c"},
                roles_by_name={"a": ClassRole.ARENA, "b": ClassRole.ARENA, "c": ClassRole.SUBJECT},
                source=ClassRoleSource.WEIGHT,
            )

    def test_no_subject_is_rejected(self):
        with pytest.raises(ValidationError):
            ClassRoleMap(
                names={0: "a", 1: "b"},
                roles_by_name={"a": ClassRole.ARENA, "b": ClassRole.CONTEXT},
                source=ClassRoleSource.WEIGHT,
            )

    def test_is_frozen_and_forbids_extra(self):
        role_map = resolve_class_role_map(BARNES)
        with pytest.raises(ValidationError):
            role_map.source = ClassRoleSource.PROJECT  # type: ignore[misc]
        with pytest.raises(ValidationError):
            ClassRoleMap(
                names={0: "rat"},
                roles_by_name={"rat": ClassRole.SUBJECT},
                source=ClassRoleSource.WEIGHT,
                unexpected=True,  # type: ignore[call-arg]
            )

    def test_roles_are_persistence_tokens(self):
        assert [r.value for r in ClassRole] == ["subject", "arena", "context", "ignored"]

    def test_role_dict_round_trip_is_plain_and_picklable(self):
        import pickle

        role_map = resolve_class_role_map(BARNES, weight_entry={"class_roles": BARNES_ROLES})
        plain = role_map.roles_as_dict()

        assert plain == BARNES_ROLES
        assert all(type(v) is str for v in plain.values())
        assert pickle.loads(pickle.dumps(role_map)) == role_map

    def test_explicit_flag_follows_the_source(self):
        assert resolve_class_role_map(BARNES).is_explicit is False
        assert resolve_class_role_map(None).is_explicit is False
        explicit = resolve_class_role_map(BARNES, weight_entry={"class_roles": BARNES_ROLES})
        assert explicit.is_explicit is True

    def test_class_name_of_unknown_id(self):
        role_map = resolve_class_role_map(BARNES)
        assert role_map.class_name_of(2) == "rat"
        assert role_map.class_name_of(99) == "99"
        assert role_map.role_of_id(99) is ClassRole.IGNORED


@settings(max_examples=60, deadline=None)
@given(st.permutations(list(BARNES.values())))
def test_permuting_ids_keeps_every_role_by_name(order):
    names = dict(enumerate(order))
    role_map = resolve_class_role_map(names, weight_entry={"class_roles": BARNES_ROLES})

    for class_id, name in names.items():
        assert role_map.role_of_id(class_id).value == BARNES_ROLES[name]
    assert role_map.subject_ids == frozenset({order.index("rat")})
    assert role_map.arena_id == order.index("arena")


_NAME_POOL = [
    *DEFAULT_ARENA_ALIASES[:5],
    *DEFAULT_ANIMAL_ALIASES[:6],
    "experimenter",
    "start_box",
    "0",
    "Fish",
]


@settings(max_examples=200, deadline=None)
@given(
    st.dictionaries(
        keys=st.integers(min_value=0, max_value=6),
        values=st.sampled_from(_NAME_POOL),
        max_size=5,
    )
)
def test_alias_path_reproduces_resolve_class_ids_exactly(names):
    role_map = resolve_class_role_map(names, strict=False)

    assert role_map.to_legacy_tuple() == resolve_class_ids(names).as_tuple()
    assert role_map.context_ids == frozenset()
    assert len(role_map.subject_ids) == 1


class TestZebrafishRegression:
    """Every zebrafish case of ``test_class_aliases.py`` keeps its legacy tuple."""

    @pytest.mark.parametrize(
        ("names", "expected"),
        [
            ({0: "aqua", 1: "zebrafish"}, (0, 1)),
            ({0: "aquarium", 1: "zebrafish"}, (0, 1)),
            ({0: "zebrafish", 1: "aqua"}, (1, 0)),
            ({0: "fish"}, (-1, 0)),
            ({0: "tank", 1: "peixe"}, (0, 1)),
            ({0: "agua", 1: "fish"}, (0, 1)),
            (None, (0, 1)),
            ({}, (0, 1)),
            ({0: "arena", 1: "experimenter", 2: "rat"}, (0, 2)),
            ({0: "arena", 1: "mouse", 2: "rat"}, (0, 1)),
            ({"0": "arena", "1": "rat"}, (0, 1)),
            (["arena", "rat"], (0, 1)),
            ({0: "0"}, (0, 1)),
        ],
    )
    def test_legacy_tuple(self, names, expected):
        role_map = resolve_class_role_map(names)
        assert role_map.to_legacy_tuple() == expected
        assert role_map.context_ids == frozenset()

    def test_single_class_fish_weight_has_no_arena(self):
        role_map = resolve_class_role_map({0: "fish"})
        assert role_map.arena_id == -1
        assert role_map.subject_ids == frozenset({0})

    def test_lowest_animal_id_is_the_only_subject_on_the_alias_path(self):
        role_map = resolve_class_role_map({0: "arena", 1: "mouse", 2: "rat"})
        assert role_map.subject_ids == frozenset({1})
        assert role_map.role_of_id(2) is ClassRole.IGNORED


class TestOverlayClassRoles:
    """What the detector publishes with its detections (#645)."""

    def test_no_map_means_the_ui_may_resolve_its_own(self):
        assert overlay_class_roles(None) is None

    def test_legacy_alias_map_publishes_an_empty_map(self):
        # ``{}`` is "the detector resolved, nobody named the roles": 7.2 colours.
        assert overlay_class_roles(resolve_class_role_map({0: "aqua", 1: "zebrafish"})) == {}

    def test_unnamed_weight_publishes_an_empty_map(self):
        assert overlay_class_roles(resolve_class_role_map({})) == {}

    def test_explicit_map_publishes_every_class_by_id(self):
        role_map = resolve_class_role_map(BARNES, weight_entry={"class_roles": BARNES_ROLES})
        assert overlay_class_roles(role_map) == {
            0: "arena",
            1: "context",
            2: "subject",
            3: "context",
        }

    def test_ids_follow_the_weight_not_the_saved_order(self):
        retrained = {0: "rat", 1: "arena", 2: "start_box", 3: "experimenter"}
        role_map = resolve_class_role_map(retrained, weight_entry={"class_roles": BARNES_ROLES})
        assert overlay_class_roles(role_map) == {
            0: "subject",
            1: "arena",
            2: "context",
            3: "context",
        }


class TestFitClassRoles:
    """Template roles re-applied to the weight chosen in the wizard (#646)."""

    def test_same_names_apply_exactly(self):
        fit = fit_class_roles(BARNES_ROLES, BARNES, weight_sha256="a" * 64)
        assert fit.applied
        assert fit.is_exact
        assert fit.roles == BARNES_ROLES
        assert fit.role_map.source is ClassRoleSource.PROJECT
        assert fit.role_map.subject_ids == frozenset({2})
        assert fit.role_map.weight_sha256 == "a" * 64

    def test_matching_is_by_name_never_by_id(self):
        retrained = {0: "start_box", 1: "rat", 2: "experimenter", 3: "arena"}
        fit = fit_class_roles(BARNES_ROLES, retrained)
        assert fit.role_map.subject_ids == frozenset({1})
        assert fit.role_map.arena_id == 3
        assert fit.role_map.context_ids == frozenset({0, 2})

    def test_names_are_normalised(self):
        fit = fit_class_roles({" Rat ": "subject"}, {0: "RAT", 1: "Arena"})
        assert fit.applied
        assert fit.roles == {"rat": "subject"}
        assert fit.unassigned == ("arena",)

    def test_reports_saved_names_the_weight_lacks(self):
        other = {0: "arena", 1: "rat", 2: "lid"}
        fit = fit_class_roles(BARNES_ROLES, other)
        assert fit.applied
        assert not fit.is_exact
        assert fit.unmatched == ("experimenter", "start_box")
        assert fit.unassigned == ("lid",)
        assert fit.roles == {"arena": "arena", "rat": "subject"}
        assert fit.role_map.role_of_id(2) is ClassRole.IGNORED

    def test_subject_missing_from_the_weight_resolves_automatically(self):
        mouse = {0: "arena", 1: "mouse"}
        fit = fit_class_roles(BARNES_ROLES, mouse)
        assert not fit.applied
        assert fit.roles == {}
        assert fit.role_map.source is ClassRoleSource.ALIASES
        assert fit.role_map.subject_ids == frozenset({1})

    def test_weight_entry_beats_the_aliases_when_the_template_does_not_apply(self):
        fit = fit_class_roles(
            {"rat": "subject"},
            {0: "arena", 1: "mouse", 2: "lid"},
            weight_entry={"class_roles": {"lid": "subject"}},
        )
        assert not fit.applied
        assert fit.role_map.source is ClassRoleSource.WEIGHT
        assert fit.role_map.subject_ids == frozenset({2})

    def test_never_falls_back_to_position(self):
        coco_like = {0: "person", 1: "bicycle", 2: "car"}
        with pytest.raises(ClassRolesUnresolvedError) as exc_info:
            fit_class_roles(BARNES_ROLES, coco_like)
        assert exc_info.value.class_names == coco_like

    def test_invalid_saved_roles_resolve_automatically(self):
        fit = fit_class_roles({"rat": "boss"}, {0: "aqua", 1: "zebrafish"})
        assert not fit.applied
        assert fit.unmatched == ()
        assert fit.role_map.source is ClassRoleSource.ALIASES

    def test_two_arena_names_are_rejected_not_half_applied(self):
        fit = fit_class_roles(
            {"rat": "subject", "arena": "arena", "lid": "arena"},
            {0: "arena", 1: "rat", 2: "lid"},
        )
        assert not fit.applied
        assert fit.role_map.source is ClassRoleSource.ALIASES

    def test_unnamed_weight_never_applies_the_template(self):
        fit = fit_class_roles(BARNES_ROLES, {})
        assert not fit.applied
        assert fit.role_map.source is ClassRoleSource.LEGACY_POSITIONAL
