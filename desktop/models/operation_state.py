from __future__ import annotations

from typing import Any


def menu_action_enabled(status: dict[str, Any]) -> dict[str, bool]:
    service_state = str(status.get("serviceState") or "UNKNOWN")
    service_installed = service_state != "NOT_INSTALLED"
    service_running = service_state == "RUNNING"
    startup_registered = bool(status.get("startupRegistered"))

    return {
        "run_once": True,
        "install_service": not service_installed,
        "start_service": service_installed and not service_running,
        "stop_service": service_running,
        "fix_wifi_profile": True,
        "register_startup": not startup_registered,
        "unregister_startup": startup_registered,
    }
