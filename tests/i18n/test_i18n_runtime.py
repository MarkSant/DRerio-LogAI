"""Behaviour of the runtime translation layer.

The load-bearing property here is that English needs no catalogue: a missing
translation falls back to the msgid, which *is* the English string. That is what
makes "English is the default" free rather than something to maintain.
"""

from __future__ import annotations

import pytest

from zebtrack import i18n
from zebtrack.analysis.reporters.reporter_context import _ as reporter_gettext


@pytest.fixture(autouse=True)
def _restore_language():
    """Leave the language as the session fixture set it."""
    yield
    i18n.reset_for_tests()
    i18n.install("en")


class TestLanguageNormalization:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("en", "en"),
            ("EN", "en"),
            ("en_US", "en"),
            ("en-US", "en"),
            ("pt_BR", "pt_BR"),
            ("pt-BR", "pt_BR"),
            ("pt_br", "pt_BR"),
            ("pt", "pt_BR"),
            ("  pt-br  ", "pt_BR"),
        ],
    )
    def test_accepts_the_shapes_humans_and_env_vars_produce(self, raw, expected):
        assert i18n.normalize_language(raw) == expected

    @pytest.mark.parametrize("raw", ["", "   ", None, "klingon", "fr", "zz_ZZ"])
    def test_rejects_anything_unsupported(self, raw):
        assert i18n.normalize_language(raw) is None


class TestInstall:
    def test_returns_the_language_installed(self):
        assert i18n.install("pt_BR") == "pt_BR"
        assert i18n.get_language() == "pt_BR"

    def test_unsupported_language_degrades_to_english_without_raising(self):
        # A typo in config.local.yaml must not stop the app from opening.
        assert i18n.install("klingon") == "en"
        assert i18n.get_language() == "en"

    def test_is_idempotent_and_switchable(self):
        i18n.install("pt_BR")
        i18n.install("pt_BR")
        assert i18n.get_language() == "pt_BR"
        i18n.install("en")
        assert i18n.get_language() == "en"


class TestTranslation:
    def test_english_returns_the_msgid_unchanged(self):
        i18n.install("en")
        assert i18n._("Video Analysis") == "Video Analysis"
        assert i18n._("Restore Defaults") == "Restore Defaults"

    def test_portuguese_returns_the_catalogue_entry(self):
        i18n.install("pt_BR")
        assert i18n._("Video Analysis") == "Análise de Vídeo"
        assert i18n._("Restore Defaults") == "Restaurar Padrões"

    def test_unknown_msgid_falls_back_to_itself_in_every_language(self):
        for language in i18n.SUPPORTED_LANGUAGES:
            i18n.install(language)
            assert i18n._("a string nobody ever added") == "a string nobody ever added"

    def test_resolution_happens_per_call_not_at_import(self):
        """The property that lets UI modules import before the language is known."""
        i18n.install("en")
        assert i18n._("Cancel") == "Cancel"
        i18n.install("pt_BR")
        assert i18n._("Cancel") == "Cancelar"


class TestDomains:
    def test_ui_and_reporter_catalogues_are_separate_but_share_the_language(self):
        i18n.install("pt_BR")
        # "Metric" lives only in the reporter domain.
        assert i18n.translate("Metric", domain=i18n.REPORTER_DOMAIN) == "Métrica"
        assert i18n.translate("Metric", domain=i18n.UI_DOMAIN) == "Metric"

    def test_reporter_module_follows_the_installed_language(self):
        """Reports used to follow the OS locale and freeze at import time."""
        i18n.install("en")
        assert reporter_gettext("Quality Metrics") == "Quality Metrics"
        i18n.install("pt_BR")
        assert reporter_gettext("Quality Metrics") == "Métricas de qualidade"


class TestLazyString:
    def test_resolves_on_each_access(self):
        label = i18n.lazy("Cancel")
        i18n.install("en")
        assert str(label) == "Cancel"
        i18n.install("pt_BR")
        assert str(label) == "Cancelar"

    def test_compares_and_formats_like_the_string_it_stands_for(self):
        i18n.install("pt_BR")
        label = i18n.lazy("Cancel")
        assert label == "Cancelar"
        assert f"[{label}]" == "[Cancelar]"
        assert len(label) == len("Cancelar")
        assert "ance" in label
        assert label + "!" == "Cancelar!"
        assert ">" + label == ">Cancelar"

    def test_delegates_str_methods(self):
        i18n.install("en")
        assert i18n.lazy("Cancel").upper() == "CANCEL"


class TestSettingsContract:
    def test_supported_languages_match_the_settings_literal(self):
        """Drift here means a config value the catalogue cannot serve."""
        from typing import get_args

        from zebtrack.settings import UISettings

        literal = UISettings.model_fields["language"].annotation
        assert set(get_args(literal)) == set(i18n.SUPPORTED_LANGUAGES)

    def test_default_language_is_english(self):
        from zebtrack.settings import UISettings

        assert UISettings().language == "en"
        assert i18n.DEFAULT_LANGUAGE == "en"

    def test_supported_languages_match_the_catalogue_directories(self):
        present = {path.name for path in i18n.LOCALES_DIR.iterdir() if path.is_dir()}
        present.discard("_pairs")
        # English is the source language and deliberately has no catalogue.
        assert present == set(i18n.SUPPORTED_LANGUAGES) - {"en"}
