"""End to end: a LIVE PROJECT session, from the Progress grid's "record" to the reports.

The contract this guards
------------------------
A live project session belongs to a block (day x group) and a subject. Its
contract, opposite to the ad-hoc session's on the same code:

* the session folder is ``<project>/Grupo_X/Dia_YY/Sujeito_ZZ/live_<timestamp>/``
  — beside the subject's pre-recorded artefacts, never under
  ``live_analysis_sessions/`` or a user-chosen folder;
* it holds the session video ``<base>.mp4`` (projects always record), the
  trajectory ``3_CoordMovimento_<base>.parquet`` (immutable schema), the frame
  ledger ``6_FrameLedger_<base>.{csv,parquet}`` with EXACTLY one row per captured
  frame and its ``_anchor.json``, and the individual report;
* the PROJECT registers the session: after reloading ``project_config.json`` from
  disk there is one entry for the session's video, ``processed``, carrying the
  block's group/day/subject and its report — that is what the Progress grid and
  the Reports tab read.

What runs for real
------------------
``LiveCameraSessionCoordinator.start_live_project_session`` with a real ``live``
project on ``tmp_path``, the real ``LiveCameraService`` threads, ``Recorder``,
``FrameLedger``, "Encerrar e Salvar" and the post-analysis thread. Fakes, from
``tests/helpers/live_flow.py``: the camera (scripted frames), the model
(deterministic plugin) and the weight registry. No Arduino, no Tk.

Runs in CI's default job (no ``slow``/``gui`` marker).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import cv2
import pandas as pd
import pytest

from tests.helpers.flow_e2e import flow_settings, make_zone
from tests.helpers.live_flow import build_live_rig, drive_live_session
from tests.helpers.prerecorded_pipeline import ARENA_POLYGON, ROI_LEFT, TRAJECTORY_COLUMNS
from zebtrack.core.project.project_manager import ProjectManager

pytestmark = pytest.mark.integration

FRAMES = 40
GROUP = "CTRL"
DAY = 1
SUBJECT = "1"
EXPERIMENT_ID = f"day{DAY}_{GROUP}_{SUBJECT}"


@pytest.fixture(scope="module")
def project_session(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    root = tmp_path_factory.mktemp("flow_live_project")
    weight = root / "scripted.pt"
    weight.write_bytes(b"not a real model")
    project_dir = root / "project"

    with pytest.MonkeyPatch.context() as monkeypatch:
        settings = flow_settings()
        pm = ProjectManager(settings_obj=settings)
        pm.create_new_project(
            project_dir,
            "live",
            group_names=[GROUP],
            num_groups=1,
            experiment_days=1,
            subjects_per_group=1,
            animals_per_aquarium=1,
            analysis_interval_frames=1,
            display_interval_frames=1,
            recording_duration_s=600,
        )
        # A live project has one camera and one arena: the zones are global.
        pm.save_zone_data(
            make_zone(
                [(int(x), int(y)) for x, y in ARENA_POLYGON],
                [(int(x), int(y)) for x, y in ROI_LEFT],
                "Esquerda",
            )
        )
        rig = build_live_rig(monkeypatch, pm, settings, frames=FRAMES, weight_file=weight)
        session_dir = drive_live_session(
            rig,
            lambda: rig.coordinator.start_live_project_session(
                day=DAY,
                group=GROUP,
                subject=SUBJECT,
                duration_s=600,
                camera_index_override=0,
                zones_validated=True,
            ),
        )

    return {
        "root": root,
        "project_dir": project_dir,
        "session": session_dir,
        "rig": rig,
        "subject_dir": project_dir / f"Grupo_{GROUP}" / f"Dia_{DAY:02d}" / "Sujeito_01",
    }


def _base(run: dict) -> str:
    return run["session"].name


def test_the_session_folder_sits_in_the_subject_folder(project_session: dict) -> None:
    session: Path = project_session["session"]
    assert session.parent == project_session["subject_dir"]
    assert session.name.startswith("live_")


def test_nothing_is_written_outside_the_project(project_session: dict) -> None:
    root: Path = project_session["root"]
    assert sorted(p.name for p in root.iterdir()) == ["project", "scripted.pt"]
    assert not (project_session["project_dir"] / "live_analysis_sessions").exists()


def test_the_session_folder_holds_video_trajectory_ledger_and_report(
    project_session: dict,
) -> None:
    session: Path = project_session["session"]
    base = _base(project_session)
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


def test_ledger_and_video_account_for_every_frame_fed(project_session: dict) -> None:
    base = _base(project_session)
    session: Path = project_session["session"]
    fed = project_session["rig"].script.delivered
    assert fed == FRAMES

    ledger = pd.read_parquet(session / f"6_FrameLedger_{base}.parquet")
    assert len(ledger) == fed
    assert sorted(ledger["pipeline_frame"].tolist()) == list(range(1, fed + 1))
    assert set(ledger["outcome"]) == {"written"}, ledger["outcome"].value_counts().to_dict()

    capture = cv2.VideoCapture(str(session / f"{base}.mp4"))
    try:
        assert int(capture.get(cv2.CAP_PROP_FRAME_COUNT)) == fed
    finally:
        capture.release()


def test_trajectory_keeps_the_immutable_schema(project_session: dict) -> None:
    base = _base(project_session)
    df = pd.read_parquet(project_session["session"] / f"3_CoordMovimento_{base}.parquet")
    assert list(df.columns) == TRAJECTORY_COLUMNS
    assert sorted(df["frame"].tolist()) == list(range(1, FRAMES + 1))
    assert df["track_id"].nunique() == 1


def test_the_project_on_disk_registers_the_session(project_session: dict) -> None:
    """Reload from disk: what the Progress grid and the Reports tab will read."""
    reloaded = ProjectManager(settings_obj=flow_settings())
    reloaded.load_project(project_session["project_dir"])
    session: Path = project_session["session"]
    entries = [
        v
        for v in reloaded.get_all_videos()
        if Path(str(v.get("path", ""))).resolve().parent == session.resolve()
    ]
    assert len(entries) == 1, [v.get("path") for v in reloaded.get_all_videos()]
    entry = entries[0]
    assert Path(entry["path"]).name == f"{_base(project_session)}.mp4"
    assert entry.get("status") == "processed", entry.get("status")
    metadata = entry.get("metadata") or {}
    assert metadata.get("group") == GROUP, metadata
    assert metadata.get("subject_id") == SUBJECT, metadata
    assert metadata.get("day") == f"Dia_{DAY}", metadata
    assert metadata.get("experiment_id") == EXPERIMENT_ID, metadata
    assert metadata.get("is_live_session") is True, metadata
    files = entry.get("parquet_files") or {}
    assert (
        Path(files["report_docx"]).resolve()
        == (session / f"4_Relatorio_{EXPERIMENT_ID}.docx").resolve()
    )


def test_the_progress_grid_sees_the_block_as_recorded(project_session: dict) -> None:
    """``get_completed_sessions`` is what paints the block in the Progress grid."""
    reloaded = ProjectManager(settings_obj=flow_settings())
    reloaded.load_project(project_session["project_dir"])
    completed = reloaded.get_completed_sessions()
    assert any(day == DAY and group == GROUP for day, group, _subject in completed), completed
