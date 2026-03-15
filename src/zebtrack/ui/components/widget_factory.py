"""WidgetFactory facade for UI builders."""

from __future__ import annotations

from zebtrack.settings import Settings
from zebtrack.ui.builders.analysis_widgets import AnalysisWidgetsBuilder
from zebtrack.ui.builders.common_widgets import STATUS_SYMBOLS, CommonWidgetsBuilder
from zebtrack.ui.builders.project_widgets import ProjectWidgetsBuilder
from zebtrack.ui.builders.zone_widgets import ZoneWidgetsBuilder


class WidgetFactory:
    """Thin facade that delegates widget creation to domain builders."""

    def __init__(self, gui, settings_obj: Settings | None = None, *, dialog_manager=None):
        self.gui = gui
        self._settings = settings_obj
        self._dialog_manager = dialog_manager

        self._common_builder = CommonWidgetsBuilder(gui, settings_obj, dialog_manager)
        self._zone_builder = ZoneWidgetsBuilder(gui, self._common_builder)
        self._analysis_builder = AnalysisWidgetsBuilder(
            gui, self._common_builder, settings_obj, dialog_manager
        )
        self._project_builder = ProjectWidgetsBuilder(
            gui, self._common_builder, self._analysis_builder, self._zone_builder
        )

    @property
    def dialog_manager(self):
        """Return injected DialogManager or fall back to gui.dialog_manager."""
        return self._dialog_manager or self.gui.dialog_manager

    def __getattr__(self, name):
        for builder in (
            self._common_builder,
            self._zone_builder,
            self._analysis_builder,
            self._project_builder,
        ):
            if hasattr(builder, name):
                return getattr(builder, name)
        raise AttributeError(f"{type(self).__name__} has no attribute {name!r}")


__all__ = ["STATUS_SYMBOLS", "WidgetFactory"]
