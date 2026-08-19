"""Extended unit tests for ui/components/zone_controls.py."""

from __future__ import annotations

from unittest.mock import MagicMock

from zebtrack.ui.components.zone_controls import (
    ZoneControlsWidget,
    _hierarchy_labels,
)
from zebtrack.ui.event_bus_v2 import UIEvents
from zebtrack.ui.payloads import (
    LiveRecordingPendingPayload,
)


class TestZoneControlsExtended:
    def test_hierarchy_labels(self):
        labels = _hierarchy_labels()
        assert "group" in labels
        assert "day" in labels
        assert "subject" in labels
        assert isinstance(labels["group"], str)
        assert isinstance(labels["day"], str)
        assert isinstance(labels["subject"], str)

    def test_has_pending_live_session_and_banner_toggle(self):
        widget = object.__new__(ZoneControlsWidget)
        widget._pending_session_payload = None
        widget.pending_session_frame = MagicMock()
        widget.pending_session_label = MagicMock()

        assert widget.has_pending_live_session() is False

        payload = LiveRecordingPendingPayload(
            experiment_id="exp1", group="G1", day="Dia_1", subject_id="Sub_1"
        )
        widget._show_pending_session_banner(payload)
        assert widget.has_pending_live_session() is True
        widget.pending_session_frame.pack.assert_called_once()
        widget.pending_session_label.config.assert_called_once()

        widget._hide_pending_session_banner()
        assert widget.has_pending_live_session() is False
        widget.pending_session_frame.pack_forget.assert_called_once()

    def test_pending_session_actions_emit_events(self):
        widget = object.__new__(ZoneControlsWidget)
        widget.emit_event = MagicMock()  # type: ignore[assignment]
        widget._hide_pending_session_banner = MagicMock()  # type: ignore[assignment]

        payload = LiveRecordingPendingPayload(experiment_id="exp42")
        widget._pending_session_payload = payload

        # Start clicked
        widget._on_start_pending_recording_clicked()
        widget.emit_event.assert_called_once()
        assert widget.emit_event.call_args[0][0] == UIEvents.LIVE_RECORDING_RESUME_REQUESTED

        widget.emit_event.reset_mock()
        # Cancel clicked
        widget._on_cancel_pending_recording_clicked()
        widget.emit_event.assert_called_once()
        assert widget.emit_event.call_args[0][0] == UIEvents.LIVE_RECORDING_CANCELLED
        widget._hide_pending_session_banner.assert_called_once()

    def test_action_buttons_emit_events(self):
        widget = object.__new__(ZoneControlsWidget)
        widget.emit_event = MagicMock()  # type: ignore[assignment]
        widget.stabilization_frames_var = MagicMock()
        widget.stabilization_frames_var.get.return_value = "15"
        widget.roi_template_var = MagicMock()
        widget.roi_template_var.get.return_value = "custom_tmpl"

        # Conclude
        widget._on_conclude_video_clicked()
        assert widget.emit_event.call_args[0][0] == UIEvents.ZONE_CONCLUDE_VIDEO

        # Auto detect
        widget._on_auto_detect_clicked()
        assert widget.emit_event.call_args[0][0] == UIEvents.ZONE_AUTO_DETECT_CLICKED

        # Draw main polygon
        widget._on_draw_main_polygon_clicked()
        assert widget.emit_event.call_args[0][0] == UIEvents.ZONE_DRAW_ARENA

        # Draw ROI
        widget._on_draw_roi_clicked()
        assert widget.emit_event.call_args[0][0] == UIEvents.ZONE_DRAW_ROI

        # Toggle view
        widget._on_toggle_view_clicked()
        assert widget.emit_event.call_args[0][0] == UIEvents.ZONE_TOGGLE_VIEW

        # Apply template
        widget._on_apply_template_clicked()
        assert widget.emit_event.call_args[0][0] == UIEvents.ZONE_TEMPLATE_APPLY

        # Save template
        widget._on_save_template_clicked()
        assert widget.emit_event.call_args[0][0] == UIEvents.ZONE_TEMPLATE_SAVE

        # Import template
        widget._on_import_template_clicked()
        assert widget.emit_event.call_args[0][0] == UIEvents.ZONE_TEMPLATE_IMPORT

        # Clear applied template
        widget._on_clear_applied_template_clicked()
        assert widget.emit_event.call_args[0][0] == UIEvents.ZONE_TEMPLATE_CLEAR_APPLIED


class TestZoneControlsExtended2:
    def test_hierarchy_labels(self):
        labels = _hierarchy_labels()
        assert "group" in labels
        assert "day" in labels
        assert "subject" in labels
        assert labels["group"] == "Group" or "Grupo" in labels["group"]
        assert labels["day"] == "Day" or "Dia" in labels["day"]
        assert labels["subject"] == "Subject" or "Sujeito" in labels["subject"]


class TestZoneControlsExtended3:
    def test_hierarchy_labels(self):
        labels = _hierarchy_labels()
        assert "group" in labels
        assert "day" in labels
        assert "subject" in labels
