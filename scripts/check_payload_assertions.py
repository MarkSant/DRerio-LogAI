#!/usr/bin/env python3
"""Pre-commit hook to detect raw dict payloads in test event assertions.

When production code migrates from raw dicts to typed payloads (zebtrack.ui.payloads),
test files that still assert `event_bus.publish(..., {"key": value})` will pass locally
but fail on CI (Linux GUI tests). This hook catches those mismatches early.

Exit codes:
- 0: no violations found
- 1: violations found (raw dicts in assert_called_with + UIEvents)
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

# Pattern: assert_called[_once]_with( UIEvents.XXX, { ... } )
# Matches multi-line assertions where the second arg is a raw dict literal.
ASSERT_WITH_DICT_RE = re.compile(
    r"assert_called(?:_once)?_with\("
    r"[^)]*UIEvents\.\w+"
    r"[^)]*"
    r"\{[^}]*\}"
    r"[^)]*\)",
    re.DOTALL,
)

# Events that are known to still use raw dicts in production (whitelist).
# Update this list if more events are intentionally kept as dicts.
ALLOWED_RAW_DICT_EVENTS: set[str] = {
    "ZONE_VIDEO_SEARCH_CHANGED",
    "FRAME_ERROR",
}


def _get_staged_test_files() -> list[Path]:
    """Return staged Python test files under tests/."""
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM", "--", "tests/"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return []
    return [Path(f) for f in result.stdout.strip().splitlines() if f.endswith(".py")]


def _scan_file(filepath: Path) -> list[dict[str, str | int]]:
    """Scan a file for raw dict assertions with UIEvents."""
    violations: list[dict[str, str | int]] = []
    try:
        content = filepath.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return violations

    for match in ASSERT_WITH_DICT_RE.finditer(content):
        span_text = match.group(0)
        # Check if the event is in the whitelist
        event_match = re.search(r"UIEvents\.(\w+)", span_text)
        if event_match and event_match.group(1) in ALLOWED_RAW_DICT_EVENTS:
            continue

        # Calculate line number
        line_no = content[: match.start()].count("\n") + 1
        event_name = event_match.group(1) if event_match else "UNKNOWN"
        violations.append(
            {
                "file": str(filepath),
                "line": line_no,
                "event": event_name,
                "hint": (
                    f"Use a typed payload from zebtrack.ui.payloads "
                    f"instead of a raw dict for {event_name}"
                ),
            }
        )

    return violations


def main() -> int:
    """Entry point."""
    files = _get_staged_test_files()
    if not files:
        return 0

    all_violations: list[dict[str, str | int]] = []
    for f in files:
        if f.exists():
            all_violations.extend(_scan_file(f))

    if not all_violations:
        return 0

    print("\n  Raw dict payloads detected in test assertions!")
    print("  These will likely fail on CI (Linux GUI tests).\n")
    for v in all_violations:
        print(f"  {v['file']}:{v['line']} - UIEvents.{v['event']}")
        print(f"    {v['hint']}\n")

    print(f"  Total: {len(all_violations)} violation(s)")
    print("  Fix: replace raw dicts with typed payloads from zebtrack.ui.payloads\n")
    return 1


if __name__ == "__main__":
    sys.exit(main())
