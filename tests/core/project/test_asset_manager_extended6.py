"""Extended unit tests for core/project/asset_manager.py (Part 6)."""

from __future__ import annotations

from zebtrack.core.project.asset_manager import AssetManager


class TestAssetManagerExtended6:
    """Test AssetManager slugify helper and synonyms mapping."""

    def test_asset_manager_slugify(self):
        assert AssetManager._slugify("My Test Arena 01!") == "my-test-arena-01"
        assert AssetManager._slugify("Grupo_Controle #2") == "grupo_controle-2"
        assert AssetManager._slugify("  simple  ") == "simple"

    def test_asset_manager_profile_synonyms(self):
        assert "group" in AssetManager._PROFILE_SYNONYMS
        assert "day" in AssetManager._PROFILE_SYNONYMS
        assert "subject" in AssetManager._PROFILE_SYNONYMS
        assert "experiment_id" in AssetManager._PROFILE_SYNONYMS
