from types import SimpleNamespace
from typing import cast

import pytest

from zebtrack.ui.gui import ApplicationGUI


class _NotebookStub:
    def __init__(self, current: str):
        self.current = current
        self.selected_history: list[str] = []

    def select(self, tab_id: str | None = None) -> str:
        if tab_id is None:
            return self.current
        self.current = tab_id
        self.selected_history.append(tab_id)
        return self.current


def test_on_tab_changed_reverts_when_pending_edit_cancelled() -> None:
    zone_tab_id = "zone-tab"
    target_tab_id = "analysis-tab"

    notebook = _NotebookStub(current=target_tab_id)
    app = SimpleNamespace(
        notebook=notebook,
        analysis_tab_frame=target_tab_id,
        zone_tab_frame=zone_tab_id,
        analysis_active=False,
        _last_selected_tab_id=zone_tab_id,
    )

    app._confirm_pending_zone_edit_before_navigation = lambda **_: False
    app._refresh_roi_templates = lambda *_, **__: None

    ApplicationGUI._on_tab_changed(cast(ApplicationGUI, app), event=None)

    assert notebook.current == zone_tab_id
    assert notebook.selected_history == [zone_tab_id]
    assert app._last_selected_tab_id == zone_tab_id


@pytest.mark.parametrize("decision", ["save", "discard"])
def test_on_tab_changed_keeps_target_tab_when_pending_edit_confirmed(decision: str) -> None:
    zone_tab_id = "zone-tab"
    target_tab_id = "analysis-tab"

    notebook = _NotebookStub(current=target_tab_id)
    app = SimpleNamespace(
        notebook=notebook,
        analysis_tab_frame=target_tab_id,
        zone_tab_frame=zone_tab_id,
        analysis_active=False,
        _last_selected_tab_id=zone_tab_id,
    )

    if decision == "save":
        app._confirm_pending_zone_edit_before_navigation = lambda **_: True
    else:
        app._confirm_pending_zone_edit_before_navigation = lambda **_: True

    app._refresh_roi_templates = lambda *_, **__: None

    ApplicationGUI._on_tab_changed(cast(ApplicationGUI, app), event=None)

    assert notebook.current == target_tab_id
    assert notebook.selected_history == []
    assert app._last_selected_tab_id == target_tab_id
