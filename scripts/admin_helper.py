from __future__ import annotations

import json
import os
import secrets
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import win32event
import win32service
import win32serviceutil
import servicemanager

REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = REPO_ROOT / "config" / "snnu-config.json"
TOKEN_PATH = REPO_ROOT / "config" / "admin-token.txt"
HELPER_PORT = int(os.environ.get("SNNU_HELPER_PORT", "18609"))
SERVICE_NAME = "SNNUWifiKeepalive"


def load_token() -> str:
    if TOKEN_PATH.exists():
        return TOKEN_PATH.read_text(encoding="utf-8").strip()
    token = secrets.token_urlsafe(24)
    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_PATH.write_text(token, encoding="utf-8")
    return token


def repo_root() -> Path:
    return REPO_ROOT


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


def do_action(action: str, payload: dict[str, str]) -> tuple[bool, str]:
    root = repo_root()
    if action == "service_install":
        ps = powershell_path()
        script = root / "scripts" / "install-service.ps1"
        code, msg = run_cmd([ps, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script), "-RunNow"])
        return code == 0, msg
    if action == "service_uninstall":
        ps = powershell_path()
        script = root / "scripts" / "uninstall-service.ps1"
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
