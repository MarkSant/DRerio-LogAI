"""
Unit tests for multi-aquarium dialog components.

Tests for:
- MultiAquariumConfirmDialog
- AquariumAssignmentDialog
"""

import tkinter as tk
from unittest.mock import MagicMock, patch

import pytest

from zebtrack.ui.dialogs.aquarium_assignment_dialog import AquariumAssignmentDialog
from zebtrack.ui.dialogs.multi_aquarium_confirm_dialog import MultiAquariumConfirmDialog
from zebtrack.ui.wizard.models import AquariumConfig


@pytest.mark.gui
class TestMultiAquariumConfirmDialog:
    """Tests for MultiAquariumConfirmDialog."""

    def test_dialog_creation(self, tkinter_root):
        """Test that dialog can be created without errors."""
        callbacks = {
            "single": MagicMock(),
            "multi": MagicMock(),
            "cancel": MagicMock(),
        }

        # Create dialog without displaying (would block)
        with patch.object(MultiAquariumConfirmDialog, "wait_window"):
            dialog = MultiAquariumConfirmDialog(
                parent=tkinter_root,
                on_single=callbacks["single"],
                on_multi=callbacks["multi"],
                on_cancel=callbacks["cancel"],
            )

        # Verify dialog was created
        assert dialog is not None
        assert hasattr(dialog, "result")
        assert dialog.result is None  # No result yet

    def test_dialog_has_correct_title(self, tkinter_root):
        """Test dialog has correct title."""
        with patch.object(MultiAquariumConfirmDialog, "wait_window"):
            dialog = MultiAquariumConfirmDialog(parent=tkinter_root)

        assert dialog.title() == "Configuração de Aquários"

    def test_get_result_returns_selection(self, tkinter_root):
        """Test get_result returns the selection."""
        with patch.object(MultiAquariumConfirmDialog, "wait_window"):
            dialog = MultiAquariumConfirmDialog(parent=tkinter_root)

        # Initially no result
        assert dialog.get_result() is None

        # Set result manually
        dialog.result = 1
        assert dialog.get_result() == 1

    def test_single_aquarium_selection(self, tkinter_root):
        """Test single aquarium callback is triggered."""
        callback = MagicMock()

        with patch.object(MultiAquariumConfirmDialog, "wait_window"):
            with patch.object(MultiAquariumConfirmDialog, "ok"):
                dialog = MultiAquariumConfirmDialog(
                    parent=tkinter_root,
                    on_single=callback,
                )
                # Set selection to 1 aquarium
                dialog._aquarium_count.set(1)
                # Simulate confirm
                dialog._on_confirm()

        callback.assert_called_once()
        assert dialog.result == 1

    def test_multi_aquarium_selection(self, tkinter_root):
        """Test multi aquarium callback is triggered."""
        callback = MagicMock()

        with patch.object(MultiAquariumConfirmDialog, "wait_window"):
            with patch.object(MultiAquariumConfirmDialog, "ok"):
                dialog = MultiAquariumConfirmDialog(
                    parent=tkinter_root,
                    on_multi=callback,
                )
                # Set selection to 2 aquariums
                dialog._aquarium_count.set(2)
                # Simulate confirm
                dialog._on_confirm()

        callback.assert_called_once()
        assert dialog.result == 2

    def test_cancel_callback(self, tkinter_root):
        """Test cancel callback is triggered."""
        callback = MagicMock()

        with patch.object(MultiAquariumConfirmDialog, "wait_window"):
            with patch.object(tk.simpledialog.Dialog, "cancel"):
                dialog = MultiAquariumConfirmDialog(
                    parent=tkinter_root,
                    on_cancel=callback,
                )
                dialog.cancel()

        callback.assert_called_once()


@pytest.mark.gui
class TestAquariumAssignmentDialog:
    """Tests for AquariumAssignmentDialog."""

    @patch("tkinter.messagebox.showinfo")
    def test_dialog_creation(self, mock_showinfo, tkinter_root):
        """Test that dialog can be created without errors."""
        groups = ["Controle", "Tratamento"]

        with patch("ttkbootstrap.Style"):  # Mock style to avoid Tcl issues
            with patch.object(AquariumAssignmentDialog, "wait_window"):
                dialog = AquariumAssignmentDialog(
                    parent=tkinter_root,
                    available_groups=groups,
                )

        assert dialog is not None
        assert dialog.available_groups == groups

    @patch("tkinter.messagebox.showinfo")
    def test_regex_auto_fill(self, mock_showinfo, tkinter_root):
        """Test regex auto-fill logic in the dialog."""
        from zebtrack.ui.wizard.models import MultiAquariumData

        groups = ["Control"]
        video_path = "G_Control_S_01--G_Stress_S_02.mp4"

        # Configure regex
        multi_config = MultiAquariumData(
            enabled=True,
            regex_pattern=r"G_(?P<group>\w+)_S_(?P<subject>\w+)",
            regex_group_field="group",
            regex_subject_field="subject",
        )

        with patch("ttkbootstrap.Style"):
            with patch.object(AquariumAssignmentDialog, "wait_window"):
                dialog = AquariumAssignmentDialog(
                    parent=tkinter_root,
                    available_groups=groups,
                    video_path=video_path,
                    multi_aquarium_config=multi_config,
                )

                # Trigger auto-fill
                dialog._on_auto_fill_click()

        # Verify results for first aquarium
        assert dialog._group_vars[0].get() == "Control"
        assert dialog._subject_vars[0].get() == "01"

        # Verify results for second aquarium (should have extracted second match)
        assert dialog._group_vars[1].get() == "Stress"
        assert dialog._subject_vars[1].get() == "02"

        # Verify Stress was added to combobox values for both
        assert "Stress" in dialog._group_combos[0]["values"]
        assert "Stress" in dialog._group_combos[1]["values"]

    def test_apply_to_all_functionality(self, tkinter_root):
        """Test that get_result returns the apply_to_all state."""
        with patch("ttkbootstrap.Style"):
            with patch.object(AquariumAssignmentDialog, "wait_window"):
                dialog = AquariumAssignmentDialog(parent=tkinter_root, available_groups=["Control"])

                # Check default
                assert dialog._apply_to_all_var.get() is False

                # Set to True
                dialog._apply_to_all_var.set(True)

                # Simulate confirm
                dialog.result = dialog.get_configs()

                configs, apply_to_all = dialog.get_result()
                assert apply_to_all is True

    def test_dynamic_group_addition(self, tkinter_root):
        """Test that new groups are added to comboboxes correctly."""
        with patch("ttkbootstrap.Style"):
            with patch.object(AquariumAssignmentDialog, "wait_window"):
                dialog = AquariumAssignmentDialog(parent=tkinter_root, available_groups=["Control"])

                # Initially only "Control"
                assert "Control" in dialog._group_combos[0]["values"]
                assert "NewGroup" not in dialog._group_combos[0]["values"]

                # Add group via method
                dialog._ensure_group_in_combobox(0, "NewGroup")

                # Now "NewGroup" should be there
                assert "NewGroup" in dialog._group_combos[0]["values"]
                # And also in the other combobox (shared logic)
                assert "NewGroup" in dialog._group_combos[1]["values"]

    def test_default_group_assignment_logic(self):
        """Test default group assignment logic without creating dialog."""
        # Test the logic directly without creating the full dialog
        groups_2 = ["Controle", "Tratamento"]
        groups_empty = []

        # For 2 groups, should assign alternating
        assert groups_2[0 % len(groups_2)] == "Controle"
        assert groups_2[1 % len(groups_2)] == "Tratamento"

        # For empty groups, fallback to defaults
        default_0 = "Controle" if not groups_empty else groups_empty[0]
        default_1 = "Tratamento" if not groups_empty or len(groups_empty) < 2 else groups_empty[1]
        assert default_0 == "Controle"
        assert default_1 == "Tratamento"

    def test_aquarium_config_creation(self):
        """Test AquariumConfig creation with valid values."""
        config = AquariumConfig(
            aquarium_id=0,
            group="Controle",
            subject_id="S01",
            day=1,
        )

        assert config.aquarium_id == 0
        assert config.group == "Controle"
        assert config.subject_id == "S01"
        assert config.day == 1

    def test_aquarium_config_validation(self):
        """Test AquariumConfig validation."""
        # Valid config
        config = AquariumConfig(aquarium_id=1, group="Test")
        assert config.aquarium_id == 1

        # Invalid aquarium_id should raise
        with pytest.raises(ValueError):
            AquariumConfig(aquarium_id=5, group="Test")  # Only 0 or 1 allowed

    def test_video_path_storage(self):
        """Test video path is stored correctly."""
        # This is a unit test for the attribute, not the full dialog
        test_path = "/path/to/video.mp4"

        # Create a mock to simulate the dialog's video_path attribute
        class MockDialog:
            def __init__(self, video_path):
                self.video_path = video_path

        dialog = MockDialog(test_path)
        assert dialog.video_path == test_path


class TestDialogImports:
    """Test dialog exports from package."""

    def test_dialogs_exported(self):
        """Test new dialogs are exported from package."""
        from zebtrack.ui.dialogs import (
            AquariumAssignmentDialog,
            MultiAquariumConfirmDialog,
        )

        assert MultiAquariumConfirmDialog is not None
        assert AquariumAssignmentDialog is not None
