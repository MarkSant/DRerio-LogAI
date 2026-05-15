"""Tests for WizardService friendly-name + camera resolver behavior.

Covers:
    - Friendly name attached to each detected camera (when pygrabber available).
    - Graceful fallback when pygrabber import fails / non-Windows.
    - Dedupe of identical DirectShow device names.
    - resolve_camera_index status semantics: MATCH / SHIFTED / MISSING.
"""

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from zebtrack.core.services.wizard_service import WizardService


@pytest.fixture(autouse=True)
def _clear_hw_cache():
    WizardService.clear_hardware_cache()
    yield
    WizardService.clear_hardware_cache()


def _make_mock_cap():
    """A VideoCapture that passes ghost-detection and returns 640x480 @ 30fps."""
    mock_cap = MagicMock()
    mock_cap.isOpened.return_value = True
    mock_cap.get.side_effect = [640, 480, 30.0]
    valid_frame = np.ones((480, 640, 3), dtype=np.uint8) * 128
    mock_cap.read.return_value = (True, valid_frame)
    return mock_cap


def _make_failing_cap():
    """A VideoCapture that fails to open — closes the probe loop quickly."""
    mock_cap = MagicMock()
    mock_cap.isOpened.return_value = False
    return mock_cap


class TestFriendlyNames:
    @patch("cv2.VideoCapture")
    @patch.object(WizardService, "_get_dshow_friendly_names")
    def test_friendly_name_attached_when_available(self, mock_names, mock_vc):
        """Description uses the DirectShow friendly name when pygrabber returns one."""
        mock_names.return_value = ["Logi C270 HD WebCam", "ASUS FHD webcam"]
        # Two cameras open, the rest fail (so the loop stops after consecutive failures).
        mock_vc.side_effect = [_make_mock_cap(), _make_mock_cap()] + [
            _make_failing_cap() for _ in range(4)
        ]

        cameras = WizardService.detect_available_cameras(use_cache=False)

        assert len(cameras) == 2
        assert cameras[0]["friendly_name"] == "Logi C270 HD WebCam"
        assert cameras[1]["friendly_name"] == "ASUS FHD webcam"
        assert "Logi C270 HD WebCam" in cameras[0]["description"]
        assert "ASUS FHD webcam" in cameras[1]["description"]

    @patch("cv2.VideoCapture")
    @patch.object(WizardService, "_get_dshow_friendly_names")
    def test_fallback_when_pygrabber_unavailable(self, mock_names, mock_vc):
        """When pygrabber returns [], descriptions fall back to numbered labels."""
        mock_names.return_value = []
        mock_vc.side_effect = [_make_mock_cap(), _make_mock_cap()] + [
            _make_failing_cap() for _ in range(4)
        ]

        cameras = WizardService.detect_available_cameras(use_cache=False)

        assert len(cameras) == 2
        assert cameras[0]["friendly_name"] == ""
        assert "Câmera #1" in cameras[0]["description"]
        assert "Câmera #2" in cameras[1]["description"]

    def test_dedupe_identical_dshow_names(self):
        """Two devices with identical DirectShow names get (#2), (#3) suffixes."""
        # Direct unit test on the helper. Mock the FilterGraph at the import site.
        fake_module = MagicMock()
        fake_module.dshow_graph.FilterGraph.return_value.get_input_devices.return_value = [
            "Logi C270 HD WebCam",
            "Logi C270 HD WebCam",
            "ASUS FHD webcam",
            "Logi C270 HD WebCam",
        ]

        with (
            patch("sys.platform", "win32"),
            patch.dict(
                "sys.modules",
                {"pygrabber": fake_module, "pygrabber.dshow_graph": fake_module.dshow_graph},
            ),
        ):
            names = WizardService._get_dshow_friendly_names()

        assert names == [
            "Logi C270 HD WebCam",
            "Logi C270 HD WebCam (#2)",
            "ASUS FHD webcam",
            "Logi C270 HD WebCam (#3)",
        ]

    def test_friendly_names_empty_on_non_win32(self):
        with patch("sys.platform", "linux"):
            assert WizardService._get_dshow_friendly_names() == []


class TestResolveCameraIndex:
    """The resolver MUST NOT open any camera — it relies solely on the
    lightweight pygrabber DirectShow enumeration, so we mock that helper."""

    @patch.object(WizardService, "_get_dshow_friendly_names")
    def test_match_when_index_unchanged(self, mock_names):
        mock_names.return_value = ["Logi C270 HD WebCam", "ASUS FHD webcam"]
        new_index, status = WizardService.resolve_camera_index(1, "ASUS FHD webcam")
        assert (new_index, status) == (1, "MATCH")

    @patch.object(WizardService, "_get_dshow_friendly_names")
    def test_shifted_when_friendly_name_at_new_index(self, mock_names):
        # USB camera was reordered: was index 1, now at 0
        mock_names.return_value = ["ASUS FHD webcam", "Logi C270 HD WebCam"]
        new_index, status = WizardService.resolve_camera_index(1, "ASUS FHD webcam")
        assert (new_index, status) == (0, "SHIFTED")

    @patch.object(WizardService, "_get_dshow_friendly_names")
    def test_missing_when_camera_disconnected(self, mock_names):
        mock_names.return_value = ["Logi C270 HD WebCam"]
        new_index, status = WizardService.resolve_camera_index(1, "ASUS FHD webcam")
        # Returns saved_index but caller must NOT silently use it (status=MISSING).
        assert (new_index, status) == (1, "MISSING")

    @patch.object(WizardService, "_get_dshow_friendly_names")
    def test_resolver_does_not_invoke_detect_probe(self, mock_names):
        """Critical: the resolver must never trigger detect_available_cameras,
        which opens cv2.VideoCapture for every index 0..5 and can power on
        cameras that should remain idle."""
        mock_names.return_value = ["ASUS FHD webcam"]
        with patch.object(WizardService, "detect_available_cameras") as mock_detect:
            WizardService.resolve_camera_index(0, "ASUS FHD webcam")
        mock_detect.assert_not_called()

    def test_legacy_project_without_friendly_name(self):
        """Empty saved_name means legacy project — trust saved_index, return MATCH."""
        with patch.object(WizardService, "_get_dshow_friendly_names") as mock_names:
            new_index, status = WizardService.resolve_camera_index(2, "")
        assert (new_index, status) == (2, "MATCH")
        mock_names.assert_not_called()

    @patch.object(WizardService, "_get_dshow_friendly_names")
    def test_no_enumeration_available_trusts_saved_index(self, mock_names):
        """Non-Windows / pygrabber missing: cannot verify, must trust saved index."""
        mock_names.return_value = []
        new_index, status = WizardService.resolve_camera_index(3, "Some Cam")
        assert (new_index, status) == (3, "MATCH")
