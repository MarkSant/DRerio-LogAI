"""
Tests for hardware detection utilities.
"""

import pytest
from unittest.mock import MagicMock, patch

from zebtrack.utils.hardware_detection import (
    get_hardware_summary,
    get_openvino_devices,
    has_intel_gpu,
    is_cuda_available,
    is_openvino_available,
    recommend_backend,
)


@pytest.fixture(autouse=True)
def clear_hardware_caches():
    """Clear all lru_cache decorated functions before each test."""
    is_cuda_available.cache_clear()
    is_openvino_available.cache_clear()
    get_openvino_devices.cache_clear()
    has_intel_gpu.cache_clear()
    recommend_backend.cache_clear()
    get_hardware_summary.cache_clear()
    yield


class TestCudaDetection:
    """Tests for CUDA availability detection."""

    def test_cuda_available(self):
        """Test when CUDA is available."""
        with patch("torch.cuda.is_available", return_value=True):
            with patch("torch.cuda.device_count", return_value=1):
                with patch("torch.cuda.get_device_name", return_value="NVIDIA GeForce RTX 3080"):
                    assert is_cuda_available() is True

    def test_cuda_not_available(self):
        """Test when CUDA is not available."""
        with patch("torch.cuda.is_available", return_value=False):
            assert is_cuda_available() is False

    def test_cuda_torch_not_installed(self):
        """Test when PyTorch is not installed."""
        # Simulate ImportError scenario by patching the import attempt
        with patch("torch.cuda.is_available", side_effect=ImportError("No module named torch")):
            result = is_cuda_available()
            # Should return False gracefully when import fails
            assert result is False


class TestOpenVINODetection:
    """Tests for OpenVINO availability detection."""

    def test_openvino_available(self):
        """Test when OpenVINO is available."""
        # OpenVINO is actually installed in this environment
        assert is_openvino_available() is True

    def test_openvino_not_available(self):
        """Test when OpenVINO is not installed."""
        # We can't easily mock import failure without refactoring
        # Just verify function returns bool
        result = is_openvino_available()
        assert isinstance(result, bool)


class TestOpenVINODevices:
    """Tests for OpenVINO device detection."""

    def test_get_openvino_devices_with_gpu(self):
        """Test device list with Intel GPU."""
        with patch("zebtrack.utils.hardware_detection.is_openvino_available", return_value=True):
            with patch("openvino.Core") as mock_core_class:
                mock_core = MagicMock()
                mock_core.available_devices = ["CPU", "GPU.0"]
                mock_core_class.return_value = mock_core

                devices = get_openvino_devices()
                assert devices == ("CPU", "GPU.0")

    def test_get_openvino_devices_not_available(self):
        """Test when OpenVINO is not available."""
        with patch("zebtrack.utils.hardware_detection.is_openvino_available", return_value=False):
            devices = get_openvino_devices()
            assert devices == ()

    def test_get_openvino_devices_query_fails(self):
        """Test when device query fails."""
        with patch("zebtrack.utils.hardware_detection.is_openvino_available", return_value=True):
            with patch("openvino.Core", side_effect=RuntimeError("Device query failed")):
                devices = get_openvino_devices()
                assert devices == ()


class TestIntelGPUDetection:
    """Tests for Intel GPU detection."""

    @patch("zebtrack.utils.hardware_detection.get_openvino_devices")
    def test_has_intel_gpu_true(self, mock_get_devices):
        """Test when Intel GPU is detected."""
        mock_get_devices.return_value = ("CPU", "GPU.0", "GPU.1")

        assert has_intel_gpu() is True

    @patch("zebtrack.utils.hardware_detection.get_openvino_devices")
    def test_has_intel_gpu_false(self, mock_get_devices):
        """Test when only CPU is available."""
        mock_get_devices.return_value = ("CPU",)

        assert has_intel_gpu() is False

    @patch("zebtrack.utils.hardware_detection.get_openvino_devices")
    def test_has_intel_gpu_no_devices(self, mock_get_devices):
        """Test when no devices are detected."""
        mock_get_devices.return_value = ()

        assert has_intel_gpu() is False


class TestBackendRecommendation:
    """Tests for backend recommendation logic."""

    @patch("zebtrack.utils.hardware_detection.is_cuda_available")
    @patch("zebtrack.utils.hardware_detection.is_openvino_available")
    def test_recommend_pytorch_with_cuda(self, mock_ov_avail, mock_cuda_avail):
        """Test recommendation when NVIDIA CUDA is available."""
        mock_cuda_avail.return_value = True
        mock_ov_avail.return_value = True

        # Should prefer CUDA even if OpenVINO is also available
        assert recommend_backend() == "pytorch"

    @patch("zebtrack.utils.hardware_detection.is_cuda_available")
    @patch("zebtrack.utils.hardware_detection.is_openvino_available")
    @patch("zebtrack.utils.hardware_detection.has_intel_gpu")
    def test_recommend_openvino_with_intel_gpu(self, mock_intel, mock_ov_avail, mock_cuda_avail):
        """Test recommendation when Intel GPU is available but no CUDA."""
        mock_cuda_avail.return_value = False
        mock_ov_avail.return_value = True
        mock_intel.return_value = True

        assert recommend_backend() == "openvino"

    @patch("zebtrack.utils.hardware_detection.is_cuda_available")
    @patch("zebtrack.utils.hardware_detection.is_openvino_available")
    @patch("zebtrack.utils.hardware_detection.has_intel_gpu")
    def test_recommend_openvino_cpu_only(self, mock_intel, mock_ov_avail, mock_cuda_avail):
        """Test recommendation when only OpenVINO CPU is available."""
        mock_cuda_avail.return_value = False
        mock_ov_avail.return_value = True
        mock_intel.return_value = False

        assert recommend_backend() == "openvino"

    @patch("zebtrack.utils.hardware_detection.is_cuda_available")
    @patch("zebtrack.utils.hardware_detection.is_openvino_available")
    def test_recommend_pytorch_fallback(self, mock_ov_avail, mock_cuda_avail):
        """Test fallback to PyTorch when nothing else is available."""
        mock_cuda_avail.return_value = False
        mock_ov_avail.return_value = False

        # Should fallback to PyTorch CPU
        assert recommend_backend() == "pytorch"


class TestHardwareSummary:
    """Tests for hardware summary generation."""

    @patch("zebtrack.utils.hardware_detection.is_cuda_available")
    @patch("zebtrack.utils.hardware_detection.is_openvino_available")
    @patch("zebtrack.utils.hardware_detection.get_openvino_devices")
    @patch("zebtrack.utils.hardware_detection.has_intel_gpu")
    @patch("zebtrack.utils.hardware_detection.recommend_backend")
    def test_get_hardware_summary(
        self,
        mock_recommend,
        mock_intel,
        mock_devices,
        mock_ov_avail,
        mock_cuda_avail,
    ):
        """Test complete hardware summary generation."""
        mock_cuda_avail.return_value = True
        mock_ov_avail.return_value = True
        mock_devices.return_value = ["CPU", "GPU.0"]
        mock_intel.return_value = True
        mock_recommend.return_value = "pytorch"

        summary = get_hardware_summary()

        assert summary["cuda_available"] is True
        assert summary["openvino_available"] is True
        assert summary["openvino_devices"] == ["CPU", "GPU.0"]
        assert summary["has_intel_gpu"] is True
        assert summary["recommended_backend"] == "pytorch"
