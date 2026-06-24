"""可复用的文件拖放区组件。

显示一块虚线框提示区, 接受从资源管理器拖入的文件, 通过 files_dropped
信号把本地文件路径列表抛给上层。拖拽悬停时高亮边框以给出明确反馈。
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel


class DropZone(QFrame):
    """接受文件拖入的区域。"""

    files_dropped = Signal(list)  # list[str] 本地文件路径
    clicked = Signal()

    def __init__(self, text: str = "拖入文件 / 截图到此处",
                 hint: str = "或点击选择") -> None:
        super().__init__()
        self.setObjectName("DropZone")
        self.setAcceptDrops(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(64)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(8)
        self._label = QLabel(f"⬇  {text}")
        self._label.setObjectName("Dim")
        self._label.setAlignment(Qt.AlignCenter)
        lay.addWidget(self._label, 1)

        self._default_text = f"⬇  {text}"
        self._hint = hint

    # --- 拖放事件 ----------------------------------------------------
    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self._set_active(True)
        else:
            event.ignore()

    def dragLeaveEvent(self, event) -> None:  # noqa: N802
        self._set_active(False)

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        self._set_active(False)
        paths: list[str] = []
        for url in event.mimeData().urls():
            if url.isLocalFile():
                paths.append(url.toLocalFile())
        if paths:
            self.files_dropped.emit(paths)
            event.acceptProposedAction()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
            event.accept()

    def _set_active(self, active: bool) -> None:
        self.setObjectName("DropZoneActive" if active else "DropZone")
        self._label.setText(
            "松开以添加文件" if active else self._default_text
        )
        # 重新应用样式表使 objectName 生效
        self.style().unpolish(self)
        self.style().polish(self)
