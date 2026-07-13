"""Application-wide constants for DRerio LogAI.

Centralizes magic numbers to improve readability and consistency.
Settings-driven values (Pydantic defaults in settings.py) are NOT duplicated here;
these are fallback / layout constants used when settings are unavailable.
"""

from __future__ import annotations

from typing import Final

# ---------------------------------------------------------------------------
# Recorder defaults (used when settings_obj is None or field is missing)
# ---------------------------------------------------------------------------
DEFAULT_FLUSH_INTERVAL_SECONDS: Final[float] = 5.0
DEFAULT_FLUSH_ROW_THRESHOLD: Final[int] = 500

# ---------------------------------------------------------------------------
# Splash screen
# ---------------------------------------------------------------------------
SPLASH_WIDTH: Final[int] = 500
SPLASH_HEIGHT: Final[int] = 400
SPLASH_CLOSE_DELAY_MS: Final[int] = 300

# ---------------------------------------------------------------------------
# Wizard dialog layout
# ---------------------------------------------------------------------------
WIZARD_TARGET_WIDTH: Final[int] = 1050
WIZARD_TARGET_HEIGHT: Final[int] = 780
WIZARD_MIN_WIDTH: Final[int] = 900
WIZARD_MIN_HEIGHT: Final[int] = 650

# ---------------------------------------------------------------------------
# Performance fallback (when settings unavailable)
# ---------------------------------------------------------------------------
DEFAULT_MAX_PARALLEL_PLOTS: Final[int] = 3
