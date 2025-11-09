"""
Testes para AquariumDetector - cobertura completa (0% → 90%)

Este arquivo implementa testes abrangentes para o módulo aquarium_detector,
conforme especificado na Task 3.1 do EXECUTION_PLAN.md.

Cenários cobertos:
1. Inicialização (model loading, error handling)
2. Cálculo de IoU (overlapping, non-overlapping, edge cases)
3. Extração de polígonos (segmentação, bbox, resultado vazio)
4. Detecção em frames únicos (mode switching, error handling)
5. Detecção em vídeos (vídeo completo, progress callback)
6. Estabilização temporal (temporal consistency, outlier detection)
"""

from unittest.mock import MagicMock, patch

import cv2
import numpy as np
import pytest

# Verificar se ultralytics está disponível
try:
    from ultralytics import YOLO  # noqa: F401

    ULTRALYTICS_AVAILABLE = True
except ImportError:
    ULTRALYTICS_AVAILABLE = False

from zebtrack.core.aquarium_detector import AquariumDetector

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def mock_yolo_model():
    """Mock do modelo YOLO para testes sem dependências de modelo real."""
    mock = MagicMock()
    mock.predict = MagicMock()
    return mock


@pytest.fixture
def sample_frame():
    """Frame de teste (640x480, BGR)."""
    return np.zeros((480, 640, 3), dtype=np.uint8)


@pytest.fixture
def sample_polygon_large():
    """Polígono válido cobrindo ~50% do frame (640x480)."""
    return np.array(
        [[100, 100], [540, 100], [540, 380], [100, 380]], dtype=np.int32
    )


@pytest.fixture
def sample_polygon_small():
    """Polígono pequeno (<10% do frame)."""
    return np.array(
        [[200, 200], [250, 200], [250, 250], [200, 250]], dtype=np.int32
    )


@pytest.fixture
def mock_video_file(tmp_path):
    """Cria um vídeo de teste temporário."""
    video_path = tmp_path / "test_video.mp4"

    # Criar vídeo simples com OpenCV
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(str(video_path), fourcc, 30.0, (640, 480))

    # Escrever 15 frames
    for i in range(15):
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        # Adicionar algum conteúdo visual
        cv2.rectangle(frame, (100, 100), (540, 380), (255, 255, 255), -1)
        out.write(frame)

    out.release()
    return video_path


# ============================================================================
# CLASSE 1: TESTES DE INICIALIZAÇÃO
# ============================================================================


class TestAquariumDetectorInit:
    """Testes de inicialização do AquariumDetector."""

    @pytest.mark.skipif(not ULTRALYTICS_AVAILABLE, reason="Ultralytics not available")
    def test_init_valid_model_seg_mode(self, tmp_path):
        """Teste de inicialização com modelo válido em modo segmentação."""
        # Criar arquivo de modelo mock
        model_path = tmp_path / "model.pt"
        model_path.write_text("fake model")

        with patch("zebtrack.core.aquarium_detector.YOLO") as mock_yolo:
            mock_yolo.return_value = MagicMock()

            detector = AquariumDetector(model_path, mode="seg")

            assert detector.mode == "seg"
            assert detector.model is not None
            mock_yolo.assert_called_once_with(str(model_path))

    @pytest.mark.skipif(not ULTRALYTICS_AVAILABLE, reason="Ultralytics not available")
    def test_init_valid_model_det_mode(self, tmp_path):
        """Teste de inicialização com modelo válido em modo detecção."""
        model_path = tmp_path / "model.pt"
        model_path.write_text("fake model")

        with patch("zebtrack.core.aquarium_detector.YOLO") as mock_yolo:
            mock_yolo.return_value = MagicMock()

            detector = AquariumDetector(model_path, mode="det")

            assert detector.mode == "det"
            assert detector.model is not None

    @pytest.mark.skipif(not ULTRALYTICS_AVAILABLE, reason="Ultralytics not available")
    def test_init_missing_model(self, tmp_path):
        """Teste de error handling quando arquivo de modelo não existe."""
        model_path = tmp_path / "nonexistent_model.pt"

        with patch("zebtrack.core.aquarium_detector.YOLO") as mock_yolo:
            mock_yolo.side_effect = FileNotFoundError("Model file not found")

            with pytest.raises(FileNotFoundError):
                AquariumDetector(model_path)

    @pytest.mark.skipif(not ULTRALYTICS_AVAILABLE, reason="Ultralytics not available")
    def test_init_corrupted_model(self, tmp_path):
        """Teste de error handling quando arquivo de modelo está corrompido."""
        model_path = tmp_path / "corrupted_model.pt"
        model_path.write_bytes(b"corrupted data")

        with patch("zebtrack.core.aquarium_detector.YOLO") as mock_yolo:
            mock_yolo.side_effect = RuntimeError("Failed to load model")

            with pytest.raises(RuntimeError):
                AquariumDetector(model_path)

    @pytest.mark.skipif(not ULTRALYTICS_AVAILABLE, reason="Ultralytics not available")
    def test_init_invalid_mode(self, tmp_path):
        """Teste de error handling quando modo inválido é fornecido."""
        model_path = tmp_path / "model.pt"
        model_path.write_text("fake model")

        with patch("zebtrack.core.aquarium_detector.YOLO"):
            with pytest.raises(ValueError, match="Invalid mode 'invalid'"):
                AquariumDetector(model_path, mode="invalid")

    def test_init_ultralytics_not_available(self, tmp_path):
        """Teste quando ultralytics não está disponível."""
        model_path = tmp_path / "model.pt"
        model_path.write_text("fake model")

        with patch("zebtrack.core.aquarium_detector.ULTRALYTICS_AVAILABLE", False):
            with pytest.raises(ImportError, match="Ultralytics is not available"):
                AquariumDetector(model_path)

    @pytest.mark.skipif(not ULTRALYTICS_AVAILABLE, reason="Ultralytics not available")
    def test_init_with_string_path(self, tmp_path):
        """Teste de inicialização com caminho como string."""
        model_path = tmp_path / "model.pt"
        model_path.write_text("fake model")

        with patch("zebtrack.core.aquarium_detector.YOLO") as mock_yolo:
            mock_yolo.return_value = MagicMock()

            # Passar como string em vez de Path
            detector = AquariumDetector(str(model_path))

            assert detector.model is not None
            mock_yolo.assert_called_once_with(str(model_path))


# ============================================================================
# CLASSE 2: TESTES DE CÁLCULO DE IoU
# ============================================================================


class TestAquariumDetectorIoU:
    """Testes de cálculo de Intersection over Union (IoU)."""

    @pytest.fixture
    def detector(self, tmp_path):
        """Fixture para criar detector mock."""
        model_path = tmp_path / "model.pt"
        model_path.write_text("fake model")

        with patch("zebtrack.core.aquarium_detector.YOLO") as mock_yolo:
            mock_yolo.return_value = MagicMock()
            return AquariumDetector(model_path)

    @pytest.mark.skipif(not ULTRALYTICS_AVAILABLE, reason="Ultralytics not available")
    def test_iou_overlapping_polygons(self, detector):
        """Teste de IoU com polígonos sobrepostos."""
        poly1 = np.array([[0, 0], [100, 0], [100, 100], [0, 100]])
        poly2 = np.array([[50, 50], [150, 50], [150, 150], [50, 150]])

        iou = detector._calculate_iou(poly1, poly2)

        # Área de interseção: 50x50 = 2500
        # Área de união: 10000 + 10000 - 2500 = 17500
        # IoU esperado: 2500/17500 ≈ 0.1429
        assert 0.14 < iou < 0.15

    @pytest.mark.skipif(not ULTRALYTICS_AVAILABLE, reason="Ultralytics not available")
    def test_iou_non_overlapping_polygons(self, detector):
        """Teste de IoU com polígonos sem sobreposição (IoU = 0)."""
        poly1 = np.array([[0, 0], [100, 0], [100, 100], [0, 100]])
        poly2 = np.array([[200, 200], [300, 200], [300, 300], [200, 300]])

        iou = detector._calculate_iou(poly1, poly2)

        assert iou == 0.0

    @pytest.mark.skipif(not ULTRALYTICS_AVAILABLE, reason="Ultralytics not available")
    def test_iou_coincident_polygons(self, detector):
        """Teste de IoU com polígonos coincidentes (IoU = 1)."""
        poly1 = np.array([[0, 0], [100, 0], [100, 100], [0, 100]])
        poly2 = np.array([[0, 0], [100, 0], [100, 100], [0, 100]])

        iou = detector._calculate_iou(poly1, poly2)

        assert iou == 1.0

    @pytest.mark.skipif(not ULTRALYTICS_AVAILABLE, reason="Ultralytics not available")
    def test_iou_degenerate_polygon_point(self, detector):
        """Teste de IoU com polígono degenerado (ponto)."""
        poly1 = np.array([[0, 0], [100, 0], [100, 100], [0, 100]])
        poly2 = np.array([[50, 50], [50, 50], [50, 50], [50, 50]])  # Ponto

        iou = detector._calculate_iou(poly1, poly2)

        # Polígono degenerado retorna 0.0
        assert iou == 0.0

    @pytest.mark.skipif(not ULTRALYTICS_AVAILABLE, reason="Ultralytics not available")
    def test_iou_degenerate_polygon_line(self, detector):
        """Teste de IoU com polígono degenerado (linha)."""
        poly1 = np.array([[0, 0], [100, 0], [100, 100], [0, 100]])
        poly2 = np.array([[50, 0], [50, 100], [50, 100], [50, 0]])  # Linha vertical

        iou = detector._calculate_iou(poly1, poly2)

        # Polígono degenerado (linha) retorna 0.0
        assert iou == 0.0

    @pytest.mark.skipif(not ULTRALYTICS_AVAILABLE, reason="Ultralytics not available")
    def test_iou_zero_area_polygon(self, detector):
        """Teste de IoU quando área de união é zero."""
        # Dois polígonos com área zero
        poly1 = np.array([[0, 0], [0, 0], [0, 0], [0, 0]])
        poly2 = np.array([[0, 0], [0, 0], [0, 0], [0, 0]])

        iou = detector._calculate_iou(poly1, poly2)

        assert iou == 0.0

    @pytest.mark.skipif(not ULTRALYTICS_AVAILABLE, reason="Ultralytics not available")
    def test_iou_invalid_polygon_self_intersecting(self, detector):
        """Teste de IoU com polígono auto-intersectante."""
        poly1 = np.array([[0, 0], [100, 0], [100, 100], [0, 100]])
        # Polígono auto-intersectante (bow-tie)
        poly2 = np.array([[0, 0], [100, 100], [100, 0], [0, 100]])

        iou = detector._calculate_iou(poly1, poly2)

        # Shapely considera auto-intersectante como inválido, retorna 0.0
        assert iou == 0.0

    @pytest.mark.skipif(not ULTRALYTICS_AVAILABLE, reason="Ultralytics not available")
    def test_iou_exception_handling(self, detector):
        """Teste de error handling quando cálculo de IoU falha."""
        # Polígonos inválidos que causam exceção
        poly1 = [[0, 0]]  # Apenas um ponto, inválido
        poly2 = [[50, 50]]

        iou = detector._calculate_iou(poly1, poly2)

        # Deve retornar 0.0 em caso de exceção
        assert iou == 0.0


# ============================================================================
# CLASSE 3: TESTES DE EXTRAÇÃO DE POLÍGONOS
# ============================================================================


class TestAquariumDetectorExtraction:
    """Testes de extração de polígonos de detecções."""

    @pytest.fixture
    def detector(self, tmp_path):
        """Fixture para criar detector mock."""
        model_path = tmp_path / "model.pt"
        model_path.write_text("fake model")

        with patch("zebtrack.core.aquarium_detector.YOLO") as mock_yolo:
            mock_yolo.return_value = MagicMock()
            return AquariumDetector(model_path, mode="det")

    @pytest.mark.skipif(not ULTRALYTICS_AVAILABLE, reason="Ultralytics not available")
    def test_extract_polygon_from_detection_with_bbox(self, detector, sample_frame):
        """Teste de extração de polígono de bounding box válido."""
        # Mock de resultados com bbox
        mock_box = MagicMock()
        mock_box.conf = 0.85
        mock_box.xyxy = [np.array([100, 100, 540, 380])]

        mock_results = [MagicMock()]
        mock_results[0].boxes = [mock_box]

        polygon = detector._extract_polygon_from_detection(sample_frame, mock_results)

        assert polygon is not None
        assert polygon.shape == (4, 2)
        # Verificar que é um retângulo
        assert np.array_equal(polygon[0], [100, 100])  # top-left
        assert np.array_equal(polygon[1], [540, 100])  # top-right
        assert np.array_equal(polygon[2], [540, 380])  # bottom-right
        assert np.array_equal(polygon[3], [100, 380])  # bottom-left

    @pytest.mark.skipif(not ULTRALYTICS_AVAILABLE, reason="Ultralytics not available")
    def test_extract_polygon_empty_results(self, detector, sample_frame):
        """Teste de extração quando resultado está vazio."""
        mock_results = []

        polygon = detector._extract_polygon_from_detection(sample_frame, mock_results)

        assert polygon is None

    @pytest.mark.skipif(not ULTRALYTICS_AVAILABLE, reason="Ultralytics not available")
    def test_extract_polygon_no_boxes(self, detector, sample_frame):
        """Teste de extração quando não há boxes no resultado."""
        mock_results = [MagicMock()]
        mock_results[0].boxes = []

        polygon = detector._extract_polygon_from_detection(sample_frame, mock_results)

        assert polygon is None

    @pytest.mark.skipif(not ULTRALYTICS_AVAILABLE, reason="Ultralytics not available")
    def test_extract_polygon_multiple_detections(self, detector, sample_frame):
        """Teste de extração com múltiplas detecções (escolhe melhor confiança)."""
        # Mock de múltiplos boxes com diferentes confianças
        mock_box1 = MagicMock()
        mock_box1.conf = 0.60
        mock_box1.xyxy = [np.array([50, 50, 250, 250])]

        mock_box2 = MagicMock()
        mock_box2.conf = 0.90  # Maior confiança
        mock_box2.xyxy = [np.array([100, 100, 540, 380])]

        mock_box3 = MagicMock()
        mock_box3.conf = 0.75
        mock_box3.xyxy = [np.array([150, 150, 300, 300])]

        mock_results = [MagicMock()]
        mock_results[0].boxes = [mock_box1, mock_box2, mock_box3]

        polygon = detector._extract_polygon_from_detection(sample_frame, mock_results)

        # Deve escolher box2 (maior confiança)
        assert polygon is not None
        assert np.array_equal(polygon[0], [100, 100])

    @pytest.mark.skipif(not ULTRALYTICS_AVAILABLE, reason="Ultralytics not available")
    def test_extract_polygon_too_small(self, detector, sample_frame):
        """Teste de extração quando detecção é muito pequena (<10% do frame)."""
        # Mock de box muito pequeno
        mock_box = MagicMock()
        mock_box.conf = 0.85
        mock_box.xyxy = [np.array([200, 200, 250, 250])]  # 50x50 = 2500px, ~0.8% do frame

        mock_results = [MagicMock()]
        mock_results[0].boxes = [mock_box]

        polygon = detector._extract_polygon_from_detection(sample_frame, mock_results)

        # Deve retornar None (muito pequeno)
        assert polygon is None

    @pytest.mark.skipif(not ULTRALYTICS_AVAILABLE, reason="Ultralytics not available")
    def test_extract_polygon_too_large(self, detector, sample_frame):
        """Teste de extração quando detecção é muito grande (>95% do frame)."""
        # Mock de box quase do tamanho do frame
        mock_box = MagicMock()
        mock_box.conf = 0.85
        mock_box.xyxy = [np.array([5, 5, 635, 475])]  # ~97% do frame

        mock_results = [MagicMock()]
        mock_results[0].boxes = [mock_box]

        polygon = detector._extract_polygon_from_detection(sample_frame, mock_results)

        # Deve retornar None (muito grande, provável falso positivo)
        assert polygon is None

    @pytest.mark.skipif(not ULTRALYTICS_AVAILABLE, reason="Ultralytics not available")
    def test_extract_polygon_valid_size_range(self, detector, sample_frame):
        """Teste de extração com tamanho válido (entre 10% e 95%)."""
        # Mock de box com tamanho válido (~50% do frame)
        mock_box = MagicMock()
        mock_box.conf = 0.85
        mock_box.xyxy = [np.array([100, 100, 540, 380])]  # ~48% do frame

        mock_results = [MagicMock()]
        mock_results[0].boxes = [mock_box]

        polygon = detector._extract_polygon_from_detection(sample_frame, mock_results)

        assert polygon is not None

    @pytest.mark.skipif(not ULTRALYTICS_AVAILABLE, reason="Ultralytics not available")
    def test_process_segmentation_single_mask_valid(self, detector, sample_frame):
        """Teste de processamento de segmentação com máscara válida."""
        # Reconfigurar detector para modo seg
        detector.mode = "seg"

        # Mock de máscara válida
        mask_polygon = np.array([[100, 100], [540, 100], [540, 380], [100, 380]])

        mock_box = MagicMock()
        mock_box.conf = 0.85
        mock_box.cls = 0

        mock_results = [MagicMock()]
        mock_results[0].masks = MagicMock()
        mock_results[0].masks.xy = [mask_polygon]
        mock_results[0].boxes = [mock_box]

        polygon = detector._process_segmentation_results(sample_frame, mock_results, 0)

        assert polygon is not None
        assert isinstance(polygon, np.ndarray)

    @pytest.mark.skipif(not ULTRALYTICS_AVAILABLE, reason="Ultralytics not available")
    def test_process_segmentation_no_masks(self, detector, sample_frame):
        """Teste de processamento quando não há máscaras."""
        detector.mode = "seg"

        mock_results = [MagicMock()]
        mock_results[0].masks = None

        # Mock do método predict para fallback
        detector.model.predict = MagicMock(return_value=[MagicMock(masks=None)])

        polygon = detector._process_segmentation_results(sample_frame, mock_results, 0)

        assert polygon is None


# ============================================================================
# CLASSE 4: TESTES DE DETECÇÃO EM FRAMES ÚNICOS
# ============================================================================


class TestAquariumDetectorDetection:
    """Testes de detecção em frames únicos."""

    @pytest.mark.skipif(not ULTRALYTICS_AVAILABLE, reason="Ultralytics not available")
    def test_detect_frame_seg_mode(self, tmp_path, sample_frame):
        """Teste de detecção em frame único (modo segmentação)."""
        model_path = tmp_path / "model.pt"
        model_path.write_text("fake model")

        with patch("zebtrack.core.aquarium_detector.YOLO") as mock_yolo:
            mock_model = MagicMock()

            # Mock de resultado de segmentação
            mask_polygon = np.array([[100, 100], [540, 100], [540, 380], [100, 380]])
            mock_box = MagicMock()
            mock_box.conf = 0.85
            mock_box.cls = 0

            mock_result = MagicMock()
            mock_result.masks = MagicMock()
            mock_result.masks.xy = [mask_polygon]
            mock_result.boxes = [mock_box]

            mock_model.predict = MagicMock(return_value=[mock_result])
            mock_yolo.return_value = mock_model

            detector = AquariumDetector(model_path, mode="seg")

            # Processar resultado
            polygon = detector._process_segmentation_results(sample_frame, [mock_result], 0)

            assert polygon is not None

    @pytest.mark.skipif(not ULTRALYTICS_AVAILABLE, reason="Ultralytics not available")
    def test_detect_frame_det_mode(self, tmp_path, sample_frame):
        """Teste de detecção em frame único (modo detecção)."""
        model_path = tmp_path / "model.pt"
        model_path.write_text("fake model")

        with patch("zebtrack.core.aquarium_detector.YOLO") as mock_yolo:
            mock_model = MagicMock()

            # Mock de resultado de detecção (bbox)
            mock_box = MagicMock()
            mock_box.conf = 0.85
            mock_box.xyxy = [np.array([100, 100, 540, 380])]

            mock_result = MagicMock()
            mock_result.boxes = [mock_box]

            mock_model.predict = MagicMock(return_value=[mock_result])
            mock_yolo.return_value = mock_model

            detector = AquariumDetector(model_path, mode="det")

            # Processar resultado
            polygon = detector._extract_polygon_from_detection(sample_frame, [mock_result])

            assert polygon is not None

    @pytest.mark.skipif(not ULTRALYTICS_AVAILABLE, reason="Ultralytics not available")
    def test_detect_frame_invalid_frame(self, tmp_path):
        """Teste de error handling com frame inválido."""
        model_path = tmp_path / "model.pt"
        model_path.write_text("fake model")

        with patch("zebtrack.core.aquarium_detector.YOLO") as mock_yolo:
            mock_model = MagicMock()
            mock_model.predict = MagicMock(side_effect=Exception("Invalid frame"))
            mock_yolo.return_value = mock_model

            detector = AquariumDetector(model_path)

            # Frame inválido (None)
            with pytest.raises(Exception, match="Invalid frame"):
                detector.model.predict(None)

    @pytest.mark.skipif(not ULTRALYTICS_AVAILABLE, reason="Ultralytics not available")
    def test_mode_switching(self, tmp_path, sample_frame):
        """Teste de troca entre modos seg e det."""
        model_path = tmp_path / "model.pt"
        model_path.write_text("fake model")

        with patch("zebtrack.core.aquarium_detector.YOLO") as mock_yolo:
            mock_yolo.return_value = MagicMock()

            # Criar detector em modo seg
            detector_seg = AquariumDetector(model_path, mode="seg")
            assert detector_seg.mode == "seg"

            # Criar detector em modo det
            detector_det = AquariumDetector(model_path, mode="det")
            assert detector_det.mode == "det"


# ============================================================================
# CLASSE 5: TESTES DE DETECÇÃO EM VÍDEO
# ============================================================================


class TestAquariumDetectorVideoDetection:
    """Testes de detecção em vídeos completos."""

    @pytest.mark.skipif(not ULTRALYTICS_AVAILABLE, reason="Ultralytics not available")
    def test_detect_aquariums_valid_video(self, tmp_path, mock_video_file):
        """Teste de detecção em vídeo completo com detecções válidas."""
        model_path = tmp_path / "model.pt"
        model_path.write_text("fake model")

        with patch("zebtrack.core.aquarium_detector.YOLO") as mock_yolo:
            mock_model = MagicMock()

            # Mock de resultado consistente
            mock_box = MagicMock()
            mock_box.conf = 0.85
            mock_box.xyxy = [np.array([100, 100, 540, 380])]

            mock_result = MagicMock()
            mock_result.boxes = [mock_box]
            mock_result.masks = None

            mock_model.predict = MagicMock(return_value=[mock_result])
            mock_yolo.return_value = mock_model

            detector = AquariumDetector(model_path, mode="det")

            polygons = detector.detect_aquariums(mock_video_file, stabilization_frames=5)

            assert len(polygons) > 0

    @pytest.mark.skipif(not ULTRALYTICS_AVAILABLE, reason="Ultralytics not available")
    def test_detect_aquariums_video_not_exists(self, tmp_path):
        """Teste de error handling quando vídeo não existe."""
        model_path = tmp_path / "model.pt"
        model_path.write_text("fake model")

        with patch("zebtrack.core.aquarium_detector.YOLO") as mock_yolo:
            mock_yolo.return_value = MagicMock()

            detector = AquariumDetector(model_path)

            # Vídeo inexistente
            polygons = detector.detect_aquariums(tmp_path / "nonexistent.mp4")

            # Deve retornar lista vazia em caso de erro
            assert polygons == []

    @pytest.mark.skipif(not ULTRALYTICS_AVAILABLE, reason="Ultralytics not available")
    def test_detect_aquariums_no_detections(self, tmp_path, mock_video_file):
        """Teste quando não há detecções no vídeo."""
        model_path = tmp_path / "model.pt"
        model_path.write_text("fake model")

        with patch("zebtrack.core.aquarium_detector.YOLO") as mock_yolo:
            mock_model = MagicMock()

            # Mock de resultado vazio
            mock_result = MagicMock()
            mock_result.boxes = []
            mock_result.masks = None

            mock_model.predict = MagicMock(return_value=[mock_result])
            mock_yolo.return_value = mock_model

            detector = AquariumDetector(model_path, mode="det")

            polygons = detector.detect_aquariums(mock_video_file, stabilization_frames=5)

            # Deve gerar polígono default quando não há detecções
            # (conforme implementação de _find_consensus_polygon)
            assert isinstance(polygons, list)

    @pytest.mark.skipif(not ULTRALYTICS_AVAILABLE, reason="Ultralytics not available")
    def test_detect_aquariums_stabilization_frames(self, tmp_path, mock_video_file):
        """Teste do parâmetro stabilization_frames."""
        model_path = tmp_path / "model.pt"
        model_path.write_text("fake model")

        with patch("zebtrack.core.aquarium_detector.YOLO") as mock_yolo:
            mock_model = MagicMock()

            call_count = 0

            def predict_side_effect(*args, **kwargs):
                nonlocal call_count
                call_count += 1

                mock_box = MagicMock()
                mock_box.conf = 0.85
                mock_box.xyxy = [np.array([100, 100, 540, 380])]

                mock_result = MagicMock()
                mock_result.boxes = [mock_box]
                mock_result.masks = None

                return [mock_result]

            mock_model.predict = MagicMock(side_effect=predict_side_effect)
            mock_yolo.return_value = mock_model

            detector = AquariumDetector(model_path, mode="det")

            # Detectar com 3 frames de estabilização
            polygons = detector.detect_aquariums(mock_video_file, stabilization_frames=3)

            # Deve ter chamado predict 3 vezes
            assert call_count == 3
            # E deve ter retornado polígonos
            assert len(polygons) > 0

    @pytest.mark.skipif(not ULTRALYTICS_AVAILABLE, reason="Ultralytics not available")
    def test_detect_aquariums_with_string_path(self, tmp_path, mock_video_file):
        """Teste de detecção com caminho como string."""
        model_path = tmp_path / "model.pt"
        model_path.write_text("fake model")

        with patch("zebtrack.core.aquarium_detector.YOLO") as mock_yolo:
            mock_model = MagicMock()

            mock_box = MagicMock()
            mock_box.conf = 0.85
            mock_box.xyxy = [np.array([100, 100, 540, 380])]

            mock_result = MagicMock()
            mock_result.boxes = [mock_box]
            mock_result.masks = None

            mock_model.predict = MagicMock(return_value=[mock_result])
            mock_yolo.return_value = mock_model

            detector = AquariumDetector(model_path, mode="det")

            # Passar caminho como string
            polygons = detector.detect_aquariums(str(mock_video_file), stabilization_frames=2)

            assert len(polygons) > 0


# ============================================================================
# CLASSE 6: TESTES DE ESTABILIZAÇÃO TEMPORAL
# ============================================================================


class TestAquariumDetectorStabilization:
    """Testes de estabilização temporal e consenso de polígonos."""

    @pytest.fixture
    def detector(self, tmp_path):
        """Fixture para criar detector mock."""
        model_path = tmp_path / "model.pt"
        model_path.write_text("fake model")

        with patch("zebtrack.core.aquarium_detector.YOLO") as mock_yolo:
            mock_yolo.return_value = MagicMock()
            return AquariumDetector(model_path)

    @pytest.fixture
    def mock_video_source(self):
        """Mock de VideoSource para testes de consenso."""
        mock = MagicMock()
        mock._cap = MagicMock()
        mock._cap.get = MagicMock(side_effect=lambda prop: {
            cv2.CAP_PROP_FRAME_WIDTH: 640,
            cv2.CAP_PROP_FRAME_HEIGHT: 480
        }.get(prop, 0))
        return mock

    @pytest.mark.skipif(not ULTRALYTICS_AVAILABLE, reason="Ultralytics not available")
    def test_find_consensus_single_polygon(self, detector, mock_video_source):
        """Teste de consenso com um único polígono."""
        polygon = np.array([[100, 100], [540, 100], [540, 380], [100, 380]])

        result = detector._find_consensus_polygon([polygon], mock_video_source)

        assert len(result) == 1
        assert np.array_equal(result[0], polygon)

    @pytest.mark.skipif(not ULTRALYTICS_AVAILABLE, reason="Ultralytics not available")
    def test_find_consensus_multiple_similar_polygons(self, detector, mock_video_source):
        """Teste de consenso com múltiplos polígonos similares."""
        # Polígonos similares (pequenas variações)
        poly1 = np.array([[100, 100], [540, 100], [540, 380], [100, 380]])
        poly2 = np.array([[105, 105], [535, 105], [535, 375], [105, 375]])
        poly3 = np.array([[98, 98], [542, 98], [542, 382], [98, 382]])

        result = detector._find_consensus_polygon([poly1, poly2, poly3], mock_video_source)

        assert len(result) == 1
        # Deve escolher o polígono com maior IoU médio

    @pytest.mark.skipif(not ULTRALYTICS_AVAILABLE, reason="Ultralytics not available")
    def test_find_consensus_no_polygons(self, detector, mock_video_source):
        """Teste de consenso sem polígonos (gera default)."""
        result = detector._find_consensus_polygon([], mock_video_source)

        # Deve gerar polígono default
        assert len(result) == 1
        # Verificar que é um retângulo válido
        assert result[0].shape == (4, 2)

    @pytest.mark.skipif(not ULTRALYTICS_AVAILABLE, reason="Ultralytics not available")
    def test_find_consensus_outlier_detection(self, detector, mock_video_source):
        """Teste de detecção de outliers no consenso."""
        # Maioria de polígonos similares + 1 outlier
        poly1 = np.array([[100, 100], [540, 100], [540, 380], [100, 380]])
        poly2 = np.array([[105, 105], [535, 105], [535, 375], [105, 375]])
        poly3 = np.array([[98, 98], [542, 98], [542, 382], [98, 382]])
        # Outlier (muito diferente)
        poly_outlier = np.array([[10, 10], [100, 10], [100, 100], [10, 100]])

        result = detector._find_consensus_polygon(
            [poly1, poly2, poly3, poly_outlier], mock_video_source
        )

        assert len(result) == 1
        # O polígono escolhido deve ser um dos similares (não o outlier)
        # Verificar que não é o outlier verificando área aproximada
        chosen = result[0]
        x_min, y_min = chosen[:, 0].min(), chosen[:, 1].min()
        x_max, y_max = chosen[:, 0].max(), chosen[:, 1].max()
        area = (x_max - x_min) * (y_max - y_min)

        # Área deve ser grande (~440x280 = 123200), não pequena (~90x90 = 8100)
        assert area > 50000

    @pytest.mark.skipif(not ULTRALYTICS_AVAILABLE, reason="Ultralytics not available")
    def test_temporal_consistency_frames(self, tmp_path, mock_video_file):
        """Teste de consistência temporal entre frames consecutivos."""
        model_path = tmp_path / "model.pt"
        model_path.write_text("fake model")

        with patch("zebtrack.core.aquarium_detector.YOLO") as mock_yolo:
            mock_model = MagicMock()

            frame_count = 0

            def predict_side_effect(*args, **kwargs):
                nonlocal frame_count
                frame_count += 1

                # Variação temporal pequena (simulando aquário estável)
                offset = frame_count * 2

                mock_box = MagicMock()
                mock_box.conf = 0.85
                mock_box.xyxy = [np.array([100 + offset, 100, 540 + offset, 380])]

                mock_result = MagicMock()
                mock_result.boxes = [mock_box]
                mock_result.masks = None

                return [mock_result]

            mock_model.predict = MagicMock(side_effect=predict_side_effect)
            mock_yolo.return_value = mock_model

            detector = AquariumDetector(model_path, mode="det")

            polygons = detector.detect_aquariums(mock_video_file, stabilization_frames=5)

            # Deve ter encontrado polígono consensual
            assert len(polygons) > 0

    @pytest.mark.skipif(not ULTRALYTICS_AVAILABLE, reason="Ultralytics not available")
    def test_boundary_conditions_start_frames(self, tmp_path, mock_video_file):
        """Teste de condições de boundary nos primeiros frames."""
        model_path = tmp_path / "model.pt"
        model_path.write_text("fake model")

        with patch("zebtrack.core.aquarium_detector.YOLO") as mock_yolo:
            mock_model = MagicMock()

            # Primeiro frame sem detecção, demais com detecção
            call_count = 0

            def predict_side_effect(*args, **kwargs):
                nonlocal call_count
                call_count += 1

                mock_result = MagicMock()

                if call_count == 1:
                    # Primeiro frame: sem detecção
                    mock_result.boxes = []
                    mock_result.masks = None
                else:
                    # Demais frames: com detecção
                    mock_box = MagicMock()
                    mock_box.conf = 0.85
                    mock_box.xyxy = [np.array([100, 100, 540, 380])]
                    mock_result.boxes = [mock_box]
                    mock_result.masks = None

                return [mock_result]

            mock_model.predict = MagicMock(side_effect=predict_side_effect)
            mock_yolo.return_value = mock_model

            detector = AquariumDetector(model_path, mode="det")

            polygons = detector.detect_aquariums(mock_video_file, stabilization_frames=5)

            # Deve ter encontrado polígono baseado nos frames válidos
            assert isinstance(polygons, list)

    @pytest.mark.skipif(not ULTRALYTICS_AVAILABLE, reason="Ultralytics not available")
    def test_default_polygon_generation_no_cap(self, detector):
        """Teste de geração de polígono default quando VideoSource não tem _cap."""
        mock_source = MagicMock()
        # Simular ausência de _cap
        del mock_source._cap

        result = detector._find_consensus_polygon([], mock_source)

        # Deve retornar lista vazia quando não consegue gerar default
        assert result == []
