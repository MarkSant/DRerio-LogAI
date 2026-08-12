"""The one help text explaining what an analysis profile is.

``analysis_controls`` and ``analysis_display`` both render this tooltip and
each used to carry its own copy of the wording -- the display one had an extra
sentence naming the fallback label, so the two drifted. Producing it from a
single accessor keeps them from drifting again and, being a function, resolves
the translation per call instead of freezing it at import time.
"""

from __future__ import annotations

from zebtrack.i18n import _


def analysis_profile_tooltip() -> str:
    """Tooltip shown next to the "analysis profile" label of a session."""
    return _(
        "Shows the analysis configuration applied to this session. "
        "When no specific rule matches the group, day or individual, the "
        "project uses the default profile. When it reads 'project default "
        "(default)', that is exactly this fallback."
    )
