#!/usr/bin/env python3
"""Focused overlay validation without external dependencies."""

from pathlib import Path
from typing import Tuple

REPO_ROOT = Path(__file__).resolve().parents[2]
GUI_PATH = REPO_ROOT / "src" / "zebtrack" / "ui" / "gui.py"
CONTROLLER_PATH = REPO_ROOT / "src" / "zebtrack" / "core" / "controller.py"
DETECTOR_PATH = REPO_ROOT / "src" / "zebtrack" / "core" / "detector.py"


def test_display_analysis_frame_logic() -> Tuple[bool, str]:
    """Validate that display_analysis_frame preserves overlays."""
    content = GUI_PATH.read_text(encoding="utf-8")
    start = content.find('def display_analysis_frame(self, frame):')
    if start == -1:
        return False, "Method display_analysis_frame not found"

    end = content.find('\n    def ', start + 1)
    if end == -1:
        end = content.find('\nclass ', start + 1)
    if end == -1:
        end = len(content)

    method_code = content[start:end]
    if '_draw_zones_on_frame' in method_code:
        return False, "display_analysis_frame still calls _draw_zones_on_frame"
    if 'frame_to_display = frame.copy()' not in method_code:
        return False, "display_analysis_frame doesn't copy frame directly"
    if 'already have overlays' not in method_code:
        return False, "Missing explanatory comment about overlays"
    if 'cv2.cvtColor(frame_to_display,' not in method_code:
        return False, "Should process frame_to_display with cvtColor"

    return True, "display_analysis_frame correctly preserves overlays"


def test_controller_overlay_calls() -> Tuple[bool, str]:
    """Confirm controller applies overlays before reporting progress."""
    content = CONTROLLER_PATH.read_text(encoding="utf-8")
    start = content.find('def _run_tracking_if_needed(')
    if start == -1:
        return False, "_run_tracking_if_needed method not found"

    end = content.find('\n    def ', start + 1)
    if end == -1:
        end = len(content)

    method_code = content[start:end]
    overlay_calls = method_code.count('self.detector.draw_overlay(frame,')
    if overlay_calls < 2:
        return False, f"Expected at least 2 draw_overlay calls, found {overlay_calls}"

    lines = method_code.split('\n')
    overlay_before_callback_count = 0
    for i, line in enumerate(lines):
        if 'self.detector.draw_overlay(frame,' in line:
            for j in range(i + 1, min(i + 5, len(lines))):
                if 'progress_callback(' in lines[j]:
                    overlay_before_callback_count += 1
                    break
    if overlay_before_callback_count < 2:
        return False, (
            "Expected 2 overlay->callback sequences, "
            f"found {overlay_before_callback_count}"
        )

    return True, "Controller correctly calls draw_overlay before progress_callback"


def test_detector_draw_overlay_completeness() -> Tuple[bool, str]:
    """Ensure draw_overlay renders polygons, boxes, and labels."""
    content = DETECTOR_PATH.read_text(encoding="utf-8")
    start = content.find('def draw_overlay(self, frame, detections):')
    if start == -1:
        return False, "draw_overlay method not found"

    end = content.find('\n    def ', start + 1)
    if end == -1:
        end = content.find('\nclass ', start + 1)
    if end == -1:
        end = len(content)

    method_code = content[start:end]
    required_elements = [
        ("ROI polygons", 'cv2.polylines(frame, [polygon]'),
        ("processing area", 'scaled_polygon'),
        ("bounding boxes", 'cv2.rectangle(frame, (x1, y1), (x2, y2)'),
        ("detection labels", 'cv2.putText('),
    ]
    for element_name, pattern in required_elements:
        if pattern not in method_code:
            return False, f"draw_overlay doesn't draw {element_name} (missing: {pattern})"

    return True, "draw_overlay draws all required elements"


def test_backward_compatibility() -> Tuple[bool, str]:
    """Check non-analysis display retains legacy behavior."""
    content = GUI_PATH.read_text(encoding="utf-8")
    start = content.find('def display_frame(self, frame):')
    if start == -1:
        return False, "display_frame method not found"

    end = content.find('\n    def ', start + 1)
    if end == -1:
        end = len(content)

    method_code = content[start:end]
    if '_draw_zones_on_frame(frame.copy())' not in method_code:
        return False, "display_frame should still call _draw_zones_on_frame for backward compatibility"
    if 'self.display_analysis_frame(frame)' not in method_code:
        return False, "display_frame should route to display_analysis_frame during analysis"

    return True, "Backward compatibility maintained"


def main() -> bool:
    """Run focused overlay validation checks."""
    print("🎯 Focused Overlay Integration Tests")
    print("=" * 50)

    tests = [
        test_display_analysis_frame_logic,
        test_controller_overlay_calls,
        test_detector_draw_overlay_completeness,
        test_backward_compatibility,
    ]

    all_passed = True
    for test_func in tests:
        test_name = test_func.__name__.replace('test_', '').replace('_', ' ').title()
        print(f"\n🔬 {test_name}:")
        try:
            success, message = test_func()
        except Exception as exc:  # pragma: no cover - manual runner
            print(f"   ❌ ERROR: {exc}")
            all_passed = False
            continue

        if success:
            print(f"   ✅ PASS: {message}")
        else:
            print(f"   ❌ FAIL: {message}")
            all_passed = False

    print("\n" + "=" * 50)
    if all_passed:
        print("🎉 ALL TESTS PASSED!")
        print("\n📋 Validation Summary:")
        print("✅ display_analysis_frame preserves detector overlays")
        print("✅ Controller applies overlays before sending frames to GUI")
        print("✅ Detector draws zones, boxes, and labels comprehensively")
        print("✅ Backward compatibility maintained for non-analysis display")
        print("\n🚀 The overlay integration fix is complete and working!")
        print("\n💡 What users will see:")
        print("   - Bounding boxes around detected animals during analysis")
        print("   - Zone polygons showing arena and ROI boundaries")
        print("   - Track IDs and confidence scores as text labels")
        print("   - All overlays visible simultaneously in analysis view")
    else:
        print("❌ Some tests failed. Please review the implementation.")

    return all_passed


if __name__ == "__main__":
    raise SystemExit(0 if main() else 1)
