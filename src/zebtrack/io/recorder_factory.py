"""Factory for lazy-loading Recorder with heavy dependencies."""

import structlog

log = structlog.get_logger()


class RecorderFactory:
    """Factory that delays Recorder instantiation until first use.

    This avoids importing heavy dependencies (pandas, pyarrow) during startup.
    The Recorder is created on first access, typically when user starts analysis.
    """

    def __init__(self, settings_obj):
        """Initialize factory with settings.

        Args:
            settings_obj: Settings instance to pass to Recorder
        """
        self._settings_obj = settings_obj
        self._recorder = None
        self._initialized = False
        log.info("recorder_factory.created", lazy_load=True)

    def get_recorder(self):
        """Get Recorder instance, creating it lazily on first access.

        Returns:
            Recorder instance
        """
        if not self._initialized:
            log.info("recorder_factory.initializing", first_access=True)
            import time

            _t0 = time.perf_counter()

            # Import only when needed (heavy: pandas + pyarrow)
            from zebtrack.io.recorder import Recorder

            self._recorder = Recorder(settings_obj=self._settings_obj)
            elapsed_ms = int((time.perf_counter() - _t0) * 1000)

            self._initialized = True
            log.info("recorder_factory.initialized", elapsed_ms=elapsed_ms)

        return self._recorder

    @property
    def recorder(self):
        """Property access to recorder (lazy-loads on first access)."""
        return self.get_recorder()

    def __getattr__(self, name):
        """Delegate all other attributes to the underlying recorder.

        This makes RecorderFactory transparent - callers can use it
        as if it were a Recorder directly.
        """
        return getattr(self.get_recorder(), name)

    def __enter__(self):
        """Support context manager protocol by delegating to Recorder."""
        return self.get_recorder().__enter__()

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Support context manager protocol by delegating to Recorder."""
        return self.get_recorder().__exit__(exc_type, exc_val, exc_tb)
