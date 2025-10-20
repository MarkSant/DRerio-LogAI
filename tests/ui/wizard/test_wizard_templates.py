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
