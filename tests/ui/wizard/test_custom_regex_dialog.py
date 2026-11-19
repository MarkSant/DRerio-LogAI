"""Tests for the custom regex dialog (group / day / subject from file names).

Part one drives the pure functions the dialog is built on with realistic file
names and asserts the exact group, day and subject they extract. Part two builds
the real dialog and drives its handlers.

The preview deliberately mirrors what the wizard's detection step does with the
same patterns (``re.search``/``finditer``, group 1 when the pattern has groups,
else the whole match), so these tests also pin that rule.
"""

from __future__ import annotations

import re
import tkinter as tk
from typing import Any
from unittest.mock import patch

import pytest

from zebtrack.ui.wizard import custom_regex_dialog as regex_module
from zebtrack.ui.wizard.custom_regex_dialog import (
    CustomRegexDialog,
    compile_patterns,
    evaluate_path,
    match_path_rows,
)

GROUP = r"(Controle|Tratamento)"
DAY = r"Dia[_ ](\d+)"
SUBJECT = r"CECT_(\d+)"


def _compile(**patterns: str) -> tuple[dict[str, re.Pattern[str]], dict[str, str]]:
    return compile_patterns(patterns)


class TestCompilePatterns:
    def test_blank_patterns_are_left_out_and_others_are_stripped(self):
        compiled, errors = compile_patterns({"group": "  (A|B) ", "day": "   ", "subject": ""})

        assert list(compiled) == ["group"]
        assert compiled["group"].pattern == "(A|B)"
        assert errors == {}

    def test_compiled_patterns_ignore_case_like_the_project_import(self):
        compiled, _errors = compile_patterns({"day": r"Dia_(\d+)"})

        assert compiled["day"].flags & re.IGNORECASE

    def test_an_invalid_pattern_is_reported_under_its_own_key(self):
        compiled, errors = compile_patterns({"group": "(", "day": r"D(\d+)"})

        assert list(compiled) == ["day"]
        assert list(errors) == ["group"]
        assert "unterminated subpattern" in errors["group"]


class TestMatchPathRows:
    def test_rows_match_ignoring_case_and_use_the_group_that_took_part(self):
        compiled, errors = _compile(group=GROUP, day=r"Dia_(\d+)|D(\d+)", subject=SUBJECT)

        rows = match_path_rows("controle_cect_4_d3.mp4", compiled, errors)

        assert rows == [
            {"path": "controle_cect_4_d3.mp4", "group": "controle", "day": "3", "subject": "4"}
        ]

    def test_every_match_of_a_multi_subject_name_is_a_row_whatever_its_case(self):
        compiled, errors = _compile(subject=r"S(\d+)")

        rows = match_path_rows("g1_d1_s1--g1_d1_S2.mp4", compiled, errors)

        assert [row["subject"] for row in rows] == ["1", "2"]

    def test_one_name_gives_one_row_with_group_day_and_subject(self):
        compiled, errors = _compile(group=GROUP, day=DAY, subject=SUBJECT)

        rows = match_path_rows("Controle_CECT_4_Dia_2.mp4", compiled, errors)

        assert rows == [
            {
                "path": "Controle_CECT_4_Dia_2.mp4",
                "group": "Controle",
                "day": "2",
                "subject": "4",
            }
        ]

    def test_spaces_and_accents_in_the_name_are_matched_and_kept(self):
        compiled, errors = _compile(group=r"Grupo (\w+)", day=r"Dia (\d+)", subject=r"Rato (\d+)")

        rows = match_path_rows("Grupo Ação/Dia 3/Rato 07.mp4", compiled, errors)

        assert len(rows) == 1
        assert (rows[0]["group"], rows[0]["day"], rows[0]["subject"]) == ("Ação", "3", "07")

    def test_a_name_that_matches_nothing_shows_dashes(self):
        compiled, errors = _compile(group=GROUP, day=DAY, subject=SUBJECT)

        rows = match_path_rows("video.mp4", compiled, errors)

        assert rows == [{"path": "video.mp4", "group": "-", "day": "-", "subject": "-"}]

    def test_a_pattern_that_is_not_defined_shows_a_dash(self):
        compiled, errors = _compile(subject=SUBJECT)

        rows = match_path_rows("Controle_CECT_4_Dia_2.mp4", compiled, errors)

        assert (rows[0]["group"], rows[0]["day"], rows[0]["subject"]) == ("-", "-", "4")

    def test_an_invalid_pattern_shows_error_in_its_column_only(self):
        compiled, errors = _compile(group="(", subject=SUBJECT)

        rows = match_path_rows("Controle_CECT_4_Dia_2.mp4", compiled, errors)

        assert (rows[0]["group"], rows[0]["day"], rows[0]["subject"]) == ("Error", "-", "4")

    def test_two_subjects_in_one_name_give_one_row_each_and_the_group_repeats(self):
        compiled, errors = _compile(group=r"G(\d+)", day=r"D(\d+)", subject=r"S(\d+)")

        rows = match_path_rows("G1_D1_S1--G2_D1_S2.mp4", compiled, errors)

        assert rows == [
            {
                "path": "G1_D1_S1--G2_D1_S2.mp4 (match 1)",
                "group": "1",
                "day": "1",
                "subject": "1",
            },
            {"path": "  └─ (match 2)", "group": "2", "day": "1", "subject": "2"},
        ]

    def test_a_field_with_fewer_matches_is_padded_with_dashes(self):
        compiled, errors = _compile(group=r"G(\d+)", subject=r"S(\d+)")

        rows = match_path_rows("G1_S1_S2_S3.mp4", compiled, errors)

        assert [(r["group"], r["subject"]) for r in rows] == [("1", "1"), ("-", "2"), ("-", "3")]

    def test_a_pattern_without_a_group_yields_the_whole_match(self):
        compiled, errors = _compile(group=r"Control|Treatment")

        rows = match_path_rows("Video_Treatment_Day1.mp4", compiled, errors)

        assert rows[0]["group"] == "Treatment"

    def test_a_path_of_65_characters_is_shown_whole(self):
        path = "a" * 61 + ".mp4"
        assert len(path) == 65

        rows = match_path_rows(path, {}, {})

        assert rows[0]["path"] == path

    def test_a_longer_path_keeps_the_last_64_characters_after_an_ellipsis(self):
        path = "x" + "a" * 61 + ".mp4"
        assert len(path) == 66

        rows = match_path_rows(path, {}, {})

        assert rows[0]["path"] == "…" + path[-64:]
        assert len(rows[0]["path"]) == 65


class TestEvaluatePath:
    @staticmethod
    def _eval(path: str, **patterns: str) -> dict[str, str]:
        compiled, errors = compile_patterns(patterns)
        return evaluate_path(
            path,
            {"group": "", "day": "", "subject": "", **patterns},
            compiled,
            errors,
        )

    def test_each_defined_field_reports_what_it_found(self):
        result = self._eval("Controle_CECT_4_Dia_2.mp4", group=GROUP, day=DAY, subject=SUBJECT)

        assert result == {
            "group": "✓ Group: 'Controle'",
            "day": "✓ Day: '2'",
            "subject": "✓ Subject: '4'",
            "summary": "",
        }

    def test_a_field_without_a_pattern_says_so(self):
        result = self._eval("Controle_CECT_4_Dia_2.mp4", subject=SUBJECT)

        assert result["group"] == "○ Group: pattern not defined"
        assert result["day"] == "○ Day: pattern not defined"
        assert result["subject"] == "✓ Subject: '4'"

    def test_a_pattern_that_finds_nothing_says_no_match(self):
        result = self._eval("video.mp4", day=DAY)

        assert result["day"] == "✗ Day: no match"

    def test_the_search_ignores_case_like_the_project_import(self):
        result = self._eval("controle_cect_4_dia_2.mp4", group=GROUP, day=DAY, subject=SUBJECT)

        assert result["group"] == "✓ Group: 'controle'"
        assert result["day"] == "✓ Day: '2'"
        assert result["subject"] == "✓ Subject: '4'"

    def test_an_alternation_of_groups_shows_the_group_that_matched(self):
        result = self._eval("D3.mp4", day=r"Dia_(\d+)|D(\d+)")

        assert result["day"] == "✓ Day: '3'"

    def test_the_pattern_may_match_anywhere_in_a_folder_path(self):
        result = self._eval("D:/exp/Tratamento/Dia 3/CECT_9.mp4", group=GROUP, day=DAY)

        assert result["group"] == "✓ Group: 'Tratamento'"
        assert result["day"] == "✓ Day: '3'"

    def test_an_empty_path_asks_for_one_and_fills_every_field(self):
        result = self._eval("", group=GROUP)

        assert result["summary"] == "✗ Enter a path to test"
        assert result["group"] == "✗ Group: enter a path"
        assert result["day"] == "○ Day: pattern not defined"

    def test_a_recorded_compile_error_is_shown_for_that_field(self):
        compiled, errors = compile_patterns({"group": "("})

        result = evaluate_path("x.mp4", {"group": "(", "day": "", "subject": ""}, compiled, errors)

        assert result["group"].startswith("✗ Group: invalid regex - ")
        assert "unterminated subpattern" in result["group"]

    def test_a_pattern_not_compiled_yet_is_compiled_on_the_fly(self):
        result = evaluate_path("Dia_2.mp4", {"group": "", "day": DAY, "subject": ""}, {}, {})

        assert result["day"] == "✓ Day: '2'"

    def test_a_pattern_not_compiled_yet_is_also_case_insensitive(self):
        result = evaluate_path("dia_2.mp4", {"group": "", "day": DAY, "subject": ""}, {}, {})

        assert result["day"] == "✓ Day: '2'"

    def test_a_pattern_not_compiled_yet_and_invalid_reports_the_error(self):
        result = evaluate_path("x.mp4", {"group": "", "day": "(", "subject": ""}, {}, {})

        assert result["day"].startswith("✗ Day: invalid regex - ")


# --------------------------------------------------------------------------
# The real dialog
# --------------------------------------------------------------------------


def _walk(widget: tk.Misc) -> list[tk.Misc]:
    found: list[tk.Misc] = []
    for child in widget.winfo_children():
        found.append(child)
        found.extend(_walk(child))
    return found


def _buttons(dialog: tk.Misc, text: str) -> list[tk.Button]:
    return [w for w in _walk(dialog) if isinstance(w, tk.Button) and str(w.cget("text")) == text]


def _build(
    root: tk.Misc,
    patterns: dict | None = None,
    sample_paths: list[str] | None = None,
) -> CustomRegexDialog:
    with patch.object(CustomRegexDialog, "wait_window"):
        return CustomRegexDialog(root, patterns, sample_paths=sample_paths)


def _type(entry: tk.Entry, text: str) -> None:
    entry.delete(0, "end")
    entry.insert(0, text)


def _rows(dialog: CustomRegexDialog) -> list[tuple[str, str, str, str]]:
    """Preview rows as (path, group, day, subject) strings."""
    tree = dialog.preview_tree
    return [
        (
            str(tree.set(iid, "path")),
            str(tree.set(iid, "group")),
            str(tree.set(iid, "day")),
            str(tree.set(iid, "subject")),
        )
        for iid in tree.get_children()
    ]


class _MessageBoxes:
    def __init__(self) -> None:
        self.warnings: list[tuple[str, str]] = []
        self.errors: list[tuple[str, str]] = []

    def showwarning(self, title: str, message: str, **_kw: Any) -> None:
        self.warnings.append((title, message))

    def showerror(self, title: str, message: str, **_kw: Any) -> None:
        self.errors.append((title, message))


@pytest.fixture
def boxes(monkeypatch: pytest.MonkeyPatch) -> _MessageBoxes:
    recorder = _MessageBoxes()
    monkeypatch.setattr(regex_module.messagebox, "showwarning", recorder.showwarning)
    monkeypatch.setattr(regex_module.messagebox, "showerror", recorder.showerror)
    return recorder


@pytest.mark.gui
class TestInitialState:
    def test_current_patterns_are_loaded_into_the_fields(self, tkinter_root):
        dialog = _build(
            tkinter_root,
            {"group_pattern": GROUP, "day_pattern": DAY, "subject_pattern": None},
        )

        assert dialog.group_pattern_entry.get() == GROUP
        assert dialog.day_pattern_entry.get() == DAY
        assert dialog.subject_pattern_entry.get() == ""

    def test_the_first_sample_path_is_the_test_path(self, tkinter_root):
        dialog = _build(tkinter_root, None, ["a/Controle_CECT_4_Dia_2.mp4", "b.mp4"])

        assert dialog.test_path_entry.get() == "a/Controle_CECT_4_Dia_2.mp4"

    def test_without_samples_a_default_example_is_used_and_the_preview_asks_for_videos(
        self, tkinter_root
    ):
        dialog = _build(tkinter_root)
        dialog._refresh_live_previews()

        assert dialog.test_path_entry.get() == "/Control/Day01/Subject_S01.mp4"
        assert _rows(dialog) == [("Add videos in the previous step", "-", "-", "-")]

    def test_at_most_fifty_samples_are_kept(self, tkinter_root):
        dialog = _build(tkinter_root, None, [f"v{i}.mp4" for i in range(80)])

        assert len(dialog.sample_paths) == 50


@pytest.mark.gui
class TestLivePreview:
    def test_the_tree_shows_what_each_sample_yields(self, tkinter_root):
        samples = ["Controle_CECT_4_Dia_2.mp4", "Tratamento_CECT_5_Dia_3.mp4", "outro.mp4"]
        dialog = _build(
            tkinter_root,
            {"group_pattern": GROUP, "day_pattern": DAY, "subject_pattern": SUBJECT},
            samples,
        )

        dialog._refresh_live_previews()

        assert _rows(dialog) == [
            ("Controle_CECT_4_Dia_2.mp4", "Controle", "2", "4"),
            ("Tratamento_CECT_5_Dia_3.mp4", "Tratamento", "3", "5"),
            ("outro.mp4", "-", "-", "-"),
        ]

    def test_editing_a_field_changes_the_preview_after_the_refresh(self, tkinter_root):
        dialog = _build(tkinter_root, None, ["Controle_CECT_4_Dia_2.mp4"])
        dialog._refresh_live_previews()
        assert _rows(dialog)[0][1:] == ("-", "-", "-")

        _type(dialog.subject_pattern_entry, SUBJECT)
        dialog._refresh_live_previews()

        assert _rows(dialog)[0][1:] == ("-", "-", "4")

    def test_typing_schedules_one_refresh_and_replaces_a_pending_one(self, tkinter_root):
        dialog = _build(tkinter_root, None, ["a.mp4"])
        scheduled: list[tuple[int, Any]] = []
        cancelled: list[str] = []

        def fake_after(delay: int, func: Any = None, *_a: Any) -> str:
            scheduled.append((delay, func))
            return f"job{len(scheduled)}"

        dialog.after = fake_after  # type: ignore[method-assign, assignment]
        dialog.after_cancel = cancelled.append  # type: ignore[method-assign, assignment]
        dialog._live_update_job = None

        dialog.group_pattern_var.set("A")
        dialog.group_pattern_var.set("AB")

        assert scheduled == [(150, dialog._refresh_live_previews)] * 2
        assert cancelled == ["job1"]

    def test_only_fifteen_paths_are_listed_and_the_rest_is_counted(self, tkinter_root):
        samples = [f"Controle_CECT_{i}_Dia_1.mp4" for i in range(17)]
        dialog = _build(tkinter_root, {"subject_pattern": SUBJECT}, samples)

        dialog._refresh_live_previews()

        rows = _rows(dialog)
        assert len(rows) == 16
        assert rows[14][3] == "14"
        assert rows[15][0] == "… 2 additional paths"

    def test_a_single_extra_path_uses_the_singular(self, tkinter_root):
        dialog = _build(tkinter_root, None, [f"v{i}.mp4" for i in range(16)])

        dialog._refresh_live_previews()

        assert _rows(dialog)[-1][0] == "… 1 additional path"

    def test_a_multi_subject_name_lists_one_row_per_subject(self, tkinter_root):
        dialog = _build(
            tkinter_root,
            {"group_pattern": r"G(\d+)", "subject_pattern": r"S(\d+)"},
            ["G1_D1_S1--G1_D1_S2.mp4"],
        )

        dialog._refresh_live_previews()

        assert _rows(dialog) == [
            ("G1_D1_S1--G1_D1_S2.mp4 (match 1)", "1", "-", "1"),
            ("  └─ (match 2)", "1", "-", "2"),
        ]

    def test_an_invalid_pattern_shows_error_in_the_tree_and_in_the_test_panel(self, tkinter_root):
        dialog = _build(tkinter_root, {"group_pattern": "("}, ["a.mp4"])

        dialog._refresh_live_previews()

        assert _rows(dialog)[0][1] == "Error"
        assert dialog._test_result_vars["group"].get().startswith("✗ Group: invalid regex - ")


@pytest.mark.gui
class TestTestPanel:
    def test_the_test_button_evaluates_the_typed_path(self, tkinter_root):
        dialog = _build(tkinter_root, {"group_pattern": GROUP, "day_pattern": DAY})
        _type(dialog.test_path_entry, "Controle_CECT_4_Dia_2.mp4")

        _buttons(dialog, "Test")[0].invoke()
        dialog._refresh_live_previews()

        assert dialog._test_result_vars["group"].get() == "✓ Group: 'Controle'"
        assert dialog._test_result_vars["day"].get() == "✓ Day: '2'"
        assert dialog._test_result_vars["subject"].get() == "○ Subject: pattern not defined"

    def test_testing_an_empty_path_warns_and_does_not_refresh(self, tkinter_root, boxes):
        dialog = _build(tkinter_root, {"group_pattern": GROUP})
        _type(dialog.test_path_entry, "   ")
        dialog._live_update_job = None

        _buttons(dialog, "Test")[0].invoke()

        assert boxes.warnings == [("Empty Path", "Enter a path to test.")]
        assert dialog._live_update_job is None

    def test_the_panel_starts_as_waiting_until_the_first_refresh(self, tkinter_root):
        # The first refresh is an after(0) timer. Whether it fires inside
        # __init__ depends on the window system (Dialog's wait_visibility spins
        # the event loop under Xvfb, not on Windows), so it is held here and
        # run explicitly: the assertion is about the state BEFORE it.
        with patch.object(CustomRegexDialog, "_refresh_live_previews", lambda self: None):
            dialog = _build(tkinter_root)

        assert dialog._test_result_vars["group"].get() == "○ Group: waiting"
        assert dialog._test_result_vars["day"].get() == "○ Day: waiting"
        assert dialog._test_result_vars["subject"].get() == "○ Subject: waiting"

        dialog._refresh_live_previews()

        assert dialog._test_result_vars["group"].get() == "○ Group: pattern not defined"


@pytest.mark.gui
class TestExamples:
    @pytest.mark.parametrize(
        ("index", "field", "pattern"),
        [
            (0, "group", r"(Control|Treatment)"),
            (1, "day", r"Day(\d+)"),
            (2, "subject", r"S(\d+)"),
            (3, "group", r"(\w+)"),
        ],
    )
    def test_use_copies_the_example_into_its_field_only(self, tkinter_root, index, field, pattern):
        dialog = _build(tkinter_root)

        _buttons(dialog, "Use")[index].invoke()

        entries = {
            "group": dialog.group_pattern_entry,
            "day": dialog.day_pattern_entry,
            "subject": dialog.subject_pattern_entry,
        }
        assert entries[field].get() == pattern
        assert [e.get() for k, e in entries.items() if k != field] == ["", ""]

    def test_an_example_pattern_drives_the_preview(self, tkinter_root):
        dialog = _build(tkinter_root, None, ["Video_Treatment_Day1.mp4"])

        _buttons(dialog, "Use")[0].invoke()
        dialog._refresh_live_previews()

        assert _rows(dialog)[0][1] == "Treatment"


@pytest.mark.gui
class TestClearAll:
    def test_clear_all_empties_the_patterns_and_restores_the_default_test_path(self, tkinter_root):
        dialog = _build(
            tkinter_root,
            {"group_pattern": GROUP, "day_pattern": DAY, "subject_pattern": SUBJECT},
            ["first.mp4", "second.mp4"],
        )
        _type(dialog.test_path_entry, "typed.mp4")

        _buttons(dialog, "Clear All")[0].invoke()
        dialog._refresh_live_previews()

        assert dialog.group_pattern_entry.get() == ""
        assert dialog.day_pattern_entry.get() == ""
        assert dialog.subject_pattern_entry.get() == ""
        assert dialog.test_path_entry.get() == "first.mp4"
        assert dialog._test_result_vars["group"].get() == "○ Group: pattern not defined"


@pytest.mark.gui
class TestSaving:
    def test_ok_returns_the_trimmed_patterns_and_none_for_blank_ones(self, tkinter_root):
        dialog = _build(tkinter_root)
        _type(dialog.group_pattern_entry, f"  {GROUP}  ")
        _type(dialog.day_pattern_entry, "   ")
        _type(dialog.subject_pattern_entry, SUBJECT)

        _buttons(dialog, "Save")[0].invoke()

        assert dialog.get_result() == {
            "group_pattern": GROUP,
            "day_pattern": None,
            "subject_pattern": SUBJECT,
        }
        assert not dialog.winfo_exists()

    def test_cancel_returns_nothing(self, tkinter_root):
        dialog = _build(tkinter_root, {"group_pattern": GROUP})

        _buttons(dialog, "Cancel")[0].invoke()

        assert dialog.get_result() is None
        assert not dialog.winfo_exists()

    def test_an_invalid_pattern_blocks_saving_and_names_the_field_and_the_error(
        self, tkinter_root, boxes
    ):
        dialog = _build(tkinter_root)
        _type(dialog.day_pattern_entry, "Dia_(")

        _buttons(dialog, "Save")[0].invoke()

        assert dialog.winfo_exists()
        assert dialog.get_result() is None
        assert len(boxes.errors) == 1
        title, message = boxes.errors[0]
        assert title == "Invalid Regex"
        assert message.startswith("Invalid Day pattern:\nDia_(\n\nError: ")
        assert "unterminated subpattern" in message

    def test_validation_reports_the_first_invalid_field_in_group_day_subject_order(
        self, tkinter_root, boxes
    ):
        dialog = _build(tkinter_root)
        _type(dialog.subject_pattern_entry, "S(")
        _type(dialog.group_pattern_entry, "G(")

        assert dialog.validate() is False

        assert boxes.errors[0][1].startswith("Invalid Group pattern:\nG(")

    def test_all_blank_patterns_are_valid_and_save_as_none(self, tkinter_root):
        dialog = _build(tkinter_root)

        assert dialog.validate() is True
        dialog.apply()

        assert dialog.get_result() == {
            "group_pattern": None,
            "day_pattern": None,
            "subject_pattern": None,
        }


@pytest.mark.gui
class TestGeometry:
    """The dialog sizes itself from an idle callback (it already ran during __init__).

    Each test resets the "done" flag so it drives the real method and reads back
    the size bounds Tk ended up with.
    """

    def test_the_window_gets_resize_bounds_around_800_by_780(self, tkinter_root):
        dialog = _build(tkinter_root)
        dialog._geometry_initialized = False

        dialog._initialize_geometry()

        assert dialog._geometry_initialized is True
        assert dialog.minsize() == (680, 585)
        max_w, max_h = dialog.maxsize()
        assert max_w == 1000
        assert max_h <= 897

    def test_geometry_is_initialised_once(self, tkinter_root):
        dialog = _build(tkinter_root)
        dialog._geometry_initialized = False
        dialog._initialize_geometry()
        dialog.minsize(300, 300)

        dialog._initialize_geometry()

        assert dialog.minsize() == (300, 300)

    def test_when_the_window_cannot_be_made_resizable_nothing_is_resized_and_nothing_is_raised(
        self, tkinter_root
    ):
        """Pins what the user sees: the dialog keeps the default geometry (A5: line 576)."""
        dialog = _build(tkinter_root)
        dialog._geometry_initialized = False
        dialog.minsize(300, 300)

        def refuse(*_args: Any) -> None:
            raise tk.TclError("bad window path name")

        dialog.resizable = refuse  # type: ignore[method-assign, assignment]
        dialog._initialize_geometry()

        assert dialog._geometry_initialized is False
        assert dialog.minsize() == (300, 300)

    def test_a_window_manager_that_refuses_resizing_still_gets_the_full_dialog(self, tkinter_root):
        """F2 pragma review: ``resizable`` failing in ``body`` must not abort the build."""

        def refuse(*_args: Any) -> None:
            raise tk.TclError("bad window path name")

        with patch.object(CustomRegexDialog, "resizable", refuse):
            dialog = _build(tkinter_root, {"group_pattern": GROUP}, ["a/Controle_CECT_4_Dia_2.mp4"])

        assert dialog.group_pattern_entry.get() == GROUP
        assert dialog.test_path_entry.get() == "a/Controle_CECT_4_Dia_2.mp4"
        assert _buttons(dialog, "Test")
