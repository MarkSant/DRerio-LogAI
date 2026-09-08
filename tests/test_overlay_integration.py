#!/usr/bin/env python3
"""Tests for the detection-overlay drawing contract.

What changed here, and why
--------------------------
This file used to gate its only substantial test on::

    importlib.util.find_spec("zebtrack.plugins.yolov8_zebrafish_detector")

That module does not exist. ``src/zebtrack/plugins/`` holds ``base.py``,
``openvino_detector.py`` and ``ultralytics_detector.py``, and ``DETECTOR_PLUGINS``
registers only the Ultralytics and OpenVINO plugins; the only references to the
``yolov8_zebrafish_detector`` name anywhere in the tree were the three inside
this file. The condition could therefore never be false, so the test had not run
since the plugin was removed -- it reported as *skipped*, which reads exactly
like *fine*.

Two further premises had gone stale with it:

* **Overlays are not drawn by a plugin.** ``UltralyticsDetectorPlugin`` has no
  ``draw_overlay`` at all. The single implementation lives on
  :class:`~zebtrack.core.detection.single_detector.Detector`, which is what both
  production call sites use (``core/video/processing_worker.py`` for
  pre-recorded, ``core/recording/frame_processing_pipeline.py`` for live).
* **It returns ``None``.** The dead test asserted a returned ``ndarray``;
  ``Detector.draw_overlay`` mutates the frame in place. Had it ever run, it
  would have failed on a contract that is not broken.

The tests below drive that real implementation. They also pin the invariant the
two call sites depend on: both deliberately pass an EMPTY detection list, so the
overlay contributes zones only and the bounding boxes are rendered once, later,
by the frame consumer (integrated canvas or ``LivePreviewWindow``). Passing the
detections here instead burns a second box onto every animal -- the duplicated
bbox regression the call-site comments describe.
"""

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from zebtrack.core.detection import Detector, ZoneData
from zebtrack.plugins.base import DetectorPlugin

#: Module path used when patching ``cv2``: ``draw_overlay`` calls it through the
#: ``single_detector`` module namespace, so that is where it must be patched.
CV2 = "zebtrack.core.detection.single_detector.cv2"

ARENA_POLYGON = [[100, 100], [500, 100], [500, 400], [100, 400]]
ROI_POLYGONS = [
    [[150, 150], [200, 150], [200, 200], [150, 200]],
    [[300, 150], [350, 150], [350, 200], [300, 200]],
]


def _build_detector() -> Detector:
    """A real ``Detector`` with zones configured at native scale.

    The plugin is a spec'd stand-in on purpose: ``draw_overlay`` never touches
    it, and using the real one would drag in torch and a model file to exercise
    drawing code that needs neither. ``base_*`` matches ``actual_*`` so the zone
    scaler is an identity map and the asserted coordinates are the ones written
    above.
    """
    detector = Detector(
        plugin=MagicMock(spec=DetectorPlugin),
        base_width=640,
        base_height=480,
    )
    detector.set_zones(
        ZoneData(
            polygon=ARENA_POLYGON,
            roi_polygons=ROI_POLYGONS,
            roi_names=["ROI A", "ROI B"],
            roi_colors=[(255, 0, 0), (0, 255, 0)],
        ),
        actual_width=640,
        actual_height=480,
    )
    return detector


@pytest.mark.integration
class TestOverlayIntegration:
    """The overlay contract shared by the pre-recorded and live pipelines."""

    def test_draw_overlay_draws_one_box_per_detection(self):
        """Every detection becomes exactly one rectangle, at its own corners."""
        detector = _build_detector()
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        detections = [
            (110, 120, 160, 170, 0.9, 1),
            (300, 310, 340, 350, 0.75, 2),
        ]

        with patch(f"{CV2}.rectangle") as mock_rectangle:
            detector.draw_overlay(frame, detections)

        assert mock_rectangle.call_count == len(detections)
        drawn_corners = [(c.args[1], c.args[2]) for c in mock_rectangle.call_args_list]
        assert drawn_corners == [((110, 120), (160, 170)), ((300, 310), (340, 350))]

    def test_draw_overlay_labels_each_box_with_track_id_and_confidence(self):
        """The label carries the track ID and the confidence as a percentage."""
        detector = _build_detector()
        frame = np.zeros((480, 640, 3), dtype=np.uint8)

        with patch(f"{CV2}.putText") as mock_put_text:
            detector.draw_overlay(frame, [(110, 120, 160, 170, 0.9, 42)])

        assert mock_put_text.call_count == 1
        label = mock_put_text.call_args.args[1]
        assert "42" in label, f"track ID missing from label: {label!r}"
        assert "90" in label, f"confidence percentage missing from label: {label!r}"

    def test_draw_overlay_with_empty_detections_draws_zones_but_no_boxes(self):
        """The call both pipelines actually make: zones only, never a bbox.

        ``processing_worker`` and ``frame_processing_pipeline`` each invoke
        ``draw_overlay(frame, [])`` and leave the boxes to the frame consumer,
        so that a Track-ID filter can suppress them. If this call started
        drawing boxes, every animal would show two overlapping ones.
        """
        detector = _build_detector()
        frame = np.zeros((480, 640, 3), dtype=np.uint8)

        with patch(f"{CV2}.rectangle") as mock_rectangle, patch(f"{CV2}.polylines") as mock_lines:
            detector.draw_overlay(frame, [])

        mock_rectangle.assert_not_called()
        # One polyline per ROI, plus the arena outline.
        assert mock_lines.call_count == len(ROI_POLYGONS) + 1

    def test_draw_overlay_annotates_the_caller_s_own_frame_buffer(self):
        """In-place is the contract; the caller keeps using its own buffer.

        Both call sites discard the return value and pass ``frame`` straight on
        to the preview, so a version that painted onto a copy would leave every
        caller displaying an unannotated frame. Asserting on a returned array --
        as the dead test in this file did -- cannot see that: the return is
        ``None`` either way. Only the caller's buffer can.
        """
        detector = _build_detector()
        frame = np.zeros((480, 640, 3), dtype=np.uint8)

        detector.draw_overlay(frame, [(110, 120, 160, 170, 0.9, 7)])

        assert frame.any(), "draw_overlay left the caller's frame untouched"
        # The bbox colour is magenta; finding it proves the box landed on THIS
        # buffer rather than on a copy that was drawn and dropped.
        assert tuple(frame[120, 110]) == (255, 0, 255)
