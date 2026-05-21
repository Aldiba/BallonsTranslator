# -*- coding: utf-8 -*-
"""Pure Python localization engine. Replaces .ts/.qm file loading.

Usage in launch.py:
    from utils.i18n import DictTranslator, set_language
    set_language("zh_CN")
    app.installTranslator(DictTranslator())

The DictTranslator works as a drop-in replacement for QTranslator.
All existing self.tr() calls in the codebase work without modification.
"""

from typing import Optional, Dict
from qtpy.QtCore import QTranslator, QCoreApplication

# Translation data: LANG_DATA[lang_code][context][source] = translation
LANG_DATA: Dict[str, Dict[str, Dict[str, str]]] = {}

# Currently active language code
_current_lang: str = "en_US"


class DictTranslator(QTranslator):
    """A QTranslator subclass that resolves translations from Python dicts."""

    def translate(self,
                  context: str,
                  sourceText: str,
                  disambiguation: Optional[str] = None,
                  n: int = -1) -> Optional[str]:
        """Override QTranslator.translate to look up in LANG_DATA."""
        global _current_lang

        # English: return None so Qt uses source text as-is
        if _current_lang in ("en_US", "English"):
            return None

        lang_dict = LANG_DATA.get(_current_lang, {})
        context_dict = lang_dict.get(context, {})

        if sourceText in context_dict:
            translation = context_dict[sourceText]
            if translation:
                return translation
            # Empty string means no translation available, fall through to source

        return None


def set_language(lang_code: str) -> None:
    """Set the active language code (e.g. 'zh_CN', 'en_US')."""
    global _current_lang
    _current_lang = lang_code


def get_language() -> str:
    """Return the currently active language code."""
    return _current_lang


def load_translations() -> None:
    """Load all translation data from translate/i18n/ package."""
    from translate.i18n import load_all as _load
    _load()
    global LANG_DATA
    from translate.i18n import LANG_DATA as _data
    LANG_DATA.clear()
    LANG_DATA.update(_data)


def get_available_languages() -> Dict[str, str]:
    """Return {display_name: lang_code} for all available languages."""
    result = {}
    for code in LANG_DATA:
        if code == "en_US":
            result["English"] = code
    return result


def switch_language(lang_code: str) -> None:
    """Switch UI language at runtime by updating translator state."""
    set_language(lang_code)
    # Send LanguageChange event to top-level widgets so they re-evaluate tr()
    app = QCoreApplication.instance()
    if app is not None:
        event_type = type('EventType', (), {'LanguageChange': 89})()
        # QEvent.Type.LanguageChange = 89 - use raw value for compatibility
        from qtpy.QtCore import QEvent
        for widget in app.topLevelWidgets():
            QCoreApplication.sendEvent(widget, QEvent(QEvent.Type.LanguageChange))


# Display name mappings for the language menu
DISPLAY_NAMES = {
    "zh_CN": "简体中文",
    "ru_RU": "Русский",
    "pt_BR": "Português (Brasil)",
    "ko_KR": "한국어",
    "es_MX": "Español",
    "hu_HU": "Hungarian",
    "fr_FR": "Français",
}
