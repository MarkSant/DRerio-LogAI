"""``ui/terminology``: the interface vocabulary that follows the animal model.

Contract under test (Barnes v8.1, stage 3): a zebrafish or legacy project reads
exactly today's text, a rodent/other project reads "arena"/"animal", the wording is
resolved at CALL time, and each variant is a whole sentence (no noun is spliced into a
translated sentence).
"""

from __future__ import annotations

import json
import string
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import polib
import pytest

from zebtrack import i18n
from zebtrack.core.services.experiment_profile import AnimalModel
from zebtrack.ui.terminology import (
    animal_model_of,
    animal_model_of_gui,
    term,
    term_keys,
    variants,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
LOCALES = REPO_ROOT / "src" / "zebtrack" / "locales"
NEW_PAIRS = LOCALES / "_pairs" / "barnes-animal-terms.json"
ALL_KEYS = term_keys()


@pytest.fixture(autouse=True)
def _english_after():
    """Leave the language as the session fixture set it."""
    yield
    i18n.install("en")


def _fields(text: str) -> set[str]:
    return {name for _lit, name, _spec, _conv in string.Formatter().parse(text) if name}


def _pt_catalogue() -> dict[str, str]:
    po = polib.pofile(str(LOCALES / "pt_BR" / "LC_MESSAGES" / "zebtrack.po"))
    return {entry.msgid: entry.msgstr for entry in po}


class TestEveryKeyForEveryAnimalModel:
    @pytest.mark.parametrize("key", ALL_KEYS)
    @pytest.mark.parametrize("model", list(AnimalModel))
    def test_each_cell_is_a_non_empty_string(self, key: str, model: AnimalModel) -> None:
        text = variants(key)[model]

        assert isinstance(text, str) and text.strip()

    @pytest.mark.parametrize("key", ALL_KEYS)
    def test_every_variant_carries_the_same_format_fields(self, key: str) -> None:
        # A translator must be able to reorder, never to lose or invent a field.
        fields = {model: _fields(text) for model, text in variants(key).items()}

        assert len({frozenset(f) for f in fields.values()}) == 1, fields

    @pytest.mark.parametrize("key", ALL_KEYS)
    def test_a_non_zebrafish_variant_does_not_name_the_aquarium_or_the_fish(self, key: str) -> None:
        for model in (AnimalModel.RODENT, AnimalModel.OTHER):
            text = variants(key)[model].lower()
            assert "aquarium" not in text and "fish" not in text and "🐟" not in text, (key, model)

    @pytest.mark.parametrize("key", ALL_KEYS)
    def test_a_non_zebrafish_variant_differs_from_the_legacy_text(self, key: str) -> None:
        by_model = variants(key)

        assert by_model[AnimalModel.RODENT] != by_model[AnimalModel.ZEBRAFISH]
        assert by_model[AnimalModel.OTHER] != by_model[AnimalModel.ZEBRAFISH]

    def test_other_reads_like_rodent_except_where_the_emoji_differ(self) -> None:
        differing = {
            key
            for key in ALL_KEYS
            if variants(key)[AnimalModel.OTHER] != variants(key)[AnimalModel.RODENT]
        }

        assert differing == {"zones.active_frame", "subject.label", "subject.list_title"}


class TestZebrafishIsTodaysText:
    def test_the_known_legacy_strings(self) -> None:
        assert term("calibration.count_label") == "Number of aquariums (videos):"
        assert term("zones.detect_button", AnimalModel.ZEBRAFISH) == "Detect Aquarium (Auto)"
        assert term("zones.active_frame", "zebrafish") == "🐟 Active Aquarium"
        assert term("behavioral.perspective_title") == "Aquarium Perspective *"
        assert term("subject.label", None, label="S1") == "🐟 Subject S1"
        assert term("assignment.title") == "Aquarium Configuration"

    @pytest.mark.parametrize("key", ALL_KEYS)
    def test_every_legacy_msgid_already_had_a_portuguese_translation(self, key: str) -> None:
        # The zebrafish variant is the ORIGINAL msgid: it is in the catalogue before this
        # change (so it is not one of the new pairs) and its translation is untouched.
        legacy = variants(key)[AnimalModel.ZEBRAFISH]
        new_pairs = json.loads(NEW_PAIRS.read_text(encoding="utf-8"))

        assert legacy not in new_pairs
        assert _pt_catalogue().get(legacy), f"{key}: legacy msgid has no pt_BR translation"

    def test_no_profile_and_zebrafish_and_the_legacy_default_agree(self) -> None:
        for key in ALL_KEYS:
            fmt: dict[str, Any] = dict.fromkeys(_fields(variants(key)[AnimalModel.ZEBRAFISH]), "1")
            assert (
                term(key, None, **fmt)
                == term(key, "zebrafish", **fmt)
                == term(key, AnimalModel.ZEBRAFISH, **fmt)
            )


class TestRodentVocabulary:
    def test_the_arena_replaces_the_aquarium(self) -> None:
        assert term("calibration.count_label", "rodent") == "Number of arenas (videos):"
        assert term("zones.detect_button", AnimalModel.RODENT) == "Detect Arena (Auto)"
        assert term("zones.active_frame", "rodent") == "🐀 Active Arena"
        assert term("behavioral.perspective_title", "rodent") == "Arena Perspective *"
        assert (
            term("behavioral.thigmotaxis_help", "rodent")
            == "Distance threshold for considering the animal close to the arena walls:"
        )

    def test_other_species_get_the_neutral_wording_and_their_own_emoji(self) -> None:
        assert term("zones.detect_button", "other") == "Detect Arena (Auto)"
        assert term("subject.label", "other", label="A") == "🐾 Subject A"
        assert term("subject.label", "rodent", label="A") == "🐀 Subject A"

    def test_an_unknown_token_degrades_to_other_like_the_profile_resolver(self) -> None:
        assert term("zones.detect_button", "axolotl") == term("zones.detect_button", "other")

    def test_format_arguments_are_applied_only_when_given(self) -> None:
        assert term("assignment.group_empty", "rodent", number=2) == (
            "The group of Arena 2 cannot be empty"
        )
        assert "{number}" in term("assignment.group_empty", "rodent")

    def test_an_unknown_key_raises_instead_of_reading_as_legacy(self) -> None:
        with pytest.raises(KeyError):
            term("no.such.key")


class TestQuotedButtonsStayInStep:
    """Help text that names the Detect button must name THAT animal's button."""

    @pytest.mark.parametrize("model", list(AnimalModel))
    @pytest.mark.parametrize(
        "key", ["zones.no_frame", "zones.no_arena_live_prompt", "zones.no_arena_live_steps"]
    )
    def test_the_quoted_label_is_the_buttons_own(self, key: str, model: AnimalModel) -> None:
        button = term("zones.detect_button", model)

        assert f"'{button}'" in term(key, model)


class TestPortuguese:
    @pytest.fixture(autouse=True)
    def _portuguese(self) -> None:
        i18n.install("pt_BR")

    @pytest.mark.parametrize("key", ALL_KEYS)
    def test_rodent_and_other_are_translated_and_never_say_aquario_or_peixe(self, key: str) -> None:
        for model in (AnimalModel.RODENT, AnimalModel.OTHER):
            text = variants(key)[model]
            assert text != variants(key)[AnimalModel.ZEBRAFISH]
            lowered = text.lower()
            assert "aquário" not in lowered and "peixe" not in lowered and "🐟" not in text
            assert "aquarium" not in lowered, key

    def test_the_arena_agrees_in_gender(self) -> None:
        assert term("zones.active_frame", "rodent") == "🐀 Arena Ativa"
        assert (
            term("zones.sequential_radio", "rodent") == "Sequencial (2 passagens, 1 arena por vez)"
        )
        assert term("behavioral.zones_split", "rodent") == "Dividir a arena em:"
        assert term("live.count_help", "rodent") == (
            "A análise ao vivo trata UMA arena por vez.\n"
            "Para várias arenas, crie um projeto ao vivo."
        )

    def test_the_zebrafish_text_is_unchanged(self) -> None:
        assert term("zones.active_frame", "zebrafish") == "🐟 Aquário Ativo"
        assert term("zones.detect_button", None) == "Detectar Aquário (Auto)"

    def test_wording_follows_the_language_at_call_time(self) -> None:
        i18n.install("en")
        before = term("zones.detect_button", "rodent")
        i18n.install("pt_BR")

        assert (before, term("zones.detect_button", "rodent")) == (
            "Detect Arena (Auto)",
            "Detectar Arena (Auto)",
        )


class TestAnimalModelOf:
    def test_no_project_and_no_profile_are_zebrafish(self) -> None:
        assert animal_model_of() is AnimalModel.ZEBRAFISH
        assert animal_model_of({}) is AnimalModel.ZEBRAFISH

    def test_the_project_block_and_the_run_config_both_count(self) -> None:
        project = {"behavioral_config": {"animal_model": "rodent"}}

        assert animal_model_of(project) is AnimalModel.RODENT
        assert animal_model_of(None, {"animal_model": "other"}) is AnimalModel.OTHER

    def test_barnes_forces_the_rodent_vocabulary(self) -> None:
        project = {"behavioral_config": {"protocol": "barnes", "animal_model": "zebrafish"}}

        assert animal_model_of(project) is AnimalModel.RODENT

    def test_gui_helper_reads_the_open_projects_profile(self) -> None:
        manager = SimpleNamespace(project_data={"behavioral_config": {"animal_model": "rodent"}})
        gui = SimpleNamespace(controller=SimpleNamespace(project_manager=manager))

        assert animal_model_of_gui(gui) is AnimalModel.RODENT

    @pytest.mark.parametrize(
        "gui",
        [
            None,
            SimpleNamespace(),
            SimpleNamespace(controller=None),
            SimpleNamespace(controller=SimpleNamespace(project_manager=None)),
            SimpleNamespace(
                controller=SimpleNamespace(project_manager=SimpleNamespace(project_data="x"))
            ),
        ],
    )
    def test_gui_helper_reads_no_project_as_zebrafish(self, gui: Any) -> None:
        assert animal_model_of_gui(gui) is AnimalModel.ZEBRAFISH
