import sys
import types
from typing import Any, cast


class FakeTree:
    def __init__(self):
        self.inserted = {}
        self.children = {}

    def insert(self, parent, index, iid, text, values=(), open=False):
        if iid in self.inserted:
            raise AssertionError(f"Duplicate iid inserted: {iid}")
        self.inserted[iid] = {
            "parent": parent,
            "text": text,
            "values": values,
            "open": open,
        }
        self.children.setdefault(parent, []).append(iid)
        self.children.setdefault(iid, [])
        return iid


class _PMStub:
    def __init__(self, canonical_entry):
        self._canonical_entry = canonical_entry

    def find_video_entry(self, path):
        # The real ProjectManager accepts Path|str, we just echo canonical.
        return self._canonical_entry


class _ControllerStub:
    def __init__(self, project_manager):
        self.project_manager = project_manager


class _GUIStub:
    def __init__(self, controller):
        self.controller = controller


def _make_pvm_stub(gui):
    # Import lazily so tests can stub zebtrack.ui.gui before the method runs.
    from zebtrack.ui.components.project_views.reports_tree_manager import ReportsTreeManager

    pvm = ReportsTreeManager.__new__(ReportsTreeManager)
    pvm.gui = gui

    # Avoid touching filesystem from this unit test.
    pvm_any = cast(Any, pvm)
    pvm_any.append_processing_reports_artifacts = lambda *args, **kwargs: None
    return pvm


def test_reports_tree_includes_both_aquariums_via_canonical_fallback(monkeypatch):
    # Stub out zebtrack.ui.gui to avoid importing the real GUI module in a headless test.
    stub_gui_mod = types.SimpleNamespace(
        STATUS_SYMBOLS={
            "arena": "A",
            "rois": "R",
            "trajectory": "T",
            "summary": "S",
        }
    )
    monkeypatch.setitem(sys.modules, "zebtrack.ui.gui", stub_gui_mod)

    video_path = "C:/tmp/video.mp4"

    # Simulate hierarchy video dict missing multi_aquarium_outputs.
    hierarchy = {
        "G1": {
            "display": "Grupo 1",
            "days": {
                1: [
                    {
                        "path": video_path,
                        "metadata": {"subject": "S1", "day": 1},
                        "has_arena": True,
                        "has_rois": True,
                        "has_trajectory": True,
                        "has_summary": True,
                    }
                ]
            },
        }
    }

    canonical_entry = {
        "path": video_path,
        "multi_aquarium_outputs": {
            0: {"results_dir": "", "parquet_files": {"trajectory": "t0.parquet"}},
            1: {"results_dir": "", "parquet_files": {"trajectory": "t1.parquet"}},
        },
    }

    pm = _PMStub(canonical_entry=canonical_entry)
    gui = _GUIStub(controller=_ControllerStub(project_manager=pm))
    pvm = _make_pvm_stub(gui)

    tree = FakeTree()
    metadata_store: dict[str, object] = {}

    pvm._populate_reports_tree_from_hierarchy(tree, hierarchy, "", metadata_store)

    aquarium_nodes = [iid for iid in tree.inserted.keys() if "_aquarium_" in iid]
    assert any(iid.endswith("_aquarium_0") for iid in aquarium_nodes)
    assert any(iid.endswith("_aquarium_1") for iid in aquarium_nodes)


def test_reports_tree_normalizes_mixed_aquarium_keys(monkeypatch):
    stub_gui_mod = types.SimpleNamespace(
        STATUS_SYMBOLS={
            "arena": "A",
            "rois": "R",
            "trajectory": "T",
            "summary": "S",
        }
    )
    monkeypatch.setitem(sys.modules, "zebtrack.ui.gui", stub_gui_mod)

    video_path = "C:/tmp/video2.mp4"

    hierarchy = {
        "G1": {
            "display": "Grupo 1",
            "days": {
                1: [
                    {
                        "path": video_path,
                        "metadata": {"subject": "S2", "day": 1},
                        "has_arena": True,
                        "has_rois": True,
                        "has_trajectory": True,
                        "has_summary": True,
                        # Mixed keys should merge into aquarium 0 + aquarium 1.
                        "multi_aquarium_outputs": {
                            0: {"results_dir": "", "parquet_files": {"trajectory": "t0.parquet"}},
                            "0": {
                                "results_dir": "",
                                "parquet_files": {"summary": "s0.parquet"},
                                "frame_crop_box": (1, 2, 3, 4),
                            },
                            "1": {"results_dir": "", "parquet_files": {"trajectory": "t1.parquet"}},
                        },
                    }
                ]
            },
        }
    }

    pm = _PMStub(canonical_entry=None)
    gui = _GUIStub(controller=_ControllerStub(project_manager=pm))
    pvm = _make_pvm_stub(gui)

    tree = FakeTree()
    metadata_store: dict[str, object] = {}

    pvm._populate_reports_tree_from_hierarchy(tree, hierarchy, "", metadata_store)

    aquarium_nodes = [iid for iid in tree.inserted.keys() if "_aquarium_" in iid]
    # Should be exactly two aquariums (0 and 1) after normalization.
    assert sum(1 for iid in aquarium_nodes if iid.endswith("_aquarium_0")) == 1
    assert sum(1 for iid in aquarium_nodes if iid.endswith("_aquarium_1")) == 1

    # Ensure metadata for aquarium 0 was created (and didn't crash on mixed keys).
    assert any(
        (isinstance(meta, dict) and meta.get("type") == "aquarium" and meta.get("aquarium_id") == 0)
        for meta in metadata_store.values()
    )
