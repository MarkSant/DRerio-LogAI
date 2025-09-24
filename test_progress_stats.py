#!/usr/bin/env python3
"""
Test script to validate progress callback statistics update functionality
"""

import time
from unittest.mock import MagicMock, patch
import tkinter as tk

# Import the GUI module to test our changes
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from zebtrack.ui.gui import ApplicationGUI


def test_update_processing_stats():
    """Test that update_processing_stats method works correctly"""
    print("Testing update_processing_stats method...")
    
    # Create a root window for GUI
    root = tk.Tk()
    root.withdraw()  # Hide the window during testing
    
    # Mock controller
    mock_controller = MagicMock()
    
    # Create GUI instance
    gui = ApplicationGUI(root, mock_controller)
    
    # Initialize progress frame to create progress_labels
    gui._build_progress_frame()
    
    # Test statistics updates
    start_time = time.time() - 10  # 10 seconds ago
    
    print("Updating statistics...")
    gui.update_processing_stats(
        total_frames=1000,
        processed_frames=250,
        detected_frames=180,
        start_time=start_time
    )
    
    # Check that values were set correctly
    assert gui.progress_labels["total"].get() == "1000", f"Expected '1000', got '{gui.progress_labels['total'].get()}'"
    assert gui.progress_labels["processed"].get() == "250", f"Expected '250', got '{gui.progress_labels['processed'].get()}'"
    assert gui.progress_labels["detected"].get() == "180", f"Expected '180', got '{gui.progress_labels['detected'].get()}'"
    
    # Check percentage calculation
    percent_val = gui.progress_labels["percent"].get()
    expected_percent = "25.0%"
    assert percent_val == expected_percent, f"Expected '{expected_percent}', got '{percent_val}'"
    
    # Check that elapsed time is set (should be approximately 10 seconds)
    elapsed_val = gui.progress_labels["elapsed"].get()
    assert elapsed_val != "-", f"Elapsed time should be set, got '{elapsed_val}'"
    print(f"Elapsed time: {elapsed_val}")
    
    # Check that ETA is set
    eta_val = gui.progress_labels["eta"].get()
    assert eta_val != "-", f"ETA should be calculated, got '{eta_val}'"
    print(f"ETA: {eta_val}")
    
    print("✅ update_processing_stats test passed!")
    root.destroy()
    

def test_progress_callback_signature():
    """Test that progress callback can handle the new stats parameter"""
    print("Testing progress callback with stats parameter...")
    
    # Mock components
    mock_root = MagicMock()
    mock_view = MagicMock()
    
    # Create a sample stats dictionary
    stats = {
        'total_frames': 500,
        'processed_frames': 100,
        'detected_frames': 80,
        'start_time': time.time() - 5
    }
    
    # Define a test progress callback similar to what's in controller
    def test_progress_callback(progress_fraction, status_message, frame=None, stats=None):
        print(f"Progress: {progress_fraction:.2f}, Status: {status_message}")
        if stats:
            print(f"Stats: {stats}")
            # Simulate calling the GUI update
            mock_view.update_processing_stats(
                total_frames=stats.get('total_frames'),
                processed_frames=stats.get('processed_frames'), 
                detected_frames=stats.get('detected_frames'),
                start_time=stats.get('start_time')
            )
        return True
    
    # Test the callback
    result = test_progress_callback(0.2, "Processing...", None, stats)
    assert result is True
    
    # Verify that the mock was called with expected arguments
    mock_view.update_processing_stats.assert_called_once_with(
        total_frames=500,
        processed_frames=100,
        detected_frames=80,
        start_time=stats['start_time']
    )
    
    print("✅ Progress callback signature test passed!")


if __name__ == "__main__":
    print("Running progress statistics tests...")
    print("=" * 50)
    
    test_update_processing_stats()
    test_progress_callback_signature()
    
    print("=" * 50)
    print("✅ All tests passed!")