"""集中式主题与样式表 (QSS)。

支持深色 / 浅色两套配色, 以及"跟随系统"。所有面板复用同一套
设计 token: 运行期把当前生效配色写入可变的 ACTIVE 字典, 内联样式
通过 color() 读取, 这样切换主题后重建控件即可刷新颜色。
"""
from __future__ import annotations

# --- 深色配色 ----------------------------------------------------------
DARK = {
    "bg": "#171A24",
    "bg_alt": "#1F2330",
    "surface": "#272C3B",
    "surface_hover": "#323849",
    "border": "#363D52",
    "border_soft": "#2C3243",
    "text": "#EEF1F8",
    "text_dim": "#A2ABC4",
    "text_faint": "#6E7794",
    "accent": "#6C8EF5",
    "accent_hover": "#83A0F8",
    "accent_soft": "#2A3354",
    "success": "#4CC38A",
    "warning": "#E5A94E",
    "danger": "#E5604D",
    "q1": "#E5604D",
    "q2": "#4CC38A",
    "q3": "#E5A94E",
    "q4": "#6C8EF5",
}

# --- 浅色配色 ----------------------------------------------------------
LIGHT = {
    "bg": "#EEF1F7",
    "bg_alt": "#FFFFFF",
    "surface": "#FFFFFF",
    "surface_hover": "#EDF1FA",
    "border": "#CDD5E3",
    "border_soft": "#E2E7F0",
    "text": "#1C2130",
    "text_dim": "#56607A",
    "text_faint": "#8A93A8",
    "accent": "#3F6FE0",
    "accent_hover": "#3563D0",
    "accent_soft": "#E4ECFB",
    "success": "#2FA372",
    "warning": "#C8862F",
    "danger": "#D24A39",
    "q1": "#D24A39",
    "q2": "#2FA372",
    "q3": "#C8862F",
    "q4": "#3F6FE0",
}

# 当前生效配色 (可变, 内联样式读取它)。务必原地修改以保持引用有效。
ACTIVE: dict[str, str] = dict(DARK)
# 向后兼容别名: 旧代码通过 COLORS[...] 取色。
COLORS = ACTIVE

RADIUS = 12
RADIUS_SM = 8


def color(key: str) -> str:
    """读取当前生效配色, 供内联样式使用。"""
    return ACTIVE.get(key, "#000000")


def resolve_mode(mode: str) -> str:
    """把 'dark' / 'light' / 'system' 解析为实际的 'dark' 或 'light'。"""
    if mode == "light":
        return "light"
    if mode == "dark":
        return "dark"
    return "dark" if _system_is_dark() else "light"


def _system_is_dark() -> bool:
    """检测系统是否处于深色模式 (Windows 注册表), 失败时回退深色。"""
    import sys

    if not sys.platform.startswith("win"):
        return True
    try:
        import winreg

        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        )
        value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
        winreg.CloseKey(key)
        return value == 0
    except OSError:
        return True


def apply_palette(mode: str, accent: str | None = None) -> None:
    """根据模式更新 ACTIVE 配色 (原地修改以保持引用)。"""
    base = LIGHT if resolve_mode(mode) == "light" else DARK
    ACTIVE.clear()
    ACTIVE.update(base)
    if accent:
        ACTIVE["accent"] = accent
        ACTIVE["accent_hover"] = _lighten(accent, 0.12)
        ACTIVE["accent_soft"] = _mix(accent, ACTIVE["bg"], 0.82)


def build_qss(accent: str | None = None, mode: str = "dark") -> str:
    """根据模式与强调色生成完整 QSS, 并刷新 ACTIVE 配色。"""
    apply_palette(mode, accent)
    return _TEMPLATE.format(**ACTIVE, r=RADIUS, rs=RADIUS_SM)


def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def _rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    return "#{:02X}{:02X}{:02X}".format(*(max(0, min(255, int(v))) for v in rgb))


def _lighten(value: str, amount: float) -> str:
    r, g, b = _hex_to_rgb(value)
    return _rgb_to_hex((r + (255 - r) * amount, g + (255 - g) * amount, b + (255 - b) * amount))


def _mix(fg: str, bg: str, bg_weight: float) -> str:
    fr, fg_, fb = _hex_to_rgb(fg)
    br, bg_, bb = _hex_to_rgb(bg)
    w = bg_weight
    return _rgb_to_hex((
        fr * (1 - w) + br * w,
        fg_ * (1 - w) + bg_ * w,
        fb * (1 - w) + bb * w,
    ))


_TEMPLATE = """
* {{
    font-family: 'Microsoft YaHei UI', 'Segoe UI', sans-serif;
    font-size: 13px;
    color: {text};
    outline: none;
}}

#RootFrame {{
    background-color: {bg};
    border: 1px solid {border};
    border-radius: {r}px;
}}

#TitleBar {{ background-color: transparent; }}
#AppTitle {{
    font-size: 14px;
    font-weight: 700;
    color: {text};
    letter-spacing: 0.3px;
}}

QWidget#Panel {{ background-color: transparent; }}
QLabel#PanelTitle {{
    font-size: 16px;
    font-weight: 700;
    color: {text};
}}

/* 通用按钮 */
QPushButton {{
    background-color: {surface};
    border: 1px solid {border};
    border-radius: {rs}px;
    padding: 6px 14px;
    color: {text};
}}
QPushButton:hover {{
    background-color: {surface_hover};
    border: 1px solid {text_faint};
}}
QPushButton:pressed {{ background-color: {bg_alt}; }}
QPushButton#Primary {{
    background-color: {accent};
    border: 1px solid {accent};
    color: white;
    font-weight: 600;
}}
QPushButton#Primary:hover {{
    background-color: {accent_hover};
    border: 1px solid {accent_hover};
}}
QPushButton#Ghost {{
    background-color: transparent;
    border: none;
    color: {text_dim};
}}
QPushButton#Ghost:hover {{ color: {text}; background-color: {surface}; }}
QPushButton#WinBtn {{
    background-color: transparent;
    border: none;
    color: {text_dim};
    padding: 2px;
    font-size: 15px;
    border-radius: {rs}px;
}}
QPushButton#WinBtn:hover {{ background-color: {surface}; color: {text}; }}
QPushButton#CloseBtn:hover {{ background-color: {danger}; color: white; }}

/* 侧边导航 */
#NavBar {{
    background-color: {bg_alt};
    border: 1px solid {border_soft};
    border-radius: {r}px;
}}
QPushButton#NavBtn {{
    background-color: transparent;
    border: none;
    border-radius: {rs}px;
    padding: 10px 14px;
    text-align: left;
    color: {text_dim};
    font-size: 13px;
}}
QPushButton#NavBtn:hover {{ background-color: {surface}; color: {text}; }}
QPushButton#NavBtn:checked {{
    background-color: {accent_soft};
    color: {text};
    font-weight: 600;
    border-left: 3px solid {accent};
}}

/* 输入控件 */
QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QDoubleSpinBox, QSpinBox {{
    background-color: {bg_alt};
    border: 1px solid {border};
    border-radius: {rs}px;
    padding: 7px 10px;
    color: {text};
    selection-background-color: {accent};
    selection-color: white;
}}
QLineEdit:hover, QPlainTextEdit:hover, QComboBox:hover {{
    border: 1px solid {text_faint};
}}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus,
QComboBox:focus, QDoubleSpinBox:focus, QSpinBox:focus {{
    border: 1px solid {accent};
}}
QComboBox::drop-down {{ border: none; width: 20px; }}
QComboBox QAbstractItemView {{
    background-color: {surface};
    border: 1px solid {border};
    border-radius: {rs}px;
    selection-background-color: {accent};
    selection-color: white;
    color: {text};
    padding: 4px;
}}

/* 列表/滚动区 */
QScrollArea {{ background-color: transparent; border: none; }}
/* 滚动区视口及其内部 host 容器透明, 否则会露出默认白底 */
QScrollArea > QWidget > QWidget {{ background-color: transparent; }}
QListWidget {{
    background-color: {bg_alt};
    border: 1px solid {border_soft};
    border-radius: {rs}px;
    padding: 4px;
    color: {text};
}}
QListWidget::item {{
    background-color: transparent;
    border-radius: {rs}px;
    padding: 6px 8px;
    margin: 1px 0px;
    color: {text};
}}
QListWidget::item:hover {{ background-color: {surface_hover}; }}
QListWidget::item:selected {{ background-color: {accent_soft}; color: {text}; }}

QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{
    background: {border};
    border-radius: 5px;
    min-height: 28px;
}}
QScrollBar::handle:vertical:hover {{ background: {text_faint}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {border}; border-radius: 5px; min-width: 28px; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

/* 卡片 */
QFrame#Card {{
    background-color: {surface};
    border: 1px solid {border_soft};
    border-radius: {r}px;
}}
QFrame#Card:hover {{ border: 1px solid {border}; }}
/* 拖拽待办悬停于象限卡片时高亮 */
QFrame#Card[dropHover="true"] {{
    border: 2px dashed {accent};
    background-color: {accent_soft};
}}
QFrame#InputCard {{
    background-color: {bg_alt};
    border: 1px solid {border_soft};
    border-radius: {r}px;
}}
QFrame#DropZone {{
    background-color: {bg_alt};
    border: 2px dashed {border};
    border-radius: {rs}px;
}}
QFrame#DropZoneActive {{
    background-color: {accent_soft};
    border: 2px dashed {accent};
    border-radius: {rs}px;
}}

QCheckBox {{ spacing: 8px; color: {text}; }}
QCheckBox::indicator {{
    width: 17px; height: 17px;
    border: 1px solid {border};
    border-radius: 5px;
    background: {bg_alt};
}}
QCheckBox::indicator:hover {{ border: 1px solid {accent}; }}
QCheckBox::indicator:checked {{ background: {accent}; border: 1px solid {accent}; }}

QLabel#Dim {{ color: {text_dim}; }}
QLabel#Faint {{ color: {text_faint}; font-size: 12px; }}
QLabel#SectionTitle {{ font-size: 13px; font-weight: 600; color: {text}; }}

QToolTip {{
    background-color: {surface};
    color: {text};
    border: 1px solid {border};
    border-radius: {rs}px;
    padding: 4px 6px;
}}

QMenu {{
    background-color: {surface};
    border: 1px solid {border};
    border-radius: {rs}px;
    padding: 4px;
}}
QMenu::item {{ padding: 6px 18px; border-radius: {rs}px; color: {text}; }}
QMenu::item:selected {{ background-color: {accent}; color: white; }}

QDialog {{ background-color: {bg}; }}
QMessageBox {{ background-color: {bg}; }}
QMessageBox QLabel {{ color: {text}; }}
"""
