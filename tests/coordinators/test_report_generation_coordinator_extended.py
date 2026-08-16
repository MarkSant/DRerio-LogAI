"""Extended unit tests for ReportGenerationCoordinator."""

from __future__ import annotations

from unittest.mock import MagicMock

from zebtrack.coordinators.report_generation_coordinator import ReportGenerationCoordinator
from zebtrack.settings import load_settings


class TestReportGenerationCoordinatorExtended:
    """Test coordinator initialization, dependencies injection, and helper functions."""

    def test_initialization(self):
        state_mgr = MagicMock()
        project_mgr = MagicMock()
        settings = load_settings()
        event_bus = MagicMock()

        coord = ReportGenerationCoordinator(
            state_manager=state_mgr,
            project_manager=project_mgr,
            settings_obj=settings,
            event_bus=event_bus,
        )

        assert coord.state_manager is state_mgr
        assert coord.project_manager is project_mgr
        assert coord.settings is settings
        assert coord.event_bus is event_bus
        assert coord.analysis_service is None
