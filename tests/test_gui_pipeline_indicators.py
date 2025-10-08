from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from zebtrack.ui import gui


class DummyVar:
    def __init__(self, value="0"):
        self.value = value

    def set(self, value):
        self.value = value

    def get(self):
        return self.value


class DummyTree:
    def __init__(self):
        self.items = []

    def get_children(self):
        return [item["iid"] for item in self.items]

    def delete(self, iid):
        self.items = [item for item in self.items if item["iid"] != iid]

    def insert(self, parent, index, iid=None, values=None):
        self.items.append({"iid": iid, "values": values})

    def selection(self):
        return []


def _make_zone_summary_gui():
    instance = gui.ApplicationGUI.__new__(gui.ApplicationGUI)
    inst_any = cast(Any, instance)
    inst_any.zone_summary_cards = {
        "arena_missing": {"value": DummyVar(), "detail": DummyVar()},
        "rois_missing": {"value": DummyVar(), "detail": DummyVar()},
        "ready_for_processing": {"value": DummyVar(), "detail": DummyVar()},
    }
    inst_any.controller = SimpleNamespace(project_manager=None)
    return instance


def test_update_zone_summary_cards_populates_metrics():
    gui_instance = _make_zone_summary_gui()
    videos = [
        {"path": "a.mp4", "has_arena": True, "has_rois": True, "has_trajectory": False},
        {"path": "b.mp4", "has_arena": True, "has_rois": True, "has_trajectory": True},
        {"path": "c.mp4", "has_arena": True, "has_rois": False, "has_trajectory": False},
        {"path": "d.mp4", "has_arena": False, "has_rois": False, "has_trajectory": False},
    ]

    gui_instance._update_zone_summary_cards(videos)

    assert gui_instance.zone_summary_cards["arena_missing"]["value"].get() == "1"
    assert gui_instance.zone_summary_cards["arena_missing"]["detail"].get() == "3 com arena salva"

    assert gui_instance.zone_summary_cards["rois_missing"]["value"].get() == "2"
    assert gui_instance.zone_summary_cards["rois_missing"]["detail"].get() == "2 com ROIs salvas"

    assert gui_instance.zone_summary_cards["ready_for_processing"]["value"].get() == "1"
    assert gui_instance.zone_summary_cards["ready_for_processing"]["detail"].get() == "1 já com trajetórias"


def test_update_zone_summary_cards_handles_empty_input():
    gui_instance = _make_zone_summary_gui()

    gui_instance._update_zone_summary_cards([])

    for card in gui_instance.zone_summary_cards.values():
        assert card["value"].get() == "0"
        assert card["detail"].get() == "Nenhum vídeo listado"


def test_refresh_pipeline_video_table_sets_summary_column(tmp_path: Path):
    video1 = tmp_path / "vid1.mp4"
    video2 = tmp_path / "vid2.mp4"

    summary_dir = tmp_path / "vid1_results"
    summary_dir.mkdir()
    (summary_dir / "vid1_summary.parquet").write_text("", encoding="utf-8")

    videos = [
        {
            "path": str(video1),
            "has_arena": True,
            "has_rois": True,
            "has_trajectory": True,
            "status": "complete",
        },
        {
            "path": str(video2),
            "has_arena": True,
            "has_rois": False,
            "has_trajectory": False,
            "status": "pending",
        },
    ]

    instance = gui.ApplicationGUI.__new__(gui.ApplicationGUI)
    inst_any = cast(Any, instance)
    inst_any.pipeline_tab_frame = object()
    inst_any.pipeline_video_tree = DummyTree()
    inst_any.pipeline_video_vars = {}
    inst_any.pipeline_selection_label = None
    inst_any.pipeline_action_buttons = {}
    inst_any.controller = SimpleNamespace(
        project_manager=SimpleNamespace(
            project_path=str(tmp_path),
            get_all_videos=lambda: videos,
        )
    )

    instance._refresh_pipeline_video_table(videos)

    # Tree rows should match sorted by filename (vid1, vid2)
    tree = cast(DummyTree, inst_any.pipeline_video_tree)
    assert len(tree.items) == 2

    first_row = tree.items[0]["values"]
    assert first_row[0] == "✓"  # ROIs
    assert first_row[1] == "✓"  # Trajectory
    assert first_row[2] == "✓"  # Summary column reflects existing parquet
    assert first_row[3].startswith("✅")

    second_row = tree.items[1]["values"]
    assert second_row[0] == "✗"
    assert second_row[1] == "✗"
    assert second_row[2] == "✗"
    assert second_row[3].startswith("⏳")

    vars_map = cast(dict[str, dict], inst_any.pipeline_video_vars)
    assert vars_map[str(video1)]["summary"] is True
    assert vars_map[str(video2)]["summary"] is False
