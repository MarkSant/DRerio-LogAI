"""Serviço para obter metadados de vídeos."""

import structlog
import cv2

log = structlog.get_logger()


class VideoMetadataService:
    """Serviço responsável por extrair metadados de arquivos de vídeo."""

    @staticmethod
    def get_video_dimensions(video_path: str) -> tuple[int, int] | None:
        """Obtém as dimensões de um vídeo.

        Args:
            video_path: Caminho para o arquivo de vídeo

        Returns:
            Tupla (largura, altura) ou None se falhar

        Raises:
            ValueError: Se o vídeo não puder ser aberto
        """
        try:
            cap = cv2.VideoCapture(video_path)

            if not cap.isOpened():
                raise ValueError(f"Não foi possível abrir o vídeo: {video_path}")

            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            cap.release()

            if width <= 0 or height <= 0:
                raise ValueError(f"Dimensões inválidas: {width}x{height}")

            log.debug(
                "video_metadata.dimensions_retrieved",
                video_path=video_path,
                width=width,
                height=height,
            )

            return width, height

        except Exception as e:
            log.error(
                "video_metadata.dimensions_error",
                video_path=video_path,
                error=str(e),
            )
            raise

    @staticmethod
    def get_video_info(video_path: str) -> dict:
        """Obtém informações completas de um vídeo.

        Args:
            video_path: Caminho para o arquivo de vídeo

        Returns:
            Dicionário com width, height, fps, frame_count
        """
        try:
            cap = cv2.VideoCapture(video_path)

            if not cap.isOpened():
                raise ValueError(f"Não foi possível abrir o vídeo: {video_path}")

            info = {
                "width": int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                "height": int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
                "fps": cap.get(cv2.CAP_PROP_FPS),
                "frame_count": int(cap.get(cv2.CAP_PROP_FRAME_COUNT)),
            }

            cap.release()
            return info

        except Exception as e:
            log.error(
                "video_metadata.info_error",
                video_path=video_path,
                error=str(e),
            )
            raise
