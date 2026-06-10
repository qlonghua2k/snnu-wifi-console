from __future__ import annotations

import os
import sys
from typing import Any

from desktop.constants import APP_ROOT, BUNDLE_ROOT, SERVICE_NAME, SOURCE_ROOT, STARTUP_ENTRY_NAME
from desktop.core.keepalive import KeepaliveManager
from desktop.models.config_model import config_path, load_config
from desktop.utils.windows import quote_ps, run_command, run_elevated_command, run_elevated_powershell, powershell_path


class KeepaliveService:
    def manager(self) -> KeepaliveManager:
        return KeepaliveManager(config_path())

    def status(self) -> dict[str, Any]:
        data = self.manager().status()
        cfg = load_config()
        data["autoKeepalive"] = bool(cfg.get("autoKeepalive", False))
        data["serviceState"] = self.service_state()
        data["serviceRunning"] = data["serviceState"] == "RUNNING"
        data["startupRegistered"] = self.startup_registered()
        data["wifiEnabled"] = str(data.get("adapterStatus") or "").lower() != "disabled"
        data["hotspotState"] = self.hotspot_state()
        data["hotspotEnabled"] = data["hotspotState"].lower() == "on"
        return data

    def control_status(self) -> dict[str, Any]:
        return {
            "serviceState": self.service_state(),
            "startupRegistered": self.startup_registered(),
        }

    def run_once(self) -> Any:
        return self.manager().run_once()

    def start_service(self) -> None:
        run_elevated_command(
            ["sc.exe", "start", SERVICE_NAME],
            label="Start service",
            success_codes={0, 1056},
        )

    def stop_service(self) -> None:
        run_elevated_command(
            ["sc.exe", "stop", SERVICE_NAME],
            label="Stop service",
            success_codes={0, 1062},
        )

    def install_service(self) -> None:
        service_exe = APP_ROOT / "SNNUWifiKeepaliveService.exe"
        if service_exe.exists():
            run_elevated_command([str(service_exe), "install"], label="Install service")
            run_elevated_command(
                ["sc.exe", "description", SERVICE_NAME, "Keep SNNU Wi-Fi connected and auto-login to portal."],
                label="Set service description",
            )
            run_elevated_command(
                ["sc.exe", "failure", SERVICE_NAME, "reset=", "60", "actions=", "restart/5000/restart/5000/restart/5000"],
                label="Set service recovery",
            )
            run_elevated_command(["sc.exe", "failureflag", SERVICE_NAME, "1"], label="Enable service recovery flag")
            run_elevated_command(["sc.exe", "config", SERVICE_NAME, "start=", "delayed-auto"], label="Set service autostart")
            run_elevated_command(["sc.exe", "config", SERVICE_NAME, "depend=", "WlanSvc"], label="Set service dependency")
            run_elevated_command([str(service_exe), "start"], label="Start service", success_codes={0, 1056})
            return

        script = BUNDLE_ROOT / "scripts" / "service" / "install-service.ps1"
        run_elevated_powershell(["-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script), "-Force", "-RunNow"])

    def register_startup(self) -> None:
        script = BUNDLE_ROOT / "scripts" / "app" / "register-startup.ps1"
        args = ["-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)]
        if getattr(sys, "frozen", False):
            args.extend(["-ExecutablePath", sys.executable])
        result = run_command([powershell_path(), *args], timeout=60)
        if result.returncode != 0:
            raise RuntimeError((result.stderr or result.stdout or "注册开机启动失败").strip())

    def unregister_startup(self) -> None:
        script = BUNDLE_ROOT / "scripts" / "app" / "unregister-startup.ps1"
        result = run_command([powershell_path(), "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)], timeout=60)
        if result.returncode != 0:
            raise RuntimeError((result.stderr or result.stdout or "取消开机启动失败").strip())

    def fix_wifi_profile(self) -> None:
        cfg = load_config()
        profile = cfg.get("profileName") or cfg.get("ssid", "SNNU")
        script = BUNDLE_ROOT / "scripts" / "network" / "fix-wifi-profile.ps1"
        run_elevated_powershell(["-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script), "-Profile", profile])

    def set_wifi_enabled(self, enabled: bool) -> None:
        cfg = load_config()
        adapter_info = self.manager().wifi_adapter()
        adapter = cfg.get("adapterName") or (adapter_info or {}).get("Name") or "WLAN"
        verb = "Enable-NetAdapter" if enabled else "Disable-NetAdapter"
        command = f"{verb} -Name {quote_ps(str(adapter))} -Confirm:$false -ErrorAction Stop"
        run_elevated_powershell(["-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command])

    def set_hotspot_enabled(self, enabled: bool) -> None:
        script = BUNDLE_ROOT / "scripts" / "network" / "set-hotspot.ps1"
        flag = "-Enable" if enabled else "-Disable"
        result = run_command([powershell_path(), "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script), flag], timeout=60)
        if result.returncode != 0:
            raise RuntimeError((result.stderr or result.stdout or "热点切换失败").strip())

    def service_state(self) -> str:
        result = run_command(["sc.exe", "query", SERVICE_NAME], timeout=15)
        if result.returncode != 0:
            return "NOT_INSTALLED"
        output = f"{result.stdout}\n{result.stderr}"
        if "RUNNING" in output:
            return "RUNNING"
        if "STOPPED" in output:
            return "STOPPED"
        if "START_PENDING" in output:
            return "STARTING"
        if "STOP_PENDING" in output:
            return "STOPPING"
        return "UNKNOWN"

    def startup_registered(self) -> bool:
        try:
            import winreg

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run") as key:
                winreg.QueryValueEx(key, STARTUP_ENTRY_NAME)
                return True
        except FileNotFoundError:
            return False
        except OSError:
            return False

    def hotspot_state(self) -> str:
        script = BUNDLE_ROOT / "scripts" / "network" / "set-hotspot.ps1"
        result = run_command(
            [powershell_path(), "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script), "-Status"],
            timeout=8,
        )
        if result.returncode != 0:
            return "UNKNOWN"
        output = (result.stdout or "").strip()
        if ":" in output:
            return output.rsplit(":", 1)[-1].strip()
        return output or "UNKNOWN"

    def read_logs(self, lines: int = 180) -> str:
        cfg = load_config()
        log_path = APP_ROOT / cfg.get("logPath", "logs\\wifi-keepalive.log")
        if not log_path.exists() and not getattr(sys, "frozen", False):
            log_path = SOURCE_ROOT / cfg.get("logPath", "logs\\wifi-keepalive.log")
        if not log_path.exists():
            return "日志文件还不存在。"
        return "\n".join(log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:])

    def open_logs_dir(self) -> None:
        logs = APP_ROOT / "logs"
        if not logs.exists() and not getattr(sys, "frozen", False):
            logs = SOURCE_ROOT / "logs"
        logs.mkdir(exist_ok=True)
        os.startfile(str(logs))
