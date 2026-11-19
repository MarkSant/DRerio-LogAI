"""In-memory stand-ins for the inference backends the detector plugins wrap.

The real OpenVINO runtime needs an exported model on disk and a device to
compile it for, so a test that wants to drive ``OpenVINOPlugin.__init__`` or
``detect`` end to end cannot use it. These fakes implement exactly the slice of
the OpenVINO Python API the plugin touches, and nothing else, so that:

- the plugin's OWN code runs for real (device choice, config building,
  fallback, output discovery, pre- and post-processing, the Ultralytics NMS);
- every decision the plugin hands to the runtime is recorded and can be
  asserted (``FakeCore.compile_calls``, ``FakeInferRequest.inputs``).

Install with :func:`install_fake_openvino`, which swaps the module-level ``ov``
of ``zebtrack.plugins.openvino_detector`` for a :class:`FakeOpenVINO`.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np

DEFAULT_ANCHORS = 16


class FakeDimension:
    """One axis of a partial shape; ``None`` means dynamic."""

    def __init__(self, length: int | None) -> None:
        self._length = length

    @property
    def is_static(self) -> bool:
        return self._length is not None

    def get_length(self) -> int:
        if self._length is None:
            raise RuntimeError("dynamic dimension has no length")
        return self._length

    def __int__(self) -> int:
        return self.get_length()


class FakePartialShape:
    """``ov.PartialShape`` reduced to rank, length and indexing."""

    def __init__(self, dims: Sequence[int | None] | None) -> None:
        # ``None`` models a shape of dynamic RANK (not just dynamic axes).
        self._dims = None if dims is None else [FakeDimension(d) for d in dims]

    @property
    def rank(self) -> SimpleNamespace:
        return SimpleNamespace(is_static=self._dims is not None)

    def __len__(self) -> int:
        if self._dims is None:
            raise RuntimeError("shape of dynamic rank has no length")
        return len(self._dims)

    def __getitem__(self, index: int) -> FakeDimension:
        if self._dims is None:
            raise RuntimeError("shape of dynamic rank cannot be indexed")
        return self._dims[index]


class FakePort:
    """An input or output port. Hashable by identity, like ``ov.Output``."""

    def __init__(self, name: str, dims: Sequence[int | None] | None) -> None:
        self.any_name = name
        self.partial_shape = FakePartialShape(dims)
        self.shape = list(dims) if dims is not None else []

    def __repr__(self) -> str:
        return f"<FakePort {self.any_name}>"


class FakeInferRequest:
    """Synchronous request: records its input and serves the queued results."""

    def __init__(self, compiled: FakeCompiledModel) -> None:
        self._compiled = compiled
        self.inputs: list[np.ndarray] = []
        self.results: dict[FakePort, np.ndarray] = {}

    def infer(self, inputs: dict[str, np.ndarray]) -> None:
        if self._compiled.infer_error is not None:
            raise self._compiled.infer_error
        (tensor,) = inputs.values()
        assert set(inputs) == {self._compiled.input(0).any_name}
        self.inputs.append(tensor)
        self.results = self._compiled.next_results()


class FakeCompiledModel:
    """A compiled model with one input and a detection (+ optional proto) output."""

    def __init__(
        self,
        *,
        input_dims: Sequence[int | None] | None,
        output_dims: Sequence[Sequence[int | None]],
        device_name: str,
        config: dict[str, Any],
        properties: dict[str, Any] | None = None,
    ) -> None:
        self._input = FakePort("images", input_dims)
        self.outputs = [FakePort(f"output{i}", dims) for i, dims in enumerate(output_dims)]
        self.device_name = device_name
        self.config = dict(config)
        self._properties = properties
        self._queued: list[dict[FakePort, np.ndarray]] = []
        self.infer_error: Exception | None = None
        self.requests: list[FakeInferRequest] = []

    def input(self, index: int) -> FakePort:
        assert index == 0
        return self._input

    def output(self, index: int) -> FakePort:
        return self.outputs[index]

    def create_infer_request(self) -> FakeInferRequest:
        request = FakeInferRequest(self)
        self.requests.append(request)
        return request

    def get_property(self, name: str) -> Any:
        if self._properties is None or name not in self._properties:
            raise RuntimeError(f"unsupported property {name}")
        return self._properties[name]

    def queue_results(self, *tensors: np.ndarray | None) -> None:
        """Queue one inference result; ``tensors`` align with ``outputs``.

        The last queued result is served again once the queue runs dry, so a
        test that only cares about one frame needs a single call.
        """
        result = {
            port: tensor
            for port, tensor in zip(self.outputs, tensors, strict=True)
            if tensor is not None
        }
        self._queued.append(result)

    def next_results(self) -> dict[FakePort, np.ndarray]:
        if not self._queued:
            return {}
        if len(self._queued) == 1:
            return self._queued[0]
        return self._queued.pop(0)


class FakeModel:
    """What ``Core.read_model`` returns: only the input port is inspected."""

    def __init__(self, path: str, input_dims: Sequence[int | None] | None) -> None:
        self.path = path
        self._input = FakePort("images", input_dims)
        self.input_error: Exception | None = None

    def input(self, index: int) -> FakePort:
        if self.input_error is not None:
            raise self.input_error
        assert index == 0
        return self._input


class FakeCore:
    """``ov.Core``: device list, model reading and (recorded) compilation."""

    def __init__(self, backend: FakeOpenVINO) -> None:
        self._backend = backend
        self.available_devices = list(backend.available_devices)

    def read_model(self, path: str) -> FakeModel:
        model = FakeModel(str(path), self._backend.input_dims)
        model.input_error = self._backend.model_input_error
        self._backend.models.append(model)
        return model

    def compile_model(
        self, *, model: FakeModel, device_name: str, config: dict[str, Any]
    ) -> FakeCompiledModel:
        self._backend.compile_calls.append((device_name, dict(config)))
        if device_name in self._backend.failing_devices:
            raise RuntimeError(f"cannot compile for {device_name}")
        compiled = FakeCompiledModel(
            input_dims=self._backend.input_dims,
            output_dims=self._backend.output_dims,
            device_name=device_name,
            config=config,
            properties=self._backend.properties,
        )
        compiled.infer_error = self._backend.infer_error
        for tensors in self._backend.pending_results:
            compiled.queue_results(*tensors)
        self._backend.compiled.append(compiled)
        return compiled


class FakeAsyncInferQueue:
    """``ov.AsyncInferQueue`` that completes requests in REVERSE submission order.

    Real requests finish in whatever order the device returns them, so a caller
    that stores results by completion order instead of by ``userdata`` is wrong.
    Completing them backwards makes that mistake visible deterministically.
    """

    def __init__(self, compiled: FakeCompiledModel, jobs: int) -> None:
        self._compiled = compiled
        self.jobs = jobs
        self._callback: Any = None
        self._pending: list[tuple[dict[FakePort, np.ndarray], int]] = []
        self.submitted: list[int] = []
        compiled_queues = getattr(compiled, "async_queues", None)
        if compiled_queues is None:
            compiled.async_queues = []  # type: ignore[attr-defined]
        compiled.async_queues.append(self)  # type: ignore[attr-defined]

    def set_callback(self, callback: Any) -> None:
        self._callback = callback

    def start_async(self, inputs: dict[str, np.ndarray], userdata: int) -> None:
        assert set(inputs) == {self._compiled.input(0).any_name}
        self.submitted.append(userdata)
        self._pending.append((self._compiled.next_results(), userdata))

    def wait_all(self) -> None:
        for results, userdata in reversed(self._pending):
            self._callback(SimpleNamespace(results=results), userdata)
        self._pending.clear()


class FakeOpenVINO:
    """The ``openvino`` module as the plugin sees it (``ov.Core``, ``ov.AsyncInferQueue``).

    Args:
        input_dims: Input partial shape, ``[1, 3, H, W]`` by default. ``None``
            models an input of dynamic rank.
        output_dims: One partial shape per model output.
        available_devices: What ``Core.available_devices`` reports.
        failing_devices: Devices whose compilation raises.
        properties: Compiled-model properties; ``None`` makes every query raise.
    """

    def __init__(
        self,
        *,
        input_dims: Sequence[int | None] | None = (1, 3, 640, 640),
        output_dims: Sequence[Sequence[int | None]] = ((1, 6, DEFAULT_ANCHORS),),
        available_devices: Sequence[str] = ("CPU", "GPU"),
        failing_devices: Sequence[str] = (),
        properties: dict[str, Any] | None = None,
    ) -> None:
        self.input_dims = input_dims
        self.output_dims = [tuple(dims) for dims in output_dims]
        self.available_devices = list(available_devices)
        self.failing_devices = set(failing_devices)
        self.properties = properties
        self.model_input_error: Exception | None = None
        # Copied onto every model compiled afterwards (so it also hits warm-up).
        self.infer_error: Exception | None = None
        self.async_queue_error: Exception | None = None
        self.pending_results: list[tuple[np.ndarray | None, ...]] = []
        self.models: list[FakeModel] = []
        self.compiled: list[FakeCompiledModel] = []
        self.compile_calls: list[tuple[str, dict[str, Any]]] = []

    def Core(self) -> FakeCore:
        return FakeCore(self)

    def AsyncInferQueue(self, compiled: FakeCompiledModel, jobs: int) -> FakeAsyncInferQueue:
        if self.async_queue_error is not None:
            raise self.async_queue_error
        return FakeAsyncInferQueue(compiled, jobs)

    def queue_results(self, *tensors: np.ndarray | None) -> None:
        """Queue a result for models compiled LATER (i.e. before the plugin exists)."""
        self.pending_results.append(tensors)


def install_fake_openvino(monkeypatch: Any, backend: FakeOpenVINO | None = None) -> FakeOpenVINO:
    """Point ``openvino_detector.ov`` at a fake backend and mark it available."""
    from zebtrack.plugins import openvino_detector

    backend = backend or FakeOpenVINO()
    monkeypatch.setattr(openvino_detector, "ov", backend)
    monkeypatch.setattr(openvino_detector, "OPENVINO_AVAILABLE", True)
    return backend


def write_openvino_model_dir(
    directory: Path, *, class_names: dict[int, str] | None = None, metadata_text: str | None = None
) -> Path:
    """Create the files ``OpenVINOPlugin`` looks for in a model directory.

    Args:
        directory: Directory to create.
        class_names: Written to ``metadata.json`` when given.
        metadata_text: Raw ``metadata.json`` content (overrides ``class_names``),
            for corrupt-file cases.
    """
    import json

    directory.mkdir(parents=True, exist_ok=True)
    (directory / "model.xml").write_text("<net/>", encoding="utf-8")
    (directory / "model.bin").write_bytes(b"\x00")
    if metadata_text is not None:
        (directory / "metadata.json").write_text(metadata_text, encoding="utf-8")
    elif class_names is not None:
        payload = {"class_names": {str(k): v for k, v in class_names.items()}}
        (directory / "metadata.json").write_text(json.dumps(payload), encoding="utf-8")
    return directory


def detection_tensor(
    boxes: Sequence[tuple[float, float, float, float, float, int]],
    *,
    num_classes: int,
    num_masks: int = 0,
    anchors: int = DEFAULT_ANCHORS,
) -> np.ndarray:
    """Build a raw YOLO head output ``[1, 4 + nc + nm, anchors]``.

    Args:
        boxes: ``(cx, cy, w, h, score, class_id)`` in MODEL-INPUT pixels, one per
            anchor; the remaining anchors are empty (score 0).
        num_classes: Number of class channels.
        num_masks: Number of mask-coefficient channels (0 for detection weights).
        anchors: Width of the tensor.
    """
    assert len(boxes) <= anchors
    tensor = np.zeros((1, 4 + num_classes + num_masks, anchors), dtype=np.float32)
    for index, (cx, cy, w, h, score, class_id) in enumerate(boxes):
        tensor[0, :4, index] = (cx, cy, w, h)
        tensor[0, 4 + class_id, index] = score
    return tensor


def openvino_settings(**openvino_overrides: Any) -> SimpleNamespace:
    """A settings stub carrying only what ``OpenVINOPlugin`` reads.

    Defaults mirror ``config.yaml`` for a CPU machine; override any
    ``settings.openvino`` field by keyword.
    """
    openvino: dict[str, Any] = {
        "device": "AUTO",
        "device_batch": "AUTO",
        "performance_hint_live": "LATENCY",
        "performance_hint_batch": "THROUGHPUT",
        "enable_model_cache": False,
        "cache_dir": None,
        "precision": "FP32",
        "num_streams": None,
        "num_threads": None,
        "npu_turbo": False,
        "batch_nireq": 4,
    }
    unknown = set(openvino_overrides) - set(openvino)
    assert not unknown, f"not an OpenVINO setting: {sorted(unknown)}"
    openvino.update(openvino_overrides)
    return SimpleNamespace(
        yolo_model=SimpleNamespace(
            confidence_threshold=0.4, animal_confidence_threshold=None, nms_threshold=0.5
        ),
        openvino=SimpleNamespace(**openvino),
        bytetrack=SimpleNamespace(track_threshold=0.6, match_threshold=0.85),
    )


def stop_session_that_completes(stopped: bool = True, returns: bool = True) -> Any:
    """``side_effect`` for a mocked ``LiveCameraService.stop_session``.

    Since A6-07 the real service finishes a stop through its ``on_stopped``
    callback (asynchronously when there is a Tk root). A bare ``return_value``
    never calls it, so the caller's finalization would never run.
    """

    def _stop(*_args: Any, on_stopped: Any = None, **_kwargs: Any) -> bool:
        if on_stopped is not None:
            on_stopped(stopped)
        return returns

    return _stop
