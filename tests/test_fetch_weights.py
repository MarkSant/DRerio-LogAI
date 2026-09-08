"""Tests for :mod:`zebtrack.fetch_weights`.

The download path is exercised against a real HTTP server bound to localhost
rather than a mocked ``urlopen``: the thing most worth proving is that a corrupt
transfer is discarded instead of being renamed into place, and a mock that
returns bytes on demand would never exercise the staging file at all.
"""

from __future__ import annotations

import hashlib
import http.server
import json
import threading
import unittest
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

from zebtrack.fetch_weights import (
    Manifest,
    WeightEntry,
    download_entry,
    file_is_valid,
    generate_manifest,
    load_manifest,
    main,
    sha256_of,
)

_PAYLOAD = b"pretend-this-is-a-yolo-checkpoint" * 64
_PAYLOAD_SHA = hashlib.sha256(_PAYLOAD).hexdigest()


def _entry(
    name: str = "best_seg_lateral.pt",
    *,
    sha256: str = _PAYLOAD_SHA,
    size_bytes: int | None = None,
    weight_type: str = "seg",
    perspective: str | None = "lateral",
    required: bool = True,
) -> WeightEntry:
    """A manifest entry describing :data:`_PAYLOAD` unless told otherwise."""
    return WeightEntry(
        name=name,
        sha256=sha256,
        size_bytes=len(_PAYLOAD) if size_bytes is None else size_bytes,
        weight_type=weight_type,
        perspective=perspective,
        required=required,
    )


def _make_handler(body: bytes | None) -> type[http.server.BaseHTTPRequestHandler]:
    """Build a handler bound to one response body.

    A fresh class per server keeps the body off shared class state, so nothing
    here depends on tests running in a particular order.
    """

    class _Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            if body is None:
                self.send_error(404, "no such asset")
                return
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):  # silence the per-request stderr noise
            return

    return _Handler


@dataclass(frozen=True)
class _LocalManifest(Manifest):
    """A real :class:`Manifest` whose asset URLs point at the local test server.

    A genuine subclass rather than a look-alike, so ``download_entry`` is called
    with the type it declares. Only ``url_for`` is overridden: the production
    implementation hardcodes github.com and is covered separately by
    :meth:`TestManifest.test_url_points_at_the_release_asset`.
    """

    base: str = ""

    def url_for(self, entry: WeightEntry) -> str:
        return f"{self.base}/{entry.name}"


class _LocalServer:
    """A localhost HTTP server usable as a context manager."""

    def __init__(self, body: bytes | None):
        self._httpd = http.server.HTTPServer(("127.0.0.1", 0), _make_handler(body))
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)

    def __enter__(self) -> _LocalServer:
        self._thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()
        self._thread.join(timeout=5)

    @property
    def manifest(self) -> _LocalManifest:
        return _LocalManifest(
            repository="local/test",
            release_tag="local-test",
            entries=(),
            base=f"http://127.0.0.1:{self._httpd.server_port}",
        )


class TestHashing(unittest.TestCase):
    def test_sha256_of_matches_hashlib(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "blob.bin"
            path.write_bytes(_PAYLOAD)
            self.assertEqual(sha256_of(path), _PAYLOAD_SHA)

    def test_file_is_valid_rejects_absent_wrong_size_and_wrong_bytes(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "best_seg_lateral.pt"
            entry = _entry()

            self.assertFalse(file_is_valid(path, entry), "absent file must not validate")

            path.write_bytes(_PAYLOAD[:-1])
            self.assertFalse(file_is_valid(path, entry), "short file must not validate")

            path.write_bytes(b"x" * len(_PAYLOAD))
            self.assertFalse(file_is_valid(path, entry), "right size, wrong bytes")

            path.write_bytes(_PAYLOAD)
            self.assertTrue(file_is_valid(path, entry))


class TestManifest(unittest.TestCase):
    def _write(self, tmp: str, payload) -> Path:
        path = Path(tmp) / "weights_manifest.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_missing_manifest_raises_filenotfound(self):
        with TemporaryDirectory() as tmp:
            with self.assertRaises(FileNotFoundError):
                load_manifest(Path(tmp) / "nope.json")

    def test_unknown_version_is_refused(self):
        with TemporaryDirectory() as tmp:
            path = self._write(tmp, {"manifest_version": 99, "files": []})
            with self.assertRaises(ValueError) as ctx:
                load_manifest(path)
            self.assertIn("manifest_version", str(ctx.exception))

    def test_empty_file_list_is_refused(self):
        with TemporaryDirectory() as tmp:
            path = self._write(
                tmp,
                {"manifest_version": 1, "repository": "a/b", "release_tag": "t", "files": []},
            )
            with self.assertRaises(ValueError):
                load_manifest(path)

    def test_malformed_entry_is_refused(self):
        with TemporaryDirectory() as tmp:
            path = self._write(
                tmp,
                {
                    "manifest_version": 1,
                    "repository": "a/b",
                    "release_tag": "t",
                    "files": [{"name": "x.pt"}],  # no sha256, no bytes
                },
            )
            with self.assertRaises(ValueError):
                load_manifest(path)

    def test_url_points_at_the_release_asset(self):
        manifest = Manifest(repository="MarkSant/DRerio-LogAI", release_tag="w1", entries=())
        url = manifest.url_for(_entry("best_det_topdown.pt"))
        self.assertEqual(
            url,
            "https://github.com/MarkSant/DRerio-LogAI/releases/download/w1/best_det_topdown.pt",
        )


class TestGenerateManifest(unittest.TestCase):
    def test_round_trip_classifies_and_reloads(self):
        with TemporaryDirectory() as tmp:
            source = Path(tmp) / "weights"
            source.mkdir()
            (source / "best_seg_lateral.pt").write_bytes(_PAYLOAD)
            (source / "best_det_topdown.pt").write_bytes(_PAYLOAD)
            (source / "best_seg.pt").write_bytes(_PAYLOAD)  # legacy, no perspective
            dest = Path(tmp) / "weights_manifest.json"

            code = generate_manifest(source, dest, repository="a/b", release_tag="w1")
            self.assertEqual(code, 0)

            manifest = load_manifest(dest)
            by_name = {e.name: e for e in manifest.entries}

            self.assertEqual(by_name["best_seg_lateral.pt"].perspective, "lateral")
            self.assertEqual(by_name["best_seg_lateral.pt"].weight_type, "seg")
            self.assertEqual(by_name["best_det_topdown.pt"].perspective, "top_down")
            self.assertEqual(by_name["best_det_topdown.pt"].weight_type, "det")

            # Every model in the manifest is fetched by default. The flat-named
            # generalists used to be marked optional because WeightManager could
            # not discover them; it can now, so a standard install carries all
            # six rather than four.
            self.assertTrue(by_name["best_seg_lateral.pt"].required)
            self.assertTrue(by_name["best_seg.pt"].required)
            self.assertIsNone(by_name["best_seg.pt"].perspective)

            self.assertEqual(by_name["best_seg_lateral.pt"].sha256, _PAYLOAD_SHA)

    def test_empty_source_directory_reports_failure(self):
        with TemporaryDirectory() as tmp:
            source = Path(tmp) / "weights"
            source.mkdir()
            code = generate_manifest(
                source, Path(tmp) / "m.json", repository="a/b", release_tag="w1"
            )
            self.assertEqual(code, 1)


class TestDownload(unittest.TestCase):
    def test_good_download_lands_under_its_final_name(self):
        with TemporaryDirectory() as tmp, _LocalServer(_PAYLOAD) as server:
            dest = Path(tmp)
            entry = _entry()

            download_entry(server.manifest, entry, dest)

            final = dest / entry.name
            self.assertTrue(final.is_file())
            self.assertEqual(final.read_bytes(), _PAYLOAD)
            self.assertFalse((dest / f"{entry.name}.part").exists(), "staging file left behind")

    def test_checksum_mismatch_is_discarded_not_renamed(self):
        """A corrupt transfer must never masquerade as a usable weight.

        Renaming it anyway would surface much later as silently bad detections
        rather than as an error.
        """
        with TemporaryDirectory() as tmp, _LocalServer(b"corrupted-bytes") as server:
            dest = Path(tmp)
            entry = _entry()

            with self.assertRaises(RuntimeError) as ctx:
                download_entry(server.manifest, entry, dest)

            self.assertIn("Checksum mismatch", str(ctx.exception))
            self.assertFalse((dest / entry.name).exists(), "corrupt file was kept")
            self.assertFalse((dest / f"{entry.name}.part").exists(), "staging file left behind")

    def test_http_error_names_the_release(self):
        with TemporaryDirectory() as tmp, _LocalServer(None) as server:
            dest = Path(tmp)
            entry = _entry()

            with self.assertRaises(RuntimeError) as ctx:
                download_entry(server.manifest, entry, dest)

            message = str(ctx.exception)
            self.assertIn("404", message)
            self.assertFalse((dest / f"{entry.name}.part").exists())


class TestCheckMode(unittest.TestCase):
    def _manifest_file(self, tmp: Path) -> Path:
        payload = {
            "manifest_version": 1,
            "repository": "a/b",
            "release_tag": "w1",
            "files": [
                {
                    "name": "best_seg_lateral.pt",
                    "sha256": _PAYLOAD_SHA,
                    "bytes": len(_PAYLOAD),
                    "type": "seg",
                    "perspective": "lateral",
                    "required": True,
                },
                {
                    "name": "best_seg.pt",
                    "sha256": _PAYLOAD_SHA,
                    "bytes": len(_PAYLOAD),
                    "type": "seg",
                    "perspective": None,
                    "required": False,
                },
            ],
        }
        path = tmp / "weights_manifest.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_check_fails_when_required_weight_is_absent(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = self._manifest_file(root)
            dest = root / "weights"

            code = main(["--check", "--manifest", str(manifest), "--dest", str(dest)])

            self.assertEqual(code, 1)

    def test_check_passes_once_required_weights_are_present(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = self._manifest_file(root)
            dest = root / "weights"
            dest.mkdir()
            (dest / "best_seg_lateral.pt").write_bytes(_PAYLOAD)

            code = main(["--check", "--manifest", str(manifest), "--dest", str(dest)])

            self.assertEqual(code, 0, "the optional legacy weight must not be required")

    def test_check_with_all_also_demands_the_optional_weights(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = self._manifest_file(root)
            dest = root / "weights"
            dest.mkdir()
            (dest / "best_seg_lateral.pt").write_bytes(_PAYLOAD)

            code = main(["--check", "--all", "--manifest", str(manifest), "--dest", str(dest)])

            self.assertEqual(code, 1)

    def test_missing_manifest_reports_an_error_code(self):
        with TemporaryDirectory() as tmp:
            code = main(["--check", "--manifest", str(Path(tmp) / "absent.json")])
            self.assertEqual(code, 1)


class TestShippedManifest(unittest.TestCase):
    """The manifest committed to the repository must stay loadable and coherent."""

    def test_repository_manifest_requires_every_published_model(self):
        manifest = load_manifest()

        self.assertEqual(manifest.repository, "MarkSant/DRerio-LogAI")

        required = {e.name for e in manifest.entries if e.required}
        self.assertEqual(
            required,
            {
                "best_seg_lateral.pt",
                "best_det_lateral.pt",
                "best_seg_topdown.pt",
                "best_det_topdown.pt",
                "best_oi.pt",
                "best_seg.pt",
            },
            "both perspectives need a seg and a det weight -- a lateral model on "
            "a top-down scene returns zero polygons -- and the two generalists "
            "ship with them so the model configuration panel has something to "
            "offer beyond the four specialists",
        )

    def test_every_entry_has_a_plausible_digest_and_size(self):
        for entry in load_manifest().entries:
            with self.subTest(entry.name):
                self.assertEqual(len(entry.sha256), 64, "not a SHA-256 digest")
                self.assertRegex(entry.sha256, r"^[0-9a-f]{64}$")
                self.assertGreater(entry.size_bytes, 1_000_000, "a YOLO checkpoint is megabytes")

    def test_required_names_match_the_discovery_glob(self):
        """WeightManager.discover_weights() globs ``best_*.pt``.

        A required entry whose name misses that glob would download fine and
        then be ignored by the catalogue, which is indistinguishable from not
        having downloaded it at all. That is exactly what happened to
        ``best_oi.pt`` and ``best_seg.pt`` while discovery matched only the
        perspective suffixes.
        """
        for entry in load_manifest().entries:
            if not entry.required:
                continue
            with self.subTest(entry.name):
                self.assertTrue(
                    entry.name.startswith("best_") and entry.name.endswith(".pt"),
                    f"{entry.name} would never be auto-discovered",
                )


class TestUrlSchemeGuard(unittest.TestCase):
    """Only http/https may reach urlopen.

    ``urlopen`` honours ``file:`` and any scheme with a registered handler, so a
    manifest naming ``file:///etc/passwd`` would have it copied into ``weights/``
    under a ``.pt`` name. The manifest is tracked and therefore trusted today --
    but that assumption stops holding the day a manifest arrives from elsewhere,
    and the checksum would not save us: an attacker writing the manifest writes
    the hash too.
    """

    def test_file_scheme_is_refused(self):
        with TemporaryDirectory() as tmp:
            dest = Path(tmp)
            source = dest / "planted.pt"
            source.write_bytes(_PAYLOAD)

            manifest = _LocalManifest(
                repository="local/test",
                release_tag="t",
                entries=(),
                base=source.parent.as_uri(),
            )
            entry = _entry("planted.pt")

            with self.assertRaises(RuntimeError) as ctx:
                download_entry(manifest, entry, dest / "out")

            self.assertIn("scheme", str(ctx.exception).lower())

    def test_refusal_happens_before_any_file_is_created(self):
        with TemporaryDirectory() as tmp:
            dest = Path(tmp) / "weights"
            dest.mkdir()
            manifest = _LocalManifest(
                repository="local/test", release_tag="t", entries=(), base="ftp://example.invalid"
            )

            with self.assertRaises(RuntimeError):
                download_entry(manifest, _entry(), dest)

            self.assertEqual(list(dest.iterdir()), [], "nothing may be written before the check")

    def test_http_and_https_are_allowed(self):
        from zebtrack.fetch_weights import _reject_unsupported_scheme

        # Must not raise.
        _reject_unsupported_scheme("http://127.0.0.1:8000/best_seg_lateral.pt")
        _reject_unsupported_scheme("https://github.com/o/r/releases/download/t/best.pt")

    def test_scheme_check_is_case_insensitive(self):
        from zebtrack.fetch_weights import _reject_unsupported_scheme

        _reject_unsupported_scheme("HTTPS://github.com/o/r/releases/download/t/best.pt")

    def test_a_bare_path_without_scheme_is_refused(self):
        from zebtrack.fetch_weights import _reject_unsupported_scheme

        with self.assertRaises(RuntimeError):
            _reject_unsupported_scheme("/etc/passwd")
