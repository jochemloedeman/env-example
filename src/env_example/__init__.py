from importlib.metadata import version

from env_example.main import main

__version__ = version("env-example")
__all__ = ["main"]
