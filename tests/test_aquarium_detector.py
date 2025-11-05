"""Testes para AquariumDetector."""

import unittest
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch, PropertyMock

import cv2
import numpy as np
import pytest

from zebtrack.core.aquarium_detector import AquariumDetector


class TestAquariumDetectorInit(unittest.TestCase):
    """Testes de inicialização do AquariumDetector."""

    @patch("zebtrack.core.aquarium_detector.YOLO")
    def test_init_valid_model_seg_mode(self, mock_yolo):
        """Test: Inicialização com modelo válido em modo segmentação."""
        detector = AquariumDetector("fake_model.pt", mode="seg")

        assert detector.mode == "seg"
        mock_yolo.assert_called_once_with("fake_model.pt")

    @patch("zebtrack.core.aquarium_detector.YOLO")
    def test_init_valid_model_det_mode(self, mock_yolo):
        """Test: Inicialização com modelo válido em modo detecção."""
        detector = AquariumDetector("fake_model.pt", mode="det")

        assert detector.mode == "det"
        mock_yolo.assert_called_once_with("fake_model.pt")

    @patch("zebtrack.core.aquarium_detector.YOLO")
    def test_init_with_path_object(self, mock_yolo):
        """Test: Inicialização com Path object."""
        path_obj = Path("fake_model.pt")
        detector = AquariumDetector(path_obj, mode="seg")

        assert detector.mode == "seg"
        mock_yolo.assert_called_once_with("fake_model.pt")

    def test_init_invalid_mode(self):
        """Test: Error handling com modo inválido."""
        with pytest.raises(ValueError, match="Invalid mode"):
            with patch("zebtrack.core.aquarium_detector.YOLO"):
                AquariumDetector("fake_model.pt", mode="invalid")

    @patch("zebtrack.core.aquarium_detector.ULTRALYTICS_AVAILABLE", False)
    def test_init_ultralytics_not_available(self):
        """Test: Error handling quando ultralytics não está disponível."""
        with pytest.raises(ImportError, match="Ultralytics is not available"):
            AquariumDetector("fake_model.pt", mode="seg")

    @patch("zebtrack.core.aquarium_detector.YOLO")
    def test_init_model_loading_error(self, mock_yolo):
        """Test: Error handling quando modelo falha ao carregar."""
        mock_yolo.side_effect = RuntimeError("Invalid model format")

        with pytest.raises(RuntimeError, match="Invalid model format"):
            AquariumDetector("fake_model.pt", mode="seg")


class TestAquariumDetectorIoU(unittest.TestCase):
    """Testes de cálculo de IoU."""

    def setUp(self):
        """Setup: Criar detector mock."""
        with patch("zebtrack.core.aquarium_detector.YOLO"):
            self.detector = AquariumDetector("fake_model.pt", mode="seg")

    def test_iou_overlapping_polygons(self):
        """Test: IoU com polígonos sobrepostos."""
        poly1 = np.array([[0, 0], [10, 0], [10, 10], [0, 10]])
        poly2 = np.array([[5, 5], [15, 5], [15, 15], [5, 15]])

        iou = self.detector._calculate_iou(poly1, poly2)

        # IoU esperado: área de interseção / área de união
        # Área interseção: 5x5 = 25
        # Área união: 100 + 100 - 25 = 175
        # IoU = 25/175 ≈ 0.143
        assert 0.14 <= iou <= 0.15

    def test_iou_no_overlap(self):
        """Test: IoU com polígonos sem overlap (IoU = 0)."""
        poly1 = np.array([[0, 0], [10, 0], [10, 10], [0, 10]])
        poly2 = np.array([[20, 20], [30, 20], [30, 30], [20, 30]])

        iou = self.detector._calculate_iou(poly1, poly2)

        assert iou == 0.0

    def test_iou_identical_polygons(self):
        """Test: IoU com polígonos idênticos (IoU = 1)."""
        poly1 = np.array([[0, 0], [10, 0], [10, 10], [0, 10]])
        poly2 = np.array([[0, 0], [10, 0], [10, 10], [0, 10]])

        iou = self.detector._calculate_iou(poly1, poly2)

        assert iou == 1.0

    def test_iou_degenerate_polygon(self):
        """Test: IoU com polígono degenerado (área zero)."""
        poly1 = np.array([[0, 0], [10, 0], [10, 10], [0, 10]])
        poly2 = np.array([[0, 0], [0, 0], [0, 0]])  # Ponto único

        iou = self.detector._calculate_iou(poly1, poly2)

        assert iou == 0.0

    def test_iou_invalid_polygon_handling(self):
        """Test: Error handling com polígono inválido."""
        poly1 = np.array([[0, 0], [10, 0], [10, 10], [0, 10]])
        # Self-intersecting polygon (bowtie)
        poly2 = np.array([[0, 0], [10, 10], [10, 0], [0, 10]])

        # Should handle gracefully and return 0.0
        iou = self.detector._calculate_iou(poly1, poly2)

        assert isinstance(iou, float)
        assert iou >= 0.0


class TestAquariumDetectorExtraction(unittest.TestCase):
    """Testes de extração de polígono."""

    def setUp(self):
        """Setup: Criar detector mock."""
        with patch("zebtrack.core.aquarium_detector.YOLO"):
            self.detector = AquariumDetector("fake_model.pt", mode="det")

    def test_extract_polygon_from_bbox(self):
        """Test: Extração com bounding box válido."""
        frame = np.zeros((480, 640, 3), dtype=np.uint8)

        # Mock de resultado YOLO com bbox
        mock_box = Mock()
        mock_box.xyxy = [np.array([50, 50, 300, 300])]
        mock_box.conf = 0.90

        mock_result = Mock()
        mock_result.boxes = [mock_box]

        polygon = self.detector._extract_polygon_from_detection(frame, [mock_result])

        assert polygon is not None
        assert polygon.shape == (4, 2)  # Bbox convertido em 4 pontos
        # Verify the corners
        assert polygon[0][0] == 50  # top-left x
        assert polygon[0][1] == 50  # top-left y
        assert polygon[2][0] == 300  # bottom-right x
        assert polygon[2][1] == 300  # bottom-right y

    def test_extract_polygon_empty_results(self):
        """Test: Resultado vazio/None."""
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        polygon = self.detector._extract_polygon_from_detection(frame, None)

        assert polygon is None

    def test_extract_polygon_no_boxes(self):
        """Test: Resultado sem boxes."""
        frame = np.zeros((480, 640, 3), dtype=np.uint8)

        mock_result = Mock()
        mock_result.boxes = None

        polygon = self.detector._extract_polygon_from_detection(frame, [mock_result])

        assert polygon is None

    def test_extract_polygon_empty_boxes(self):
        """Test: Resultado com lista de boxes vazia."""
        frame = np.zeros((480, 640, 3), dtype=np.uint8)

        mock_result = Mock()
        mock_result.boxes = []

        polygon = self.detector._extract_polygon_from_detection(frame, [mock_result])

        assert polygon is None

    def test_extract_polygon_multiple_boxes(self):
        """Test: Seleção do box com maior confiança."""
        frame = np.zeros((480, 640, 3), dtype=np.uint8)

        # Mock de múltiplos boxes com diferentes confianças
        mock_box1 = Mock()
        mock_box1.xyxy = [np.array([10, 10, 100, 100])]
        mock_box1.conf = 0.70

        mock_box2 = Mock()
        mock_box2.xyxy = [np.array([50, 50, 300, 300])]
        mock_box2.conf = 0.95  # Maior confiança

        mock_box3 = Mock()
        mock_box3.xyxy = [np.array([150, 150, 400, 400])]
        mock_box3.conf = 0.80

        mock_result = Mock()
        mock_result.boxes = [mock_box1, mock_box2, mock_box3]

        polygon = self.detector._extract_polygon_from_detection(frame, [mock_result])

        assert polygon is not None
        # Should select box2 (highest confidence)
        assert polygon[0][0] == 50

    def test_extract_polygon_too_small(self):
        """Test: Rejeição de detecção muito pequena (<10% do frame)."""
        frame = np.zeros((480, 640, 3), dtype=np.uint8)

        # Caixa muito pequena: 20x20 = 400 pixels
        # Frame: 480x640 = 307200 pixels
        # Ratio: 400/307200 ≈ 0.0013 < 0.1
        mock_box = Mock()
        mock_box.xyxy = [np.array([100, 100, 120, 120])]
        mock_box.conf = 0.95

        mock_result = Mock()
        mock_result.boxes = [mock_box]

        polygon = self.detector._extract_polygon_from_detection(frame, [mock_result])

        assert polygon is None

    def test_extract_polygon_too_large(self):
        """Test: Rejeição de detecção muito grande (>95% do frame)."""
        frame = np.zeros((480, 640, 3), dtype=np.uint8)

        # Caixa quase do tamanho do frame (>95%)
        mock_box = Mock()
        mock_box.xyxy = [np.array([0, 0, 639, 479])]
        mock_box.conf = 0.95

        mock_result = Mock()
        mock_result.boxes = [mock_box]

        polygon = self.detector._extract_polygon_from_detection(frame, [mock_result])

        assert polygon is None

    def test_extract_polygon_valid_size(self):
        """Test: Aceitação de detecção com tamanho válido (10%-95%)."""
        frame = np.zeros((480, 640, 3), dtype=np.uint8)

        # Caixa de tamanho médio (aproximadamente 50% do frame)
        mock_box = Mock()
        mock_box.xyxy = [np.array([50, 50, 450, 350])]
        mock_box.conf = 0.90

        mock_result = Mock()
        mock_result.boxes = [mock_box]

        polygon = self.detector._extract_polygon_from_detection(frame, [mock_result])

        assert polygon is not None
        assert polygon.shape == (4, 2)


class TestAquariumDetectorSegmentationProcessing(unittest.TestCase):
    """Testes de processamento de resultados de segmentação."""

    def setUp(self):
        """Setup: Criar detector mock."""
        with patch("zebtrack.core.aquarium_detector.YOLO"):
            self.detector = AquariumDetector("fake_model.pt", mode="seg")

    def test_process_segmentation_single_valid_mask(self):
        """Test: Processamento com uma máscara válida."""
        frame = np.zeros((480, 640, 3), dtype=np.uint8)

        # Mock segmentation mask (área grande, ~60% do frame)
        mask_points = np.array([[50, 50], [590, 50], [590, 430], [50, 430]])

        mock_box = Mock()
        mock_box.conf = 0.95
        mock_box.cls = 0

        mock_result = Mock()
        mock_result.masks = Mock()
        mock_result.masks.xy = [mask_points]
        mock_result.boxes = [mock_box]

        polygon = self.detector._process_segmentation_results(frame, [mock_result], frame_index=0)

        assert polygon is not None
        assert len(polygon) == 4

    def test_process_segmentation_mask_too_small(self):
        """Test: Rejeição de máscara muito pequena (<30% do frame)."""
        frame = np.zeros((480, 640, 3), dtype=np.uint8)

        # Máscara pequena (<30%)
        mask_points = np.array([[100, 100], [200, 100], [200, 200], [100, 200]])

        mock_box = Mock()
        mock_box.conf = 0.95
        mock_box.cls = 0

        mock_result = Mock()
        mock_result.masks = Mock()
        mock_result.masks.xy = [mask_points]
        mock_result.boxes = [mock_box]

        polygon = self.detector._process_segmentation_results(frame, [mock_result], frame_index=0)

        assert polygon is None

    def test_process_segmentation_low_confidence(self):
        """Test: Rejeição de máscara com confiança baixa."""
        frame = np.zeros((480, 640, 3), dtype=np.uint8)

        # Máscara grande mas confiança baixa
        mask_points = np.array([[50, 50], [590, 50], [590, 430], [50, 430]])

        mock_box = Mock()
        mock_box.conf = 0.03  # Abaixo do threshold de 0.05
        mock_box.cls = 0

        mock_result = Mock()
        mock_result.masks = Mock()
        mock_result.masks.xy = [mask_points]
        mock_result.boxes = [mock_box]

        polygon = self.detector._process_segmentation_results(frame, [mock_result], frame_index=0)

        assert polygon is None

    def test_process_segmentation_multiple_masks(self):
        """Test: Rejeição quando há múltiplas máscaras (espera-se exatamente uma)."""
        frame = np.zeros((480, 640, 3), dtype=np.uint8)

        mask1 = np.array([[50, 50], [300, 50], [300, 300], [50, 300]])
        mask2 = np.array([[350, 350], [590, 350], [590, 430], [350, 430]])

        mock_result = Mock()
        mock_result.masks = Mock()
        mock_result.masks.xy = [mask1, mask2]
        mock_result.boxes = []

        polygon = self.detector._process_segmentation_results(frame, [mock_result], frame_index=0)

        # Multiple masks should be rejected
        assert polygon is None

    def test_process_segmentation_no_masks_with_fallback(self):
        """Test: Fallback quando não há máscaras no resultado principal."""
        frame = np.zeros((480, 640, 3), dtype=np.uint8)

        # Resultado principal sem máscaras
        mock_result = Mock()
        mock_result.masks = None
        mock_result.boxes = None

        # Mock de resultado de fallback
        fallback_mask = np.array([[50, 50], [590, 50], [590, 430], [50, 430]])

        with patch.object(self.detector.model, "predict") as mock_predict:
            mock_fallback_result = Mock()
            mock_fallback_result.masks = Mock()
            mock_fallback_result.masks.xy = [fallback_mask]
            mock_fallback_result.boxes = []
            mock_predict.return_value = [mock_fallback_result]

            polygon = self.detector._process_segmentation_results(
                frame, [mock_result], frame_index=0
            )

            assert polygon is not None
            mock_predict.assert_called_once()

    def test_process_segmentation_fallback_accepts_large_mask(self):
        """Test: Fallback aceita máscara grande (>10% do frame)."""
        frame = np.zeros((480, 640, 3), dtype=np.uint8)

        mock_result = Mock()
        mock_result.masks = None

        # Fallback mask grande (>10%)
        fallback_mask = np.array([[50, 50], [400, 50], [400, 300], [50, 300]])

        with patch.object(self.detector.model, "predict") as mock_predict:
            mock_fallback_result = Mock()
            mock_fallback_result.masks = Mock()
            mock_fallback_result.masks.xy = [fallback_mask]
            mock_predict.return_value = [mock_fallback_result]

            polygon = self.detector._process_segmentation_results(
                frame, [mock_result], frame_index=0
            )

            assert polygon is not None

    def test_process_segmentation_fallback_rejects_small_mask(self):
        """Test: Fallback rejeita máscara pequena (<10% do frame)."""
        frame = np.zeros((480, 640, 3), dtype=np.uint8)

        mock_result = Mock()
        mock_result.masks = None

        # Fallback mask pequena (<10%)
        fallback_mask = np.array([[100, 100], [150, 100], [150, 150], [100, 150]])

        with patch.object(self.detector.model, "predict") as mock_predict:
            mock_fallback_result = Mock()
            mock_fallback_result.masks = Mock()
            mock_fallback_result.masks.xy = [fallback_mask]
            mock_predict.return_value = [mock_fallback_result]

            polygon = self.detector._process_segmentation_results(
                frame, [mock_result], frame_index=0
            )

            assert polygon is None


class TestAquariumDetectorConsensus(unittest.TestCase):
    """Testes de busca de consenso entre polígonos."""

    def setUp(self):
        """Setup: Criar detector mock."""
        with patch("zebtrack.core.aquarium_detector.YOLO"):
            self.detector = AquariumDetector("fake_model.pt", mode="seg")

    def test_consensus_single_polygon(self):
        """Test: Consenso com polígono único."""
        polygon = np.array([[0, 0], [100, 0], [100, 100], [0, 100]])
        mock_source = Mock()

        result = self.detector._find_consensus_polygon([polygon], mock_source)

        assert len(result) == 1
        np.testing.assert_array_equal(result[0], polygon)

    def test_consensus_consistent_polygons(self):
        """Test: Consenso com polígonos consistentes."""
        poly1 = np.array([[0, 0], [100, 0], [100, 100], [0, 100]])
        poly2 = np.array([[1, 1], [101, 1], [101, 101], [1, 101]])
        poly3 = np.array([[0, 0], [100, 0], [100, 100], [0, 100]])

        mock_source = Mock()

        result = self.detector._find_consensus_polygon([poly1, poly2, poly3], mock_source)

        assert len(result) == 1
        assert result[0] is not None

    def test_consensus_with_outlier(self):
        """Test: Consenso ignora outlier."""
        poly1 = np.array([[0, 0], [100, 0], [100, 100], [0, 100]])
        poly2 = np.array([[1, 1], [101, 1], [101, 101], [1, 101]])
        poly_outlier = np.array([[500, 500], [600, 500], [600, 600], [500, 600]])
        poly4 = np.array([[0, 0], [100, 0], [100, 100], [0, 100]])

        mock_source = Mock()

        result = self.detector._find_consensus_polygon(
            [poly1, poly2, poly_outlier, poly4], mock_source
        )

        assert len(result) == 1
        # O resultado deve estar próximo do grupo principal (0,0)-(100,100)
        assert np.mean(result[0]) < 200

    def test_consensus_empty_list_creates_default(self):
        """Test: Lista vazia gera polígono padrão."""
        mock_cap = Mock()
        mock_cap.get.side_effect = lambda prop: 640 if prop == cv2.CAP_PROP_FRAME_WIDTH else 480

        mock_source = Mock()
        mock_source._cap = mock_cap

        result = self.detector._find_consensus_polygon([], mock_source)

        assert len(result) == 1
        # Polígono padrão deve ter 4 pontos
        assert result[0].shape == (4, 2)
        # Deve ter margens (10%)
        assert result[0][0][0] == 64  # 10% de 640
        assert result[0][0][1] == 48  # 10% de 480

    def test_consensus_empty_list_no_cap(self):
        """Test: Lista vazia sem cap retorna lista vazia."""
        mock_source = Mock(spec=[])  # sem atributo _cap

        result = self.detector._find_consensus_polygon([], mock_source)

        assert len(result) == 0


class TestAquariumDetectorDetectAquariums(unittest.TestCase):
    """Testes do método principal detect_aquariums."""

    def setUp(self):
        """Setup: Criar detector mock."""
        with patch("zebtrack.core.aquarium_detector.YOLO"):
            self.detector = AquariumDetector("fake_model.pt", mode="seg")

    @patch("zebtrack.core.aquarium_detector.VideoFileSource")
    def test_detect_aquariums_seg_mode(self, mock_video_source):
        """Test: Detecção em modo segmentação."""
        # Mock video source
        mock_source_instance = Mock()
        mock_source_instance.get_frame.side_effect = [
            (True, np.zeros((480, 640, 3), dtype=np.uint8)),
            (True, np.zeros((480, 640, 3), dtype=np.uint8)),
            (False, None),
        ]
        mock_video_source.return_value = mock_source_instance

        # Mock model predictions
        mask = np.array([[50, 50], [590, 50], [590, 430], [50, 430]])
        mock_box = Mock()
        mock_box.conf = 0.95
        mock_box.cls = 0

        mock_result = Mock()
        mock_result.masks = Mock()
        mock_result.masks.xy = [mask]
        mock_result.boxes = [mock_box]

        with patch.object(self.detector.model, "predict") as mock_predict:
            mock_predict.return_value = [mock_result]

            result = self.detector.detect_aquariums("fake_video.mp4", stabilization_frames=2)

            assert len(result) == 1
            assert result[0] is not None

    @patch("zebtrack.core.aquarium_detector.VideoFileSource")
    def test_detect_aquariums_det_mode(self, mock_video_source):
        """Test: Detecção em modo detecção."""
        with patch("zebtrack.core.aquarium_detector.YOLO"):
            detector = AquariumDetector("fake_model.pt", mode="det")

        # Mock video source
        mock_source_instance = Mock()
        mock_source_instance.get_frame.side_effect = [
            (True, np.zeros((480, 640, 3), dtype=np.uint8)),
            (True, np.zeros((480, 640, 3), dtype=np.uint8)),
            (False, None),
        ]
        mock_video_source.return_value = mock_source_instance

        # Mock detection boxes
        mock_box = Mock()
        mock_box.xyxy = [np.array([50, 50, 300, 300])]
        mock_box.conf = 0.90

        mock_result = Mock()
        mock_result.boxes = [mock_box]
        mock_result.masks = None

        with patch.object(detector.model, "predict") as mock_predict:
            mock_predict.return_value = [mock_result]

            result = detector.detect_aquariums("fake_video.mp4", stabilization_frames=2)

            assert len(result) == 1
            assert result[0] is not None

    @patch("zebtrack.core.aquarium_detector.VideoFileSource")
    def test_detect_aquariums_with_path_object(self, mock_video_source):
        """Test: Detecção com Path object."""
        mock_source_instance = Mock()
        mock_source_instance.get_frame.side_effect = [(False, None)]
        mock_source_instance._cap = Mock()
        mock_source_instance._cap.get.side_effect = (
            lambda prop: 640 if prop == cv2.CAP_PROP_FRAME_WIDTH else 480
        )
        mock_video_source.return_value = mock_source_instance

        with patch.object(self.detector.model, "predict"):
            result = self.detector.detect_aquariums(Path("fake_video.mp4"), stabilization_frames=1)

            # Should create default polygon
            assert len(result) == 1

    @patch("zebtrack.core.aquarium_detector.VideoFileSource")
    def test_detect_aquariums_video_read_error(self, mock_video_source):
        """Test: Error handling quando leitura de vídeo falha."""
        mock_source_instance = Mock()
        mock_source_instance.get_frame.side_effect = Exception("Video read error")
        mock_video_source.return_value = mock_source_instance

        result = self.detector.detect_aquariums("fake_video.mp4")

        assert len(result) == 0

    @patch("zebtrack.core.aquarium_detector.VideoFileSource")
    def test_detect_aquariums_source_released(self, mock_video_source):
        """Test: Garantir que source é sempre liberado."""
        mock_source_instance = Mock()
        mock_source_instance.get_frame.side_effect = Exception("Error")
        mock_video_source.return_value = mock_source_instance

        with patch.object(self.detector.model, "predict"):
            result = self.detector.detect_aquariums("fake_video.mp4")

            # Should always call release
            mock_source_instance.release.assert_called_once()

    @patch("zebtrack.core.aquarium_detector.VideoFileSource")
    def test_detect_aquariums_stabilization_frames(self, mock_video_source):
        """Test: Respeita parâmetro stabilization_frames."""
        mock_source_instance = Mock()
        frames_returned = []
        for i in range(15):  # Mais frames do que necessário
            frames_returned.append((True, np.zeros((480, 640, 3), dtype=np.uint8)))
        frames_returned.append((False, None))
        mock_source_instance.get_frame.side_effect = frames_returned
        mock_video_source.return_value = mock_source_instance

        mask = np.array([[50, 50], [590, 50], [590, 430], [50, 430]])
        mock_box = Mock()
        mock_box.conf = 0.95
        mock_box.cls = 0

        mock_result = Mock()
        mock_result.masks = Mock()
        mock_result.masks.xy = [mask]
        mock_result.boxes = [mock_box]

        with patch.object(self.detector.model, "predict") as mock_predict:
            mock_predict.return_value = [mock_result]

            result = self.detector.detect_aquariums("fake_video.mp4", stabilization_frames=5)

            # Should only process 5 frames
            assert mock_predict.call_count == 5

    @patch("zebtrack.core.aquarium_detector.VideoFileSource")
    def test_detect_aquariums_no_valid_detections(self, mock_video_source):
        """Test: Handling quando não há detecções válidas."""
        mock_source_instance = Mock()
        mock_source_instance.get_frame.side_effect = [
            (True, np.zeros((480, 640, 3), dtype=np.uint8)),
            (True, np.zeros((480, 640, 3), dtype=np.uint8)),
            (False, None),
        ]
        mock_source_instance._cap = Mock()
        mock_source_instance._cap.get.side_effect = (
            lambda prop: 640 if prop == cv2.CAP_PROP_FRAME_WIDTH else 480
        )
        mock_video_source.return_value = mock_source_instance

        # Mock sem detecções
        mock_result = Mock()
        mock_result.masks = None
        mock_result.boxes = None

        with patch.object(self.detector.model, "predict") as mock_predict:
            mock_predict.return_value = [mock_result]

            result = self.detector.detect_aquariums("fake_video.mp4", stabilization_frames=2)

            # Should create default polygon
            assert len(result) == 1


if __name__ == "__main__":
    unittest.main()
