"""Single rule for applying the user's group/day/subject regex patterns to a path.

The wizard lets the operator type one regex each for the group, the day and the
subject, and the app applies them in three places: the preview of the pattern
dialog, the wizard's detection step and the project import
(``ProjectWorkflowService._extract_group/_day/_subject``). Each place carried its
own copy of the rule, and the copies disagreed:

- **Case.** The import searched with ``re.IGNORECASE``; the detection step and the
  dialog did not. ``dia_2.mp4`` read "no match" in the dialog, found no design in
  the detection step and was then imported anyway.
- **Value.** ``match.group(1) if match.groups() else match.group(0)`` takes group 1
  even when it did not take part in the match. With an alternation such as
  ``Dia_(\\d+)|D(\\d+)`` on ``D3.mp4`` the value is group 2 and group 1 is ``None``:
  the dialog printed ``'None'`` and the other two callers crashed on
  ``None.isdigit()`` / ``None.lower()``.

The rule, in one place:

1. A pattern is searched **case-insensitively** (``USER_PATTERN_FLAGS``).
2. The value a match yields is its **first capture group that took part** in the
   match; with no group, or none that took part, the whole match.

``re.error`` from an invalid pattern is NOT handled here: each caller decides what an
invalid pattern means for it (the dialog shows the message, the detection step logs
it and gives up on the design).
"""

from __future__ import annotations

import re

#: Flags every user pattern is searched with.
USER_PATTERN_FLAGS = re.IGNORECASE


def compile_user_pattern(pattern: str | re.Pattern[str]) -> re.Pattern[str]:
    """Compile ``pattern`` for the user-pattern rule (case-insensitive).

    A pattern compiled elsewhere without the flag is recompiled with it, so a caller
    cannot opt out of the rule by compiling first.

    Raises:
        re.error: for an invalid pattern.
    """
    if isinstance(pattern, re.Pattern):
        if pattern.flags & USER_PATTERN_FLAGS:
            return pattern
        return re.compile(pattern.pattern, pattern.flags | USER_PATTERN_FLAGS)
    return re.compile(pattern, USER_PATTERN_FLAGS)


def match_value(match: re.Match[str]) -> str:
    """The value a match extracted: its first participating group, else the whole match.

    A group that matched the empty string took part in the match and is the value
    (``""``); only a group that did not take part (``None``) is skipped.
    """
    for group in match.groups():
        if group is not None:
            return group
    return match.group(0)


def search_value(pattern: str | re.Pattern[str], text: str) -> str | None:
    """The value of the first match of ``pattern`` in ``text``, or ``None`` if it has none."""
    match = compile_user_pattern(pattern).search(text)
    return None if match is None else match_value(match)


def finditer_values(pattern: str | re.Pattern[str], text: str) -> list[str]:
    """The value of every non-overlapping match of ``pattern`` in ``text``, in order."""
    return [match_value(m) for m in compile_user_pattern(pattern).finditer(text)]
