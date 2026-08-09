"""Runtime internationalisation for DRerio LogAI.

English is the source language: every ``msgid`` in the code *is* the English
string the user sees.  A translation catalogue therefore only ever exists for
the *other* languages -- ``install("en")`` resolves to
:class:`gettext.NullTranslations`, which returns the ``msgid`` untouched.  There
is no ``en`` catalogue to create or maintain.

Two catalogue domains share this module:

``zebtrack``
    Everything the graphical interface says -- menus, dialogs, wizard, panels.

``reporter``
    Headings and labels written into the generated ``.docx``/``.html`` reports.
    Consumed through :mod:`zebtrack.analysis.reporters.reporter_context`, which
    keeps its own ``_()`` bound to this domain.

Two rules make this module safe to import from anywhere:

1. **The language is resolved when a string is translated, never when a module
   is imported.**  ``_`` is a plain function that looks the catalogue up on each
   call, so importing a UI module before :func:`install` has run is harmless.
   The one thing that is *not* harmless is *calling* ``_()`` at import time --
   at module or class scope -- because that captures a translation before the
   language is known.  ``tests/i18n/test_no_import_time_translation.py`` fails
   the build when it happens; use :func:`lazy` if a deferred value is genuinely
   needed.

2. **The operating system locale is never consulted.**  ``LANG``, ``LC_ALL`` and
   friends are deliberately ignored: before v5.0.0 a Brazilian Windows install
   silently produced Portuguese reports nobody asked for.  The setting
   ``ui.language`` is now the sole authority, with ``ZEBTRACK_LANGUAGE`` as a
   test/CI escape hatch.
"""

from __future__ import annotations

import gettext as _gettext
import os
import threading
from pathlib import Path
from typing import Any, Final

import structlog

log = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
LOCALES_DIR: Final[Path] = Path(__file__).resolve().parent / "locales"
UI_DOMAIN: Final[str] = "zebtrack"
REPORTER_DOMAIN: Final[str] = "reporter"
DEFAULT_LANGUAGE: Final[str] = "en"
SUPPORTED_LANGUAGES: Final[tuple[str, ...]] = ("en", "pt_BR")
LANGUAGE_ENV_VAR: Final[str] = "ZEBTRACK_LANGUAGE"

# ---------------------------------------------------------------------------
# Module state
# ---------------------------------------------------------------------------
_state_lock = threading.RLock()
_active_language: str | None = None
_catalogs: dict[tuple[str, str], _gettext.NullTranslations] = {}


def normalize_language(value: str | None) -> str | None:
    """Map a loosely written language tag onto a supported one.

    Accepts the shapes a human or an environment variable realistically
    produces -- ``pt-BR``, ``pt_br``, ``pt``, ``en-US`` -- and returns the
    canonical member of :data:`SUPPORTED_LANGUAGES`, or ``None`` when nothing
    matches.  The canonical spelling uses an underscore (``pt_BR``) so it can be
    handed straight to :func:`gettext.translation` and matches the directory
    layout under ``locales/``.
    """
    if not value:
        return None

    candidate = value.strip().replace("-", "_")
    if not candidate:
        return None

    lowered = candidate.lower()
    for supported in SUPPORTED_LANGUAGES:
        if lowered == supported.lower():
            return supported

    # Bare language subtag: "pt" -> "pt_BR", "en" -> "en".
    base = lowered.split("_", 1)[0]
    for supported in SUPPORTED_LANGUAGES:
        if base == supported.lower().split("_", 1)[0]:
            return supported

    return None


def _catalog_for(language: str, domain: str) -> _gettext.NullTranslations:
    """Return (and memoise) the catalogue for *language* / *domain*."""
    key = (language, domain)
    with _state_lock:
        cached = _catalogs.get(key)
        if cached is not None:
            return cached

        if language == DEFAULT_LANGUAGE:
            # English is the source language: the msgid is already the answer.
            catalog: _gettext.NullTranslations = _gettext.NullTranslations()
        else:
            try:
                catalog = _gettext.translation(
                    domain,
                    localedir=str(LOCALES_DIR),
                    languages=[language],
                    fallback=True,
                )
            except OSError as exc:
                # A missing or unreadable catalogue must degrade to English, not
                # take the application down on startup.
                log.warning(
                    "i18n.catalog.load_failed",
                    language=language,
                    domain=domain,
                    error=str(exc),
                )
                catalog = _gettext.NullTranslations()

        _catalogs[key] = catalog
        return catalog


def _resolve_language_from_environment() -> str:
    """Best-effort language when :func:`install` was never called.

    This is the library/CLI path -- generating a report from a script, running a
    single test module -- where no one ran the application startup sequence.
    Order: ``ZEBTRACK_LANGUAGE`` then ``ui.language`` from the settings files.
    """
    from_env = normalize_language(os.environ.get(LANGUAGE_ENV_VAR))
    if from_env is not None:
        return from_env

    try:
        # Imported lazily: settings.py is heavy and imports back into zebtrack.
        from zebtrack.settings import load_settings

        from_settings = normalize_language(load_settings().ui.language)
    except Exception as exc:
        # A broken config must not break report generation: fall back to English.
        log.debug("i18n.settings_lookup.failed", error=str(exc))
        return DEFAULT_LANGUAGE

    return from_settings if from_settings is not None else DEFAULT_LANGUAGE


def install(language: str | None) -> str:
    """Make *language* the active language for every later translation.

    Call this once, early in startup, before any user-visible string is
    produced.  Idempotent, and safe to call again to switch language.  An
    unsupported value degrades to English with a warning rather than raising --
    a typo in ``config.local.yaml`` should not stop the application from
    opening.

    Returns:
        The language actually installed.
    """
    resolved = normalize_language(language)
    if resolved is None:
        if language:
            log.warning(
                "i18n.install.unsupported_language",
                requested=language,
                fallback=DEFAULT_LANGUAGE,
                supported=list(SUPPORTED_LANGUAGES),
            )
        resolved = DEFAULT_LANGUAGE

    global _active_language
    with _state_lock:
        _active_language = resolved

    log.info("i18n.install.done", language=resolved)
    return resolved


def get_language() -> str:
    """Return the active language, resolving it from the environment if needed."""
    global _active_language

    with _state_lock:
        if _active_language is not None:
            return _active_language

    # Resolved outside the lock: load_settings() does file I/O and must not be
    # holding a lock that translate() also wants.
    resolved = _resolve_language_from_environment()
    with _state_lock:
        if _active_language is None:
            _active_language = resolved
        return _active_language


def translate(message: str, *, domain: str = UI_DOMAIN) -> str:
    """Translate *message* into the active language.

    The lookup happens here, on every call -- that is what allows UI modules to
    be imported before the language is known.
    """
    return _catalog_for(get_language(), domain).gettext(message)


def ngettext(singular: str, plural: str, n: int, *, domain: str = UI_DOMAIN) -> str:
    """Plural-aware counterpart of :func:`translate`."""
    return _catalog_for(get_language(), domain).ngettext(singular, plural, n)


def _(message: str) -> str:
    """Translate *message* using the ``zebtrack`` (user interface) domain.

    This is the name to import in UI code::

        from zebtrack.i18n import _

        ttk.Button(parent, text=_("Save project"))
    """
    return translate(message, domain=UI_DOMAIN)


# Explicit alias for call sites where a bare underscore would read poorly.
gettext = _


class LazyString:
    """A translation that resolves every time it is read, not when created.

    The escape hatch for the rare label that genuinely has to live in a
    module-level or class-level constant.  Prefer turning the constant into a
    function instead -- that keeps the value an ordinary ``str`` and sidesteps
    every caveat below.

    Tkinter coerces ``text=`` through :func:`str`, so passing one of these to a
    widget works.  What does *not* work, and must never be attempted: using it
    as a dictionary key, putting it in a ``set``, comparing it in a ``match``
    statement, or handing it to pandas, Pydantic or ``json``.  Those all want a
    real ``str`` and will either raise or silently store the proxy's repr.
    """

    __slots__ = ("_domain", "_message")

    def __init__(self, message: str, *, domain: str = UI_DOMAIN) -> None:
        self._message = message
        self._domain = domain

    def __str__(self) -> str:
        return translate(self._message, domain=self._domain)

    def __repr__(self) -> str:
        return f"LazyString({self._message!r}, domain={self._domain!r})"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, LazyString):
            return str(self) == str(other)
        if isinstance(other, str):
            return str(self) == other
        return NotImplemented

    def __hash__(self) -> int:
        return hash(str(self))

    def __format__(self, format_spec: str) -> str:
        return format(str(self), format_spec)

    def __len__(self) -> int:
        return len(str(self))

    def __contains__(self, item: object) -> bool:
        return str(item) in str(self)

    def __add__(self, other: object) -> str:
        return str(self) + str(other)

    def __radd__(self, other: object) -> str:
        return str(other) + str(self)

    def __getattr__(self, name: str) -> Any:
        # Delegate str methods (.upper(), .format(), .strip(), ...) to the
        # resolved value so a LazyString behaves like the string it stands for.
        return getattr(str(self), name)


def lazy(message: str, *, domain: str = UI_DOMAIN) -> LazyString:
    """Build a :class:`LazyString` for *message*. See its docstring for limits."""
    return LazyString(message, domain=domain)


def reset_for_tests() -> None:
    """Forget the active language and every cached catalogue.

    Test-support only; the application never calls this.
    """
    global _active_language
    with _state_lock:
        _active_language = None
        _catalogs.clear()
