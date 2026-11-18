"""End to end: a SINGLE VIDEO with no project, from "start" to the reports.

The contract this guards
------------------------
The single-video flow is the one with NO project. Its contract is the opposite
of the project flow's on the same code (``ProjectManager``,
``resolve_results_directory``, ``VideoCompletionMixin``,
``ReportGenerationCoordinator``):

* every artefact lands in ``<video_dir>/<stem>_results/`` — never in a
  ``Grupo_*/Dia_*/Sujeito_*`` tree, which is the project layout;
* no project is created or saved: no ``project_config.json`` anywhere, and the
  ``ProjectManager`` still has no ``project_path`` afterwards (the video is only
  registered in memory, so the report step can find its entry);
* the folder holds the trajectory with the immutable schema, the zones the user
  drew, and the individual report.

Report names: what this flow writes TODAY is ``4_Relatorio_<stem>.{docx,xlsx}``
(the production path ends in ``ReportGenerationCoordinator``, same as the
project). The ``<stem>_report.docx`` / ``<stem>_summary.xlsx`` names quoted in
CLAUDE.md come from ``AnalysisPipelineRunnerMixin``, reachable only through
``VideoProcessingService.process_single_video``, which no production entry point
calls (see ``docs/audits/2026-11_A8_flows.md``). The test pins the names the
flow really produces; changing them is a user-visible change and must be done on
purpose.

What runs for real
------------------
``VideoProcessingCoordinator.start_single_video_processing`` — what
``VIDEO_START_SINGLE_PROCESSING`` and ``AnalysisControlViewModel`` call — with a
real project-less ``ProjectManager``, the real worker loop and the real
completion/report chain. Fakes, as in ``tests/helpers/flow_e2e.py``: the worker
process, the model, the worker's logging setup.

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
    ARENA_POLYGON,
    EXPERIMENT_ID,
    ROI_LEFT,
    TRAJECTORY_COLUMNS,
    write_golden_video,
)
from zebtrack.core.project.project_manager import ProjectManager
from zebtrack.settings import Settings

pytestmark = pytest.mark.integration

STEM = EXPERIMENT_ID


def _run_single_video(root: Path, settings: Settings) -> dict[str, Any]:
    """Run the single-video flow in ``root`` on a fresh, project-less manager."""
    video = root / "input" / f"{STEM}.mp4"
    video.parent.mkdir(parents=True)
    try:
        write_golden_video(video)
    except RuntimeError as exc:  # pragma: no cover - codec-less runner
        pytest.skip(str(exc))

    with pytest.MonkeyPatch.context() as monkeypatch:
        run_worker_in_process(monkeypatch)
        pm = ProjectManager(settings_obj=settings)
        coordinator = build_processing_coordinator(pm, settings)
        coordinator.start_single_video_processing(
            video_path=str(video),
            config={},
            zone_data=make_zone(
                [(int(x), int(y)) for x, y in ARENA_POLYGON],
                [(int(x), int(y)) for x, y in ROI_LEFT],
                "Esquerda",
            ),
        )
        wait_for_processing(coordinator)

    return {"root": root, "video": video, "pm": pm, "results": video.parent / f"{STEM}_results"}


@pytest.fixture(scope="module")
def single_run(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    """The flow once, with zones shaped exactly like the Zones tab saves them."""
    return _run_single_video(tmp_path_factory.mktemp("flow_single_video"), flow_settings())


def test_outputs_land_in_the_stem_results_folder_next_to_the_video(single_run: dict) -> None:
    results: Path = single_run["results"]
    for name in (
        f"1_ProcessingArea_{STEM}.parquet",
        f"2_AreasOfInterest_{STEM}.parquet",
        f"3_CoordMovimento_{STEM}.parquet",
        f"4_Relatorio_{STEM}.docx",
        f"4_Relatorio_{STEM}.xlsx",
    ):
        assert (results / name).is_file(), f"{name} missing in {results}"
    assert sorted(p.name for p in single_run["video"].parent.iterdir()) == sorted(
        [single_run["video"].name, results.name]
    )


def test_no_project_is_created_anywhere(single_run: dict) -> None:
    root: Path = single_run["root"]
    assert list(root.rglob("project_config.json")) == []
    assert list(root.rglob("config_snapshot.yaml")) == []
    assert [p for p in root.rglob("Grupo_*")] == [], "the project layout leaked in"
    pm: ProjectManager = single_run["pm"]
    assert not pm.project_path


def test_trajectory_keeps_the_immutable_schema(single_run: dict) -> None:
    df = pd.read_parquet(single_run["results"] / f"3_CoordMovimento_{STEM}.parquet")
    assert list(df.columns) == TRAJECTORY_COLUMNS
    assert len(df) > 0
    # Raw video pixels, whole arena: the subject walks to x = 500 px.
    assert df["x_center_px"].min() < 200
    assert df["x_center_px"].max() > 400


def test_the_report_uses_the_roi_the_user_drew(single_run: dict) -> None:
    sheet = pd.read_excel(single_run["results"] / f"4_Relatorio_{STEM}.xlsx", sheet_name=0)
    assert "Esquerda" in sheet.to_string(), "the ROI drawn for this video is not in the report"


def test_the_video_is_registered_only_in_memory(single_run: dict) -> None:
    """The report step finds the entry; nothing about it was persisted."""
    pm: ProjectManager = single_run["pm"]
    entry = pm.find_video_entry(path=str(single_run["video"]))
    assert entry is not None
    assert entry.get("metadata", {}).get("group") == "single_video"
    files = entry.get("parquet_files") or {}
    assert (
        Path(files["report_docx"]).resolve()
        == (single_run["results"] / f"4_Relatorio_{STEM}.docx").resolve()
    )


@pytest.mark.xfail(
    strict=True,
    reason=(
        "A8-001: single-aquarium zones are saved in raw video pixels with no source "
        "size, and the worker scales them from camera.desired_width/height; a video "
        "whose resolution differs from the camera reference gets a wrong arena."
    ),
)
def test_arena_is_honoured_when_the_video_is_not_the_camera_size(tmp_path: Path) -> None:
    """Shipped camera reference (1280x720) and a 640x480 video.

    The user drew the arena on THIS video's frame (the canvas converts clicks to
    video pixels), and the report reads it as raw pixels. The worker instead
    treats it as 1280x720 reference coordinates and halves it, so the subject's
    walk to x = 500 px is filtered out as "outside the arena" while the run
    reports success.
    """
    run = _run_single_video(tmp_path, flow_settings(camera_matches_video=False))
    df = pd.read_parquet(run["results"] / f"3_CoordMovimento_{STEM}.parquet")
    assert df["x_center_px"].max() > 400
