"""Tests for ``ui/wizard/design_editor_dialog.py``.

The dialog is a modal ``simpledialog.Dialog``; these tests build it with
``object.__new__`` and drive its real methods with the widgets they touch
replaced, so no window is shown. Close validation lives in
``tests/ui/dialogs/test_project_video_import_dialog_extended.py``.
"""

from __future__ import annotations

import tkinter
from typing import Any
from unittest.mock import Mock

import pytest

import zebtrack.ui.wizard.design_editor_dialog as module
from zebtrack.ui.wizard.design_editor_dialog import DesignEditorDialog


def _bare_editor() -> DesignEditorDialog:
    return object.__new__(DesignEditorDialog)


class TestLoadDesign:
    def test_design_is_loaded_even_when_the_scroll_reset_fails(self):
        """F2 pragma review: a canvas that refuses ``yview_moveto`` must not lose the design."""
        editor = _bare_editor()
        editor.groups_canvas = Mock()
        editor.groups_canvas.yview_moveto.side_effect = tkinter.TclError("bad window path")

        editor._load_design(
            {
                "groups": ["G1", "G2"],
                "days": ["Dia_1"],
                "group_display_names": {"G1": "Controle"},
            }
        )

        editor.groups_canvas.yview_moveto.assert_called_once_with(0)
        assert editor.groups == ["G1", "G2"]
        assert editor.days == ["Dia_1"]
        assert editor.group_display_names == {"G1": "Controle", "G2": "G2"}


class _FakeRegexDialog:
    result: dict[str, Any] | None = None

    def __init__(self, parent: Any, patterns: dict, *, sample_paths: list[str]) -> None:
        self.patterns = patterns

    def get_result(self) -> dict[str, Any] | None:
        return _FakeRegexDialog.result


class TestCustomRegexCallback:
    @pytest.fixture
    def warnings(self, monkeypatch: pytest.MonkeyPatch) -> list[str]:
        shown: list[str] = []
        monkeypatch.setattr(module, "CustomRegexDialog", _FakeRegexDialog)
        monkeypatch.setattr(
            module.messagebox, "showwarning", lambda title, message, **_kw: shown.append(title)
        )
        return shown

    @staticmethod
    def _editor(callback: Any) -> DesignEditorDialog:
        editor = _bare_editor()
        editor.custom_regex_patterns = None
        editor.sample_paths = ["Controle/Dia_1/S1.mp4"]
        editor.on_custom_regex_configured = callback
        editor._load_design({"groups": ["Old"]})
        return editor

    def test_failing_detection_keeps_the_patterns_and_warns(self, warnings):
        """F2 pragma review: a callback that raises reads as "no design found", not a crash."""
        _FakeRegexDialog.result = {"group_pattern": r"(Controle|Tratado)", "day_pattern": ""}

        def failing_callback(patterns: dict) -> dict:
            raise ValueError("regex matched nothing usable")

        editor = self._editor(failing_callback)

        editor._open_custom_regex_dialog()

        assert editor.custom_regex_patterns == _FakeRegexDialog.result
        assert editor.groups == []
        assert warnings == ["Regex with no results"]

    def test_successful_detection_replaces_the_design(self, warnings):
        _FakeRegexDialog.result = {"group_pattern": r"(Controle|Tratado)"}
        editor = self._editor(lambda patterns: {"groups": ["Controle", "Tratado"]})

        editor._open_custom_regex_dialog()

        assert editor.groups == ["Controle", "Tratado"]
        assert warnings == []
