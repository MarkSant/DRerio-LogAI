from unittest.mock import MagicMock, patch

from zebtrack.plugins.ultralytics_detector import UltralyticsDetectorPlugin


def test_tracking_parameters_update_plugin_attributes():
    with patch(
        "zebtrack.plugins.ultralytics_detector.YOLO", autospec=True
    ) as mock_yolo:
        mock_yolo.return_value = MagicMock()
        plugin = UltralyticsDetectorPlugin("dummy_model.pt")

    assert plugin.track_threshold == 0.25
    assert plugin.match_threshold == 0.15

    plugin.set_tracking_parameters(track_threshold=0.4, match_threshold=0.7)

    assert plugin.track_threshold == 0.4
    assert plugin.match_threshold == 0.7
