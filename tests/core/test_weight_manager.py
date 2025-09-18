from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from zebtrack.core.weight_manager import OPENVINO_CACHE_DIR, WeightManager


@pytest.fixture
def wm_setup(tmp_path):
    """
    Provides a WeightManager instance in a temporary directory.
    It patches tkinter.messagebox to avoid GUI popups during tests.
    It also creates a dummy .pt file to be used as a default weight.
    """
    config_dir = tmp_path / "config"
    config_dir.mkdir()

    # Create a dummy .pt file inside the config dir to act as the default
    default_weight_path = config_dir / "default_weight.pt"
    default_weight_path.touch()

    # Patch the global settings to point to this dummy file for initialization
    with (
        patch("zebtrack.core.weight_manager.settings") as mock_settings,
        patch("zebtrack.core.weight_manager.messagebox") as mock_messagebox,
    ):
        mock_settings.yolo_model.path = str(default_weight_path)

        # Instantiate the manager pointing to the temp config dir
        manager = WeightManager(config_dir=str(config_dir))
        yield manager, config_dir, tmp_path, mock_messagebox


def test_wm_initialization_creates_default(wm_setup):
    """
    Tests that if no config file exists, the manager creates one using the
    default model path from settings.
    """
    manager, config_dir, _, _ = wm_setup
    config_path = config_dir / "weights_config.json"

    assert config_path.exists()
    weights = manager.get_all_weights()
    assert len(weights) == 1
    assert "default_weight.pt" in weights

    name, details = manager.get_default_weight()
    assert name == "default_weight.pt"
    assert details["is_default"] is True


def test_wm_add_weight(wm_setup):
    """Tests adding a new weight file."""
    manager, config_dir, _, _ = wm_setup

    new_weight_path = config_dir / "new_model.pt"
    new_weight_path.touch()

    manager.add_weight(str(new_weight_path), set_as_default=False)

    weights = manager.get_all_weights()
    assert len(weights) == 2
    assert "new_model.pt" in weights
    details = manager.get_weight_details("new_model.pt")
    assert details["is_default"] is False


def test_wm_add_weight_as_default(wm_setup):
    """Tests that adding a weight as default correctly updates the old default."""
    manager, config_dir, _, _ = wm_setup

    # Get the original default
    old_default_name, _ = manager.get_default_weight()
    assert old_default_name == "default_weight.pt"

    # Add a new one as default
    new_weight_path = config_dir / "new_default.pt"
    new_weight_path.touch()
    manager.add_weight(str(new_weight_path), set_as_default=True)

    # Check that the new weight is the default
    new_default_name, _ = manager.get_default_weight()
    assert new_default_name == "new_default.pt"

    # Check that the old default is no longer the default
    old_default_details = manager.get_weight_details(old_default_name)
    assert old_default_details["is_default"] is False


def test_wm_delete_weight(wm_setup):
    """Tests deleting a non-default weight."""
    manager, config_dir, _, _ = wm_setup
    # Add a second weight to delete
    new_weight_path = config_dir / "to_delete.pt"
    new_weight_path.touch()
    manager.add_weight(str(new_weight_path), set_as_default=False)
    assert "to_delete.pt" in manager.get_all_weights()

    # Delete it
    manager.delete_weight("to_delete.pt")
    assert "to_delete.pt" not in manager.get_all_weights()
    assert len(manager.get_all_weights()) == 1


def test_wm_delete_default_weight(wm_setup):
    """Tests that deleting the default weight assigns a new default."""
    manager, config_dir, _, _ = wm_setup
    # Add a second weight
    new_weight_path = config_dir / "new_one.pt"
    new_weight_path.touch()
    manager.add_weight(str(new_weight_path), set_as_default=False)

    # Delete the original default
    manager.delete_weight("default_weight.pt")

    # Check that the other weight is now the default
    new_default_name, _ = manager.get_default_weight()
    assert new_default_name == "new_one.pt"


def test_wm_cannot_delete_last_weight(wm_setup):
    """Tests that the last remaining weight cannot be deleted."""
    manager, _, _, mock_messagebox = wm_setup
    assert len(manager.get_all_weights()) == 1

    # Attempt to delete the last weight
    manager.delete_weight("default_weight.pt")

    # Check that it was not deleted and the messagebox was called
    assert len(manager.get_all_weights()) == 1
    mock_messagebox.showerror.assert_called_once()


@patch("zebtrack.core.weight_manager.YOLO")
@patch("shutil.move")
def test_wm_convert_to_openvino(mock_move, mock_yolo, wm_setup):
    """
    Tests the OpenVINO conversion process, mocking the actual conversion.
    """
    manager, config_dir, tmp_path, _ = wm_setup
    weight_name = "default_weight.pt"

    # --- Mock the behavior of YOLO().export() ---
    # It should return a path to a temporary directory it "created"
    mock_model_instance = MagicMock()
    mock_yolo.return_value = mock_model_instance

    # The temp export dir that ultralytics would create
    temp_export_dir = tmp_path / "temp_export_dir"
    temp_export_dir.mkdir()
    # Create a dummy file inside to make it a valid directory
    (temp_export_dir / "dummy.xml").touch()
    mock_model_instance.export.return_value = str(temp_export_dir)

    # --- Define a side effect for the mock that simulates the move ---
    def move_side_effect(src, dst):
        # In the test, we need to simulate that the move operation creates
        # the destination directory and the file inside it.
        dst_path = Path(dst)
        if not dst_path.exists():
            dst_path.mkdir(parents=True)
        # The original temp file was named dummy.xml, so we create that here.
        (dst_path / "dummy.xml").touch()
        return str(dst_path)

    mock_move.side_effect = move_side_effect

    # --- Run the conversion ---
    openvino_path = manager.convert_to_openvino(weight_name)

    # --- Assertions ---
    # 1. Assert that YOLO was called with the correct .pt path
    details = manager.get_weight_details(weight_name)
    mock_yolo.assert_called_once_with(details["path"])

    # 2. Assert that the export was called
    mock_model_instance.export.assert_called_once_with(format="openvino", half=True)

    # 3. Assert that the final model path is correct and exists
    expected_final_dir = (
        config_dir / OPENVINO_CACHE_DIR / "default_weight_openvino_model"
    )
    assert openvino_path == str(expected_final_dir)

    # 4. Assert that shutil.move was called to move the temp dir
    mock_move.assert_called_once_with(str(temp_export_dir), str(expected_final_dir))

    # 5. Assert that the config was updated with the new path
    updated_details = manager.get_weight_details(weight_name)
    assert updated_details["openvino_path"] == openvino_path
