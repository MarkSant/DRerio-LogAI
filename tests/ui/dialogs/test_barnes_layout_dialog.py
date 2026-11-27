"""Barnes arena assistant dialog (ui/dialogs/barnes_layout_dialog.py, #633).

Driven on a synthetic table with known hole centres. Async work goes through a
synchronous runner, so every assertion sees the finished state; one test runs the
real worker thread.
"""

from __future__ import annotations

import math
import time
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import numpy as np
import pytest
from PIL import Image
from tests.helpers.barnes_synthetic import SyntheticTable

from zebtrack.analysis.protocols.barnes.contract import (
    BarnesLayout,
    BarnesParams,
    TrialType,
    expected_roi_names,
)
from zebtrack.core.detection import barnes_geometry as geometry
from zebtrack.ui.dialogs import barnes_layout_dialog as dialog_module
from zebtrack.ui.dialogs.barnes_layout_dialog import (
    AssistantMode,
    BarnesAssistantInputs,
    BarnesLayoutDialog,
    OtherVideo,
    OtherVideosChoice,
    OtherVideosDialog,
)
from zebtrack.ui.event_bus_v2 import BarnesLayoutApplyPayload, UIEvents

pytestmark = pytest.mark.gui

VIDEO = "C:/exp/Dia_1/rat_3/trial.mp4"


def _sync(work, done):
    done(work())


def _distance(a, b) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


@pytest.fixture
def boxes(monkeypatch):
    """Scripted message boxes: ``askyesno`` answers ``boxes.answer``."""
    calls: dict[str, list[Any]] = {"askyesno": [], "showinfo": [], "showerror": [], "warn": []}
    state = SimpleNamespace(answer=True, calls=calls)

    def askyesno(*args, **kwargs):
        calls["askyesno"].append(args)
        return state.answer

    fake = SimpleNamespace(
        askyesno=askyesno,
        showinfo=lambda *a, **k: calls["showinfo"].append(a),
        showerror=lambda *a, **k: calls["showerror"].append(a),
        showwarning=lambda *a, **k: calls["warn"].append(a),
    )
    monkeypatch.setattr(dialog_module, "messagebox", fake)
    return state


class AnsweringBus:
    """The bus as the coordinator answers it: ``on_result(answer)`` for every write."""

    def __init__(self, answer: bool = True) -> None:
        self.answer = answer
        self.events: list[tuple[Any, Any]] = []

    def publish(self, event, payload=None) -> None:
        self.events.append((event, payload))
        on_result = getattr(payload, "on_result", None)
        if callable(on_result):
            on_result(self.answer)


def _build(
    root,
    synth: SyntheticTable | None = None,
    *,
    bus: Any = None,
    table: bool = True,
    loader: Any = None,
    detect: Any = None,
    run_async: Any = _sync,
    **overrides: Any,
) -> BarnesLayoutDialog:
    synth = synth or SyntheticTable()
    image = synth.image()
    fields: dict[str, Any] = {
        "video_path": VIDEO,
        "frame": Image.fromarray(image).convert("RGB"),
        "params": BarnesParams(n_holes=20),
        "background_source": VIDEO,
        "initial_table": synth.table_ellipse() if table else None,
        "can_detect_table": detect is not None,
    }
    fields.update(overrides)
    event_bus: Any = bus if bus is not None else AnsweringBus()
    return BarnesLayoutDialog(
        root,
        event_bus,
        BarnesAssistantInputs(**fields),
        detect_table=detect,
        load_background=loader or (lambda _path: image),
        run_async=run_async,
    )


def _published(bus) -> list[BarnesLayoutApplyPayload]:
    if isinstance(bus, AnsweringBus):
        pairs = bus.events
    else:
        pairs = [(call.args[0], call.args[1]) for call in bus.publish.call_args_list]
    return [payload for event, payload in pairs if event is UIEvents.ZONE_BARNES_LAYOUT_APPLY]


def _layout_of(dialog: BarnesLayoutDialog) -> BarnesLayout:
    layout = dialog._layout
    assert layout is not None
    return layout


def _table_of(dialog: BarnesLayoutDialog):
    table = dialog._table
    assert table is not None
    return table


def _loaded(metadata) -> BarnesLayout:
    layout = BarnesLayout.from_metadata(metadata)
    assert layout is not None
    return layout


def _ev(x: float, y: float) -> Any:
    """A canvas mouse event (only ``x`` and ``y`` are read)."""
    return SimpleNamespace(x=x, y=y)


def _enabled(widget) -> bool:
    return not widget.instate(["disabled"])


class TestOpening:
    def test_without_a_table_it_asks_for_the_rim(self, tkinter_root):
        dialog = _build(tkinter_root, table=False)

        assert dialog.mode is AssistantMode.RIM
        assert dialog.title() == "Barnes assistant"
        assert "rim" in dialog.status_label.cget("text")
        assert not _enabled(dialog.apply_button)
        assert not _enabled(dialog.target_button)
        assert not _enabled(dialog.detect_button)
        assert not _enabled(dialog.fit_button)

    def test_with_a_table_it_asks_for_the_escape_hole(self, tkinter_root):
        dialog = _build(tkinter_root)

        assert dialog.mode is AssistantMode.TARGET
        assert dialog.status_label.cget("text") == "Click the centre of the escape hole."
        assert _enabled(dialog.target_button)

    def test_the_frame_is_shown_scaled_and_clicks_come_back_in_raw_pixels(self, tkinter_root):
        dialog = _build(tkinter_root)

        scale = min(900 / 640, 620 / 480)
        assert int(dialog.canvas.cget("width")) == round(640 * scale)
        assert dialog._canvas_to_video(100 * scale, 50 * scale) == pytest.approx((100.0, 50.0))

    def test_the_default_trial_type_is_the_projects(self, tkinter_root):
        dialog = _build(
            tkinter_root, params=BarnesParams(n_holes=20, default_trial_type=TrialType.PROBE)
        )
        assert dialog.trial_type_var.get() == "probe"

    def test_the_videos_trial_type_wins(self, tkinter_root):
        dialog = _build(tkinter_root, trial_type="probe")
        assert dialog.trial_type_var.get() == "probe"

    def test_a_cached_layout_opens_ready_to_adjust_and_is_kept(self, tkinter_root):
        synth = SyntheticTable()
        cached, _model = geometry.layout_from_click(
            synth.table_ellipse(), synth.hole_center(2), 20, synth.image()
        )
        moved = {
            **cached.to_metadata(),
        }
        moved["holes"][0]["center_px"] = [
            moved["holes"][0]["center_px"][0] + 3.0,
            moved["holes"][0]["center_px"][1],
        ]
        moved["holes"][0]["snapped"] = False
        moved["holes"][0]["residual_px"] = None
        hand_edited = BarnesLayout.from_metadata(moved)

        dialog = _build(tkinter_root, synth, table=False, cached_layout=hand_edited)

        assert dialog.mode is AssistantMode.ADJUST
        assert dialog._layout == hand_edited  # the background did not re-snap it
        assert _enabled(dialog.apply_button)

    def test_a_cached_layout_keeps_its_own_hole_count(self, tkinter_root):
        synth = SyntheticTable(n_holes=18)
        cached, _ = geometry.layout_from_click(synth.table_ellipse(), synth.hole_center(0), 18)
        dialog = _build(tkinter_root, synth, cached_layout=cached)
        assert dialog.mode is AssistantMode.ADJUST
        assert dialog._layout == cached
        assert dialog.n_holes_var.get() == "18"
        assert dialog.count_label.cget("text") == "project: 20"


class TestTable:
    def test_five_rim_clicks_fit_the_table(self, tkinter_root):
        synth = SyntheticTable()
        dialog = _build(tkinter_root, synth, table=False)
        rim = synth.rim_points(5)

        for point in rim[:4]:
            dialog.handle_click(*point)
        assert not _enabled(dialog.fit_button)
        dialog.handle_click(*rim[4])
        assert _enabled(dialog.fit_button)

        dialog.fit_rim()

        assert dialog.mode is AssistantMode.TARGET
        truth = synth.table_ellipse()
        assert _table_of(dialog).center_px == pytest.approx(truth.center_px, abs=1.0)
        assert dialog._rim_points == []

    def test_a_degenerate_rim_reports_instead_of_failing(self, tkinter_root):
        dialog = _build(tkinter_root, table=False)
        for x in range(5):
            dialog.handle_click(10.0 * x, 10.0)

        dialog.fit_rim()

        assert dialog.mode is AssistantMode.RIM
        assert dialog._table is None
        assert "Could not fit" in dialog.status_label.cget("text")

    def test_restarting_the_rim_forgets_the_points(self, tkinter_root):
        dialog = _build(tkinter_root, table=False)
        dialog.handle_click(1.0, 2.0)
        dialog.start_rim()
        assert dialog._rim_points == []
        assert dialog.mode is AssistantMode.RIM

    def _detect(self, dialog) -> None:
        dialog.detect_table()
        deadline = time.monotonic() + 5.0
        while dialog._busy and time.monotonic() < deadline:
            dialog.update()
            time.sleep(0.01)

    def test_auto_detection_sets_the_inscribed_ellipse(self, tkinter_root):
        calls = []

        def detect(video):
            calls.append(video)
            return [(120, 40), (520, 40), (520, 440), (120, 440)]

        dialog = _build(tkinter_root, table=False, detect=detect)
        assert _enabled(dialog.detect_button)

        self._detect(dialog)

        assert calls == [VIDEO]
        assert dialog.mode is AssistantMode.TARGET
        assert _table_of(dialog).center_px == pytest.approx((320.0, 240.0))
        assert "saved this outline as the video's arena" in dialog.status_label.cget("text")

    @pytest.mark.parametrize(
        ("result", "message"),
        [(None, "not detected"), ([(0, 0), (1, 1), (2, 2)], "not usable")],
        ids=["nothing", "degenerate"],
    )
    def test_auto_detection_failures_fall_back_to_the_rim(self, tkinter_root, result, message):
        dialog = _build(tkinter_root, table=False, detect=lambda _video: result)
        self._detect(dialog)
        assert dialog.mode is AssistantMode.RIM
        assert message in dialog.status_label.cget("text")

    def test_an_exploding_detector_leaves_the_dialog_usable(self, tkinter_root):
        def detect(_video):
            raise RuntimeError("model missing")

        dialog = _build(tkinter_root, table=False, detect=detect)
        self._detect(dialog)
        assert dialog.mode is AssistantMode.RIM
        assert dialog._busy is False


class TestEscapeHole:
    def test_the_click_places_and_snaps_every_hole(self, tkinter_root):
        synth = SyntheticTable()
        dialog = _build(tkinter_root, synth)

        click = synth.hole_center(3)
        scale = dialog._scale
        dialog._on_press(_ev(x=click[0] * scale, y=click[1] * scale))

        assert dialog.mode is AssistantMode.ADJUST
        layout = _layout_of(dialog)
        assert _distance(layout.target.center_px, synth.hole_center(3)) < 1.0
        assert all(hole.snapped for hole in layout.holes)
        assert dialog.quality_label.cget("text").startswith("20/20 holes snapped")
        assert dialog.warning_label.cget("text") == ""
        assert dialog.canvas.find_withtag("hole")

    def test_a_missing_hole_warns(self, tkinter_root):
        synth = SyntheticTable(missing=(4,))
        dialog = _build(tkinter_root, synth)
        dialog.handle_click(*synth.hole_center(0))
        assert dialog.quality_label.cget("text").startswith("19/20")
        assert "number of holes (20)" in dialog.warning_label.cget("text")

    def test_a_click_outside_the_table_is_explained(self, tkinter_root):
        dialog = _build(tkinter_root)
        dialog.handle_click(2.0, 2.0)
        assert dialog._layout is None
        assert dialog.mode is AssistantMode.TARGET
        assert "inside the table" in dialog.status_label.cget("text")

    def test_without_a_background_file_the_frame_is_used(self, tkinter_root):
        synth = SyntheticTable()
        dialog = _build(tkinter_root, synth, loader=lambda _p: None)
        dialog.handle_click(*synth.hole_center(0))
        assert all(hole.snapped for hole in _layout_of(dialog).holes)

    def test_no_background_source_snaps_on_the_frame(self, tkinter_root):
        synth = SyntheticTable()
        loader = MagicMock()
        dialog = _build(tkinter_root, synth, loader=loader, background_source=None)
        dialog.handle_click(*synth.hole_center(0))
        loader.assert_not_called()
        assert all(hole.snapped for hole in _layout_of(dialog).holes)

    def test_a_click_before_the_background_is_snapped_when_it_arrives(self, tkinter_root):
        synth = SyntheticTable()
        pending = []
        dialog = _build(tkinter_root, synth, run_async=lambda work, done: pending.append(done))
        assert dialog._busy is True
        dialog._busy = False  # the user clicks while the background still loads
        dialog._background = None
        dialog.handle_click(*synth.hole_center(0))
        assert not any(hole.snapped for hole in _layout_of(dialog).holes)

        pending[0](synth.image())

        assert all(hole.snapped for hole in _layout_of(dialog).holes)

    def test_the_real_worker_thread_delivers_the_background(self, tkinter_root):
        synth = SyntheticTable()
        dialog = _build(tkinter_root, synth, run_async=None)
        deadline = time.monotonic() + 5.0
        while dialog._busy and time.monotonic() < deadline:
            dialog.update()
            time.sleep(0.01)
        assert dialog._busy is False
        assert dialog._background is not None

    def test_a_failing_worker_still_releases_the_dialog(self, tkinter_root):
        def loader(_path):
            raise OSError("disk gone")

        dialog = _build(tkinter_root, loader=loader, run_async=None)
        deadline = time.monotonic() + 5.0
        while dialog._busy and time.monotonic() < deadline:
            dialog.update()
            time.sleep(0.01)
        assert dialog._busy is False
        assert dialog._background is not None  # fell back to the frame


class TestAdjust:
    def _placed(self, root, synth=None):
        synth = synth or SyntheticTable()
        dialog = _build(root, synth)
        dialog.handle_click(*synth.hole_center(0))
        return synth, dialog

    def test_rotating_moves_the_escape_hole_one_hole(self, tkinter_root):
        synth, dialog = self._placed(tkinter_root)
        dialog.rotate(1)
        assert _distance(_layout_of(dialog).target.center_px, synth.hole_center(1)) < 1.0
        dialog.rotate(-2)
        assert _distance(_layout_of(dialog).target.center_px, synth.hole_center(19)) < 1.0

    def test_dragging_a_hole_moves_it(self, tkinter_root):
        synth, dialog = self._placed(tkinter_root)
        start = synth.hole_center(5)

        assert dialog.begin_drag(start[0] + 2.0, start[1])
        dialog.drag_to(start[0] + 5.0, start[1] + 1.0)
        dialog.end_drag(start[0] + 6.0, start[1] + 2.0)

        hole = next(h for h in _layout_of(dialog).holes if h.offset == 5)
        assert hole.center_px == pytest.approx((start[0] + 6.0, start[1] + 2.0), abs=0.01)
        assert hole.snapped is False
        assert _enabled(dialog.reset_button)

        dialog.reset_adjustments()
        hole = next(h for h in _layout_of(dialog).holes if h.offset == 5)
        assert _distance(hole.center_px, start) < 1.0
        assert not _enabled(dialog.reset_button)

    def test_a_press_away_from_holes_does_not_drag(self, tkinter_root):
        _synth, dialog = self._placed(tkinter_root)
        before = dialog._layout
        dialog._on_press(_ev(x=320 * dialog._scale, y=240 * dialog._scale))
        dialog._on_release(_ev(x=330 * dialog._scale, y=250 * dialog._scale))
        assert dialog._layout == before

    def test_drag_events_through_the_canvas_handlers(self, tkinter_root):
        synth, dialog = self._placed(tkinter_root)
        start = synth.hole_center(7)
        s = dialog._scale
        dialog._on_press(_ev(x=start[0] * s, y=start[1] * s))
        dialog._on_motion(_ev(x=(start[0] + 3) * s, y=start[1] * s))
        assert dialog._drag_point == pytest.approx((start[0] + 3, start[1]))
        dialog._on_release(_ev(x=(start[0] + 4) * s, y=start[1] * s))
        hole = next(h for h in _layout_of(dialog).holes if h.offset == 7)
        assert hole.center_px == pytest.approx((start[0] + 4, start[1]), abs=0.01)

    def test_a_new_table_replaces_the_holes_on_the_same_click(self, tkinter_root):
        synth, dialog = self._placed(tkinter_root)
        dialog.set_table(synth.table_ellipse())
        assert dialog.mode is AssistantMode.ADJUST
        assert _distance(_layout_of(dialog).target.center_px, synth.hole_center(0)) < 1.0


class TestApply:
    def test_apply_publishes_the_contract_rois_and_closes(self, tkinter_root, boxes):
        synth = SyntheticTable()
        bus = AnsweringBus()
        dialog = _build(tkinter_root, synth, bus=bus)
        dialog.handle_click(*synth.hole_center(6))
        dialog.trial_type_var.set("probe")

        dialog.apply_layout()

        (payload,) = _published(bus)
        assert payload.video_path == VIDEO
        assert [name for name, _poly in payload.rois] == list(expected_roi_names(20))
        assert len(payload.arena_polygon) == 64
        assert payload.trial_type == "probe"
        layout = _loaded(payload.layout_metadata)
        assert layout is not None
        assert _distance(layout.target.center_px, synth.hole_center(6)) < 1.0
        assert boxes.calls["askyesno"] == []
        assert not dialog.winfo_exists()

    def test_a_frame_without_a_video_entry_sends_no_trial_type(self, tkinter_root, boxes):
        synth = SyntheticTable()
        bus = AnsweringBus()
        dialog = _build(tkinter_root, synth, bus=bus, trial_type_editable=False)
        assert not _enabled(dialog.training_radio)
        dialog.handle_click(*synth.hole_center(0))
        dialog.apply_layout()
        assert _published(bus)[0].trial_type is None

    @pytest.mark.parametrize("answer", [True, False])
    def test_a_suspicious_layout_asks_first(self, tkinter_root, boxes, answer):
        synth = SyntheticTable(missing=(2,))
        bus = AnsweringBus()
        boxes.answer = answer
        dialog = _build(tkinter_root, synth, bus=bus)
        dialog.handle_click(*synth.hole_center(0))

        dialog.apply_layout()

        assert len(boxes.calls["askyesno"]) == 1
        assert len(_published(bus)) == (1 if answer else 0)
        assert bool(dialog.winfo_exists()) is (not answer)

    def test_collapsed_holes_are_reported_not_written(self, tkinter_root, boxes):
        synth = SyntheticTable()
        bus = MagicMock()
        dialog = _build(tkinter_root, synth, bus=bus)
        dialog.handle_click(*synth.hole_center(0))
        dialog._manual = {1: synth.hole_center(0)}
        dialog._relayout()

        dialog.apply_layout()

        assert _published(bus) == []
        assert "overlap" in dialog.status_label.cget("text")
        assert dialog.winfo_exists()

    @pytest.mark.parametrize(
        "bus", [AnsweringBus(answer=False), MagicMock()], ids=["refused", "unanswered"]
    )
    def test_a_write_that_did_not_happen_keeps_the_dialog_open(self, tkinter_root, boxes, bus):
        synth = SyntheticTable()
        dialog = _build(tkinter_root, synth, bus=bus)
        dialog.handle_click(*synth.hole_center(0))

        dialog.apply_layout()

        assert len(_published(bus)) == 1
        assert dialog.winfo_exists()
        assert dialog.applied_paths == []
        assert "could not be saved" in dialog.status_label.cget("text")

    def test_cancel_writes_nothing(self, tkinter_root):
        bus = MagicMock()
        synth = SyntheticTable()
        dialog = _build(tkinter_root, synth, bus=bus)
        dialog.handle_click(*synth.hole_center(0))
        dialog.cancel()
        assert not dialog.winfo_exists()
        assert _published(bus) == []


class TestOtherVideos:
    OTHERS = (OtherVideo("C:/exp/Dia_2/trial.mp4", "G1 / 2"), OtherVideo("C:/x/b.mp4", "b"))

    def test_same_escape_hole_is_re_snapped_on_each_video(self, tkinter_root, boxes):
        here = SyntheticTable()
        shifted = SyntheticTable(center=(324.0, 238.0))  # the camera moved a little
        backgrounds = {VIDEO: here.image(), self.OTHERS[0].path: shifted.image()}
        bus = AnsweringBus()
        dialog = _build(
            tkinter_root,
            here,
            bus=bus,
            loader=lambda path: backgrounds.get(path),
            other_videos=self.OTHERS,
        )
        dialog.handle_click(*here.hole_center(0))
        assert _enabled(dialog.apply_others_button)
        dialog.choose_other_videos = lambda: OtherVideosChoice(  # type: ignore[method-assign]
            paths=tuple(v.path for v in self.OTHERS), same_escape_hole=True, trial_type="training"
        )

        dialog.apply_to_other_videos()

        current, payload = _published(bus)
        assert current.video_path == VIDEO  # one Apply writes this video too
        assert payload.video_path == self.OTHERS[0].path
        assert payload.trial_type == "training"
        layout = _loaded(payload.layout_metadata)
        assert _distance(layout.target.center_px, shifted.hole_center(0)) < 1.0
        assert all(hole.snapped for hole in layout.holes)
        summary = boxes.calls["showinfo"][0][1]
        assert "2 video(s)" in summary and "Could not read: b.mp4" in summary
        assert dialog.applied_paths == [VIDEO, self.OTHERS[0].path]
        assert not dialog.winfo_exists()

    def test_suspicious_copies_are_named(self, tkinter_root, boxes):
        here = SyntheticTable()
        holey = SyntheticTable(missing=(3,))
        bus = AnsweringBus()
        dialog = _build(
            tkinter_root,
            here,
            bus=bus,
            loader=lambda path: here.image() if path == VIDEO else holey.image(),
            other_videos=self.OTHERS[:1],
        )
        dialog.handle_click(*here.hole_center(0))
        dialog.choose_other_videos = lambda: OtherVideosChoice(  # type: ignore[method-assign]
            paths=(self.OTHERS[0].path,), same_escape_hole=True, trial_type=None
        )

        dialog.apply_to_other_videos()

        (current,) = _published(bus)  # the doubtful copy is NOT written
        assert current.video_path == VIDEO
        assert "trial.mp4" in boxes.calls["showinfo"][0][1].split("\n")[1]
        assert dialog.video_path == self.OTHERS[0].path  # reviewed by hand instead
        assert dialog.mode is AssistantMode.TARGET
        assert "Video 1 of 1" in dialog.status_label.cget("text")

    def test_a_cancelled_choice_does_nothing(self, tkinter_root, boxes):
        synth = SyntheticTable()
        bus = MagicMock()
        dialog = _build(tkinter_root, synth, bus=bus, other_videos=self.OTHERS)
        dialog.handle_click(*synth.hole_center(0))
        dialog.choose_other_videos = lambda: None  # type: ignore[method-assign]
        dialog.apply_to_other_videos()
        assert _published(bus) == []

    def test_asking_for_each_escape_hole_walks_the_videos(self, tkinter_root, boxes):
        here = SyntheticTable()
        second = SyntheticTable(phase_deg=2.0)
        third = SyntheticTable(phase_deg=12.0)
        backgrounds = {
            VIDEO: here.image(),
            self.OTHERS[0].path: second.image(),
            self.OTHERS[1].path: third.image(),
        }
        bus = AnsweringBus()
        dialog = _build(
            tkinter_root,
            here,
            bus=bus,
            loader=lambda path: backgrounds[path],
            other_videos=self.OTHERS,
        )
        dialog.handle_click(*here.hole_center(0))
        dialog.choose_other_videos = lambda: OtherVideosChoice(  # type: ignore[method-assign]
            paths=tuple(v.path for v in self.OTHERS), same_escape_hole=False, trial_type="probe"
        )

        dialog.apply_to_other_videos()

        assert dialog.video_path == self.OTHERS[0].path
        assert dialog.mode is AssistantMode.TARGET
        assert "Video 1 of 2" in dialog.status_label.cget("text")
        assert not _enabled(dialog.apply_others_button)
        dialog.handle_click(*second.hole_center(7))
        dialog.apply_layout()
        assert dialog.video_path == self.OTHERS[1].path
        dialog.handle_click(*third.hole_center(11))
        dialog.apply_layout()

        current, first, last = _published(bus)
        assert current.video_path == VIDEO
        assert first.video_path == self.OTHERS[0].path and last.video_path == self.OTHERS[1].path
        assert {first.trial_type, last.trial_type} == {"probe"}
        assert (
            _distance(
                _loaded(last.layout_metadata).target.center_px,
                third.hole_center(11),
            )
            < 1.0
        )
        assert not dialog.winfo_exists()

    def test_an_unreadable_queued_video_is_skipped(self, tkinter_root, boxes):
        here = SyntheticTable()
        bus = AnsweringBus()
        dialog = _build(
            tkinter_root,
            here,
            bus=bus,
            loader=lambda path: here.image() if path in (VIDEO, self.OTHERS[1].path) else None,
            other_videos=self.OTHERS,
        )
        dialog.handle_click(*here.hole_center(0))
        dialog.choose_other_videos = lambda: OtherVideosChoice(  # type: ignore[method-assign]
            paths=tuple(v.path for v in self.OTHERS), same_escape_hole=False, trial_type=None
        )

        dialog.apply_to_other_videos()

        assert boxes.calls["warn"]
        assert dialog.video_path == self.OTHERS[1].path

    def test_a_differently_framed_copy_is_not_written(self, tkinter_root, boxes):
        here = SyntheticTable()
        small = np.full((240, 320), 200, dtype=np.uint8)
        bus = AnsweringBus()
        dialog = _build(
            tkinter_root,
            here,
            bus=bus,
            loader=lambda path: here.image() if path == VIDEO else small,
            other_videos=self.OTHERS[:1],
        )
        dialog.handle_click(*here.hole_center(0))
        dialog.choose_other_videos = lambda: OtherVideosChoice(  # type: ignore[method-assign]
            paths=(self.OTHERS[0].path,), same_escape_hole=True, trial_type=None
        )

        dialog.apply_to_other_videos()

        assert [p.video_path for p in _published(bus)] == [VIDEO]
        assert "Framed differently" in boxes.calls["showinfo"][0][1]

    def test_a_table_outside_another_frame_is_not_reused(self, tkinter_root, boxes):
        here = SyntheticTable()
        moved = SyntheticTable(center=(320.0, 240.0))
        bus = AnsweringBus()
        dialog = _build(
            tkinter_root,
            here,
            bus=bus,
            loader=lambda path: here.image() if path == VIDEO else moved.image(),
            other_videos=self.OTHERS[:1],
            initial_table=geometry.BarnesEllipse(
                center_px=(320.0, 240.0), semi_axes_px=(200.0, 170.0), angle_deg=0.0
            ),
        )
        dialog._table = geometry.BarnesEllipse(
            center_px=(620.0, 240.0), semi_axes_px=(200.0, 170.0), angle_deg=0.0
        )
        dialog._model = geometry.ring_from_click(dialog._table, (700.0, 240.0), 20)
        dialog._layout = geometry.assemble_layout(dialog._table, dialog._model)
        boxes.answer = True
        dialog.choose_other_videos = lambda: OtherVideosChoice(  # type: ignore[method-assign]
            paths=(self.OTHERS[0].path,), same_escape_hole=True, trial_type=None
        )

        dialog.apply_to_other_videos()

        assert self.OTHERS[0].path not in [p.video_path for p in _published(bus)]
        assert "Framed differently" in boxes.calls["showinfo"][0][1]

    def test_a_queued_video_framed_differently_asks_for_its_table(self, tkinter_root, boxes):
        here = SyntheticTable()
        other = np.full((300, 400), 200, dtype=np.uint8)
        dialog = _build(
            tkinter_root,
            here,
            loader=lambda path: here.image() if path == VIDEO else other,
            other_videos=self.OTHERS[:1],
        )
        dialog.handle_click(*here.hole_center(0))
        dialog.choose_other_videos = lambda: OtherVideosChoice(  # type: ignore[method-assign]
            paths=(self.OTHERS[0].path,), same_escape_hole=False, trial_type=None
        )

        dialog.apply_to_other_videos()

        assert dialog.video_path == self.OTHERS[0].path
        assert dialog.mode is AssistantMode.RIM
        assert dialog._table is None
        assert "framed differently" in dialog.status_label.cget("text")

    def test_nothing_else_is_written_when_this_video_fails(self, tkinter_root, boxes):
        here = SyntheticTable()
        bus = AnsweringBus(answer=False)
        dialog = _build(tkinter_root, here, bus=bus, other_videos=self.OTHERS)
        dialog.handle_click(*here.hole_center(0))
        dialog.choose_other_videos = lambda: OtherVideosChoice(  # type: ignore[method-assign]
            paths=tuple(v.path for v in self.OTHERS), same_escape_hole=True, trial_type=None
        )

        dialog.apply_to_other_videos()

        assert [p.video_path for p in _published(bus)] == [VIDEO]
        assert boxes.calls["showinfo"] == []

    def test_the_last_unreadable_video_closes_the_dialog(self, tkinter_root, boxes):
        here = SyntheticTable()
        dialog = _build(
            tkinter_root,
            here,
            loader=lambda path: here.image() if path == VIDEO else None,
            other_videos=self.OTHERS[:1],
        )
        dialog.handle_click(*here.hole_center(0))
        dialog.choose_other_videos = lambda: OtherVideosChoice(  # type: ignore[method-assign]
            paths=(self.OTHERS[0].path,), same_escape_hole=False, trial_type=None
        )
        dialog.apply_to_other_videos()
        assert not dialog.winfo_exists()


class TestOtherVideosDialog:
    VIDEOS = (OtherVideo("a.mp4", "A"), OtherVideo("b.mp4", "B"), OtherVideo("c.mp4", "C"))

    def test_select_all_and_confirm(self, tkinter_root):
        dialog = OtherVideosDialog(tkinter_root, self.VIDEOS, default_trial_type="probe")
        assert dialog.video_list.size() == 3
        dialog.select_all()
        dialog.same_hole_var.set(False)

        dialog.confirm()

        assert dialog.result == OtherVideosChoice(
            paths=("a.mp4", "b.mp4", "c.mp4"), same_escape_hole=False, trial_type="probe"
        )

    def test_keep_each_videos_trial_type(self, tkinter_root):
        dialog = OtherVideosDialog(tkinter_root, self.VIDEOS)
        dialog.video_list.selection_set(1)
        dialog.trial_type_var.set("")
        dialog.confirm()
        assert dialog.result == OtherVideosChoice(
            paths=("b.mp4",), same_escape_hole=True, trial_type=None
        )

    def test_cancel_has_no_result(self, tkinter_root):
        dialog = OtherVideosDialog(tkinter_root, self.VIDEOS)
        dialog.cancel()
        assert dialog.result is None


def test_the_background_falls_back_to_the_frame_in_grayscale(tkinter_root):
    synth = SyntheticTable()
    dialog = _build(tkinter_root, synth, loader=lambda _p: None)
    assert dialog._background is not None
    assert dialog._background.shape == (480, 640)
    assert np.abs(dialog._background.astype(int) - synth.image().astype(int)).max() <= 1


class TestHoleCount:
    @pytest.mark.parametrize(("table_holes", "project_holes"), [(18, 20), (20, 18)])
    def test_the_count_is_detected_on_the_video(self, tkinter_root, table_holes, project_holes):
        synth = SyntheticTable(n_holes=table_holes)
        dialog = _build(tkinter_root, synth, params=BarnesParams(n_holes=project_holes))

        dialog.handle_click(*synth.hole_center(0))

        layout = _layout_of(dialog)
        assert layout.n_holes == table_holes
        assert all(hole.snapped for hole in layout.holes)
        assert dialog.n_holes_var.get() == str(table_holes)
        assert dialog.count_label.cget("text") == (
            f"detected: {table_holes} · project: {project_holes}"
        )

    def test_a_matching_count_writes_no_project_change(self, tkinter_root, boxes):
        synth = SyntheticTable(n_holes=18)
        bus = AnsweringBus()
        dialog = _build(tkinter_root, synth, bus=bus, params=BarnesParams(n_holes=18))
        dialog.handle_click(*synth.hole_center(0))
        assert dialog.count_label.cget("text") == "detected: 18"

        dialog.apply_layout()

        (payload,) = _published(bus)
        assert payload.project_n_holes is None
        assert [name for name, _p in payload.rois] == list(expected_roi_names(18))
        assert boxes.calls["askyesno"] == []

    def test_a_different_count_asks_before_changing_the_project(self, tkinter_root, boxes):
        synth = SyntheticTable(n_holes=18)
        bus = AnsweringBus()
        dialog = _build(tkinter_root, synth, bus=bus, params=BarnesParams(n_holes=20))
        dialog.handle_click(*synth.hole_center(0))

        dialog.apply_layout()

        (question,) = boxes.calls["askyesno"]
        assert "18 holes" in question[1] and "set to 20" in question[1]
        (payload,) = _published(bus)
        assert payload.project_n_holes == 18
        assert [name for name, _p in payload.rois] == list(expected_roi_names(18))
        assert dialog._params.n_holes == 18

    def test_refusing_the_project_change_writes_nothing(self, tkinter_root, boxes):
        synth = SyntheticTable(n_holes=18)
        bus = AnsweringBus()
        boxes.answer = False
        dialog = _build(tkinter_root, synth, bus=bus, params=BarnesParams(n_holes=20))
        dialog.handle_click(*synth.hole_center(0))

        dialog.apply_layout()

        assert _published(bus) == []
        assert dialog.winfo_exists()

    def test_the_user_can_override_the_count(self, tkinter_root):
        synth = SyntheticTable(n_holes=18)
        dialog = _build(tkinter_root, synth, params=BarnesParams(n_holes=18))
        dialog.handle_click(*synth.hole_center(0))

        dialog.n_holes_var.set("20")
        dialog.on_hole_count_changed()

        assert _layout_of(dialog).n_holes == 20
        assert dialog._count_overridden is True
        assert _distance(_layout_of(dialog).target.center_px, synth.hole_center(0)) < 1.5
        dialog.rotate(1)  # an override survives the next placement
        assert _layout_of(dialog).n_holes == 20

    @pytest.mark.parametrize("typed", ["abc", "2", "500"])
    def test_an_invalid_count_is_put_back(self, tkinter_root, typed):
        synth = SyntheticTable()
        dialog = _build(tkinter_root, synth)
        dialog.handle_click(*synth.hole_center(0))

        dialog.n_holes_var.set(typed)
        dialog.on_hole_count_changed()

        assert dialog.n_holes_var.get() == "20"
        assert _layout_of(dialog).n_holes == 20

    def test_a_count_set_before_the_click_is_used(self, tkinter_root):
        synth = SyntheticTable(n_holes=18)
        dialog = _build(tkinter_root, synth, params=BarnesParams(n_holes=18))
        dialog.n_holes_var.set("20")
        dialog.on_hole_count_changed()
        assert dialog._layout is None

        dialog.handle_click(*synth.hole_center(0))

        assert _layout_of(dialog).n_holes == 20


class TestStatusNotes:
    def test_a_single_frame_background_is_announced(self, tkinter_root):
        dialog = _build(tkinter_root, loader=lambda _p: None)
        assert "single frame" in dialog.status_label.cget("text")

    def test_a_real_background_has_no_note(self, tkinter_root):
        dialog = _build(tkinter_root)
        assert "single frame" not in dialog.status_label.cget("text")

    def test_a_relayout_failure_is_shown(self, tkinter_root, monkeypatch):
        synth = SyntheticTable()
        dialog = _build(tkinter_root, synth)
        dialog.handle_click(*synth.hole_center(0))

        def broken(*_args, **_kwargs):
            raise geometry.BarnesGeometryError("ring lost")

        monkeypatch.setattr(dialog_module.geometry, "relayout", broken)
        dialog.rotate(1)

        assert "could not be placed: ring lost" in dialog.status_label.cget("text")
