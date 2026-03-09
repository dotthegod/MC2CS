"""MCtoCS — Minecraft to CS2 Map Converter

Launch the GUI application for converting Minecraft .nbt, .schematic,
and .schem files into CS2 .vmap map files.
"""

import sys
import os
import multiprocessing

# Ensure the project root is on the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gui.app import run_app


if __name__ == "__main__":
    multiprocessing.freeze_support()
    run_app()
