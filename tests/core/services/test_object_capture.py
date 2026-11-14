"""``should_capture_objects`` — the single rule for the ``3c_Objetos_`` sidecar (ADR-010).

The sidecar is ON by default for every real ``Settings``. The rule only says yes
when the kill switch is a real ``bool`` set to ``True``: a test double that never
configured it (``MagicMock`` auto-attributes, a bare ``SimpleNamespace``) is not
an operator decision, and writing a sidecar for it would scatter files through
unrelated tests.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from tests.helpers.prerecorded_pipeline import load_pristine_settings

from zebtrack.core.services.object_capture import should_capture_objects


class TestRealSettings:
    def test_default_settings_capture_objects(self):
        settings = load_pristine_settings()

        assert settings.recorder.persist_object_sidecar is True
        assert should_capture_objects(settings) is True

    def test_kill_switch_off_disables_capture(self):
        settings = load_pristine_settings()
        settings.recorder.persist_object_sidecar = False

        assert should_capture_objects(settings) is False


class TestDegradedInputs:
    def test_no_settings_never_captures(self):
        assert should_capture_objects(None) is False

    def test_mock_settings_never_capture(self):
        """A ``MagicMock`` flag is truthy but nobody configured it."""
        assert should_capture_objects(MagicMock()) is False

    def test_settings_without_a_recorder_section_never_capture(self):
        assert should_capture_objects(SimpleNamespace()) is False

    def test_recorder_section_without_the_flag_never_captures(self):
        assert should_capture_objects(SimpleNamespace(recorder=SimpleNamespace())) is False

    @pytest.mark.parametrize("value", ["yes", 1, "True"])
    def test_non_bool_flag_is_not_an_operator_decision(self, value):
        settings = SimpleNamespace(recorder=SimpleNamespace(persist_object_sidecar=value))

        assert should_capture_objects(settings) is False

    def test_explicit_true_on_a_plain_namespace_captures(self):
        settings = SimpleNamespace(recorder=SimpleNamespace(persist_object_sidecar=True))

        assert should_capture_objects(settings) is True

    def test_explicit_false_on_a_plain_namespace_does_not_capture(self):
        settings = SimpleNamespace(recorder=SimpleNamespace(persist_object_sidecar=False))

        assert should_capture_objects(settings) is False
