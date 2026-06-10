from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import QWidget


class Background(QWidget):
    def __init__(self, image_path: Path):
        super().__init__()
        self.pixmap = QPixmap(str(image_path)) if image_path.exists() else QPixmap()
        self.theme = "light"

    def set_theme(self, theme: str) -> None:
        self.theme = theme
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        rect = self.rect()
        if not self.pixmap.isNull():
            scaled = self.pixmap.scaled(rect.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            painter.drawPixmap((rect.width() - scaled.width()) // 2, (rect.height() - scaled.height()) // 2, scaled)
            overlay = QColor(247, 251, 255, 58) if self.theme == "light" else QColor(5, 12, 22, 112)
            painter.fillRect(rect, overlay)
        else:
            painter.fillRect(rect, QColor("#eef6fb" if self.theme == "light" else "#091522"))
        super().paintEvent(event)
