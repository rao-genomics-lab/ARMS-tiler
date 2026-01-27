"""
ARMS Tiling Application

An interactive napari-based desktop application for preprocessing tissue
annotations for laser capture microdissection (LCM).
"""

__version__ = "1.0.0"
__author__ = "Srinivasa Rao"

from .app import main

__all__ = ["main", "__version__"]
