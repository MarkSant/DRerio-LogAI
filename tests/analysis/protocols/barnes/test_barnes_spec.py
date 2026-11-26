"""``analysis/protocols/barnes/spec.py`` — the registered Barnes spec (#633)."""

from __future__ import annotations

from zebtrack import i18n
from zebtrack.analysis.protocols.barnes.contract import ASSISTANT_ID, barnes_tidy_columns
from zebtrack.analysis.protocols.barnes.metrics import compute_barnes_metrics
from zebtrack.analysis.protocols.barnes.spec import BARNES_SPEC
from zebtrack.analysis.protocols.base import GenericReportSection
from zebtrack.core.services.experiment_profile import ProtocolId


def test_the_spec_declares_what_the_contract_says():
    assert BARNES_SPEC.protocol is ProtocolId.BARNES
    assert BARNES_SPEC.compute_metrics is compute_barnes_metrics
    assert BARNES_SPEC.suppressed_report_sections == frozenset(
        {GenericReportSection.THIGMOTAXIS, GenericReportSection.GEOTAXIS}
    )
    assert BARNES_SPEC.zone_assistant == ASSISTANT_ID
    assert BARNES_SPEC.window_preset is None


def test_tidy_columns_follow_the_project_hole_count():
    # Default: the lab's 18-hole table, d00 (target) .. d09 (opposite).
    assert BARNES_SPEC.tidy_columns({}) == barnes_tidy_columns(18)
    assert BARNES_SPEC.tidy_columns({})[-1] == "barnes_visits_d09"
    assert BARNES_SPEC.tidy_columns({"n_holes": 20}) == barnes_tidy_columns(20)
    assert BARNES_SPEC.tidy_columns({"n_holes": 12}) == barnes_tidy_columns(12)
    assert BARNES_SPEC.tidy_columns({"n_holes": 12})[-1] == "barnes_visits_d06"
    # A bad value falls back to the default instead of raising.
    assert BARNES_SPEC.tidy_columns({"n_holes": "x"}) == barnes_tidy_columns(18)


def test_display_name_is_translated_at_call_time():
    previous = i18n.get_language()
    try:
        i18n.install("en")
        assert BARNES_SPEC.display_name() == "Barnes maze"
        i18n.install("pt_BR")
        assert BARNES_SPEC.display_name() == "Labirinto de Barnes"
    finally:
        i18n.install(previous)
