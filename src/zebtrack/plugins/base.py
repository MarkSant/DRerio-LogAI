from abc import ABC, abstractmethod
from pathlib import Path

import numpy as np


def bytetrack_threshold_hints(settings_obj: object | None) -> tuple[float, float]:
    """``(track_threshold, match_threshold)`` a plugin exposes as its ByteTrack hints.

    Read from ``settings_obj.bytetrack`` when there is one, otherwise the shared
    defaults (#698). These attributes are only the tracker's fallback for a caller
    with no settings: ``DetectionPostProcessor`` reads the settings first, so a
    value written after the plugin was built still reaches ByteTrack. The two
    plugins used to disagree on the no-settings match default (0.95 vs 0.80).

    Args:
        settings_obj: Application settings, or ``None``.

    Returns:
        The track and match thresholds.
    """
    from zebtrack.settings import DEFAULT_MATCH_THRESHOLD, DEFAULT_TRACK_THRESHOLD

    bytetrack = getattr(settings_obj, "bytetrack", None)
    return (
        float(getattr(bytetrack, "track_threshold", DEFAULT_TRACK_THRESHOLD)),
        float(getattr(bytetrack, "match_threshold", DEFAULT_MATCH_THRESHOLD)),
    )


class DetectorPlugin(ABC):
    """
    Abstract Base Class for a detector plugin.

    This interface defines the contract that all detector plugins must follow,
    ensuring they can be used interchangeably by the main Detector class.
    """

    conf_threshold: float = 0.25
    nms_threshold: float = 0.45

    #: Captura de máscaras no caminho de TRACKING. Desligada por padrão porque
    #: decodificar a máscara custa tempo de inferência a cada frame e só a
    #: regra ``seg_overlap`` consome o resultado. Enquanto for ``False``,
    #: nenhum decode acontece — é isso que garante o custo zero prometido por
    #: ``recorder.persist_masks``.
    _capture_masks: bool = False

    @abstractmethod
    def __init__(self, model_path: Path | str, **kwargs):
        """
        Initializes the plugin and loads the specified model.

        Args:
            model_path: The path to the model file or directory.
            **kwargs: Additional keyword arguments (e.g., settings_obj, expected_hash).
        """
        pass

    @abstractmethod
    def detect(
        self, frame: np.ndarray, conf_threshold: float | None = None
    ) -> list[tuple[int, int, int, int, float, int | None, int]]:
        """
        Performs object detection on a single frame.

        Args:
            frame (np.ndarray): The input video frame.
            conf_threshold (float, optional): Confidence threshold override.

        Returns:
            A list of detections. Each detection is a tuple containing:
            (x1, y1, x2, y2, confidence, track_id, class_id).
            ``track_id`` should be ``None`` when the underlying model does not
            provide identity assignments for the detections.
        """
        pass

    @staticmethod
    @abstractmethod
    def get_name() -> str:
        """
        Returns the user-friendly name of the plugin.
        e.g., "YOLOv8 (Ultralytics)"
        """
        pass

    @property
    @abstractmethod
    def model_input_shape(self) -> tuple[int, int]:
        """
        Returns the expected input shape (height, width) of the model.
        """
        pass

    def set_mask_capture(self, enabled: bool) -> None:
        """Liga ou desliga o decode de máscaras no caminho de tracking.

        Um plugin sem modelo de segmentação aceita a chamada e simplesmente não
        produz máscara nenhuma: quem decide se a regra é aplicável é a camada
        de análise, que já sabe degradar para ``bbox_intersects``. Falhar aqui
        transformaria uma configuração inconsistente numa exceção no meio da
        gravação.
        """
        self._capture_masks = bool(enabled)

    def pop_frame_masks(self) -> list[np.ndarray | None]:
        """Contornos do ÚLTIMO ``detect()``, alinhados por índice às detecções.

        Consome o buffer: uma segunda chamada sem novo ``detect()`` devolve
        lista vazia. É deliberado — devolver de novo o frame anterior faria
        máscaras velhas serem gravadas com o ``track_id`` de outro frame, que
        é exatamente o erro que este sidecar existe para não cometer.

        Cada elemento é um ``ndarray`` ``(N, 2)`` de pontos em pixels do FRAME
        ORIGINAL, ou ``None`` quando aquela detecção não produziu contorno.
        A implementação padrão nunca captura nada.
        """
        return []

    def detect_batch(
        self,
        frames: list[np.ndarray],
        conf_threshold: float | None = None,
    ) -> list[list[tuple[int, int, int, int, float, int | None, int]]]:
        """Process multiple frames in a single call (batch inference).

        The default implementation falls back to sequential ``detect()`` calls.
        Plugins that support native batch inference should override this.

        Args:
            frames: List of BGR frames.
            conf_threshold: Optional confidence threshold override.

        Returns:
            List of detection lists, one per input frame.
        """
        results = [self.detect(frame, conf_threshold=conf_threshold) for frame in frames]
        if len(frames) > 1:
            # Sobraria a máscara do ÚLTIMO frame, que um ``pop_frame_masks``
            # posterior atribuiria ao lote inteiro. Ver a mesma decisão em
            # ``OpenVINOPlugin.detect_batch``.
            self._drop_frame_masks()
        return results

    def _drop_frame_masks(self) -> None:
        """Descarta o buffer de máscaras (no-op quando não há captura)."""
        self.pop_frame_masks()
