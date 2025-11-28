#!/usr/bin/env python3
import importlib
import sys


def check_import(module_name, display_name=None):
    if display_name is None:
        display_name = module_name
    try:
        importlib.import_module(module_name)
        print(f"✅ {display_name} imported successfully.")
        return True
    except ImportError as e:
        print(f"❌ Failed to import {display_name}: {e}")
        return False
    except Exception as e:
        print(f"❌ Error while importing {display_name}: {e}")
        return False


def check_tkinter():
    import importlib.util

    try:
        # Check if tkinter is available without importing
        if importlib.util.find_spec("tkinter") is not None:
            # In a headless environment without X server (or xvfb running), this might fail
            # strictly on root creation if DISPLAY is not set.
            # We just check availability here. The setup script handles xvfb.
            print("✅ tkinter is available.")
            return True
        print("❌ tkinter module not found.")
        return False
    except (ImportError, ValueError) as e:
        print(f"❌ Failed to check tkinter: {e}")
        return False


def main():
    print("--- Verifying Environment Setup ---")

    checks = [
        lambda: check_import("cv2", "OpenCV"),
        lambda: check_import("openvino", "OpenVINO"),
        lambda: check_import("ultralytics", "Ultralytics (YOLO)"),
        lambda: check_import("torch", "PyTorch"),
        check_tkinter,
    ]

    failed = False
    for check in checks:
        if not check():
            failed = True

    if failed:
        print("\n❌ Setup verification FAILED.")
        sys.exit(1)
    else:
        print("\n✅ Setup verification PASSED.")
        sys.exit(0)


if __name__ == "__main__":
    main()
