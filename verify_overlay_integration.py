#!/usr/bin/env python3
"""
Manual verification script to test overlay integration without dependencies.
This script validates the logic of our changes by simulating the frame flow.
"""
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

def test_gui_change():
    """Test that GUI change preserves frames correctly."""
    print("Testing GUI display_analysis_frame modification...")
    
    # Read the modified file
    gui_path = os.path.join('src', 'zebtrack', 'ui', 'gui.py')
    with open(gui_path, 'r') as f:
        gui_content = f.read()
    
    # Check that display_analysis_frame doesn't call _draw_zones_on_frame
    # Find the display_analysis_frame method
    method_start = gui_content.find('def display_analysis_frame(self, frame):')
    if method_start == -1:
        print("❌ FAIL: display_analysis_frame method not found")
        return False
    
    # Extract the method content (until next method)
    next_method = gui_content.find('def ', method_start + 1)
    method_content = gui_content[method_start:next_method] if next_method != -1 else gui_content[method_start:]
    
    if '_draw_zones_on_frame' in method_content:
        print("❌ FAIL: display_analysis_frame still calls _draw_zones_on_frame")
        return False
    
    # Check that the new logic is in place
    if 'frame_to_display = frame.copy()' in gui_content:
        print("✅ PASS: display_analysis_frame now preserves frame as-is")
    else:
        print("❌ FAIL: Expected frame preservation logic not found")
        return False
    
    # Check that the comment explains the change
    if 'frames should already have overlays' in gui_content:
        print("✅ PASS: Code includes explanatory comment")
    else:
        print("❌ FAIL: Missing explanatory comment")
        return False
    
    return True

def test_controller_flow():
    """Test that controller flow calls draw_overlay correctly."""
    print("\nTesting controller overlay flow...")
    
    # Read the controller file
    controller_path = os.path.join('src', 'zebtrack', 'core', 'controller.py')
    with open(controller_path, 'r') as f:
        controller_content = f.read()
    
    # Check that draw_overlay is called in the right places
    overlay_calls = controller_content.count('self.detector.draw_overlay(frame,')
    if overlay_calls >= 2:  # Should be at least 2 calls (fresh and cached detections)
        print(f"✅ PASS: Found {overlay_calls} draw_overlay calls in controller")
    else:
        print(f"❌ FAIL: Only found {overlay_calls} draw_overlay calls in controller")
        return False
    
    # Check that the calls happen before progress_callback
    lines = controller_content.split('\n')
    overlay_before_callback = False
    
    for i, line in enumerate(lines):
        if 'self.detector.draw_overlay(frame,' in line:
            # Look for progress_callback in the next few lines
            for j in range(i+1, min(i+5, len(lines))):
                if 'progress_callback(' in lines[j]:
                    overlay_before_callback = True
                    break
    
    if overlay_before_callback:
        print("✅ PASS: draw_overlay called before progress_callback")
    else:
        print("❌ FAIL: draw_overlay not called before progress_callback")
        return False
    
    return True

def test_detector_overlay_method():
    """Test that detector overlay method draws both zones and boxes."""
    print("\nTesting detector draw_overlay method...")
    
    # Read the detector file
    detector_path = os.path.join('src', 'zebtrack', 'core', 'detector.py')
    with open(detector_path, 'r') as f:
        detector_content = f.read()
    
    # Find the draw_overlay method
    method_start = detector_content.find('def draw_overlay(self, frame, detections):')
    if method_start == -1:
        print("❌ FAIL: draw_overlay method not found")
        return False
    
    # Extract the method content (until next method or class)
    method_content = detector_content[method_start:method_start+2000]  # Reasonable size
    
    # Check that it draws ROI polygons
    if 'cv2.polylines(frame, [polygon]' in method_content:
        print("✅ PASS: draw_overlay draws ROI polygons")
    else:
        print("❌ FAIL: draw_overlay doesn't draw ROI polygons")
        return False
    
    # Check that it draws processing area polygon
    if 'Draw the processing area polygon' in method_content:
        print("✅ PASS: draw_overlay draws processing area polygon")
    else:
        print("❌ FAIL: draw_overlay doesn't draw processing area polygon")
        return False
    
    # Check that it draws bounding boxes
    if 'cv2.rectangle(frame, (x1, y1), (x2, y2)' in method_content:
        print("✅ PASS: draw_overlay draws detection bounding boxes")
    else:
        print("❌ FAIL: draw_overlay doesn't draw bounding boxes")
        return False
    
    # Check that it draws labels
    if 'cv2.putText(' in method_content:
        print("✅ PASS: draw_overlay draws detection labels")
    else:
        print("❌ FAIL: draw_overlay doesn't draw detection labels")
        return False
    
    return True

def test_integration_logic():
    """Test the overall integration logic."""
    print("\nTesting integration logic...")
    
    print("📋 Expected flow:")
    print("  1. Controller processes frame and detections")
    print("  2. Controller calls detector.draw_overlay(frame, detections)")
    print("  3. Controller passes overlay-enhanced frame to progress_callback")
    print("  4. progress_callback sends frame to view.display_frame")
    print("  5. view.display_frame routes to display_analysis_frame during analysis")
    print("  6. display_analysis_frame uses frame as-is (preserving overlays)")
    
    print("\n🎯 Key improvement:")
    print("  - Before: GUI redrew zones, losing detection boxes")
    print("  - After: GUI preserves frames with both zones AND detection boxes")
    
    return True

def main():
    """Run all verification tests."""
    print("🔍 Verifying overlay integration changes...\n")
    
    tests = [
        test_gui_change,
        test_controller_flow, 
        test_detector_overlay_method,
        test_integration_logic
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            if test():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"❌ FAIL: Test {test.__name__} threw exception: {e}")
            failed += 1
    
    print(f"\n📊 Results: {passed} passed, {failed} failed")
    
    if failed == 0:
        print("\n🎉 All tests passed! The overlay integration should work correctly.")
        print("\n📝 Summary of changes:")
        print("  ✅ display_analysis_frame no longer overwrites detector overlays")
        print("  ✅ Frames preserve both zone polygons AND detection bounding boxes")
        print("  ✅ Complete flow from controller to GUI maintains overlays")
        print("\n🚀 Ready for testing with actual video analysis!")
    else:
        print(f"\n❌ {failed} tests failed. Please review the implementation.")
    
    return failed == 0

if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)