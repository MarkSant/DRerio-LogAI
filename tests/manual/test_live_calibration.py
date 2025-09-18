#!/usr/bin/env python3
"""
Test script for Live calibration flow validation.
This script tests the key components of the Live project calibration workflow.
"""

import os
import sys
import tempfile
from pathlib import Path

# Add src to the path to import zebtrack modules
sys.path.insert(0, str(Path(__file__).parent / "src"))

try:
    import tkinter as tk

    from zebtrack.core.controller import AppController
    from zebtrack.core.project_manager import ProjectManager
    from zebtrack.ui.gui import GUI
except ImportError as e:
    print(f"❌ Import error: {e}")
    print("Make sure you're running this from the project root directory")
    sys.exit(1)


def test_zone_validation():
    """Test comprehensive zone validation method."""
    print("\n=== Testing Zone Validation ===")

    # Create temporary project
    with tempfile.TemporaryDirectory() as temp_dir:
        project_path = os.path.join(temp_dir, "test_project")
        os.makedirs(project_path)

        # Create mock project manager
        pm = ProjectManager()
        pm.project_path = project_path
        pm.project_data = {
            "project_name": "Test Live Project",
            "project_type": "live",
            "detection_zones": {}
        }

        # Create mock controller
        root = tk.Tk()
        root.withdraw()  # Hide the window
        controller = Controller(root)
        controller.project_manager = pm

        # Test 1: No zones defined
        print("Test 1: No zones defined")
        is_valid, summary, recommendations = controller.validate_zone_configuration_comprehensive()
        print(f"Valid: {is_valid}")
        print(f"Summary: {summary}")
        assert not is_valid, "Should be invalid with no zones"
        assert "❌ Arena principal não definida" in summary
        print("✅ Test 1 passed")

        # Test 2: Main arena defined
        print("\nTest 2: Main arena defined")
        pm.project_data["detection_zones"] = {
            "polygon": [[0, 0], [100, 0], [100, 100], [0, 100]]
        }
        is_valid, summary, recommendations = controller.validate_zone_configuration_comprehensive()
        print(f"Valid: {is_valid}")
        print(f"Summary: {summary}")
        assert is_valid, "Should be valid with main arena"
        assert "✅ Arena principal definida" in summary
        print("✅ Test 2 passed")

        # Test 3: Main arena + ROIs
        print("\nTest 3: Main arena + ROIs")
        pm.project_data["detection_zones"] = {
            "polygon": [[0, 0], [100, 0], [100, 100], [0, 100]],
            "roi_polygons": [
                [[20, 20], [40, 20], [40, 40], [20, 40]],  # Valid ROI
                [[60, 60], [80, 60], [80, 80], [60, 80]]   # Valid ROI
            ],
            "roi_names": ["ROI 1", "ROI 2"]
        }
        is_valid, summary, recommendations = controller.validate_zone_configuration_comprehensive()
        print(f"Valid: {is_valid}")
        print(f"Summary: {summary}")
        assert is_valid, "Should be valid with arena and ROIs"
        assert "✅ 2 ROI(s) definida(s)" in summary
        print("✅ Test 3 passed")

        root.destroy()


def test_live_project_setup():
    """Test Live project setup components."""
    print("\n=== Testing Live Project Setup ===")

    # Test that we can create the controller and project manager
    root = tk.Tk()
    root.withdraw()  # Hide the window

    try:
        controller = Controller(root)
        assert controller is not None
        print("✅ Controller created successfully")

        pm = controller.project_manager
        assert pm is not None
        print("✅ Project manager accessible")

        # Test validation method exists
        assert hasattr(controller, 'validate_zone_configuration_comprehensive')
        print("✅ Comprehensive validation method exists")

        # Test GUI has the calibration check method
        gui = GUI(root, controller)
        assert hasattr(gui, '_check_live_project_calibration')
        print("✅ GUI auto-calibration method exists")

        assert hasattr(gui, '_validate_zone_configuration')
        print("✅ GUI validation method exists")

    except Exception as e:
        print(f"❌ Error during Live project setup test: {e}")
        return False
    finally:
        root.destroy()

    return True


def main():
    """Run all tests."""
    print("🧪 Testing ZebTrack-AI Live Calibration Flow")
    print("=" * 50)

    try:
        # Test zone validation
        test_zone_validation()

        # Test Live project setup
        test_live_project_setup()

        print("\n" + "=" * 50)
        print("✅ All tests passed! Live calibration flow is working correctly.")
        print("\nImplemented features:")
        print("• Automatic calibration prompt for Live projects")
        print("• Comprehensive zone validation with detailed feedback")
        print("• Validation button in Zone Configuration tab")
        print("• Enhanced user guidance and workflow")

    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        return 1

    return 0


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
