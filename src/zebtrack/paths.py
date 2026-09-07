"""Project-root anchoring for the files the application reads and writes.

Every configuration file, weight and cache this project touches used to be
addressed by a bare relative path -- ``Path("config.yaml")``, ``config_dir="."``
-- which resolves against the *current working directory*. That works only
while the app is launched from the repository root, and it fails in the one
case a fresh user is most likely to hit::

    cd ~
    poetry -C /path/to/DRerio-LogAI run zebtrack
    # -> FileNotFoundError -> "Configuration File Not Found" -> exit(1)

The helpers here resolve those paths against the repository root instead, so
the launch directory stops mattering. Behaviour is unchanged for anyone
already running from the root: the resolved paths are the same files.

**Import-time evaluation is deliberate.** ``load_settings`` takes its config
paths as default arguments, and Python evaluates those once at import. Keeping
the resolution here -- rather than probing inside the function body -- means the
number and order of filesystem calls made by ``load_settings`` does not change,
which the existing ``patch("pathlib.Path.is_file", side_effect=[True, False])``
tests in ``tests/test_settings.py`` depend on.
"""

import os
from pathlib import Path, PurePath
from typing import Any, Final

# Markers that identify the repository root. ``pyproject.toml`` alone is not
# enough: a nested tool directory could carry one, and the root we want is the
# one that also holds the configuration the application loads.
_ROOT_MARKERS: Final[tuple[str, ...]] = ("pyproject.toml", "config.yaml")

DEFAULT_WEIGHTS_DIR: Final[str] = "weights"


def _find_repo_root() -> Path:
    """Walk upwards from this file until a directory carries every marker.

    Falls back to the ``src`` layout position (``paths.py`` -> ``src/zebtrack``
    -> ``src`` -> root) when no marked directory is found, so the result is
    always a concrete path and never the working directory.
    """
    here = Path(__file__).resolve()
    for parent in here.parents:
        if all((parent / marker).exists() for marker in _ROOT_MARKERS):
            return parent
    return here.parents[2]


_REPO_ROOT: Final[Path] = _find_repo_root()


def repo_root() -> Path:
    """Directory holding ``config.yaml``, ``weights/`` and the runtime caches."""
    return _REPO_ROOT


def default_config_path() -> Path:
    """Absolute path to the tracked base configuration."""
    return _REPO_ROOT / "config.yaml"


def default_local_config_path() -> Path:
    """Absolute path to the git-ignored per-machine override."""
    return _REPO_ROOT / "config.local.yaml"


def resolve_weights_dir(
    settings_obj: Any,
    config_dir: Path | str | None = None,
    override: Path | str | None = None,
) -> Path:
    """Resolve the folder holding the ``.pt`` weight files.

    Priority: explicit *override* > ``settings.weights.source_dir`` >
    :data:`DEFAULT_WEIGHTS_DIR`. Relative paths are anchored at *config_dir*,
    which defaults to the repository root.

    It lives here, and not next to :class:`~zebtrack.core.services.weight_manager.WeightManager`,
    so the startup pre-flight can ask where the weights are without importing
    that module -- which drags in torch, cv2, ultralytics and openvino, and
    spawns a thread pool, purely to answer a question about a path. That import
    belongs after the pre-flight, not before it.

    Defensive: any value that is not a real ``str`` or ``PurePath`` -- a Mock
    from partially-stubbed test settings, say -- is ignored in favour of the
    default. Testing against ``os.PathLike`` is NOT enough: ``MagicMock``
    implements ``__fspath__``, so it passes that check and ``os.fspath`` happily
    yields a path built out of the mock's own repr.
    """
    if override is not None:
        try:
            candidate = Path(os.fspath(override))
        except TypeError:
            candidate = Path(DEFAULT_WEIGHTS_DIR)
    else:
        source_dir: str | None = None
        if settings_obj is not None:
            weights_settings = getattr(settings_obj, "weights", None)
            if weights_settings is not None:
                raw = getattr(weights_settings, "source_dir", None)
                if isinstance(raw, str):
                    source_dir = raw
                elif isinstance(raw, PurePath):
                    source_dir = str(raw)
        candidate = Path(source_dir or DEFAULT_WEIGHTS_DIR)

    if not candidate.is_absolute():
        base = repo_root() if config_dir is None else Path(config_dir)
        candidate = base / candidate
    return candidate
