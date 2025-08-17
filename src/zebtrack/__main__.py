import logging
import tkinter as tk

import structlog

from zebtrack.core.controller import AppController
from zebtrack.settings import settings
from zebtrack.utils import set_seed


def main():
    """
    Initializes and runs the application.
    """
    # Configure logging with structlog
    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer()
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Route standard library logs to structlog
    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
        handlers=[logging.FileHandler("analysis.log", mode="w")],
    )

    log = structlog.get_logger()

    # Set seed for reproducibility before anything else
    if settings and settings.reproducibility and settings.reproducibility.seed:
        set_seed(settings.reproducibility.seed)
        log.info("reproducibility.seed.set", seed=settings.reproducibility.seed)

    log.info("application.starting", component="main")

    try:
        root = tk.Tk()
        controller = AppController(root)
        controller.run()
    except Exception:
        log.critical("unhandled.exception", exc_info=True)
        # Optionally, show a message to the user
        # import tkinter.messagebox as messagebox
        # messagebox.showerror(
        #     "Fatal Error",
        #     "A fatal error occurred. See analysis.log for details."
        # )
    finally:
        log.info("application.finished", component="main")


if __name__ == "__main__":
    main()
