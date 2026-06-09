"""Tests for ``ProjectInitializer._sync_aquarium_count_from_project``.

Regression: stale multi-aquarium UI state leaked across projects. A
pre-recorded 2-aquarium test left ``zone_controls.aquarium_count_var`` at 2;
a newly created 1-aquarium live project then went down the multi-aquarium
arena-save path. The sync resets the aquarium count (UI var + settings) to the
loaded project's ``calibration.num_aquariums`` on every project load.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from zebtrack.ui.components.project_initializer import ProjectInitializer


def _make_gui() -> MagicMock:
    gui = MagicMock()
    gui.zone_controls = MagicMock()
    gui.settings = MagicMock()
    gui.settings.analysis_config = MagicMock()
    return gui


def _make_pm(num_aquariums, project_type: str = "live") -> MagicMock:
    pm = MagicMock()
    if num_aquariums is None:
        pm.project_data = {}
    else:
        pm.project_data = {"calibration": {"num_aquariums": num_aquariums}}
    pm.get_project_type.return_value = project_type
    return pm


def test_sync_resets_stale_count_to_single():
    """A var de UI vazada em 2 volta a 1 num projeto de 1 aquário."""
    gui = _make_gui()
    pi = ProjectInitializer(gui)
    pm = _make_pm(1)

    pi._sync_aquarium_count_from_project(pm)

    gui.zone_controls.set_aquarium_count.assert_called_once_with(1)
    assert gui.settings.analysis_config.num_aquariums == 1


def test_sync_preserves_multi_aquarium_project():
    """Projeto de 2 aquários mantém a contagem em 2."""
    gui = _make_gui()
    pi = ProjectInitializer(gui)
    pm = _make_pm(2)

    pi._sync_aquarium_count_from_project(pm)

    gui.zone_controls.set_aquarium_count.assert_called_once_with(2)
    assert gui.settings.analysis_config.num_aquariums == 2


def test_sync_defaults_to_one_when_calibration_missing():
    """Sem calibration.num_aquariums, assume 1 (single)."""
    gui = _make_gui()
    pi = ProjectInitializer(gui)
    pm = _make_pm(None)

    pi._sync_aquarium_count_from_project(pm)

    gui.zone_controls.set_aquarium_count.assert_called_once_with(1)
    assert gui.settings.analysis_config.num_aquariums == 1


def test_sync_no_zone_controls_is_noop_safe():
    """Sem zone_controls (ainda não criado), não quebra e sincroniza settings."""
    gui = _make_gui()
    gui.zone_controls = None
    pi = ProjectInitializer(gui)
    pm = _make_pm(1)

    pi._sync_aquarium_count_from_project(pm)  # não deve levantar

    assert gui.settings.analysis_config.num_aquariums == 1
