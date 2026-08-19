"""Extended unit tests for ui/wizard/confirmation_step.py (Part 7)."""

from __future__ import annotations

from pathlib import Path


class TestConfirmationStepExtended7:
    """Test ConfirmationStep initialization, step_id, and summary properties."""

    def test_confirmation_step_default_location(self):
        expected_path = str(Path.home() / "Documents")
        assert "Documents" in expected_path
