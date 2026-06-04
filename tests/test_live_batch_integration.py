"""Integration tests for LiveBatchCoordinator with wizard workflow (v2.3.0)."""

from datetime import datetime
from unittest.mock import MagicMock

from pandas import DataFrame

from zebtrack.coordinators.live_batch_coordinator import LiveBatchCoordinator
from zebtrack.coordinators.live_camera_session_coordinator import LiveCameraSessionCoordinator


def test_wizard_to_batch_coordinator_flow(test_settings, tmp_path):
    """Test complete flow from wizard metadata to batch report.

    Simulates user filling wizard with experimental metadata and verifies
    that batch coordinator correctly groups sessions by group/day/*.
    Each subject creates a separate session but they share the same batch.
    """
    # Setup
    batch_coord = LiveBatchCoordinator(
        project_manager=MagicMock(),
        analysis_service=MagicMock(),
        state_manager=MagicMock(),
        settings_obj=test_settings,
    )

    # Simulate 3 sessions from wizard with same group/day
    # Note: Batch key is group_day_*, so all these sessions should be in different batches
    # since LiveBatchCoordinator uses actual subject_id in key construction
    wizard_sessions = [
        {
            "experimental_group": "Controle",
            "experiment_day": "Dia_1",
            "subject_id": "Peixe_01",
            "is_batch_last_session": False,
        },
        {
            "experimental_group": "Controle",
            "experiment_day": "Dia_1",
            "subject_id": "Peixe_01",  # Same subject = same batch
            "is_batch_last_session": False,
        },
        {
            "experimental_group": "Controle",
            "experiment_day": "Dia_1",
            "subject_id": "Peixe_01",  # Same subject = same batch
            "is_batch_last_session": True,  # ← Last session
        },
    ]

    batch_ids = []
    for i, session in enumerate(wizard_sessions):
        # Transform wizard field names to batch metadata keys (like SessionCoordinator does)
        metadata = {
            "group": session["experimental_group"],
            "day": session["experiment_day"],
            "subject_id": session["subject_id"],
            "timestamp": datetime.now().isoformat(),
        }

        batch_id = batch_coord.register_session(
            experiment_id=f"exp_{session['subject_id']}_{i}",
            video_path=tmp_path / f"{session['subject_id']}_{i}.mp4",
            metadata=metadata,
        )
        batch_ids.append(batch_id)

    # Assert: All sessions in same batch (same group/day/subject)
    assert len(set(batch_ids)) == 1, "All sessions should have same batch_id"

    # Assert: Batch has correct session count
    # Batch key format: {group}_{day}_{subject}
    batch_key = "Controle_Dia_1_Peixe_01"
    batch = batch_coord._active_batches.get(batch_key)
    assert batch is not None, (
        f"Batch not found. Available batches: {list(batch_coord._active_batches.keys())}"
    )
    assert batch.session_count == 3


def test_session_coordinator_batch_registration(test_settings, tmp_path):
    """Test LiveCameraSessionCoordinator correctly registers sessions with batch coordinator."""
    # Setup mocks
    mock_live_camera_service = MagicMock()
    mock_live_camera_service.current_output_dir = tmp_path
    mock_project_manager = MagicMock()
    mock_detector_service = MagicMock()

    # Create batch coordinator
    mock_analysis_service = MagicMock()
    batch_coord = LiveBatchCoordinator(
        project_manager=mock_project_manager,
        analysis_service=mock_analysis_service,
        state_manager=MagicMock(),
        settings_obj=test_settings,
    )

    # Create live camera session coordinator with batch coordinator
    session_coord = LiveCameraSessionCoordinator(
        state_manager=MagicMock(),
        live_camera_service=mock_live_camera_service,
        project_manager=mock_project_manager,
        detector_service=mock_detector_service,
        settings_obj=test_settings,
        live_calibration_coordinator=MagicMock(),
        live_batch_coordinator=batch_coord,
    )

    # Simulate wizard data with batch metadata
    wizard_data = {
        "experimental_group": "Tratado",
        "experiment_day": "Dia_2",
        "subject_id": "Peixe_05",
        "is_batch_last_session": False,
        "recording_duration_s": 300.0,
        "camera_index": 0,
    }

    # Create mock video file
    video_file = tmp_path / "live_recording.mp4"
    video_file.touch()

    # Start session with wizard data
    session_coord._active_live_session_id = "test_session_001"
    session_coord._active_wizard_data = wizard_data

    # Mock stop_session to return success
    mock_live_camera_service.stop_session.return_value = True

    # Stop session (should trigger batch registration)
    success = session_coord.stop_live_session()

    assert success
    # Verify batch was registered - batch key format: {group}_{day}_{subject_id}
    batch_key = "Tratado_Dia_2_Peixe_05"
    assert batch_key in batch_coord._active_batches
    assert batch_coord._active_batches[batch_key].session_count == 1


def test_batch_metadata_incomplete_skips_registration(test_settings, tmp_path):
    """Test that incomplete batch metadata skips registration gracefully."""
    # Setup mocks
    mock_live_camera_service = MagicMock()
    mock_live_camera_service.current_output_dir = tmp_path
    mock_project_manager = MagicMock()
    mock_detector_service = MagicMock()
    mock_analysis_service = MagicMock()

    batch_coord = LiveBatchCoordinator(
        project_manager=mock_project_manager,
        analysis_service=mock_analysis_service,
        state_manager=MagicMock(),
        settings_obj=test_settings,
    )

    session_coord = LiveCameraSessionCoordinator(
        state_manager=MagicMock(),
        live_camera_service=mock_live_camera_service,
        project_manager=mock_project_manager,
        detector_service=mock_detector_service,
        settings_obj=test_settings,
        live_calibration_coordinator=MagicMock(),
        live_batch_coordinator=batch_coord,
    )

    # Incomplete wizard data (missing subject_id)
    wizard_data = {
        "experimental_group": "Controle",
        "experiment_day": "Dia_1",
        "subject_id": None,  # Missing!
        "is_batch_last_session": False,
    }

    session_coord._active_live_session_id = "test_session_002"
    session_coord._active_wizard_data = wizard_data
    mock_live_camera_service.stop_session.return_value = True

    # Should not raise error, just skip registration
    success = session_coord.stop_live_session()

    assert success
    # No batch should be created
    assert len(batch_coord._active_batches) == 0


def test_multi_aquarium_batch_registration(test_settings, tmp_path):
    """Test batch registration with multi-aquarium sessions.

    Per user requirement 3: Each aquarium treated as separate subject_id.
    """
    MagicMock()
    mock_live_camera_service = MagicMock()
    mock_live_camera_service.current_output_dir = tmp_path
    mock_project_manager = MagicMock()
    MagicMock()
    MagicMock()
    mock_analysis_service = MagicMock()

    batch_coord = LiveBatchCoordinator(
        project_manager=mock_project_manager,
        analysis_service=mock_analysis_service,
        state_manager=MagicMock(),
        settings_obj=test_settings,
    )

    # Register two aquariums from same session as separate subjects
    aquarium_0_data = {
        "group": "Controle",
        "day": "Dia_1",
        "subject_id": "Peixe_01_Aquario_0",
    }

    aquarium_1_data = {
        "group": "Controle",
        "day": "Dia_1",
        "subject_id": "Peixe_01_Aquario_1",
    }

    # Create mock video files
    video_0 = tmp_path / "live_recording_aquarium_0" / "recording.mp4"
    video_0.parent.mkdir(parents=True)
    video_0.touch()

    video_1 = tmp_path / "live_recording_aquarium_1" / "recording.mp4"
    video_1.parent.mkdir(parents=True)
    video_1.touch()

    # Register both aquariums
    batch_id_0 = batch_coord.register_session(
        experiment_id="exp_multi_aquarium",
        video_path=video_0,
        metadata=aquarium_0_data,
    )

    batch_id_1 = batch_coord.register_session(
        experiment_id="exp_multi_aquarium",
        video_path=video_1,
        metadata=aquarium_1_data,
    )

    # Both should be in DIFFERENT batches (each aquarium is separate subject_id)
    assert batch_id_0 != batch_id_1

    # Each batch should have 1 session
    batch_key_0 = "Controle_Dia_1_Peixe_01_Aquario_0"
    batch_key_1 = "Controle_Dia_1_Peixe_01_Aquario_1"

    assert batch_key_0 in batch_coord._active_batches
    assert batch_key_1 in batch_coord._active_batches

    assert batch_coord._active_batches[batch_key_0].session_count == 1
    assert batch_coord._active_batches[batch_key_1].session_count == 1


def test_register_session_detects_relatorio_excel_as_summary(test_settings, tmp_path):
    project_manager = MagicMock()
    project_manager.project_data = {"batches": []}

    batch_coord = LiveBatchCoordinator(
        project_manager=project_manager,
        analysis_service=MagicMock(),
        state_manager=MagicMock(),
        settings_obj=test_settings,
    )

    (tmp_path / "4_Relatorio_live_exp.xlsx").touch()

    batch_coord.register_session(
        experiment_id="live_exp",
        video_path=tmp_path / "live_exp.mp4",
        metadata={"group": "Controle", "day": "Dia_1", "subject_id": "Peixe_01"},
    )

    entry = project_manager.project_data["batches"][0]["videos"][0]
    assert entry["has_summary"] is True


def test_generate_unified_report_uses_parquet_files_summary_excel(test_settings, tmp_path):
    project_manager = MagicMock()
    project_manager.project_root = tmp_path
    project_manager.find_video_entry.return_value = {
        "parquet_files": {"summary_excel": (tmp_path / "4_Relatorio_live_exp.xlsx").as_posix()}
    }

    analysis_service = MagicMock()
    batch_coord = LiveBatchCoordinator(
        project_manager=project_manager,
        analysis_service=analysis_service,
        state_manager=MagicMock(),
        settings_obj=test_settings,
    )

    summary_path = tmp_path / "4_Relatorio_live_exp.xlsx"
    DataFrame({"metric": [1.0]}).to_excel(summary_path, index=False)

    batch = batch_coord._active_batches.setdefault(
        "Controle_Dia_1_Peixe_01",
        batch_coord._active_batches.get("Controle_Dia_1_Peixe_01")
        or __import__(
            "zebtrack.coordinators.live_batch_coordinator",
            fromlist=["BatchMetadata"],
        ).BatchMetadata(
            batch_id="batch_1",
            group="Controle",
            day="Dia_1",
            subject_id="Peixe_01",
            session_count=1,
            session_paths=[tmp_path / "live_exp.mp4"],
        ),
    )

    assert batch_coord._generate_unified_report(batch) is True
    analysis_service.aggregate_session_summaries.assert_called_once()
    assert analysis_service.aggregate_session_summaries.call_args[0][0] == [summary_path]
