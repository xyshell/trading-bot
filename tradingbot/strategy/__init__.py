import os
import importlib
import inspect

from .core import Strategy


# store dynamically imported subclasses of Strategy
_imported_subclasses = {}

# load subclasses of Strategy in the current module
modules = [
    f[:-3] for f in os.listdir(os.path.dirname(__file__))
    if f.endswith(".py") and f not in ["__init__.py", "core.py"] and not f.startswith("_")
]
for module in modules:
    mod = importlib.import_module(f".{module}", package=__name__)

    # Extract all subclasses of Strategy
    for name, obj in inspect.getmembers(mod, inspect.isclass):
        # Ensure the class is a direct subclass of Strategy and is defined in this module
        if issubclass(obj, Strategy) and obj is not Strategy and obj.__module__ == mod.__name__:
            _imported_subclasses[name] = obj

# update globals() so subclasses can be accessed directly from the package
globals().update(_imported_subclasses)

# define __all__ to explicitly include Strategy + dynamically imported subclasses
__all__ = ["Strategy"] + list(_imported_subclasses.keys())
