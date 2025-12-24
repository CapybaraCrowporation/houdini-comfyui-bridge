"""Top-level package for houconnect."""

__all__ = [
    "NODE_CLASS_MAPPINGS",
    "NODE_DISPLAY_NAME_MAPPINGS",
    "WEB_DIRECTORY",
]

__author__ = """houconnect"""
__email__ = "xxx@xxx.xxx"
__version__ = "0.1.0"

from .src.houconnect.nodes import NODE_CLASS_MAPPINGS
from .src.houconnect.nodes import NODE_DISPLAY_NAME_MAPPINGS

WEB_DIRECTORY = "./web"
