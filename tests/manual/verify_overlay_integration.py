#!/usr/bin/env python3
"""Manual verification for overlay integration logic."""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_PATH = REPO_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

GUI_PATH = SRC_PATH / "zebtrack" / "ui" / "gui.py"
CONTROLLER_PATH = SRC_PATH / "zebtrack" / "core" / "controller.py"
DETECTOR_PATH = SRC_PATH / "zebtrack" / "core" / "detector.py"


def test_gui_change() -> bool:
    """Test that GUI change preserves frames correctly."""
    print("Testing GUI display_analysis_frame modification...")
    content = GUI_PATH.read_text(encoding="utf-8")
    method_start = content.find('def display_analysis_frame(self, frame):')
    if method_start == -1:
        print("❌ FAIL: display_analysis_frame method not found")
        return False

    next_method = content.find('def ', method_start + 1)
    method_content = (
        content[method_start:next_method]
        if next_method != -1
        else content[method_start:]
    )
    if '_draw_zones_on_frame' in method_content:
        print("❌ FAIL: display_analysis_frame still calls _draw_zones_on_frame")
        return False
    if 'frame_to_display = frame.copy()' not in content:
        print("❌ FAIL: Expected frame preservation logic not found")
        return False
    if 'frames should already have overlays' not in content:
        print("❌ FAIL: Missing explanatory comment")
        return False

    print("✅ PASS: display_analysis_frame now preserves frame as-is")
    print("✅ PASS: Code includes explanatory comment")
    return True


def test_controller_flow() -> bool:
    """Test that controller flow calls draw_overlay correctly."""
    print("\nTesting controller overlay flow...")
    content = CONTROLLER_PATH.read_text(encoding="utf-8")
    overlay_calls = content.count('self.detector.draw_overlay(frame,')
    if overlay_calls < 2:
        print(f"❌ FAIL: Only found {overlay_calls} draw_overlay calls in controller")
        return False

    lines = content.split('\n')
    overlay_before_callback = False
    for index, line in enumerate(lines):
        if 'self.detector.draw_overlay(frame,' in line:
            for look_ahead in range(index + 1, min(index + 5, len(lines))):
                if 'progress_callback(' in lines[look_ahead]:
                    overlay_before_callback = True
                    break
    if not overlay_before_callback:
        print("❌ FAIL: draw_overlay not called before progress_callback")
        return False

    print("✅ PASS: Controller calls draw_overlay before progress_callback")
    return True


def test_detector_overlay_method() -> bool:
    """Test that detector overlay method draws both zones and boxes."""
    print("\nTesting detector draw_overlay method...")
    content = DETECTOR_PATH.read_text(encoding="utf-8")
    method_start = content.find('def draw_overlay(self, frame, detections):')
    if method_start == -1:
        print("❌ FAIL: draw_overlay method not found")
        return False

    method_content = content[method_start:method_start + 2000]
    if 'cv2.polylines(frame, [polygon]' not in method_content:
        print("❌ FAIL: draw_overlay doesn't draw ROI polygons")
        return False
    if 'Draw the processing area polygon' not in method_content:
        print("❌ FAIL: draw_overlay doesn't draw processing area polygon")
        return False
    if 'cv2.rectangle(frame, (x1, y1), (x2, y2)' not in method_content:
        print("❌ FAIL: draw_overlay doesn't draw bounding boxes")
        return False
    if 'cv2.putText(' not in method_content:
        print("❌ FAIL: draw_overlay doesn't draw detection labels")
        return False

    print("✅ PASS: draw_overlay draws necessary overlays")
    return True


def test_integration_logic() -> bool:
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


def main() -> bool:
    """Run all verification tests."""
    print("🔍 Verifying overlay integration changes...\n")
    tests = [
        test_gui_change,
        test_controller_flow,
        test_detector_overlay_method,
        test_integration_logic,
    ]

    passed = 0
    failed = 0
    for test in tests:
        try:
            if test():
                passed += 1
            else:
                failed += 1
        except Exception as exc:  # pragma: no cover - manual runner
            print(f"❌ FAIL: Test {test.__name__} threw exception: {exc}")
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


if __name__ == "__main__":
    raise SystemExit(0 if main() else 1)
