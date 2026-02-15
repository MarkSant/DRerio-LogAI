"""
Session cache for wizard performance optimization.

Caches expensive operations (file scanning, design detection) to avoid
recomputation when user navigates back/forward through wizard steps.

Cache is invalidated when video selection changes (Step 2).
"""

import hashlib
from collections.abc import Callable

import structlog

log = structlog.get_logger()


class WizardCache:
    """
    In-memory cache for wizard session.

    Lifecycle: Created when wizard opens, destroyed when wizard closes.

    Cached Data:
        - scan_results: Per-video parquet info (from scan_input_paths)
        - design_detection: Detected experimental design
        - videos_hash: MD5 of sorted video paths (for invalidation)

    Invalidation:
        When video_paths change (detected via hash comparison),
        all caches are cleared.

    Usage:
        >>> cache = WizardCache()
        >>> results = cache.get_scan_results(video_paths, scan_func)
        >>> # Fast on second call (cached)
        >>> results = cache.get_scan_results(video_paths, scan_func)
    """

    def __init__(self):
        """Initialize empty cache."""
        self._scan_results: dict[str, dict] = {}
        self._design_detection: dict | None = None
        self._videos_hash: str | None = None

    def get_scan_results(
        self, video_paths: list[str], scan_func: Callable[[list[str]], dict[str, dict]]
    ) -> dict[str, dict]:
        """
        Get cached scan results or compute if cache miss/invalid.

        Args:
            video_paths: List of video file paths
            scan_func: Function to call if cache miss (signature: list[str] -> dict)

        Returns:
            dict[str, dict]: Mapping of video_path -> VideoParquetInfo

        Example:
            >>> def my_scan(paths):
            ...     return {p: scan_single_video(p) for p in paths}
            >>> results = cache.get_scan_results(video_paths, my_scan)
        """
        videos_hash = self._compute_hash(video_paths)

        if videos_hash != self._videos_hash:
            # Cache invalidated (video selection changed)
            log.info(
                "wizard.cache.invalidated",
                reason="video_selection_changed",
                old_hash=self._videos_hash,
                new_hash=videos_hash,
            )
            self._videos_hash = videos_hash
            self._scan_results = scan_func(video_paths)
            self._design_detection = None  # Also invalidate detection

        return self._scan_results

    def get_design_detection(
        self, video_paths: list[str], detect_func: Callable[[list[str]], dict | None]
    ) -> dict | None:
        """
        Get cached design detection or compute if cache miss.

        Args:
            video_paths: List of video file paths
            detect_func: Function to call if cache miss (signature: list[str] -> dict)

        Returns:
            dict | None: DetectionResult or None if no detection

        Example:
            >>> def my_detect(paths):
            ...     return detector.detect_from_folders(paths)
            >>> result = cache.get_design_detection(video_paths, my_detect)
        """
        videos_hash = self._compute_hash(video_paths)

        if videos_hash != self._videos_hash:
            # Cache invalidated - force recompute
            self._videos_hash = videos_hash
            self._design_detection = None

        if self._design_detection is None:
            # Cache miss - compute and store
            log.info("wizard.cache.miss", cache_type="design_detection")
            self._design_detection = detect_func(video_paths)
        else:
            log.info("wizard.cache.hit", cache_type="design_detection")

        return self._design_detection

    def invalidate(self):
        """
        Manually invalidate all caches.

        Use this when user manually changes data that affects cached results
        (e.g., manual design edit).
        """
        log.info("wizard.cache.invalidated", reason="manual")
        self._scan_results = {}
        self._design_detection = None
        self._videos_hash = None

    def _compute_hash(self, video_paths: list[str]) -> str:
        """
        Compute BLAKE2b hash of sorted video paths.

        Task 2.0a: Replaced MD5 with BLAKE2b for security.

        Args:
            video_paths: List of video file paths

        Returns:
            str: Hex digest of BLAKE2b hash (32 chars)
        """
        # Sort to make hash order-independent
        sorted_paths = sorted(video_paths)
        paths_str = "".join(sorted_paths)
        return hashlib.blake2b(paths_str.encode("utf-8"), digest_size=16).hexdigest()
