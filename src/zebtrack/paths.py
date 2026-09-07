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

from pathlib import Path
from typing import Final

# Markers that identify the repository root. ``pyproject.toml`` alone is not
# enough: a nested tool directory could carry one, and the root we want is the
# one that also holds the configuration the application loads.
_ROOT_MARKERS: Final[tuple[str, ...]] = ("pyproject.toml", "config.yaml")


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
