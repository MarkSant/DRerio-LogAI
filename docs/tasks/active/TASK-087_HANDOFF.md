# TASK-087 — handoff prompt for the next session

Copy everything below the line into a new Claude Code session opened on the repository.

---

Continue TASK-087, the test-coverage and loose-ends campaign of DRerio LogAI. It was started in
the Claude Code session "Plano de cobertura de testes" (`local_e88384ce-36c3-42fd-8714-1d1b422b9915`);
if you can read that session's transcript, use it for detail, but everything you need is here and in
the repository.

## Where things are

- Branch `worktree-cov-plugins-utils`, worktree
  `.claude/worktrees/cov-plugins-utils`, pushed. Draft PR MarkSant/DRerio-LogAI#717 against `main`,
  with Auto-fix on. Last pushed commit `008f3271`. Work in that worktree, on that branch.
- Read first, in this order:
  1. `CLAUDE.md` (project rules; "What counts as a test" is the standard for every test here).
  2. `docs/tasks/active/ROLLING_TASK_LOG.md`, entry TASK-087.
  3. `docs/audits/2026-11_loose_ends.md` (the register: status and decision of every finding).
  4. The detailed reports next to it: `2026-11_A1_events.md`, `2026-11_A2_dead_code.md`,
     `2026-11_A5_silent_failures.md` (has the fix-status table), `2026-11_A7_config_docs.md`,
     `2026-11_F2_viewmodels.md`, `2026-11_F2_video.md`, `2026-11_F2_project.md`,
     `2026-11_F2_ui_dialogs.md`.
  5. `docs/testing/COVERAGE_BASELINE.md` (gates and per-package floors).

## Done (do not redo)

- Coverage floors per package in CI (`scripts/coverage_summary.py --fail-under`): plugins 94,
  utils 92, core.viewmodels 96, core.video 94. Global gates raised to 65.0 / 35.5 / 57.0 (core-Linux,
  GUI-Linux, core-Windows), measured by CI at 66.32 / 36.12 / 58.24 on `ec86f146`.
- Phase 1: plugins/ and utils/ at about 97 %; four real defects fixed (OpenVINO mask letterbox,
  OpenVINO height/width swap, benchmark compiled-cache path, benchmark video handle).
- Phase 2 done: core/viewmodels (99 %), core/video (97 %), UI dialogs (four 0 % dialogs now 89-96 %
  in the GUI suite), core/project (merged up to `6f0e7a2d`; final numbers not reported yet).
- A1 events: `_publish_event` typed as `UIEvents`; `tests/quality/test_no_orphan_ui_events.py`
  checks three directions with shrink-only allowlists.
- A2 dead code: modules and classes removed in two batches (about 6,500 lines).
- A5: all seven `data` findings fixed, plus A5-S-009 (camera dialog).
- A7: impact_analyzer cp1252 crash, KNOWN_ISSUES.md, impact map paths, pytest.ini comments.
- A4-01: unified report reads ROI names/colours from every aquarium.
- CI on `6962d420` failed on 2 Windows + 3 Linux tests; fixed in `008f3271` (test-only). Check
  that this CI run is green before anything else; Auto-fix will also report it.

## What is left, in order

1. **CI of PR 717 green on `008f3271`.** If red, fix first.
2. **Measure and lock in.** Run the core suite with coverage (see "How to run" below), then raise the
   global gates in `.github/workflows/ci.yml` to what CI measures (about 1 point under), add a floor
   for `core.project` and record everything in `docs/testing/COVERAGE_BASELINE.md`. Update the PR
   description (it predates the UI and core/project fronts and A4-01).
3. **Reported defects, not fixed yet** (each has a strict-xfail test or an audit row; confirm by
   reading the code, write or flip the red test, fix, add a mutation block):
   - F2-P-001: `remove_video_entry(delete_files=True)` rmtree()s the video's PARENT folder, deleting
     sibling videos. Data loss: highest priority. Confirm before fixing.
   - F2-P-002, F2-P-003, F2-P-004 (`docs/audits/2026-11_F2_project.md`).
   - F2-UI-002: the live pipeline calls `preview_window.update_frame`, which the two-aquarium
     preview window does not have.
   - F2-UI-007 / F2-UI-008: camera-disconnect dialog never closed after "wait"; aquarium-detection
     dialog closes only at frame >= 100 while detection ends at <= 10 frames.
   - F2-UI-003 / F2-UI-009: regex preview shows `None` with alternated groups and is
     case-sensitive while the project import is not (the same rule lives in three places).
   - A4-13: `_run_analysis_pipeline` reads the GLOBAL zones although it receives `video_path`. Trace
     whether a pre-recorded project batch reaches it before changing anything.
   - A4-02: live completion dialog counts raw track ids as animals (use `count_subjects()`).
   - v8 audit leftovers in `docs/tasks/v8/AUDIT.md` (distance summed across tracking gaps,
     `fillna(0)` in freezing, keyword arguments at `live_analysis_post_processor.py`).
4. **Phase 2, `core/recording`** (82 % line, 70 % branch). Delegate (see below).
5. **A3 dependency injection** (three `ProjectService` instances, twelve decorative registrations,
   unread `MainViewModelDependencies` fields). Do it yourself: it crosses every flow.
6. **A6 threads/Tk**: `time.sleep` on the Tk thread (`report_generator_actions.py` deletion retry,
   `live_calibration_coordinator.py`), `psutil.cpu_percent(interval=0.5)` from the live wizard step.
7. **A8**: one end-to-end golden test per flow (pre-recorded project, single video, live project,
   ad-hoc live), on `tests/helpers/prerecorded_pipeline.py` and
   `docs/testing/LIVE_FLOW_TEST_PROTOCOL.md`.
8. **A2 tail**: 206 zero-reference functions in `2026-11_A2_dead_code.md` (only 14 were read one
   by one). Read each before proposing deletion; deletion is the maintainer's decision.
9. **Close**: mark TASK-087 done in the rolling log, register every row of the loose-ends file as
   fixed / accepted / open, take the PR out of draft only when the maintainer asks.

## How to run (Windows, OneDrive)

- In this worktree, `source scripts/wt-env.sh` and `poetry run` do not work from a worktree-isolated
  session. Use PowerShell `. .\scripts\wt-env.ps1` for git commit/push (the hooks are the CI gates,
  never `--no-verify`). For Python in Bash, set `PATH` to the main repo's `.venv/Scripts` first and
  `PYTHONPATH` to `<worktree>/src`, then check `python -c "import zebtrack; print(zebtrack.__file__)"`.
- Core suite with coverage: `python -m pytest -m "not gui" --cov-branch --cov-report=xml:<scratch>/c.xml`
  (about 6 min), then `python scripts/coverage_summary.py <scratch>/c.xml --below 0`. Never narrow
  `--cov` to one module.
- Always pass `--basetemp=<scratch>/<name>` when more than one pytest can run at once (subagents
  share the temp folder otherwise).
- `scripts/impact_analyzer.py` before every source change; mutation blocks append to the end of
  `scripts/mutation_catalog.yaml`; `python scripts/mutation_check.py --module <block>`.
- New `_()` strings: `python scripts/update_translations.py`, fill the pt_BR `msgstr`,
  `python scripts/compile_translations.py`. Merge conflicts in the catalogue: keep both sides;
  in `.po`/`.pot`/`.mo`: take ours, regenerate, refill from the other branch's `.po` (polib).
- Every git command prints "failed to delete .git/worktrees/...: Permission denied"; harmless.
- Write substitution scripts to files with the Write tool (heredocs eat backslashes) and edit by
  bytes, preserving line endings.

## Delegation

The user asked to delegate what can be delegated, to cheaper models, in parallel:

- Separate sessions (`start_session`) are refused when the user is on Remote Control; then use
  background subagents (`Agent` with `isolation: "worktree"`, `model`, `effort`).
- Opus 5.5, effort `medium` for work that touches contracts or flows (core/recording, A4-13).
  Sonnet 5.5, effort `high` for read-and-report audits and isolated test work (A6 report, A2 tail
  reading, UI dialog defects). Keep A3, A4 fixes, merges and the final integration yourself.
- At most two agents running tests at once; give each `--basetemp`.
- Every brief: check the worktree is at or after the branch tip (`git merge --ff-only
  worktree-cov-plugins-utils` if not), the environment traps above, the test standard (derive
  expected values from the input; mutation blocks; one test file per module; red test before a
  fix; anything beyond a local obvious bug is reported, not changed), which files are off limits,
  a NEW audit file of its own (never edit `2026-11_loose_ends.md`), and COMMIT AFTER EACH PIECE:
  agents were cut off by the usage limit five times in the previous session, and resuming them with
  `SendMessage` worked only because they had committed.
- Review every agent's diff before merging; agents wrote Windows-only path tests once.

## Rules from the maintainer

- Communicate in Portuguese.
- Deleting code is the maintainer's decision; propose with evidence.
- Push before credits run out, so CI reports coverage.
- Do not merge the PR; do not enable auto-merge.
