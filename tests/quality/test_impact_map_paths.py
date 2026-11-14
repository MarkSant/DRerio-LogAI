"""`.copilot-impact-map.yaml` is trusted before every change: each path it names must exist."""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
IMPACT_MAP = REPO_ROOT / ".copilot-impact-map.yaml"
PACKAGE = REPO_ROOT / "src" / "zebtrack"

# A whole-string path: no spaces, at least one separator, a file extension or a glob/dir tail.
_PATH = re.compile(r"^[A-Za-z0-9_./*\-]+$")
_EXTENSIONS = (".py", ".yaml", ".yml", ".json", ".md", ".toml", ".txt")


def _strings(node: Any) -> Iterator[str]:
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for value in node.values():
            yield from _strings(value)
    elif isinstance(node, list):
        for item in node:
            yield from _strings(item)


def _is_path_reference(text: str) -> bool:
    if not _PATH.match(text) or "/" not in text:
        return False
    return text.endswith(_EXTENSIONS) or text.endswith("/*") or text.endswith("/")


def _exists(text: str) -> bool:
    """Paths are repo-relative or relative to the package (`ui/gui.py`)."""
    for base in (REPO_ROOT, PACKAGE):
        if "*" in text:
            if any(base.glob(text)):
                return True
        elif (base / text).exists():
            return True
    return False


def _referenced_paths() -> list[str]:
    data = yaml.safe_load(IMPACT_MAP.read_text(encoding="utf-8"))
    return sorted({s for s in _strings(data) if _is_path_reference(s)})


def test_the_map_names_paths() -> None:
    # Guards the guard: a parser that finds nothing would pass the next test vacuously.
    assert len(_referenced_paths()) > 50


def test_every_path_in_the_map_exists() -> None:
    missing = [p for p in _referenced_paths() if not _exists(p)]
    assert not missing, f"{IMPACT_MAP.name} names paths that do not exist: {missing}"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("src/zebtrack/plugins/detector.py", False),
        ("ui/dialogs/dialog_manager.py", False),
        ("ui/components/dialog_manager.py", True),
        ("ui/components/canvas/*", True),
    ],
)
def test_existence_check_tells_real_paths_from_stale_ones(text: str, expected: bool) -> None:
    assert _exists(text) is expected
