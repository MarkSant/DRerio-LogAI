"""ZebTrack-AI application entrypoint."""

import tkinter as tk
from tkinter import messagebox

from zebtrack.core.app_runner import run_app
from zebtrack.logging_config import configure_logging


def main() -> None:
    run_app(
        tk_module=tk,
        messagebox_module=messagebox,
        configure_logging_fn=configure_logging,
    )


if __name__ == "__main__":
    main()
