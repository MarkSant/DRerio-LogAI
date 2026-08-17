"""Extended unit tests for coordinators/report_generation_coordinator.py."""

from __future__ import annotations

from unittest.mock import MagicMock

import pandas as pd

from zebtrack.coordinators.report_generation_coordinator import ReportGenerationCoordinator


class TestReportGenerationCoordinatorExtended:
    """Test ReportGenerationCoordinator initialization, batch checks, and report base naming."""

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
