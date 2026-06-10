from __future__ import annotations

import json
import os
import secrets
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import win32event
import win32service
import win32serviceutil
import servicemanager


def resolve_bundle_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent / "_internal"))
    return Path(__file__).resolve().parents[2]


def resolve_app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    root = resolve_bundle_root()
    return root.parent if root.name == "_internal" else root


BUNDLE_ROOT = resolve_bundle_root()
APP_ROOT = resolve_app_root()
CONFIG_PATH = APP_ROOT / "config" / "snnu-config.json"
TOKEN_PATH = APP_ROOT / "config" / "admin-token.txt"
HELPER_PORT = int(os.environ.get("SNNU_HELPER_PORT", "18609"))
SERVICE_NAME = "SNNUWifiKeepalive"


def load_token() -> str:
    if TOKEN_PATH.exists():
        return TOKEN_PATH.read_text(encoding="utf-8").strip()
    token = secrets.token_urlsafe(24)
    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_PATH.write_text(token, encoding="utf-8")
    return token


def bundle_root() -> Path:
    return BUNDLE_ROOT


def powershell_path() -> str:
    windir = os.environ.get("WINDIR", r"C:\Windows")
    return str(Path(windir) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe")


def run_cmd(cmd: list[str]) -> tuple[int, str]:
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    result = subprocess.run(cmd, capture_output=True, text=True, errors="replace", creationflags=flags)
    out = (result.stdout or "").strip()
    err = (result.stderr or "").strip()
    if out and err:
        msg = f"{out}\n{err}"
    else:
        msg = out or err
    return result.returncode, msg


def run_steps(steps: list[list[str]]) -> tuple[bool, str]:
    messages: list[str] = []
    for cmd in steps:
        code, msg = run_cmd(cmd)
        if msg:
            messages.append(msg)
        if code != 0:
            return False, "\n".join(messages) or f"Command failed: {' '.join(cmd)}"
    return True, "\n".join(messages)


def do_action(action: str, payload: dict[str, str]) -> tuple[bool, str]:
    root = bundle_root()
    if action == "service_install":
        service_exe = APP_ROOT / "SNNUWifiKeepaliveService.exe"
        if service_exe.exists():
            return run_steps(
                [
                    [str(service_exe), "install"],
                    ["sc.exe", "description", SERVICE_NAME, "Keep SNNU Wi-Fi connected and auto-login to portal."],
                    ["sc.exe", "failure", SERVICE_NAME, "reset=", "60", "actions=", "restart/5000/restart/5000/restart/5000"],
                    ["sc.exe", "failureflag", SERVICE_NAME, "1"],
                    ["sc.exe", "config", SERVICE_NAME, "start=", "delayed-auto"],
                    ["sc.exe", "config", SERVICE_NAME, "depend=", "WlanSvc"],
                    [str(service_exe), "start"],
                ]
            )
        ps = powershell_path()
        script = root / "scripts" / "service" / "install-service.ps1"
        code, msg = run_cmd([ps, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script), "-RunNow"])
        return code == 0, msg
    if action == "service_uninstall":
        service_exe = APP_ROOT / "SNNUWifiKeepaliveService.exe"
        if service_exe.exists():
            _, stop_msg = run_cmd([str(service_exe), "stop"])
            remove_code, remove_msg = run_cmd([str(service_exe), "remove"])
            msg = "\n".join(part for part in [stop_msg, remove_msg] if part)
            return remove_code == 0, msg
        ps = powershell_path()
        script = root / "scripts" / "service" / "uninstall-service.ps1"
        code, msg = run_cmd([ps, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)])
        return code == 0, msg
    if action == "service_start":
        code, msg = run_cmd(["sc.exe", "start", SERVICE_NAME])
        return code == 0, msg
    if action == "service_stop":
        code, msg = run_cmd(["sc.exe", "stop", SERVICE_NAME])
        return code == 0, msg
    if action == "service_autostart":
        enable = payload.get("enable") in {"1", "true", "True", "yes"}
        start_value = "auto" if enable else "demand"
        code, msg = run_cmd(["sc.exe", "config", SERVICE_NAME, "start=", start_value])
        return code == 0, msg
    return False, f"Unknown action: {action}"


class Handler(BaseHTTPRequestHandler):
    def _send(self, status: int, data: dict[str, object]) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):  # noqa: N802
        token = self.headers.get("X-Admin-Token", "")
        if token != load_token():
            self._send(403, {"ok": False, "message": "Invalid token."})
            return
        length = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(length) if length > 0 else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            self._send(400, {"ok": False, "message": "Invalid JSON."})
            return
        action = payload.get("action", "")
        ok, msg = do_action(action, payload)
        self._send(200, {"ok": ok, "message": msg})

    def log_message(self, format: str, *args) -> None:  # noqa: A002
        return


class AdminHelperService(win32serviceutil.ServiceFramework):
    _svc_name_ = "SNNUAdminHelper"
    _svc_display_name_ = "SNNU Admin Helper"
    _svc_description_ = "Executes privileged actions for SNNU Web UI."

    def __init__(self, args):
        super().__init__(args)
        self.hWaitStop = win32event.CreateEvent(None, 0, 0, None)
        self.server: ThreadingHTTPServer | None = None
        self.thread: threading.Thread | None = None

    def SvcStop(self):
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        win32event.SetEvent(self.hWaitStop)
        if self.server:
            self.server.shutdown()

    def SvcDoRun(self):
        servicemanager.LogInfoMsg("SNNU Admin Helper starting.")
        load_token()
        self.server = ThreadingHTTPServer(("127.0.0.1", HELPER_PORT), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        win32event.WaitForSingleObject(self.hWaitStop, win32event.INFINITE)
        if self.server:
            self.server.server_close()
        servicemanager.LogInfoMsg("SNNU Admin Helper stopped.")


if __name__ == "__main__":
    win32serviceutil.HandleCommandLine(AdminHelperService)
