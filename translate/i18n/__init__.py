# -*- coding: utf-8 -*-
"""Translation data package. Auto-generated. Do not edit manually."""
import os
import importlib

LANG_DATA = {}

def load_all():
    """Dynamically import all translation modules in this package."""
    package_dir = os.path.dirname(__file__)
    LANG_DATA.clear()
    for fname in sorted(os.listdir(package_dir)):
        if fname.endswith(".py") and fname != "__init__.py":
            lang_code = fname[:-3]
            mod = importlib.import_module(f".{lang_code}", __package__)
            LANG_DATA[lang_code] = getattr(mod, 'TRANSLATIONS', {})

def get_available_codes():
    """Return list of available language codes."""
    return sorted(LANG_DATA.keys())
