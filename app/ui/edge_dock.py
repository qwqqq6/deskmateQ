"""屏幕贴边自动隐藏控制器 (类似 QQ 的吸边)。

当窗口拖动到屏幕上/左/右边缘并松手时, 自动吸附到该边并"收起":
只在屏幕边缘留出一条很窄的触发条。鼠标移到那条触发条 (或窗口区域)
时自动滑出完整窗口; 鼠标离开窗口一段时间后自动收回。

实现要点:
- 只在窗口非置顶交互时生效, 不依赖额外线程, 用 QTimer 轮询鼠标全局
  位置判断进出 (跨平台、简单可靠)。
- 收起时窗口并不隐藏, 而是移动到屏幕外只留 EDGE_PEEK 像素, 这样鼠标
  仍能"碰"到它触发滑出。
- 暂停: 当用户正在拖动窗口或窗口处于激活编辑状态时, 不自动收起。
"""
from __future__ import annotations

from enum import Enum

from PySide6.QtCore import QObject, QPoint, QTimer, QRect, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QCursor, QGuiApplication
from PySide6.QtWidgets import QWidget


class Edge(Enum):
    NONE = 0
    TOP = 1
    LEFT = 2
    RIGHT = 3


class EdgeDock(QObject):
    """管理窗口的贴边吸附与自动收起/弹出。"""

    EDGE_SNAP = 60          # 窗口边/鼠标距屏幕边缘多少像素内触发吸附
    EDGE_PEEK = 6           # 收起时露在屏幕内的像素 (触发条宽度)
    POLL_MS = 100           # 鼠标位置轮询间隔
    HIDE_DELAY_MS = 600     # 鼠标离开后多久收起
    ANIM_MS = 180           # 滑入/滑出动画时长

    def __init__(self, window: QWidget) -> None:
        super().__init__(window)
        self._win = window
        self._enabled = False
        self._auto_hide = True   # 贴边后是否自动隐藏 (收起)
        self._edge = Edge.NONE
        self._collapsed = False
        self._suspend = False  # 拖动中等情形暂停自动收起
        self._screen_rect: QRect | None = None  # 吸附时锁定的屏幕工作区

        self._timer = QTimer(self)
        self._timer.setInterval(self.POLL_MS)
        self._timer.timeout.connect(self._tick)

        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.setInterval(self.HIDE_DELAY_MS)
        self._hide_timer.timeout.connect(self._collapse)

        # 滑入/滑出位置动画 (作用于窗口 pos 属性)
        self._anim = QPropertyAnimation(window, b"pos", self)
        self._anim.setDuration(self.ANIM_MS)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)

    # --- 开关 --------------------------------------------------------
    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled
        if enabled:
            self._timer.start()
            # 开启时, 若当前窗口已有部分在屏幕外则立即吸附
            self._snap_if_offscreen()
        else:
            self._timer.stop()
            self._hide_timer.stop()
            if self._collapsed:
                self._expand()
            self._edge = Edge.NONE
            self._collapsed = False
            self._screen_rect = None

    @property
    def enabled(self) -> bool:
        return self._enabled

    def set_auto_hide(self, on: bool) -> None:
        """贴边后是否自动隐藏。关闭时, 若已收起则展开并保持常驻。"""
        self._auto_hide = on
        if not on:
            self._hide_timer.stop()
            if self._collapsed:
                self._expand()
        elif self._enabled and self._edge != Edge.NONE:
            # 重新开启自动隐藏: 安排一次收起
            self._schedule_hide()

    @property
    def auto_hide(self) -> bool:
        return self._auto_hide

    def suspend(self, on: bool) -> None:
        """拖动窗口期间暂停自动收起。"""
        self._suspend = on
        if on:
            self._hide_timer.stop()

    # --- 拖动结束后调用: 判断是否吸边 --------------------------------
    def on_drag_finished(self) -> None:
        if not self._enabled:
            return
        self._snap_if_offscreen()

    def _screen_geo(self) -> QRect:
        """吸附期间锁定的屏幕工作区。

        收起态窗口在屏幕外, 用 center() 反查屏幕会落到别的显示器 (甚至主屏),
        导致弹出时跑到错误的屏幕。因此吸附时锁定屏幕, 后续收/放都用它。
        """
        if self._screen_rect is not None:
            return self._screen_rect
        return self._current_screen_geo()

    def _current_screen_geo(self) -> QRect:
        """根据窗口当前真实位置查所在屏幕的工作区。"""
        screen = QGuiApplication.screenAt(self._win.frameGeometry().center())
        if screen is None:
            # center 不在任何屏幕 (例如已移出), 退回左上角所在屏
            screen = QGuiApplication.screenAt(self._win.frameGeometry().topLeft())
        if screen is None:
            screen = QGuiApplication.primaryScreen()
        return screen.availableGeometry()

    def _snap_if_offscreen(self) -> None:
        """仅当窗口有一部分越出所在屏幕边界时, 吸附到越出最多的那条边。"""
        scr = self._current_screen_geo()
        geo = self._win.frameGeometry()
        # 各边越出屏幕的量 ( >0 表示该方向有部分在屏幕外)
        over = {
            Edge.TOP: scr.top() - geo.top(),
            Edge.LEFT: scr.left() - geo.left(),
            Edge.RIGHT: geo.right() - scr.right(),
        }
        worst = max(over, key=over.get)
        if over[worst] <= 0:
            # 完全在屏幕内, 不吸附 (取消之前的吸附状态)
            if not self._collapsed:
                self._edge = Edge.NONE
                self._screen_rect = None
            return
        self._edge = worst
        # 锁定吸附屏幕, 后续收/放都基于它 (避免收起到屏幕外后查错屏幕)
        self._screen_rect = scr
        # 先贴齐边缘 (完全可见), 再按需收起
        self._move_expanded()
        self._collapsed = False
        self._schedule_hide()

    # --- 展开 / 收起位置计算 -----------------------------------------
    def _expanded_pos(self) -> QPoint:
        """完全展开 (贴齐边缘) 时窗口左上角坐标。"""
        geo = self._win.frameGeometry()
        scr = self._screen_geo()
        x, y = geo.x(), geo.y()
        if self._edge == Edge.TOP:
            y = scr.top()
            x = min(max(x, scr.left()), scr.right() - geo.width())
        elif self._edge == Edge.LEFT:
            x = scr.left()
            y = min(max(y, scr.top()), scr.bottom() - geo.height())
        elif self._edge == Edge.RIGHT:
            x = scr.right() - geo.width() + 1
            y = min(max(y, scr.top()), scr.bottom() - geo.height())
        return QPoint(x, y)

    def _collapsed_pos(self) -> QPoint:
        """收起 (移出屏幕只留触发条) 时窗口左上角坐标。"""
        geo = self._win.frameGeometry()
        scr = self._screen_geo()
        peek = self.EDGE_PEEK
        if self._edge == Edge.TOP:
            return QPoint(geo.x(), scr.top() - geo.height() + peek)
        if self._edge == Edge.LEFT:
            return QPoint(scr.left() - geo.width() + peek, geo.y())
        if self._edge == Edge.RIGHT:
            return QPoint(scr.right() - peek, geo.y())
        return geo.topLeft()

    def _animate_to(self, target: QPoint, animated: bool = True) -> None:
        self._anim.stop()
        if not animated or self.ANIM_MS <= 0:
            self._win.move(target)
            return
        self._anim.setStartValue(self._win.pos())
        self._anim.setEndValue(target)
        self._anim.start()

    def _move_expanded(self, animated: bool = False) -> None:
        self._animate_to(self._expanded_pos(), animated)

    def _expand(self) -> None:
        if self._edge == Edge.NONE:
            return
        self._animate_to(self._expanded_pos(), animated=True)
        self._collapsed = False

    def _collapse(self) -> None:
        if (self._edge == Edge.NONE or self._suspend
                or not self._enabled or not self._auto_hide):
            return
        # 不在自身窗口内才收起
        if self._cursor_in_window():
            self._schedule_hide()
            return
        self._animate_to(self._collapsed_pos(), animated=True)
        self._collapsed = True

    def _schedule_hide(self) -> None:
        # 仅在开启自动隐藏时才安排收起
        if self._auto_hide and self._edge != Edge.NONE and not self._suspend:
            self._hide_timer.start()

    # --- 轮询: 判断鼠标进出 ------------------------------------------
    def _tick(self) -> None:
        if self._edge == Edge.NONE or self._suspend:
            return
        pos = QCursor.pos()
        if self._collapsed:
            # 鼠标贴到触发边 -> 弹出
            if self._cursor_on_trigger(pos):
                self._expand()
                self._hide_timer.stop()
        else:
            # 已展开: 鼠标离开窗口 -> 安排收起 (避免每个 tick 都重启计时器)
            if not self._cursor_in_window(pos):
                if not self._hide_timer.isActive():
                    self._hide_timer.start()
            else:
                self._hide_timer.stop()

    def _cursor_in_window(self, pos: QPoint | None = None) -> bool:
        pos = pos or QCursor.pos()
        return self._win.frameGeometry().contains(pos)

    def _cursor_on_trigger(self, pos: QPoint) -> bool:
        """鼠标是否触碰到屏幕边缘的触发条。"""
        geo = self._win.frameGeometry()
        scr = self._screen_geo()
        t = self.EDGE_PEEK + 2
        if self._edge == Edge.TOP:
            return (pos.y() <= scr.top() + t
                    and geo.left() <= pos.x() <= geo.right())
        if self._edge == Edge.LEFT:
            return (pos.x() <= scr.left() + t
                    and geo.top() <= pos.y() <= geo.bottom())
        if self._edge == Edge.RIGHT:
            return (pos.x() >= scr.right() - t
                    and geo.top() <= pos.y() <= geo.bottom())
        return False
