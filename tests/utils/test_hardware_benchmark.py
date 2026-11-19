"""Tests for ``zebtrack.utils.hardware_benchmark``.

The benchmark decides how a fresh install is configured (backend, device,
inference size, memory mode), so what is checked here is the DECISION each
function takes, on hardware that is described rather than owned: fake
``torch``/``openvino``/``psutil`` modules, a scripted ``VideoCapture`` and a
clock that advances by a fixed step, so every timing is exact.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import cv2
import numpy as np
import pytest

from zebtrack.paths import repo_root
from zebtrack.utils import hardware_benchmark as hb
from zebtrack.utils.hardware_benchmark import (
    BenchmarkRecommendation,
    BenchmarkResult,
    GPUType,
    HardwareProfile,
    SystemBenchmarkResult,
)

pytestmark = pytest.mark.unit

GIB = 1024**3
STEP_MS = 4.0  # every timed section lasts exactly this long under the fake clock
STEP_FPS = 250.0


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _Clock:
    """``time`` stand-in: each ``perf_counter()`` call is ``STEP_MS`` after the last."""

    def __init__(self) -> None:
        self._now = 0.0

    def perf_counter(self) -> float:
        self._now += STEP_MS / 1000
        return self._now


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> _Clock:
    fake = _Clock()
    monkeypatch.setattr(hb, "time", fake)
    return fake


class _Backend:
    """A scripted ``openvino`` module (``Core``, properties, compile, infer)."""

    def __init__(
        self,
        *,
        devices: tuple[str, ...] = ("CPU",),
        properties: dict[tuple[str, str], Any] | None = None,
        failing_devices: tuple[str, ...] = (),
        read_error: Exception | None = None,
    ) -> None:
        self.devices = list(devices)
        self.properties = properties or {}
        self.failing_devices = set(failing_devices)
        self.read_error = read_error
        self.read_paths: list[str] = []
        self.compile_calls: list[tuple[str, dict[str, Any]]] = []
        self.blobs: list[np.ndarray] = []

    def Core(self) -> _Backend:
        return self

    @property
    def available_devices(self) -> list[str]:
        return list(self.devices)

    def get_property(self, device: str, name: str) -> Any:
        if (device, name) not in self.properties:
            raise RuntimeError(f"{device} has no {name}")
        return self.properties[(device, name)]

    def read_model(self, path: str) -> str:
        if self.read_error is not None:
            raise self.read_error
        self.read_paths.append(path)
        return "model"

    def compile_model(self, model: str, device: str, config: dict[str, Any]) -> _Backend:
        self.compile_calls.append((device, dict(config)))
        if device in self.failing_devices:
            raise RuntimeError(f"cannot compile for {device}")
        return self

    def create_infer_request(self) -> _Backend:
        return self

    def infer(self, inputs: dict[int, np.ndarray]) -> None:
        self.blobs.append(inputs[0])

    def get_output_tensor(self, index: int) -> SimpleNamespace:
        return SimpleNamespace(data=np.zeros(4, dtype=np.float32))


def _install_openvino(monkeypatch: pytest.MonkeyPatch, backend: _Backend | None) -> None:
    """``None`` makes ``import openvino`` raise ImportError."""
    monkeypatch.setitem(sys.modules, "openvino", backend)


def _install_torch(
    monkeypatch: pytest.MonkeyPatch,
    *,
    available: bool = False,
    count: int = 0,
    name: str = "",
    memory_bytes: int | None = None,
    missing: bool = False,
) -> None:
    if missing:
        monkeypatch.setitem(sys.modules, "torch", None)
        return

    def _properties(index: int) -> SimpleNamespace:
        if memory_bytes is None:
            raise RuntimeError("no properties")
        return SimpleNamespace(total_memory=memory_bytes)

    cuda = SimpleNamespace(
        is_available=lambda: available,
        device_count=lambda: count,
        get_device_name=lambda index: name,
        get_device_properties=_properties,
    )
    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(cuda=cuda))


def _install_psutil(monkeypatch: pytest.MonkeyPatch, total_gb: float | None) -> None:
    if total_gb is None:
        monkeypatch.setitem(sys.modules, "psutil", None)
        return
    memory = SimpleNamespace(total=int(total_gb * GIB))
    monkeypatch.setitem(sys.modules, "psutil", SimpleNamespace(virtual_memory=lambda: memory))


@pytest.fixture
def bare_machine(monkeypatch: pytest.MonkeyPatch) -> None:
    """No torch, no OpenVINO, 16 GB of RAM, an 8-core "TestCPU"."""
    _install_torch(monkeypatch, missing=True)
    _install_openvino(monkeypatch, None)
    _install_psutil(monkeypatch, 16.0)
    monkeypatch.setattr("platform.processor", lambda: "TestCPU")
    monkeypatch.setattr("os.cpu_count", lambda: 8)


class _Capture:
    """Scripted ``cv2.VideoCapture``: ``frames`` readable frames, then EOF."""

    frames = 3
    closed_backends: tuple[int, ...] = ()
    broken_backends: tuple[int, ...] = ()
    instances: list[_Capture]

    def __init__(self, path: str, backend: int | None = None) -> None:
        if backend in self.broken_backends:
            raise RuntimeError("backend exploded")
        self.path = path
        self.backend = backend
        self.position = 0
        self.reads = 0
        self.released = False
        type(self).instances.append(self)

    def isOpened(self) -> bool:
        return self.backend not in self.closed_backends

    def set(self, prop: int, value: float) -> None:
        assert prop == cv2.CAP_PROP_POS_FRAMES
        self.position = int(value)

    def read(self) -> tuple[bool, np.ndarray | None]:
        self.reads += 1
        if self.position >= self.frames:
            return False, None
        self.position += 1
        return True, np.full((48, 64, 3), 255, dtype=np.uint8)

    def release(self) -> None:
        self.released = True


@pytest.fixture
def capture(monkeypatch: pytest.MonkeyPatch) -> type[_Capture]:
    """Install a fresh scripted capture class; configure it through class attributes."""
    scripted = type("ScriptedCapture", (_Capture,), {"instances": []})
    monkeypatch.setattr(hb.cv2, "VideoCapture", scripted)
    return scripted


@pytest.fixture
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the module's repository root at an empty temporary directory."""
    monkeypatch.setattr(hb, "repo_root", lambda: tmp_path)
    return tmp_path


def _result(device: str, fps: float, name: str = "x") -> BenchmarkResult:
    return BenchmarkResult(
        name=name,
        device=device,
        scenario="pipeline",
        avg_ms=1000 / fps,
        min_ms=1000 / fps,
        max_ms=1000 / fps,
        fps=fps,
    )


def _recommendation(**overrides: Any) -> BenchmarkRecommendation:
    values: dict[str, Any] = {
        "backend": "openvino",
        "device_live": "GPU",
        "device_batch": "GPU",
        "openvino_hint_live": "LATENCY",
        "openvino_hint_batch": "THROUGHPUT",
        "openvino_precision": "FP16",
        "enable_model_cache": True,
        "decode_backend": "FFMPEG",
        "recommended_batch_size": 4,
        "estimated_fps_live": 31.5,
        "estimated_fps_batch": 44.0,
        "recommended_inference_size": 416,
        "recommended_memory_mode": "low",
    }
    values.update(overrides)
    return BenchmarkRecommendation(**values)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


class TestSerialization:
    def test_a_hardware_profile_survives_json(self) -> None:
        profile = HardwareProfile(
            cpu_name="i7",
            cpu_cores=12,
            gpu_type=GPUType.INTEL_ARC,
            gpu_name="Arc A770",
            gpu_memory_gb=16.0,
            gpu_capabilities=["FP32", "FP16"],
            openvino_available=True,
            openvino_devices=["CPU", "GPU"],
            cuda_available=False,
            cuda_device_count=0,
            fingerprint="abc123",
            total_memory_gb=32.0,
        )
        encoded = json.loads(json.dumps(profile.to_dict()))

        assert encoded["gpu_type"] == "intel_arc"  # the enum is stored by value
        assert HardwareProfile.from_dict(encoded) == profile

    def test_from_dict_does_not_modify_its_argument(self) -> None:
        data = {"gpu_type": "nvidia"}
        assert HardwareProfile.from_dict(data).gpu_type is GPUType.NVIDIA
        assert data == {"gpu_type": "nvidia"}

    def test_a_profile_without_a_gpu_type_defaults_to_none(self) -> None:
        assert HardwareProfile.from_dict({}).gpu_type is GPUType.NONE

    def test_a_recommendation_survives_json(self) -> None:
        recommendation = _recommendation()
        encoded = json.loads(json.dumps(recommendation.to_dict()))
        assert BenchmarkRecommendation.from_dict(encoded) == recommendation

    def test_a_full_result_survives_json(self) -> None:
        result = SystemBenchmarkResult(
            benchmark_version="1.0.0",
            benchmark_date="2026-11-14T10:00:00",
            benchmark_duration_s=42.5,
            hardware=HardwareProfile(cpu_name="i7", gpu_type=GPUType.INTEL_IGPU),
            decode_results={"FFMPEG": _result("CPU", 100.0).to_dict()},
            compute_results={"CPU_LATENCY": _result("CPU", 20.0).to_dict()},
            pipeline_live_results={"CPU_LATENCY": _result("CPU", 18.0).to_dict()},
            pipeline_batch_results={"GPU_LATENCY": _result("GPU", 25.0).to_dict()},
            recommendation=_recommendation(),
            inconclusive=True,
        )
        restored = SystemBenchmarkResult.from_dict(json.loads(json.dumps(result.to_dict())))
        assert restored == result

    def test_a_result_without_recommendation_restores_as_none(self) -> None:
        restored = SystemBenchmarkResult.from_dict(SystemBenchmarkResult().to_dict())
        assert restored.recommendation is None
        assert restored.inconclusive is False

    def test_an_old_cache_without_the_newer_keys_still_loads(self) -> None:
        restored = SystemBenchmarkResult.from_dict({})
        assert restored == SystemBenchmarkResult()


# ---------------------------------------------------------------------------
# Hardware detection
# ---------------------------------------------------------------------------


class TestSystemMemory:
    def test_memory_is_reported_in_gigabytes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _install_psutil(monkeypatch, 15.74)
        assert hb._detect_system_memory_gb() == 15.7

    def test_without_psutil_memory_is_unknown(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _install_psutil(monkeypatch, None)
        assert hb._detect_system_memory_gb() == 0.0


def _fingerprint(cpu: str, gpu: str, memory: float, npu: bool) -> str:
    return hashlib.sha256(f"{cpu}|{gpu}|{memory}|npu={npu}".encode()).hexdigest()[:12]


@pytest.mark.usefixtures("bare_machine")
class TestDetectHardwareProfile:
    def test_a_machine_with_no_accelerator(self) -> None:
        profile = hb.detect_hardware_profile()

        assert profile == HardwareProfile(
            cpu_name="TestCPU",
            cpu_cores=8,
            total_memory_gb=16.0,
            fingerprint=_fingerprint("TestCPU", "", 0.0, False),
        )

    def test_unknown_cpu_and_core_count_get_safe_values(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("platform.processor", lambda: "")
        monkeypatch.setattr("os.cpu_count", lambda: None)
        profile = hb.detect_hardware_profile()
        assert (profile.cpu_name, profile.cpu_cores) == ("Unknown CPU", 1)

    def test_a_cuda_gpu_is_nvidia_with_its_memory(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _install_torch(monkeypatch, available=True, count=1, name="RTX 3060", memory_bytes=12 * GIB)
        profile = hb.detect_hardware_profile()

        assert profile.cuda_available is True
        assert profile.cuda_device_count == 1
        assert (profile.gpu_type, profile.gpu_name) == (GPUType.NVIDIA, "RTX 3060")
        assert profile.gpu_memory_gb == 12.0
        assert profile.fingerprint == _fingerprint("TestCPU", "RTX 3060", 12.0, False)

    def test_unreadable_cuda_memory_leaves_it_at_zero(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _install_torch(monkeypatch, available=True, count=1, name="RTX", memory_bytes=None)
        profile = hb.detect_hardware_profile()
        assert (profile.gpu_type, profile.gpu_memory_gb) == (GPUType.NVIDIA, 0.0)

    def test_cuda_without_a_device_is_not_a_gpu(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _install_torch(monkeypatch, available=True, count=0)
        profile = hb.detect_hardware_profile()
        assert profile.cuda_available is True
        assert (profile.gpu_type, profile.gpu_name) == (GPUType.NONE, "")

    def test_torch_without_cuda_reports_no_cuda(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _install_torch(monkeypatch, available=False, count=3, name="ghost")
        profile = hb.detect_hardware_profile()
        assert (profile.cuda_available, profile.cuda_device_count) == (False, 0)

    @pytest.mark.parametrize(
        ("gpu_name", "expected"),
        [
            ("Intel(R) Arc(TM) A770 Graphics", GPUType.INTEL_ARC),
            ("Intel(R) Iris(R) Xe Graphics", GPUType.INTEL_IGPU),
            ("Intel(R) UHD Graphics 770", GPUType.INTEL_IGPU),
            ("NVIDIA GeForce RTX 4070", GPUType.NVIDIA),
            ("GeForce GTX 1650", GPUType.NVIDIA),
            ("AMD Radeon RX 7600", GPUType.AMD),
            ("Radeon Graphics", GPUType.AMD),
            ("Mystery Accelerator", GPUType.UNKNOWN),
        ],
    )
    def test_an_openvino_gpu_is_classified_by_its_name(
        self, monkeypatch: pytest.MonkeyPatch, gpu_name: str, expected: GPUType
    ) -> None:
        backend = _Backend(
            devices=("CPU", "GPU"),
            properties={
                ("CPU", "FULL_DEVICE_NAME"): "Intel Core i7",
                ("GPU", "FULL_DEVICE_NAME"): gpu_name,
                ("GPU", "GPU_DEVICE_TOTAL_MEM_SIZE"): 6 * GIB,
                ("GPU", "OPTIMIZATION_CAPABILITIES"): ("FP32", "FP16"),
            },
        )
        _install_openvino(monkeypatch, backend)
        profile = hb.detect_hardware_profile()

        assert profile.openvino_available is True
        assert profile.openvino_devices == ["CPU", "GPU"]
        # OpenVINO's CPU name replaces the platform one.
        assert profile.cpu_name == "Intel Core i7"
        assert (profile.gpu_type, profile.gpu_name) == (expected, gpu_name)
        assert profile.gpu_memory_gb == 6.0
        assert profile.gpu_capabilities == ["FP32", "FP16"]
        assert profile.fingerprint == _fingerprint("Intel Core i7", gpu_name, 6.0, False)

    def test_gpu_details_that_cannot_be_read_keep_their_defaults(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        backend = _Backend(
            devices=("CPU", "GPU"), properties={("GPU", "FULL_DEVICE_NAME"): "Intel UHD"}
        )
        _install_openvino(monkeypatch, backend)
        profile = hb.detect_hardware_profile()

        assert profile.cpu_name == "TestCPU"  # no OpenVINO CPU name: the platform one stays
        assert profile.gpu_type is GPUType.INTEL_IGPU
        assert (profile.gpu_memory_gb, profile.gpu_capabilities) == (0.0, [])

    def test_empty_capabilities_become_an_empty_list(self, monkeypatch: pytest.MonkeyPatch) -> None:
        backend = _Backend(
            devices=("GPU",),
            properties={
                ("GPU", "FULL_DEVICE_NAME"): "Intel UHD",
                ("GPU", "OPTIMIZATION_CAPABILITIES"): None,
            },
        )
        _install_openvino(monkeypatch, backend)
        assert hb.detect_hardware_profile().gpu_capabilities == []

    def test_the_first_gpu_wins(self, monkeypatch: pytest.MonkeyPatch) -> None:
        backend = _Backend(
            devices=("CPU", "GPU.0", "GPU.1"),
            properties={
                ("GPU.0", "FULL_DEVICE_NAME"): "Intel Iris Xe",
                ("GPU.1", "FULL_DEVICE_NAME"): "Intel Arc A380",
            },
        )
        _install_openvino(monkeypatch, backend)
        profile = hb.detect_hardware_profile()
        assert (profile.gpu_type, profile.gpu_name) == (GPUType.INTEL_IGPU, "Intel Iris Xe")

    def test_a_gpu_that_cannot_be_named_is_skipped_for_the_next(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        backend = _Backend(
            devices=("GPU.0", "GPU.1"),
            properties={("GPU.1", "FULL_DEVICE_NAME"): "Intel Arc A380"},
        )
        _install_openvino(monkeypatch, backend)
        profile = hb.detect_hardware_profile()
        assert (profile.gpu_type, profile.gpu_name) == (GPUType.INTEL_ARC, "Intel Arc A380")

    def test_an_npu_alone_is_the_primary_accelerator(self, monkeypatch: pytest.MonkeyPatch) -> None:
        backend = _Backend(devices=("CPU", "NPU"))
        _install_openvino(monkeypatch, backend)
        profile = hb.detect_hardware_profile()

        assert profile.gpu_type is GPUType.INTEL_NPU
        # NPU presence is part of the fingerprint: plugging one in invalidates the cache.
        assert profile.fingerprint == _fingerprint("TestCPU", "", 0.0, True)
        assert profile.fingerprint != _fingerprint("TestCPU", "", 0.0, False)

    def test_an_npu_beside_a_known_gpu_does_not_replace_it(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        backend = _Backend(
            devices=("CPU", "GPU", "NPU"),
            properties={
                ("GPU", "FULL_DEVICE_NAME"): "Intel Arc A770",
                ("NPU", "FULL_DEVICE_NAME"): "Intel AI Boost",
            },
        )
        _install_openvino(monkeypatch, backend)
        assert hb.detect_hardware_profile().gpu_type is GPUType.INTEL_ARC

    def test_an_npu_beside_an_unrecognised_gpu_takes_over(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        backend = _Backend(
            devices=("GPU", "NPU"), properties={("GPU", "FULL_DEVICE_NAME"): "Mystery"}
        )
        _install_openvino(monkeypatch, backend)
        assert hb.detect_hardware_profile().gpu_type is GPUType.INTEL_NPU


# ---------------------------------------------------------------------------
# Locating the video and the model
# ---------------------------------------------------------------------------


def _touch(path: Path, size: int = 1) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x00" * size)
    return path


class TestFindTestVideo:
    def test_nothing_to_find(self, root: Path) -> None:
        assert hb._find_test_video() is None

    def test_the_largest_video_of_a_folder_is_chosen(self, root: Path) -> None:
        _touch(root / "tests" / "fixtures" / "small.mp4", 10)
        big = _touch(root / "tests" / "fixtures" / "nested" / "big.mp4", 500)
        assert hb._find_test_video() == big

    def test_recorded_sessions_are_searched_before_fixtures(self, root: Path) -> None:
        session = _touch(root / "live_analysis_sessions" / "s1" / "s1.mp4", 1)
        _touch(root / "tests" / "fixtures" / "huge.mp4", 900)
        assert hb._find_test_video() == session

    def test_other_containers_are_accepted(self, root: Path) -> None:
        avi = _touch(root / "resources" / "clip.avi")
        assert hb._find_test_video() == avi

    def test_an_existing_but_empty_folder_does_not_stop_the_search(self, root: Path) -> None:
        (root / "live_analysis_sessions").mkdir()
        (root / "tests" / "fixtures").mkdir(parents=True)
        mkv = _touch(root / "test_data" / "clip.mkv")
        assert hb._find_test_video() == mkv


class TestFindOpenvinoModel:
    def test_no_cache_folder_no_model(self, root: Path) -> None:
        assert hb._find_openvino_model() is None

    def test_a_cache_without_converted_models(self, root: Path) -> None:
        cache = root / hb.OPENVINO_CACHE_DIRNAME
        (cache / "half_converted").mkdir(parents=True)
        # A stray XML at the top level is not a model directory.
        _touch(cache / "stray.xml")
        assert hb._find_openvino_model() is None

    def test_the_xml_of_a_model_directory_is_returned(self, root: Path) -> None:
        cache = root / hb.OPENVINO_CACHE_DIRNAME
        (cache / "empty").mkdir(parents=True)
        xml = _touch(cache / "yolo_openvino_model" / "yolo.xml")
        assert hb._find_openvino_model() == xml


class _WeightManager:
    """Scripted ``WeightManager``; configure through class attributes."""

    det_weight: str | None = "det.pt"
    default_weight: str | None = "default.pt"
    converted: Any = "ok"
    error: Exception | None = None
    converted_names: list[str]

    def __init__(self, settings_obj: Any) -> None:
        self.settings_obj = settings_obj

    def get_default_det_weight(self) -> tuple[str | None, dict]:
        return self.det_weight, {}

    def get_default_weight(self) -> tuple[str | None, dict]:
        return self.default_weight, {}

    def convert_to_openvino(self, name: str) -> Any:
        type(self).converted_names.append(name)
        if self.error is not None:
            raise self.error
        return self.converted


@pytest.fixture
def weight_manager(monkeypatch: pytest.MonkeyPatch) -> type[_WeightManager]:
    scripted = type("ScriptedWeightManager", (_WeightManager,), {"converted_names": []})
    monkeypatch.setattr("zebtrack.core.services.weight_manager.WeightManager", scripted)
    monkeypatch.setattr(hb, "_find_openvino_model", lambda: Path("converted.xml"))
    return scripted


class TestPrepareOpenvinoModel:
    def test_without_settings_nothing_is_converted(
        self, weight_manager: type[_WeightManager]
    ) -> None:
        assert hb._prepare_openvino_model(None) is None
        assert weight_manager.converted_names == []

    def test_the_default_detection_weight_is_converted(
        self, weight_manager: type[_WeightManager]
    ) -> None:
        assert hb._prepare_openvino_model(object()) == Path("converted.xml")
        assert weight_manager.converted_names == ["det.pt"]

    def test_the_default_weight_is_the_fallback(self, weight_manager: type[_WeightManager]) -> None:
        weight_manager.det_weight = None
        assert hb._prepare_openvino_model(object()) == Path("converted.xml")
        assert weight_manager.converted_names == ["default.pt"]

    def test_no_registered_weight_means_no_model(
        self, weight_manager: type[_WeightManager]
    ) -> None:
        weight_manager.det_weight = None
        weight_manager.default_weight = None
        assert hb._prepare_openvino_model(object()) is None
        assert weight_manager.converted_names == []

    def test_a_conversion_that_returns_nothing_means_no_model(
        self, weight_manager: type[_WeightManager]
    ) -> None:
        weight_manager.converted = None
        assert hb._prepare_openvino_model(object()) is None

    def test_a_failing_conversion_never_stops_startup(
        self, weight_manager: type[_WeightManager]
    ) -> None:
        weight_manager.error = RuntimeError("exporter blew up")
        assert hb._prepare_openvino_model(object()) is None


# ---------------------------------------------------------------------------
# Individual benchmarks
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("clock")
class TestVideoDecodeBenchmark:
    def test_every_backend_that_opens_is_timed(self, capture: type[_Capture]) -> None:
        results = hb._benchmark_video_decode(Path("clip.mp4"), num_frames=5)

        assert set(results) == {"FFMPEG", "MSMF", "AUTO"}
        for result in results.values():
            assert result.avg_ms == pytest.approx(STEP_MS)
            assert result.min_ms == pytest.approx(STEP_MS)
            assert result.max_ms == pytest.approx(STEP_MS)
            assert result.fps == pytest.approx(STEP_FPS)
            assert result.scenario == "isolated"
        # Media Foundation is the hardware path; the others decode on the CPU.
        assert {key: result.device for key, result in results.items()} == {
            "FFMPEG": "CPU",
            "MSMF": "GPU",
            "AUTO": "CPU",
        }
        assert [(c.backend, c.reads, c.released) for c in capture.instances] == [
            (cv2.CAP_FFMPEG, 5, True),
            (cv2.CAP_MSMF, 5, True),
            (cv2.CAP_ANY, 5, True),
        ]

    def test_a_backend_that_does_not_open_is_left_out(self, capture: type[_Capture]) -> None:
        capture.closed_backends = (cv2.CAP_MSMF,)
        assert set(hb._benchmark_video_decode(Path("clip.mp4"), num_frames=2)) == {"FFMPEG", "AUTO"}

    def test_a_backend_that_raises_does_not_stop_the_others(self, capture: type[_Capture]) -> None:
        capture.broken_backends = (cv2.CAP_FFMPEG,)
        assert set(hb._benchmark_video_decode(Path("clip.mp4"), num_frames=2)) == {"MSMF", "AUTO"}

    def test_a_video_with_no_readable_frame_yields_no_result(self, capture: type[_Capture]) -> None:
        capture.frames = 0
        assert hb._benchmark_video_decode(Path("clip.mp4"), num_frames=3) == {}


def _frame() -> np.ndarray:
    return np.full((48, 64, 3), 255, dtype=np.uint8)


@pytest.mark.usefixtures("clock", "root")
class TestOpenvinoInferenceBenchmark:
    def _run(
        self,
        monkeypatch: pytest.MonkeyPatch,
        profile: HardwareProfile,
        backend: _Backend | None = None,
        iterations: int = 4,
    ) -> tuple[dict[str, BenchmarkResult], _Backend]:
        backend = backend or _Backend()
        _install_openvino(monkeypatch, backend)
        results = hb._benchmark_openvino_inference(Path("model.xml"), _frame(), profile, iterations)
        return results, backend

    def test_a_cpu_only_machine_times_the_cpu(self, monkeypatch: pytest.MonkeyPatch) -> None:
        results, backend = self._run(monkeypatch, HardwareProfile(openvino_devices=["CPU"]))

        assert list(results) == ["CPU_LATENCY"]
        result = results["CPU_LATENCY"]
        assert (result.name, result.device, result.scenario) == (
            "Inference (CPU LATENCY)",
            "CPU",
            "isolated",
        )
        assert result.avg_ms == pytest.approx(STEP_MS)
        assert result.fps == pytest.approx(STEP_FPS)
        assert backend.read_paths == ["model.xml"]
        assert backend.compile_calls == [("CPU", {"PERFORMANCE_HINT": "LATENCY"})]
        # Five warm-up runs are not timed; then one run per iteration.
        assert len(backend.blobs) == 5 + 4

    def test_the_input_is_a_normalised_640_blob(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _results, backend = self._run(monkeypatch, HardwareProfile(openvino_devices=["CPU"]))
        blob = backend.blobs[0]
        assert blob.shape == (1, 3, 640, 640)
        assert blob.dtype == np.float32
        assert blob.max() == pytest.approx(1.0)

    @pytest.mark.parametrize(
        ("gpu_type", "capabilities", "devices", "expected"),
        [
            (GPUType.INTEL_IGPU, [], ["CPU", "GPU"], ["CPU_LATENCY", "GPU_LATENCY"]),
            (
                GPUType.INTEL_IGPU,
                ["FP16"],
                ["CPU", "GPU"],
                ["CPU_LATENCY", "GPU_LATENCY", "GPU_LATENCY_FP16"],
            ),
            # THROUGHPUT is only worth measuring on a discrete GPU.
            (
                GPUType.INTEL_ARC,
                ["FP16"],
                ["CPU", "GPU"],
                ["CPU_LATENCY", "GPU_LATENCY", "GPU_THROUGHPUT", "GPU_LATENCY_FP16"],
            ),
            (GPUType.NVIDIA, [], ["CPU", "GPU"], ["CPU_LATENCY", "GPU_LATENCY", "GPU_THROUGHPUT"]),
            (
                GPUType.INTEL_NPU,
                [],
                ["CPU", "NPU"],
                ["CPU_LATENCY", "NPU_LATENCY", "NPU_THROUGHPUT"],
            ),
            # FP16 capability without a GPU device changes nothing.
            (GPUType.NONE, ["FP16"], ["CPU"], ["CPU_LATENCY"]),
        ],
    )
    def test_the_configurations_follow_the_hardware(
        self,
        monkeypatch: pytest.MonkeyPatch,
        gpu_type: GPUType,
        capabilities: list[str],
        devices: list[str],
        expected: list[str],
    ) -> None:
        profile = HardwareProfile(
            gpu_type=gpu_type, gpu_capabilities=capabilities, openvino_devices=devices
        )
        results, _backend = self._run(monkeypatch, profile)
        assert list(results) == expected

    def test_gpu_runs_use_the_shared_compiled_cache_and_fp16_when_asked(
        self, monkeypatch: pytest.MonkeyPatch, root: Path
    ) -> None:
        profile = HardwareProfile(
            gpu_type=GPUType.INTEL_IGPU, gpu_capabilities=["FP16"], openvino_devices=["CPU", "GPU"]
        )
        _results, backend = self._run(monkeypatch, profile)
        cache = str(root / hb.OPENVINO_CACHE_DIRNAME / "compiled_cache")

        assert backend.compile_calls == [
            ("CPU", {"PERFORMANCE_HINT": "LATENCY"}),
            ("GPU", {"PERFORMANCE_HINT": "LATENCY", "CACHE_DIR": cache}),
            (
                "GPU",
                {
                    "PERFORMANCE_HINT": "LATENCY",
                    "CACHE_DIR": cache,
                    "INFERENCE_PRECISION_HINT": "f16",
                },
            ),
        ]

    def test_a_device_that_fails_to_compile_is_left_out(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        profile = HardwareProfile(gpu_type=GPUType.INTEL_IGPU, openvino_devices=["CPU", "GPU"])
        results, _backend = self._run(monkeypatch, profile, _Backend(failing_devices=("GPU",)))
        assert list(results) == ["CPU_LATENCY"]

    def test_a_model_that_cannot_be_read_yields_nothing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        backend = _Backend(read_error=RuntimeError("corrupt"))
        results, backend = self._run(monkeypatch, HardwareProfile(), backend)
        assert results == {}
        assert backend.compile_calls == []

    def test_without_openvino_nothing_is_timed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _install_openvino(monkeypatch, None)
        assert hb._benchmark_openvino_inference(Path("m.xml"), _frame(), HardwareProfile()) == {}


class TestCudaBenchmark:
    def test_without_cuda_nothing_is_timed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _install_torch(monkeypatch, available=False)
        assert hb._benchmark_pytorch_cuda(_frame()) == {}

    def test_without_torch_nothing_is_timed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _install_torch(monkeypatch, missing=True)
        assert hb._benchmark_pytorch_cuda(_frame()) == {}


@pytest.mark.usefixtures("clock", "root")
class TestPipelineBenchmark:
    def test_a_pipeline_run_is_timed_frame_by_frame(
        self, monkeypatch: pytest.MonkeyPatch, capture: type[_Capture]
    ) -> None:
        backend = _Backend()
        _install_openvino(monkeypatch, backend)

        result = hb._benchmark_pipeline_complete(
            Path("clip.mp4"), Path("model.xml"), "CPU", "LATENCY", num_frames=6
        )

        assert result is not None
        assert (result.name, result.device, result.scenario) == (
            "Pipeline (CPU LATENCY)",
            "CPU",
            "pipeline",
        )
        assert result.avg_ms == pytest.approx(STEP_MS)
        assert result.fps == pytest.approx(STEP_FPS)
        assert backend.compile_calls == [("CPU", {"PERFORMANCE_HINT": "LATENCY"})]
        # Three warm-up frames, then the six that are timed.
        assert len(backend.blobs) == 3 + 6
        assert backend.blobs[0].shape == (1, 3, 640, 640)
        (cap,) = capture.instances
        assert cap.released is True

    def test_a_short_video_is_looped(
        self, monkeypatch: pytest.MonkeyPatch, capture: type[_Capture]
    ) -> None:
        capture.frames = 2
        backend = _Backend()
        _install_openvino(monkeypatch, backend)

        result = hb._benchmark_pipeline_complete(
            Path("clip.mp4"), Path("model.xml"), "CPU", "LATENCY", num_frames=5
        )

        assert result is not None
        assert len(backend.blobs) == 3 + 5

    @pytest.mark.parametrize("device", ["GPU", "NPU"])
    def test_accelerators_compile_into_the_shared_cache(
        self, monkeypatch: pytest.MonkeyPatch, capture: type[_Capture], root: Path, device: str
    ) -> None:
        backend = _Backend()
        _install_openvino(monkeypatch, backend)
        hb._benchmark_pipeline_complete(Path("clip.mp4"), Path("m.xml"), device, "THROUGHPUT", 1)

        cache = str(root / hb.OPENVINO_CACHE_DIRNAME / "compiled_cache")
        assert backend.compile_calls == [
            (device, {"PERFORMANCE_HINT": "THROUGHPUT", "CACHE_DIR": cache})
        ]

    def test_a_video_that_does_not_open_yields_nothing(
        self, monkeypatch: pytest.MonkeyPatch, capture: type[_Capture]
    ) -> None:
        capture.closed_backends = (None,)  # type: ignore[assignment]
        _install_openvino(monkeypatch, _Backend())
        assert (
            hb._benchmark_pipeline_complete(Path("x.mp4"), Path("m.xml"), "CPU", "LATENCY") is None
        )

    def test_a_device_that_fails_to_compile_yields_nothing(
        self, monkeypatch: pytest.MonkeyPatch, capture: type[_Capture]
    ) -> None:
        _install_openvino(monkeypatch, _Backend(failing_devices=("GPU",)))
        assert (
            hb._benchmark_pipeline_complete(Path("x.mp4"), Path("m.xml"), "GPU", "LATENCY") is None
        )
        assert capture.instances == []

    def test_the_video_is_released_when_the_run_fails_midway(
        self, monkeypatch: pytest.MonkeyPatch, capture: type[_Capture]
    ) -> None:
        capture.frames = 0  # nothing to read: the resize of ``None`` raises
        _install_openvino(monkeypatch, _Backend())

        assert (
            hb._benchmark_pipeline_complete(Path("x.mp4"), Path("m.xml"), "CPU", "LATENCY") is None
        )
        (cap,) = capture.instances
        assert cap.released is True


# ---------------------------------------------------------------------------
# Recommendation
# ---------------------------------------------------------------------------


def _recommend(
    profile: HardwareProfile,
    *,
    compute: dict[str, BenchmarkResult] | None = None,
    live: dict[str, BenchmarkResult] | None = None,
    batch: dict[str, BenchmarkResult] | None = None,
    decode: dict[str, BenchmarkResult] | None = None,
) -> BenchmarkRecommendation:
    return hb._generate_recommendation(
        profile, compute or {}, live or {}, batch or {}, decode or {}
    )


class TestRecommendation:
    def test_with_nothing_measured_the_defaults_are_cpu_at_zero_fps(self) -> None:
        recommendation = _recommend(HardwareProfile(openvino_available=True, total_memory_gb=16))

        assert recommendation == BenchmarkRecommendation(
            backend="openvino",
            device_live="CPU",
            device_batch="CPU",
            openvino_hint_live="LATENCY",
            openvino_hint_batch="LATENCY",
            openvino_precision="FP32",
            enable_model_cache=True,
            decode_backend="AUTO",
            # 1, not 0: no reported GPU memory used to give a batch of 0 (A2-11).
            recommended_batch_size=1,
            estimated_fps_live=0.0,
            estimated_fps_batch=0.0,
            recommended_inference_size=640,
            recommended_memory_mode="normal",
        )

    def test_without_openvino_the_backend_is_pytorch(self) -> None:
        recommendation = _recommend(HardwareProfile(total_memory_gb=16))
        assert recommendation.backend == "pytorch"
        assert recommendation.recommended_batch_size == 1

    def test_nvidia_with_cuda_uses_pytorch_on_cuda(self) -> None:
        profile = HardwareProfile(
            gpu_type=GPUType.NVIDIA, cuda_available=True, openvino_available=True
        )
        recommendation = _recommend(
            profile,
            compute={"CUDA": _result("CUDA", 120.0)},
            live={"CPU_LATENCY": _result("CPU", 500.0)},
        )
        assert (
            recommendation.backend,
            recommendation.device_live,
            recommendation.device_batch,
        ) == (
            "pytorch",
            "cuda",
            "cuda",
        )
        assert (recommendation.estimated_fps_live, recommendation.estimated_fps_batch) == (
            120.0,
            120.0,
        )

    def test_nvidia_with_little_ram_still_gets_the_low_memory_mode(self) -> None:
        # A4-11: the CUDA branch returned before the sizing and the decoder.
        profile = HardwareProfile(gpu_type=GPUType.NVIDIA, cuda_available=True, total_memory_gb=6)
        recommendation = _recommend(profile, decode={"FFMPEG": _result("CPU", 300.0)})
        assert recommendation.recommended_memory_mode == "low"
        assert recommendation.decode_backend == "FFMPEG"

    def test_a_gpu_without_reported_memory_still_batches_one(self) -> None:
        profile = HardwareProfile(
            gpu_type=GPUType.UNKNOWN, openvino_available=True, gpu_memory_gb=0.0
        )
        assert _recommend(profile).recommended_batch_size == 1

    def test_nvidia_without_a_cuda_measurement_estimates_zero(self) -> None:
        profile = HardwareProfile(gpu_type=GPUType.NVIDIA, cuda_available=True)
        recommendation = _recommend(profile)
        assert recommendation.device_live == "cuda"
        assert recommendation.estimated_fps_live == 0.0

    def test_an_nvidia_card_seen_only_through_openvino_stays_on_openvino(self) -> None:
        profile = HardwareProfile(
            gpu_type=GPUType.NVIDIA, cuda_available=False, openvino_available=True
        )
        recommendation = _recommend(profile, live={"GPU_LATENCY": _result("GPU", 40.0)})
        assert (recommendation.backend, recommendation.device_live) == ("openvino", "GPU")

    def test_the_fastest_live_pipeline_picks_the_live_device(self) -> None:
        recommendation = _recommend(
            HardwareProfile(openvino_available=True, gpu_type=GPUType.INTEL_IGPU),
            live={
                "CPU_LATENCY": _result("CPU", 18.0),
                "GPU_LATENCY": _result("GPU", 33.0),
                "NPU_LATENCY": _result("NPU", 21.0),
            },
        )
        assert (recommendation.device_live, recommendation.estimated_fps_live) == ("GPU", 33.0)
        # Batch was not measured: it keeps its default.
        assert (recommendation.device_batch, recommendation.estimated_fps_batch) == ("CPU", 0.0)

    @pytest.mark.parametrize(
        ("batch", "device", "hint", "fps"),
        [
            (
                {"GPU_LATENCY": _result("GPU", 30.0), "GPU_THROUGHPUT": _result("GPU", 55.0)},
                "GPU",
                "THROUGHPUT",
                55.0,
            ),
            (
                {"GPU_THROUGHPUT": _result("GPU", 30.0), "CPU_LATENCY": _result("CPU", 55.0)},
                "CPU",
                "LATENCY",
                55.0,
            ),
        ],
    )
    def test_the_fastest_batch_pipeline_picks_device_and_hint(
        self, batch: dict[str, BenchmarkResult], device: str, hint: str, fps: float
    ) -> None:
        recommendation = _recommend(
            HardwareProfile(openvino_available=True, gpu_type=GPUType.INTEL_ARC), batch=batch
        )
        assert (
            recommendation.device_batch,
            recommendation.openvino_hint_batch,
            recommendation.estimated_fps_batch,
        ) == (device, hint, fps)
        assert recommendation.openvino_hint_live == "LATENCY"

    @pytest.mark.parametrize(
        ("fp32_fps", "fp16_fps", "expected"),
        [(30.0, 45.0, "FP16"), (45.0, 30.0, "FP32"), (30.0, 30.0, "FP32")],
    )
    def test_fp16_is_recommended_only_when_it_is_faster(
        self, fp32_fps: float, fp16_fps: float, expected: str
    ) -> None:
        recommendation = _recommend(
            HardwareProfile(openvino_available=True, gpu_type=GPUType.INTEL_IGPU),
            compute={
                "GPU_LATENCY": _result("GPU", fp32_fps),
                "GPU_LATENCY_FP16": _result("GPU", fp16_fps),
            },
        )
        assert recommendation.openvino_precision == expected

    def test_fp16_alone_is_not_evidence(self) -> None:
        recommendation = _recommend(
            HardwareProfile(openvino_available=True),
            compute={"GPU_LATENCY_FP16": _result("GPU", 99.0)},
        )
        assert recommendation.openvino_precision == "FP32"

    @pytest.mark.parametrize("slot", ["live", "batch"])
    def test_an_npu_in_either_role_forces_fp16(self, slot: str) -> None:
        results = {"NPU_LATENCY": _result("NPU", 40.0)}
        recommendation = _recommend(
            HardwareProfile(openvino_available=True, gpu_type=GPUType.INTEL_NPU),
            **{slot: results},  # type: ignore[arg-type]
        )
        assert recommendation.openvino_precision == "FP16"

    @pytest.mark.parametrize(
        ("gpu_type", "memory_gb", "expected"),
        [
            # Arc: two per GB, capped at eight.
            (GPUType.INTEL_ARC, 16.0, 8),
            (GPUType.INTEL_ARC, 3.0, 6),
            # Shared memory and the NPU never batch.
            (GPUType.INTEL_IGPU, 16.0, 1),
            (GPUType.INTEL_NPU, 16.0, 1),
            # Anything else: one per GB, capped at four.
            (GPUType.AMD, 8.0, 4),
            (GPUType.UNKNOWN, 2.5, 2),
        ],
    )
    def test_the_batch_size_follows_the_gpu_and_its_memory(
        self, gpu_type: GPUType, memory_gb: float, expected: int
    ) -> None:
        profile = HardwareProfile(
            openvino_available=True, gpu_type=gpu_type, gpu_memory_gb=memory_gb, total_memory_gb=16
        )
        assert _recommend(profile).recommended_batch_size == expected

    def test_the_fastest_decoder_is_recommended(self) -> None:
        recommendation = _recommend(
            HardwareProfile(openvino_available=True),
            decode={
                "FFMPEG": _result("CPU", 210.0),
                "MSMF": _result("GPU", 340.0),
                "AUTO": _result("CPU", 205.0),
            },
        )
        assert recommendation.decode_backend == "MSMF"


class TestHardwareSizing:
    @pytest.mark.parametrize(
        ("memory_gb", "size", "mode"),
        [
            (4.0, 320, "low"),
            (5.9, 320, "low"),
            (6.0, 416, "low"),
            (7.9, 416, "low"),
            (8.0, 416, "normal"),
            (9.9, 416, "normal"),
            (10.0, 640, "normal"),
            (32.0, 640, "normal"),
        ],
    )
    def test_a_cpu_only_machine_is_sized_by_its_ram(
        self, memory_gb: float, size: int, mode: str
    ) -> None:
        recommendation = _recommendation(
            recommended_inference_size=640, recommended_memory_mode="normal"
        )
        hb._apply_hardware_sizing(recommendation, HardwareProfile(total_memory_gb=memory_gb))
        assert (
            recommendation.recommended_inference_size,
            recommendation.recommended_memory_mode,
        ) == (size, mode)

    @pytest.mark.parametrize(
        "profile",
        [
            HardwareProfile(gpu_type=GPUType.INTEL_IGPU, total_memory_gb=4.0),
            HardwareProfile(gpu_type=GPUType.NONE, cuda_available=True, total_memory_gb=4.0),
        ],
    )
    def test_an_accelerator_keeps_the_full_inference_size(self, profile: HardwareProfile) -> None:
        recommendation = _recommendation(
            recommended_inference_size=640, recommended_memory_mode="normal"
        )
        hb._apply_hardware_sizing(recommendation, profile)
        # The input stays at 640, but 4 GB of RAM is still a low-memory machine.
        assert recommendation.recommended_inference_size == 640
        assert recommendation.recommended_memory_mode == "low"

    def test_an_unrecognised_gpu_counts_as_cpu_only(self) -> None:
        recommendation = _recommendation(recommended_inference_size=640)
        hb._apply_hardware_sizing(
            recommendation, HardwareProfile(gpu_type=GPUType.UNKNOWN, total_memory_gb=4.0)
        )
        assert recommendation.recommended_inference_size == 320

    def test_sizing_is_applied_by_the_recommendation(self) -> None:
        recommendation = _recommend(HardwareProfile(openvino_available=True, total_memory_gb=4.0))
        assert recommendation.recommended_inference_size == 320
        assert recommendation.recommended_memory_mode == "low"


class TestBenchmarkDevices:
    @pytest.mark.parametrize(
        ("devices", "expected"),
        [
            ([], ["CPU"]),
            (["CPU"], ["CPU"]),
            (["CPU", "GPU"], ["CPU", "GPU"]),
            (["NPU", "GPU", "CPU"], ["CPU", "GPU", "NPU"]),
        ],
    )
    def test_the_cpu_is_always_benchmarked_first(
        self, devices: list[str], expected: list[str]
    ) -> None:
        assert hb._get_benchmark_devices(HardwareProfile(openvino_devices=devices)) == expected


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


class _Stubs:
    """Replaces every measurement of ``run_adaptive_benchmark`` and records the calls."""

    def __init__(
        self,
        monkeypatch: pytest.MonkeyPatch,
        *,
        profile: HardwareProfile,
        video: Path | None = Path("clip.mp4"),
        model: Path | None = Path("model.xml"),
        prepared: Path | None = None,
        compute: dict[str, BenchmarkResult] | None = None,
        cuda: dict[str, BenchmarkResult] | None = None,
        pipeline_fps: float | None = 30.0,
    ) -> None:
        self.prepare_calls: list[Any] = []
        self.decode_calls: list[tuple[Path, int]] = []
        self.inference_calls: list[tuple[Path, tuple[int, ...], int]] = []
        self.cuda_calls: list[int] = []
        self.pipeline_calls: list[tuple[str, str, int]] = []

        def _prepare(settings_obj: Any) -> Path | None:
            self.prepare_calls.append(settings_obj)
            return prepared

        def _decode(video_path: Path, num_frames: int) -> dict[str, BenchmarkResult]:
            self.decode_calls.append((video_path, num_frames))
            return {"FFMPEG": _result("CPU", 200.0)}

        def _inference(
            model_path: Path, frame: np.ndarray, hw: HardwareProfile, iterations: int
        ) -> dict[str, BenchmarkResult]:
            self.inference_calls.append((model_path, frame.shape, iterations))
            return dict(compute if compute is not None else {"CPU_LATENCY": _result("CPU", 20.0)})

        def _cuda(frame: np.ndarray, iterations: int) -> dict[str, BenchmarkResult]:
            self.cuda_calls.append(iterations)
            return dict(cuda or {})

        def _pipeline(
            video_path: Path, model_path: Path, device: str, hint: str, num_frames: int
        ) -> BenchmarkResult | None:
            self.pipeline_calls.append((device, hint, num_frames))
            return None if pipeline_fps is None else _result(device, pipeline_fps)

        monkeypatch.setattr(hb, "detect_hardware_profile", lambda: profile)
        monkeypatch.setattr(hb, "_find_test_video", lambda: video)
        monkeypatch.setattr(hb, "_find_openvino_model", lambda: model)
        monkeypatch.setattr(hb, "_prepare_openvino_model", _prepare)
        monkeypatch.setattr(hb, "_benchmark_video_decode", _decode)
        monkeypatch.setattr(hb, "_benchmark_openvino_inference", _inference)
        monkeypatch.setattr(hb, "_benchmark_pytorch_cuda", _cuda)
        monkeypatch.setattr(hb, "_benchmark_pipeline_complete", _pipeline)


@pytest.mark.usefixtures("capture")
class TestRunAdaptiveBenchmark:
    CPU = HardwareProfile(openvino_available=True, openvino_devices=["CPU"], total_memory_gb=16)

    def test_progress_is_reported_for_each_of_the_seven_steps(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _Stubs(monkeypatch, profile=self.CPU)
        seen: list[tuple[int, int, str]] = []

        hb.run_adaptive_benchmark(progress_callback=lambda *args: seen.append(args))

        assert [(step, total) for step, total, _message in seen] == [
            (step, 7) for step in range(1, 8)
        ]
        assert all(message.startswith(f"Step {step}/7") for step, _total, message in seen)
        assert hb.TOTAL_BENCHMARK_STEPS == 7

    def test_a_full_run_fills_every_section_and_recommends(
        self, monkeypatch: pytest.MonkeyPatch, clock: _Clock
    ) -> None:
        stubs = _Stubs(monkeypatch, profile=self.CPU)

        result = hb.run_adaptive_benchmark()

        assert result.hardware is self.CPU
        assert result.inconclusive is False
        assert result.decode_results == {"FFMPEG": _result("CPU", 200.0).to_dict()}
        assert result.compute_results == {"CPU_LATENCY": _result("CPU", 20.0).to_dict()}
        assert result.pipeline_live_results == {"CPU_LATENCY": _result("CPU", 30.0).to_dict()}
        assert result.pipeline_batch_results == {"CPU_LATENCY": _result("CPU", 30.0).to_dict()}
        assert result.recommendation is not None
        assert result.recommendation.estimated_fps_live == 30.0
        assert result.recommendation.decode_backend == "FFMPEG"
        # Two clock readings bracket the run.
        assert result.benchmark_duration_s == pytest.approx(STEP_MS / 1000)
        assert result.benchmark_date
        # The full run uses 50 frames and 30 iterations; the model was found, not converted.
        assert stubs.decode_calls == [(Path("clip.mp4"), 50)]
        assert stubs.inference_calls == [(Path("model.xml"), (48, 64, 3), 30)]
        assert stubs.pipeline_calls == [("CPU", "LATENCY", 50), ("CPU", "LATENCY", 50)]
        assert stubs.prepare_calls == []
        assert stubs.cuda_calls == []

    def test_quick_mode_halves_the_work(self, monkeypatch: pytest.MonkeyPatch) -> None:
        stubs = _Stubs(monkeypatch, profile=self.CPU)
        hb.run_adaptive_benchmark(quick_mode=True)

        assert stubs.decode_calls == [(Path("clip.mp4"), 25)]
        assert stubs.inference_calls[0][2] == 15
        assert {frames for _device, _hint, frames in stubs.pipeline_calls} == {25}

    def test_a_missing_model_is_converted_first(self, monkeypatch: pytest.MonkeyPatch) -> None:
        settings_obj = object()
        stubs = _Stubs(monkeypatch, profile=self.CPU, model=None, prepared=Path("fresh.xml"))

        result = hb.run_adaptive_benchmark(settings_obj=settings_obj)

        assert stubs.prepare_calls == [settings_obj]
        assert stubs.inference_calls[0][0] == Path("fresh.xml")
        assert result.inconclusive is False

    def test_without_openvino_no_model_is_converted_or_timed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        stubs = _Stubs(monkeypatch, profile=HardwareProfile(total_memory_gb=16), model=None)

        result = hb.run_adaptive_benchmark(settings_obj=object())

        assert stubs.prepare_calls == []
        assert stubs.inference_calls == []
        assert stubs.pipeline_calls == []
        assert result.inconclusive is True

    def test_a_run_that_timed_nothing_is_inconclusive(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Fresh install whose conversion failed: there is still a recommendation,
        # but it is a default, and the result must say so.
        _Stubs(monkeypatch, profile=self.CPU, model=None, prepared=None)

        result = hb.run_adaptive_benchmark()

        assert result.inconclusive is True
        assert result.compute_results == {}
        assert result.recommendation is not None
        assert result.recommendation.estimated_fps_live == 0.0

    def test_a_pipeline_measurement_alone_is_conclusive(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _Stubs(monkeypatch, profile=self.CPU, compute={})
        assert hb.run_adaptive_benchmark().inconclusive is False

    def test_a_compute_measurement_alone_is_conclusive(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _Stubs(monkeypatch, profile=self.CPU, pipeline_fps=None)
        result = hb.run_adaptive_benchmark()
        assert result.inconclusive is False
        assert result.pipeline_live_results == {}

    def test_without_a_video_a_synthetic_frame_feeds_the_inference(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        stubs = _Stubs(monkeypatch, profile=self.CPU, video=None)

        result = hb.run_adaptive_benchmark()

        assert stubs.decode_calls == []
        assert stubs.pipeline_calls == []
        assert stubs.inference_calls == [(Path("model.xml"), (720, 1280, 3), 30)]
        assert result.decode_results == {}

    def test_an_unreadable_video_also_falls_back_to_the_synthetic_frame(
        self, monkeypatch: pytest.MonkeyPatch, capture: type[_Capture]
    ) -> None:
        capture.frames = 0
        stubs = _Stubs(monkeypatch, profile=self.CPU)
        hb.run_adaptive_benchmark()
        assert stubs.inference_calls[0][1] == (720, 1280, 3)
        assert all(cap.released for cap in capture.instances)

    def test_cuda_is_timed_alongside_openvino(self, monkeypatch: pytest.MonkeyPatch) -> None:
        profile = HardwareProfile(
            gpu_type=GPUType.NVIDIA,
            cuda_available=True,
            openvino_available=True,
            openvino_devices=["CPU"],
        )
        stubs = _Stubs(monkeypatch, profile=profile, cuda={"CUDA": _result("CUDA", 140.0)})

        result = hb.run_adaptive_benchmark()

        assert stubs.cuda_calls == [30]
        assert set(result.compute_results) == {"CPU_LATENCY", "CUDA"}
        assert result.recommendation is not None
        assert result.recommendation.estimated_fps_live == 140.0

    @pytest.mark.parametrize(
        ("gpu_type", "devices", "batch"),
        [
            (
                GPUType.INTEL_IGPU,
                ["CPU", "GPU"],
                [("CPU", "LATENCY"), ("GPU", "LATENCY")],
            ),
            (
                GPUType.INTEL_ARC,
                ["CPU", "GPU"],
                [("CPU", "LATENCY"), ("GPU", "LATENCY"), ("GPU", "THROUGHPUT")],
            ),
            (
                GPUType.INTEL_NPU,
                ["CPU", "NPU"],
                [("CPU", "LATENCY"), ("NPU", "LATENCY"), ("NPU", "THROUGHPUT")],
            ),
        ],
    )
    def test_throughput_is_only_tried_where_it_can_pay_off(
        self,
        monkeypatch: pytest.MonkeyPatch,
        gpu_type: GPUType,
        devices: list[str],
        batch: list[tuple[str, str]],
    ) -> None:
        profile = HardwareProfile(
            openvino_available=True, gpu_type=gpu_type, openvino_devices=devices
        )
        stubs = _Stubs(monkeypatch, profile=profile)

        result = hb.run_adaptive_benchmark()

        live = [(device, "LATENCY") for device in hb._get_benchmark_devices(profile)]
        assert [(device, hint) for device, hint, _frames in stubs.pipeline_calls] == live + batch
        assert list(result.pipeline_batch_results) == [f"{d}_{h}" for d, h in batch]


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------


def _measured(fingerprint: str = "fp-1") -> SystemBenchmarkResult:
    return SystemBenchmarkResult(
        benchmark_date="2026-11-14T10:00:00",
        hardware=HardwareProfile(cpu_name="i7", fingerprint=fingerprint),
        compute_results={"CPU_LATENCY": _result("CPU", 20.0).to_dict()},
        recommendation=_recommendation(),
    )


@pytest.fixture
def same_hardware(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(hb, "detect_hardware_profile", lambda: HardwareProfile(fingerprint="fp-1"))


class TestCache:
    def test_the_cache_file_lives_under_the_repository_root(self) -> None:
        # ``--reset`` deletes this exact file; a CWD-relative path would miss it.
        assert hb.get_benchmark_cache_path() == (
            repo_root() / "openvino_model_cache" / "system_benchmark.json"
        )

    def test_no_file_no_cache(self, root: Path) -> None:
        assert hb.load_cached_benchmark() is None

    @pytest.mark.usefixtures("same_hardware")
    def test_a_saved_result_is_loaded_back(self, root: Path) -> None:
        result = _measured()
        hb.save_benchmark_cache(result)

        assert hb.get_benchmark_cache_path().parent.is_dir()
        assert hb.load_cached_benchmark() == result

    def test_a_cache_from_other_hardware_is_ignored(
        self, root: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        hb.save_benchmark_cache(_measured("fp-1"))
        monkeypatch.setattr(
            hb, "detect_hardware_profile", lambda: HardwareProfile(fingerprint="fp-2")
        )
        assert hb.load_cached_benchmark() is None
        # Ignored, not deleted: the next save overwrites it.
        assert hb.get_benchmark_cache_path().exists()

    @pytest.mark.usefixtures("same_hardware")
    @pytest.mark.parametrize(
        "content",
        [
            "{not json",
            # A field this version does not know (a cache written by a newer one).
            json.dumps({"hardware": {"fingerprint": "fp-1", "from_the_future": 1}}),
            json.dumps({"hardware": {"gpu_type": "quantum"}}),
        ],
    )
    def test_an_unreadable_cache_is_treated_as_absent(self, root: Path, content: str) -> None:
        path = hb.get_benchmark_cache_path()
        path.parent.mkdir(parents=True)
        path.write_text(content, encoding="utf-8")
        assert hb.load_cached_benchmark() is None

    def test_an_inconclusive_result_is_never_cached(self, root: Path) -> None:
        result = _measured()
        result.inconclusive = True
        hb.save_benchmark_cache(result)
        assert not hb.get_benchmark_cache_path().exists()

    def test_a_failed_write_is_logged_not_raised(
        self, root: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _refuse(*args: Any, **kwargs: Any) -> Any:
            raise PermissionError("locked by OneDrive")

        monkeypatch.setattr("builtins.open", _refuse)
        hb.save_benchmark_cache(_measured())  # must not raise

    @pytest.mark.usefixtures("same_hardware")
    def test_a_valid_cache_short_circuits_the_benchmark(
        self, root: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cached = _measured()
        hb.save_benchmark_cache(cached)
        monkeypatch.setattr(
            hb, "run_adaptive_benchmark", lambda **kwargs: pytest.fail("benchmark ran")
        )
        assert hb.get_or_run_benchmark() == cached

    @pytest.mark.usefixtures("same_hardware")
    def test_force_rerun_ignores_the_cache_and_replaces_it(
        self, root: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        hb.save_benchmark_cache(_measured())
        fresh = _measured()
        fresh.benchmark_date = "2026-12-01T00:00:00"
        seen: list[dict[str, Any]] = []

        def _rerun(**kwargs: Any) -> SystemBenchmarkResult:
            seen.append(kwargs)
            return fresh

        monkeypatch.setattr(hb, "run_adaptive_benchmark", _rerun)
        settings_obj = object()
        callback = lambda step, total, message: None  # noqa: E731

        result = hb.get_or_run_benchmark(
            force_rerun=True, quick_mode=True, progress_callback=callback, settings_obj=settings_obj
        )

        assert result is fresh
        assert seen == [
            {"quick_mode": True, "progress_callback": callback, "settings_obj": settings_obj}
        ]
        assert hb.load_cached_benchmark() == fresh

    def test_without_a_cache_the_benchmark_runs_and_is_saved(
        self, root: Path, monkeypatch: pytest.MonkeyPatch, same_hardware: None
    ) -> None:
        fresh = _measured()
        monkeypatch.setattr(hb, "run_adaptive_benchmark", lambda **kwargs: fresh)
        assert hb.get_or_run_benchmark() is fresh
        assert hb.load_cached_benchmark() == fresh

    def test_an_inconclusive_run_is_returned_but_not_frozen(
        self, root: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        inconclusive = _measured()
        inconclusive.inconclusive = True
        monkeypatch.setattr(hb, "run_adaptive_benchmark", lambda **kwargs: inconclusive)
        assert hb.get_or_run_benchmark() is inconclusive
        assert not hb.get_benchmark_cache_path().exists()


# ---------------------------------------------------------------------------
# Reporting helpers
# ---------------------------------------------------------------------------


class TestSummary:
    def test_the_summary_lists_hardware_results_and_recommendation(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        result = _measured()
        result.hardware = HardwareProfile(
            cpu_name="i7",
            gpu_name="Arc A770",
            gpu_type=GPUType.INTEL_ARC,
            gpu_memory_gb=16.0,
            total_memory_gb=32.0,
            openvino_devices=["CPU", "GPU"],
        )
        result.pipeline_live_results = {"GPU_LATENCY": _result("GPU", 40.0).to_dict()}

        hb.print_benchmark_summary(result)
        out = capsys.readouterr().out

        assert "CPU: i7" in out
        assert "GPU: Arc A770 (intel_arc)" in out
        assert "GPU Memory: 16.00 GB" in out
        assert "System RAM: 32.0 GB" in out
        assert "CPU_LATENCY: 50.0ms = 20.0 FPS" in out
        assert "GPU_LATENCY: 25.0ms = 40.0 FPS" in out
        assert "Device (Live): GPU with LATENCY" in out
        assert "Device (Batch): GPU with THROUGHPUT" in out
        assert "Model Cache: Enabled" in out
        assert "Estimated FPS (Batch): 44.0" in out

    def test_an_empty_result_prints_only_the_hardware(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        hb.print_benchmark_summary(SystemBenchmarkResult())
        out = capsys.readouterr().out
        assert "HARDWARE BENCHMARK SUMMARY" in out
        assert "Inference Performance" not in out
        assert "Live Camera Pipeline" not in out
        assert "RECOMMENDED CONFIGURATION" not in out
