"""Tests for ``core.services.zone_autoimport_policy``.

The rule these tests pin down is the one that failed in the field: a
pre-recorded project created over a folder that already contained
``1_ProcessingArea_*`` / ``2_AreasOfInterest_*`` from an earlier study loaded
those polygons on the first double-click, even though the wizard's import had
been declined. Nothing crashed and nothing was logged as wrong — the reports
came out complete, measured against the previous experiment's arena.
"""

from __future__ import annotations

import os

import pytest

from zebtrack.core.services.zone_autoimport_policy import (
    ZoneAutoImport,
    decide_zone_autoimport,
    describe_candidate_origin,
    wizard_import_declined,
)

PROJECT = os.path.join("C:", os.sep, "Experimentos", "Projeto_CEC")
FOREIGN_DIR = os.path.join("D:", os.sep, "Estudo_2025", "CECT_4")
FOREIGN_VIDEO = os.path.join(FOREIGN_DIR, "CECT_4.mp4")
FOREIGN_CANDIDATES = {
    "arena": os.path.join(FOREIGN_DIR, "1_ProcessingArea_CECT_4.parquet"),
    "rois": os.path.join(FOREIGN_DIR, "2_AreasOfInterest_CECT_4.parquet"),
}
SESSION_DIR = os.path.join(PROJECT, "Grupo_CEC", "Dia_01", "Sujeito_S04")
OWNED_CANDIDATES = {
    "arena": os.path.join(SESSION_DIR, "1_ProcessingArea_CECT_4.parquet"),
    "rois": os.path.join(SESSION_DIR, "2_AreasOfInterest_CECT_4.parquet"),
}


def _wizard(video: str, *, arena: bool, rois: bool) -> dict:
    return {
        "_wizard_metadata": {
            "import_config": [
                {"video": video, "import_arena": arena, "import_rois": rois},
            ]
        }
    }


class TestWizardImportDeclined:
    def test_declined_when_both_flags_are_false(self):
        project_data = _wizard(FOREIGN_VIDEO, arena=False, rois=False)
        assert wizard_import_declined(project_data, FOREIGN_VIDEO) is True

    @pytest.mark.parametrize(("arena", "rois"), [(True, False), (False, True), (True, True)])
    def test_not_declined_when_any_asset_was_requested(self, arena, rois):
        decision = wizard_import_declined(
            _wizard(FOREIGN_VIDEO, arena=arena, rois=rois), FOREIGN_VIDEO
        )
        assert decision is False

    def test_absent_record_is_none_not_false(self):
        """ "Never asked" must stay distinguishable from "asked and said yes".

        Collapsing them into one falsy value is how a project with no wizard
        record would be read as consent.
        """
        assert wizard_import_declined({}, FOREIGN_VIDEO) is None
        other = _wizard("other.mp4", arena=False, rois=False)
        assert wizard_import_declined(other, FOREIGN_VIDEO) is None

    def test_matches_across_separator_and_case_differences(self):
        """The wizard writes POSIX paths; video entries write Windows ones."""
        posix_style = FOREIGN_VIDEO.replace(os.sep, "/")
        project_data = _wizard(posix_style, arena=False, rois=False)

        assert wizard_import_declined(project_data, FOREIGN_VIDEO) is True

    def test_malformed_project_data_degrades_to_none(self):
        assert wizard_import_declined(None, FOREIGN_VIDEO) is None
        assert wizard_import_declined({"_wizard_metadata": "junk"}, FOREIGN_VIDEO) is None
        bad_config = {"_wizard_metadata": {"import_config": 7}}
        assert wizard_import_declined(bad_config, FOREIGN_VIDEO) is None
        assert wizard_import_declined({}, "") is None


class TestDecideZoneAutoimport:
    def test_no_candidates_is_skip(self):
        assert (
            decide_zone_autoimport(
                video_path=FOREIGN_VIDEO,
                candidates={},
                project_path=PROJECT,
                project_data={},
            )
            is ZoneAutoImport.SKIP
        )

    def test_parquets_inside_the_project_are_auto(self):
        """The live-recording case the silent import was written for."""
        assert (
            decide_zone_autoimport(
                video_path=os.path.join(SESSION_DIR, "CECT_4.mp4"),
                candidates=OWNED_CANDIDATES,
                project_path=PROJECT,
                project_data={"project_type": "live"},
            )
            is ZoneAutoImport.AUTO
        )

    def test_no_project_keeps_legacy_auto(self):
        """Single-video and ad-hoc live have no wizard and no project to compare."""
        assert (
            decide_zone_autoimport(
                video_path=FOREIGN_VIDEO,
                candidates=FOREIGN_CANDIDATES,
                project_path=None,
                project_data={},
            )
            is ZoneAutoImport.AUTO
        )

    def test_foreign_parquets_after_declined_wizard_are_skipped(self):
        assert (
            decide_zone_autoimport(
                video_path=FOREIGN_VIDEO,
                candidates=FOREIGN_CANDIDATES,
                project_path=PROJECT,
                project_data=_wizard(FOREIGN_VIDEO, arena=False, rois=False),
            )
            is ZoneAutoImport.SKIP
        )

    def test_foreign_parquets_without_a_record_are_asked_about(self):
        assert (
            decide_zone_autoimport(
                video_path=FOREIGN_VIDEO,
                candidates=FOREIGN_CANDIDATES,
                project_path=PROJECT,
                project_data={},
            )
            is ZoneAutoImport.ASK
        )

    def test_partly_foreign_candidates_are_not_treated_as_owned(self):
        """One foreign file is enough: it alone can replace the arena."""
        mixed = {
            "arena": FOREIGN_CANDIDATES["arena"],
            "rois": OWNED_CANDIDATES["rois"],
        }
        assert (
            decide_zone_autoimport(
                video_path=FOREIGN_VIDEO,
                candidates=mixed,
                project_path=PROJECT,
                project_data={},
            )
            is ZoneAutoImport.ASK
        )

    def test_sibling_directory_is_not_inside_the_project(self):
        """``Projeto_CEC_backup`` must not count as being under ``Projeto_CEC``.

        A plain ``startswith`` on the raw string says it does, which would grant
        AUTO to files the project never produced.
        """
        sibling = PROJECT + "_backup"
        candidates = {"arena": os.path.join(sibling, "1_ProcessingArea_x.parquet")}
        assert (
            decide_zone_autoimport(
                video_path=os.path.join(sibling, "x.mp4"),
                candidates=candidates,
                project_path=PROJECT,
                project_data={},
            )
            is ZoneAutoImport.ASK
        )


class TestDescribeCandidateOrigin:
    def test_names_the_folder_the_files_came_from(self):
        assert describe_candidate_origin(FOREIGN_CANDIDATES) == FOREIGN_DIR

    def test_falls_back_to_rois_when_only_rois_exist(self):
        assert describe_candidate_origin({"rois": FOREIGN_CANDIDATES["rois"]}) == FOREIGN_DIR

    def test_empty_without_candidates(self):
        assert describe_candidate_origin({}) == ""
        assert describe_candidate_origin(None) == ""
