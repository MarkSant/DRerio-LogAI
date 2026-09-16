# DRerio LogAI v7.2.0

The documentation and prerequisites release. v7.1.0 made the program install and
open without a terminal; putting that in front of people who have never
programmed left two gaps — the installer still required a terminal whenever a
prerequisite was missing, and the README explained none of the terms it used.

## Relation to the published results

Unchanged. The validation and benchmark results reported in the associated
manuscripts were produced with release **4.0.0**, available as tag `v4.0.0`,
which remains the version to check out for exact reproduction. Releases 5 through
7 are subsequent work on the codebase and were not used to generate any reported
result.

## Installing this release

On Windows, download the source ZIP from this page, extract it somewhere
permanent, and double-click `install.bat`.

**It now installs the prerequisites it needs.** If Python 3.12 or Poetry is
missing, it offers to install them — Python through winget in user scope (no
administrator prompt), Poetry through its official installer — and puts Poetry on
your PATH. Answer `Y` to what it asks.

From a terminal, on any platform:

```bash
git clone https://github.com/MarkSant/DRerio-LogAI.git && cd DRerio-LogAI
poetry install
poetry run fetch-weights     # ~240 MiB of trained models, required
poetry run zebtrack
```

Python 3.12 or 3.13; **not** 3.14, where the pinned numpy has no wheel. No C
compiler is needed. Budget about 3 GB of free disk for the environment and the
models together.

Step-by-step instructions written for someone who has never opened a terminal:
[`docs/wiki/1_Installation.md`](../wiki/1_Installation.md) (English) ·
[`docs/wiki/1_Instalacao.md`](../wiki/1_Instalacao.md) (português).

**The model assets are unchanged**, and `weights_manifest.json` still points at
`v7.0.0`. That is deliberate: the manifest names a published release, so
`fetch-weights` works immediately rather than depending on this page.

## What changed

### The installer installs what is missing

Until now, a machine without Poetry got a PowerShell one-liner to paste and an
instruction to "add that folder to your PATH" — the single step of the install
that the researcher this script is written for cannot perform. A machine without
Python got the same shape of answer.

Three details decide whether this works on a clean machine, and all three were
learned by reading what the tools actually do:

- **Poetry installed but not on PATH is the common case**, because its own
  installer merely asks you to edit PATH and most people close the window.
  `Find-PoetryExecutable` looks in `POETRY_HOME` and the two default folders
  before giving up, and the script then uses the full path rather than the name.
- **The user PATH is read and written raw, as `REG_EXPAND_SZ`.**
  `[Environment]::GetEnvironmentVariable` expands `%USERPROFILE%`-style entries
  and `SetEnvironmentVariable` writes `REG_SZ`, so round-tripping through them
  would silently freeze every such entry in the PATH of whoever installs.
- **A process does not see the PATH another process just changed.** After winget
  runs, the session re-reads the registry, and the Python candidates include the
  per-user install folder — which is exactly where winget puts the interpreter.

`-Yes` accepts every offer without asking. Without it, an unattended run declines
rather than hanging: `-NonInteractive` makes `Read-Host` throw, and that is read
as "no".

### A README for the person who runs experiments

The README opened with 200 lines of release highlights for versions 4 through 7
and only reached installation on line 297. Between installation and the end came
VS Code extensions, the directory tree and test-suite statistics — developer
material in the path of someone who only wants to analyse videos.

It now follows the order in which a user needs things: what it is, what it does,
installation in five steps, first run, models and OpenVINO, first project,
parameters, outputs, common problems. The version history moved to
[`docs/releases/INDEX.md`](INDEX.md).

Three sections are new, because they existed nowhere and are exactly what is
missing on a first launch:

- **The six models, by camera angle.** A lateral model on a top-down recording
  detects nothing at all, and nothing said so.
- **The four roles and OpenVINO**, with the per-hardware rule the getting-started
  window applies: NVIDIA card ⇒ leave it off; Intel without NVIDIA ⇒ turn it on.
- **A parameter table** — confidence, NMS, ByteTrack, analysis interval, ROI rule
  — with when to raise and when to lower each. The values were read out of
  `config.yaml`, not from memory: confidence 0.05, NMS 0.5, match 0.95, buffer
  150, max distance 400 px, and `bbox_intersects` as the default ROI rule.

### Guides that describe this program

`GETTING_STARTED.md` described a different one: a 5-step wizard, `Ctrl+N` /
`Ctrl+R` / `Ctrl+Shift+A` shortcuts that do not exist, "NVIDIA GPU recommended",
JSON export and a YouTube channel. It was rewritten against the real interface —
7 steps for pre-recorded projects and 6 for live, the exact tab and button names,
the four model roles, the live flow with Arduino, and the files the program
really writes.

`TROUBLESHOOTING.md` told people to use `poetry shell`, removed in Poetry 2.0,
and asked for "Python 3.12 or higher", which includes 3.14 — where the install
fails.

Portuguese versions of the installation and user guides now exist alongside the
English ones, and the two link to each other.

### The DOI badge, and the version numbers

The DOI badge rendered as a broken icon on GitHub, on phones and desktops alike.
Zenodo's badge endpoint answers 200 to a direct request, but it is rate-limited
to 120 requests per minute and sent with `cache-control: no-cache`; README images
are fetched through GitHub's shared image proxy, which serves thousands of
repositories from the same addresses and therefore takes HTTP 429 often. It is a
static shields.io badge now, with the same text and the same link to `doi.org`.

**The five version declarations agree again.** v7.1.0 was published with
`src/zebtrack/__init__.py` and `.zenodo.json` still reading 7.0.1 — and since
`.zenodo.json`'s `version` overrides the tag name, that release's Zenodo record
is labelled 7.0.1.

## Full changelog

See [`CHANGELOG.md`](../../CHANGELOG.md) for the complete list with the reasoning
behind each change.
