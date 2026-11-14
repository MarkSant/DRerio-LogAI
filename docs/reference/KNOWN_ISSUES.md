# Known Issues

Last verified: 2026-11-14 against the `main` sources of release 8.0.0.

## Test suite

### Current shape

`pytest --collect-only` reports **10033** tests. The markers in `pytest.ini` split them as
follows:

| Selection                    | Command                         | Tests |
| ---------------------------- | ------------------------------- | ----- |
| Fast (default)               | `pytest`                        | 8635  |
| GUI (`gui` marker)           | `pytest -m gui -n0`             | 1374  |
| Slow (`slow` marker)         | `pytest -m slow`                | 24    |
| Everything                   | `pytest -m "" -n0`              | 10033 |

The GUI suite passes on its own: `pytest -m gui -n0` finished with 1374 passed in 73 s on
2026-11-14. The fast suite excludes `gui`, `slow` and `ttkbootstrap_singleton` through the `-m`
expression in `addopts`; a `-m` given on the command line replaces it.

### GUI tests must run without xdist workers

ttkbootstrap keeps a process-wide `Style` singleton that holds references to Tk instances. Under
`pytest-xdist` (`-n N` with `N > 0`) that state is shared in ways the GUI tests do not tolerate.
`pytest.ini` therefore passes `-n0` in `addopts`, so a plain `pytest` already runs sequentially;
pass `-n auto` explicitly to parallelise the fast suite and never combine it with `-m gui`. CI
runs the GUI suite as `pytest -m gui -n0 --reruns 2` under `xvfb-run`.

The `ttkbootstrap_singleton` marker is still declared in `pytest.ini` but no test carries it
today, so it deselects nothing.

### Open: a test helper leaves a fake OpenVINO runtime installed

`tests/test_openvino_batch_inference.py` (the `_make_plugin` helper) executes
`sys.modules["openvino"] = MagicMock()` when OpenVINO is not importable and never removes it. On a
machine without OpenVINO every test that runs afterwards in the same process sees a fake runtime
instead of an `ImportError`. The behaviours that file covers are also covered without mocks by
`TestDetectBatch` in `tests/plugins/test_openvino_detector.py`. Tracked as A7-08 in
`docs/audits/2026-11_loose_ends.md`.

## Reporting a new issue

Open a GitHub issue with the failing command, the full output and the output of
`python -c "import zebtrack; print(zebtrack.__file__)"`. In a git worktree, run
`source scripts/wt-env.sh` first (see `CLAUDE.md`), otherwise the tests may exercise the main
checkout's sources.
