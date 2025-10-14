from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

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
        self.items: dict[str, dict[str, Any]] = {}
        self.children: dict[str, list[str]] = {"": []}
        self._counter = 0

    def get_children(self, item: str | None = None):
        key = item or ""
        return list(self.children.get(key, []))

    def delete(self, iid):
        iid_str = str(iid)
        for child in list(self.children.get(iid_str, [])):
            self.delete(child)
        self.children.pop(iid_str, None)

        info = self.items.pop(iid_str, None)
        parent = info["parent"] if info else ""
        if parent in self.children:
            self.children[parent] = [c for c in self.children[parent] if c != iid_str]

    def insert(self, parent, index, iid=None, text="", values=None, tags=(), **kwargs):
        if iid is None:
            self._counter += 1
            iid = f"auto_{self._counter}"

        iid_str = str(iid)
        parent_str = str(parent or "")
        self.items[iid_str] = {
            "parent": parent_str,
            "text": text,
            "values": values,
            "tags": tags,
        }
        self.children.setdefault(parent_str, []).append(iid_str)
        self.children.setdefault(iid_str, [])
        return iid_str

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
        {
            "path": "a.mp4",
            "has_arena": True,
            "has_rois": True,
            "has_trajectory": False,
        },
        {
            "path": "b.mp4",
            "has_arena": True,
            "has_rois": True,
            "has_trajectory": True,
        },
        {
            "path": "c.mp4",
            "has_arena": True,
            "has_rois": False,
            "has_trajectory": False,
        },
        {
            "path": "d.mp4",
            "has_arena": False,
            "has_rois": False,
            "has_trajectory": False,
        },
    ]

    gui_instance._update_zone_summary_cards(videos)

    assert gui_instance.zone_summary_cards["arena_missing"]["value"].get() == "1"
    assert gui_instance.zone_summary_cards["arena_missing"]["detail"].get() == "3 com arena salva"

    assert gui_instance.zone_summary_cards["rois_missing"]["value"].get() == "2"
    assert gui_instance.zone_summary_cards["rois_missing"]["detail"].get() == "2 com ROIs salvas"

    assert gui_instance.zone_summary_cards["ready_for_processing"]["value"].get() == "1"
    assert (
        gui_instance.zone_summary_cards["ready_for_processing"]["detail"].get()
        == "1 já com trajetórias"
    )


def test_update_zone_summary_cards_handles_empty_input():
    gui_instance = _make_zone_summary_gui()

    gui_instance._update_zone_summary_cards([])

    for card in gui_instance.zone_summary_cards.values():
        assert card["value"].get() == "0"
        assert card["detail"].get() == "Nenhum vídeo listado"


def test_refresh_pipeline_video_table_sets_summary_column(tmp_path: Path):
    video1 = tmp_path / "vid1.mp4"
    video2 = tmp_path / "vid2.mp4"

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

    class DummyPM(SimpleNamespace):
        def __init__(self, base_path: Path, payload: list[dict]):
            super().__init__()
            self.project_path = str(base_path)
            self._videos = payload

        def get_all_videos(self):
            return self._videos

        def find_video_entry(self, path: str):
            for video in self._videos:
                if video["path"] == path:
                    return video
            return None

        def resolve_results_directory(
            self,
            experiment_id: str,
            *,
            video_path=None,
            metadata=None,
        ):
            return (
                Path(self.project_path)
                / "Grupo_Sem_Grupo"
                / "Dia_Indefinido"
                / "Sujeito_Indefinido"
                / experiment_id
            )

    dummy_pm = DummyPM(tmp_path, videos)
    summary_dir = dummy_pm.resolve_results_directory("vid1", video_path=str(video1))
    summary_dir.mkdir(parents=True, exist_ok=True)
    (summary_dir / "vid1_summary.parquet").write_text("", encoding="utf-8")

    instance = gui.ApplicationGUI.__new__(gui.ApplicationGUI)
    inst_any = cast(Any, instance)
    inst_any.pipeline_tab_frame = object()
    inst_any.pipeline_video_tree = DummyTree()
    inst_any.pipeline_video_vars = {}
    inst_any.pipeline_selection_label = None
    inst_any.pipeline_action_buttons = {}
    inst_any.controller = SimpleNamespace(project_manager=dummy_pm)

    instance._refresh_pipeline_video_table(videos)

    # Tree rows should match sorted by filename (vid1, vid2)
    tree = cast(DummyTree, inst_any.pipeline_video_tree)
    assert str(video1) in tree.items
    assert str(video2) in tree.items

    first_row = tree.items[str(video1)]["values"]
    assert first_row[0] == "✓"  # ROIs
    assert first_row[1] == "✓"  # Trajectory
    assert first_row[2] == "✓"  # Summary column reflects existing parquet
    assert first_row[3].startswith("✅")

    second_row = tree.items[str(video2)]["values"]
    assert second_row[0] == "✗"
    assert second_row[1] == "✗"
    assert second_row[2] == "✗"
    assert second_row[3].startswith("⏳")

    vars_map = cast(dict[str, dict], inst_any.pipeline_video_vars)
    assert vars_map[str(video1)]["summary"] is True
    assert vars_map[str(video2)]["summary"] is False
