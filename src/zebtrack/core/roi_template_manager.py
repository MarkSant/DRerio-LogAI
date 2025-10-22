"""
ROI Template Manager

Gerencia templates globais de ROI/Arena independente de projetos específicos.
Templates podem ser salvos em configurações globais do usuário, no projeto,
ou em locais personalizados.
"""

import json
import re
import unicodedata
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import structlog

from zebtrack.core.detector import ZoneData

log = structlog.get_logger()

ROI_TEMPLATE_VERSION = 1


class ROITemplateManager:
    """
    Gerencia templates de ROI/Arena com suporte a salvamento em múltiplos locais.

    Templates podem conter:
    - Arena principal (polygon)
    - Regiões de Interesse (roi_polygons, roi_names, roi_colors)
    - Ou ambos

    Locais de salvamento:
    - Global: ~/.zebtrack/roi_templates/ (reutilizável entre projetos)
    - Projeto: {project_path}/roi_templates/ (específico do projeto)
    - Custom: caminho escolhido pelo usuário
    """

    def __init__(self):
        """Inicializa o gerenciador de templates."""
        # Diretório global de templates
        self.global_templates_dir = Path.home() / ".zebtrack" / "roi_templates"
        self.global_templates_dir.mkdir(parents=True, exist_ok=True)

        log.info(
            "roi_template_manager.initialized",
            global_dir=str(self.global_templates_dir),
        )

    @staticmethod
    def _slugify(value: str) -> str:
        """
        Converte string em slug seguro para nomes de arquivo.

        Args:
            value: String original

        Returns:
            String slugificada (lowercase, sem caracteres especiais)
        """
        normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
        normalized = re.sub(r"[^a-zA-Z0-9_-]+", "-", normalized).strip("-")
        return normalized.lower() or "template"

    def save_template(
        self,
        name: str,
        zone_data: ZoneData,
        *,
        slug: str | None = None,
        save_arena: bool = True,
        save_rois: bool = True,
        save_location: Literal["global", "project", "custom"] = "global",
        project_path: str | None = None,
        custom_path: str | Path | None = None,
        overwrite: bool = True,
    ) -> dict[str, Any]:
        """
        Salva template de ROI/Arena.

        Args:
            name: Nome do template
            zone_data: Dados de zona contendo arena e/ou ROIs
            save_arena: Se True, inclui arena no template
            save_rois: Se True, inclui ROIs no template
            save_location: Onde salvar ("global", "project", "custom")
            project_path: Caminho do projeto (necessário se save_location="project")
            custom_path: Caminho personalizado (necessário se save_location="custom")
            overwrite: Se True, sobrescreve template existente com mesmo nome

        Returns:
            Dicionário com metadados do template salvo

        Raises:
            ValueError: Se nome vazio, dados inválidos, ou parâmetros faltando
        """
        # Validações
        if not name or not name.strip():
            raise ValueError("O nome do template não pode ficar vazio.")

        if not save_arena and not save_rois:
            raise ValueError("Selecione ao menos arena ou ROIs para salvar.")

        if not zone_data:
            raise ValueError("Dados de zona não podem ser vazios.")

        if save_arena and (not zone_data.polygon or len(zone_data.polygon) < 3):
            raise ValueError("Arena inválida: é necessário ao menos 3 pontos.")

        if save_rois and not zone_data.roi_polygons:
            raise ValueError("Nenhuma ROI disponível para salvar.")

        # Determinar diretório de destino
        if save_location == "global":
            target_dir = self.global_templates_dir
        elif save_location == "project":
            if not project_path:
                raise ValueError("Caminho do projeto é necessário para salvar template no projeto.")
            target_dir = Path(project_path) / "roi_templates"
        elif save_location == "custom":
            if not custom_path:
                raise ValueError("Caminho personalizado é necessário para save_location='custom'.")
            custom_path = Path(custom_path)
            if custom_path.is_dir():
                target_dir = custom_path
            else:
                # Se custom_path é um arquivo, usar seu diretório pai
                target_dir = custom_path.parent
        else:
            raise ValueError(f"save_location inválido: {save_location}")

        # Criar diretório se não existir
        target_dir.mkdir(parents=True, exist_ok=True)

        # Gerar slug e caminho do arquivo
        normalized_slug = slug or self._slugify(name)
        if not normalized_slug:
            normalized_slug = self._slugify(name)

        template_path = target_dir / f"{normalized_slug}.json"

        # Verificar se já existe
        if template_path.exists() and not overwrite:
            raise ValueError(
                f"Template '{name}' já existe em {target_dir}. "
                f"Use overwrite=True para sobrescrever."
            )

        # Preparar dados do template (incluir apenas componentes selecionados)
        now = datetime.now(UTC).isoformat()

        serialized_data = {}

        if save_arena:
            serialized_data["polygon"] = [list(point) for point in (zone_data.polygon or [])]

        if save_rois:
            serialized_data["roi_polygons"] = [
                [list(point) for point in polygon] for polygon in (zone_data.roi_polygons or [])
            ]
            serialized_data["roi_names"] = list(zone_data.roi_names or [])
            serialized_data["roi_colors"] = [list(color) for color in (zone_data.roi_colors or [])]

        # Metadados do arquivo
        payload = {
            "version": ROI_TEMPLATE_VERSION,
            "name": name,
            "created_at": now,
            "updated_at": now,
            "save_location": save_location,
            "includes_arena": save_arena,
            "includes_rois": save_rois,
            "data": serialized_data,
        }

        # Salvar arquivo JSON
        with open(template_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

        # Preparar metadados de retorno
        metadata = {
            "name": name,
            "slug": normalized_slug,
            "file": str(template_path),
            "location": save_location,
            "includes_arena": save_arena,
            "includes_rois": save_rois,
            "roi_count": len(zone_data.roi_polygons) if save_rois else 0,
            "created_at": now,
            "updated_at": now,
        }

        log.info(
            "roi_template_manager.template_saved",
            name=name,
            location=save_location,
            path=str(template_path),
            includes_arena=save_arena,
            includes_rois=save_rois,
        )

        return metadata

    def load_template(self, template_path: str | Path) -> ZoneData:
        """
        Carrega template de um caminho específico.

        Args:
            template_path: Caminho do arquivo de template

        Returns:
            ZoneData com dados carregados

        Raises:
            FileNotFoundError: Se arquivo não existir
            ValueError: Se conteúdo do arquivo for inválido
        """
        template_path = Path(template_path)

        if not template_path.exists():
            raise FileNotFoundError(f"Template não encontrado: {template_path}")

        try:
            with open(template_path, encoding="utf-8") as f:
                payload = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"Arquivo JSON inválido: {e}") from e

        if not isinstance(payload, dict):
            raise ValueError("Formato de template inválido.")

        data_block = payload.get("data")
        if not isinstance(data_block, dict):
            raise ValueError("Bloco 'data' ausente ou inválido no template.")

        # Reconstruir ZoneData
        polygon = [list(point) for point in data_block.get("polygon", [])]

        roi_polygons = []
        for polygon_points in data_block.get("roi_polygons", []):
            roi_polygons.append([list(point) for point in polygon_points])

        roi_names = list(data_block.get("roi_names", []))
        roi_colors = [tuple(color) for color in data_block.get("roi_colors", [])]

        zone_data = ZoneData(
            polygon=polygon,
            roi_polygons=roi_polygons,
            roi_names=roi_names,
            roi_colors=roi_colors,
        )

        log.info(
            "roi_template_manager.template_loaded",
            path=str(template_path),
            has_arena=bool(zone_data.polygon),
            roi_count=len(zone_data.roi_polygons),
        )

        return zone_data

    def list_global_templates(self) -> list[dict[str, Any]]:
        """
        Lista todos os templates globais disponíveis.

        Returns:
            Lista de dicionários com metadados dos templates
        """
        templates = []

        try:
            for template_file in self.global_templates_dir.glob("*.json"):
                try:
                    # Validate file is actually readable
                    if not template_file.exists() or not template_file.is_file():
                        log.warning(
                            "roi_template_manager.skipping_invalid_file",
                            file=str(template_file),
                            exists=template_file.exists()
                            if hasattr(template_file, "exists")
                            else False,
                        )
                        continue

                    with open(template_file, encoding="utf-8") as f:
                        payload = json.load(f)

                    # Use the actual file path, not what's stored in the JSON
                    # (the stored path might be outdated)
                    template_info = {
                        "name": payload.get("name", template_file.stem),
                        "slug": template_file.stem,
                        "file": str(template_file.resolve()),  # Use actual resolved path
                        "location": "global",
                        "includes_arena": payload.get("includes_arena", True),
                        "includes_rois": payload.get("includes_rois", True),
                        "roi_count": len(payload.get("data", {}).get("roi_polygons", [])),
                        "created_at": payload.get("created_at", ""),
                        "updated_at": payload.get("updated_at", ""),
                    }

                    log.debug(
                        "roi_template_manager.template_loaded",
                        name=template_info["name"],
                        file=template_info["file"],
                    )

                    templates.append(template_info)
                except Exception as e:
                    log.warning(
                        "roi_template_manager.template_read_error",
                        file=str(template_file),
                        error=str(e),
                    )
        except Exception as e:
            log.error(
                "roi_template_manager.list_templates_error",
                error=str(e),
                exc_info=True,
            )

        return sorted(templates, key=lambda t: t.get("name", "").lower())

    def cleanup_orphaned_templates(self) -> dict[str, int]:
        """
        Remove templates cujos arquivos não existem mais.

        Returns:
            Dict com contagem de templates removidos e mantidos
        """
        removed = 0
        kept = 0

        try:
            for template_file in self.global_templates_dir.glob("*.json"):
                try:
                    # If file exists and is readable, keep it
                    if template_file.exists() and template_file.is_file():
                        # Verify it's valid JSON
                        with open(template_file, encoding="utf-8") as f:
                            json.load(f)
                        kept += 1
                        log.debug("roi_template_manager.cleanup.keeping", file=str(template_file))
                    else:
                        template_file.unlink()
                        removed += 1
                        log.info(
                            "roi_template_manager.cleanup.removed_missing", file=str(template_file)
                        )
                except json.JSONDecodeError:
                    # Invalid JSON, remove it
                    template_file.unlink()
                    removed += 1
                    log.info(
                        "roi_template_manager.cleanup.removed_invalid_json", file=str(template_file)
                    )
                except Exception as e:
                    log.warning(
                        "roi_template_manager.cleanup.error", file=str(template_file), error=str(e)
                    )
        except Exception as e:
            log.error("roi_template_manager.cleanup.failed", error=str(e), exc_info=True)

        log.info("roi_template_manager.cleanup.completed", removed=removed, kept=kept)

        return {"removed": removed, "kept": kept}

    def delete_template(
        self,
        template_path: str | Path,
    ) -> bool:
        """
        Remove um template.

        Args:
            template_path: Caminho do template a remover

        Returns:
            True se removido com sucesso, False caso contrário
        """
        try:
            template_path = Path(template_path)

            if not template_path.exists():
                log.warning(
                    "roi_template_manager.template_not_found",
                    path=str(template_path),
                )
                return False

            template_path.unlink()

            log.info(
                "roi_template_manager.template_deleted",
                path=str(template_path),
            )
            return True

        except Exception as e:
            log.error(
                "roi_template_manager.delete_error",
                path=str(template_path),
                error=str(e),
                exc_info=True,
            )
            return False
