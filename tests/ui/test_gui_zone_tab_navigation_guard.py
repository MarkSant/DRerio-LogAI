from types import SimpleNamespace

import pytest

from zebtrack.ui.components.zone_edit_guard import ZoneEditGuard


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


def _make_guard(app: SimpleNamespace, *, confirm_result: bool) -> ZoneEditGuard:
    """Create a ZoneEditGuard wired to *app* with a stubbed confirm method."""
    guard = ZoneEditGuard.__new__(ZoneEditGuard)
    guard.gui = app  # type: ignore[assignment]
    guard.confirm_pending_zone_edit_before_navigation = lambda **_: confirm_result  # type: ignore[assignment]
    return guard


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

    guard = _make_guard(app, confirm_result=False)
    app.zone_edit_guard = guard
    app.roi_template_manager = SimpleNamespace(refresh_templates=lambda: None)

    guard.on_tab_changed(event=None)

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

    guard = _make_guard(app, confirm_result=True)
    app.zone_edit_guard = guard
    app.roi_template_manager = SimpleNamespace(refresh_templates=lambda: None)

    guard.on_tab_changed(event=None)

    assert notebook.current == target_tab_id
    assert notebook.selected_history == []
    assert app._last_selected_tab_id == target_tab_id
