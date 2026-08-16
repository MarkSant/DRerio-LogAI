import threading
from unittest.mock import MagicMock, patch

import pytest

from zebtrack.coordinators.base_coordinator import CoordinatorValidationError
from zebtrack.coordinators.model_diagnostics_coordinator import (
    DiagnosticAbortError,
    ModelDiagnosticsCoordinator,
)
from zebtrack.ui.event_bus_v2 import UIEvents


@pytest.fixture
def mock_state_manager():
    return MagicMock()


@pytest.fixture
def mock_weight_manager():
    manager = MagicMock()
    manager.active_weight_name = "test_weight"
    manager.get_weight_details.return_value = {
        "path": "/path/to/best.pt",
        "openvino_path": "/path/to/openvino",
    }
    return manager


@pytest.fixture
def mock_event_bus():
    return MagicMock()


@pytest.fixture
def coordinator(mock_state_manager, mock_weight_manager, mock_event_bus):
    root = MagicMock()
    view = MagicMock()
    return ModelDiagnosticsCoordinator(
        state_manager=mock_state_manager,
        weight_manager=mock_weight_manager,
        event_bus=mock_event_bus,
        cancel_event=threading.Event(),
        root=root,
        view=view,
    )


def test_init_and_validate_dependencies(coordinator):
    assert coordinator.validate_dependencies() is True

    # Test missing dependency
    coordinator.weight_manager = None
    with pytest.raises(CoordinatorValidationError, match="WeightManager is required"):
        coordinator.validate_dependencies()


@patch("zebtrack.ui.dialogs.DiagnosticProgressDialog", autospec=True)
@patch("zebtrack.coordinators.model_diagnostics_coordinator.threading.Thread")
def test_run_model_diagnostic_success(mock_thread, mock_dialog, coordinator):
    config = {
        "video_path": "test.mp4",
        "frames_to_analyze": 10,
        "confidence_threshold": 0.5,
        "model_to_test": "YOLO (PyTorch)",
    }

    coordinator.run_model_diagnostic(config)

    mock_thread.assert_called_once()
    thread_instance = mock_thread.return_value
    thread_instance.start.assert_called_once()


@patch("zebtrack.ui.dialogs.DiagnosticProgressDialog", autospec=True)
def test_run_model_diagnostic_no_weight(mock_dialog, coordinator):
    coordinator.weight_manager.get_weight_details.return_value = None

    config = {
        "video_path": "test.mp4",
        "frames_to_analyze": 10,
        "confidence_threshold": 0.5,
        "model_to_test": "YOLO (PyTorch)",
    }

    coordinator.run_model_diagnostic(config)

    # Should publish an error
    coordinator.event_bus.publish.assert_called()
    event = coordinator.event_bus.publish.call_args[0][0]
    assert event.type == UIEvents.UI_SHOW_ERROR


@patch("zebtrack.coordinators.model_diagnostics_coordinator.YOLO")
@patch("zebtrack.coordinators.model_diagnostics_coordinator.cv2.VideoCapture")
def test_diagnostic_processing_thread_abort(mock_video_capture, mock_yolo, coordinator):
    # Mock video capture
    mock_cap = MagicMock()
    mock_cap.isOpened.return_value = False
    mock_video_capture.return_value = mock_cap

    config = {
        "video_path": "test.mp4",
        "frames_to_analyze": 10,
        "confidence_threshold": 0.5,
        "model_to_test": "YOLO (PyTorch)",
        "progress_dialog": MagicMock(),
    }

    weight_details = {"path": "test.pt"}

    # Thread catches the abort error and finishes
    coordinator._diagnostic_processing_thread(config, weight_details)

    # Assert error was published
    coordinator.event_bus.publish.assert_called()
    event = coordinator.event_bus.publish.call_args[0][0]
    assert event.type == UIEvents.UI_SHOW_ERROR
    assert "Could not open the video" in event.data.message


@patch("zebtrack.ui.dialogs.DiagnosticProgressDialog", autospec=True)
@patch(
    "zebtrack.coordinators.model_diagnostics_coordinator._is_valid_openvino_directory",
    return_value=False,
)
@patch("zebtrack.coordinators.model_diagnostics_coordinator.threading.Thread")
def test_run_model_diagnostic_openvino_convert_yes(
    mock_thread, mock_is_valid, mock_dialog, coordinator
):
    config = {
        "video_path": "test.mp4",
        "frames_to_analyze": 10,
        "confidence_threshold": 0.5,
        "model_to_test": "OpenVINO",
    }

    coordinator.view.dialog_manager.ask_ok_cancel.return_value = True
    coordinator._convert_weight_callback = MagicMock()

    coordinator.run_model_diagnostic(config)

    coordinator.view.dialog_manager.ask_ok_cancel.assert_called_once()
    coordinator._convert_weight_callback.assert_called_once_with("test_weight")


@patch("zebtrack.ui.dialogs.DiagnosticProgressDialog", autospec=True)
@patch(
    "zebtrack.coordinators.model_diagnostics_coordinator._is_valid_openvino_directory",
    return_value=False,
)
@patch("zebtrack.coordinators.model_diagnostics_coordinator.threading.Thread")
def test_run_model_diagnostic_openvino_convert_no(
    mock_thread, mock_is_valid, mock_dialog, coordinator
):
    config = {
        "video_path": "test.mp4",
        "frames_to_analyze": 10,
        "confidence_threshold": 0.5,
        "model_to_test": "OpenVINO",
    }

    coordinator.view.dialog_manager.ask_ok_cancel.return_value = False

    coordinator.run_model_diagnostic(config)

    coordinator.view.dialog_manager.ask_ok_cancel.assert_called_once()
    # Should publish cancellation status
    coordinator.event_bus.publish.assert_called()
    event = coordinator.event_bus.publish.call_args[0][0]
    assert event.type == UIEvents.UI_SET_STATUS
    assert "Diagnostics cancelled" in event.data.message
    # Thread should not start
    mock_thread.assert_not_called()


# =====================================================================
# Additional tests for coverage
# =====================================================================


class TestIsValidOpenvinoDirectory:
    def test_none_path(self):
        from zebtrack.coordinators.model_diagnostics_coordinator import (
            _is_valid_openvino_directory,
        )

        assert _is_valid_openvino_directory(None) is False

    def test_empty_string(self):
        from zebtrack.coordinators.model_diagnostics_coordinator import (
            _is_valid_openvino_directory,
        )

        assert _is_valid_openvino_directory("") is False

    def test_nonexistent_path(self):
        from zebtrack.coordinators.model_diagnostics_coordinator import (
            _is_valid_openvino_directory,
        )

        assert _is_valid_openvino_directory("/nonexistent/path") is False


class TestModelDiagnosticsCoordinatorError:
    def test_with_context(self):
        from zebtrack.coordinators.model_diagnostics_coordinator import (
            ModelDiagnosticsCoordinatorError,
        )

        err = ModelDiagnosticsCoordinatorError("test error", {"key": "value"})
        assert str(err) == "test error"
        assert err.context == {"key": "value"}

    def test_without_context(self):
        from zebtrack.coordinators.model_diagnostics_coordinator import (
            ModelDiagnosticsCoordinatorError,
        )

        err = ModelDiagnosticsCoordinatorError("test error")
        assert err.context == {}


class TestRepr:
    def test_repr(self, coordinator):
        r = repr(coordinator)
        assert "ModelDiagnosticsCoordinator" in r
        assert "has_weight_manager=True" in r


class TestUpdateDiagnosticProgress:
    def test_with_dialog_and_root(self, coordinator):
        dialog = MagicMock()
        coordinator._update_diagnostic_progress(dialog, "Loading...", 1, 10)
        coordinator.root.after.assert_called_once()

    def test_no_dialog(self, coordinator):
        coordinator._update_diagnostic_progress(None, "Loading...")
        coordinator.root.after.assert_not_called()

    def test_no_root(self, coordinator):
        coordinator.root = None
        dialog = MagicMock()
        coordinator._update_diagnostic_progress(dialog, "Loading...")


class TestFinishProgressDialog:
    def test_with_dialog_and_root(self, coordinator):
        dialog = MagicMock()
        coordinator._finish_progress_dialog(dialog)
        coordinator.root.after.assert_called_once()

    def test_no_dialog(self, coordinator):
        coordinator._finish_progress_dialog(None)
        coordinator.root.after.assert_not_called()

    def test_no_root(self, coordinator):
        coordinator.root = None
        dialog = MagicMock()
        coordinator._finish_progress_dialog(dialog)


class TestFormatDiagnosticReport:
    def test_empty_results(self, coordinator):
        config = {
            "video_path": "test.mp4",
            "frames_to_analyze": 10,
            "confidence_threshold": 0.5,
        }
        result = coordinator._format_diagnostic_report(config, {})
        assert "test.mp4" in result
        assert "10" in result

    def test_openvino_results(self, coordinator):
        config = {
            "video_path": "test.mp4",
            "frames_to_analyze": 1,
            "confidence_threshold": 0.5,
        }
        results = {
            "OpenVINO": [
                [
                    {
                        "class_id": 0,
                        "class_name": "zebrafish",
                        "confidence": 0.92,
                        "box": [10, 20, 30, 40],
                        "has_mask": False,
                    }
                ]
            ]
        }
        report = coordinator._format_diagnostic_report(config, results)
        assert "OPENVINO" in report
        assert "zebrafish" in report
        assert "0.92" in report

    def test_openvino_results_with_mask(self, coordinator):
        config = {
            "video_path": "test.mp4",
            "frames_to_analyze": 1,
            "confidence_threshold": 0.5,
        }
        results = {
            "OpenVINO": [
                [
                    {
                        "class_id": 0,
                        "class_name": "fish",
                        "confidence": 0.8,
                        "box": [10, 20, 30, 40],
                        "has_mask": True,
                        "mask_points": 50,
                    }
                ]
            ]
        }
        report = coordinator._format_diagnostic_report(config, results)
        assert "Mask" in report

    def test_no_detections_frame(self, coordinator):
        config = {
            "video_path": "test.mp4",
            "frames_to_analyze": 1,
            "confidence_threshold": 0.5,
        }
        results = {"YOLO (PyTorch)": [MagicMock(boxes=None, masks=None)]}
        # Set hasattr to return True for boxes and masks
        report = coordinator._format_diagnostic_report(config, results)
        assert "No detections found" in report


class TestFinishDiagnosticAndSaveReport:
    def test_no_view(self, coordinator):
        coordinator.view = None
        coordinator._finish_diagnostic_and_save_report(
            {"video_path": "v.mp4", "frames_to_analyze": 1, "confidence_threshold": 0.5},
            {},
        )
        # Should log warning but not crash

    def test_save_path_selected(self, coordinator, tmp_path):
        save_file = tmp_path / "report.txt"
        coordinator.view.dialog_manager.ask_save_filename.return_value = str(save_file)
        coordinator._finish_diagnostic_and_save_report(
            {"video_path": "v.mp4", "frames_to_analyze": 1, "confidence_threshold": 0.5},
            {},
        )
        assert save_file.exists()
        coordinator.event_bus.publish.assert_called()

    def test_save_cancelled(self, coordinator):
        coordinator.view.dialog_manager.ask_save_filename.return_value = None
        coordinator._finish_diagnostic_and_save_report(
            {"video_path": "v.mp4", "frames_to_analyze": 1, "confidence_threshold": 0.5},
            {},
        )
        # Should still publish status
        coordinator.event_bus.publish.assert_called()


class TestInitializeDiagnosticModels:
    def test_yolo_model_not_needed(self, coordinator):
        result = coordinator._initialize_diagnostic_yolo_model("OpenVINO", {}, {}, MagicMock())
        assert result is None

    def test_openvino_model_not_needed(self, coordinator):
        result = coordinator._initialize_diagnostic_openvino_model(
            "YOLO (PyTorch)", {}, {}, MagicMock()
        )
        assert result is None

    @patch(
        "zebtrack.coordinators.model_diagnostics_coordinator._is_valid_openvino_directory",
        return_value=False,
    )
    def test_openvino_invalid_directory(self, mock_valid, coordinator):
        with pytest.raises(DiagnosticAbortError):
            coordinator._initialize_diagnostic_openvino_model(
                "OpenVINO",
                {"openvino_path": "/fake/path"},
                {},
                MagicMock(),
            )


class TestRunDiagnosticFrameLoop:
    @patch("zebtrack.coordinators.model_diagnostics_coordinator.cv2.VideoCapture")
    def test_video_not_opened(self, mock_cap, coordinator):
        cap = MagicMock()
        cap.isOpened.return_value = False
        mock_cap.return_value = cap
        with pytest.raises(DiagnosticAbortError):
            coordinator._run_diagnostic_frame_loop(
                "test.mp4", 10, 0.5, None, None, {}, MagicMock(user_cancelled=False)
            )

    @patch("zebtrack.coordinators.model_diagnostics_coordinator.cv2.VideoCapture")
    def test_cancel_event_set(self, mock_cap, coordinator):
        cap = MagicMock()
        cap.isOpened.return_value = True
        mock_cap.return_value = cap
        coordinator.cancel_event = threading.Event()
        coordinator.cancel_event.set()
        coordinator._run_diagnostic_frame_loop(
            "test.mp4", 10, 0.5, None, None, {}, MagicMock(user_cancelled=False)
        )
        cap.release.assert_called_once()

    @patch("zebtrack.coordinators.model_diagnostics_coordinator.cv2.VideoCapture")
    def test_user_cancelled(self, mock_cap, coordinator):
        cap = MagicMock()
        cap.isOpened.return_value = True
        mock_cap.return_value = cap
        coordinator.cancel_event = None
        progress_dialog = MagicMock()
        progress_dialog.user_cancelled = True
        coordinator._run_diagnostic_frame_loop("test.mp4", 10, 0.5, None, None, {}, progress_dialog)
        cap.release.assert_called_once()

    @patch("zebtrack.coordinators.model_diagnostics_coordinator.cv2.VideoCapture")
    def test_frame_read_failure(self, mock_cap, coordinator):
        cap = MagicMock()
        cap.isOpened.return_value = True
        cap.read.return_value = (False, None)
        mock_cap.return_value = cap
        coordinator.cancel_event = None
        coordinator._run_diagnostic_frame_loop(
            "test.mp4", 10, 0.5, None, None, {}, MagicMock(user_cancelled=False)
        )
        cap.release.assert_called_once()

    @patch("zebtrack.coordinators.model_diagnostics_coordinator.cv2.VideoCapture")
    def test_yolo_only_success(self, mock_cap, coordinator):
        cap = MagicMock()
        cap.isOpened.return_value = True
        cap.read.side_effect = [(True, MagicMock()), (False, None)]
        mock_cap.return_value = cap
        coordinator.cancel_event = None
        yolo_model = MagicMock()
        yolo_model.predict.return_value = [MagicMock()]
        results: dict = {"YOLO (PyTorch)": []}
        coordinator._run_diagnostic_frame_loop(
            "test.mp4", 2, 0.5, yolo_model, None, results, MagicMock(user_cancelled=False)
        )
        assert len(results["YOLO (PyTorch)"]) == 1
        cap.release.assert_called_once()


class TestDiagnosticProcessingThread:
    @patch("zebtrack.coordinators.model_diagnostics_coordinator.cv2.VideoCapture")
    def test_generic_exception_handling(self, mock_cap, coordinator):
        """Test that generic exceptions in the thread are caught."""
        mock_cap.side_effect = RuntimeError("unexpected")
        config = {
            "video_path": "test.mp4",
            "frames_to_analyze": 10,
            "confidence_threshold": 0.5,
            "model_to_test": "YOLO (PyTorch)",
            "progress_dialog": MagicMock(),
        }
        weight_details = {"path": "test.pt"}
        coordinator._diagnostic_processing_thread(config, weight_details)
        # Should publish error
        coordinator.event_bus.publish.assert_called()


class TestRunModelDiagnosticEdgeCases:
    @patch("zebtrack.ui.dialogs.DiagnosticProgressDialog", autospec=True)
    @patch("zebtrack.coordinators.model_diagnostics_coordinator.threading.Thread")
    def test_parent_dialog_destroy(self, mock_thread, mock_dialog, coordinator):
        parent = MagicMock()
        config = {
            "video_path": "test.mp4",
            "frames_to_analyze": 10,
            "confidence_threshold": 0.5,
            "model_to_test": "YOLO (PyTorch)",
            "parent_dialog": parent,
        }
        coordinator.run_model_diagnostic(config)
        parent.destroy.assert_called_once()

    @patch("zebtrack.ui.dialogs.DiagnosticProgressDialog", autospec=True)
    @patch("zebtrack.coordinators.model_diagnostics_coordinator.threading.Thread")
    def test_weight_name_from_manager_method(self, mock_thread, mock_dialog, coordinator):
        coordinator.weight_manager.active_weight_name = None
        coordinator.weight_manager.get_active_weight_name.return_value = "fallback_weight"
        config = {
            "video_path": "test.mp4",
            "frames_to_analyze": 10,
            "confidence_threshold": 0.5,
            "model_to_test": "YOLO (PyTorch)",
        }
        coordinator.run_model_diagnostic(config)
        mock_thread.assert_called_once()
