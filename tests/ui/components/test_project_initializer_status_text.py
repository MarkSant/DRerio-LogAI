"""Status-bar label of the main control frame.

``create_main_control_frame`` serves two flows — opening a project, and the
single-video analysis launched from the welcome screen. Only the first has a
project, so the label has to distinguish them instead of formatting a project
name that does not exist.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from zebtrack.ui.components.project_initializer import build_main_frame_status_text


def _pm(*, project_path, project_type=None, name="N/A"):
    return SimpleNamespace(
        project_path=project_path,
        get_project_type=lambda: project_type,
        get_project_name=lambda: name,
    )


def test_single_video_flow_names_the_mode_not_a_missing_project():
    """No project loaded: the bar used to read "Project: N/A (None)".

    Both placeholders came from sentinels — ``get_project_name`` returns "N/A"
    and ``get_project_type`` returns None when nothing is open — so the bar
    announced a broken project to a user who never opened one.
    """
    text = build_main_frame_status_text(_pm(project_path=None))

    assert text == "Single-video analysis (no project)"
    assert "N/A" not in text
    assert "None" not in text


def test_prerecorded_project_keeps_its_label():
    text = build_main_frame_status_text(
        _pm(project_path="C:/proj", project_type="pre-recorded", name="Estudo CBD")
    )

    assert text == "Project: Estudo CBD (Pre-recorded)"


def test_live_project_keeps_its_label():
    text = build_main_frame_status_text(
        _pm(project_path="C:/proj", project_type="live", name="Sessao 1")
    )

    assert text == "Project: Sessao 1 (Live)"


@pytest.mark.parametrize("project_path", ["", None, 0])
def test_any_falsy_project_path_means_single_video(project_path):
    """``project_path`` is the same signal save_project/register_outputs gate on."""
    assert (
        build_main_frame_status_text(
            _pm(project_path=project_path, project_type="pre-recorded", name="X")
        )
        == "Single-video analysis (no project)"
    )


def test_unknown_project_type_still_reports_the_project():
    """An unrecognised type is shown verbatim rather than swallowing the project."""
    text = build_main_frame_status_text(
        _pm(project_path="C:/proj", project_type="legacy-batch", name="Antigo")
    )

    assert text == "Project: Antigo (legacy-batch)"
