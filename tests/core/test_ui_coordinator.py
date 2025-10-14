# -*- coding: utf-8 -*-
"""
Unit tests for UICoordinator.

Phase 4: UI Coordination Consolidation tests for UI scheduling,
event bus integration, and convenience methods.
"""

import unittest
from unittest.mock import Mock, patch

import pytest

from zebtrack.core.ui_coordinator import UICoordinator


class TestUICoordinatorInitialization(unittest.TestCase):
    """Test suite for UICoordinator initialization."""

    def test_init_with_root_only(self):
        """Test initialization with only root provided."""
        mock_root = Mock()
        coordinator = UICoordinator(root=mock_root)

        assert coordinator.root == mock_root
        assert coordinator.event_bus is None

    def test_init_with_event_bus_only(self):
        """Test initialization with only event bus provided."""
        mock_event_bus = Mock()
        coordinator = UICoordinator(event_bus=mock_event_bus)

        assert coordinator.root is None
        assert coordinator.event_bus == mock_event_bus

    def test_init_with_both(self):
        """Test initialization with both root and event bus."""
        mock_root = Mock()
        mock_event_bus = Mock()
        coordinator = UICoordinator(root=mock_root, event_bus=mock_event_bus)

        assert coordinator.root == mock_root
        assert coordinator.event_bus == mock_event_bus

    def test_init_with_neither(self):
        """Test initialization with neither root nor event bus."""
        coordinator = UICoordinator()

        assert coordinator.root is None
        assert coordinator.event_bus is None


class TestUICoordinatorScheduling(unittest.TestCase):
    """Test suite for UICoordinator scheduling methods."""

    def test_schedule_with_event_bus_success(self):
        """Test scheduling via event bus when successful."""
        mock_event_bus = Mock()
        mock_event_bus.publish_callable.return_value = True
        coordinator = UICoordinator(event_bus=mock_event_bus)

        mock_func = Mock()
        coordinator.schedule(mock_func, "arg1", kwarg1="value1")

        mock_event_bus.publish_callable.assert_called_once_with(
            mock_func, "arg1", kwarg1="value1"
        )
        mock_func.assert_not_called()  # Should not be called directly

    def test_schedule_with_event_bus_failure_fallback_to_root(self):
        """Test fallback to root.after when event bus fails."""
        mock_event_bus = Mock()
        mock_event_bus.publish_callable.return_value = False
        mock_root = Mock()
        coordinator = UICoordinator(root=mock_root, event_bus=mock_event_bus)

        mock_func = Mock()
        coordinator.schedule(mock_func, "arg1")

        # Event bus should be tried first
        mock_event_bus.publish_callable.assert_called_once()
        # Should fall back to root.after
        mock_root.after.assert_called_once()

    def test_schedule_with_root_only(self):
        """Test scheduling via root.after when no event bus."""
        mock_root = Mock()
        coordinator = UICoordinator(root=mock_root)

        mock_func = Mock()
        coordinator.schedule(mock_func, "arg1")

        mock_root.after.assert_called_once()
        # Verify the lambda calls the function correctly
        call_args = mock_root.after.call_args
        assert call_args[0][0] == 0  # delay should be 0
        # Execute the lambda to verify it works
        call_args[0][1]()
        mock_func.assert_called_once_with("arg1")

    def test_schedule_direct_execution_fallback(self):
        """Test direct execution when neither root nor event bus available."""
        coordinator = UICoordinator()

        mock_func = Mock()
        coordinator.schedule(mock_func, "arg1", kwarg1="value1")

        mock_func.assert_called_once_with("arg1", kwarg1="value1")

    def test_schedule_after_with_root(self):
        """Test scheduling with delay via root.after."""
        mock_root = Mock()
        mock_root.after.return_value = "after_id_123"
        coordinator = UICoordinator(root=mock_root)

        mock_func = Mock()
        result = coordinator.schedule_after(100, mock_func, "arg1")

        assert result == "after_id_123"
        mock_root.after.assert_called_once()
        call_args = mock_root.after.call_args
        assert call_args[0][0] == 100  # delay

    def test_schedule_after_without_root(self):
        """Test schedule_after returns None when no root."""
        coordinator = UICoordinator()

        result = coordinator.schedule_after(100, Mock())

        assert result is None

    def test_cancel_scheduled(self):
        """Test canceling a scheduled callback."""
        mock_root = Mock()
        coordinator = UICoordinator(root=mock_root)

        coordinator.cancel_scheduled("after_id_123")

        mock_root.after_cancel.assert_called_once_with("after_id_123")

    def test_cancel_scheduled_without_root(self):
        """Test cancel_scheduled does nothing when no root."""
        coordinator = UICoordinator()

        # Should not raise error
        coordinator.cancel_scheduled("after_id_123")


class TestUICoordinatorViewUpdates(unittest.TestCase):
    """Test suite for view update convenience methods."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_root = Mock()
        self.coordinator = UICoordinator(root=self.mock_root)
        self.mock_view = Mock()

    def test_update_view_success(self):
        """Test updating view by method name."""
        self.coordinator.update_view(self.mock_view, "set_status", "Test message")

        # Should schedule the method call
        self.mock_root.after.assert_called_once()
        # Execute the scheduled lambda
        call_args = self.mock_root.after.call_args
        call_args[0][1]()
        # Verify method was called
        self.mock_view.set_status.assert_called_once_with("Test message")

    def test_update_view_method_not_found(self):
        """Test update_view handles missing method gracefully."""
        # Configure mock to not have the method
        del self.mock_view.nonexistent_method

        # Should not raise error, just log warning
        self.coordinator.update_view(self.mock_view, "nonexistent_method", "arg")

        # Should not schedule anything
        self.mock_root.after.assert_not_called()

    def test_update_view_none_view(self):
        """Test update_view handles None view gracefully."""
        # Should not raise error, just log warning
        self.coordinator.update_view(None, "some_method", "arg")

        # Should not schedule anything
        self.mock_root.after.assert_not_called()

    def test_set_status(self):
        """Test set_status convenience method."""
        self.coordinator.set_status(self.mock_view, "Status message")

        self.mock_root.after.assert_called_once()
        # Execute scheduled lambda
        self.mock_root.after.call_args[0][1]()
        self.mock_view.set_status.assert_called_once_with("Status message")

    def test_show_error(self):
        """Test show_error convenience method."""
        self.coordinator.show_error(self.mock_view, "Error Title", "Error message")

        self.mock_root.after.assert_called_once()
        # Execute scheduled lambda
        self.mock_root.after.call_args[0][1]()
        self.mock_view.show_error.assert_called_once_with("Error Title", "Error message")

    def test_show_info(self):
        """Test show_info convenience method."""
        self.coordinator.show_info(self.mock_view, "Info Title", "Info message")

        self.mock_root.after.assert_called_once()
        # Execute scheduled lambda
        self.mock_root.after.call_args[0][1]()
        self.mock_view.show_info.assert_called_once_with("Info Title", "Info message")

    def test_update_progress(self):
        """Test update_progress convenience method."""
        self.coordinator.update_progress(self.mock_view, 0.75)

        self.mock_root.after.assert_called_once()
        # Execute scheduled lambda
        self.mock_root.after.call_args[0][1]()
        self.mock_view.update_progress.assert_called_once_with(0.75)

    def test_update_button_state(self):
        """Test update_button_state convenience method."""
        self.coordinator.update_button_state(self.mock_view, "start_rec", "disabled")

        self.mock_root.after.assert_called_once()
        # Execute scheduled lambda
        self.mock_root.after.call_args[0][1]()
        self.mock_view.update_button_state.assert_called_once_with("start_rec", "disabled")

    def test_display_frame(self):
        """Test display_frame convenience method."""
        mock_frame = Mock()
        self.coordinator.display_frame(self.mock_view, mock_frame)

        self.mock_root.after.assert_called_once()
        # Execute scheduled lambda
        self.mock_root.after.call_args[0][1]()
        self.mock_view.display_frame.assert_called_once_with(mock_frame)

    def test_update_detection_overlay(self):
        """Test update_detection_overlay convenience method."""
        payload = {"detections": []}
        processing_info = {"fps": 30}
        self.coordinator.update_detection_overlay(
            self.mock_view, payload, processing_info
        )

        self.mock_root.after.assert_called_once()
        # Execute scheduled lambda
        self.mock_root.after.call_args[0][1]()
        self.mock_view.update_detection_overlay.assert_called_once_with(
            payload, processing_info
        )

    def test_show_progress_bar(self):
        """Test show_progress_bar convenience method."""
        self.coordinator.show_progress_bar(self.mock_view)

        self.mock_root.after.assert_called_once()
        # Execute scheduled lambda
        self.mock_root.after.call_args[0][1]()
        self.mock_view.show_progress_bar.assert_called_once()

    def test_hide_progress_bar(self):
        """Test hide_progress_bar convenience method."""
        self.coordinator.hide_progress_bar(self.mock_view)

        self.mock_root.after.assert_called_once()
        # Execute scheduled lambda
        self.mock_root.after.call_args[0][1]()
        self.mock_view.hide_progress_bar.assert_called_once()

    def test_update_idletasks(self):
        """Test update_idletasks convenience method."""
        self.coordinator.update_idletasks(self.mock_view)

        self.mock_root.after.assert_called_once()
        # Execute scheduled lambda
        self.mock_root.after.call_args[0][1]()
        self.mock_view.update_idletasks.assert_called_once()


class TestUICoordinatorErrorHandling(unittest.TestCase):
    """Test suite for error handling in UICoordinator."""

    def test_schedule_handles_after_exception(self):
        """Test that schedule handles root.after exceptions gracefully."""
        mock_root = Mock()
        mock_root.after.side_effect = Exception("Tk error")
        coordinator = UICoordinator(root=mock_root)

        mock_func = Mock()
        # Should fall back to direct execution
        coordinator.schedule(mock_func, "arg1")

        mock_func.assert_called_once_with("arg1")

    def test_schedule_handles_direct_execution_exception(self):
        """Test that schedule handles direct execution exceptions."""
        coordinator = UICoordinator()

        mock_func = Mock(side_effect=Exception("Function error"))
        # Should not raise, just log error
        coordinator.schedule(mock_func)

    def test_schedule_after_handles_exception(self):
        """Test that schedule_after handles exceptions gracefully."""
        mock_root = Mock()
        mock_root.after.side_effect = Exception("Tk error")
        coordinator = UICoordinator(root=mock_root)

        result = coordinator.schedule_after(100, Mock())

        assert result is None

    def test_cancel_scheduled_handles_exception(self):
        """Test that cancel_scheduled handles exceptions gracefully."""
        mock_root = Mock()
        mock_root.after_cancel.side_effect = Exception("Cancel error")
        coordinator = UICoordinator(root=mock_root)

        # Should not raise error
        coordinator.cancel_scheduled("after_id_123")


if __name__ == "__main__":
    unittest.main()
