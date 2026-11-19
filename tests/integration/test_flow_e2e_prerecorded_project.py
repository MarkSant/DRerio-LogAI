"""End to end: a PRE-RECORDED PROJECT, from "process pending videos" to the reports.

The contract this guards
------------------------
A pre-recorded project is the flow where identity is the PATH, never the stem.
A longitudinal project films the same animal every day, so
``Dia_1/CECT_4/CECT_4.mp4`` and ``Dia_2/CECT_4/CECT_4.mp4`` share the
experiment id ``CECT_4``. The flow must, for each video:

* write every artefact into ``<project>/Grupo_X/Dia_YY/Sujeito_ZZ/`` derived from
  THAT video's metadata, so day 2 never overwrites day 1;
* process it with ITS OWN arena: the arena of video A is not the arena of
  video B (``save_zone_data`` no longer mirrors per-video zones into the global
  default of a pre-recorded project, see CLAUDE.md);
* record the immutable trajectory schema, in order;
* produce the individual report (``4_Relatorio_<base>.{docx,xlsx}``) and register
  it in the project entry of THAT video.

What runs for real
------------------
``VideoProcessingCoordinator.process_pending_project_videos`` — the handler of
the project's "process pending" action — with a real ``ProjectManager`` on
``tmp_path``, the real selection / validation / classification services, the real
``ProcessingWorker`` monitor thread and callbacks, the real ``_WorkerProcess``
loop (``run()``), the real ``VideoCompletionMixin`` and the real
``ReportGenerationCoordinator`` with a real ``AnalysisService``.

What is faked, and why
----------------------
Only the boundaries a headless test cannot cross:

* the PROCESS boundary — ``_WorkerProcess.start`` runs ``run()`` in this process
  (``is_alive``/``join`` follow suit). Spawning would re-import the module tree
  in the child, where the deterministic detector cannot be injected;
* the MODEL — the YOLO plugin class the worker imports becomes
  ``GoldenDeterministicPlugin`` (no weights, no inference variance); the rest of
  ``_initialize_detector`` runs for real;
* the worker's ``configure_logging`` — it would reconfigure structlog for the
  whole test session and write ``analysis_worker.log`` into the cwd.

Zones are saved exactly as the Zones tab saves them (raw pixels of the video,
no source size). The module fixture sets ``camera.desired_*`` to the video size;
the tests at the bottom keep the shipped 1280x720 reference and prove the
camera reference plays no part in a pre-recorded run (A8-001), and that a zone
which states its source size keeps it all the way to the worker (A8-002).

Runs in CI's default job (no ``slow``/``gui`` marker).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from tests.helpers.flow_e2e import (
    build_processing_coordinator,
    flow_settings,
    make_zone,
    run_worker_in_process,
    wait_for_processing,
)
from tests.helpers.prerecorded_pipeline import (
    HEIGHT,
    TRAJECTORY_COLUMNS,
    WIDTH,
    write_golden_video,
)
from zebtrack.core.detection import ZoneData
from zebtrack.core.project.project_manager import ProjectManager
from zebtrack.settings import Settings

pytestmark = pytest.mark.integration

STEM = "CECT_4"
GROUP = "CEC"
SUBJECT = 4

#: Video A (day 1) sees the whole tank; video B (day 2) only its right half.
#: The subject travels x = 100 -> 500 px and later zig-zags back to x ~ 280,
#: so a run with B's arena can only keep detections whose centre is at
#: x >= 320, while a run with A's arena keeps the left half too.
ARENA_A = [(40, 40), (600, 40), (600, 440), (40, 440)]
ARENA_B = [(320, 40), (600, 40), (600, 440), (320, 440)]
ROI_A = [(40, 40), (320, 40), (320, 440), (40, 440)]
ROI_B = [(320, 40), (460, 40), (460, 440), (320, 440)]


def _entry(pm: ProjectManager, path: str) -> dict[str, Any]:
    entry = pm.find_video_entry(path=path)
    assert entry is not None, f"{path} is not in the project"
    return entry


def _run_project(root: Path, settings: Settings, zones: dict[int, ZoneData]) -> dict[str, Any]:
    """Create the project in ``root``, process both days, return what the tests read."""
    videos = {}
    for day in (1, 2):
        path = root / "videos" / f"Dia_{day}" / STEM / f"{STEM}.mp4"
        path.parent.mkdir(parents=True)
        try:
            write_golden_video(path)
        except RuntimeError as exc:  # pragma: no cover - codec-less runner
            pytest.skip(str(exc))
        videos[day] = path

    with pytest.MonkeyPatch.context() as monkeypatch:
        run_worker_in_process(monkeypatch)
        project_dir = root / "project"
        pm = ProjectManager(settings_obj=settings)
        pm.create_new_project(
            project_dir,
            "pre-recorded",
            video_files=[
                {
                    "path": str(videos[day]),
                    "metadata": {"group": GROUP, "day": day, "subject": SUBJECT},
                }
                for day in (1, 2)
            ],
        )
        stored = {day: _entry(pm, str(videos[day]))["path"] for day in (1, 2)}
        for day, zone in zones.items():
            pm.save_zone_data(zone, stored[day])

        coordinator = build_processing_coordinator(pm, settings)
        coordinator.process_pending_project_videos([stored[1], stored[2]])
        wait_for_processing(coordinator)

    return {
        "project_dir": project_dir,
        "videos": videos,
        "stored_paths": stored,
        "pm": pm,
        "folders": {
            day: project_dir / f"Grupo_{GROUP}" / f"Dia_{day:02d}" / f"Sujeito_{SUBJECT:02d}"
            for day in (1, 2)
        },
    }


@pytest.fixture(scope="module")
def project_run(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    """Process both days once, with zones shaped exactly like the Zones tab saves them."""
    return _run_project(
        tmp_path_factory.mktemp("flow_prerecorded_project"),
        flow_settings(),
        {1: make_zone(ARENA_A, ROI_A, "Esquerda"), 2: make_zone(ARENA_B, ROI_B, "Faixa")},
    )


def test_each_day_lands_in_its_own_group_day_subject_folder(project_run: dict) -> None:
    for day, folder in project_run["folders"].items():
        for name in (
            f"1_ProcessingArea_{STEM}.parquet",
            f"3_CoordMovimento_{STEM}.parquet",
            f"4_Relatorio_{STEM}.docx",
            f"4_Relatorio_{STEM}.xlsx",
        ):
            assert (folder / name).is_file(), f"day {day}: {name} missing in {folder}"


def test_nothing_is_written_next_to_the_source_videos(project_run: dict) -> None:
    """The project's tree is the only destination; the input folders stay clean."""
    for video in project_run["videos"].values():
        assert sorted(p.name for p in video.parent.iterdir()) == [video.name]


def test_trajectory_keeps_the_immutable_schema(project_run: dict) -> None:
    for day, folder in project_run["folders"].items():
        df = pd.read_parquet(folder / f"3_CoordMovimento_{STEM}.parquet")
        assert list(df.columns) == TRAJECTORY_COLUMNS, f"day {day}"
        assert len(df) > 0, f"day {day}: the trajectory is empty"


def test_each_video_was_processed_with_its_own_arena(project_run: dict) -> None:
    """Day 2's arena is the right half; day 1's is the whole tank."""
    folders = project_run["folders"]
    day1 = pd.read_parquet(folders[1] / f"3_CoordMovimento_{STEM}.parquet")
    day2 = pd.read_parquet(folders[2] / f"3_CoordMovimento_{STEM}.parquet")

    assert (day1["x_center_px"] < 320).any(), "day 1 lost the left half of its arena"
    assert (day2["x_center_px"] >= 320 - 12).all(), (
        "day 2 kept detections outside its own arena — it ran with another video's"
    )
    assert len(day1) > len(day2)

    arena1 = pd.read_parquet(folders[1] / f"1_ProcessingArea_{STEM}.parquet")
    arena2 = pd.read_parquet(folders[2] / f"1_ProcessingArea_{STEM}.parquet")
    assert not arena1.equals(arena2), "both days recorded the same arena polygon"


def test_day_two_did_not_overwrite_day_one(project_run: dict) -> None:
    """Different arenas -> different numbers; equal reports would mean one copy."""
    folders = project_run["folders"]
    traj1 = (folders[1] / f"3_CoordMovimento_{STEM}.parquet").read_bytes()
    traj2 = (folders[2] / f"3_CoordMovimento_{STEM}.parquet").read_bytes()
    assert traj1 != traj2
    sheet1 = pd.read_excel(folders[1] / f"4_Relatorio_{STEM}.xlsx", sheet_name=0)
    sheet2 = pd.read_excel(folders[2] / f"4_Relatorio_{STEM}.xlsx", sheet_name=0)
    assert not sheet1.equals(sheet2)


def test_the_project_registers_each_report_on_its_own_entry(project_run: dict) -> None:
    pm: ProjectManager = project_run["pm"]
    for day, stored in project_run["stored_paths"].items():
        entry = pm.find_video_entry(path=stored)
        assert entry is not None
        folder = project_run["folders"][day]
        # ``update_video_status(..., "complete")`` persists the canonical "processed".
        assert entry.get("status") == "processed", f"day {day}: {entry.get('status')}"
        files = entry.get("parquet_files") or {}
        expected = {
            "trajectory": folder / f"3_CoordMovimento_{STEM}.parquet",
            "report_docx": folder / f"4_Relatorio_{STEM}.docx",
            "summary_excel": folder / f"4_Relatorio_{STEM}.xlsx",
        }
        for key, path in expected.items():
            assert files.get(key), f"day {day}: {key} not registered: {files}"
            assert Path(files[key]).resolve() == path.resolve(), f"day {day}: {key}"
        assert Path(entry["results_dir"]).resolve() == folder.resolve()


def test_identity_is_the_path_even_for_byte_identical_videos(project_run: dict) -> None:
    """Both days are the SAME bytes (same sha256) and the same stem.

    Only the path tells the two entries apart, so any lookup by stem or by
    content hash would have folded day 2 into day 1.
    """
    pm: ProjectManager = project_run["pm"]
    entries = [_entry(pm, p) for p in project_run["stored_paths"].values()]
    assert entries[0] is not entries[1]
    assert entries[0]["sha256"] == entries[1]["sha256"]
    assert [e["metadata"]["day"] for e in entries] == [1, 2]


def _halved(points: list[tuple[int, int]]) -> list[tuple[int, int]]:
    return [(x // 2, y // 2) for x, y in points]


def test_project_worker_receives_the_zone_source_size(tmp_path: Path) -> None:
    """Zones that DO state their source size must be scaled from it (A8-002).

    Shipped camera reference (1280x720), a 640x480 video, and both arenas saved
    at HALF size WITH ``source_video_width/height = 320x240``, as a zone drawn on
    a 320x240 proxy would be. Only that metadata turns the half-size polygon back
    into the whole tank: without it the worker reads the points as this video's
    own pixels (the A8-001 default), the arena ends at x = 300 and the subject's
    walk to x = 500 px is dropped. So this fails exactly when the project batch
    (``_load_zones_for_eligible_videos``) strips ``metadata`` on the way to the
    worker, whatever the default for zones without a size.
    """
    half = (WIDTH // 2, HEIGHT // 2)
    run = _run_project(
        tmp_path,
        flow_settings(camera_matches_video=False),
        {
            1: make_zone(_halved(ARENA_A), _halved(ROI_A), "Esquerda", source_size=half),
            2: make_zone(_halved(ARENA_A), _halved(ROI_A), "Esquerda", source_size=half),
        },
    )
    for day in (1, 2):
        df = pd.read_parquet(run["folders"][day] / f"3_CoordMovimento_{STEM}.parquet")
        assert df["x_center_px"].max() > 400, f"day {day}"


def test_zones_without_a_source_size_are_this_videos_pixels(tmp_path: Path) -> None:
    """Shipped 1280x720 camera reference, 640x480 videos, zones with NO source size.

    That is how every Zones-tab zone is saved (A8-001): raw pixels of the video
    they belong to. The camera reference is the live camera's resolution, never
    a coordinate base for a file, so the whole-tank arena must keep the walk to
    x = 500 px on both days.
    """
    run = _run_project(
        tmp_path,
        flow_settings(camera_matches_video=False),
        {1: make_zone(ARENA_A, ROI_A, "Esquerda"), 2: make_zone(ARENA_A, ROI_A, "Esquerda")},
    )
    for day in (1, 2):
        df = pd.read_parquet(run["folders"][day] / f"3_CoordMovimento_{STEM}.parquet")
        assert df["x_center_px"].max() > 400, f"day {day}"
