import json
import tempfile
import unittest
from pathlib import Path

from zebtrack.ui.wizard.templates import TemplateManager, format_template_banner


class TestTemplateManager(unittest.TestCase):
    def setUp(self):
        super().setUp()
        self._tmpdir = tempfile.TemporaryDirectory()
        self.templates_dir = Path(self._tmpdir.name)
        self.manager = TemplateManager(templates_dir=self.templates_dir)

    def tearDown(self):
        self._tmpdir.cleanup()
        super().tearDown()

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

        self.assertTrue(saved)
        self.assertTrue(destination.exists())

        with open(destination, "r", encoding="utf-8") as handle:
            data = json.load(handle)

        self.assertEqual(data["name"], "Template Manual")
        self.assertEqual(data["project_type"], "experimental")

    def test_load_template_from_path(self):
        template_path = self.templates_dir / "externo.json"
        template_path.write_text(
            json.dumps({"name": "Externo", "project_type": "exploratory"}),
            encoding="utf-8",
        )

        loaded = self.manager.load_template_from_path(template_path)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["name"], "Externo")
        self.assertEqual(loaded["project_type"], "exploratory")


class TestFormatTemplateBanner(unittest.TestCase):
    def test_banner_with_name_and_path(self):
        banner = format_template_banner(
            {
                "name": "Template Banner",
                "path": "C:/tmp/template_banner.json",
            }
        )

        self.assertIn("Template Banner", banner)
        self.assertIn("template_banner.json", banner)

    def test_banner_without_metadata(self):
        self.assertEqual(format_template_banner(None), "")
        self.assertEqual(format_template_banner({}), "")


if __name__ == "__main__":
    unittest.main()
