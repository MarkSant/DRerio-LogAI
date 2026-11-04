"""Every ``_()`` msgid in the source must be in the committed ``.pot``.

``test_catalog_integrity`` checks ``.pot`` -> ``.po`` -> ``.mo``, but it trusts the
``.pot``. When a front adds ``_("New label")`` and nobody runs
``scripts/update_translations.py``, the template, the catalogue and the compiled
file all stay mutually consistent -- and the new label silently renders in English
for every Portuguese user. Before v8 the ``.pot`` was 40 msgids behind the ``.po``
and the v8 fronts added a few hundred more; nothing failed.

This test re-extracts the msgids from the source with Babel, using the same
keywords, comment tag and domain split as ``scripts/update_translations.py``, and
fails on any msgid missing from the committed template. It does not fail on
msgids that are in the ``.pot`` but no longer in the code: those are obsolete
entries the next regeneration drops, harmless at runtime.

Extraction of the whole package takes about four seconds, so the test stays in
the fast suite; the extraction runs once per domain per session.
"""

from __future__ import annotations

from pathlib import Path

import polib
import pytest
from babel.messages.extract import DEFAULT_KEYWORDS, extract_from_dir

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src" / "zebtrack"
LOCALES_DIR = SRC_ROOT / "locales"

# Mirrors scripts/update_translations.py: KEYWORDS adds "lazy" and "translate" to
# Babel's defaults (the CLI's --keyword appends, it does not replace), and the
# reporters subtree is its own domain, excluded from "zebtrack".
_KEYWORDS = {**DEFAULT_KEYWORDS, "lazy": None, "translate": None}
_DOMAINS: dict[str, tuple[Path, str | None]] = {
    "zebtrack": (SRC_ROOT, "reporters"),
    "reporter": (SRC_ROOT / "analysis" / "reporters", None),
}


def _extract_msgids(source: Path, ignore_dir: str | None) -> set[str]:
    msgids: set[str] = set()
    for filename, _lineno, message, _comments, _context in extract_from_dir(
        str(source),
        method_map=[("**.py", "python")],
        keywords=_KEYWORDS,
        comment_tags=("i18n",),
    ):
        if ignore_dir is not None and ignore_dir in Path(filename).parts:
            continue
        msgid = message[0] if isinstance(message, tuple) else message
        if msgid:
            msgids.add(msgid)
    return msgids


@pytest.fixture(scope="module", params=sorted(_DOMAINS))
def domain_msgids(request: pytest.FixtureRequest) -> tuple[str, set[str]]:
    domain = request.param
    source, ignore_dir = _DOMAINS[domain]
    return domain, _extract_msgids(source, ignore_dir)


def test_extraction_finds_known_msgids(domain_msgids: tuple[str, set[str]]) -> None:
    """Guard the guard: an extraction that finds nothing would pass vacuously."""
    domain, msgids = domain_msgids
    known = {"zebtrack": "Cancel", "reporter": "Analysis Window"}[domain]
    assert known in msgids, f"extraction of {domain} did not find {known!r}"


@pytest.mark.xfail(
    strict=True,
    reason="v8 msgids not catalogued yet; the catalogue commit removes this marker",
)
def test_every_source_msgid_is_in_the_template(domain_msgids: tuple[str, set[str]]) -> None:
    domain, msgids = domain_msgids
    template = {entry.msgid for entry in polib.pofile(str(LOCALES_DIR / f"{domain}.pot"))}

    missing = sorted(msgids - template)
    assert not missing, (
        f"{len(missing)} msgid(s) used in the code are not in {domain}.pot: "
        f"{missing[:5]}\nRun `python scripts/update_translations.py`, translate the new "
        "entries (record them in src/zebtrack/locales/_pairs/) and commit the .pot, "
        "the .po and the .mo."
    )
