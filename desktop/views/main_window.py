from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QPainter, QPen, QPixmap, QTextCursor
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFrame,
    QGraphicsDropShadowEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QPushButton,
    QSizePolicy,
    QSystemTrayIcon,
    QTextEdit,
    QVBoxLayout,
)

from desktop.constants import APP_TITLE, DESKTOP_ASSETS_DIR, NETWORK_LABELS
from desktop.models.config_model import display, masked_username, normalize_state
from desktop.views.background import Background
from desktop.views.styles import build_styles


class MainWindow(QMainWindow):
    status_refresh_requested = Signal()
    logs_refresh_requested = Signal()
    settings_requested = Signal()
    run_once_requested = Signal()
    auto_keepalive_toggle_requested = Signal(bool)
    wifi_toggle_requested = Signal(bool)
    hotspot_toggle_requested = Signal(bool)
    start_service_requested = Signal()
    stop_service_requested = Signal()
    install_service_requested = Signal()
    fix_wifi_profile_requested = Signal()
    register_startup_requested = Signal()
    unregister_startup_requested = Signal()
    operations_menu_opening_requested = Signal()
    wifi_enable_requested = Signal()
    wifi_disable_requested = Signal()
    hotspot_enable_requested = Signal()
    hotspot_disable_requested = Signal()
    logs_dir_requested = Signal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.setFixedSize(1280, 760)
        self.setWindowFlag(Qt.WindowMaximizeButtonHint, False)
        self.move(120, 80)

        self.status_labels: dict[str, QLabel] = {}
        self.config_labels: dict[str, QLabel] = {}
        self.switches: dict[str, QCheckBox] = {}
        self.switch_labels: dict[str, QLabel] = {}
        self.operation_controls: list[Any] = []
        self.operation_actions: dict[str, QAction] = {}
        self.log_view: QTextEdit | None = None
        self.status_bar_label = QLabel("就绪")
        self.tray: QSystemTrayIcon | None = None
        self.theme = "light"
        self.background: Background | None = None

        self.build_ui()
        self.apply_theme()
        self.setup_tray()

    def build_ui(self) -> None:
        self.background = Background(DESKTOP_ASSETS_DIR / "background.png")
        self.setCentralWidget(self.background)

        root = QVBoxLayout(self.background)
        root.setContentsMargins(28, 20, 28, 12)
        root.setSpacing(12)

        root.addLayout(self.build_header())

        body = QHBoxLayout()
        body.setSpacing(16)
        root.addLayout(body, 1)

        left = QVBoxLayout()
        left.setSpacing(12)
        body.addLayout(left, 0)

        left.addWidget(self.build_status_card())
        left.addWidget(self.build_config_card())
        left.addWidget(self.build_actions_card())
        left.addStretch(1)

        body.addWidget(self.build_log_card(), 1)

        footer = QHBoxLayout()
        self.status_bar_label.setObjectName("footerStatus")
        footer.addWidget(self.status_bar_label)
        footer.addStretch(1)
        root.addLayout(footer)

    def build_header(self) -> QHBoxLayout:
        header = QHBoxLayout()
        header.setSpacing(14)

        title_block = QVBoxLayout()
        title_block.setSpacing(4)
        eyebrow = QLabel("陕西师范大学 / 本地网络控制台")
        eyebrow.setObjectName("eyebrow")
        title_block.addWidget(eyebrow)
        title = QLabel("SNNU Wi-Fi 控制台")
        title.setObjectName("title")
        subtitle = QLabel("校园网连接 · 门户认证 · 守护服务管理")
        subtitle.setObjectName("subtitle")
        title_block.addWidget(title)
        title_block.addWidget(subtitle)
        header.addLayout(title_block)
        header.addStretch(1)

        self.status_pill = QLabel("检测中")
        self.status_pill.setObjectName("statusPill")
        self.status_pill.setAlignment(Qt.AlignCenter)
        self.status_pill.setFixedSize(96, 40)
        header.addWidget(self.status_pill)

        self.theme_button = QPushButton()
        self.theme_button.setObjectName("iconButton")
        self.theme_button.setToolTip("切换主题")
        self.theme_button.setFixedSize(40, 40)
        self.theme_button.clicked.connect(self.toggle_theme)
        header.addWidget(self.theme_button)

        refresh = QPushButton("刷新状态")
        refresh.setObjectName("secondaryButton")
        refresh.setFixedSize(96, 40)
        refresh.clicked.connect(self.status_refresh_requested.emit)
        header.addWidget(refresh)
        return header

    def build_status_card(self) -> QFrame:
        card = self.card("statusCard")
        card.setFixedHeight(198)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 12, 18, 12)
        layout.setSpacing(7)

        top = QHBoxLayout()
        heading = QLabel("连接状态")
        heading.setObjectName("cardTitle")
        top.addWidget(heading)
        top.addStretch(1)
        self.health_dot = QLabel()
        self.health_dot.setObjectName("healthDot")
        self.health_dot.setFixedSize(12, 12)
        top.addWidget(self.health_dot)
        layout.addLayout(top)

        state = QLabel("-")
        state.setObjectName("hudState")
        state.setFixedHeight(42)
        self.status_labels["lastState"] = state
        layout.addWidget(state)

        self.hud_detail = QLabel("SSID -  /  IP -  /  网卡 -")
        self.hud_detail.setObjectName("hudDetail")
        self.hud_detail.setWordWrap(True)
        self.hud_detail.setFixedHeight(34)
        layout.addWidget(self.hud_detail)

        self.profile_warning = QLabel("服务模式可能无法读取当前 Wi-Fi 配置文件")
        self.profile_warning.setObjectName("warningText")
        self.profile_warning.setWordWrap(True)
        self.profile_warning.setFixedHeight(28)
        self.profile_warning.hide()
        layout.addWidget(self.profile_warning)

        self.error_hint = QLabel("")
        self.error_hint.setObjectName("hintText")
        self.error_hint.setWordWrap(True)
        self.error_hint.setFixedHeight(28)
        self.error_hint.hide()
        layout.addWidget(self.error_hint)
        return card

    def build_config_card(self) -> QFrame:
        card = self.card("configCard")
        card.setFixedHeight(154)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 12, 18, 12)
        layout.setSpacing(8)

        title = QLabel("连接配置")
        title.setObjectName("cardTitle")
        layout.addWidget(title)

        rows = QGridLayout()
        rows.setHorizontalSpacing(12)
        rows.setVerticalSpacing(8)
        for row, (key, label) in enumerate([("ssid", "SSID"), ("network", "网络"), ("username", "账号")]):
            lab = QLabel(label)
            lab.setObjectName("formLabel")
            value = QLabel("-")
            value.setObjectName("fieldValue")
            self.config_labels[key] = value
            rows.addWidget(lab, row, 0)
            rows.addWidget(value, row, 1)
        layout.addLayout(rows)

        edit = QPushButton("修改配置")
        edit.setObjectName("secondaryButton")
        edit.setFixedSize(96, 38)
        edit.clicked.connect(self.settings_requested.emit)
        layout.addWidget(edit, alignment=Qt.AlignRight)
        return card

    def build_actions_card(self) -> QFrame:
        card = self.card("actionsCard")
        card.setFixedHeight(250)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 12, 18, 12)
        layout.setSpacing(10)

        title = QLabel("控制开关")
        title.setObjectName("cardTitle")
        layout.addWidget(title)

        layout.addLayout(self.build_switch_row("auto", "自动保活", self.auto_keepalive_toggle_requested.emit))
        layout.addLayout(self.build_switch_row("wifi", "Wi-Fi", self.wifi_toggle_requested.emit))
        layout.addLayout(self.build_switch_row("hotspot", "移动热点", self.hotspot_toggle_requested.emit))
        layout.addStretch(1)

        more = QPushButton("更多")
        more.setObjectName("secondaryButton")
        more.setFixedHeight(38)
        menu = QMenu(more)
        menu.aboutToShow.connect(self.operations_menu_opening_requested.emit)
        for action_id, text, handler in [
            ("run_once", "立即检测", self.run_once_requested.emit),
            ("install_service", "安装服务", self.install_service_requested.emit),
            ("start_service", "启动服务", self.start_service_requested.emit),
            ("stop_service", "停止服务", self.stop_service_requested.emit),
            ("fix_wifi_profile", "修复配置", self.fix_wifi_profile_requested.emit),
            ("register_startup", "注册开机启动", self.register_startup_requested.emit),
            ("unregister_startup", "取消开机启动", self.unregister_startup_requested.emit),
        ]:
            action = QAction(text, self)
            action.triggered.connect(handler)
            menu.addAction(action)
            self.operation_actions[action_id] = action
        more.setMenu(menu)
        self.operation_controls.append(more)
        layout.addWidget(more)
        return card

    def build_switch_row(self, key: str, label: str, handler: Any) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(10)

        name = QLabel(label)
        name.setObjectName("switchName")
        row.addWidget(name)
        row.addStretch(1)

        state = QLabel("未知")
        state.setObjectName("switchState")
        state.setFixedWidth(64)
        state.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.switch_labels[key] = state
        row.addWidget(state)

        switch = QCheckBox()
        switch.setObjectName("toggleSwitch")
        switch.setFixedSize(58, 30)
        switch.toggled.connect(handler)
        self.switches[key] = switch
        self.operation_controls.append(switch)
        row.addWidget(switch)
        return row

    def build_log_card(self) -> QFrame:
        card = self.card("logCard")
        card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(12)

        top = QHBoxLayout()
        title = QLabel("运行日志")
        title.setObjectName("cardTitle")
        top.addWidget(title)
        top.addStretch(1)

        refresh = QPushButton("刷新日志")
        refresh.setObjectName("secondaryButton")
        refresh.setFixedSize(96, 40)
        refresh.clicked.connect(self.logs_refresh_requested.emit)
        top.addWidget(refresh)

        open_dir = QPushButton("打开目录")
        open_dir.setObjectName("secondaryButton")
        open_dir.setFixedSize(96, 40)
        open_dir.clicked.connect(self.logs_dir_requested.emit)
        top.addWidget(open_dir)
        layout.addLayout(top)

        self.log_view = QTextEdit()
        self.log_view.setObjectName("logView")
        self.log_view.setReadOnly(True)
        self.log_view.setLineWrapMode(QTextEdit.NoWrap)
        self.log_view.setFont(QFont("Cascadia Mono", 10))
        layout.addWidget(self.log_view, 1)
        return card

    def card(self, name: str) -> QFrame:
        frame = QFrame()
        frame.setObjectName(name)
        frame.setProperty("class", "card")
        if name == "logCard":
            frame.setFixedWidth(862)
        else:
            frame.setFixedWidth(346)
        shadow = QGraphicsDropShadowEffect(frame)
        shadow.setBlurRadius(24)
        shadow.setOffset(0, 8)
        shadow.setColor(QColor(0, 0, 0, 72))
        frame.setGraphicsEffect(shadow)
        return frame

    def apply_theme(self) -> None:
        self.setStyleSheet(build_styles(self.theme))
        if self.background:
            self.background.set_theme(self.theme)
        self.theme_button.setIcon(self.theme_icon("dark" if self.theme == "light" else "light"))
        self.theme_button.setIconSize(self.theme_button.size() * 0.55)
        self.apply_state_polish()

    def toggle_theme(self) -> None:
        self.theme = "dark" if self.theme == "light" else "light"
        self.apply_theme()

    def set_config_summary(self, cfg: dict[str, Any]) -> None:
        creds = cfg.get("credentials") or {}
        options = cfg.get("portalOptions") or {}
        self.config_labels["ssid"].setText(display(cfg.get("ssid", "SNNU")))
        self.config_labels["network"].setText(NETWORK_LABELS.get(options.get("networkType", "campus"), "校园网"))
        self.config_labels["username"].setText(masked_username(creds.get("username", "")))

    def set_status_data(self, status: dict[str, Any]) -> None:
        online = bool(status.get("connectivityOk"))
        raw_state = status.get("lastState") or "UNKNOWN"
        state_text = "在线" if online else normalize_state(raw_state)
        self.status_labels["lastState"].setText(state_text)
        self.hud_detail.setText(
            f"SSID {display(status.get('ssid'))}  /  IP {display(status.get('ip'))}  /  网卡 {display(status.get('adapter'))}"
        )

        if online:
            pill_text, state = "在线", "online"
        elif raw_state in {"CONNECTED_NO_NET", "LOGIN_COOLDOWN", "NEEDS_LOGIN"}:
            pill_text, state = "待认证", "warning"
        else:
            pill_text, state = "离线", "offline"
        self.status_pill.setText(pill_text)
        self.status_pill.setProperty("state", state)
        self.health_dot.setProperty("state", state)
        self.apply_state_polish()

        self.set_switch_state("auto", bool(status.get("autoKeepalive")), "开启" if status.get("autoKeepalive") else "关闭")
        self.set_switch_state("wifi", bool(status.get("wifiEnabled")), "开启" if status.get("wifiEnabled") else "关闭")
        self.set_switch_state("hotspot", bool(status.get("hotspotEnabled")), self.hotspot_state_text(status.get("hotspotState")))

        profile_ready = bool(status.get("allUserProfile"))
        last_error = str(status.get("lastError") or "")
        self.profile_warning.setVisible(not profile_ready)
        self.error_hint.setVisible(bool(last_error))
        self.error_hint.setText(f"最近错误：{last_error}" if last_error else "")
        if not profile_ready:
            self.set_status_text("提示：服务模式可能无法读取当前 Wi-Fi 配置文件，可点击“修复配置”。")
        elif last_error:
            self.set_status_text(f"最近错误：{last_error}")
        self.set_operation_action_state(status)

    def set_logs(self, content: str) -> None:
        if not self.log_view:
            return
        self.log_view.setPlainText(content)
        self.log_view.moveCursor(QTextCursor.MoveOperation.End)

    def set_status_text(self, message: str) -> None:
        self.status_bar_label.setText(message)

    def set_switch_state(self, key: str, checked: bool, label: str) -> None:
        switch = self.switches.get(key)
        state = self.switch_labels.get(key)
        if switch:
            switch.blockSignals(True)
            switch.setChecked(checked)
            switch.blockSignals(False)
        if state:
            state.setText(label)

    def set_operations_enabled(self, enabled: bool) -> None:
        for control in self.operation_controls:
            control.setEnabled(enabled)

    def set_operation_action_state(self, status: dict[str, Any]) -> None:
        from desktop.models.operation_state import menu_action_enabled

        enabled = menu_action_enabled(status)
        for action_id, action in self.operation_actions.items():
            action.setEnabled(enabled.get(action_id, True))

    @staticmethod
    def service_state_text(value: Any) -> str:
        mapping = {
            "RUNNING": "运行",
            "STOPPED": "停止",
            "STARTING": "启动中",
            "STOPPING": "停止中",
            "NOT_INSTALLED": "未安装",
        }
        return mapping.get(str(value or ""), "未知")

    @staticmethod
    def hotspot_state_text(value: Any) -> str:
        mapping = {
            "On": "开启",
            "Off": "关闭",
            "InTransition": "切换中",
            "UNKNOWN": "未知",
        }
        return mapping.get(str(value or ""), str(value or "未知"))

    def apply_state_polish(self) -> None:
        for widget in [getattr(self, "status_pill", None), getattr(self, "health_dot", None), getattr(self, "theme_button", None)]:
            if widget:
                widget.style().unpolish(widget)
                widget.style().polish(widget)

    @staticmethod
    def theme_icon(target_theme: str) -> QIcon:
        pix = QPixmap(28, 28)
        pix.fill(Qt.transparent)
        painter = QPainter(pix)
        painter.setRenderHint(QPainter.Antialiasing)
        if target_theme == "dark":
            painter.setBrush(QColor("#174767"))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(6, 4, 16, 16)
            painter.setBrush(QColor(0, 0, 0, 0))
            painter.setCompositionMode(QPainter.CompositionMode_Clear)
            painter.drawEllipse(12, 1, 16, 16)
            painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
        else:
            painter.setPen(QPen(QColor("#f6b73c"), 2))
            painter.drawLine(14, 1, 14, 5)
            painter.drawLine(14, 23, 14, 27)
            painter.drawLine(1, 14, 5, 14)
            painter.drawLine(23, 14, 27, 14)
            painter.setBrush(QColor("#f6b73c"))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(8, 8, 12, 12)
        painter.end()
        return QIcon(pix)

    def setup_tray(self) -> None:
        icon = self.windowIcon()
        self.tray = QSystemTrayIcon(icon, self)
        self.tray.setToolTip(APP_TITLE)

        menu = QMenu()
        show_action = QAction("显示主窗口", self)
        show_action.triggered.connect(self.show_normal)
        refresh_action = QAction("刷新状态", self)
        refresh_action.triggered.connect(self.status_refresh_requested.emit)
        quit_action = QAction("退出", self)
        quit_action.triggered.connect(QApplication.instance().quit)
        menu.addAction(show_action)
        menu.addAction(refresh_action)
        menu.addSeparator()
        menu.addAction(quit_action)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(
            lambda reason: self.show_normal()
            if reason == QSystemTrayIcon.ActivationReason.DoubleClick
            else None
        )
        self.tray.show()

    def show_normal(self) -> None:
        self.show()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event) -> None:  # noqa: N802
        if self.tray and self.tray.isVisible():
            event.ignore()
            self.hide()
            self.tray.showMessage(
                APP_TITLE,
                "已最小化到系统托盘",
                QSystemTrayIcon.MessageIcon.Information,
                1600,
            )
        else:
            super().closeEvent(event)
