from pathlib import Path
from unittest.mock import MagicMock, patch

from zebtrack.plugins.ultralytics_detector import (
    UltralyticsDetectorPlugin,
    _cleanup_tracker_temp_files,
)


def test_tracker_config_written_to_yaml(tmp_path, monkeypatch):
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path), raising=False)

    with patch(
        "zebtrack.plugins.ultralytics_detector.YOLO", autospec=True
    ) as mock_yolo:
        mock_yolo.return_value = MagicMock()
        plugin = UltralyticsDetectorPlugin("dummy_model.pt")

    try:
        config_path = Path(plugin._build_tracker_config())
        assert config_path.suffix == ".yaml"
        assert "tracker_type: bytetrack" in config_path.read_text(encoding="utf-8")

        plugin.set_tracking_parameters(track_threshold=0.4, match_threshold=0.7)
        updated_path = Path(plugin._build_tracker_config())
        assert updated_path.exists()
        assert updated_path != config_path
        assert "track_high_thresh: 0.4" in updated_path.read_text(encoding="utf-8")
    finally:
        _cleanup_tracker_temp_files()
