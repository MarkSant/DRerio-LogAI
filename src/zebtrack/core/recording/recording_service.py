"""
Recording Service - Phase 2.2: Recording & Arduino Consolidation.

Extracts recording session orchestration logic from MainViewModel.
Coordinates recorder, state management, Arduino hardware, and UI feedback.

Responsibilities:
- Schedule recording sessions (with optional countdown)
- Start/stop recording sessions
- Manage timed recording jobs
- Coordinate Arduino commands during recording lifecycle
- Update StateManager with recording state transitions
"""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from tkinter import Label, Toplevel
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from tkinter import Misc

    from zebtrack.core.main_view_model import MainViewModel
    from zebtrack.core.project.project_manager import ProjectManager
    from zebtrack.core.state_manager import StateManager

log = structlog.get_logger()


class RecordingService:
    """
    Service for managing recording session lifecycle.

    Coordinates between Recorder, StateManager, ProjectManager, and ArduinoManager
    to orchestrate recording sessions with proper state tracking and hardware control.

    Note: Stores controller reference to access dynamically updated recorder and
    arduino_manager instances (which can be replaced in tests).
    """

    def __init__(
        self,
        state_manager: StateManager,
        project_manager: ProjectManager,
        controller: MainViewModel | None = None,
        root: Misc | None = None,
    ):
        """
        Initialize RecordingService.

        Args:
            controller: MainViewModel controller for accessing recorder and arduino_manager.
                        Can be None during construction and set later.
            state_manager: StateManager for centralized state tracking
            project_manager: ProjectManager for project-specific data
            root: Tkinter root for scheduling timed jobs
        """
        self.controller = controller
        self.state_manager = state_manager
        self.project_manager = project_manager
        self.root = root

        # Timed recording job handle
        self.timed_recording_job: str | None = None

        # UI callbacks (injected by MainViewModel)
        self._ui_callbacks: dict[str, Callable] = {}

    @property
    def recorder(self):
        """Property to access controller's current recorder instance."""
        if self.controller is None:
            raise RuntimeError("RecordingService.controller not yet set")
        return self.controller.recorder

    @property
    def arduino_manager(self):
        """Property to access controller's current arduino_manager instance."""
        if self.controller is None:
            raise RuntimeError("RecordingService.controller not yet set")
        return self.controller.arduino_manager

    def set_ui_callbacks(self, callbacks: dict[str, Callable]) -> None:
        """
        Set UI callbacks for view updates.

        Expected callbacks:
        - show_error(title: str, message: str)
        - update_button_state(button: str, state: str)
        - set_status(message: str)
        - schedule_on_ui(func: Callable, *args, **kwargs)
        """
        self._ui_callbacks = callbacks

    def schedule_recording(
        self,
        context: dict[str, Any],
        project_data: dict[str, Any],
        *,
        trigger_source: str,
    ) -> None:
        """
        Schedule a recording session with optional countdown.

        Args:
            context: Recording session context (day, group, cobaia, folders, Arduino state)
            project_data: Project configuration (countdown settings, timed recording, etc)
            trigger_source: Source identifier for logging (e.g., "manual", "external", "grid")
        """
        countdown_s = int(project_data.get("countdown_duration_s", 0) or 0)
        use_countdown = bool(project_data.get("use_countdown")) and countdown_s > 0

        def _start_now():
            self.start_session(context, project_data, trigger_source)

        if use_countdown:
            self._run_countdown(countdown_s, _start_now)
        else:
            _start_now()

    def start_session(
        self,
        context: dict[str, Any],
        project_data: dict[str, Any],
        trigger_source: str,
    ) -> None:
        """
        Start a recording session immediately.

        Args:
            context: Recording session context
            project_data: Project configuration
            trigger_source: Source identifier for logging
        """
        folder_name = context["folder_name"]
        output_folder = context["output_folder"]

        zone_data = self.project_manager.get_zone_data()

        # Validate camera dimensions (injected via context)
        camera_width = context.get("camera_width")
        camera_height = context.get("camera_height")

        if camera_width is None or camera_height is None:
            self._show_error(
                "Erro",
                "Configuração da câmera indisponível para iniciar a gravação.",
            )
            self._update_button_state("start_rec", "normal")
            return

        # Save metadata for this recording session (will be used when video is registered)
        metadata_to_save = {}
        if "day" in context:
            metadata_to_save["day"] = context["day"]
        if "group" in context:
            metadata_to_save["group"] = context["group"]
        if "cobaia" in context:
            metadata_to_save["subject"] = context[
                "cobaia"
            ]  # Use 'subject' key as per project_manager

        if metadata_to_save:
            import json

            metadata_file = Path(output_folder) / "_recording_metadata.json"
            try:
                with open(metadata_file, "w", encoding="utf-8") as f:
                    json.dump(metadata_to_save, f, indent=2)
                log.info(
                    "recording_service.metadata_saved",
                    metadata=metadata_to_save,
                    path=str(metadata_file),
                )
            except (OSError, TypeError, ValueError) as e:
                log.warning(
                    "recording_service.metadata_save_failed",
                    error=str(e),
                    metadata=metadata_to_save,
                )

        # Start recorder
        recording_started = self.recorder.start_recording(
            output_folder,
            camera_width,
            camera_height,
            zones=zone_data,
        )

        # Update StateManager
        self.state_manager.update_recording_state(
            source=f"recording_service.start_session.{trigger_source}",
            is_recording=recording_started,
            output_path=Path(output_folder) if recording_started else None,
            recording_start_time=datetime.now() if recording_started else None,
        )

        if not recording_started:
            self._show_error("Erro", "Não foi possível iniciar a gravação.")
            self._update_button_state("start_rec", "normal")
            self._update_button_state("stop_rec", "disabled")
            return

        # Update UI
        self._update_button_state("start_rec", "disabled")
        self._update_button_state("stop_rec", "normal")
        self._set_status(f"Recording session: {folder_name}")

        # Send Arduino start command
        if context.get("arduino_enabled") and self.arduino_manager:
            box_number = self._resolve_box_number(
                context["day"], context["group"], context["cobaia"]
            )
            if box_number is None:
                log.warning(
                    "recording_service.arduino_invalid_box",
                    day=context["day"],
                    group=context["group"],
                    cobaia=context["cobaia"],
                )
            else:
                self.arduino_manager.send_command(box_number, source=f"{trigger_source}-start")

        # Setup timed recording
        if project_data.get("use_timed_recording"):
            duration_s = project_data.get("recording_duration_s", 0) or 0
            if duration_s > 0 and self.root:
                duration_ms = int(duration_s * 1000)
                # Callback will be injected
                stop_callback = self._ui_callbacks.get("stop_recording_callback")
                if stop_callback:
                    self.timed_recording_job = self.root.after(duration_ms, stop_callback)
                    log.info(
                        "recording_service.timed_recording_scheduled",
                        duration_s=duration_s,
                        trigger=trigger_source,
                    )

    def stop_session(self) -> None:
        """
        Stop the current recording session.

        Cancels timed recording jobs, stops recorder, sends Arduino stop commands,
        and updates StateManager.
        """
        log.info("recording_service.stop_session")

        # Cancel timed recording job
        if self.timed_recording_job and self.root:
            self.root.after_cancel(self.timed_recording_job)
            self.timed_recording_job = None
            log.info("recording_service.timed_cancelled")

        # Stop recorder
        recording_state = self.state_manager.get_recording_state()
        if recording_state.is_recording:
            self.recorder.stop_recording()
            self.state_manager.update_recording_state(
                source="recording_service.stop_session",
                is_recording=False,
                output_path=None,
            )

        # Send Arduino stop command
        project_data = getattr(self.project_manager, "project_data", {}) or {}
        if project_data.get("use_arduino"):
            manager = self.arduino_manager
            if manager and manager.is_connected():
                if not manager.send_command(0, source="manual-stop"):
                    log.warning("recording_service.arduino_stop_failed")
            else:
                log.warning("recording_service.arduino_stop_not_connected")

        # Update UI
        self._update_button_state("start_rec", "normal")
        self._update_button_state("stop_rec", "disabled")

    def _run_countdown(self, duration_s: int, callback: Callable) -> None:
        """
        Display a countdown window and execute callback when finished.

        Args:
            duration_s: Countdown duration in seconds
            callback: Function to call after countdown completes
        """
        if not self.root:
            log.warning("recording_service.countdown_no_root")
            callback()
            return

        countdown_window = Toplevel(self.root)
        countdown_window.overrideredirect(True)  # Remove title bar
        countdown_window.attributes("-topmost", True)
        countdown_label = Label(
            countdown_window, font=("Helvetica", 150, "bold"), bg="black", fg="white"
        )
        countdown_label.pack(expand=True, fill="both")

        # Center the window
        win_w, win_h = 200, 200
        pos_x = (self.root.winfo_screenwidth() // 2) - (win_w // 2)
        pos_y = (self.root.winfo_screenheight() // 2) - (win_h // 2)
        countdown_window.geometry(f"{win_w}x{win_h}+{pos_x}+{pos_y}")

        callback_executed = False

        def finish_countdown() -> None:
            nonlocal callback_executed
            if callback_executed:
                return
            callback_executed = True

            if countdown_window.winfo_exists():
                countdown_window.destroy()

            callback()

        def update_timer(seconds_left: int) -> None:
            if not countdown_window.winfo_exists():
                return

            if seconds_left <= 0:
                finish_countdown()
                return

            countdown_label.config(text=str(seconds_left))

            if self.root:
                self.root.after(1000, lambda: update_timer(seconds_left - 1))
            else:
                finish_countdown()

        try:
            update_timer(int(duration_s))
        except tk.TclError as exc:
            log.warning("recording_service.countdown_failed", error=str(exc))
            callback()

    def _resolve_box_number(self, day: int, group: str, cobaia: str) -> int | None:
        """
        Resolve Arduino box number from session identifiers.

        By default converts cobaia to int. Override if custom mapping needed.

        Args:
            day: Day identifier
            group: Group identifier
            cobaia: Subject/cobaia identifier

        Returns:
            Arduino box number (relay channel) or None if resolution fails
        """
        try:
            return int(cobaia)
        except (TypeError, ValueError):
            log.warning(
                "recording_service.box_resolution_failed",
                day=day,
                group=group,
                cobaia=cobaia,
            )
            return None

    # UI callback wrappers
    def _show_error(self, title: str, message: str) -> None:
        """Show error dialog via UI callback."""
        callback = self._ui_callbacks.get("show_error")
        if callback:
            callback(title, message)

    def _update_button_state(self, button: str, state: str) -> None:
        """Update button state via UI callback."""
        callback = self._ui_callbacks.get("update_button_state")
        if callback:
            callback(button, state)

    def _set_status(self, message: str) -> None:
        """Set status message via UI callback."""
        callback = self._ui_callbacks.get("set_status")
        if callback:
            callback(message)
