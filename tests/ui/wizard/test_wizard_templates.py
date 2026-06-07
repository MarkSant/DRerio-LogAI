import json
import tempfile
from pathlib import Path

import pytest

from zebtrack.ui.wizard.templates import TemplateManager, format_template_banner


class TestTemplateManager:
    @pytest.fixture(autouse=True)
    def setup(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.templates_dir = Path(self._tmpdir.name)
        self.manager = TemplateManager(templates_dir=self.templates_dir)
        yield
        self._tmpdir.cleanup()

    def test_save_template_to_custom_path(self):
        destination = self.templates_dir / "custom" / "meu_template.json"

        payload = {
            "project_type": "experimental",
            "num_aquariums": 2,
        }

        saved = self.manager.save_template(
            "Template Manual",
            payload,
            destination_path=destination,
        )

        assert saved
        assert destination.exists()

        with open(destination, encoding="utf-8") as handle:
            data = json.load(handle)

        assert data["name"] == "Template Manual"
        assert data["project_type"] == "experimental"

    def test_load_template_from_path(self):
        template_path = self.templates_dir / "externo.json"
        template_path.write_text(
            json.dumps({"name": "Externo", "project_type": "exploratory"}),
            encoding="utf-8",
        )

        loaded = self.manager.load_template_from_path(template_path)
        assert loaded is not None
        assert loaded["name"] == "Externo"
        assert loaded["project_type"] == "exploratory"

    def test_save_template_includes_live_capture_and_behavioral(self):
        """Schema v3: LiveConfig (incl. camera) + behavioral_analysis are persisted.

        The camera is safe to store because LiveConfigStep reconciles it against
        the host hardware on load (graceful fallback when absent).
        """
        payload = {
            "project_type": "live",
            # Live capture block (Step 3), camera included.
            "camera_index": 2,
            "camera_friendly_name": "Cam Y",
            "use_arduino": True,
            "arduino_port": "COM7",
            "external_trigger_mode": True,
            "use_timed_recording": True,
            "recording_duration_s": 600.0,
            "use_countdown": True,
            "countdown_duration_s": 15,
            "preserve_real_aquarium_shape": True,
            "selected_live_mode": "MULTI",
            # Behavioral analysis (Step 4).
            "behavioral_analysis": {"freezing": True},
            # Experimental design (Step 2).
            "experiment_days": 5,
            "num_groups": 3,
            "subjects_per_group": 6,
            "group_names": ["g1", "g2", "g3"],
        }

        assert self.manager.save_template("Live T", payload)

        with open(self.templates_dir / "live_t.json", encoding="utf-8") as handle:
            data = json.load(handle)

        assert data["schema_version"] == 3
        for key, expected in payload.items():
            assert data[key] == expected, f"{key!r} not persisted correctly"


@pytest.mark.gui
class TestApplyTemplateData:
    """DiscoveryStep._apply_template_data must seed wizard_data with every
    step's keys so steps 2-4 repopulate from a loaded template."""

    @pytest.fixture(autouse=True)
    def setup(self, wizard_dependencies):
        self.root = wizard_dependencies["root"]

    def test_apply_template_populates_design_live_and_behavioral_keys(self):
        from zebtrack.ui.wizard.discovery_step import DiscoveryStep

        wizard_data: dict = {}
        step = DiscoveryStep(self.root, wizard_data)
        step.build_ui()

        template = {
            "name": "T",
            "project_type": "live",
            "experiment_days": 3,
            "num_groups": 2,
            "subjects_per_group": 4,
            "group_names": ["A", "B"],
            "camera_index": 1,
            "camera_friendly_name": "Cam X",
            "use_arduino": True,
            "arduino_port": "COM5",
            "external_trigger_mode": True,
            "use_timed_recording": False,
            "recording_duration_s": 120.0,
            "use_countdown": False,
            "countdown_duration_s": 5,
            "preserve_real_aquarium_shape": True,
            "selected_live_mode": "SINGLE",
            "behavioral_analysis": {"enabled": True},
        }

        step._apply_template_data(template, "T.json")

        expected_keys = [
            "experiment_days",
            "num_groups",
            "subjects_per_group",
            "group_names",
            "camera_index",
            "camera_friendly_name",
            "use_arduino",
            "arduino_port",
            "external_trigger_mode",
            "use_timed_recording",
            "recording_duration_s",
            "use_countdown",
            "countdown_duration_s",
            "preserve_real_aquarium_shape",
            "selected_live_mode",
            "behavioral_analysis",
        ]
        for key in expected_keys:
            assert wizard_data[key] == template[key], f"{key!r} not applied to wizard_data"


class TestFormatTemplateBanner:
    def test_banner_with_name_and_path(self):
        banner = format_template_banner(
            {
                "name": "Template Banner",
                "path": "C:/tmp/template_banner.json",
            }
        )

        assert "Template Banner" in banner
        assert "template_banner.json" in banner

    def test_banner_without_metadata(self):
        assert format_template_banner(None) == ""
        assert format_template_banner({}) == ""
