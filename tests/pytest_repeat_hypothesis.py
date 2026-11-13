"""Pytest plugin for repeated runs (``--count``) of Hypothesis tests.

Loaded only by the nightly flakiness job (``-p tests.pytest_repeat_hypothesis``),
never by the default suite.

pytest-repeat turns every test into N parametrised items. For a ``@given`` test
defined as a method, each item gets its own instance of the test class, so
Hypothesis sees the same test function called from different ``self`` objects
and raises ``FailedHealthCheck: ... called from multiple different executors``
on the second repetition. That is an artefact of the repetition itself, not
flakiness in the code under test: the first nightly run with pytest-repeat
installed stopped on exactly that in ``tests/analysis/test_geotaxis_metrics.py``.

The plugin suppresses only that health check, and adds it to the explicit
``suppress_health_check`` lists that individual tests declare (an explicit
``@settings`` list replaces the profile's instead of extending it). Every other
health check and every assertion stay active.
"""

from __future__ import annotations

from typing import Any

import pytest
from hypothesis import HealthCheck, settings

_PROFILE = "repeat"

settings.register_profile(_PROFILE, suppress_health_check=[HealthCheck.differing_executors])
settings.load_profile(_PROFILE)


def _add_differing_executors(test_function: Any) -> None:
    """Extend the settings Hypothesis will read for ``test_function`` in place.

    ``@given`` copies the effective settings onto the wrapper it returns
    (``_hypothesis_internal_use_settings``) when the module is imported, and
    reads them back from that wrapper on every call, so that is the object to
    update. Bound methods are unwrapped to the underlying function first.
    """
    wrapper = getattr(test_function, "__func__", test_function)
    if getattr(wrapper, "hypothesis", None) is None:
        return
    current: settings = getattr(wrapper, "_hypothesis_internal_use_settings", None) or settings()
    suppressed = list(current.suppress_health_check)
    if HealthCheck.differing_executors in suppressed:
        return
    suppressed.append(HealthCheck.differing_executors)
    wrapper._hypothesis_internal_use_settings = settings(current, suppress_health_check=suppressed)


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        function = getattr(item, "function", None)
        if function is not None:
            _add_differing_executors(function)
