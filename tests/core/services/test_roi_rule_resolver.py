"""Testes da fonte canônica da regra de inclusão em ROI."""

from __future__ import annotations

import dataclasses
from types import SimpleNamespace

import pytest

from zebtrack.core.services.roi_rule_resolver import (
    DEFAULT_BUFFER_RADIUS_VALUE,
    DEFAULT_MIN_BBOX_OVERLAP_RATIO,
    DEFAULT_ROI_INCLUSION_RULE,
    RoiRuleConfig,
    apply_roi_rule_to_settings,
    resolve_roi_rule,
)


def _settings(
    rule: str = "bbox_intersects",
    buffer_radius: float = 1.5,
    overlap: float = 0.25,
) -> SimpleNamespace:
    """Duplo mínimo de ``Settings`` (o resolvedor só lê atributos)."""
    return SimpleNamespace(
        roi_inclusion_rule=rule,
        roi_buffer_radius_value=buffer_radius,
        roi_min_bbox_overlap_ratio=overlap,
    )


# ----------------------------------------------------------------------
# Precedência
# ----------------------------------------------------------------------


def test_project_overrides_global():
    project = {"roi_settings": {"roi_inclusion_rule": "centroid_in"}}
    config = resolve_roi_rule(project, _settings(rule="bbox_intersects"))
    assert config.rule == "centroid_in"


def test_global_used_when_project_has_no_roi_settings():
    config = resolve_roi_rule({"outra_chave": 1}, _settings(rule="centroid_in"))
    assert config.rule == "centroid_in"


def test_defaults_when_no_project_and_no_settings():
    config = resolve_roi_rule(None, None)
    assert config.rule == DEFAULT_ROI_INCLUSION_RULE
    assert config.buffer_radius_value == DEFAULT_BUFFER_RADIUS_VALUE
    assert config.min_bbox_overlap_ratio == DEFAULT_MIN_BBOX_OVERLAP_RATIO


def test_empty_project_data_falls_back_to_settings():
    config = resolve_roi_rule({}, _settings(rule="centroid_in_on_buffered_roi", buffer_radius=2.0))
    assert config.rule == "centroid_in_on_buffered_roi"
    assert config.buffer_radius_value == 2.0


def test_partial_project_key_keeps_remaining_from_settings():
    """Só a regra vem do projeto; os parâmetros continuam vindo do global."""
    project = {"roi_settings": {"roi_inclusion_rule": "centroid_in_on_buffered_roi"}}
    config = resolve_roi_rule(project, _settings(buffer_radius=3.0, overlap=0.4))
    assert config.rule == "centroid_in_on_buffered_roi"
    assert config.buffer_radius_value == 3.0
    assert config.min_bbox_overlap_ratio == 0.4


def test_all_three_keys_from_project():
    project = {
        "roi_settings": {
            "roi_inclusion_rule": "bbox_intersects",
            "roi_buffer_radius_value": 4.0,
            "roi_min_bbox_overlap_ratio": 0.75,
        }
    }
    config = resolve_roi_rule(project, _settings(rule="centroid_in"))
    assert config == RoiRuleConfig("bbox_intersects", 4.0, 0.75)


# ----------------------------------------------------------------------
# Tolerância a lixo
# ----------------------------------------------------------------------


def test_invalid_rule_in_project_falls_back_to_settings():
    project = {"roi_settings": {"roi_inclusion_rule": "regra_que_nao_existe"}}
    config = resolve_roi_rule(project, _settings(rule="centroid_in"))
    assert config.rule == "centroid_in"


def test_invalid_rule_in_settings_falls_back_to_default():
    config = resolve_roi_rule(None, _settings(rule="bbox_center"))
    assert config.rule == DEFAULT_ROI_INCLUSION_RULE


@pytest.mark.parametrize("bad", [float("inf"), float("-inf"), float("nan")])
def test_non_finite_parameters_fall_back(bad):
    """``inf`` passaria pelo teste de faixa (buffer não tem máximo)."""
    project = {
        "roi_settings": {
            "roi_buffer_radius_value": bad,
            "roi_min_bbox_overlap_ratio": bad,
        }
    }
    config = resolve_roi_rule(project, _settings(buffer_radius=2.0, overlap=0.25))
    assert config.buffer_radius_value == 2.0
    assert config.min_bbox_overlap_ratio == 0.25


@pytest.mark.parametrize("raw", ["2.5", " 2.5 ", 2.5])
def test_accepts_text_from_the_ui(raw):
    """A aba de Zonas manda o campo cru; a conversão é aqui, não na UI."""
    project = {"roi_settings": {"roi_buffer_radius_value": raw}}
    assert resolve_roi_rule(project, _settings()).buffer_radius_value == 2.5


@pytest.mark.parametrize("bad", ["texto", None, float("nan"), -1.0])
def test_invalid_buffer_falls_back(bad):
    project = {
        "roi_settings": {
            "roi_inclusion_rule": "centroid_in_on_buffered_roi",
            "roi_buffer_radius_value": bad,
        }
    }
    config = resolve_roi_rule(project, _settings(buffer_radius=2.0))
    assert config.buffer_radius_value == 2.0


@pytest.mark.parametrize("bad", [1.5, -0.1, "muito"])
def test_invalid_overlap_falls_back(bad):
    project = {"roi_settings": {"roi_min_bbox_overlap_ratio": bad}}
    config = resolve_roi_rule(project, _settings(overlap=0.25))
    assert config.min_bbox_overlap_ratio == 0.25


def test_roi_settings_of_wrong_type_is_ignored():
    config = resolve_roi_rule({"roi_settings": "não é dict"}, _settings(rule="centroid_in"))
    assert config.rule == "centroid_in"


@pytest.mark.parametrize("garbage", ["texto", ["lista"], 42, object()])
def test_project_data_of_wrong_type_never_raises(garbage):
    """Isto roda no loop ao vivo: ``.get`` num não-dict levantaria AttributeError."""
    config = resolve_roi_rule(garbage, _settings(rule="centroid_in"))
    assert config.rule == "centroid_in"


def test_settings_without_roi_attributes_uses_defaults():
    config = resolve_roi_rule(None, SimpleNamespace())
    assert config == RoiRuleConfig()


def test_config_is_always_self_consistent():
    """Parâmetros zerados viram default: aplicar a config nunca invalida Settings."""
    project = {
        "roi_settings": {
            "roi_inclusion_rule": "centroid_in",
            "roi_buffer_radius_value": 0.0,
            "roi_min_bbox_overlap_ratio": 0.0,
        }
    }
    config = resolve_roi_rule(project, None)
    assert config.rule == "centroid_in"
    assert config.buffer_radius_value > 0
    assert 0 < config.min_bbox_overlap_ratio <= 1


@pytest.mark.parametrize("zero", [0.0, 0, "0", -0.0])
def test_zero_parameter_falls_back_one_level_not_to_default(zero):
    """Zero é inválido, não "valor do projeto".

    Se o zero passasse pela coerção, a normalização o trocaria pelo DEFAULT em
    silêncio — o valor global seria descartado sem ninguém saber. Ele tem de
    cair um nível, como qualquer outro valor inválido.
    """
    project = {
        "roi_settings": {
            "roi_buffer_radius_value": zero,
            "roi_min_bbox_overlap_ratio": zero,
        }
    }
    config = resolve_roi_rule(project, _settings(buffer_radius=2.0, overlap=0.25))
    assert config.buffer_radius_value == 2.0
    assert config.min_bbox_overlap_ratio == 0.25


# ----------------------------------------------------------------------
# Imutabilidade / helpers
# ----------------------------------------------------------------------


def test_config_is_frozen():
    config = RoiRuleConfig()
    with pytest.raises(dataclasses.FrozenInstanceError):
        config.rule = "centroid_in"  # type: ignore[misc]


def test_config_flags():
    assert RoiRuleConfig("bbox_intersects").uses_bbox is True
    assert RoiRuleConfig("seg_overlap").uses_bbox is True
    assert RoiRuleConfig("centroid_in").uses_bbox is False
    assert RoiRuleConfig("centroid_in_on_buffered_roi").uses_buffer is True
    assert RoiRuleConfig("centroid_in").uses_buffer is False


def test_resolver_does_not_mutate_project_data():
    project = {"roi_settings": {"roi_inclusion_rule": "centroid_in"}}
    before = {"roi_settings": dict(project["roi_settings"])}
    resolve_roi_rule(project, _settings())
    assert project == before


# ----------------------------------------------------------------------
# Aplicação em Settings reais (validate_assignment + validador cruzado)
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "target_rule",
    ["centroid_in", "centroid_in_on_buffered_roi", "bbox_intersects", "seg_overlap"],
)
def test_apply_to_real_settings_survives_cross_field_validator(target_rule):
    """A ordem de atribuição não pode passar por um estado intermediário inválido."""
    from zebtrack.settings import load_settings

    settings = load_settings()
    for start in ("centroid_in", "centroid_in_on_buffered_roi", "bbox_intersects"):
        apply_roi_rule_to_settings(settings, RoiRuleConfig(start, 1.0, 0.3))
        apply_roi_rule_to_settings(settings, RoiRuleConfig(target_rule, 2.0, 0.6))
        assert settings.roi_inclusion_rule == target_rule
        assert settings.roi_buffer_radius_value == 2.0
        assert settings.roi_min_bbox_overlap_ratio == 0.6


def test_apply_to_none_is_noop():
    assert apply_roi_rule_to_settings(None, RoiRuleConfig()) is None
