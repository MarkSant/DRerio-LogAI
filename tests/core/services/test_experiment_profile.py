"""``resolve_experiment_profile`` — the one reader of animal model + protocol (ADR-014)."""

from __future__ import annotations

import pytest

from zebtrack.core.services.experiment_profile import (
    ANIMAL_MODEL_KEY,
    PROTOCOL_KEY,
    PROTOCOL_PARAMS_KEY,
    AnimalModel,
    ExperimentProfile,
    ProtocolId,
    forced_animal_model,
    resolve_experiment_profile,
)


def test_the_persisted_key_names_are_frozen():
    assert (ANIMAL_MODEL_KEY, PROTOCOL_KEY, PROTOCOL_PARAMS_KEY) == (
        "animal_model",
        "protocol",
        "protocol_params",
    )
    assert [m.value for m in AnimalModel] == ["zebrafish", "rodent", "other"]
    assert [p.value for p in ProtocolId] == ["generic", "barnes"]


@pytest.mark.parametrize(
    ("project_data", "behavioral_config"),
    [
        (None, None),
        ({}, {}),
        ({"behavioral_config": {"aquarium_perspective": "lateral"}}, None),
        ("not a mapping", "neither"),
    ],
)
def test_a_project_that_declares_nothing_is_the_legacy_profile(project_data, behavioral_config):
    profile = resolve_experiment_profile(project_data, behavioral_config)

    assert profile == ExperimentProfile()
    assert profile.animal_model is AnimalModel.ZEBRAFISH
    assert profile.protocol is ProtocolId.GENERIC
    assert profile.is_generic
    assert profile.warnings == ()
    assert dict(profile.protocol_params) == {}


def test_barnes_forces_rodent_without_a_warning_when_no_model_was_declared():
    profile = resolve_experiment_profile(behavioral_config={"protocol": "barnes"})

    assert profile.protocol is ProtocolId.BARNES
    assert profile.animal_model is AnimalModel.RODENT
    assert not profile.is_generic
    assert profile.warnings == ()


def test_barnes_replaces_a_declared_zebrafish_and_says_so():
    profile = resolve_experiment_profile(
        behavioral_config={"protocol": "barnes", "animal_model": "zebrafish"}
    )

    assert profile.animal_model is AnimalModel.RODENT
    assert len(profile.warnings) == 1
    assert "barnes" in profile.warnings[0]
    assert "zebrafish" in profile.warnings[0]


def test_a_declared_rodent_under_barnes_needs_no_correction():
    profile = resolve_experiment_profile(
        behavioral_config={"protocol": "barnes", "animal_model": "rodent"}
    )

    assert profile.animal_model is AnimalModel.RODENT
    assert profile.warnings == ()


def test_generic_keeps_any_declared_model():
    profile = resolve_experiment_profile(behavioral_config={"animal_model": "rodent"})

    assert profile.animal_model is AnimalModel.RODENT
    assert profile.protocol is ProtocolId.GENERIC
    assert profile.is_generic


def test_tokens_are_normalised():
    profile = resolve_experiment_profile(
        behavioral_config={"protocol": "  Barnes ", "animal_model": "RODENT"}
    )

    assert profile.protocol is ProtocolId.BARNES
    assert profile.animal_model is AnimalModel.RODENT
    assert profile.warnings == ()


def test_the_behavioral_config_wins_key_by_key_over_the_project():
    project = {"behavioral_config": {"animal_model": "other", "protocol": "barnes"}}

    profile = resolve_experiment_profile(project, {"protocol": "generic"})

    assert profile.protocol is ProtocolId.GENERIC
    # animal_model was not in the run's config: the project's value is used.
    assert profile.animal_model is AnimalModel.OTHER


def test_a_none_value_is_undeclared_and_falls_through_to_the_project():
    project = {"behavioral_config": {"protocol": "barnes"}}

    profile = resolve_experiment_profile(project, {"protocol": None})

    assert profile.protocol is ProtocolId.BARNES


def test_the_legacy_behavioral_analysis_block_is_read():
    profile = resolve_experiment_profile({"behavioral_analysis": {"animal_model": "rodent"}})

    assert profile.animal_model is AnimalModel.RODENT


def test_behavioral_config_shadows_the_legacy_block_even_when_empty():
    project = {"behavioral_config": {}, "behavioral_analysis": {"animal_model": "rodent"}}

    profile = resolve_experiment_profile(project)

    assert profile.animal_model is AnimalModel.ZEBRAFISH


def test_a_non_mapping_project_block_is_ignored():
    profile = resolve_experiment_profile({"behavioral_config": ["barnes"]})

    assert profile == ExperimentProfile()


@pytest.mark.parametrize("value", ["mouse", 7, ""])
def test_an_unknown_animal_model_degrades_to_other_with_a_warning(value):
    profile = resolve_experiment_profile(behavioral_config={"animal_model": value})

    assert profile.animal_model is AnimalModel.OTHER
    assert len(profile.warnings) == 1
    assert repr(value) in profile.warnings[0]


@pytest.mark.parametrize("value", ["Morris", 3])
def test_an_unknown_protocol_stays_visible_instead_of_passing_as_generic(value):
    profile = resolve_experiment_profile(behavioral_config={"protocol": value})

    assert profile.protocol is ProtocolId.GENERIC
    assert profile.declared_protocol is not None
    assert not profile.is_generic
    assert len(profile.warnings) == 1
    assert repr(value) in profile.warnings[0]


def test_an_unknown_string_protocol_keeps_its_normalised_token():
    profile = resolve_experiment_profile(behavioral_config={"protocol": " Morris "})

    assert profile.declared_protocol == "morris"


def test_an_unknown_non_string_protocol_keeps_its_repr():
    profile = resolve_experiment_profile(behavioral_config={"protocol": 3})

    assert profile.declared_protocol == "3"


def test_only_the_effective_protocols_params_are_kept():
    config = {
        "protocol": "barnes",
        "protocol_params": {"barnes": {"n_holes": 18}, "generic": {"x": 1}},
    }

    profile = resolve_experiment_profile(behavioral_config=config)

    assert dict(profile.protocol_params) == {"n_holes": 18}
    assert profile.warnings == ()


def test_the_params_are_a_read_only_copy():
    raw = {"n_holes": 18}
    profile = resolve_experiment_profile(
        behavioral_config={"protocol": "barnes", "protocol_params": {"barnes": raw}}
    )

    raw["n_holes"] = 12
    assert profile.protocol_params["n_holes"] == 18
    with pytest.raises(TypeError):
        profile.protocol_params["n_holes"] = 5  # type: ignore[index]


def test_a_missing_block_for_the_protocol_gives_empty_params_silently():
    profile = resolve_experiment_profile(
        behavioral_config={"protocol": "barnes", "protocol_params": {"generic": {}}}
    )

    assert dict(profile.protocol_params) == {}
    assert profile.warnings == ()


def test_a_malformed_block_for_the_protocol_warns():
    profile = resolve_experiment_profile(
        behavioral_config={"protocol": "barnes", "protocol_params": {"barnes": [1, 2]}}
    )

    assert dict(profile.protocol_params) == {}
    assert len(profile.warnings) == 1
    assert "barnes" in profile.warnings[0]


def test_malformed_params_warn():
    profile = resolve_experiment_profile(behavioral_config={"protocol_params": "18 holes"})

    assert dict(profile.protocol_params) == {}
    assert len(profile.warnings) == 1


def test_forced_animal_model():
    assert forced_animal_model(ProtocolId.BARNES) is AnimalModel.RODENT
    assert forced_animal_model(ProtocolId.GENERIC) is None


def test_the_profile_is_immutable():
    profile = resolve_experiment_profile()

    with pytest.raises(AttributeError):
        profile.protocol = ProtocolId.BARNES  # type: ignore[misc]
