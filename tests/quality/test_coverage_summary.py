"""Tests for ``scripts/coverage_summary.py``, the per-package coverage floor.

The global ``--cov-fail-under`` gate cannot see one package eroding, so CI also
pins a floor on ``plugins`` and ``utils``. These tests check what the script
DECIDES from a Cobertura report: which files belong to which package, how the
percentages are derived, and when a floor passes, fails, or cannot be trusted.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import coverage_summary  # noqa: E402
from coverage_summary import Counts  # noqa: E402

pytestmark = pytest.mark.unit


def _class(filename: str, hits: list[int], branches: dict[int, str] | None = None) -> str:
    """One Cobertura ``<class>``: line N has ``hits[N-1]`` hits."""
    branches = branches or {}
    lines = []
    for number, count in enumerate(hits, start=1):
        if number in branches:
            lines.append(
                f'<line number="{number}" hits="{count}" branch="true" '
                f'condition-coverage="{branches[number]}"/>'
            )
        else:
            lines.append(f'<line number="{number}" hits="{count}"/>')
    return f'<class filename="{filename}"><lines>{"".join(lines)}</lines></class>'


def _write_report(tmp_path: Path, *classes: str) -> str:
    path = tmp_path / "coverage.xml"
    path.write_text(
        '<?xml version="1.0" ?><coverage><packages><package name="x"><classes>'
        + "".join(classes)
        + "</classes></package></packages></coverage>",
        encoding="utf-8",
    )
    return str(path)


@pytest.fixture
def report(tmp_path: Path) -> str:
    """plugins 3/4, utils 1/4, core.detection 2/2, core.services 0/2, top level 1/1."""
    return _write_report(
        tmp_path,
        _class("plugins/base.py", [1, 1]),
        _class("plugins/openvino_detector.py", [3, 0], {1: "50% (1/2)"}),
        _class("utils/cache.py", [1, 0, 0, 0]),
        _class("core/detection/class_roles.py", [1, 1], {2: "100% (4/4)"}),
        _class("core/services/mask_capture.py", [0, 0]),
        _class("settings.py", [1]),
    )


class TestPathHandling:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("plugins/base.py", "plugins/base.py"),
            ("src/zebtrack/plugins/base.py", "plugins/base.py"),
            ("src\\zebtrack\\core\\detection\\zones.py", "core/detection/zones.py"),
            ("C:/repo/src/zebtrack/settings.py", "settings.py"),
            # A directory that merely shares the package's name must not truncate twice.
            ("zebtrack/src/zebtrack/utils/cache.py", "utils/cache.py"),
        ],
    )
    def test_filenames_are_made_relative_to_the_package(self, raw: str, expected: str) -> None:
        assert coverage_summary.normalize_filename(raw) == expected

    @pytest.mark.parametrize(
        ("filename", "package"),
        [
            ("settings.py", "."),
            ("plugins/base.py", "plugins"),
            ("core/detection/zones.py", "core.detection"),
        ],
    )
    def test_package_is_the_dotted_parent(self, filename: str, package: str) -> None:
        assert coverage_summary.package_of(filename) == package


class TestCounts:
    def test_rates_come_from_the_tallies(self) -> None:
        counts = Counts(statements=8, covered=6, branches=4, branches_covered=1)
        assert counts.missed == 2
        assert counts.line_rate == pytest.approx(75.0)
        assert counts.branch_rate == pytest.approx(25.0)

    def test_an_empty_aggregate_is_not_a_zero_percent_failure(self) -> None:
        assert Counts().line_rate == 100.0

    def test_branch_rate_is_absent_when_no_branch_was_measured(self) -> None:
        assert Counts(statements=3, covered=3).branch_rate is None


class TestReading:
    def test_a_line_counts_as_covered_only_with_hits(self, report: str) -> None:
        files = coverage_summary.read_file_counts(report)
        cache = files["utils/cache.py"]
        assert (cache.statements, cache.covered) == (4, 1)

    def test_branch_counts_are_read_from_condition_coverage(self, report: str) -> None:
        files = coverage_summary.read_file_counts(report)
        openvino = files["plugins/openvino_detector.py"]
        assert (openvino.branches, openvino.branches_covered) == (2, 1)
        assert files["plugins/base.py"].branches == 0

    def test_packages_do_not_absorb_their_subpackages(self, report: str) -> None:
        packages = coverage_summary.aggregate_by_package(coverage_summary.read_file_counts(report))
        assert set(packages) == {".", "plugins", "utils", "core.detection", "core.services"}
        assert (packages["plugins"].statements, packages["plugins"].covered) == (4, 3)

    def test_a_prefix_sums_every_subpackage(self, report: str) -> None:
        files = coverage_summary.read_file_counts(report)
        core = coverage_summary.aggregate_prefix(files, "core")
        assert core is not None
        assert (core.statements, core.covered) == (4, 2)

    def test_a_prefix_does_not_match_a_longer_sibling_name(self, tmp_path: Path) -> None:
        # "core" must not swallow "coreutils": the match is on a dotted boundary.
        files = coverage_summary.read_file_counts(
            _write_report(tmp_path, _class("core/a.py", [1]), _class("coreutils/b.py", [0, 0]))
        )
        core = coverage_summary.aggregate_prefix(files, "core")
        assert core is not None
        assert (core.statements, core.covered) == (1, 1)

    def test_the_root_package_is_only_the_top_level_files(self, report: str) -> None:
        files = coverage_summary.read_file_counts(report)
        root = coverage_summary.aggregate_prefix(files, ".")
        assert root is not None
        assert root.statements == 1

    def test_an_unknown_package_is_reported_as_missing(self, report: str) -> None:
        files = coverage_summary.read_file_counts(report)
        assert coverage_summary.aggregate_prefix(files, "plugin") is None


class TestFloorParsing:
    def test_package_and_percent_are_split(self) -> None:
        assert coverage_summary.parse_floor("plugins=85") == ("plugins", 85.0)

    def test_a_slash_path_is_accepted_as_a_package(self) -> None:
        assert coverage_summary.parse_floor("core/detection=62.5") == ("core.detection", 62.5)

    @pytest.mark.parametrize("spec", ["plugins", "=80", "plugins=abc", "plugins=101", "utils=-1"])
    def test_malformed_floors_are_rejected(self, spec: str) -> None:
        with pytest.raises(ValueError):
            coverage_summary.parse_floor(spec)


class TestExitCodes:
    def test_a_report_without_floors_passes(
        self, report: str, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert coverage_summary.main([report]) == 0
        out = capsys.readouterr().out
        # 7 of 13 statements, 5 of 6 branches.
        assert "Overall line coverage: 53.85% (7/13 statements)" in out
        assert "Overall branch coverage: 83.33% (5/6 branches)" in out

    def test_a_floor_exactly_met_passes(self, report: str) -> None:
        assert coverage_summary.main([report, "--fail-under", "plugins=75"]) == 0

    def test_a_package_under_its_floor_fails(
        self, report: str, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert coverage_summary.main([report, "--fail-under", "plugins=75.01"]) == 1
        assert "FAIL plugins: 75.00% line coverage" in capsys.readouterr().err

    def test_one_failing_floor_among_several_fails(self, report: str) -> None:
        code = coverage_summary.main(
            [report, "--fail-under", "plugins=50", "--fail-under", "utils=50"]
        )
        assert code == 1

    def test_a_floor_on_an_unmeasured_package_cannot_be_trusted(
        self, report: str, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert coverage_summary.main([report, "--fail-under", "plugin=10"]) == 2
        assert "plugin" in capsys.readouterr().err

    def test_a_malformed_floor_cannot_be_trusted(self, report: str) -> None:
        assert coverage_summary.main([report, "--fail-under", "plugins"]) == 2

    def test_a_missing_report_cannot_be_trusted(self, tmp_path: Path) -> None:
        assert coverage_summary.main([str(tmp_path / "absent.xml")]) == 2

    def test_low_files_are_listed_and_covered_ones_are_not(
        self, report: str, capsys: pytest.CaptureFixture[str]
    ) -> None:
        coverage_summary.main([report, "--below", "30"])
        listing = capsys.readouterr().out.split("--- Files under 30% line coverage ---")[1]
        assert "core/services/mask_capture.py" in listing
        assert "utils/cache.py" in listing
        assert "plugins/base.py" not in listing
