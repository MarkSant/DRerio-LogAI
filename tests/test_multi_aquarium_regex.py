import pytest
from zebtrack.ui.wizard.models import MultiAquariumData


class TestMultiAquariumRegex:
    """Tests for MultiAquariumData.extract_metadata with multi-subject support."""

    def test_extract_metadata_single_match(self):
        """Test extraction with a single match (legacy behavior fallback)."""
        data = MultiAquariumData(
            regex_pattern=r"(?P<group>\w+)_(?P<subject>S\d+)",
            regex_group_field="group",
            regex_subject_field="subject",
            enabled=True,
            aquarium_configs=[
                {"aquarium_id": 0, "group": "G1", "subject_id": "S1", "day": 1},
                {"aquarium_id": 1, "group": "G2", "subject_id": "S2", "day": 1},
            ],
        )

        # Should return a list with one dictionary
        results = data.extract_metadata("Controle_S01.mp4")
        assert isinstance(results, list)
        assert len(results) == 1
        assert results[0]["group"] == "Controle"
        assert results[0]["subject"] == "S01"

    def test_extract_metadata_multiple_matches(self):
        """Test extraction with multiple matches in one filename."""
        # Pattern: Group_Subject (e.g., G1_S01--G2_S02)
        # Note: We use a non-greedy approach or specific structure to separate them
        # Let's try a pattern that matches "Group_Subject" blocks

        data = MultiAquariumData(
            # Start of string or separator, followed by Group_Subject
            regex_pattern=r"(?P<group>[A-Za-z]+)_(?P<subject>S\d+)",
            regex_group_field="group",
            regex_subject_field="subject",
            enabled=True,
            aquarium_configs=[
                {"aquarium_id": 0, "group": "G1", "subject_id": "S1", "day": 1},
                {"aquarium_id": 1, "group": "G2", "subject_id": "S2", "day": 1},
            ],
        )

        filename = "Controle_S01--Tratamento_S02.mp4"
        results = data.extract_metadata(filename)

        assert len(results) == 2

        # Match 1 (Aquarium 0)
        assert results[0]["group"] == "Controle"
        assert results[0]["subject"] == "S01"

        # Match 2 (Aquarium 1)
        assert results[1]["group"] == "Tratamento"
        assert results[1]["subject"] == "S02"

    def test_extract_metadata_no_matches(self):
        """Test when no matches are found."""
        data = MultiAquariumData(
            regex_pattern=r"(?P<group>\w+)_(?P<subject>S\d+)",
            enabled=True,
            aquarium_configs=[
                {"aquarium_id": 0, "group": "G1", "subject_id": "S1", "day": 1},
                {"aquarium_id": 1, "group": "G2", "subject_id": "S2", "day": 1},
            ],
        )
        results = data.extract_metadata("random_video.mp4")
        assert results == []

    def test_extract_metadata_with_day(self):
        """Test extraction including day field."""
        data = MultiAquariumData(
            regex_pattern=r"(?P<group>\w+)_(?P<subject>S\d+)_D(?P<day>\d+)",
            regex_day_field="day",
            enabled=True,
            aquarium_configs=[
                {"aquarium_id": 0, "group": "G1", "subject_id": "S1", "day": 1},
                {"aquarium_id": 1, "group": "G2", "subject_id": "S2", "day": 1},
            ],
        )

        filename = "Controle_S01_D1--Tratamento_S02_D1.mp4"
        results = data.extract_metadata(filename)

        assert len(results) == 2
        assert results[0]["day"] == "1"
        assert results[1]["day"] == "1"


class TestBuildCombinedRegexPattern:
    """Tests for MultiAquariumData.build_combined_regex_pattern."""

    def test_build_pattern_with_all_components(self):
        """Test building a pattern with group, day, and subject."""
        pattern = MultiAquariumData.build_combined_regex_pattern(
            group_pattern=r"G(\d+)",
            day_pattern=r"D(\d+)",
            subject_pattern=r"S(\d+)",
        )

        # Should create a pattern with named groups
        assert "(?P<group>" in pattern
        assert "(?P<day>" in pattern
        assert "(?P<subject>" in pattern

        # The pattern should match and extract from "G1_D1_S1"
        import re

        match = re.search(pattern, "G1_D1_S1")
        assert match is not None
        assert match.group("group") == "1"
        assert match.group("day") == "1"
        assert match.group("subject") == "1"

    def test_build_pattern_with_partial_components(self):
        """Test building a pattern with only some components."""
        pattern = MultiAquariumData.build_combined_regex_pattern(
            group_pattern=r"G(\d+)",
            subject_pattern=r"S(\d+)",
        )

        assert "(?P<group>" in pattern
        assert "(?P<subject>" in pattern
        assert "(?P<day>" not in pattern

    def test_build_pattern_empty_when_no_patterns(self):
        """Test that empty string is returned when no patterns provided."""
        pattern = MultiAquariumData.build_combined_regex_pattern()
        assert pattern == ""

    def test_build_pattern_with_patterns_without_capture_groups(self):
        """Test patterns that don't have explicit capture groups."""
        pattern = MultiAquariumData.build_combined_regex_pattern(
            group_pattern=r"G\d+",  # No capture group
            subject_pattern=r"S\d+",  # No capture group
        )

        # Should wrap in named groups
        import re

        match = re.search(pattern, "G1_S2")
        assert match is not None
        # When no capture group, the whole pattern becomes the named group
        assert "G1" in match.group("group") or "1" in match.group("group")

    def test_full_workflow_with_build_and_extract(self):
        """Test the complete workflow: build pattern then extract metadata."""
        # Step 1: Build combined pattern from separate patterns
        combined = MultiAquariumData.build_combined_regex_pattern(
            group_pattern=r"G(\d+)",
            day_pattern=r"D(\d+)",
            subject_pattern=r"S(\d+)",
        )

        # Step 2: Create MultiAquariumData with the combined pattern
        data = MultiAquariumData(
            regex_pattern=combined,
            enabled=True,
            aquarium_configs=[
                {"aquarium_id": 0, "group": "G1", "subject_id": "S1", "day": 1},
                {"aquarium_id": 1, "group": "G2", "subject_id": "S2", "day": 1},
            ],
        )

        # Step 3: Extract metadata from filename with multiple subjects
        filename = "G1_D1_S1--G1_D1_S2.mp4"
        results = data.extract_metadata(filename)

        # Should find 2 matches
        assert len(results) == 2

        # First match
        assert results[0]["group"] == "1"
        assert results[0]["day"] == "1"
        assert results[0]["subject"] == "1"

        # Second match
        assert results[1]["group"] == "1"
        assert results[1]["day"] == "1"
        assert results[1]["subject"] == "2"

    def test_workflow_with_different_format(self):
        """Test workflow with Controle/Tratamento format."""
        combined = MultiAquariumData.build_combined_regex_pattern(
            group_pattern=r"(Controle|Tratamento)",
            subject_pattern=r"S(\d+)",
        )

        data = MultiAquariumData(
            regex_pattern=combined,
            enabled=True,
            aquarium_configs=[
                {"aquarium_id": 0, "group": "G1", "subject_id": "S1", "day": 1},
                {"aquarium_id": 1, "group": "G2", "subject_id": "S2", "day": 1},
            ],
        )

        filename = "Controle_S01--Tratamento_S02.mp4"
        results = data.extract_metadata(filename)

        assert len(results) == 2
        assert results[0]["group"] == "Controle"
        assert results[0]["subject"] == "01"
        assert results[1]["group"] == "Tratamento"
        assert results[1]["subject"] == "02"
