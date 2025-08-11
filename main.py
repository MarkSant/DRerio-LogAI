import tkinter as tk
from gui import ApplicationGUI

def main():
    """
    Initializes and runs the application.
    """
    root = tk.Tk()
    app = ApplicationGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()
