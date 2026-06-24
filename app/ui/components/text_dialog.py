"""可复用的文本编辑对话框。

替代 QInputDialog: 它能继承应用样式表, 并带 WindowStaysOnTopHint,
这样在置顶的无边框主窗口之上也能正常显示, 不会被压在窗口后面。
显示时强制居中到父窗口并抢占焦点, 避免出现在屏幕角落或父窗背后。
支持单行与多行两种模式。
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QPushButton,
    QVBoxLayout, QWidget,
)


class TextEditDialog(QDialog):
    """编辑一段文本 (单行或多行)。点击保存返回 accepted。"""

    def __init__(self, title: str, label: str, text: str = "",
                 multiline: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(380)
        self.setModal(True)
        # 显式声明为对话框且置顶, 避免被置顶的无边框主窗口遮挡
        self.setWindowFlags(Qt.Dialog | Qt.WindowStaysOnTopHint)
        if parent is not None:
            self.setStyleSheet(parent.styleSheet())

        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 16, 18, 16)
        lay.setSpacing(10)

        lbl = QLabel(label)
        lbl.setObjectName("Dim")
        lay.addWidget(lbl)

        self._multiline = multiline
        if multiline:
            self._edit: QLineEdit | QPlainTextEdit = QPlainTextEdit(text)
            self._edit.setMinimumHeight(120)
        else:
            self._edit = QLineEdit(text)
        lay.addWidget(self._edit)

        btns = QHBoxLayout()
        btns.addStretch(1)
        cancel = QPushButton("取消")
        cancel.setCursor(Qt.PointingHandCursor)
        cancel.clicked.connect(self.reject)
        btns.addWidget(cancel)
        save = QPushButton("保存")
        save.setObjectName("Primary")
        save.setCursor(Qt.PointingHandCursor)
        save.setDefault(True)
        save.clicked.connect(self.accept)
        btns.addWidget(save)
        lay.addLayout(btns)

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        # 居中到父窗口 (无父则居中到屏幕), 并强制前置 + 抢焦点
        parent = self.parentWidget()
        if parent is not None:
            geo = parent.frameGeometry()
            self.move(geo.center() - self.rect().center())
        self.raise_()
        self.activateWindow()
        self._edit.setFocus()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        # 单行: 回车保存; 多行: Ctrl+Enter 保存 (普通回车换行)
        is_enter = event.key() in (Qt.Key_Return, Qt.Key_Enter)
        if is_enter:
            if not self._multiline or (event.modifiers() & Qt.ControlModifier):
                self.accept()
                return
        super().keyPressEvent(event)

    def value(self) -> str:
        if self._multiline:
            return self._edit.toPlainText().strip()
        return self._edit.text().strip()

    @staticmethod
    def get_text(parent: QWidget | None, title: str, label: str,
                 text: str = "", multiline: bool = False) -> tuple[str, bool]:
        """便捷调用: 返回 (文本, 是否确认)。"""
        dlg = TextEditDialog(title, label, text, multiline, parent)
        ok = dlg.exec() == QDialog.Accepted
        return dlg.value(), ok

