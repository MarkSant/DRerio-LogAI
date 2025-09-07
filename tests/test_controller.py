import unittest
from unittest.mock import MagicMock, patch

from zebtrack.core.controller import AppController


class TestAppController(unittest.TestCase):
    @patch("zebtrack.core.controller.ProjectManager")
    @patch("zebtrack.core.controller.ApplicationGUI")
    def setUp(self, mock_gui, mock_pm):
        """Set up a test environment before each test."""
        self.root = MagicMock()

        # The patched classes are passed as arguments to setUp
        self.mock_view = mock_gui.return_value
        self.mock_pm = mock_pm.return_value

        self.controller = AppController(self.root)

        # The controller now has MOCK instances for its dependencies
        self.controller.project_manager = self.mock_pm
        self.controller.view = self.mock_view

    def tearDown(self):
        """Clean up after each test."""
        pass

    def test_create_project_workflow_success(self):
        """
        Test the successful creation of a new project through the controller.
        """
        # --- Arrange ---
        self.mock_pm.create_new_project.return_value = True
        with patch.object(self.controller, "setup_detector", return_value=True):
            # --- Act ---
            self.controller.create_project_workflow(
            project_path="/fake/parent/fake_project",
            project_type="live",
            use_openvino=False,
            video_files=[],
            num_aquariums=1,
            aquarium_width_cm=10.0,
            aquarium_height_cm=10.0,
        )

        # --- Assert ---
        self.mock_pm.create_new_project.assert_called_once_with(
            project_path="/fake/parent/fake_project",
            project_type="live",
            use_openvino=False,
            video_files=[],
            num_aquariums=1,
            aquarium_width_cm=10.0,
            aquarium_height_cm=10.0,
            active_weight="",
        )
        self.mock_view._load_project_view.assert_called_once()

    def test_create_project_workflow_failure(self):
        """
        Test the project creation workflow when the project manager fails.
        """
        # --- Arrange ---
        self.mock_pm.create_new_project.return_value = False

        # --- Act ---
        self.controller.create_project_workflow(
            project_path="/fake/parent/fake_project",
            project_type="live",
            use_openvino=False,
            video_files=[],
            num_aquariums=1,
            aquarium_width_cm=10.0,
            aquarium_height_cm=10.0,
        )

        # --- Assert ---
        self.mock_view.show_error.assert_called_once_with(
            "Error", "Failed to create the new project."
        )
        self.mock_view._load_project_view.assert_not_called()


if __name__ == "__main__":
    unittest.main()
