"""Tests for AquariumDetectionProgressDialog (live arena auto-detection progress).

``close_dialog`` is exercised through the UI coordinator's tests
(``tests/ui/test_ui_coordinator_helpers.py``), which are what call it. ``show_completion``
was removed as dead (A2-D-319).
"""

from __future__ import annotations

import tkinter as tk
import types
from tkinter import ttk
from typing import Any

import numpy as np
import pytest
import structlog
from PIL import ImageTk

from zebtrack.ui.dialogs import aquarium_detection_progress_dialog as dialog_module
from zebtrack.ui.dialogs.aquarium_detection_progress_dialog import (
    AquariumDetectionProgressDialog,
    thumbnail_geometry,
)


class TestThumbnailGeometry:
    def test_a_large_frame_is_fitted_inside_400_by_300_keeping_its_aspect(self):
        # 1920x1080: width is the binding side (400/1920 < 300/1080).
        assert thumbnail_geometry(1920, 1080, None) == (400, 225, None)

    def test_a_tall_frame_is_bound_by_its_height(self):
        # 600x1200: height binds (300/1200 = 0.25 < 400/600).
        assert thumbnail_geometry(600, 1200, None) == (150, 300, None)

    def test_the_bbox_is_scaled_with_the_frame(self):
        # 800x600 -> scale 0.5
        assert thumbnail_geometry(800, 600, (100, 120, 300, 340)) == (
            400,
            300,
            (50, 60, 150, 170),
        )

    def test_scaled_coordinates_are_truncated_to_integers(self):
        # scale = 400/1000 = 0.4 ; 105 * 0.4 = 42.0 ; 107 * 0.4 = 42.8 -> 42
        assert thumbnail_geometry(1000, 750, (105, 107, 205, 207))[2] == (42, 42, 82, 82)

    def test_a_small_frame_is_scaled_up_to_the_binding_side(self):
        assert thumbnail_geometry(100, 50, None) == (400, 200, None)

    def test_an_empty_frame_is_rejected(self):
        with pytest.raises(ZeroDivisionError):
            thumbnail_geometry(0, 480, None)


def _walk(widget: tk.Misc) -> list[tk.Misc]:
    found: list[tk.Misc] = []
    for child in widget.winfo_children():
        found.append(child)
        found.extend(_walk(child))
    return found


def _label_texts(dialog: tk.Misc) -> list[str]:
    return [str(w.cget("text")) for w in _walk(dialog) if isinstance(w, ttk.Label)]


def _build(root: tk.Misc, **kwargs: Any) -> AquariumDetectionProgressDialog:
    return AquariumDetectionProgressDialog(
        parent=root, experiment_id=kwargs.pop("experiment_id", "CECT_4"), **kwargs
    )


@pytest.fixture
def captured_images(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    """Record the PIL image handed to Tk, while still building a real PhotoImage."""
    images: list[Any] = []

    def photo_image(image: Any) -> Any:
        images.append(image)
        return ImageTk.PhotoImage(image=image)

    monkeypatch.setattr(dialog_module, "ImageTk", types.SimpleNamespace(PhotoImage=photo_image))
    return images


GREEN_RGB = (0, 255, 0)  # BGR (0, 255, 0): valid detections
ORANGE_RGB = (255, 165, 0)  # BGR (0, 165, 255): ignored detections
BLACK = (0, 0, 0)


@pytest.mark.gui
class TestInitialState:
    def test_the_dialog_names_the_session_and_starts_empty(self, tkinter_root):
        dialog = _build(tkinter_root, experiment_id="CECT_4")

        texts = _label_texts(dialog)
        assert "Session: CECT_4\nAnalyzing frames to identify the aquarium region..." in texts
        assert dialog.frame_label.cget("text") == "Frame: 0 / 100"
        assert dialog.valid_label.cget("text") == "✓ Valid: 0"
        assert dialog.invalid_label.cget("text") == "✗ Invalid: 0"
        assert dialog.thumbnail_label.cget("text") == "Waiting for frames..."
        assert dialog.status_label.cget("text") == "Starting detection..."
        assert dialog.title() == "Detecting Aquarium"

    def test_the_bar_follows_max_frames(self, tkinter_root):
        dialog = _build(tkinter_root, max_frames=10)

        assert dialog.frame_label.cget("text") == "Frame: 0 / 10"
        assert float(dialog.progress_bar.cget("maximum")) == 10.0

    def test_the_user_cannot_close_the_dialog_while_detection_runs(self, tkinter_root):
        dialog = _build(tkinter_root)

        dialog.tk.call(dialog.protocol("WM_DELETE_WINDOW"))

        assert dialog.winfo_exists()

    def test_the_dialog_is_modal(self, tkinter_root):
        dialog = _build(tkinter_root)

        assert dialog.grab_current() == dialog


@pytest.mark.gui
class TestUpdateProgress:
    def test_frame_counter_and_bar_follow_the_frame_number(self, tkinter_root):
        dialog = _build(tkinter_root)

        dialog.update_progress(frame_number=7)

        assert dialog.current_frame == 7
        assert dialog.frame_label.cget("text") == "Frame: 7 / 100"
        assert float(dialog.progress_bar.cget("value")) == 7.0

    def test_valid_and_invalid_detections_are_counted_separately(self, tkinter_root):
        dialog = _build(tkinter_root)

        dialog.update_progress(1, detected_bbox=(1, 1, 5, 5), is_valid=True)
        dialog.update_progress(2, detected_bbox=(1, 1, 5, 5), is_valid=True)
        dialog.update_progress(3, detected_bbox=(1, 1, 5, 5), is_valid=False)

        assert (dialog.valid_detections, dialog.invalid_detections) == (2, 1)
        assert dialog.valid_label.cget("text") == "✓ Valid: 2"
        assert dialog.invalid_label.cget("text") == "✗ Invalid: 1"

    def test_a_frame_without_a_bbox_counts_nothing_and_keeps_the_status(self, tkinter_root):
        dialog = _build(tkinter_root)
        dialog.update_progress(1, detected_bbox=(1, 1, 5, 5), is_valid=True)

        dialog.update_progress(2, detected_bbox=None, is_valid=True)

        assert (dialog.valid_detections, dialog.invalid_detections) == (1, 0)
        assert dialog.status_label.cget("text") == "✓ Aquarium detected (valid area)"

    def test_a_valid_detection_says_so_in_green(self, tkinter_root):
        dialog = _build(tkinter_root)

        dialog.update_progress(1, detected_bbox=(1, 1, 5, 5), is_valid=True)

        assert dialog.status_label.cget("text") == "✓ Aquarium detected (valid area)"
        assert str(dialog.status_label.cget("foreground")) == "green"

    def test_an_ignored_detection_explains_why_in_orange(self, tkinter_root):
        dialog = _build(tkinter_root)

        dialog.update_progress(1, detected_bbox=(1, 1, 5, 5), is_valid=False)

        assert dialog.status_label.cget("text") == "✗ Detection ignored (insufficient area)"
        assert str(dialog.status_label.cget("foreground")) == "orange"

    def test_an_explicit_status_message_wins_over_the_detection_summary(self, tkinter_root):
        dialog = _build(tkinter_root)

        dialog.update_progress(
            1, detected_bbox=(1, 1, 5, 5), is_valid=True, status_message="Consensus reached"
        )

        assert dialog.status_label.cget("text") == "Consensus reached"
        assert dialog.valid_detections == 1


@pytest.mark.gui
class TestThumbnail:
    @staticmethod
    def _frame() -> np.ndarray:
        return np.zeros((600, 800, 3), dtype=np.uint8)

    def test_the_thumbnail_is_shown_at_the_fitted_size(self, tkinter_root, captured_images):
        dialog = _build(tkinter_root)

        dialog.update_progress(1, frame_image=self._frame())

        assert captured_images[0].size == (400, 300)
        assert str(dialog.thumbnail_label.cget("text")) == ""
        assert dialog._thumbnail_photo is not None
        assert dialog._thumbnail_photo.width() == 400

    def test_a_valid_bbox_is_outlined_in_green_at_thumbnail_scale(
        self, tkinter_root, captured_images
    ):
        dialog = _build(tkinter_root)

        # (100,100)-(300,300) on an 800x600 frame -> (50,50)-(150,150) at 0.5.
        dialog.update_progress(
            1, frame_image=self._frame(), detected_bbox=(100, 100, 300, 300), is_valid=True
        )

        image = captured_images[0]
        assert image.getpixel((50, 100)) == GREEN_RGB  # left edge
        assert image.getpixel((150, 100)) == GREEN_RGB  # right edge
        assert image.getpixel((100, 100)) == BLACK  # inside: untouched

    def test_an_ignored_bbox_is_outlined_in_orange(self, tkinter_root, captured_images):
        dialog = _build(tkinter_root)

        dialog.update_progress(
            1, frame_image=self._frame(), detected_bbox=(100, 100, 300, 300), is_valid=False
        )

        assert captured_images[0].getpixel((50, 100)) == ORANGE_RGB

    def test_without_a_bbox_nothing_is_drawn(self, tkinter_root, captured_images):
        dialog = _build(tkinter_root)

        dialog.update_progress(1, frame_image=self._frame(), detected_bbox=None)

        assert captured_images[0].getpixel((50, 100)) == BLACK
        assert captured_images[0].getpixel((200, 150)) == BLACK

    def test_an_unreadable_frame_is_logged_and_the_counters_still_update(self, tkinter_root):
        dialog = _build(tkinter_root)
        empty = np.zeros((0, 0, 3), dtype=np.uint8)

        with structlog.testing.capture_logs() as logs:
            dialog.update_progress(4, frame_image=empty, detected_bbox=(1, 1, 5, 5), is_valid=True)

        assert [e["event"] for e in logs] == ["aquarium_detection_dialog.thumbnail_update_failed"]
        assert dialog.thumbnail_label.cget("text") == "Waiting for frames..."
        assert dialog.frame_label.cget("text") == "Frame: 4 / 100"
        assert dialog.valid_label.cget("text") == "✓ Valid: 1"
