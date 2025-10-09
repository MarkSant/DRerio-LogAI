# Manual Test Utilities

This directory holds interactive or high-level verification scripts that supplement the automated pytest suite. They are intentionally excluded from automatic collection because several rely on Tkinter windows or direct inspection of generated text output.

## Available Scripts

- `overlay_integration_validation.py` – Static checks that confirm GUI and detector overlays include the expected logic.
- `progress_stats_manual_check.py` – Exercises the progress statistics GUI updates with a real Tkinter root window.
- `progress_stats_sanity.py` – Lightweight sanity checks for progress statistics calculations and imports.
- `verify_interval_frames.py` – Legacy shim that points to the automated pytest coverage for interval frame settings.
- `verify_overlay_integration.py` – Expanded overlay verification with step-by-step validation output.
- `visual_overlay_test.py` – Textual walkthrough of the overlay flow and expected visuals.

## Usage

Run any script directly with Python from the project root:

```powershell
python tests/manual/overlay_integration_validation.py
```

These scripts print rich diagnostics and return non-zero exit codes on failure, making them suitable for ad-hoc verification before larger refactors.
