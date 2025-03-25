import os
import importlib
import inspect

from .core import Strategy  # Explicitly import Strategy

# Get all Python files in this directory (excluding __init__.py and core.py)
module_dir = os.path.dirname(__file__)
modules = [
    f[:-3] for f in os.listdir(module_dir)
    if f.endswith(".py") and f not in ["__init__.py", "core.py"]
]

# Dictionary to store dynamically imported subclasses of Strategy
_imported_subclasses = {}

# Import all modules and extract subclasses of Strategy
for module in modules:
    mod = importlib.import_module(f".{module}", package=__name__)

    # Extract all subclasses of Strategy
    for name, obj in inspect.getmembers(mod, inspect.isclass):
        # Ensure the class is a direct subclass of Strategy and is defined in this module
        if issubclass(obj, Strategy) and obj is not Strategy and obj.__module__ == mod.__name__:
            _imported_subclasses[name] = obj

# Update globals() so subclasses can be accessed directly from the package
globals().update(_imported_subclasses)

# Define __all__ to explicitly include Strategy + dynamically imported subclasses
__all__ = ["Strategy"] + list(_imported_subclasses.keys())
