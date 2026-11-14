"""Run pip-audit against the locked runtime dependencies (#648).

The same script is the CI gate (``lint`` job) and the local pre-push hook, so a
push that would turn CI red on a new advisory is stopped before it leaves the
machine. The exceptions live in ONE file, ``scripts/pip_audit_ignores.txt``.

What is audited is exactly what CI audits: ``poetry export -f requirements.txt
--without-hashes`` (the main group of ``poetry.lock``), with ``--strict``.

Outcomes:

- an advisory not in the ignore file: exit 1, always;
- the advisory database cannot be reached (no network, timeout, DNS): a warning
  and exit 0 locally -- CI stays the final gate -- and exit 1 with
  ``--fail-on-error`` (CI);
- any other failure of export or pip-audit: exit 1.

A green result is cached for the day in ``.git/zebtrack-pip-audit.json``, keyed
by the hashes of ``poetry.lock`` and the ignore file, so pushing several times
a day pays the network round trip once. ``--no-cache`` (CI) skips the cache.

Usage::

    python scripts/run_pip_audit.py                       # pre-push hook
    python scripts/run_pip_audit.py --no-cache --fail-on-error   # CI
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
IGNORE_FILE = REPO_ROOT / "scripts" / "pip_audit_ignores.txt"
LOCK_FILE = REPO_ROOT / "poetry.lock"

EXIT_OK = 0
EXIT_FAIL = 1

# Signatures of "the advisory service could not be reached", as printed by
# requests/urllib3 (pip-audit's HTTP stack) and the OS resolver.
_NETWORK_ERROR = re.compile(
    r"ConnectionError|ConnectTimeout|ReadTimeout|Timeout|Max retries exceeded|"
    r"NameResolutionError|getaddrinfo failed|Temporary failure in name resolution|"
    r"Failed to establish a new connection|Network is unreachable|"
    r"Connection (?:refused|reset|aborted)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


Runner = Callable[[Sequence[str]], CommandResult]


def _run(cmd: Sequence[str]) -> CommandResult:
    completed = subprocess.run(
        list(cmd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        cwd=REPO_ROOT,
    )
    return CommandResult(completed.returncode, completed.stdout, completed.stderr)


def parse_ignore_file(text: str) -> list[str]:
    """Return the advisory ids of the ignore file, in order, without duplicates."""
    ids: list[str] = []
    for raw in text.splitlines():
        entry = raw.split("#", 1)[0].strip()
        if not entry:
            continue
        if any(ch.isspace() for ch in entry):
            raise ValueError(f"one advisory id per line, got {raw!r}")
        if entry not in ids:
            ids.append(entry)
    return ids


def unignored_vulns(report: dict, ignored: Iterable[str]) -> list[str]:
    """Return ``"pkg version: ID"`` for each advisory of the report not ignored.

    An advisory counts as ignored when its id OR one of its aliases is listed,
    matching how pip-audit's ``--ignore-vuln`` treats aliases.
    """
    ignored_set = set(ignored)
    found: list[str] = []
    for dep in report.get("dependencies", []):
        for vuln in dep.get("vulns", []) or []:
            names = {vuln.get("id", "")} | set(vuln.get("aliases", []) or [])
            if names & ignored_set:
                continue
            found.append(f"{dep.get('name')} {dep.get('version')}: {vuln.get('id')}")
    return found


def is_network_failure(result: CommandResult) -> bool:
    return bool(_NETWORK_ERROR.search(result.stderr or "")) or bool(
        _NETWORK_ERROR.search(result.stdout or "")
    )


def cache_key(lock_bytes: bytes, ignore_bytes: bytes, today: dt.date) -> str:
    digest = hashlib.sha256()
    digest.update(lock_bytes)
    digest.update(b"\0")
    digest.update(ignore_bytes)
    return f"{today.isoformat()}:{digest.hexdigest()}"


def _cache_path(repo_root: Path) -> Path | None:
    git_dir = repo_root / ".git"
    if git_dir.is_file():  # a worktree: ".git" points at the real git dir
        content = git_dir.read_text(encoding="utf-8").strip()
        if content.startswith("gitdir:"):
            git_dir = Path(content.split(":", 1)[1].strip())
    if not git_dir.is_dir():
        return None
    return git_dir / "zebtrack-pip-audit.json"


def _read_cache(path: Path | None) -> str | None:
    if path is None or not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("green_key")
    except (OSError, ValueError, AttributeError):
        return None


def _write_cache(path: Path | None, key: str) -> None:
    if path is None:
        return
    try:
        path.write_text(json.dumps({"green_key": key}), encoding="utf-8")
    except OSError:
        print("pip-audit: could not write the cache stamp (ignored)", file=sys.stderr)


def audit(
    *,
    runner: Runner = _run,
    ignore_file: Path = IGNORE_FILE,
    lock_file: Path = LOCK_FILE,
    cache_file: Path | None = None,
    use_cache: bool = True,
    fail_on_error: bool = False,
    today: dt.date | None = None,
    pip_audit_cmd: Sequence[str] = (sys.executable, "-m", "pip_audit"),
) -> int:
    """Run the audit and return the process exit code (see module docstring)."""
    ignore_bytes = ignore_file.read_bytes()
    ignored = parse_ignore_file(ignore_bytes.decode("utf-8"))
    key = cache_key(lock_file.read_bytes(), ignore_bytes, today or dt.date.today())

    if use_cache and _read_cache(cache_file) == key:
        print("pip-audit: lock and exceptions unchanged since today's green run (cached)")
        return EXIT_OK

    with tempfile.TemporaryDirectory() as tmp:
        requirements = Path(tmp) / "requirements.txt"
        export = runner(
            [
                "poetry",
                "export",
                "-f",
                "requirements.txt",
                "--without-hashes",
                "-o",
                str(requirements),
            ]
        )
        if export.returncode != 0:
            print(f"pip-audit: `poetry export` failed:\n{export.stderr}", file=sys.stderr)
            return EXIT_FAIL

        cmd = [*pip_audit_cmd, "--strict", "-r", str(requirements), "--format", "json"]
        for vuln_id in ignored:
            cmd += ["--ignore-vuln", vuln_id]
        result = runner(cmd)

    report: dict | None
    try:
        report = json.loads(result.stdout) if result.stdout.strip() else None
    except ValueError:
        report = None

    if report is not None:
        found = unignored_vulns(report, ignored)
        if found:
            print("pip-audit: advisories without an exception:", file=sys.stderr)
            for line in found:
                print(f"  {line}", file=sys.stderr)
            print(
                "Upgrade the dependency, or add the id WITH its justification to "
                "scripts/pip_audit_ignores.txt.",
                file=sys.stderr,
            )
            return EXIT_FAIL
        if result.returncode == 0:
            _write_cache(cache_file, key)
            print(f"pip-audit: no known vulnerabilities ({len(ignored)} documented exceptions)")
            return EXIT_OK

    if is_network_failure(result):
        message = "pip-audit: the advisory database could not be reached"
        if fail_on_error:
            print(f"{message}.\n{result.stderr}", file=sys.stderr)
            return EXIT_FAIL
        print(
            f"WARNING: {message}; skipping the local audit. CI still runs it.",
            file=sys.stderr,
        )
        return EXIT_OK

    print(
        f"pip-audit failed (exit {result.returncode}):\n{result.stderr}{result.stdout}",
        file=sys.stderr,
    )
    return EXIT_FAIL


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--no-cache", action="store_true", help="always run the audit")
    parser.add_argument(
        "--fail-on-error",
        action="store_true",
        help="treat an unreachable advisory database as a failure (CI)",
    )
    args = parser.parse_args(argv)
    return audit(
        cache_file=_cache_path(REPO_ROOT),
        use_cache=not args.no_cache,
        fail_on_error=args.fail_on_error,
    )


if __name__ == "__main__":
    sys.exit(main())
