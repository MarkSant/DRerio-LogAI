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
