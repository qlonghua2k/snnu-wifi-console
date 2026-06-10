from __future__ import annotations

import threading
from typing import Any, Callable

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtWidgets import QDialog, QMessageBox, QProgressDialog

from desktop.constants import APP_TITLE
from desktop.models.config_model import load_config, save_config
from desktop.services.keepalive_service import KeepaliveService
from desktop.views.main_window import MainWindow
from desktop.views.settings_dialog import SettingsDialog


class TaskSignals(QObject):
    finished = Signal(object)
    failed = Signal(str)


class MainController(QObject):
    def __init__(self, view: MainWindow):
        super().__init__(view)
        self.view = view
        self.service = KeepaliveService()
        self.task_signals: list[TaskSignals] = []
        self.progress_dialogs: dict[TaskSignals, QProgressDialog] = {}
        self.auto_keepalive_enabled = False
        self.keepalive_timer = QTimer(self)
        self.keepalive_timer.timeout.connect(self.run_auto_keepalive)
        self._connect_view()
        self.load_config_summary()
        self.load_auto_keepalive()
        self.refresh_status()
        self.refresh_logs()

    def _connect_view(self) -> None:
        self.view.status_refresh_requested.connect(self.refresh_status)
        self.view.logs_refresh_requested.connect(self.refresh_logs)
        self.view.settings_requested.connect(self.open_settings_dialog)
        self.view.run_once_requested.connect(self.run_once)
        self.view.auto_keepalive_toggle_requested.connect(self.toggle_auto_keepalive)
        self.view.wifi_toggle_requested.connect(self.toggle_wifi)
        self.view.hotspot_toggle_requested.connect(self.toggle_hotspot)
        self.view.start_service_requested.connect(self.start_service)
        self.view.stop_service_requested.connect(self.stop_service)
        self.view.install_service_requested.connect(self.install_service)
        self.view.fix_wifi_profile_requested.connect(self.fix_wifi_profile)
        self.view.register_startup_requested.connect(self.register_startup)
        self.view.unregister_startup_requested.connect(self.unregister_startup)
        self.view.operations_menu_opening_requested.connect(self.refresh_operations_menu_state)
        self.view.wifi_enable_requested.connect(self.enable_wifi)
        self.view.wifi_disable_requested.connect(self.disable_wifi)
        self.view.hotspot_enable_requested.connect(self.enable_hotspot)
        self.view.hotspot_disable_requested.connect(self.disable_hotspot)
        self.view.logs_dir_requested.connect(self.open_logs_dir)

    def load_config_summary(self) -> None:
        self.view.set_config_summary(load_config())

    def load_auto_keepalive(self) -> None:
        cfg = load_config()
        self.auto_keepalive_enabled = bool(cfg.get("autoKeepalive", False))
        interval = int(cfg.get("intervalSeconds", 60)) * 1000
        self.keepalive_timer.setInterval(max(interval, 10_000))
        if self.auto_keepalive_enabled:
            self.keepalive_timer.start()

    def open_settings_dialog(self) -> None:
        cfg = load_config()
        dialog = SettingsDialog(cfg, self.view)
        dialog.setStyleSheet(self.view.styleSheet())
        if dialog.exec() != QDialog.Accepted:
            return
        try:
            save_config(dialog.updated_config(cfg))
            self.load_config_summary()
            self.load_auto_keepalive()
            self.view.set_status_text("配置已保存")
        except Exception as exc:
            QMessageBox.critical(self.view, APP_TITLE, str(exc))

    def run_background(
        self,
        label: str,
        fn: Callable[[], Any],
        done: Callable[[Any], None] | None = None,
        show_progress: bool = True,
    ) -> None:
        self.view.set_status_text(f"{label}中...")
        signals = TaskSignals()
        self.task_signals.append(signals)
        if show_progress:
            self.show_progress(label, signals)
        signals.finished.connect(lambda result, s=signals: self.finish_background(label, result, done, s))
        signals.failed.connect(lambda error, s=signals: self.fail_background(label, error, s))

        def worker() -> None:
            try:
                signals.finished.emit(fn())
            except Exception as exc:
                signals.failed.emit(str(exc))

        threading.Thread(target=worker, daemon=True).start()

    def show_progress(self, label: str, signals: TaskSignals) -> None:
        self.view.set_operations_enabled(False)
        dialog = QProgressDialog(f"{label}中...", "", 0, 0, self.view)
        dialog.setWindowTitle(APP_TITLE)
        dialog.setCancelButton(None)
        dialog.setWindowModality(Qt.ApplicationModal)
        dialog.setMinimumDuration(0)
        dialog.setAutoClose(False)
        dialog.setAutoReset(False)
        dialog.show()
        self.progress_dialogs[signals] = dialog

    def close_progress(self, signals: TaskSignals | None) -> None:
        if not signals:
            return
        dialog = self.progress_dialogs.pop(signals, None)
        if dialog:
            dialog.close()
            dialog.deleteLater()
        if not self.progress_dialogs:
            self.view.set_operations_enabled(True)

    def finish_background(
        self,
        label: str,
        result: Any,
        done: Callable[[Any], None] | None,
        signals: TaskSignals | None = None,
    ) -> None:
        if signals in self.task_signals:
            self.task_signals.remove(signals)
        self.close_progress(signals)
        if done:
            done(result)
        self.view.set_status_text(f"{label}完成")

    def fail_background(self, label: str, error: str, signals: TaskSignals | None = None) -> None:
        if signals in self.task_signals:
            self.task_signals.remove(signals)
        self.close_progress(signals)
        self.view.set_status_text(f"{label}失败")
        QMessageBox.critical(self.view, APP_TITLE, error)
        if label != "刷新状态":
            self.refresh_status()

    def refresh_status(self) -> None:
        self.run_background("刷新状态", self.service.status, self.view.set_status_data, show_progress=False)

    def refresh_operations_menu_state(self) -> None:
        try:
            self.view.set_operation_action_state(self.service.control_status())
        except Exception as exc:
            self.view.set_status_text(f"读取操作状态失败：{exc}")

    def refresh_logs(self) -> None:
        self.view.set_logs(self.service.read_logs())

    def run_once(self) -> None:
        self.run_background(
            "认证",
            self.service.run_once,
            lambda _result: (self.refresh_status(), self.refresh_logs()),
        )

    def run_auto_keepalive(self) -> None:
        if self.task_signals:
            return
        self.run_background(
            "自动保活",
            self.service.run_once,
            lambda _result: (self.refresh_status(), self.refresh_logs()),
            show_progress=False,
        )

    def toggle_auto_keepalive(self, enabled: bool) -> None:
        cfg = load_config()
        cfg["autoKeepalive"] = enabled
        save_config(cfg)
        self.auto_keepalive_enabled = enabled
        interval = int(cfg.get("intervalSeconds", 60)) * 1000
        self.keepalive_timer.setInterval(max(interval, 10_000))
        if enabled:
            self.keepalive_timer.start()
            self.run_auto_keepalive()
        else:
            self.keepalive_timer.stop()
        self.refresh_status()

    def start_service(self) -> None:
        self.run_background("启动服务", self.service.start_service, lambda _result: self.refresh_status())

    def stop_service(self) -> None:
        self.run_background("停止服务", self.service.stop_service, lambda _result: self.refresh_status())

    def toggle_service(self, enabled: bool) -> None:
        if enabled:
            self.start_service()
        else:
            self.stop_service()

    def install_service(self) -> None:
        self.run_background("安装服务", self.service.install_service, lambda _result: self.refresh_status())

    def fix_wifi_profile(self) -> None:
        self.run_background("修复配置", self.service.fix_wifi_profile, lambda _result: self.refresh_status())

    def register_startup(self) -> None:
        self.run_background("注册开机启动", self.service.register_startup, lambda _result: self.refresh_status())

    def unregister_startup(self) -> None:
        self.run_background("取消开机启动", self.service.unregister_startup, lambda _result: self.refresh_status())

    def enable_wifi(self) -> None:
        self.run_background("开启 Wi-Fi", lambda: self.service.set_wifi_enabled(True), lambda _result: self.refresh_status())

    def disable_wifi(self) -> None:
        self.run_background("关闭 Wi-Fi", lambda: self.service.set_wifi_enabled(False), lambda _result: self.refresh_status())

    def toggle_wifi(self, enabled: bool) -> None:
        if enabled:
            self.enable_wifi()
        else:
            self.disable_wifi()

    def enable_hotspot(self) -> None:
        self.run_background("开启热点", lambda: self.service.set_hotspot_enabled(True), lambda _result: self.refresh_status())

    def disable_hotspot(self) -> None:
        self.run_background("关闭热点", lambda: self.service.set_hotspot_enabled(False), lambda _result: self.refresh_status())

    def toggle_hotspot(self, enabled: bool) -> None:
        if enabled:
            self.enable_hotspot()
        else:
            self.disable_hotspot()

    def open_logs_dir(self) -> None:
        self.service.open_logs_dir()
