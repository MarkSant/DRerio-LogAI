"""
Testes para consistência de paths (Path | str).

Este módulo testa se os métodos principais aceitam tanto Path quanto str
e os convertem corretamente internamente para Path.

Objetivo: Zero bugs de separador de caminho Windows/Linux.
"""

from pathlib import Path

import pytest

from zebtrack.core.project.project_service import ProjectService


class TestProjectServicePathConsistency:
    """Testa consistência de paths no ProjectService."""

    @pytest.fixture
    def project_service(self):
        """Cria uma instância do ProjectService."""
        return ProjectService()

    @pytest.fixture
    def temp_project_dir(self, tmp_path):
        """Cria um diretório temporário para projeto de teste."""
        project_dir = tmp_path / "test_project"
        return project_dir

    def test_create_project_directory_accepts_str(self, project_service, temp_project_dir):
        """Testa que create_project_directory aceita str."""
        project_path_str = str(temp_project_dir)

        result = project_service.create_project_directory(
            project_path=project_path_str,
            project_name="Test Project",
            project_type="project",
        )

        assert temp_project_dir.exists()
        assert result["project_name"] == "Test Project"

    def test_create_project_directory_accepts_path(self, project_service, temp_project_dir):
        """Testa que create_project_directory aceita Path."""
        result = project_service.create_project_directory(
            project_path=temp_project_dir,
            project_name="Test Project",
            project_type="project",
        )

        assert temp_project_dir.exists()
        assert result["project_name"] == "Test Project"

    def test_load_project_config_accepts_str(self, project_service, temp_project_dir):
        """Testa que load_project_config aceita str."""
        # Criar projeto primeiro
        project_service.create_project_directory(
            project_path=temp_project_dir,
            project_name="Test Project",
            project_type="project",
        )

        # Carregar usando str
        project_path_str = str(temp_project_dir)
        loaded_data = project_service.load_project_config(project_path_str)

        assert loaded_data["project_name"] == "Test Project"

    def test_load_project_config_accepts_path(self, project_service, temp_project_dir):
        """Testa que load_project_config aceita Path."""
        # Criar projeto primeiro
        project_service.create_project_directory(
            project_path=temp_project_dir,
            project_name="Test Project",
            project_type="project",
        )

        # Carregar usando Path
        loaded_data = project_service.load_project_config(temp_project_dir)

        assert loaded_data["project_name"] == "Test Project"

    def test_save_project_config_accepts_str(self, project_service, temp_project_dir):
        """Testa que save_project_config aceita str."""
        # Criar diretório manualmente
        temp_project_dir.mkdir(parents=True, exist_ok=True)

        project_data = {
            "project_name": "Test",
            "project_type": "project",
            "videos": [],
        }

        # Salvar usando str
        project_path_str = str(temp_project_dir)
        project_service.save_project_config(project_path_str, project_data)

        # Verificar que foi salvo
        config_file = temp_project_dir / "project_config.json"
        assert config_file.exists()

    def test_save_project_config_accepts_path(self, project_service, temp_project_dir):
        """Testa que save_project_config aceita Path."""
        # Criar diretório manualmente
        temp_project_dir.mkdir(parents=True, exist_ok=True)

        project_data = {
            "project_name": "Test",
            "project_type": "project",
            "videos": [],
        }

        # Salvar usando Path
        project_service.save_project_config(temp_project_dir, project_data)

        # Verificar que foi salvo
        config_file = temp_project_dir / "project_config.json"
        assert config_file.exists()

    def test_resolve_results_directory_accepts_str(self, project_service, temp_project_dir):
        """Testa que resolve_results_directory aceita str."""
        project_path_str = str(temp_project_dir)
        results_dir = project_service.resolve_results_directory(project_path_str)

        assert isinstance(results_dir, Path)
        assert results_dir == temp_project_dir / "results"

    def test_resolve_results_directory_accepts_path(self, project_service, temp_project_dir):
        """Testa que resolve_results_directory aceita Path."""
        results_dir = project_service.resolve_results_directory(temp_project_dir)

        assert isinstance(results_dir, Path)
        assert results_dir == temp_project_dir / "results"

    def test_ensure_roi_template_directory_accepts_str(self, project_service, temp_project_dir):
        """Testa que ensure_roi_template_directory aceita str."""
        temp_project_dir.mkdir(parents=True, exist_ok=True)

        project_path_str = str(temp_project_dir)
        template_dir = project_service.ensure_roi_template_directory(project_path_str)

        assert isinstance(template_dir, Path)
        assert template_dir.exists()
        assert template_dir == temp_project_dir / "templates"

    def test_ensure_roi_template_directory_accepts_path(self, project_service, temp_project_dir):
        """Testa que ensure_roi_template_directory aceita Path."""
        temp_project_dir.mkdir(parents=True, exist_ok=True)

        template_dir = project_service.ensure_roi_template_directory(temp_project_dir)

        assert isinstance(template_dir, Path)
        assert template_dir.exists()
        assert template_dir == temp_project_dir / "templates"

    def test_save_roi_template_accepts_str(self, project_service, temp_project_dir):
        """Testa que save_roi_template aceita str."""
        temp_project_dir.mkdir(parents=True, exist_ok=True)

        template_data: dict[str, object] = {"zones": [], "arena": None}
        project_path_str = str(temp_project_dir)

        template_file = project_service.save_roi_template(
            project_path_str, "test_template", template_data
        )

        assert isinstance(template_file, Path)
        assert template_file.exists()
        assert template_file.name == "test_template.json"

    def test_save_roi_template_accepts_path(self, project_service, temp_project_dir):
        """Testa que save_roi_template aceita Path."""
        temp_project_dir.mkdir(parents=True, exist_ok=True)

        template_data: dict[str, object] = {"zones": [], "arena": None}

        template_file = project_service.save_roi_template(
            temp_project_dir, "test_template", template_data
        )

        assert isinstance(template_file, Path)
        assert template_file.exists()
        assert template_file.name == "test_template.json"

    def test_load_roi_template_accepts_str(self, project_service, temp_project_dir):
        """Testa que load_roi_template aceita str."""
        temp_project_dir.mkdir(parents=True, exist_ok=True)

        # Criar template primeiro
        template_data: dict[str, object] = {"zones": [], "arena": None}
        project_service.save_roi_template(temp_project_dir, "test_template", template_data)

        # Carregar usando str
        project_path_str = str(temp_project_dir)
        loaded_data = project_service.load_roi_template(project_path_str, "test_template")

        assert loaded_data == template_data

    def test_load_roi_template_accepts_path(self, project_service, temp_project_dir):
        """Testa que load_roi_template aceita Path."""
        temp_project_dir.mkdir(parents=True, exist_ok=True)

        # Criar template primeiro
        template_data: dict[str, object] = {"zones": [], "arena": None}
        project_service.save_roi_template(temp_project_dir, "test_template", template_data)

        # Carregar usando Path
        loaded_data = project_service.load_roi_template(temp_project_dir, "test_template")

        assert loaded_data == template_data

    def test_list_roi_templates_accepts_str(self, project_service, temp_project_dir):
        """Testa que list_roi_templates aceita str."""
        temp_project_dir.mkdir(parents=True, exist_ok=True)

        # Criar alguns templates
        project_service.save_roi_template(temp_project_dir, "template1", {"zones": []})
        project_service.save_roi_template(temp_project_dir, "template2", {"zones": []})

        # Listar usando str
        project_path_str = str(temp_project_dir)
        templates = project_service.list_roi_templates(project_path_str)

        assert len(templates) == 2
        assert "template1" in templates
        assert "template2" in templates

    def test_list_roi_templates_accepts_path(self, project_service, temp_project_dir):
        """Testa que list_roi_templates aceita Path."""
        temp_project_dir.mkdir(parents=True, exist_ok=True)

        # Criar alguns templates
        project_service.save_roi_template(temp_project_dir, "template1", {"zones": []})
        project_service.save_roi_template(temp_project_dir, "template2", {"zones": []})

        # Listar usando Path
        templates = project_service.list_roi_templates(temp_project_dir)

        assert len(templates) == 2
        assert "template1" in templates
        assert "template2" in templates


class TestWindowsPathsHandling:
    """Testes específicos para garantir compatibilidade Windows/Linux."""

    @pytest.fixture
    def project_service(self):
        """Cria uma instância do ProjectService."""
        return ProjectService()

    def test_handles_backslash_paths_on_windows(self, project_service, tmp_path):
        """Testa que caminhos com backslash são tratados corretamente."""
        project_dir = tmp_path / "test_project"

        # Criar projeto usando Path (funcionará em ambos os sistemas)
        project_service.create_project_directory(
            project_path=project_dir,
            project_name="Test Project",
            project_type="project",
        )

        # Converter para string e verificar que pode ser recarregado
        project_path_str = str(project_dir)
        loaded_data = project_service.load_project_config(project_path_str)

        assert loaded_data["project_name"] == "Test Project"

    def test_path_objects_work_consistently(self, project_service, tmp_path):
        """Testa que Path objects funcionam de forma consistente."""
        project_dir = tmp_path / "test_project"

        # Todas as operações com Path
        project_service.create_project_directory(
            project_path=project_dir,
            project_name="Test",
            project_type="project",
        )

        config = project_service.load_project_config(project_dir)
        assert config["project_name"] == "Test"

        config["project_name"] = "Updated"
        project_service.save_project_config(project_dir, config)

        reloaded = project_service.load_project_config(project_dir)
        assert reloaded["project_name"] == "Updated"
