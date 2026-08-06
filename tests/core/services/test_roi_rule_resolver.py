"""Testes da fonte canônica da regra de inclusão em ROI."""

from __future__ import annotations

import dataclasses
from types import SimpleNamespace

import pytest

from zebtrack.core.services.roi_rule_resolver import (
    DEFAULT_BBOX_OVERLAP_BASIS,
    DEFAULT_BUFFER_RADIUS_VALUE,
    DEFAULT_MIN_BBOX_OVERLAP_RATIO,
    DEFAULT_ROI_FLUTTER_ENTER_FRAMES,
    DEFAULT_ROI_FLUTTER_EXIT_FRAMES,
    DEFAULT_ROI_INCLUSION_RULE,
    DEFAULT_ROI_MAX_GAP_S,
    DEFAULT_ROI_MIN_GAP_S,
    DEFAULT_ROI_MIN_VISIT_S,
    RoiRuleConfig,
    apply_roi_rule_to_settings,
    resolve_roi_rule,
)


def _settings(
    rule: str = "bbox_intersects",
    buffer_radius: float = 1.5,
    overlap: float = 0.25,
    basis: str = "bbox",
) -> SimpleNamespace:
    """Duplo mínimo de ``Settings`` (o resolvedor só lê atributos)."""
    return SimpleNamespace(
        roi_inclusion_rule=rule,
        roi_buffer_radius_value=buffer_radius,
        roi_min_bbox_overlap_ratio=overlap,
        roi_bbox_overlap_basis=basis,
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


@pytest.mark.parametrize(
    ("rule", "required_attr", "irrelevant_attr"),
    [
        ("centroid_in_on_buffered_roi", "buffer_radius_value", "min_bbox_overlap_ratio"),
        ("seg_overlap", "min_bbox_overlap_ratio", "buffer_radius_value"),
    ],
    ids=["buffered", "seg_overlap"],
)
def test_config_is_self_consistent_with_its_own_rule(rule, required_attr, irrelevant_attr):
    """O parâmetro EXIGIDO pela regra nunca é zero; o irrelevante pode ser.

    São as mesmas faixas do validador cruzado de ``Settings`` — é isso que
    permite aplicar a config sem passar por um estado intermediário inválido.
    ``bbox_intersects`` é a exceção documentada e tem teste próprio: nela zero
    é um limiar com significado, não um valor faltando.
    """
    project = {
        "roi_settings": {
            "roi_inclusion_rule": rule,
            "roi_buffer_radius_value": 0.0,
            "roi_min_bbox_overlap_ratio": 0.0,
        }
    }
    config = resolve_roi_rule(project, None)

    assert config.rule == rule
    assert getattr(config, required_attr) > 0
    assert getattr(config, irrelevant_attr) == 0.0


@pytest.mark.parametrize("zero", [0.0, 0, "0"])
def test_zero_overlap_is_preserved_for_bbox_intersects(zero):
    """Zero em ``bbox_intersects`` é o limiar "qualquer sobreposição real".

    É o predicado que o nome da regra sempre prometeu e que o validador antigo
    tornava inexprimível. Tratá-lo como valor faltando (caindo no global)
    devolveria silenciosamente uma fração mínima que o usuário desligou.
    """
    project = {
        "roi_settings": {
            "roi_inclusion_rule": "bbox_intersects",
            "roi_min_bbox_overlap_ratio": zero,
        }
    }
    config = resolve_roi_rule(project, _settings(overlap=0.25))
    assert config.min_bbox_overlap_ratio == 0.0
    assert config.overlap_any is True


@pytest.mark.parametrize("zero", [0.0, 0, "0"])
def test_zero_in_the_required_parameter_falls_back_one_level(zero):
    """Zero no parâmetro que a regra USA é inválido, não "valor do projeto".

    Se passasse pela coerção, a normalização o trocaria pelo DEFAULT em
    silêncio — o valor global seria descartado sem ninguém saber.
    """
    project = {
        "roi_settings": {
            "roi_inclusion_rule": "seg_overlap",
            "roi_min_bbox_overlap_ratio": zero,
        }
    }
    config = resolve_roi_rule(project, _settings(overlap=0.25))
    assert config.min_bbox_overlap_ratio == 0.25


@pytest.mark.parametrize("zero", [0.0, 0, "0"])
def test_zero_in_an_irrelevant_parameter_is_preserved(zero):
    """Zero no parâmetro que a regra IGNORA é legítimo — nem ruído nem descarte.

    ``config.yaml`` e projetos reais carregam parâmetros zerados da regra que
    não está em uso; tratá-los como inválidos encheria o log do loop ao vivo.
    """
    project = {
        "roi_settings": {
            "roi_inclusion_rule": "bbox_intersects",
            "roi_buffer_radius_value": zero,
        }
    }
    config = resolve_roi_rule(project, _settings(buffer_radius=2.0))
    assert config.buffer_radius_value == 0.0


# ----------------------------------------------------------------------
# Imutabilidade / helpers
# ----------------------------------------------------------------------


def test_config_can_be_the_base_layer_of_another_resolve():
    """Uma edição parcial resolve contra a config atual, não contra o global."""
    current = RoiRuleConfig("bbox_intersects", 3.0, 0.42)
    updated = resolve_roi_rule({"roi_settings": {"roi_inclusion_rule": "centroid_in"}}, current)
    assert updated == RoiRuleConfig("centroid_in", 3.0, 0.42)


def test_to_roi_settings_round_trips():
    config = RoiRuleConfig("centroid_in_on_buffered_roi", 2.0, 0.6)
    assert resolve_roi_rule({"roi_settings": config.to_roi_settings()}, None) == config


def test_settings_name_aliases():
    config = RoiRuleConfig("centroid_in", 2.0, 0.6)
    assert config.roi_inclusion_rule == "centroid_in"
    assert config.roi_buffer_radius_value == 2.0
    assert config.roi_min_bbox_overlap_ratio == 0.6


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


# ----------------------------------------------------------------------
# Base (denominador) da fração de sobreposição
# ----------------------------------------------------------------------


def test_basis_defaults_to_bbox():
    """Sem configurar nada, a base é a histórica — nada muda para quem já usa."""
    assert resolve_roi_rule(None, None).bbox_overlap_basis == DEFAULT_BBOX_OVERLAP_BASIS
    assert RoiRuleConfig().bbox_overlap_basis == "bbox"


@pytest.mark.parametrize("basis", ["bbox", "roi", "max"])
def test_basis_project_overrides_global(basis):
    project = {"roi_settings": {"roi_bbox_overlap_basis": basis}}
    config = resolve_roi_rule(project, _settings(basis="bbox"))
    assert config.bbox_overlap_basis == basis
    assert config.roi_bbox_overlap_basis == basis


@pytest.mark.parametrize("bad", ["area", "", 3, None])
def test_invalid_basis_falls_back_one_level(bad):
    """Base inválida cai no nível anterior; nunca levanta no loop ao vivo."""
    project = {"roi_settings": {"roi_bbox_overlap_basis": bad}}
    config = resolve_roi_rule(project, _settings(basis="max"))
    assert config.bbox_overlap_basis == "max"


def test_basis_round_trips_through_roi_settings():
    config = RoiRuleConfig("bbox_intersects", 2.0, 0.6, "max")
    assert resolve_roi_rule({"roi_settings": config.to_roi_settings()}, None) == config


def test_apply_basis_to_real_settings():
    from zebtrack.settings import load_settings

    settings = load_settings()
    apply_roi_rule_to_settings(settings, RoiRuleConfig("bbox_intersects", 1.0, 0.3, "roi"))
    assert settings.roi_bbox_overlap_basis == "roi"


def test_apply_zero_overlap_to_real_settings():
    """O limiar 0 de ``bbox_intersects`` sobrevive ao validador cruzado."""
    from zebtrack.settings import load_settings

    settings = load_settings()
    apply_roi_rule_to_settings(settings, RoiRuleConfig("centroid_in_on_buffered_roi", 1.0, 0.3))
    apply_roi_rule_to_settings(settings, RoiRuleConfig("bbox_intersects", 1.0, 0.0))
    assert settings.roi_inclusion_rule == "bbox_intersects"
    assert settings.roi_min_bbox_overlap_ratio == 0.0


def test_overlap_any_flag():
    assert RoiRuleConfig("bbox_intersects", 1.0, 0.0).overlap_any is True
    assert RoiRuleConfig("bbox_intersects", 1.0, 0.10).overlap_any is False


def test_overlap_any_is_restricted_to_bbox_intersects():
    """A flag responde pela semântica documentada, não por "ratio <= 0".

    ``seg_overlap`` não tem caminho de sobreposição pura, e as regras de
    centroide nem olham a fração — nenhuma delas pode acionar o predicado
    topológico.
    """
    for rule in ("centroid_in", "centroid_in_on_buffered_roi", "seg_overlap"):
        assert RoiRuleConfig(rule, 1.0, 0.0).overlap_any is False, rule


# ----------------------------------------------------------------------
# Autoconsistência em QUALQUER construção (não só via resolve_roi_rule)
# ----------------------------------------------------------------------


@pytest.mark.parametrize("bad", [-0.5, -1e-9, 1.5, float("nan"), float("inf"), "texto", None])
def test_direct_construction_sanitizes_the_overlap_ratio(bad):
    """Limiar fora de faixa vira o default mesmo sem passar pelo resolvedor.

    Um limiar NEGATIVO era o caso perigoso: ``ratio >= limiar`` valeria até
    para caixas que não tocam a ROI, transformando entrada inválida no
    resultado mais permissivo possível.
    """
    config = RoiRuleConfig("bbox_intersects", 1.0, bad)
    assert config.min_bbox_overlap_ratio == DEFAULT_MIN_BBOX_OVERLAP_RATIO
    assert config.overlap_any is False


@pytest.mark.parametrize("bad", [-0.5, float("nan"), float("inf"), "texto", None])
def test_direct_construction_sanitizes_the_buffer_radius(bad):
    config = RoiRuleConfig("centroid_in_on_buffered_roi", bad, 0.3)
    assert config.buffer_radius_value == DEFAULT_BUFFER_RADIUS_VALUE


def test_direct_construction_sanitizes_rule_and_basis():
    config = RoiRuleConfig("regra_inexistente", 1.0, 0.3, "area")
    assert config.rule == DEFAULT_ROI_INCLUSION_RULE
    assert config.bbox_overlap_basis == DEFAULT_BBOX_OVERLAP_BASIS


def test_zero_overlap_survives_direct_construction_for_bbox_intersects():
    """O 0 legítimo NÃO pode ser confundido com valor fora de faixa."""
    config = RoiRuleConfig("bbox_intersects", 1.0, 0.0)
    assert config.min_bbox_overlap_ratio == 0.0
    assert config.overlap_any is True


def test_zero_overlap_is_sanitized_for_seg_overlap():
    """Em ``seg_overlap`` o 0 é incoerente e cai no default, com log."""
    config = RoiRuleConfig("seg_overlap", 1.0, 0.0)
    assert config.min_bbox_overlap_ratio == DEFAULT_MIN_BBOX_OVERLAP_RATIO


def test_sanitized_config_can_be_applied_to_real_settings():
    """A autoconsistência é o que permite aplicar sem estado intermediário inválido."""
    from zebtrack.settings import load_settings

    settings = load_settings()
    apply_roi_rule_to_settings(settings, RoiRuleConfig("seg_overlap", -1.0, -0.5))
    assert settings.roi_min_bbox_overlap_ratio == DEFAULT_MIN_BBOX_OVERLAP_RATIO
    assert settings.roi_buffer_radius_value == DEFAULT_BUFFER_RADIUS_VALUE


# ----------------------------------------------------------------------
# Debounce assimétrico e limiares de duração
# ----------------------------------------------------------------------


def _timing_settings(**overrides) -> SimpleNamespace:
    """``_settings`` acrescido dos campos temporais."""
    base = _settings()
    for key, value in {
        "roi_flutter_enter_frames": DEFAULT_ROI_FLUTTER_ENTER_FRAMES,
        "roi_flutter_exit_frames": DEFAULT_ROI_FLUTTER_EXIT_FRAMES,
        "roi_min_visit_s": DEFAULT_ROI_MIN_VISIT_S,
        "roi_min_gap_s": DEFAULT_ROI_MIN_GAP_S,
        "roi_max_gap_s": DEFAULT_ROI_MAX_GAP_S,
        **overrides,
    }.items():
        setattr(base, key, value)
    return base


def test_timing_defaults_when_nothing_is_configured():
    config = resolve_roi_rule(None, None)
    assert config.flutter_enter_frames == DEFAULT_ROI_FLUTTER_ENTER_FRAMES
    assert config.flutter_exit_frames == DEFAULT_ROI_FLUTTER_EXIT_FRAMES
    assert config.min_visit_s == DEFAULT_ROI_MIN_VISIT_S
    assert config.min_gap_s == DEFAULT_ROI_MIN_GAP_S
    assert config.max_gap_s == DEFAULT_ROI_MAX_GAP_S


def test_timing_follows_the_same_precedence_as_the_rule():
    project = {"roi_settings": {"roi_flutter_exit_frames": 9, "roi_min_visit_s": 0.75}}
    config = resolve_roi_rule(project, _timing_settings(roi_flutter_exit_frames=4))
    assert config.flutter_exit_frames == 9  # projeto vence
    assert config.flutter_enter_frames == DEFAULT_ROI_FLUTTER_ENTER_FRAMES  # global
    assert config.min_visit_s == 0.75


def test_zero_seconds_is_a_valid_off_switch():
    """``0.0`` significa "desligado" e nunca pode virar o default.

    É a armadilha do ``x or default``: ``0.0 or 0.2`` é ``0.2``.
    """
    project = {"roi_settings": {"roi_min_visit_s": 0.0, "roi_min_gap_s": 0.0}}
    config = resolve_roi_rule(project, _timing_settings(roi_min_visit_s=0.5))
    assert config.min_visit_s == 0.0
    assert config.min_gap_s == 0.0


@pytest.mark.parametrize("bad", [0, -1, 2.5, "dois", float("nan")])
def test_invalid_frame_count_falls_back_to_the_default(bad):
    """Meio frame não existe, e zero frame de confirmação também não."""
    config = resolve_roi_rule({"roi_settings": {"roi_flutter_enter_frames": bad}}, None)
    assert config.flutter_enter_frames == DEFAULT_ROI_FLUTTER_ENTER_FRAMES


@pytest.mark.parametrize("bad", [-0.1, float("inf"), float("nan"), "meio segundo"])
def test_invalid_duration_falls_back_to_the_default(bad):
    config = resolve_roi_rule({"roi_settings": {"roi_min_visit_s": bad}}, None)
    assert config.min_visit_s == DEFAULT_ROI_MIN_VISIT_S


def test_max_gap_accepts_infinity_as_the_no_cap_mode():
    """``inf`` é o único jeito de reproduzir a atribuição histórica."""
    config = resolve_roi_rule({"roi_settings": {"roi_max_gap_s": float("inf")}}, None)
    assert config.max_gap_s == float("inf")


@pytest.mark.parametrize("bad", [0, -1.0, float("nan"), "sempre"])
def test_invalid_max_gap_falls_back_to_automatic(bad):
    config = resolve_roi_rule({"roi_settings": {"roi_max_gap_s": bad}}, None)
    assert config.max_gap_s == DEFAULT_ROI_MAX_GAP_S


def test_timing_round_trips_through_roi_settings():
    config = RoiRuleConfig(
        rule="centroid_in",
        flutter_enter_frames=4,
        flutter_exit_frames=6,
        min_visit_s=0.5,
        min_gap_s=0.3,
        max_gap_s=1.5,
    )
    assert resolve_roi_rule({"roi_settings": config.to_roi_settings()}, None) == config


def test_timing_is_applied_to_real_settings():
    from zebtrack.settings import load_settings

    settings = load_settings()
    apply_roi_rule_to_settings(
        settings,
        RoiRuleConfig(flutter_enter_frames=5, flutter_exit_frames=7, min_visit_s=0.4),
    )
    assert settings.roi_flutter_enter_frames == 5
    assert settings.roi_flutter_exit_frames == 7
    assert settings.roi_min_visit_s == 0.4
