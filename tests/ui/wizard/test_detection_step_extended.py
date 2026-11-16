"""Extended unit tests for ui/wizard/detection_step.py."""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar
from unittest.mock import MagicMock

from zebtrack.ui.wizard.detection_step import DetectionStep, _method_labels


class TestDetectionStepExtended:
    def test_method_labels(self):
        labels = _method_labels()
        assert "seg" in labels
        assert "det" in labels
        assert "Segmentation" in labels["seg"]
        assert "Detection" in labels["det"]

    def test_ensure_group_display_names(self):
        step = object.__new__(DetectionStep)
        step.detected_design = {
            "groups": ["Control", "Treated"],
            "group_display_names": {"Control": "Control Group"},
        }
        step._ensure_group_display_names()
        assert step.detected_design["group_display_names"]["Control"] == "Control Group"
        assert step.detected_design["group_display_names"]["Treated"] == "Treated"

    def test_pattern_groups_as_folders(self):
        step = object.__new__(DetectionStep)
        paths = [
            Path("/root/Control/video1.mp4"),
            Path("/root/Control/video2.mp4"),
            Path("/root/Treated/video1.mp4"),
            Path("/root/Treated/video2.mp4"),
        ]
        result = step._pattern_groups_as_folders(paths)
        assert result is not None
        assert "Control" in result["groups"]
        assert "Treated" in result["groups"]
        assert result["confidence"] > 0.5
        assert result["pattern_used"] == "groups_as_folders"

    def test_pattern_filename_based(self):
        step = object.__new__(DetectionStep)
        paths = [
            Path("/videos/Control_D1_S1.mp4"),
            Path("/videos/Control_D1_S2.mp4"),
            Path("/videos/Treated_D1_S1.mp4"),
            Path("/videos/Treated_D1_S2.mp4"),
        ]
        result = step._pattern_filename_based(paths)
        if result is not None:
            assert "groups" in result
            assert result["confidence"] > 0.0


class TestDetectionStepExtended2:
    def test_run_detection_empty_video_paths(self):
        step = object.__new__(DetectionStep)
        step.custom_regex_patterns = None
        step.status_var = MagicMock()
        step.wizard_data = {"video_paths": []}
        step.scanned_videos = []
        step.detected_design = None
        step.results_text = MagicMock()

        # Running detection with empty paths sets error status
        step._run_detection()
        step.status_var.set.assert_called_with("Error!")
        step.results_text.delete.assert_called_once_with("1.0", "end")

    def test_pattern_custom_regex_no_group_pattern(self):
        step = object.__new__(DetectionStep)
        res = step._pattern_custom_regex([Path("test.mp4")], {})
        assert res is None

    def test_extract_match_data(self):
        step = object.__new__(DetectionStep)
        d = {"group": "Control", "day": "2", "subject": "S1"}
        extracted = step._extract_match_data(d)
        assert extracted["group"] == "Control"
        assert extracted["day"] == "Day02"
        assert extracted["subject"] == "S1"

    def test_update_detected_sets(self):
        step = object.__new__(DetectionStep)
        groups: set[str] = set()
        days: set[str] = set()
        subjects: dict[str, set[str]] = {}

        data = {"group": "Treated", "day": "Day03", "subject": "S5"}
        step._update_detected_sets(data, groups, days, subjects)

        assert "Treated" in groups
        assert "Day03" in days
        assert "S5" in subjects["Treated"]


class TestIndividualPatternsFollowTheImportRule:
    """F2-UI-003 / F2-UI-009: same case and same value rule as the project import."""

    PATTERNS: ClassVar[dict[str, str]] = {
        "group_pattern": r"(Controle|Tratamento)",
        "day_pattern": r"Dia_(\d+)|D(\d+)",
        "subject_pattern": r"CECT_(\d+)",
    }

    def _run(self, name: str):
        step = object.__new__(DetectionStep)
        groups: set[str] = set()
        days: set[str] = set()
        subjects: dict[str, set[str]] = {}
        results = step._process_path_with_individual_patterns(
            name, self.PATTERNS, groups, days, subjects
        )
        return results, groups, days, subjects

    def test_a_name_in_another_case_is_detected(self):
        results, groups, days, subjects = self._run("controle_cect_4_dia_2.mp4")

        assert results == [{"group": "controle", "day": "Day02", "subject": "S04"}]
        assert groups == {"controle"}
        assert days == {"Day02"}
        assert subjects == {"controle": {"S04"}}

    def test_an_alternation_of_groups_uses_the_group_that_matched(self):
        results, _groups, days, _subjects = self._run("Tratamento_CECT_7_D3.mp4")

        assert results == [{"group": "Tratamento", "day": "Day03", "subject": "S07"}]
        assert days == {"Day03"}

    def test_every_subject_of_a_multi_subject_name_is_listed_whatever_its_case(self):
        results, _groups, _days, subjects = self._run("Controle_Dia_1_CECT_1--cect_2.mp4")

        assert [r["subject"] for r in results or []] == ["S01", "S02"]
        assert subjects == {"Controle": {"S01", "S02"}}

    def test_a_name_without_a_day_keeps_the_group_with_an_empty_day(self):
        results, groups, days, _subjects = self._run("Controle_CECT_4.mp4")

        assert results == [{"group": "Controle", "day": "", "subject": "S04"}]
        assert groups == {"Controle"}
        assert days == set()

    def test_a_name_without_the_group_is_not_recognised(self):
        results, groups, days, subjects = self._run("video_Dia_2.mp4")

        assert results is None
        assert (groups, days, subjects) == (set(), set(), {})
