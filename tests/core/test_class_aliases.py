"""Species-agnostic class-role resolution (``core/detection/class_aliases``).

The regression these tests pin: a non-zebrafish weight used to fall back to
``arena = 0, animal = 1`` by POSITION. Roboflow exports names alphabetically,
so a rodent weight ``{0: arena, 1: experimenter, 2: rat}`` tracked the
experimenter as the animal while every report still looked complete.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from zebtrack.core.detection.class_aliases import (
    DEFAULT_ANIMAL_ALIASES,
    DEFAULT_ARENA_ALIASES,
    ClassAliases,
    normalize_class_name,
    resolve_arena_class_id,
    resolve_class_ids,
)
from zebtrack.core.detection.detection_post_processor import DetectionPostProcessor


class TestLegacyZebrafishBehaviourIsUnchanged:
    """Every name the zebrafish weights use must resolve exactly as before."""

    @pytest.mark.parametrize(
        ("names", "expected"),
        [
            ({0: "aqua", 1: "zebrafish"}, (0, 1)),
            ({0: "aquarium", 1: "zebrafish"}, (0, 1)),
            ({0: "zebrafish", 1: "aqua"}, (1, 0)),
            ({0: "fish"}, (-1, 0)),
            ({0: "tank", 1: "peixe"}, (0, 1)),
            ({0: "agua", 1: "fish"}, (0, 1)),
        ],
    )
    def test_zebrafish_names(self, names, expected):
        assert resolve_class_ids(names).as_tuple() == expected

    def test_no_names_returns_legacy_defaults(self):
        assert resolve_class_ids(None).as_tuple() == (0, 1)
        assert resolve_class_ids({}).as_tuple() == (0, 1)

    def test_legacy_names_still_in_default_vocabularies(self):
        assert {"aqua", "aquarium", "tank", "agua"} <= set(DEFAULT_ARENA_ALIASES)
        assert {"zebrafish", "fish", "peixe"} <= set(DEFAULT_ANIMAL_ALIASES)


class TestRodentWeights:
    def test_alphabetical_roboflow_export_tracks_the_rat_not_the_experimenter(self):
        resolved = resolve_class_ids({0: "arena", 1: "experimenter", 2: "rat"})
        assert resolved.as_tuple() == (0, 2)
        assert resolved.found_arena and resolved.found_animal
        assert resolved.ignored == ("experimenter",)

    def test_start_box_is_ignored(self):
        resolved = resolve_class_ids({0: "arena", 1: "experimenter", 2: "rat", 3: "start_box"})
        assert resolved.as_tuple() == (0, 2)
        assert set(resolved.ignored) == {"experimenter", "start_box"}

    @pytest.mark.parametrize("animal", ["rat", "Rat", "mouse", "camundongo", "rodent", "rato"])
    def test_rodent_animal_names(self, animal):
        assert resolve_class_ids({0: "arena", 1: animal}).as_tuple() == (0, 1)

    def test_unrenamed_roboflow_class_zero_is_not_recognised(self):
        """A forked dataset whose class is still "0" must not pass as recognised."""
        resolved = resolve_class_ids({0: "0"})
        assert not resolved.found_animal
        assert resolved.as_tuple() == (0, 1)


class TestNormalisationAndAmbiguity:
    @pytest.mark.parametrize("raw", ["Open Field", "open-field", " OPEN_FIELD "])
    def test_normalisation(self, raw):
        assert normalize_class_name(raw) == "open_field"

    def test_lowest_id_wins_when_several_animal_names(self):
        assert resolve_class_ids({0: "arena", 1: "mouse", 2: "rat"}).as_tuple() == (0, 1)

    def test_string_keys_and_sequences_are_accepted(self):
        assert resolve_class_ids({"0": "arena", "1": "rat"}).as_tuple() == (0, 1)
        assert resolve_class_ids(["arena", "rat"]).as_tuple() == (0, 1)

    def test_mock_names_degrade_to_legacy(self):
        assert resolve_class_ids(MagicMock()).as_tuple() == (0, 1)


class TestSettingsExtension:
    def test_extra_names_are_added_not_replacing(self):
        aliases = ClassAliases.with_extra(arena_extra=["box"], animal_extra=["gerbil"])
        assert resolve_class_ids({0: "box", 1: "gerbil"}, aliases).as_tuple() == (0, 1)
        assert resolve_class_ids({0: "aqua", 1: "zebrafish"}, aliases).as_tuple() == (0, 1)

    def test_from_settings_reads_model_selection(self):
        settings = SimpleNamespace(
            model_selection=SimpleNamespace(
                class_aliases=SimpleNamespace(arena=["Caixa"], animal=["Gerbil"])
            )
        )
        aliases = ClassAliases.from_settings(settings)
        assert aliases.role_of("caixa") == "arena"
        assert aliases.role_of("gerbil") == "animal"

    @pytest.mark.parametrize("settings", [None, MagicMock(), SimpleNamespace()])
    def test_from_settings_tolerates_missing_or_mock(self, settings):
        assert ClassAliases.from_settings(settings) == ClassAliases.defaults()

    def test_conflicting_settings_fall_back_to_defaults(self):
        settings = SimpleNamespace(
            model_selection=SimpleNamespace(class_aliases=SimpleNamespace(arena=["rat"], animal=[]))
        )
        assert ClassAliases.from_settings(settings) == ClassAliases.defaults()

    def test_real_settings_model_accepts_the_section(self):
        from zebtrack.settings import ClassAliasSettings, ModelSelectionSettings

        section = ModelSelectionSettings(
            class_aliases=ClassAliasSettings(arena=["box"], animal=["gerbil"])
        )
        assert section.class_aliases.animal == ["gerbil"]
        assert ModelSelectionSettings().class_aliases.arena == []


class TestArenaClassIdForArenaModels:
    def test_arena_not_at_zero(self):
        assert resolve_arena_class_id({0: "experimenter", 1: "rat", 2: "arena"}) == 2

    @pytest.mark.parametrize("names", [None, {}, MagicMock(), {0: "rat"}])
    def test_falls_back_to_zero(self, names):
        assert resolve_arena_class_id(names) == 0


class TestPostProcessorDelegation:
    def test_plugin_with_rodent_names(self):
        plugin = SimpleNamespace(class_names={0: "arena", 1: "experimenter", 2: "rat"})
        assert DetectionPostProcessor.resolve_class_ids(plugin) == (0, 2)  # type: ignore[arg-type]

    def test_plugin_with_settings_aliases(self):
        plugin = SimpleNamespace(class_names={0: "caixa", 1: "gerbil"})
        aliases = ClassAliases.with_extra(arena_extra=["caixa"], animal_extra=["gerbil"])
        assert DetectionPostProcessor.resolve_class_ids(plugin, aliases) == (0, 1)  # type: ignore[arg-type]
