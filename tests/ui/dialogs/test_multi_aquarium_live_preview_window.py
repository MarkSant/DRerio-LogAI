"""Tests for MultiAquariumLivePreviewWindow (live preview for 2+ aquariums).

The clock is injected (the module's ``time`` is replaced by a fake whose ``time()``
a test advances by hand) and ``after`` is replaced by a recorder, so nothing here
depends on wall-clock time. ``update_aquarium_frame`` is exercised through ``update_frame``
(F2-UI-002), the entry point the live pipeline calls.
"""

from __future__ import annotations

import inspect
import time as real_time
import tkinter as tk
import types
from tkinter import ttk
from typing import Any, cast

import numpy as np
import pytest
import structlog

from zebtrack.ui.dialogs import multi_aquarium_live_preview_window as window_module
from zebtrack.ui.dialogs.multi_aquarium_live_preview_window import (
    MultiAquariumLivePreviewWindow,
    build_panel_views,
    crop_to_region,
    detection_belongs_to_region,
    format_mmss,
    grid_layout,
    progress_percent,
)

# 2026-11-15 13:45:09 local time, built from fields so the expected clock text is
# an input, not something recomputed with the code under test.
T0 = real_time.mktime((2026, 11, 15, 13, 45, 9, 0, 0, -1))


class _FakeClock:
    def __init__(self, now: float) -> None:
        self.now = now

    def time(self) -> float:
        return self.now


class _AfterRecorder:
    def __init__(self) -> None:
        self.calls: list[tuple[int, Any]] = []

    def __call__(self, delay: int, func: Any = None, *args: Any) -> str:
        self.calls.append((delay, func))
        return f"after#{len(self.calls)}"


def _walk(widget: tk.Misc) -> list[tk.Misc]:
    found: list[tk.Misc] = []
    for child in widget.winfo_children():
        found.append(child)
        found.extend(_walk(child))
    return found


def _texts(preview: MultiAquariumLivePreviewWindow, kind: type) -> list[str]:
    return [str(w.cget("text")) for w in _walk(preview.window) if isinstance(w, kind)]


class TestGridLayout:
    @pytest.mark.parametrize(
        ("count", "expected"),
        [
            (1, (2, 1, 840, 500)),
            (2, (2, 1, 840, 500)),
            (3, (2, 2, 840, 850)),
            (4, (2, 2, 840, 850)),
            (5, (3, 2, 1240, 850)),
            (6, (3, 2, 1240, 850)),
            (7, (3, 3, 1240, 1200)),
        ],
    )
    def test_columns_rows_and_window_size(self, count, expected):
        # 2 columns up to 4 aquariums, 3 beyond; 400 px per column + 40 padding;
        # 350 px per row + 150 for the controls.
        assert grid_layout(count) == expected


class TestProgressPercent:
    @pytest.mark.parametrize(
        ("elapsed", "duration", "expected"),
        [(30, 120, 25.0), (0, 120, 0.0), (120, 120, 100.0), (150, 120, 100.0), (-5, 120, 0.0)],
    )
    def test_is_clamped_to_zero_and_one_hundred(self, elapsed, duration, expected):
        assert progress_percent(elapsed, duration) == expected


class TestFormatMmss:
    @pytest.mark.parametrize(
        ("seconds", "expected"),
        [(0, "00:00"), (65.9, "01:05"), (299, "04:59"), (3599, "59:59"), (3725, "62:05")],
    )
    def test_minutes_are_not_wrapped_into_hours(self, seconds, expected):
        assert format_mmss(seconds) == expected


class TestFormatEta:
    @pytest.mark.parametrize(
        ("seconds", "expected"),
        [
            (0, "0s"),
            (59, "59s"),
            (59.9, "59s"),
            (60, "1m 00s"),
            (125, "2m 05s"),
            (3599, "59m 59s"),
            (3600, "1h 00m 00s"),
            (3725, "1h 02m 05s"),
            (-5, "0s"),
        ],
    )
    def test_renders_seconds_minutes_and_hours(self, seconds, expected):
        assert MultiAquariumLivePreviewWindow._format_eta(seconds) == expected


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> _FakeClock:
    fake = _FakeClock(T0)
    monkeypatch.setattr(
        window_module,
        "time",
        types.SimpleNamespace(
            time=fake.time, strftime=real_time.strftime, localtime=real_time.localtime
        ),
    )
    return fake


def _build(
    root: tk.Misc,
    *,
    num_aquariums: int = 2,
    duration_s: float = 300.0,
    on_stop: Any = None,
    camera_index: int = 3,
) -> tuple[Any, _AfterRecorder]:
    preview = MultiAquariumLivePreviewWindow(
        parent=root,
        camera_index=camera_index,
        num_aquariums=num_aquariums,
        duration_s=duration_s,
        on_stop_callback=on_stop,
    )
    recorder = _AfterRecorder()
    preview.window.after = recorder  # type: ignore[method-assign, assignment]
    return preview, recorder


@pytest.mark.gui
class TestLayoutOnScreen:
    def test_two_aquariums_get_two_labelled_panels_and_one_canvas_each(self, tkinter_root, clock):
        preview, _after = _build(tkinter_root, num_aquariums=2, camera_index=3)

        assert preview.window.title() == "Multi-Aquarium Live Analysis - Camera 3"
        assert sorted(preview.aquarium_canvases) == [0, 1]
        assert [t for t in _texts(preview, ttk.LabelFrame) if t.startswith("Aquarium")] == [
            "Aquarium 1",
            "Aquarium 2",
        ]
        assert sorted(preview.aquarium_labels) == [0, 1]
        assert all(
            str(label.cget("text")) == "Detections: 0" for label in preview.aquarium_labels.values()
        )
        assert "Camera: 3 | Aquariums: 2" in _texts(preview, ttk.Label)

    def test_five_aquariums_use_three_columns(self, tkinter_root, clock):
        preview, _after = _build(tkinter_root, num_aquariums=5)

        cells = [cast(Any, c.master).grid_info() for c in preview.aquarium_canvases.values()]
        columns = {int(cell["column"]) for cell in cells}
        rows = {int(cell["row"]) for cell in cells}
        assert columns == {0, 1, 2}
        assert rows == {0, 1}

    def test_a_timed_session_shows_a_determinate_bar(self, tkinter_root, clock):
        preview, _after = _build(tkinter_root, duration_s=300)

        assert str(preview.progress_bar.cget("mode")) == "determinate"

    def test_an_open_ended_session_shows_an_indeterminate_bar(self, tkinter_root, clock):
        preview, _after = _build(tkinter_root, duration_s=0)

        assert str(preview.progress_bar.cget("mode")) == "indeterminate"

    def test_initial_footer_has_placeholder_clocks_and_is_english(self, tkinter_root, clock):
        preview, _after = _build(tkinter_root)

        assert preview.status_label.cget("text") == "Status: Initializing..."
        assert preview.start_time_label.cget("text") == "Start: --:--:--"
        assert preview.stop_time_label.cget("text") == "End: --:--:--"
        assert preview.eta_label.cget("text") == "ETA: --"
        assert preview.recorded_frames_label.cget("text") == "Recorded frames: 0"


@pytest.mark.gui
class TestTimer:
    def test_start_timer_stamps_the_start_clock(self, tkinter_root, clock):
        preview, _after = _build(tkinter_root)

        preview.start_timer()

        assert preview.start_time == T0
        assert preview.start_time_label.cget("text") == "Start: 13:45:09"

    def test_a_tick_shows_elapsed_and_remaining_eta_and_percent(self, tkinter_root, clock):
        preview, after = _build(tkinter_root, duration_s=300)
        preview.start_timer()
        clock.now = T0 + 65  # 1m05s elapsed, 3m55s left

        preview._update_timer()

        assert preview.timer_label.cget("text") == "Time: 01:05 / 03:55"
        assert preview.eta_label.cget("text") == "ETA: 3m 55s"
        assert float(preview.progress_bar.cget("value")) == pytest.approx(65 / 300 * 100)
        assert after.calls == [(1000, preview._update_timer)]
        assert preview.is_stopped is False

    def test_before_the_timer_starts_a_tick_only_reschedules(self, tkinter_root, clock):
        preview, after = _build(tkinter_root)
        label_before = preview.timer_label.cget("text")

        preview._update_timer()

        assert preview.timer_label.cget("text") == label_before == "Time: waiting..."
        assert after.calls == [(1000, preview._update_timer)]

    def test_time_running_out_stops_the_session_through_the_callback(self, tkinter_root, clock):
        stops: list[str] = []
        preview, after = _build(tkinter_root, duration_s=300, on_stop=lambda: stops.append("stop"))
        preview.start_timer()
        clock.now = T0 + 300

        preview._update_timer()

        assert stops == ["stop"]
        assert preview.is_stopped is True
        assert after.calls == [], "no tick may be scheduled after the auto-stop"
        assert preview.status_label.cget("text") == "Status: Stopping..."
        assert str(preview.stop_button.cget("state")) == "disabled"
        assert preview.stop_time_label.cget("text") == "End: 13:50:09"
        assert preview.eta_label.cget("text") == "ETA: --"

    def test_one_second_before_the_end_does_not_stop(self, tkinter_root, clock):
        stops: list[str] = []
        preview, after = _build(tkinter_root, duration_s=300, on_stop=lambda: stops.append("stop"))
        preview.start_timer()
        clock.now = T0 + 299

        preview._update_timer()

        assert stops == []
        assert preview.timer_label.cget("text") == "Time: 04:59 / 00:01"
        assert len(after.calls) == 1

    def test_without_a_stop_callback_time_running_out_does_not_stop(self, tkinter_root, clock):
        preview, after = _build(tkinter_root, duration_s=300, on_stop=None)
        preview.start_timer()
        clock.now = T0 + 400

        preview._update_timer()

        assert preview.is_stopped is False
        assert preview.timer_label.cget("text") == "Time: 06:40 / 00:00"
        assert len(after.calls) == 1

    def test_an_open_ended_session_never_auto_stops_and_shows_no_eta(self, tkinter_root, clock):
        stops: list[str] = []
        preview, after = _build(tkinter_root, duration_s=0, on_stop=lambda: stops.append("stop"))
        preview.start_timer()
        clock.now = T0 + 5000

        preview._update_timer()

        assert stops == []
        assert preview.eta_label.cget("text") == "ETA: --"
        assert len(after.calls) == 1

    def test_a_tick_after_stopping_does_nothing(self, tkinter_root, clock):
        preview, after = _build(tkinter_root, duration_s=300)
        preview.start_timer()
        preview.is_stopped = True
        clock.now = T0 + 10

        preview._update_timer()

        assert preview.timer_label.cget("text") == "Time: waiting..."
        assert after.calls == []


@pytest.mark.gui
class TestStopping:
    def test_the_stop_button_calls_back_once(self, tkinter_root, clock):
        stops: list[str] = []
        preview, _after = _build(tkinter_root, on_stop=lambda: stops.append("stop"))

        preview.stop_button.invoke()

        assert stops == ["stop"]
        assert str(preview.stop_button.cget("state")) == "disabled"

    def test_a_second_stop_is_ignored(self, tkinter_root, clock):
        stops: list[str] = []
        preview, _after = _build(tkinter_root, on_stop=lambda: stops.append("stop"))

        preview._on_stop_clicked()
        preview._on_stop_clicked()

        assert stops == ["stop"]

    def test_stopping_without_a_callback_still_freezes_the_window(self, tkinter_root, clock):
        preview, _after = _build(tkinter_root, on_stop=None)

        preview._on_stop_clicked()

        assert preview.is_stopped is True
        assert preview.status_label.cget("text") == "Status: Stopping..."

    def test_an_indeterminate_bar_is_halted_at_stop(self, tkinter_root, clock):
        preview, _after = _build(tkinter_root, duration_s=0)
        calls: list[str] = []
        preview.progress_bar.stop = lambda: calls.append("stop")  # type: ignore[method-assign]

        preview._on_stop_clicked()

        assert calls == ["stop"]

    def test_closing_a_running_window_is_a_stop_not_a_destroy(self, tkinter_root, clock):
        stops: list[str] = []
        preview, _after = _build(tkinter_root, on_stop=lambda: stops.append("stop"))

        preview.window.tk.call(preview.window.protocol("WM_DELETE_WINDOW"))

        assert stops == ["stop"]
        assert preview.window.winfo_exists()

    def test_closing_an_already_stopped_window_destroys_it(self, tkinter_root, clock):
        preview, _after = _build(tkinter_root)
        preview._on_stop_clicked()

        preview.window.tk.call(preview.window.protocol("WM_DELETE_WINDOW"))

        assert not preview.window.winfo_exists()


@pytest.mark.gui
class TestStatusAndDestroy:
    def test_status_text_carries_the_colour(self, tkinter_root, clock):
        preview, _after = _build(tkinter_root)

        preview.update_status_text("● Recording", color="red")

        assert preview.status_label.cget("text") == "Status: ● Recording"
        assert str(preview.status_label.cget("foreground")) == "red"

    def test_destroy_closes_the_window(self, tkinter_root, clock):
        preview, _after = _build(tkinter_root)

        preview.destroy()

        assert not preview.window.winfo_exists()

    def test_destroying_twice_logs_and_does_not_raise(self, tkinter_root, clock):
        preview, _after = _build(tkinter_root)
        preview.destroy()
        preview.window.destroy = lambda: (_ for _ in ()).throw(  # type: ignore[method-assign]
            tk.TclError("bad window path name")
        )

        with structlog.testing.capture_logs() as logs:
            preview.destroy()

        assert [e["event"] for e in logs] == ["multi_aquarium_preview.destroy_failed"]


def _split_frame() -> np.ndarray:
    """100x200 BGR frame: left half pure blue, right half pure red."""
    frame = np.zeros((100, 200, 3), dtype=np.uint8)
    frame[:, :100] = (255, 0, 0)
    frame[:, 100:] = (0, 0, 255)
    return frame


TWO_PANELS = {0: (0, 0, 100, 100), 1: (100, 0, 200, 100)}


class TestBuildPanelViews:
    """F2-UI-002: what each aquarium panel shows for the whole camera frame."""

    def test_each_panel_gets_its_own_region_of_the_frame(self):
        views = build_panel_views(_split_frame(), [], TWO_PANELS, [0, 1])

        left, right = views[0][0], views[1][0]
        assert left.shape == (100, 100, 3)
        assert right.shape == (100, 100, 3)
        assert (left == (255, 0, 0)).all()
        assert (right == (0, 0, 255)).all()

    def test_detections_go_to_the_panel_holding_their_centre_in_crop_coordinates(self):
        frame = _split_frame()

        # centre (20, 20) -> aquarium 0; centre (140, 40) -> aquarium 1.
        views = build_panel_views(
            frame, [(10, 10, 30, 30, 0.9), (120, 20, 160, 60, 0.8)], TWO_PANELS, [0, 1]
        )

        (left, left_count), (right, right_count) = views[0], views[1]
        assert (left_count, right_count) == (1, 1)
        # box corner (10, 10) is (10, 10) in the left crop; the right box starts at frame
        # x=120, which is x=20 in the right crop.
        assert tuple(left[10, 10]) == (0, 255, 0)
        assert tuple(right[20, 20]) == (0, 255, 0)
        assert tuple(right[10, 10]) == (0, 0, 255)  # nothing is drawn where no box is
        # The frame is shared with the recorder: it must not be painted on.
        assert tuple(frame[10, 10]) == (255, 0, 0)
        assert tuple(frame[20, 120]) == (0, 0, 255)

    def test_a_detection_centred_on_the_seam_belongs_to_the_right_hand_panel(self):
        views = build_panel_views(_split_frame(), [(90, 10, 110, 30, 0.5)], TWO_PANELS, [0, 1])

        assert (views[0][1], views[1][1]) == (0, 1)

    def test_a_detection_is_placed_by_its_centre_not_its_corner(self):
        # x1 = 40 is inside aquarium 0 but the centre x = 130 is inside aquarium 1.
        views = build_panel_views(_split_frame(), [(40, 10, 220, 30, 0.5)], TWO_PANELS, [0, 1])

        assert (views[0][1], views[1][1]) == (0, 1)

    def test_an_aquarium_without_a_region_shows_the_whole_frame_and_every_detection(self):
        frame = _split_frame()

        views = build_panel_views(
            frame, [(10, 10, 30, 30, 0.9), (120, 20, 160, 60, 0.8)], {}, [0, 1]
        )

        for aquarium_id in (0, 1):
            shown, count = views[aquarium_id]
            assert shown.shape == (100, 200, 3)
            assert count == 2
            assert tuple(shown[10, 10]) == (0, 255, 0)
            assert tuple(shown[20, 120]) == (0, 255, 0)
        assert tuple(frame[10, 10]) == (255, 0, 0)  # the shared frame stays untouched

    def test_a_region_outside_the_frame_is_left_out_and_the_others_still_draw(self):
        regions = {0: (300, 0, 400, 100), 1: (0, 0, 100, 100)}

        views = build_panel_views(_split_frame(), [], regions, [0, 1])

        assert sorted(views) == [1]

    def test_a_region_hanging_over_the_edge_is_clipped_to_the_frame(self):
        views = build_panel_views(_split_frame(), [], {0: (150, -20, 260, 70)}, [0])

        assert views[0][0].shape == (70, 50, 3)  # rows 0..70, columns 150..200

    def test_only_the_requested_aquariums_are_produced(self):
        assert build_panel_views(_split_frame(), [], TWO_PANELS, [1]).keys() == {1}


class _PanelRecorder:
    """Stands in for the panel and footer writers: keeps what ``update_frame`` asked for."""

    def __init__(self) -> None:
        self.panels: dict[int, tuple[np.ndarray, int]] = {}
        self.counts: list[int] = []

    def panel(self, aquarium_id: int, frame: np.ndarray, num_detections: int = 0) -> None:
        self.panels[aquarium_id] = (frame, num_detections)

    def count(self, recorded_count: int) -> None:
        self.counts.append(recorded_count)


def _host(recorder: _PanelRecorder, *, stopped: bool = False) -> Any:
    """The attributes ``update_frame`` reads, without building a Tk window."""
    return types.SimpleNamespace(
        is_stopped=stopped,
        aquarium_canvases={0: object(), 1: object()},
        aquarium_regions=TWO_PANELS,
        update_aquarium_frame=recorder.panel,
        update_recorded_count=recorder.count,
    )


class TestUpdateFrame:
    """F2-UI-002: ``update_frame(frame, detections, recorded_count)`` is what the live
    pipeline calls on whichever window the camera handler built."""

    def test_the_signature_matches_the_single_aquarium_window_the_pipeline_was_written_for(self):
        from zebtrack.ui.dialogs.live_preview_window import LivePreviewWindow

        ours = list(inspect.signature(MultiAquariumLivePreviewWindow.update_frame).parameters)
        theirs = list(inspect.signature(LivePreviewWindow.update_frame).parameters)

        assert ours == theirs == ["self", "frame", "detections", "recorded_count"]

    def test_every_panel_is_refreshed_with_its_view_and_count(self):
        recorder = _PanelRecorder()

        MultiAquariumLivePreviewWindow.update_frame(
            _host(recorder), _split_frame(), [(120, 20, 160, 60, 0.8)], 7
        )

        assert sorted(recorder.panels) == [0, 1]
        assert recorder.panels[0][0].shape == (100, 100, 3)
        assert [recorder.panels[0][1], recorder.panels[1][1]] == [0, 1]
        assert recorder.counts == [7]

    def test_the_recorded_count_is_optional_and_detections_may_be_none(self):
        recorder = _PanelRecorder()

        MultiAquariumLivePreviewWindow.update_frame(_host(recorder), _split_frame(), None)

        assert recorder.counts == []
        assert [recorder.panels[0][1], recorder.panels[1][1]] == [0, 0]

    def test_a_zero_recorded_count_is_still_shown(self):
        recorder = _PanelRecorder()

        MultiAquariumLivePreviewWindow.update_frame(_host(recorder), _split_frame(), [], 0)

        assert recorder.counts == [0]

    def test_a_stopped_window_draws_and_counts_nothing(self):
        recorder = _PanelRecorder()

        MultiAquariumLivePreviewWindow.update_frame(
            _host(recorder, stopped=True), _split_frame(), [], 9
        )

        assert recorder.panels == {}
        assert recorder.counts == []


@pytest.mark.gui
class TestUpdateFrameOnScreen:
    def test_real_panels_receive_the_picture_the_count_and_the_footer(self, tkinter_root, clock):
        preview, _after = _build(tkinter_root, num_aquariums=2)
        preview.aquarium_regions = dict(TWO_PANELS)

        preview.update_frame(_split_frame(), [(120, 20, 160, 60, 0.8)], 3)

        assert sorted(preview.aquarium_photo_images) == [0, 1]
        assert str(preview.aquarium_labels[0].cget("text")) == "Detections: 0"
        assert str(preview.aquarium_labels[1].cget("text")) == "Detections: 1"
        assert "Recorded frames: 3" in _texts(preview, ttk.Label)

    def test_the_regions_can_be_given_when_the_window_is_built(self, tkinter_root, clock):
        preview = MultiAquariumLivePreviewWindow(
            parent=tkinter_root,
            camera_index=0,
            num_aquariums=2,
            duration_s=10.0,
            aquarium_regions=TWO_PANELS,
        )
        preview.window.after = _AfterRecorder()  # type: ignore[method-assign, assignment]

        assert preview.aquarium_regions == TWO_PANELS


class TestRegionHelpers:
    def test_crop_returns_the_clipped_view_and_its_origin(self):
        frame = np.arange(10 * 20 * 3, dtype=np.uint8).reshape(10, 20, 3)

        crop, x_off, y_off = crop_to_region(frame, (-5, 2, 8, 50))  # type: ignore[misc]

        assert (x_off, y_off) == (0, 2)
        assert crop.shape == (8, 8, 3)
        assert (crop == frame[2:10, 0:8]).all()

    @pytest.mark.parametrize("region", [(5, 5, 5, 9), (5, 5, 9, 5), (30, 0, 40, 5), (0, 20, 5, 30)])
    def test_an_empty_or_outside_region_has_no_crop(self, region):
        assert crop_to_region(np.zeros((10, 20, 3), dtype=np.uint8), region) is None

    @pytest.mark.parametrize(
        ("detection", "expected"),
        [
            ((0, 0, 20, 20), True),  # centre (10, 10)
            ((80, 80, 120, 120), False),  # centre (100, 100): the far edge is exclusive
            ((0, 0, 10, 10), True),  # centre (5, 5): the near edge is inclusive
            ((-20, 0, 0, 20), False),  # centre x = -10
            ((10, 80, 30, 120), False),  # centre y = 100
        ],
    )
    def test_membership_uses_the_centre_with_an_inclusive_near_edge(self, detection, expected):
        assert detection_belongs_to_region(detection, (5, 5, 100, 100)) is expected
