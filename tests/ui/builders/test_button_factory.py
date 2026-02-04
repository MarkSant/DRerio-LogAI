"""Tests for ButtonFactory."""

from collections.abc import Callable
from typing import Any, cast
from unittest.mock import Mock

import pytest

from zebtrack.ui.builders.button_factory import ButtonFactory


@pytest.mark.gui
def test_create_project_action_buttons(tkinter_root):
    commands: dict[str, Mock] = {
        "calibration": Mock(),
        "single_analysis": Mock(),
        "live_camera": Mock(),
        "create_project": Mock(),
        "open_project": Mock(),
    }

    frame = ButtonFactory.create_project_action_buttons(
        tkinter_root, cast(dict[str, Callable[[], None]], commands)
    )

    buttons = frame.winfo_children()
    assert len(buttons) == 5
    texts = [btn.cget("text") for btn in buttons]
    assert "Calibração Global (Pesos e Diagnóstico)..." in texts
    assert "Analisar Vídeo Único" in texts
    assert "Analisar Câmera ao Vivo" in texts
    assert "Criar Novo Projeto" in texts
    assert "Abrir Projeto Existente" in texts

    for btn in buttons:
        cast(Any, btn).invoke()

    commands["calibration"].assert_called_once()
    commands["single_analysis"].assert_called_once()
    commands["live_camera"].assert_called_once()
    commands["create_project"].assert_called_once()
    commands["open_project"].assert_called_once()


@pytest.mark.gui
def test_create_floating_drawing_buttons(tkinter_root):
    commands: dict[str, Mock] = {"undo": Mock(), "redo": Mock()}

    frame = ButtonFactory.create_floating_drawing_buttons(
        tkinter_root, cast(dict[str, Callable[[], None]], commands)
    )

    buttons = frame.winfo_children()
    assert len(buttons) == 2
    texts = [btn.cget("text") for btn in buttons]
    assert "↶ Desfazer (Ctrl+Z)" in texts
    assert "↷ Refazer (Ctrl+Y)" in texts

    for btn in buttons:
        cast(Any, btn).invoke()

    commands["undo"].assert_called_once()
    commands["redo"].assert_called_once()
