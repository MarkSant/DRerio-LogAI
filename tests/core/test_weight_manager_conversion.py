import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from zebtrack.core.weight_manager import (
    OPENVINO_STATUS_FAILED,
    OPENVINO_STATUS_NOT_CONVERTED,
    OPENVINO_STATUS_READY,
    WeightManager,
)


def _bootstrap_manager(temp_dir: str) -> WeightManager:
    with patch("zebtrack.core.weight_manager.settings") as mock_settings:
        mock_settings.weights.seg_filename = ""
        mock_settings.weights.det_filename = ""
        mock_settings.yolo_model.path = ""
        manager = WeightManager(config_dir=temp_dir)
    return manager


def _register_weight(manager: WeightManager, weight_path: str) -> None:
    manager.weights[os.path.basename(weight_path)] = {
        "path": weight_path,
        "is_default": True,
        "type": "seg",
        "is_default_seg": True,
        "is_default_det": False,
        "openvino_path": "",
        "openvino_hash": "",
        "openvino_status": OPENVINO_STATUS_NOT_CONVERTED,
        "last_conversion_error": None,
    }
    manager.save_weights()


def test_convert_to_openvino_failure_records_status(tmp_path):
    weight_file = tmp_path / "model_seg.pt"
    weight_file.write_text("mock model")

    manager = _bootstrap_manager(str(tmp_path))
    _register_weight(manager, str(weight_file))

    cached_dir = tmp_path / "openvino_model_cache" / "model_seg_openvino_model"

    with patch("zebtrack.core.weight_manager.ULTRALYTICS_AVAILABLE", True), patch(
        "zebtrack.core.weight_manager.YOLO"
    ) as mock_yolo, patch(
        "zebtrack.core.weight_manager.messagebox.showerror"
    ) as mock_message:
        mock_instance = MagicMock()
        mock_instance.export.side_effect = RuntimeError("boom")
        mock_yolo.return_value = mock_instance

        result = manager.convert_to_openvino(weight_file.name)

    assert result is None
    assert not cached_dir.exists()
    mock_message.assert_called_once()

    details = manager.get_weight_details(weight_file.name)
    assert details["openvino_status"] == OPENVINO_STATUS_FAILED
    assert details["openvino_path"] == ""
    assert "boom" in details["last_conversion_error"]


def test_convert_to_openvino_success_updates_status(tmp_path):
    weight_file = tmp_path / "model_seg.pt"
    weight_file.write_text("mock model")

    manager = _bootstrap_manager(str(tmp_path))
    _register_weight(manager, str(weight_file))

    export_dir = Path(tempfile.mkdtemp(dir=str(tmp_path))) / "exported_model"
    export_dir.mkdir(parents=True, exist_ok=True)
    xml_path = export_dir / "model_seg.xml"
    xml_path.write_text("<xml></xml>")

    with patch("zebtrack.core.weight_manager.ULTRALYTICS_AVAILABLE", True), patch(
        "zebtrack.core.weight_manager.YOLO"
    ) as mock_yolo, patch(
        "zebtrack.core.weight_manager.messagebox.showerror"
    ) as mock_message:
        mock_message.side_effect = AssertionError("messagebox should not be called")
        mock_instance = MagicMock()
        mock_instance.export.return_value = str(export_dir)
        mock_yolo.return_value = mock_instance

        result = manager.convert_to_openvino(weight_file.name)

    assert result is not None
    cached_dir = Path(result)
    assert cached_dir.exists()
    assert (cached_dir / "metadata.json").exists()
    metadata = json.loads((cached_dir / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["original_model"] == weight_file.name

    details = manager.get_weight_details(weight_file.name)
    assert details["openvino_status"] == OPENVINO_STATUS_READY
    assert details["last_conversion_error"] is None
    assert Path(details["openvino_path"]) == cached_dir

    # ensure config persisted status
    reloaded = _bootstrap_manager(str(tmp_path))
    reloaded_details = reloaded.get_weight_details(weight_file.name)
    assert reloaded_details["openvino_status"] == OPENVINO_STATUS_READY
    assert reloaded_details["last_conversion_error"] is None