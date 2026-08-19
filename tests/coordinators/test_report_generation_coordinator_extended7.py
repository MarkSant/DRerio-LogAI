"""Extended unit tests for coordinators/report_generation_coordinator.py (Part 7)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from zebtrack.coordinators.report_generation_coordinator import ReportGenerationCoordinator


class TestReportGenerationCoordinatorExtended7:
    """Test ReportGenerationCoordinator dependency injection and trajectory read delegations."""

    def test_report_generation_coordinator_init_attributes(self):
        state_mgr = MagicMock()
        pm = MagicMock()
        settings = MagicMock()
        analysis_svc = MagicMock()
        event_bus = MagicMock()
        traj_svc = MagicMock()
        extractor = MagicMock()

        coord = ReportGenerationCoordinator(
            state_manager=state_mgr,
            project_manager=pm,
            settings_obj=settings,
            analysis_service=analysis_svc,
            event_bus=event_bus,
            trajectory_data_service=traj_svc,
            video_frame_extractor=extractor,
        )

        assert coord.state_manager is state_mgr
        assert coord.project_manager is pm
        assert coord.settings is settings
        assert coord.analysis_service is analysis_svc
        assert coord.event_bus is event_bus
        assert coord._trajectory_data_service is traj_svc
        assert coord._frame_extractor is extractor
        assert coord._progress_coordinator is None

    def test_read_trajectory_delegates_to_trajectory_data_service(self):
        state_mgr = MagicMock()
        pm = MagicMock()
        settings = MagicMock()
        traj_svc = MagicMock()
        traj_svc.load_trajectory.return_value = "dummy_df"

        coord = ReportGenerationCoordinator(
            state_manager=state_mgr,
            project_manager=pm,
            settings_obj=settings,
            trajectory_data_service=traj_svc,
        )

        df = coord._read_trajectory(Path("/data/traj.parquet"))
        assert df == "dummy_df"
        traj_svc.load_trajectory.assert_called_once_with(str(Path("/data/traj.parquet")))
