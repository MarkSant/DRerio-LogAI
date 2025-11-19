"""Serviço de bootstrap da aplicação.

Este serviço foi extraído do MainViewModel como parte da Fase 1 do
plano de refatoração (PLANO_REFATORACAO_MAINVIEWMODEL.md).
Responsável por toda a sequência de inicialização da aplicação.
"""

import glob
import os
from dataclasses import dataclass
from typing import Any

import structlog

from zebtrack.core.dependency_container import MainViewModelDependencies
from zebtrack.utils.hardware_detection import get_hardware_summary, recommend_backend

log = structlog.get_logger()


def _is_valid_openvino_directory(path: str | None) -> bool:
    """
    Validate if an OpenVINO model directory exists and contains required .xml files.

    Args:
        path: Path to the OpenVINO model directory

    Returns:
        True if the directory exists and contains at least one .xml file, False otherwise
    """
    if not path or not os.path.exists(path):
        return False

    if not os.path.isdir(path):
        return False

    xml_files = glob.glob(os.path.join(path, "*.xml"))
    return len(xml_files) > 0


@dataclass
class BootstrapResult:
    """Resultado do processo de bootstrap da aplicação.

    Contém todos os componentes inicializados e estado relevante
    para ser usado pelo MainViewModel.

    Attributes:
        hardware_summary: Resumo do hardware detectado
        recommended_backend: Backend recomendado (pytorch ou openvino)
        active_weight_name: Nome do peso/modelo ativo
        use_openvino: Flag indicando se OpenVINO deve ser usado
    """

    hardware_summary: dict
    recommended_backend: str
    active_weight_name: str
    use_openvino: bool


class ApplicationBootstrapper:
    """Serviço para inicializar a aplicação no startup.

    Extrai e centraliza toda a lógica de inicialização que estava
    espalhada nos métodos _init_* do MainViewModel.

    Attributes:
        dependencies: Dependências injetadas do MainViewModel
        log: Logger estruturado
    """

    def __init__(self, dependencies: MainViewModelDependencies):
        """Inicializa o bootstrapper.

        Args:
            dependencies: Dependências do MainViewModel
        """
        self.dependencies = dependencies
        self.log = structlog.get_logger()

    def initialize_hardware_and_models(
        self, weight_manager: Any
    ) -> BootstrapResult:
        """Inicializa detecção de hardware e configuração de modelos.

        Realiza:
        - Obtenção do peso/modelo padrão
        - Detecção de hardware disponível
        - Recomendação de backend (PyTorch ou OpenVINO)
        - Configuração automática de use_openvino

        Args:
            weight_manager: Gerenciador de pesos de modelos

        Returns:
            BootstrapResult com todos os valores inicializados

        Raises:
            RuntimeError: Se nenhum peso válido estiver disponível
        """
        # Obtém peso padrão
        default_weight = self._get_default_weight(weight_manager)

        # Valida que peso é válido
        if not isinstance(default_weight, str) or not default_weight:
            raise RuntimeError(
                "No valid detector weight available. Cannot initialize application. "
                "Please ensure at least one .pt or .onnx file is in the 'models/' directory."
            )

        # Detecta hardware e recomenda backend
        log.info("bootstrap.hardware_detection_start")
        hardware_summary = get_hardware_summary()
        recommended_backend = recommend_backend()

        # Auto-configura use_openvino baseado na detecção de hardware
        use_openvino = self._configure_openvino(
            recommended_backend, default_weight, weight_manager, hardware_summary
        )

        return BootstrapResult(
            hardware_summary=hardware_summary,
            recommended_backend=recommended_backend,
            active_weight_name=default_weight,
            use_openvino=use_openvino,
        )

    def _get_default_weight(self, weight_manager: Any) -> str:
        """Obtém o peso/modelo padrão de forma segura.

        Args:
            weight_manager: Gerenciador de pesos

        Returns:
            Nome do peso padrão
        """
        try:
            default_weight, _ = weight_manager.get_default_weight()
            return default_weight
        except Exception as e:
            self.log.error("bootstrap.get_default_weight_error", error=str(e))
            raise

    def _configure_openvino(
        self,
        recommended_backend: str,
        default_weight: str,
        weight_manager: Any,
        hardware_summary: dict,
    ) -> bool:
        """Configura o uso do OpenVINO baseado no hardware e modelo.

        Args:
            recommended_backend: Backend recomendado pela detecção
            default_weight: Nome do peso padrão
            weight_manager: Gerenciador de pesos
            hardware_summary: Resumo do hardware detectado

        Returns:
            True se OpenVINO deve ser usado, False caso contrário
        """
        if recommended_backend == "openvino":
            # Verifica se modelo OpenVINO já está convertido
            openvino_converted = self._is_openvino_converted(
                default_weight, weight_manager
            )

            if openvino_converted:
                self.log.info(
                    "bootstrap.auto_selected_openvino",
                    reason="Hardware detection recommends OpenVINO and model is converted",
                    cuda_available=hardware_summary["cuda_available"],
                    openvino_available=hardware_summary["openvino_available"],
                    intel_gpu=hardware_summary["has_intel_gpu"],
                )
                return True
            else:
                # OpenVINO recomendado mas modelo não convertido - fallback para PyTorch
                self.log.warning(
                    "bootstrap.openvino_recommended_but_not_converted",
                    reason=(
                        "OpenVINO recommended by hardware but model not yet "
                        "converted, using PyTorch"
                    ),
                    cuda_available=hardware_summary["cuda_available"],
                    openvino_available=hardware_summary["openvino_available"],
                    intel_gpu=hardware_summary["has_intel_gpu"],
                    active_weight=default_weight,
                )
                return False
        else:
            self.log.info(
                "bootstrap.auto_selected_pytorch",
                reason="Hardware detection recommends PyTorch",
                cuda_available=hardware_summary["cuda_available"],
            )
            return False

    def _is_openvino_converted(
        self, weight_name: str, weight_manager: Any
    ) -> bool:
        """Verifica se o modelo OpenVINO está convertido.

        Args:
            weight_name: Nome do peso
            weight_manager: Gerenciador de pesos

        Returns:
            True se modelo está convertido, False caso contrário
        """
        if not weight_name:
            return False

        weight_details = weight_manager.get_weight_details(weight_name)
        if not weight_details:
            return False

        ov_path = weight_details.get("openvino_path")
        return _is_valid_openvino_directory(ov_path)
