from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from zebtrack.coordinators.live_batch_coordinator import BatchMetadata, LiveBatchCoordinator
from zebtrack.ui.event_bus_v2 import UIEvents


@pytest.fixture
def mock_project_manager():
    pm = MagicMock()
    pm.project_data = {"batches": []}
    return pm


@pytest.fixture
def mock_analysis_service():
    return MagicMock()


@pytest.fixture
def mock_state_manager():
    return MagicMock()


@pytest.fixture
def mock_settings():
    return MagicMock()


@pytest.fixture
def mock_event_bus():
    return MagicMock()


@pytest.fixture
def coordinator(
    mock_project_manager,
    mock_analysis_service,
    mock_state_manager,
    mock_settings,
    mock_event_bus,
):
    return LiveBatchCoordinator(
        project_manager=mock_project_manager,
        analysis_service=mock_analysis_service,
        state_manager=mock_state_manager,
        settings_obj=mock_settings,
        event_bus=mock_event_bus,
    )


def test_batch_metadata_key():
    metadata = BatchMetadata(batch_id="1", group="G1", day="Day1", subject_id="S1")
    assert metadata.batch_key == "G1_Day1_S1"

    metadata_none = BatchMetadata(batch_id="2", group=None, day=None, subject_id=None)
    assert metadata_none.batch_key == "no_group_no_day_no_subject"


def test_register_session(coordinator):
    metadata = {"group": "G1", "day": "Day1", "subject_id": "S1"}
    video_path = Path("test.mp4")

    # Call
    batch_id = coordinator.register_session("exp1", video_path, metadata)

    assert "batch_" in batch_id

    # Second session same batch
    batch_id2 = coordinator.register_session("exp2", video_path, metadata)
    assert batch_id == batch_id2

    batch = coordinator.get_batch_for_session("exp1")
    assert batch is not None
    assert batch.session_count == 2
    assert "exp1" in batch.completed_sessions
    assert "exp2" in batch.completed_sessions

    active = coordinator.get_active_batches()
    assert len(active) == 1
    assert active[0].batch_id == batch_id


def test_register_session_persistence_exception(coordinator):
    metadata = {"group": "G1", "day": "Day1", "subject_id": "S1"}
    video_path = Path("test.mp4")

    # Force failure in _persist_session_to_project_data
    coordinator._persist_session_to_project_data = MagicMock(
        side_effect=Exception("Database error")
    )

    # It should not raise an exception
    batch_id = coordinator.register_session("exp1", video_path, metadata)
    assert batch_id is not None
    assert coordinator.get_batch_for_session("exp1") is not None


def test_mark_batch_complete_not_found(coordinator):
    assert not coordinator.mark_batch_complete("non_existent")


def test_mark_batch_complete_already_done(coordinator):
    metadata = {"group": "G1", "day": "Day1", "subject_id": "S1"}
    batch_id = coordinator.register_session("exp1", Path("test.mp4"), metadata)

    batch = coordinator._find_batch_by_id(batch_id)
    batch.is_complete = True

    assert coordinator.mark_batch_complete(batch_id) is True
    # Unified report should not be called
    coordinator.analysis_service.aggregate_session_summaries.assert_not_called()


@patch("zebtrack.coordinators.live_batch_coordinator.LiveBatchCoordinator._generate_unified_report")
def test_mark_batch_complete_success(mock_generate, coordinator):
    mock_generate.return_value = True
    metadata = {"group": "G1", "day": "Day1", "subject_id": "S1"}
    batch_id = coordinator.register_session("exp1", Path("test.mp4"), metadata)

    assert coordinator.mark_batch_complete(batch_id) is True

    batch = coordinator._find_batch_by_id(batch_id)
    assert batch.is_complete
    assert batch.completed_at is not None

    # Check event
    coordinator.event_bus.publish.assert_called_once()
    event = coordinator.event_bus.publish.call_args[0][0]
    assert event.type == UIEvents.BATCH_ANALYSIS_COMPLETED
    assert event.data.batch_id == batch_id


@patch("zebtrack.coordinators.live_batch_coordinator.LiveBatchCoordinator._generate_unified_report")
def test_mark_batch_complete_failure(mock_generate, coordinator):
    mock_generate.return_value = False
    metadata = {"group": "G1", "day": "Day1", "subject_id": "S1"}
    batch_id = coordinator.register_session("exp1", Path("test.mp4"), metadata)

    assert coordinator.mark_batch_complete(batch_id) is False

    batch = coordinator._find_batch_by_id(batch_id)
    assert not batch.is_complete
    coordinator.event_bus.publish.assert_not_called()


def test_normalize_day_key():
    assert LiveBatchCoordinator._normalize_day_key("Dia 1") == "1"
    assert LiveBatchCoordinator._normalize_day_key("Dia_02") == "2"
    assert LiveBatchCoordinator._normalize_day_key(5) == "5"
    assert LiveBatchCoordinator._normalize_day_key("control") == "control"
    assert LiveBatchCoordinator._normalize_day_key("") == ""
    assert LiveBatchCoordinator._normalize_day_key(None) == ""


def test_mark_block_complete(coordinator):
    metadata = {"group": "G1", "day": "Dia 1", "subject_id": "S1"}
    batch_id = coordinator.register_session("exp1", Path("test.mp4"), metadata)

    coordinator.project_manager.register_batch_outputs.return_value = True

    result = coordinator.mark_block_complete(
        "G1", "Dia 1", unified_excel="report.xlsx", session_count=1
    )

    assert result is True
    batch = coordinator._find_batch_by_id(batch_id)
    assert batch.is_complete

    coordinator.project_manager.register_batch_outputs.assert_called_once_with(
        batch_id=batch_id, unified_excel="report.xlsx", session_count=1, group="G1", day="Dia 1"
    )

    coordinator.event_bus.publish.assert_called()


def test_mark_block_complete_no_active_batch(coordinator):
    coordinator.project_manager.register_batch_outputs.return_value = True

    result = coordinator.mark_block_complete(
        "G1", "Dia 1", unified_excel="report.xlsx", session_count=1
    )

    assert result is True
    coordinator.project_manager.register_batch_outputs.assert_called_once()

    # Extracted batch_id from the call args should contain the timestamp
    args, kwargs = coordinator.project_manager.register_batch_outputs.call_args
    assert "manual_G1_Dia1_" in kwargs["batch_id"]


@patch("zebtrack.coordinators.live_batch_coordinator.find_summary_excel_file")
def test_resolve_summary_excel_path(mock_find):
    mock_find.return_value = Path("fallback.xlsx")

    # Direct
    assert LiveBatchCoordinator._resolve_summary_excel_path(
        {"summary_excel": "direct.xlsx"}
    ) == Path("direct.xlsx")

    # Parquet
    assert LiveBatchCoordinator._resolve_summary_excel_path(
        {"parquet_files": {"summary_excel": "parquet.xlsx"}}
    ) == Path("parquet.xlsx")

    # Fallback
    assert LiveBatchCoordinator._resolve_summary_excel_path({}) == Path("fallback.xlsx")


def test_persist_session_to_project_data(coordinator):
    coordinator.project_manager.project_data = {"batches": []}

    video_path = Path("fake_dir/test.mp4")
    metadata = {"group": "G1", "day": "Day1", "subject_id": "S1", "timestamp": "123"}

    coordinator._persist_session_to_project_data(
        experiment_id="exp1", video_path=video_path, metadata=metadata
    )

    assert len(coordinator.project_manager.project_data["batches"]) == 1
    batch = coordinator.project_manager.project_data["batches"][0]
    assert batch["videos"][0]["path"] == "fake_dir/test.mp4"
    assert batch["videos"][0]["metadata"]["group"] == "G1"

    coordinator.project_manager.save_project.assert_called_once()


def test_persist_session_to_project_data_cancelled(coordinator):
    with patch("pathlib.Path.exists") as mock_exists:
        # Simulate .cancelled file exists
        mock_exists.return_value = True

        video_path = Path("fake_dir/test.mp4")
        coordinator._persist_session_to_project_data(
            experiment_id="exp1", video_path=video_path, metadata={}
        )

        # Should return early
        assert coordinator.project_manager.project_data["batches"] == []


def test_persist_session_to_project_data_no_project_data(coordinator):
    coordinator.project_manager.project_data = None

    coordinator._persist_session_to_project_data(
        experiment_id="exp1", video_path=Path("test.mp4"), metadata={}
    )

    coordinator.project_manager.save_project.assert_not_called()


def test_persist_session_to_project_data_existing(coordinator):
    coordinator.project_manager.project_data = {
        "batches": [{"videos": [{"path": "fake_dir/test.mp4", "status": "recorded"}]}]
    }

    video_path = Path("fake_dir/test.mp4")
    metadata = {"group": "G1"}

    coordinator._persist_session_to_project_data(
        experiment_id="exp1", video_path=video_path, metadata=metadata
    )

    batch = coordinator.project_manager.project_data["batches"][0]
    # Status should be updated, and metadata merged
    assert batch["videos"][0]["status"] == "recorded"
    assert batch["videos"][0]["metadata"]["group"] == "G1"


class TestUnifiedReportGeneration:
    def test_generate_unified_report_no_videos(self, coordinator):
        batch = BatchMetadata(batch_id="b1", group="G", day="1", subject_id="S", session_paths=[])
        assert coordinator._generate_unified_report(batch) is False

    def test_generate_unified_report_no_project_root(self, coordinator):
        coordinator.project_manager.project_root = None
        coordinator.project_manager.project_path = None
        batch = BatchMetadata(
            batch_id="b1", group="G", day="1", subject_id="S", session_paths=[Path("v1.mp4")]
        )
        assert coordinator._generate_unified_report(batch) is False

    def test_generate_unified_report_no_summaries(self, coordinator, tmp_path):
        coordinator.project_manager.project_root = tmp_path
        coordinator.project_manager.find_video_entry.return_value = None
        batch = BatchMetadata(
            batch_id="b1", group="G", day="1", subject_id="S", session_paths=[Path("v1.mp4")]
        )
        assert coordinator._generate_unified_report(batch) is False

    def test_generate_unified_report_success(self, coordinator, tmp_path):
        coordinator.project_manager.project_root = tmp_path
        coordinator.project_manager.find_video_entry.return_value = {
            "summary_excel": str(tmp_path / "summary.xlsx")
        }
        batch = BatchMetadata(
            batch_id="b1", session_paths=[Path("v1.mp4")], group="G1", day="1", subject_id="S1"
        )

        with patch.object(
            coordinator, "_resolve_summary_excel_path", return_value=tmp_path / "summary.xlsx"
        ):
            ok = coordinator._generate_unified_report(batch)
            assert ok is True
            coordinator.analysis_service.aggregate_session_summaries.assert_called_once()
            coordinator.project_manager.register_batch_outputs.assert_called_once()


class TestCollectMultiAquariumOutputs:
    def test_collect_none_or_missing_dir(self):
        assert LiveBatchCoordinator._collect_multi_aquarium_outputs(None, {}) == {}
        assert LiveBatchCoordinator._collect_multi_aquarium_outputs(Path("/nonexistent"), {}) == {}

    def test_collect_with_aquarium_subdirectories(self, tmp_path):
        aq1 = tmp_path / "aquarium_1"
        aq1.mkdir()
        (aq1 / "1_ProcessingArea_test.parquet").write_text("data")

        outputs = LiveBatchCoordinator._collect_multi_aquarium_outputs(
            tmp_path, {"group": "G1", "subject_id": "S1", "day": 1}
        )
        assert 0 in outputs
        assert outputs[0]["group"] == "G1"
        assert outputs[0]["subject_id"] == "S1"
