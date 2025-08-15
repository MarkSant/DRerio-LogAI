import logging
import tkinter as tk

from zebtrack.ui.gui import ApplicationGUI


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
    logging.info("Application starting.")

    root = tk.Tk()
    ApplicationGUI(root)
    root.mainloop()

    logging.info("Application finished.")


if __name__ == "__main__":
    main()
