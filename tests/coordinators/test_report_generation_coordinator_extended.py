"""Extended unit tests for coordinators/report_generation_coordinator.py."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd

from zebtrack.coordinators.report_generation_coordinator import ReportGenerationCoordinator


class TestReportGenerationCoordinatorExtended:
    def test_init_and_trajectory_read_delegation(self):
        mock_state = MagicMock()
        mock_project_mgr = MagicMock()
        mock_settings = MagicMock()
        mock_traj_svc = MagicMock()
        mock_traj_svc.load_trajectory.return_value = pd.DataFrame({"x": [1, 2]})

        coord = ReportGenerationCoordinator(
            state_manager=mock_state,
            project_manager=mock_project_mgr,
            settings_obj=mock_settings,
            trajectory_data_service=mock_traj_svc,
        )

        df = coord._read_trajectory("/path/traj.parquet")
        assert len(df) == 2
        mock_traj_svc.load_trajectory.assert_called_once_with("/path/traj.parquet")

    def test_is_batch_processing(self):
        coord = object.__new__(ReportGenerationCoordinator)
        coord._progress_coordinator = None
        assert coord._is_batch_processing() is False

        mock_ptc = MagicMock()
        mock_ptc._is_batch_processing.return_value = True
        coord._progress_coordinator = mock_ptc
        assert coord._is_batch_processing() is True

    def test_generate_project_reports_empty_list_returns_early(self):
        coord = object.__new__(ReportGenerationCoordinator)
        coord.project_manager = MagicMock()

        # Empty or None video_paths should return early without errors
        coord.generate_project_reports([])
        coord.generate_project_reports(None)
        coord.project_manager.find_video_entry.assert_not_called()

    def test_build_aquarium_report_base(self):
        meta1 = {"group": "Controle", "subject": "S01", "day": "1"}
        base1 = ReportGenerationCoordinator._build_aquarium_report_base(meta1, 0)
        assert base1 == "Controle_S01_Dia1"

        meta_empty: dict = {}
        base_empty = ReportGenerationCoordinator._build_aquarium_report_base(meta_empty, 0)
        assert base_empty == "aquario_1_S01_Dia1"

        meta_special = {"group": "Tratado A/B", "subject": "Peixe 2", "day": "Dia_5"}
        base_special = ReportGenerationCoordinator._build_aquarium_report_base(meta_special, 1)
        assert base_special == "Tratado_A_B_Peixe_2_Dia5"


class TestReportGenerationCoordinatorExtended7:
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
