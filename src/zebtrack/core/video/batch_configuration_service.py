"""Serviço para aplicar configurações de projeto a lotes de vídeos.

Este serviço foi extraído do MainViewModel como parte da Fase 1 do
plano de refatoração (PLANO_REFATORACAO_MAINVIEWMODEL.md).
Responsável por aplicar configurações do projeto (zonas, calibração, etc.)
a novos vídeos adicionados ao lote.
"""

import json
import os
from dataclasses import asdict
from pathlib import Path

import structlog

from zebtrack.core.project.project_manager import ProjectManager
from zebtrack.settings import Settings

log = structlog.get_logger()


class BatchConfigurationService:
    """Serviço para aplicar configurações de projeto a lotes de vídeos.

    Extrai e centraliza a lógica de aplicação de configurações de projeto
    (zonas, calibração, detector, etc.) a múltiplos vídeos em lote.

    Attributes:
        project_manager: Gerenciador de projeto com acesso aos dados do projeto
        settings: Configurações da aplicação
    """

    def __init__(
        self,
        project_manager: ProjectManager,
        settings_obj: Settings,
    ):
        """Inicializa o serviço de configuração em lote.

        Args:
            project_manager: Gerenciador de projeto
            settings_obj: Configurações da aplicação
        """
        self.project_manager = project_manager
        self.settings = settings_obj
        self.log = structlog.get_logger()

    def apply_settings(self, videos: list) -> bool:
        """Aplica configurações do projeto ao lote de vídeos.

        Para cada vídeo no lote, salva:
        - project_settings.json: Configurações completas do projeto
        - zones.json: Dados de zonas e ROIs (se configurados)

        Args:
            videos: Lista de dicts com informações dos vídeos (deve conter 'path')

        Returns:
            True se configurações foram aplicadas a todos os vídeos com sucesso,
            False caso contrário
        """
        if not self._validate_project():
            return False

        config = self._build_configuration()
        return self._apply_to_videos(videos, config)

    def _validate_project(self) -> bool:
        """Valida que o projeto está carregado e configurado.

        Returns:
            True se o projeto está válido, False caso contrário
        """
        if not self.project_manager.project_path:
            self.log.warning("batch_config.no_project_path")
            return False
        return True

    def _build_configuration(self) -> dict:
        """Constrói dict de configuração a partir dos dados do projeto.

        Returns:
            Dict contendo todas as configurações necessárias:
            - zone_data: Dados de zonas e ROIs
            - calibration: Dados de calibração
            - project_data: Dados completos do projeto
            - has_zones: Flag indicando se há zonas configuradas
            - has_calibration: Flag indicando se há calibração
            - has_rois: Número de ROIs configurados
        """
        project_data = self.project_manager.project_data
        zone_data = self.project_manager.get_zone_data()
        calibration = project_data.get("calibration", {})

        self.log.info(
            "batch_config.build_configuration",
            has_zones=bool(zone_data and zone_data.polygon),
            has_calibration=bool(calibration),
            has_rois=len(zone_data.roi_polygons) if zone_data else 0,
        )

        return {
            "zone_data": zone_data,
            "calibration": calibration,
            "project_data": project_data,
            "has_zones": bool(zone_data and zone_data.polygon),
            "has_calibration": bool(calibration),
            "has_rois": len(zone_data.roi_polygons) if zone_data else 0,
        }

    def _apply_to_videos(self, videos: list, config: dict) -> bool:
        """Aplica configuração a cada vídeo no lote.

        Args:
            videos: Lista de dicts com informações dos vídeos
            config: Dict de configuração gerado por _build_configuration

        Returns:
            True se configurações foram aplicadas a todos os vídeos,
            False caso contrário
        """
        self.log.info(
            "batch_config.apply_to_videos",
            videos_count=len(videos),
            has_zones=config["has_zones"],
            has_calibration=config["has_calibration"],
            has_rois=config["has_rois"],
        )

        settings_applied = 0
        for video_info in videos:
            if self._apply_to_single_video(video_info, config):
                settings_applied += 1

        self.log.info(
            "batch_config.settings_applied",
            total_videos=len(videos),
            successful=settings_applied,
        )

        return settings_applied == len(videos)

    def _apply_to_single_video(self, video_info: dict, config: dict) -> bool:
        """Aplica configuração a um único vídeo.

        Args:
            video_info: Dict com informações do vídeo (deve conter 'path')
            config: Dict de configuração

        Returns:
            True se configurações foram aplicadas com sucesso, False caso contrário
        """
        video_path = video_info.get("path")
        if not video_path:
            return False

        experiment_id = os.path.splitext(os.path.basename(video_path))[0]
        results_path = self.project_manager.resolve_results_directory(
            experiment_id,
            video_path=video_path,
        )

        try:
            self._prepare_results_directory(results_path)
            self._save_project_settings(results_path, video_info, config)
            self._save_zone_data(results_path, experiment_id, config)
            return True

        # except Exception justified: batch configuration validation — heterogeneous data sources
        except Exception as e:
            self.log.error(
                "batch_config.settings_save_error",
                video=experiment_id,
                error=str(e),
            )
            return False

    def _prepare_results_directory(self, results_path: Path) -> None:
        """Prepara o diretório de resultados para o vídeo.

        Args:
            results_path: Caminho para o diretório de resultados
        """
        results_path.mkdir(parents=True, exist_ok=True)

    def _save_project_settings(self, results_path: Path, video_info: dict, config: dict) -> None:
        """Salva as configurações do projeto em JSON.

        Args:
            results_path: Caminho para o diretório de resultados
            video_info: Dict com informações do vídeo
            config: Dict de configuração
        """
        project_data = config["project_data"]
        settings_file = results_path / "project_settings.json"

        settings_data = {
            "project_name": self.project_manager.get_project_name(),
            "active_weight": project_data.get("active_weight"),
            "use_openvino": project_data.get("use_openvino", False),
            "calibration": config["calibration"],
            "video_settings": video_info,
            "timestamp": project_data.get("timestamp"),
            "analysis_interval_frames": project_data.get("analysis_interval_frames", 10),
            "display_interval_frames": project_data.get("display_interval_frames", 10),
            "detector_config": self.project_manager.get_detector_state(),
        }

        with open(settings_file, "w") as f:
            json.dump(settings_data, f, indent=2)

    def _save_zone_data(self, results_path: Path, experiment_id: str, config: dict) -> None:
        """Salva os dados de zonas em JSON (se houver).

        Args:
            results_path: Caminho para o diretório de resultados
            experiment_id: ID do experimento/vídeo
            config: Dict de configuração
        """
        zone_data = config["zone_data"]

        if zone_data and (zone_data.polygon or zone_data.roi_polygons):
            zones_file = results_path / "zones.json"

            with open(zones_file, "w") as f:
                json.dump(asdict(zone_data), f, indent=2)

            self.log.info(
                "batch_config.zones_saved",
                video=experiment_id,
                zones_file=str(zones_file),
                settings_file=str(results_path / "project_settings.json"),
            )
