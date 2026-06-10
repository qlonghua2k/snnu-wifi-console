from __future__ import annotations

import sys
from pathlib import Path
import json

from PySide6.QtCore import QLockFile
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

SOURCE_ROOT = Path(__file__).resolve().parents[1]
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from desktop.constants import APP_ICON_PNG, APP_ROOT, APP_TITLE  # noqa: E402
from desktop.controllers.main_controller import MainController  # noqa: E402
from desktop.core.keepalive import KeepaliveManager  # noqa: E402
from desktop.models.config_model import ensure_config  # noqa: E402
from desktop.views.fonts import choose_ui_font  # noqa: E402
from desktop.views.main_window import MainWindow  # noqa: E402


def make_icon() -> QIcon:
    return QIcon(str(APP_ICON_PNG))


def set_app_user_model_id() -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("SNNU.WiFi.Console")
    except Exception:
        pass


def create_lock() -> QLockFile:
    lock_dir = APP_ROOT / "logs"
    lock_dir.mkdir(exist_ok=True)
    lock = QLockFile(str(lock_dir / "desktop.lock"))
    lock.setStaleLockTime(10_000)
    return lock


def value_after(flag: str) -> str:
    if flag not in sys.argv:
        return ""
    index = sys.argv.index(flag)
    if index + 1 >= len(sys.argv):
        return ""
    return sys.argv[index + 1]


def run_keepalive_command() -> int | None:
    if not any(arg in sys.argv for arg in {"--keepalive", "--keepalive-once", "--keepalive-status"}):
        return None
    config = value_after("--config")
    manager = KeepaliveManager(config or None)
    if "--keepalive-status" in sys.argv:
        print(json.dumps(manager.status(), ensure_ascii=False))
        return 0
    if "--keepalive-once" in sys.argv:
        manager.run_once()
        return 0
    manager.run_forever()
    return 0


def main() -> int:
    keepalive_code = run_keepalive_command()
    if keepalive_code is not None:
        return keepalive_code

    start_minimized = "--minimized" in sys.argv

    ensure_config()
    set_app_user_model_id()
    app = QApplication(sys.argv)
    app.setApplicationName(APP_TITLE)
    app.setWindowIcon(make_icon())
    app.setFont(choose_ui_font())

    lock = create_lock()
    if not lock.tryLock(100):
        QMessageBox.information(None, APP_TITLE, "SNNU Wi-Fi 控制台已在运行。")
        return 0

    window = MainWindow()
    window.setWindowIcon(make_icon())
    controller = MainController(window)
    window.controller = controller
    if start_minimized:
        window.hide()
    else:
        window.show()
    code = app.exec()
    lock.unlock()
    return code


if __name__ == "__main__":
    raise SystemExit(main())
