"""Testes para ApplicationBootstrapper.

Testes unitários para o serviço de bootstrap da aplicação,
extraído do MainViewModel na Fase 1 da refatoração.
"""

from unittest.mock import MagicMock, patch

import pytest

from zebtrack.core.application_bootstrapper import (
    ApplicationBootstrapper,
    BootstrapResult,
)
from zebtrack.core.dependency_container import MainViewModelDependencies


@pytest.fixture
def mock_dependencies():
    """Cria dependências mockadas para testes."""
    return MagicMock(spec=MainViewModelDependencies)


@pytest.fixture
def mock_weight_manager():
    """Cria WeightManager mockado."""
    manager = MagicMock()
    manager.get_default_weight.return_value = ("yolo11n", "/path/to/yolo11n.pt")
    manager.get_weight_details.return_value = {
        "name": "yolo11n",
        "path": "/path/to/yolo11n.pt",
        "openvino_path": None,
    }
    return manager


@pytest.fixture
def bootstrapper(mock_dependencies):
    """Cria instância de ApplicationBootstrapper para testes."""
    return ApplicationBootstrapper(mock_dependencies)


class TestApplicationBootstrapperInitialization:
    """Testes de inicialização do bootstrapper."""

    def test_init_stores_dependencies(self, mock_dependencies):
        """Testa que dependências são armazenadas corretamente."""
        bootstrapper = ApplicationBootstrapper(mock_dependencies)

        assert bootstrapper.dependencies is mock_dependencies
        assert bootstrapper.log is not None


class TestGetDefaultWeight:
    """Testes de obtenção de peso padrão."""

    def test_get_default_weight_success(self, bootstrapper, mock_weight_manager):
        """Testa obtenção bem-sucedida do peso padrão."""
        result = bootstrapper._get_default_weight(mock_weight_manager)

        assert result == "yolo11n"
        mock_weight_manager.get_default_weight.assert_called_once()

    def test_get_default_weight_error(self, bootstrapper, mock_weight_manager):
        """Testa tratamento de erro ao obter peso padrão."""
        mock_weight_manager.get_default_weight.side_effect = Exception("Test error")

        with pytest.raises(Exception, match="Test error"):
            bootstrapper._get_default_weight(mock_weight_manager)


class TestIsOpenvinoConverted:
    """Testes de verificação de modelo OpenVINO convertido."""

    def test_is_openvino_converted_true(self, bootstrapper, mock_weight_manager):
        """Testa quando modelo OpenVINO está convertido."""
        mock_weight_manager.get_weight_details.return_value = {
            "openvino_path": "/valid/openvino/model"
        }

        with patch(
            "zebtrack.core.application_bootstrapper._is_valid_openvino_directory",
            return_value=True,
        ):
            result = bootstrapper._is_openvino_converted("yolo11n", mock_weight_manager)

        assert result is True

    def test_is_openvino_converted_false(self, bootstrapper, mock_weight_manager):
        """Testa quando modelo OpenVINO não está convertido."""
        mock_weight_manager.get_weight_details.return_value = {
            "openvino_path": None
        }

        with patch(
            "zebtrack.core.application_bootstrapper._is_valid_openvino_directory",
            return_value=False,
        ):
            result = bootstrapper._is_openvino_converted("yolo11n", mock_weight_manager)

        assert result is False

    def test_is_openvino_converted_no_weight(self, bootstrapper, mock_weight_manager):
        """Testa quando peso não existe."""
        result = bootstrapper._is_openvino_converted("", mock_weight_manager)

        assert result is False

    def test_is_openvino_converted_no_details(self, bootstrapper, mock_weight_manager):
        """Testa quando detalhes do peso não estão disponíveis."""
        mock_weight_manager.get_weight_details.return_value = None

        result = bootstrapper._is_openvino_converted("yolo11n", mock_weight_manager)

        assert result is False


class TestConfigureOpenvino:
    """Testes de configuração do OpenVINO."""

    def test_configure_openvino_recommended_and_converted(
        self, bootstrapper, mock_weight_manager
    ):
        """Testa quando OpenVINO é recomendado e modelo está convertido."""
        hardware_summary = {
            "cuda_available": False,
            "openvino_available": True,
            "has_intel_gpu": True,
        }

        with patch.object(
            bootstrapper, "_is_openvino_converted", return_value=True
        ):
            result = bootstrapper._configure_openvino(
                "openvino", "yolo11n", mock_weight_manager, hardware_summary
            )

        assert result is True

    def test_configure_openvino_recommended_not_converted(
        self, bootstrapper, mock_weight_manager
    ):
        """Testa quando OpenVINO é recomendado mas modelo não está convertido."""
        hardware_summary = {
            "cuda_available": False,
            "openvino_available": True,
            "has_intel_gpu": True,
        }

        with patch.object(
            bootstrapper, "_is_openvino_converted", return_value=False
        ):
            result = bootstrapper._configure_openvino(
                "openvino", "yolo11n", mock_weight_manager, hardware_summary
            )

        assert result is False

    def test_configure_openvino_not_recommended(
        self, bootstrapper, mock_weight_manager
    ):
        """Testa quando OpenVINO não é recomendado."""
        hardware_summary = {
            "cuda_available": True,
            "openvino_available": False,
            "has_intel_gpu": False,
        }

        result = bootstrapper._configure_openvino(
            "pytorch", "yolo11n", mock_weight_manager, hardware_summary
        )

        assert result is False


class TestInitializeHardwareAndModels:
    """Testes de inicialização de hardware e modelos."""

    @patch("zebtrack.core.application_bootstrapper.get_hardware_summary")
    @patch("zebtrack.core.application_bootstrapper.recommend_backend")
    def test_initialize_hardware_and_models_success(
        self,
        mock_recommend,
        mock_hardware,
        bootstrapper,
        mock_weight_manager,
    ):
        """Testa inicialização bem-sucedida de hardware e modelos."""
        mock_hardware.return_value = {
            "cuda_available": True,
            "openvino_available": False,
            "has_intel_gpu": False,
        }
        mock_recommend.return_value = "pytorch"

        result = bootstrapper.initialize_hardware_and_models(mock_weight_manager)

        assert isinstance(result, BootstrapResult)
        assert result.active_weight_name == "yolo11n"
        assert result.recommended_backend == "pytorch"
        assert result.use_openvino is False
        assert "cuda_available" in result.hardware_summary

    @patch("zebtrack.core.application_bootstrapper.get_hardware_summary")
    @patch("zebtrack.core.application_bootstrapper.recommend_backend")
    def test_initialize_hardware_and_models_no_weight(
        self,
        mock_recommend,
        mock_hardware,
        bootstrapper,
        mock_weight_manager,
    ):
        """Testa falha quando nenhum peso válido está disponível."""
        mock_weight_manager.get_default_weight.return_value = (None, None)

        with pytest.raises(
            RuntimeError, match="No valid detector weight available"
        ):
            bootstrapper.initialize_hardware_and_models(mock_weight_manager)

    @patch("zebtrack.core.application_bootstrapper.get_hardware_summary")
    @patch("zebtrack.core.application_bootstrapper.recommend_backend")
    def test_initialize_hardware_and_models_empty_weight(
        self,
        mock_recommend,
        mock_hardware,
        bootstrapper,
        mock_weight_manager,
    ):
        """Testa falha quando peso é string vazia."""
        mock_weight_manager.get_default_weight.return_value = ("", "/path")

        with pytest.raises(
            RuntimeError, match="No valid detector weight available"
        ):
            bootstrapper.initialize_hardware_and_models(mock_weight_manager)

    @patch("zebtrack.core.application_bootstrapper.get_hardware_summary")
    @patch("zebtrack.core.application_bootstrapper.recommend_backend")
    def test_initialize_hardware_and_models_with_openvino(
        self,
        mock_recommend,
        mock_hardware,
        bootstrapper,
        mock_weight_manager,
    ):
        """Testa inicialização com OpenVINO habilitado."""
        mock_hardware.return_value = {
            "cuda_available": False,
            "openvino_available": True,
            "has_intel_gpu": True,
        }
        mock_recommend.return_value = "openvino"

        with patch.object(
            bootstrapper, "_is_openvino_converted", return_value=True
        ):
            result = bootstrapper.initialize_hardware_and_models(mock_weight_manager)

        assert result.use_openvino is True
        assert result.recommended_backend == "openvino"


class TestBootstrapResult:
    """Testes do dataclass BootstrapResult."""

    def test_bootstrap_result_creation(self):
        """Testa criação de BootstrapResult."""
        result = BootstrapResult(
            hardware_summary={"cuda_available": True},
            recommended_backend="pytorch",
            active_weight_name="yolo11n",
            use_openvino=False,
        )

        assert result.hardware_summary == {"cuda_available": True}
        assert result.recommended_backend == "pytorch"
        assert result.active_weight_name == "yolo11n"
        assert result.use_openvino is False
