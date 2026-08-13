"""Coordinator for user dialogs and confirmations.

Extracted from MainViewModel as part of Phase 1 of the refactoring
plan (PLANO_REFATORACAO_MAINVIEWMODEL.md).
Responsible for coordinating all user dialogs and confirmations.
"""

from pathlib import Path
from typing import TYPE_CHECKING

import structlog

from zebtrack.core.video.video_metadata_service import VideoMetadataService
from zebtrack.i18n import _
from zebtrack.ui import payloads
from zebtrack.ui.event_bus_v2 import Event, UIEvents

if TYPE_CHECKING:
    from zebtrack.core.project.project_manager import ProjectManager
    from zebtrack.core.state_manager import StateManager
    from zebtrack.core.ui_scheduler import UIScheduler
    from zebtrack.ui.event_bus_v2 import EventBusV2

log = structlog.get_logger()


class DialogCoordinator:
    """Coordinator for user dialogs and confirmations.

    Centralizes all user interaction logic through dialogs,
    decoupling MainViewModel from direct view calls.

    Attributes:
        ui_coordinator: UI coordinator for showing dialogs.
        event_bus: Event bus for UI communication.
        state_manager: Application state manager.
        project_manager: Project manager (for zone validation).
    """

    def __init__(
        self,
        ui_coordinator: "UIScheduler",
        event_bus: "EventBusV2 | None",
        state_manager: "StateManager",
        project_manager: "ProjectManager | None" = None,
        video_metadata_service: VideoMetadataService | None = None,
    ):
        """Initialize the dialog coordinator.

        Args:
            ui_coordinator: UI coordinator.
            event_bus: Event bus (optional).
            state_manager: State manager.
            project_manager: Project manager (optional,
                but required for zone validation).
            video_metadata_service: Video metadata service (optional).
        """
        self.ui_coordinator = ui_coordinator
        self.event_bus = event_bus
        self.state_manager = state_manager
        self.project_manager = project_manager
        self.video_metadata_service = video_metadata_service or VideoMetadataService()
        self.log = structlog.get_logger()

    def confirm_exit(self) -> bool:
        """Request user confirmation to exit the application.

        Returns:
            True if user confirmed, False otherwise.
        """
        return self.ui_coordinator.ask_ok_cancel(_("Exit"), _("Do you really want to exit?"))

    def handle_mixed_data_scenario(
        self,
        scanned_videos: list[dict],
    ) -> list[dict] | None:
        """Handle scenario where some videos have data and others don't.

        Args:
            scanned_videos: List of scanned video information dicts.

        Returns:
            List of videos to process, or None if all should be
            ignored/only added.
        """
        with_data = [v for v in scanned_videos if v.get("has_data")]
        without_data = [v for v in scanned_videos if not v.get("has_data")]

        if with_data and without_data:
            # Mixed case: some have data, others don't
            return self._handle_mixed_case(scanned_videos, with_data, without_data)
        elif with_data and not without_data:
            # All selected videos have data
            return self._handle_all_have_data(scanned_videos, with_data)
        else:
            # No videos have data, process all
            return without_data

    def _handle_mixed_case(
        self,
        scanned_videos: list[dict],
        with_data: list[dict],
        without_data: list[dict],
    ) -> list[dict]:
        """Handle case where there is a mix of videos with and without data.

        Args:
            scanned_videos: All scanned videos.
            with_data: Videos that already have data.
            without_data: Videos without data.

        Returns:
            Videos to process.
        """
        msg = _(
            "{with_data} video(s) already have analysis data.\n"
            "{without_data} video(s) need processing.\n\n"
            "Do you want to reprocess the videos that already have data?"
        ).format(with_data=len(with_data), without_data=len(without_data))

        if self.ui_coordinator.ask_ok_cancel(_("Mixed Data Found"), msg):
            self.log.info(
                "dialog.mixed_data.reprocess_all",
                total=len(scanned_videos),
                with_data=len(with_data),
                without_data=len(without_data),
            )
            return scanned_videos
        else:
            self.log.info(
                "dialog.mixed_data.skip_existing",
                total=len(scanned_videos),
                processing=len(without_data),
            )
            return without_data

    def _handle_all_have_data(
        self,
        scanned_videos: list[dict],
        with_data: list[dict],
    ) -> list[dict] | None:
        """Handle case where all videos already have data.

        Args:
            scanned_videos: All scanned videos.
            with_data: Videos that have data (same as scanned_videos in this case).

        Returns:
            Videos to process, or None if none should be processed.
        """
        if self.ui_coordinator.ask_ok_cancel(
            _("Data Found"),
            _("Every selected video already has analysis data. Do you want to reprocess them all?"),
        ):
            self.log.info(
                "dialog.all_have_data.reprocess",
                total=len(with_data),
            )
            return with_data
        else:
            # User doesn't want to reprocess - add to project but don't process
            self._show_processing_skipped_info()
            # Note: Responsibility for adding to the project lies with the caller
            # The dialog coordinator only decides WHAT to process
            self.log.info(
                "dialog.all_have_data.skip",
                total=len(with_data),
            )
            return None  # Signal: do not process

    def validate_zones_with_ui(self, video_path: Path | str | None = None) -> bool:
        """
        Validate that zones are defined, with UI dialogs for user interaction.

        Ported from UIStateController.
        Handles complex zone validation including main arena validation.

        Returns:
            bool: True if zones are valid/created, False if user cancelled
        """
        if not self.project_manager:
            self.log.error("dialog.validate_zones.no_project_manager")
            return False

        target_video = str(video_path) if video_path is not None else None
        target_video = target_video or self.project_manager.get_active_zone_video()
        multi_zone_data = (
            self.project_manager.get_multi_aquarium_zone_data(target_video)
            if target_video
            else None
        )
        zone_data = self.project_manager.get_zone_data(video_path=target_video)
        has_main_arena = bool(zone_data and zone_data.polygon)
        if multi_zone_data:
            has_main_arena = bool(multi_zone_data.aquariums) and all(
                len(aquarium.polygon) >= 3 for aquarium in multi_zone_data.aquariums
            )

        # Check if main arena is defined
        if not has_main_arena:
            self.log.warning("workflow.project_processing.no_main_arena")

            response = self.ui_coordinator.ask_ok_cancel(
                _("Main Arena Not Defined"),
                _(
                    "The main aquarium polygon has not been defined.\n\n"
                    "The main arena is required for an accurate analysis.\n"
                    "Do you want to define it now, before processing?"
                ),
            )

            if response:
                # Switch to zone tab and guide user
                if self.event_bus:
                    self.event_bus.publish(
                        Event(
                            type=UIEvents.UI_SELECT_TAB,
                            data=payloads.UISelectTabPayload(tab_name="zone_tab"),
                        )
                    )

                    # Load the selected video frame when available.
                    frame_video = target_video or self.project_manager.get_next_video()
                    if frame_video:
                        self.event_bus.publish(
                            Event(
                                type=UIEvents.UI_DISPLAY_VIDEO_FRAME,
                                data=payloads.VideoPathPayload(video_path=frame_video),
                            )
                        )

                        self.event_bus.publish(
                            Event(
                                type=UIEvents.UI_SHOW_INFO,
                                data=payloads.MessagePayload(
                                    title=_("Define the Main Arena"),
                                    message=_(
                                        "Please:\n"
                                        "1. Use 'Detect Aquarium (Auto)' or\n"
                                        "2. Draw the main polygon manually\n"
                                        "3. Then come back to add videos"
                                    ),
                                ),
                            )
                        )
                return False
            else:
                # Offer default arena as fallback
                if not self.ui_coordinator.ask_ok_cancel(
                    _("Use the Default Arena?"),
                    _(
                        "Do you want to use the whole frame as the arena?\n"
                        "(Not recommended for an accurate analysis)"
                    ),
                ):
                    self.log.info("workflow.project_processing.cancelled_no_arena")
                    return False

                # Create default arena based on the selected video.
                frame_video = target_video or self.project_manager.get_next_video()
                if frame_video:
                    try:
                        # Use VideoMetadataService to get dimensions
                        dimensions = self.video_metadata_service.get_video_dimensions(frame_video)
                        if not dimensions:
                            self.show_error(_("Error"), _("Could not read the video dimensions"))
                            return False

                        width, height = dimensions
                        default_arena = [[0, 0], [width, 0], [width, height], [0, height]]

                        # Update project manager with default arena
                        zone_data.polygon = default_arena
                        self.project_manager.save_zone_data(zone_data, video_path=target_video)

                        self.log.info(
                            "workflow.project_processing.default_arena_created",
                            size=f"{width}x{height}",
                        )

                        if self.event_bus:
                            self.event_bus.publish(
                                Event(
                                    type=UIEvents.UI_SHOW_INFO,
                                    data=payloads.MessagePayload(
                                        title=_("Default Arena Created"),
                                        message=_(
                                            "Default arena created ({width}x{height})\n"
                                            "Adjusting it manually afterwards is recommended."
                                        ).format(width=width, height=height),
                                    ),
                                )
                            )
                            # Trigger redraw
                            self.event_bus.publish(Event(type=UIEvents.UI_REDRAW_ZONES))
                    except Exception as e:  # except Exception justified: non-critical fallback
                        self.show_error(
                            _("Error"),
                            _("Could not create the default arena: {error}").format(error=e),
                        )
                        return False
                else:
                    self.show_error(_("Error"), _("No video found in the project"))
                    return False

        # Warn about missing ROIs (optional but informative)
        if not zone_data.roi_polygons:
            if not self.ui_coordinator.ask_ok_cancel(
                _("No ROI Defined"),
                _(
                    "No Region of Interest (ROI) has been defined.\n\n"
                    "The analysis will use the main arena only.\n"
                    "For detailed analyses, consider defining ROIs.\n\n"
                    "Do you want to continue?"
                ),
            ):
                self.log.info("workflow.project_processing.cancelled_by_user_no_roi")
                return False

        self.log.info(
            "workflow.project_processing.zones_validated",
            has_main_arena=has_main_arena,
            roi_count=len(zone_data.roi_polygons),
        )

        return True

    def _show_processing_skipped_info(self) -> None:
        """Show informational dialog about skipped processing."""
        if self.event_bus:
            self.event_bus.publish(
                Event(
                    type=UIEvents.UI_SHOW_INFO,
                    data=payloads.MessagePayload(
                        title=_("Processing Skipped"),
                        message=_("No new video was processed."),
                    ),
                )
            )
        else:
            self.ui_coordinator.show_info(
                _("Processing Skipped"),
                _("No new video was processed."),
            )

    def show_info(self, title: str, message: str) -> None:
        """Show an informational dialog."""
        self.ui_coordinator.show_info(title, message)

    def show_warning(self, title: str, message: str) -> None:
        """Show a warning dialog."""
        self.ui_coordinator.show_warning(title, message)

    def show_error(self, title: str, message: str) -> None:
        """Show an error dialog."""
        self.ui_coordinator.show_error(title, message)

    def ask_yes_no(self, title: str, message: str) -> bool:
        """Request a yes/no confirmation from the user."""
        return self.ui_coordinator.ask_ok_cancel(title, message)

    def handle_validation_error(self, validation_result) -> bool:
        """
        Handle validation errors by showing appropriate UI messages.

        Args:
            validation_result: ValidationResult from ProcessingCoordinator

        Returns:
            bool: True if validation passed, False if error was shown
        """
        if validation_result.is_valid:
            return True

        # Map error codes to appropriate UI events
        error_code = validation_result.error_code
        error_message = validation_result.error_message

        if self.event_bus:
            if error_code == "processing_already_active":
                self.event_bus.publish(
                    Event(
                        type=UIEvents.UI_SHOW_WARNING,
                        data=payloads.MessagePayload(
                            title=_("Analysis Running"),
                            message=error_message,
                        ),
                    )
                )
            elif error_code == "no_project_loaded":
                self.event_bus.publish(
                    Event(
                        type=UIEvents.UI_SHOW_ERROR,
                        data=payloads.ErrorOccurredPayload(
                            title=_("No Project Loaded"),
                            message=error_message,
                        ),
                    )
                )
            elif error_code == "no_videos":
                self.event_bus.publish(
                    Event(
                        type=UIEvents.UI_SHOW_ERROR,
                        data=payloads.ErrorOccurredPayload(
                            title=_("No Video Found"),
                            message=error_message,
                        ),
                    )
                )
            elif error_code == "no_weight_selected":
                self.event_bus.publish(
                    Event(
                        type=UIEvents.UI_SHOW_ERROR,
                        data=payloads.ErrorOccurredPayload(
                            title=_("Weight Not Selected"),
                            message=error_message,
                        ),
                    )
                )
            else:
                # Generic error fallback
                self.event_bus.publish(
                    Event(
                        type=UIEvents.UI_SHOW_ERROR,
                        data=payloads.ErrorOccurredPayload(
                            title=_("Validation Error"),
                            message=error_message,
                        ),
                    )
                )
        else:
            # Fallback to UI Coordinator direct calls if no event bus
            if error_code == "processing_already_active":
                self.ui_coordinator.show_warning(_("Analysis Running"), error_message)
            else:
                self.ui_coordinator.show_error(_("Validation Error"), error_message)

        return False
