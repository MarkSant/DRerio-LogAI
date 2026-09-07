"""Download the trained detector weights the application needs in order to start.

The weights are ~200 MB of trained YOLO models. They are deliberately not in git
(``.gitignore``: ``*.pt``, ``weights/``), so a fresh clone installs cleanly, passes
the whole test suite -- which mocks them -- and then fails to open, on a dialog
that used to name neither the cause nor the remedy.

This module is that remedy. It reads ``weights_manifest.json`` from the
repository root, downloads whatever is missing or corrupt from the GitHub
release named there, and verifies every byte against a recorded SHA-256.

Run it as ``poetry run fetch-weights``. Console-script entry points must resolve
to an importable module, and ``scripts/`` is not part of the distribution
(``packages = [{include = "zebtrack", from = "src"}]``), which is why this lives
inside the package rather than next to the other developer scripts.

**Output is deliberately untranslated.** This runs before the application has
ever started, so before the first-run language prompt has been answered: there
is no chosen language to honour yet. It follows the precedent already set by the
fatal configuration dialogs in ``core/app_runner.py``, which stay in English for
the same reason.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from zebtrack.paths import repo_root

MANIFEST_NAME = "weights_manifest.json"
_CHUNK = 1024 * 1024
_MANIFEST_VERSION = 1

# urlopen would otherwise honour file:// and any registered custom scheme.
_ALLOWED_SCHEMES = frozenset({"http", "https"})


@dataclass(frozen=True)
class WeightEntry:
    """One downloadable weight file, as described by the manifest."""

    name: str
    sha256: str
    size_bytes: int
    weight_type: str
    perspective: str | None
    required: bool

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> WeightEntry:
        return cls(
            name=raw["name"],
            sha256=raw["sha256"],
            size_bytes=int(raw["bytes"]),
            weight_type=raw.get("type", "unknown"),
            perspective=raw.get("perspective"),
            required=bool(raw.get("required", True)),
        )


@dataclass(frozen=True)
class Manifest:
    """The manifest file: where the weights live and what they must hash to."""

    repository: str
    release_tag: str
    entries: tuple[WeightEntry, ...]

    def url_for(self, entry: WeightEntry) -> str:
        return (
            f"https://github.com/{self.repository}/releases/"
            f"download/{self.release_tag}/{entry.name}"
        )


def default_manifest_path() -> Path:
    """Absolute path to the manifest, anchored at the repository root."""
    return repo_root() / MANIFEST_NAME


def load_manifest(path: Path | None = None) -> Manifest:
    """Read and validate the manifest.

    Raises:
        FileNotFoundError: the manifest is missing.
        ValueError: the manifest is malformed or of an unknown version.
    """
    manifest_path = default_manifest_path() if path is None else path
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Weights manifest not found: {manifest_path}")

    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{manifest_path} is not valid JSON: {exc}") from exc

    version = raw.get("manifest_version")
    if version != _MANIFEST_VERSION:
        raise ValueError(
            f"{manifest_path} declares manifest_version {version!r}, "
            f"but this build understands only {_MANIFEST_VERSION}."
        )

    files = raw.get("files")
    if not isinstance(files, list) or not files:
        raise ValueError(f"{manifest_path} lists no files.")

    try:
        entries = tuple(WeightEntry.from_dict(item) for item in files)
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"{manifest_path} has a malformed file entry: {exc}") from exc

    return Manifest(
        repository=raw["repository"],
        release_tag=raw["release_tag"],
        entries=entries,
    )


def sha256_of(path: Path) -> str:
    """Stream a file through SHA-256 without holding it in memory."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(_CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_is_valid(path: Path, entry: WeightEntry) -> bool:
    """True when *path* exists and matches the manifest byte for byte.

    Size is checked first because it is a stat() away and rules out the common
    case -- a truncated download -- without hashing 80 MB to find out.
    """
    if not path.is_file():
        return False
    if path.stat().st_size != entry.size_bytes:
        return False
    return sha256_of(path) == entry.sha256


def _format_size(num_bytes: int) -> str:
    return f"{num_bytes / (1024 * 1024):.1f} MiB"


def _reject_unsupported_scheme(url: str) -> None:
    """Refuse anything but http/https before it reaches ``urlopen``.

    ``urlopen`` honours ``file:`` and any scheme a handler is registered for, so
    a manifest that named ``file:///etc/passwd`` would have it dutifully copied
    into ``weights/`` under a ``.pt`` name. The manifest is a tracked file and
    therefore trusted, but "trusted input" is exactly the assumption that stops
    being true the day someone accepts a manifest from elsewhere.

    Raises:
        RuntimeError: the URL uses a scheme this downloader will not fetch.
    """
    scheme = urllib.parse.urlparse(url).scheme.lower()
    if scheme not in _ALLOWED_SCHEMES:
        raise RuntimeError(
            f"Refusing to fetch {url!r}: scheme {scheme or '(none)'!r} is not allowed. "
            f"Only {', '.join(sorted(_ALLOWED_SCHEMES))} are."
        )


def download_entry(manifest: Manifest, entry: WeightEntry, dest_dir: Path) -> None:
    """Download one weight into *dest_dir*, verifying before it takes its name.

    The download lands on ``<name>.part`` and is renamed only after the hash
    matches, so an interrupted or corrupted transfer can never masquerade as a
    usable weight -- which would surface much later as silently bad detections
    rather than as an error.

    Raises:
        RuntimeError: the transfer failed, or the bytes did not verify.
    """
    url = manifest.url_for(entry)
    _reject_unsupported_scheme(url)
    part = dest_dir / f"{entry.name}.part"
    final = dest_dir / entry.name

    print(f"  downloading {entry.name} ({_format_size(entry.size_bytes)})", flush=True)
    part.unlink(missing_ok=True)

    try:
        # The scheme is restricted to http/https by _reject_unsupported_scheme()
        # above. bandit flags every urlopen call statically (B310) because it
        # cannot see a guard that is not inline, hence the marker on this line.
        with urllib.request.urlopen(url) as response, part.open("wb") as out:  # nosec B310
            copied = 0
            while chunk := response.read(_CHUNK):
                out.write(chunk)
                copied += len(chunk)
                pct = 100.0 * copied / entry.size_bytes if entry.size_bytes else 0.0
                print(f"\r    {_format_size(copied)} ({pct:.0f}%)", end="", flush=True)
        print()
    except urllib.error.HTTPError as exc:
        # HTTPError is itself a response object holding an open socket. It is
        # raised rather than entered, so nothing else will close it.
        exc.close()
        part.unlink(missing_ok=True)
        hint = ""
        if exc.code == 404:
            hint = (
                f"\n    The asset is missing from release '{manifest.release_tag}'."
                "\n    If you are the maintainer, upload the weights to that release"
                f"\n    (see {MANIFEST_NAME}); otherwise ask for an updated manifest."
            )
        raise RuntimeError(f"HTTP {exc.code} fetching {url}{hint}") from exc
    except urllib.error.URLError as exc:
        part.unlink(missing_ok=True)
        raise RuntimeError(f"Could not reach {url}: {exc.reason}") from exc

    actual = sha256_of(part)
    if actual != entry.sha256:
        part.unlink(missing_ok=True)
        raise RuntimeError(
            f"Checksum mismatch for {entry.name}.\n"
            f"    expected {entry.sha256}\n"
            f"    got      {actual}\n"
            "    The download was discarded. Re-run to try again."
        )

    part.replace(final)


def generate_manifest(
    source_dir: Path,
    dest: Path,
    *,
    repository: str,
    release_tag: str,
) -> int:
    """Rebuild the manifest by hashing the weights present in *source_dir*.

    The maintainer's step: run this once against a known-good ``weights/``, then
    commit the result and upload the same files as release assets.
    """
    files = sorted(source_dir.glob("*.pt"))
    if not files:
        print(f"No .pt files found in {source_dir}", file=sys.stderr)
        return 1

    entries = []
    for path in files:
        stem = path.stem.lower()
        weight_type = "seg" if "seg" in stem else "det"
        perspective = None
        if stem.endswith("_lateral"):
            perspective = "lateral"
        elif stem.endswith("_topdown"):
            perspective = "top_down"

        print(f"  hashing {path.name} ({_format_size(path.stat().st_size)})", flush=True)
        entries.append(
            {
                "name": path.name,
                "sha256": sha256_of(path),
                "bytes": path.stat().st_size,
                "type": weight_type,
                "perspective": perspective,
                # `required` tracks DISCOVERY, not quality: only the
                # perspective-suffixed names are matched by
                # WeightManager.discover_perspective_weights(). The flat-named
                # generalists have to be registered by hand, so they are not
                # part of the default download.
                "required": perspective is not None,
            }
        )

    payload = {
        "manifest_version": _MANIFEST_VERSION,
        "repository": repository,
        "release_tag": release_tag,
        "files": entries,
    }
    # newline="" keeps json's "\n" as-is. Path.write_text would translate it to
    # CRLF on Windows, which .gitattributes normalizes back on commit -- so the
    # file would arrive dirty on every regeneration for no reason.
    with dest.open("w", encoding="utf-8", newline="") as handle:
        handle.write(json.dumps(payload, indent=2) + "\n")
    print(f"Wrote {dest} ({len(entries)} entries)")
    return 0


def _selected(manifest: Manifest, *, include_optional: bool) -> list[WeightEntry]:
    return [e for e in manifest.entries if e.required or include_optional]


def _report_plan(entries: list[WeightEntry], dest_dir: Path) -> tuple[list[WeightEntry], int]:
    """Print what is already valid and return what still needs downloading."""
    missing: list[WeightEntry] = []
    for entry in entries:
        if file_is_valid(dest_dir / entry.name, entry):
            print(f"  ok      {entry.name}")
        else:
            print(f"  MISSING {entry.name} ({_format_size(entry.size_bytes)})")
            missing.append(entry)
    return missing, sum(e.size_bytes for e in missing)


def main(argv: list[str] | None = None) -> int:
    """Entry point for ``fetch-weights``. Returns a process exit code."""
    parser = argparse.ArgumentParser(
        prog="fetch-weights",
        description=(
            "Download the trained detector weights DRerio LogAI needs to start. "
            "Files are verified against a SHA-256 recorded in weights_manifest.json."
        ),
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Report what is present and valid without downloading anything.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Also fetch the generalist models the manifest marks optional.",
    )
    parser.add_argument(
        "--dest",
        type=Path,
        default=None,
        help="Directory to place the weights in (default: <repo>/weights).",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=None,
        help=f"Manifest to read (default: <repo>/{MANIFEST_NAME}).",
    )
    parser.add_argument(
        "--generate-manifest",
        action="store_true",
        help="Maintainer mode: rebuild the manifest by hashing the local weights.",
    )
    parser.add_argument(
        "--repository",
        default="MarkSant/DRerio-LogAI",
        help="With --generate-manifest: the owner/repo hosting the release.",
    )
    parser.add_argument(
        "--release-tag",
        default="v7.0.0",
        help="With --generate-manifest: the release tag holding the assets.",
    )
    args = parser.parse_args(argv)

    dest_dir = args.dest if args.dest is not None else repo_root() / "weights"

    if args.generate_manifest:
        manifest_path = args.manifest if args.manifest is not None else default_manifest_path()
        return generate_manifest(
            dest_dir,
            manifest_path,
            repository=args.repository,
            release_tag=args.release_tag,
        )

    try:
        manifest = load_manifest(args.manifest)
    except (FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    dest_dir.mkdir(parents=True, exist_ok=True)
    entries = _selected(manifest, include_optional=args.all)

    print(f"Weights directory: {dest_dir}")
    print(f"Release:           {manifest.repository} @ {manifest.release_tag}")
    missing, total = _report_plan(entries, dest_dir)

    if not missing:
        print("\nAll weights present and verified.")
        return 0

    if args.check:
        print(f"\n{len(missing)} file(s) missing or corrupt ({_format_size(total)}).")
        print("Run 'poetry run fetch-weights' to download them.")
        return 1

    print(f"\nFetching {len(missing)} file(s), {_format_size(total)} total.")
    failures = 0
    for entry in missing:
        try:
            download_entry(manifest, entry, dest_dir)
        except RuntimeError as exc:
            print(f"error: {exc}", file=sys.stderr)
            failures += 1

    if failures:
        print(f"\n{failures} download(s) failed. Nothing partial was kept.", file=sys.stderr)
        return 1

    print("\nDone. All weights verified.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
