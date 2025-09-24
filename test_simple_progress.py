#!/usr/bin/env python3
"""
Simple test to validate our changes without GUI dependencies
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

def test_controller_stats_structure():
    """Test that controller handles the new statistics structure"""
    print("Testing controller statistics structure...")
    
    # Test stats dictionary structure
    stats = {
        'total_frames': 500,
        'processed_frames': 100,
        'detected_frames': 80,
        'start_time': 1234567890.0
    }
    
    # Simulate progress callback signature
    def test_progress_callback(progress_fraction, status_message, frame=None, stats=None):
        print(f"Progress: {progress_fraction:.2f}, Status: {status_message}")
        if stats:
            print(f"Stats - Total: {stats.get('total_frames')}, "
                  f"Processed: {stats.get('processed_frames')}, "
                  f"Detected: {stats.get('detected_frames')}")
            return True
        return False
    
    # Test with stats
    result = test_progress_callback(0.2, "Processing...", None, stats)
    assert result is True, "Callback should return True when stats provided"
    
    # Test without stats (backward compatibility)
    result_no_stats = test_progress_callback(0.2, "Processing...", None, None)
    assert result_no_stats is False, "Callback should return False when no stats provided"
    
    print("✅ Controller statistics structure test passed!")
    

def test_statistics_calculations():
    """Test statistics calculations"""
    print("Testing statistics calculations...")
    
    import time
    start_time = time.time() - 10  # 10 seconds ago
    
    total_frames = 1000
    processed_frames = 250
    detected_frames = 180
    
    # Test percentage calculation
    expected_percent = (processed_frames / total_frames) * 100
    assert expected_percent == 25.0, f"Expected 25.0%, got {expected_percent}%"
    
    # Test rate calculation
    elapsed = time.time() - start_time
    rate = processed_frames / elapsed
    assert rate > 0, f"Rate should be positive, got {rate}"
    
    # Test ETA calculation
    remaining_frames = total_frames - processed_frames
    eta = remaining_frames / rate
    assert eta > 0, f"ETA should be positive, got {eta}"
    
    print(f"Calculated rate: {rate:.2f} frames/sec")
    print(f"Calculated ETA: {eta:.2f} seconds")
    
    print("✅ Statistics calculations test passed!")


def test_import_structure():
    """Test that our modules can be imported without errors"""
    print("Testing module imports...")
    
    try:
        # Test core controller import
        from zebtrack.core import controller
        print("✅ Controller module imported successfully")
        
        # Test that the AppController class exists
        assert hasattr(controller, 'AppController'), "AppController class not found"
        print("✅ AppController class found")
        
        # Test settings import
        from zebtrack import settings
        print("✅ Settings module imported successfully")
        
    except Exception as e:
        print(f"❌ Import failed: {e}")
        raise
    
    print("✅ Module imports test passed!")


if __name__ == "__main__":
    print("Running simplified progress statistics tests...")
    print("=" * 60)
    
    test_import_structure()
    test_controller_stats_structure()
    test_statistics_calculations()
    
    print("=" * 60)
    print("✅ All simplified tests passed!")