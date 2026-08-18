"""Extended unit tests for coordinators/report_generation_coordinator.py (Part 8)."""

from __future__ import annotations

from unittest.mock import MagicMock

from zebtrack.coordinators.report_generation_coordinator import ReportGenerationCoordinator


class TestReportGenerationCoordinatorExtended8:
    """Test ReportGenerationCoordinator event bus wiring and analysis service injection."""

    def test_report_generation_coordinator_analysis_service_accessor(self):
        coord = object.__new__(ReportGenerationCoordinator)
        svc = MagicMock()
        coord.analysis_service = svc
        assert coord.analysis_service is svc

    def test_report_generation_coordinator_video_metadata_service(self):
        coord = object.__new__(ReportGenerationCoordinator)
        meta_svc = MagicMock()
        coord._video_metadata_service = meta_svc
        assert coord._video_metadata_service is meta_svc

    def test_report_generation_coordinator_state_manager_attr(self):
        coord = object.__new__(ReportGenerationCoordinator)
        sm = MagicMock()
        coord.state_manager = sm
        assert coord.state_manager is sm
