"""
Extended unit tests for SocialAnalysisOutcome.
"""

from __future__ import annotations

from typing import cast

from zebtrack.core.video.social_analysis_outcome import (
    SOCIAL_SKIP_REASONS,
    SocialAnalysisOutcome,
    SocialSkipReason,
)


class TestSocialAnalysisOutcomeExtended:
    """Test SocialAnalysisOutcome constructors and warning formatting."""

    def test_success_outcome(self):
        outcome = SocialAnalysisOutcome.success(
            result={"mean_distance_cm": 3.4},
            notes=("Radius fallback used",),
        )
        assert outcome.succeeded is True
        assert outcome.result == {"mean_distance_cm": 3.4}
        assert outcome.skipped_reason is None
        assert outcome.warning_message is None
        assert outcome.warning_messages == ["Radius fallback used"]

    def test_skipped_disabled_has_no_warning(self):
        outcome = SocialAnalysisOutcome.skipped("disabled")
        assert outcome.succeeded is False
        assert outcome.result is None
        assert outcome.skipped_reason == "disabled"
        assert outcome.warning_message is None
        assert outcome.warning_messages == []

    def test_skipped_reasons_formatting(self):
        for reason in SOCIAL_SKIP_REASONS:
            if reason == "disabled":
                continue
            outcome = SocialAnalysisOutcome.skipped(reason, detail="Test detail")
            assert outcome.succeeded is False
            msg = outcome.warning_message
            assert msg is not None
            assert "Social proximity analysis was skipped" in msg or "failed" in msg
            assert "Test detail" in msg
            assert outcome.warning_messages == [msg]

    def test_unknown_skipped_reason_uses_fallback(self):
        outcome = SocialAnalysisOutcome.skipped(cast(SocialSkipReason, "unknown_reason"))
        msg = outcome.warning_message
        assert msg == "Social proximity analysis was skipped for an unspecified reason."
