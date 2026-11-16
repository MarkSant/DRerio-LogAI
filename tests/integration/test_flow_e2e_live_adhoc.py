"""End to end: an AD-HOC live session (no project), from "start" to the reports.

The contract this guards
------------------------
The ad-hoc live session ("Analisar Câmera ao Vivo") has no project. Its
contract, opposite to the live project's on the same code:

* everything lands in ONE session folder under the output folder the user
  chose: ``<output>/<experiment_id>_<timestamp>/``;
* the folder holds the session video ``<base>.mp4``, the trajectory
  ``3_CoordMovimento_<base>.parquet`` (immutable schema), the frame ledger
  ``6_FrameLedger_<base>.{csv,parquet}`` with EXACTLY one row per captured
  frame, its ``_anchor.json``, and the individual report;
* nothing is written into any project: no ``project_config.json``, no
  ``Grupo_*`` tree, and the ``ProjectManager`` still has no ``project_path``
  (the session is registered in memory only, so the Reports tab can list it).

What runs for real
------------------
``LiveCameraSessionCoordinator.start_session_from_config`` (what
``LiveAnalysisDialog`` triggers), ``LiveCameraService`` with its capture,
processing and video threads, ``Recorder``, ``FrameLedger``, the "Encerrar e
Salvar" completion and the post-analysis thread. Fakes, from
``tests/helpers/live_flow.py``: the camera (scripted frames), the model
(deterministic plugin) and the weight registry. No Arduino, no Tk.

Why no numeric golden: the live timestamp is a PROCESSING clock (CLAUDE.md
§ 6_FrameLedger), so the numbers are not reproducible; the counts and the layout
are, and those are what this asserts.

Runs in CI's default job (no ``slow``/``gui`` marker).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import cv2
import pandas as pd
import pytest

from tests.helpers.flow_e2e import flow_settings, make_zone
from tests.helpers.live_flow import build_live_rig, drive_live_session
from tests.helpers.prerecorded_pipeline import ARENA_POLYGON, ROI_LEFT, TRAJECTORY_COLUMNS, WIDTH
from zebtrack.core.project.project_manager import ProjectManager

pytestmark = pytest.mark.integration

FRAMES = 40
EXPERIMENT_ID = "ADHOC_CAM"


@pytest.fixture(scope="module")
def adhoc_run(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    root = tmp_path_factory.mktemp("flow_live_adhoc")
    weight = root / "scripted.pt"
    weight.write_bytes(b"not a real model")
    output = root / "sessions"

    with pytest.MonkeyPatch.context() as monkeypatch:
        settings = flow_settings()
        pm = ProjectManager(settings_obj=settings)
        # The ad-hoc zone tab saves into the global zones: there is no video.
        pm.save_zone_data(
            make_zone(
                [(int(x), int(y)) for x, y in ARENA_POLYGON],
                [(int(x), int(y)) for x, y in ROI_LEFT],
                "Esquerda",
            ),
            persist=False,
        )
        rig = build_live_rig(monkeypatch, pm, settings, frames=FRAMES, weight_file=weight)
        session_dir = drive_live_session(
            rig,
            lambda: rig.coordinator.start_session_from_config(
                {
                    "camera_index": 0,
                    "duration_s": 600,
                    "experiment_id": EXPERIMENT_ID,
                    "output_folder": str(output),
                    "record_video": True,
                    "analysis_interval_frames": 1,
                    "display_interval_frames": 1,
                },
                zones_validated=True,
            ),
        )

    return {"root": root, "output": output, "session": session_dir, "pm": pm, "rig": rig}


def _base(run: dict) -> str:
    return run["session"].name


def test_the_session_folder_sits_under_the_chosen_output(adhoc_run: dict) -> None:
    session: Path = adhoc_run["session"]
    assert session.parent == adhoc_run["output"]
    assert session.name.startswith(f"{EXPERIMENT_ID}_")
    assert [p for p in adhoc_run["output"].iterdir()] == [session]


def test_the_session_folder_holds_video_trajectory_ledger_and_report(adhoc_run: dict) -> None:
    session: Path = adhoc_run["session"]
    base = _base(adhoc_run)
    for name in (
        f"{base}.mp4",
        f"3_CoordMovimento_{base}.parquet",
        f"6_FrameLedger_{base}.csv",
        f"6_FrameLedger_{base}.parquet",
        f"6_FrameLedger_{base}_anchor.json",
        f"4_Relatorio_{EXPERIMENT_ID}.docx",
        f"4_Relatorio_{EXPERIMENT_ID}.xlsx",
    ):
        assert (session / name).is_file(), f"{name} missing; have {sorted(os.listdir(session))}"


def test_the_session_video_has_every_captured_frame(adhoc_run: dict) -> None:
    capture = cv2.VideoCapture(str(adhoc_run["session"] / f"{_base(adhoc_run)}.mp4"))
    try:
        assert int(capture.get(cv2.CAP_PROP_FRAME_COUNT)) == FRAMES
        assert int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)) == WIDTH
    finally:
        capture.release()


def test_the_ledger_has_one_row_per_captured_frame(adhoc_run: dict) -> None:
    base = _base(adhoc_run)
    ledger = pd.read_parquet(adhoc_run["session"] / f"6_FrameLedger_{base}.parquet")
    fed = adhoc_run["rig"].script.delivered
    assert fed == FRAMES
    assert len(ledger) == fed
    assert sorted(ledger["pipeline_frame"].tolist()) == list(range(1, fed + 1))
    assert set(ledger["outcome"]) == {"written"}, ledger["outcome"].value_counts().to_dict()
    assert sorted(ledger["video_frame_index"].tolist()) == list(range(fed))


def test_the_anchor_describes_this_session(adhoc_run: dict) -> None:
    base = _base(adhoc_run)
    anchor = json.loads(
        (adhoc_run["session"] / f"6_FrameLedger_{base}_anchor.json").read_text(encoding="utf-8")
    )
    assert "t0_perf" in anchor and "t0_wall" in anchor, sorted(anchor)
    assert anchor["base_name"] == _base(adhoc_run)
    assert anchor["rows"] == FRAMES
    assert anchor["camera_frames_skipped"] == 0


def test_trajectory_keeps_the_immutable_schema(adhoc_run: dict) -> None:
    base = _base(adhoc_run)
    df = pd.read_parquet(adhoc_run["session"] / f"3_CoordMovimento_{base}.parquet")
    assert list(df.columns) == TRAJECTORY_COLUMNS
    # One subject, detected on every analysed frame (interval 1).
    assert sorted(df["frame"].tolist()) == list(range(1, FRAMES + 1))
    assert df["track_id"].nunique() == 1


def test_nothing_is_written_into_any_project(adhoc_run: dict) -> None:
    root: Path = adhoc_run["root"]
    assert list(root.rglob("project_config.json")) == []
    assert list(root.rglob("Grupo_*")) == []
    pm: ProjectManager = adhoc_run["pm"]
    assert not pm.project_path


def test_the_session_is_registered_in_memory_for_the_reports_tab(adhoc_run: dict) -> None:
    """Registered so the Reports tab lists it; with no project nothing is saved."""
    pm: ProjectManager = adhoc_run["pm"]
    session: Path = adhoc_run["session"]
    entries = [v for v in pm.get_all_videos() if Path(str(v.get("path", ""))).parent == session]
    assert len(entries) == 1, pm.get_all_videos()
    files = entries[0].get("parquet_files") or {}
    assert Path(files["report_docx"]).name == f"4_Relatorio_{EXPERIMENT_ID}.docx"
