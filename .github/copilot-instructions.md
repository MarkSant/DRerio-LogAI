# Copilot Instructions for PyZebArdYolo

## Project Overview
PyZebArdYolo is a modular Python application for controlling and tracking zebrafish experiments using video analysis (YOLO), Arduino hardware, and a Tkinter GUI. The codebase is organized by functional modules, each responsible for a distinct aspect of the workflow.

## Architecture & Data Flow
- **GUI (`gui.py`)**: Entry point for user interaction. Orchestrates project setup, video/camera selection, and controls experiment flow.
- **Main (`main.py`)**: Launches the Tkinter GUI.
- **Camera/Video Source (`camera.py`, `video_source.py`)**: Abstracts live camera and video file input. Both expose a `get_frame()` method for frame acquisition.
- **Detection (`detector.py`)**: Uses YOLO (via `ultralytics`) to detect objects. Relies on config-defined zones and thresholds. Scales detection areas to match input resolution.
- **Arduino (`arduino.py`)**: Handles serial communication with Arduino. Commands are mapped via config constants.
- **Recorder (`recorder.py`)**: Records video and movement data (CSV) for each experiment run.
- **Project Manager (`project_manager.py`)**: Manages project directories and metadata (JSON config per project).
- **Config (`config.py`)**: Centralizes all settings (camera, Arduino, YOLO, detection zones, colors, commands).

## Developer Workflows
- **Run the App**: Execute `main.py` to launch the GUI.
- **Testing**: Run unit tests in `tests/` using `python -m unittest discover tests`.
- **Dependencies**: Install from `requirements.txt`. Note: `ultralytics` may require manual installation due to size.
- **Debugging**: Most modules print errors to console. GUI errors may use Tkinter messageboxes.

## Key Patterns & Conventions
- **Config-driven**: All hardware, detection, and zone parameters are set in `config.py` and imported everywhere.
- **Threading/Queues**: GUI uses threads and queues for video processing to keep UI responsive.
- **Project Structure**: Each experiment/project gets its own directory and JSON config, managed by `ProjectManager`.
- **Recording**: Video and CSV files are named after the project and stored in the project directory.
- **Detection Zones**: Zones and polygons are defined as lists of coordinates in config; detection logic scales them to match input size.
- **Arduino Commands**: Enter/exit commands are mapped to zone indices via config constants.

## Integration Points
- **YOLO Model**: Path set in `config.py` (`best12.pt`).
- **Arduino**: Port and baud rate set in config. Serial communication is robust to missing hardware (offline mode fallback).
- **Tkinter GUI**: All user interaction flows through `ApplicationGUI` in `gui.py`.

## Example: Adding a New Detection Zone
1. Update `SQUARES` and `COLORS` in `config.py`.
2. Detection and GUI will automatically use new zones.

## Example: Customizing Arduino Commands
- Edit `ENTER_COMMANDS` and `EXIT_COMMANDS` in `config.py` to match your hardware protocol.

## References
- See `config.py` for all global settings.
- See `gui.py` for main application flow and integration.
- See `tests/` for examples of project and recorder usage.

---
For unclear or missing conventions, ask the user for clarification or examples from their workflow.
