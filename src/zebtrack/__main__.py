import logging
import tkinter as tk

from zebtrack.core.controller import AppController
from zebtrack.settings import settings
from zebtrack.utils import set_seed


def main():
    """
    Initializes and runs the application.
    """
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(threadName)s - %(name)s - %(levelname)s - %(message)s",
        filename="analysis.log",
        filemode="w",  # Overwrite log file on each run
    )

    # Set seed for reproducibility before anything else
    if settings and settings.reproducibility:
        set_seed(settings.reproducibility.seed)

    logging.info("Application starting.")

    try:
        root = tk.Tk()
        controller = AppController(root)
        controller.run()
    except Exception as e:
        logging.critical("An unhandled exception occurred.", exc_info=True)
        # Optionally, show a message to the user
        # messagebox.showerror("Fatal Error", f"A fatal error occurred: {e}\nSee analysis.log for details.")
    finally:
        logging.info("Application finished.")


if __name__ == "__main__":
    main()
