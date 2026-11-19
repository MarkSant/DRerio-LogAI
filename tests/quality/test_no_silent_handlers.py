"""No NEW broad exception handler may swallow a failure in silence (A5, TASK-087).

The A5 audit counted 532 ``except Exception`` in ``src/zebtrack``; 40 of them
neither logged nor re-raised. Most were harmless, but the same shape hid real
data loss elsewhere: a multi-aquarium stop that lost aquarium 2's trajectory
and still reported success (A5-S-001), a "Report generation finished." over a
batch where every video failed (A5-S-003). A silent handler costs nothing on
the day it is written; the researcher pays when a number is missing and no log
line says why.

A handler is SILENT when all of the following hold:

* it is broad: bare ``except:``, ``except Exception`` / ``BaseException``
  (alone or in a tuple), or a ``with contextlib.suppress(Exception)`` block;
* its body only passes, continues, breaks, returns or assigns, and nothing in
  it calls anything -- so it neither logs (``log.``/``logger.``/``self.log.``)
  nor re-raises nor tells anyone;
* it is not a DOCUMENTED FALLBACK: a ``return`` or an assignment, with a
  comment inside the handler saying why that value is the right answer.
  ``pass``/``continue``/``break`` are never a fallback, comment or not, and
  ``suppress(Exception)`` always counts as silent.

``ALLOWED_SILENT`` lists the handlers that exist today, keyed by
``<path>::<enclosing function>`` with their exact count and the verdict of
reading each one (``docs/audits/2026-11_A5_remaining_handlers.md``). A new
silent handler, or one more in an allowed function, fails; an entry whose
handlers are gone (or fewer) fails as stale. The list only SHRINKS: log the
failure, narrow the exception, or document the fallback.
"""

from __future__ import annotations

import ast
import io
import re
import tokenize
from collections import Counter
from collections.abc import Iterable, Iterator
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = REPO_ROOT / "src" / "zebtrack"

_BROAD = frozenset({"Exception", "BaseException"})
_QUIET = (ast.Pass, ast.Continue, ast.Break, ast.Return, ast.Assign, ast.AnnAssign, ast.AugAssign)
_FALLBACK = (ast.Return, ast.Assign, ast.AnnAssign, ast.AugAssign)

_SRC = "src/zebtrack/"
_DEAD_WIDGET = "Tk widget or canvas already destroyed; 'gone' is the answer (legitimate)"

# Verdicts from reading each handler on 2026-11-19; details per site in
# docs/audits/2026-11_A5_remaining_handlers.md. None hides a data failure.
ALLOWED_SILENT: dict[str, tuple[int, str]] = {
    _SRC + "__main__.py::_report_crash_without_a_console": (
        1,
        "crash reporter runs before logging exists; the default log path is the point",
    ),
    _SRC + "coordinators/video_processing_coordinator.py::VideoProcessingCoordinator"
    "._get_video_dimensions": (
        1,
        "cv2 fallback that runs only without the injected metadata service (A2-07, A5-S-011)",
    ),
    _SRC + "core/video/shared_frame_buffer.py::SharedFrameBuffer.close": (
        1,
        "SharedMemory.close() during cleanup must not propagate (legitimate)",
    ),
    _SRC + "ui/components/canvas/event_handler.py::CanvasEventHandler._editing_canvas": (
        1,
        _DEAD_WIDGET,
    ),
    _SRC + "ui/components/canvas/event_handler.py::CanvasEventHandler._handle_index_under_cursor": (
        2,
        _DEAD_WIDGET,
    ),
    _SRC + "ui/components/canvas/renderer.py::CanvasRenderer._get_canvas": (1, _DEAD_WIDGET),
    _SRC + "ui/components/canvas_manager.py::CanvasManager._get_canvas": (1, _DEAD_WIDGET),
    _SRC + "ui/components/dialog_manager.py::DialogManager.show_external_trigger_notice": (
        1,
        "cosmetic day label in the trigger notice; falls back to the raw day (legitimate)",
    ),
    _SRC + "ui/components/global_model_configuration_panel.py::GlobalModelConfigurationPanel"
    ".destroy": (1, "after_cancel during destroy(); the poller may already be gone (legitimate)"),
    _SRC + "ui/components/polygon_drawing_service.py::_is_multi_aquarium_context": (
        1,
        "reads a Tk variable of a panel that may be destroyed; single is the safe answer",
    ),
    _SRC + "ui/components/video_display.py::VideoDisplayWidget._draw_bg_image_to_canvas": (
        1,
        "Pillow resampling constant moved between versions; BICUBIC is the last resort",
    ),
    _SRC + "ui/wizard/custom_regex_dialog.py::CustomRegexDialog._initialize_geometry": (
        1,
        "dialog destroyed while its geometry is being set; nothing left to size",
    ),
    _SRC + "ui/wizard/model_selection_step.py::ModelSelectionStep._available_openvino_devices": (
        1,
        "OpenVINO device probe for the wizard; no devices leaves only AUTO (legitimate; "
        "its only comment is a pragma)",
    ),
    _SRC + "ui/wizard/wizard_dialog.py::WizardDialog._initialize_geometry": (
        1,
        "dialog destroyed while its geometry is being set; nothing left to size",
    ),
}


def _names(node: ast.expr | None) -> set[str]:
    if node is None:
        return set()
    if isinstance(node, ast.Tuple):
        return set().union(*(_names(elt) for elt in node.elts))
    if isinstance(node, ast.Name):
        return {node.id}
    if isinstance(node, ast.Attribute):
        return {node.attr}
    return set()


def _is_broad(handler: ast.ExceptHandler) -> bool:
    return handler.type is None or bool(_names(handler.type) & _BROAD)


def _is_suppress_broad(item: ast.withitem) -> bool:
    call = item.context_expr
    if not isinstance(call, ast.Call):
        return False
    func = call.func
    name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
    return name == "suppress" and any(_names(arg) & _BROAD for arg in call.args)


# A comment that carries a tool directive documents nothing, whatever follows
# it: ``# pragma: no cover - defensive`` says nothing about why the fallback
# value is right, and such comments come and go with coverage and lint work --
# a handler must not turn silent the day someone deletes a pragma.
_DIRECTIVES = re.compile(r"pragma:|noqa|type:\s*ignore|nosec", re.IGNORECASE)


def _comment_lines(source: str) -> set[int]:
    """Lines holding a comment that explains something (two words or more)."""
    lines: set[int] = set()
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type != tokenize.COMMENT or _DIRECTIVES.search(token.string):
            continue
        if len(re.findall(r"[^\W\d_]{2,}", token.string)) >= 2:
            lines.add(token.start[0])
    return lines


def _documenting_lines(handler: ast.ExceptHandler, lines: list[str]) -> range:
    """The handler itself plus the comment block right above its ``except``.

    The project's convention is ``# except Exception justified: <why>`` on the
    lines just before the clause, so that block documents the handler too.
    """
    first = handler.lineno
    while first > 1 and lines[first - 2].lstrip().startswith("#"):
        first -= 1
    return range(first, (handler.end_lineno or handler.lineno) + 1)


def _is_silent(handler: ast.ExceptHandler, comments: set[int], lines: list[str]) -> bool:
    body = handler.body
    if not all(isinstance(stmt, _QUIET) for stmt in body):
        return False
    if any(isinstance(sub, ast.Call) for stmt in body for sub in ast.walk(stmt)):
        return False
    is_fallback = any(isinstance(stmt, _FALLBACK) for stmt in body)
    documented = any(line in comments for line in _documenting_lines(handler, lines))
    return not (is_fallback and documented)


def _scoped(tree: ast.AST) -> Iterator[tuple[str, ast.AST]]:
    def visit(node: ast.AST, scope: tuple[str, ...]) -> Iterator[tuple[str, ast.AST]]:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
                yield from visit(child, (*scope, child.name))
            else:
                yield ".".join(scope) or "<module>", child
                yield from visit(child, scope)

    yield from visit(tree, ())


def silent_handlers(source: str) -> list[tuple[str, int]]:
    """``(enclosing scope, line)`` of every silent broad handler in ``source``."""
    tree = ast.parse(source)
    comments = _comment_lines(source)
    lines = source.splitlines()
    found: list[tuple[str, int]] = []
    for scope, node in _scoped(tree):
        if (
            isinstance(node, ast.ExceptHandler)
            and _is_broad(node)
            and _is_silent(node, comments, lines)
        ):
            found.append((scope, node.lineno))
        elif isinstance(node, ast.With | ast.AsyncWith):
            found.extend((scope, node.lineno) for item in node.items if _is_suppress_broad(item))
    return found


def scan(files: Iterable[Path], root: Path = REPO_ROOT) -> Counter[str]:
    hits: Counter[str] = Counter()
    for path in files:
        rel = path.resolve().relative_to(root).as_posix()
        for scope, _line in silent_handlers(path.read_text(encoding="utf-8")):
            hits[f"{rel}::{scope}"] += 1
    return hits


def _package_hits() -> Counter[str]:
    return scan(sorted(PACKAGE_ROOT.rglob("*.py")))


def _format(entries: dict[str, int]) -> str:
    return "\n".join(f"  {key} ({n})" for key, n in sorted(entries.items()))


def test_no_new_silent_broad_handler() -> None:
    hits = _package_hits()
    extra = {key: n - ALLOWED_SILENT.get(key, (0, ""))[0] for key, n in hits.items()}
    extra = {key: n for key, n in extra.items() if n > 0}
    assert not extra, (
        "broad except that neither logs, re-raises nor returns a documented fallback:\n"
        + _format(extra)
        + "\nLog the failure (log.<level>('domain.action.failed', ...)), narrow the exception, "
        "or document why the fallback value is right in a comment inside the handler."
    )


def test_allowed_silent_has_no_stale_entries() -> None:
    hits = _package_hits()
    stale = {
        key: count - hits.get(key, 0)
        for key, (count, _reason) in ALLOWED_SILENT.items()
        if hits.get(key, 0) < count
    }
    assert not stale, "silent handlers that are gone; shrink ALLOWED_SILENT:\n" + _format(stale)


def test_every_allowance_states_its_verdict() -> None:
    assert all(count >= 1 and len(reason) >= 30 for count, reason in ALLOWED_SILENT.values())


# --- the scanner itself -------------------------------------------------------


@pytest.mark.parametrize(
    "handler",
    [
        "except Exception:\n        pass",
        "except:\n        pass",
        "except (ValueError, Exception):\n        continue",
        "except BaseException:\n        return None",
        "except Exception:\n        # a comment does not make pass a fallback\n        pass",
        "except Exception as exc:\n        value = 0",
        "except Exception:  # pragma: no cover - defensive\n        return None",
        "except Exception:  # noqa: BLE001\n        return None",
    ],
)
def test_silent_handlers_are_found(handler: str) -> None:
    source = f"def f(items):\n    try:\n        g()\n    {handler}\n"
    assert silent_handlers(source) == [("f", 4)]


@pytest.mark.parametrize(
    "handler",
    [
        "except Exception:\n        log.warning('x.failed')",
        "except Exception:\n        self.log.error('x.failed')",
        "except Exception:\n        raise",
        "except Exception:\n        notify_user()",
        "except Exception:\n        # width probe fails on a destroyed widget: 0 hides it\n"
        "        return 0",
        "except Exception:  # documented: stub settings in tests\n        value = None",
        "# except Exception justified: the probe may fail on a dead widget\n"
        "    except Exception:\n        return False",
        "except ValueError:\n        pass",
    ],
)
def test_handlers_that_answer_are_not_silent(handler: str) -> None:
    source = f"def f():\n    try:\n        g()\n    {handler}\n"
    assert silent_handlers(source) == []


def test_suppress_exception_is_silent_and_suppress_narrow_is_not() -> None:
    source = (
        "import contextlib\n"
        "class W:\n"
        "    def close(self):\n"
        "        with contextlib.suppress(Exception):\n"
        "            self.a()\n"
        "        with contextlib.suppress(OSError):\n"
        "            self.b()\n"
    )
    assert silent_handlers(source) == [("W.close", 4)]


def test_scan_counts_per_enclosing_scope(tmp_path: Path) -> None:
    module = tmp_path / "mod.py"
    module.write_text(
        "def f():\n"
        "    try:\n        a()\n    except Exception:\n        pass\n"
        "    try:\n        b()\n    except Exception:\n        pass\n",
        encoding="utf-8",
    )
    assert scan([module], root=tmp_path) == Counter({"mod.py::f": 2})
