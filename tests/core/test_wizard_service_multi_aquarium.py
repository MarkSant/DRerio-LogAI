"""Tests for WizardService multi-aquarium validation (Phase 9).

These tests cover:
- Validation of disabled configurations
- Validation of aquarium count
- Validation of regex patterns
- Validation of regex group captures
- Validation against sample filenames
"""

from zebtrack.core.wizard_service import WizardService
from zebtrack.ui.wizard.models import AquariumConfig, MultiAquariumData


class TestValidateMultiAquariumConfig:
    """Tests for validate_multi_aquarium_config method."""

    def test_validate_disabled_config(self):
        """Test that disabled config passes validation."""
        config = MultiAquariumData(enabled=False)

        is_valid, errors, _ = WizardService.validate_multi_aquarium_config(config)

        assert is_valid is True
        assert errors == []

    def test_validate_enabled_with_2_aquariums(self):
        """Test that enabled config with 2 aquariums passes."""
        config = MultiAquariumData(
            enabled=True,
            aquarium_configs=[
                AquariumConfig(aquarium_id=0, group="Control"),
                AquariumConfig(aquarium_id=1, group="Treatment"),
            ],
        )

        is_valid, errors, _ = WizardService.validate_multi_aquarium_config(config)

        assert is_valid is True
        assert errors == []

    def test_validate_missing_aquariums(self):
        """Test validation fails when aquariums are missing."""
        # Use model_construct to bypass Pydantic validation
        config = MultiAquariumData.model_construct(
            enabled=True,
            aquarium_configs=[],
            regex_pattern="",
            regex_group_field="group",
            regex_subject_field="subject",
            regex_day_field="day",
        )

        is_valid, errors, _ = WizardService.validate_multi_aquarium_config(config)

        assert is_valid is False
        assert any("2 aquários" in e for e in errors)

    def test_validate_only_one_aquarium(self):
        """Test validation fails with only one aquarium."""
        config = MultiAquariumData.model_construct(
            enabled=True,
            aquarium_configs=[AquariumConfig(aquarium_id=0, group="Control")],
            regex_pattern="",
            regex_group_field="group",
            regex_subject_field="subject",
            regex_day_field="day",
        )

        is_valid, errors, _ = WizardService.validate_multi_aquarium_config(config)

        assert is_valid is False
        assert any("2 aquários" in e for e in errors)

    def test_validate_invalid_regex_pattern(self):
        """Test validation fails for invalid regex."""
        config = MultiAquariumData.model_construct(
            enabled=True,
            aquarium_configs=[
                AquariumConfig(aquarium_id=0, group="Control"),
                AquariumConfig(aquarium_id=1, group="Treatment"),
            ],
            regex_pattern="[invalid(regex",  # Invalid regex
            regex_group_field="group",
            regex_subject_field="subject",
            regex_day_field="day",
        )

        is_valid, errors, _ = WizardService.validate_multi_aquarium_config(config)

        assert is_valid is False
        assert any("regex inválido" in e.lower() for e in errors)

    def test_validate_regex_missing_groups(self):
        """Test validation fails when regex doesn't capture expected fields."""
        config = MultiAquariumData.model_construct(
            enabled=True,
            aquarium_configs=[
                AquariumConfig(aquarium_id=0, group="Control"),
                AquariumConfig(aquarium_id=1, group="Treatment"),
            ],
            regex_pattern=r"(?P<other>\w+)",  # Missing group and subject
            regex_group_field="group",
            regex_subject_field="subject",
            regex_day_field="day",
        )

        is_valid, errors, _ = WizardService.validate_multi_aquarium_config(config)

        assert is_valid is False
        assert any("não captura" in e for e in errors)

    def test_validate_regex_with_correct_groups(self):
        """Test validation passes when regex has correct groups."""
        config = MultiAquariumData(
            enabled=True,
            aquarium_configs=[
                AquariumConfig(aquarium_id=0, group="Control"),
                AquariumConfig(aquarium_id=1, group="Treatment"),
            ],
            regex_pattern=r"(?P<group>\w+)_(?P<subject>\w+)_(?P<day>\d+)",
            regex_group_field="group",
            regex_subject_field="subject",
        )

        is_valid, errors, _ = WizardService.validate_multi_aquarium_config(config)

        assert is_valid is True
        assert errors == []

    def test_validate_regex_against_matching_filenames(self):
        """Test regex validation against matching sample filenames."""
        config = MultiAquariumData(
            enabled=True,
            aquarium_configs=[
                AquariumConfig(aquarium_id=0, group="Control"),
                AquariumConfig(aquarium_id=1, group="Treatment"),
            ],
            regex_pattern=r"(?P<group>Control|Treatment)_(?P<subject>S\d+)",
        )

        sample_filenames = [
            "Control_S01_day1.mp4",
            "Treatment_S02_day1.mp4",
        ]

        is_valid, errors, _ = WizardService.validate_multi_aquarium_config(config, sample_filenames)

        assert is_valid is True
        assert errors == []

    def test_validate_regex_against_non_matching_filenames(self):
        """Test regex validation fails for non-matching filenames."""
        config = MultiAquariumData(
            enabled=True,
            aquarium_configs=[
                AquariumConfig(aquarium_id=0, group="Control"),
                AquariumConfig(aquarium_id=1, group="Treatment"),
            ],
            regex_pattern=r"(?P<group>Control|Treatment)_(?P<subject>S\d+)",
        )

        sample_filenames = [
            "totally_different_format.mp4",
            "another_bad_format.mp4",
        ]

        is_valid, errors, _ = WizardService.validate_multi_aquarium_config(config, sample_filenames)

        assert is_valid is False
        assert any("não corresponde" in e for e in errors)

    def test_validate_with_empty_regex(self):
        """Test validation passes with empty regex pattern."""
        config = MultiAquariumData(
            enabled=True,
            aquarium_configs=[
                AquariumConfig(aquarium_id=0, group="Control"),
                AquariumConfig(aquarium_id=1, group="Treatment"),
            ],
            regex_pattern="",  # Empty regex is OK
        )

        is_valid, errors, _ = WizardService.validate_multi_aquarium_config(config)

        assert is_valid is True
        assert errors == []

    def test_validate_partial_regex_match(self):
        """Test regex that only matches some filenames."""
        config = MultiAquariumData(
            enabled=True,
            aquarium_configs=[
                AquariumConfig(aquarium_id=0, group="Control"),
                AquariumConfig(aquarium_id=1, group="Treatment"),
            ],
            regex_pattern=r"(?P<group>Control)_(?P<subject>S\d+)",
        )

        sample_filenames = [
            "Control_S01.mp4",  # Matches
            "Treatment_S02.mp4",  # Doesn't match (Treatment not in pattern)
            "Control_S03.mp4",  # Matches
        ]

        is_valid, errors, _ = WizardService.validate_multi_aquarium_config(config, sample_filenames)

        # Should fail because Treatment doesn't match
        assert is_valid is False
        assert any("não corresponde" in e for e in errors)


class TestValidateMultiAquariumConfigEdgeCases:
    """Edge case tests for validate_multi_aquarium_config."""

    def test_validate_dict_like_config(self):
        """Test validation works with dict-like configuration."""
        config = {
            "enabled": False,
        }

        is_valid, errors, _ = WizardService.validate_multi_aquarium_config(config)

        assert is_valid is True
        assert errors == []

    def test_validate_dict_enabled_missing_aquariums(self):
        """Test dict config with enabled but missing aquariums."""
        config = {
            "enabled": True,
            "aquarium_configs": [],
            "regex_pattern": "",
            "regex_group_field": "group",
            "regex_subject_field": "subject",
        }

        is_valid, errors, _ = WizardService.validate_multi_aquarium_config(config)

        assert is_valid is False
        assert any("2 aquários" in e for e in errors)

    def test_validate_with_none_sample_filenames(self):
        """Test validation works with None sample filenames."""
        config = MultiAquariumData(
            enabled=True,
            aquarium_configs=[
                AquariumConfig(aquarium_id=0, group="Control"),
                AquariumConfig(aquarium_id=1, group="Treatment"),
            ],
        )

        is_valid, errors, _ = WizardService.validate_multi_aquarium_config(config, None)

        assert is_valid is True
        assert errors == []

    def test_validate_with_empty_sample_filenames(self):
        """Test validation works with empty sample filenames list."""
        config = MultiAquariumData(
            enabled=True,
            aquarium_configs=[
                AquariumConfig(aquarium_id=0, group="Control"),
                AquariumConfig(aquarium_id=1, group="Treatment"),
            ],
            regex_pattern=r"(?P<group>\w+)_(?P<subject>\w+)",
        )

        is_valid, errors, _ = WizardService.validate_multi_aquarium_config(config, [])

        assert is_valid is True
        assert errors == []

    def test_validate_complex_regex(self):
        """Test validation with complex regex pattern."""
        config = MultiAquariumData(
            enabled=True,
            aquarium_configs=[
                AquariumConfig(aquarium_id=0, group="Control"),
                AquariumConfig(aquarium_id=1, group="Treatment"),
            ],
            regex_pattern=r"(?P<group>[A-Za-z]+)_D(?P<day>\d+)_(?P<subject>[A-Z]\d+)",
        )

        sample_filenames = [
            "Control_D01_S01.mp4",
            "Treatment_D02_S02.mp4",
        ]

        is_valid, errors, _ = WizardService.validate_multi_aquarium_config(config, sample_filenames)

        assert is_valid is True
        assert errors == []

    def test_validate_multiple_errors_accumulated(self):
        """Test that multiple errors are accumulated."""
        config = MultiAquariumData.model_construct(
            enabled=True,
            aquarium_configs=[],  # Missing aquariums
            regex_pattern="[invalid(regex",  # Invalid regex
            regex_group_field="group",
            regex_subject_field="subject",
            regex_day_field="day",
        )

        is_valid, errors, _ = WizardService.validate_multi_aquarium_config(config)

        assert is_valid is False
        # Should have at least 2 errors
        assert len(errors) >= 2


class TestIntegrationWithWizardFlow:
    """Integration tests simulating wizard flow."""

    def test_complete_wizard_flow_validation(self):
        """Test validation as it would be called in wizard flow."""
        # Step 1: Create empty config
        config = MultiAquariumData(enabled=False)
        is_valid, _, _ = WizardService.validate_multi_aquarium_config(config)
        assert is_valid is True

        # Step 2: Enable and configure
        config = MultiAquariumData(
            enabled=True,
            aquarium_configs=[
                AquariumConfig(aquarium_id=0, group="Controle", subject_id="S01", day=1),
                AquariumConfig(aquarium_id=1, group="CBD", subject_id="S02", day=1),
            ],
            regex_pattern=r"(?P<group>Controle|CBD)_(?P<subject>S\d+)_D(?P<day>\d+)",
        )

        sample_filenames = [
            "Controle_S01_D01.mp4",
            "CBD_S02_D01.mp4",
        ]

        is_valid, errors, _ = WizardService.validate_multi_aquarium_config(config, sample_filenames)

        assert is_valid is True
        assert errors == []
