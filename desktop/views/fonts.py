from __future__ import annotations

from PySide6.QtGui import QFont, QFontDatabase


PREFERRED_UI_FONTS = [
    "Microsoft YaHei UI",
    "Microsoft YaHei",
    "SimHei",
    "SimSun",
    "Noto Sans CJK SC",
    "Source Han Sans SC",
    "Segoe UI",
]


def choose_ui_font() -> QFont:
    families = set(QFontDatabase.families())
    for family in PREFERRED_UI_FONTS:
        if family in families:
            return QFont(family, 10)
    return QFont("Segoe UI", 10)
