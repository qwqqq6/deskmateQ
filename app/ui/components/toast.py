"""轻量提示条 (Toast): 在窗口底部短暂显示操作反馈。"""
from __future__ import annotations

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QLabel, QWidget

from app.ui.theme import COLORS, RADIUS_SM


class Toast(QLabel):
    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("Toast")
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet(
            f"background-color: {COLORS['accent']}; color: white;"
            f"border-radius: {RADIUS_SM}px; padding: 8px 14px; font-weight: 600;"
        )
        self.setWordWrap(True)
        self.hide()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)

    def show_message(self, text: str, msec: int = 1800) -> None:
        self.setText(text)
        self.adjustSize()
        self._reposition()
        self.show()
        self.raise_()
        self._timer.start(msec)

    def _reposition(self) -> None:
        p = self.parentWidget()
        if not p:
            return
        w = min(max(self.width(), 120), p.width() - 40)
        self.setFixedWidth(w)
        self.adjustSize()
        x = (p.width() - self.width()) // 2
        y = p.height() - self.height() - 24
        self.move(x, y)
