from __future__ import annotations

import subprocess
import sys
import time
import json
from pathlib import Path

import win32event
import win32service
import win32serviceutil
import servicemanager


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def resolve_python(root: Path) -> str:
    cfg_path = root / "config" / "snnu-config.json"
    if cfg_path.exists():
        try:
            cfg = json.loads(cfg_path.read_text(encoding="utf-8-sig"))
            py = cfg.get("pythonPath")
            if py and Path(py).exists():
                return str(Path(py))
        except Exception:
            pass
    sibling = Path(sys.executable).with_name("python.exe")
    if sibling.exists():
        return str(sibling)
    return "python"


class SNNUService(win32serviceutil.ServiceFramework):
    _svc_name_ = "SNNUWifiKeepalive"
    _svc_display_name_ = "SNNU Wi-Fi Keepalive"
    _svc_description_ = "Keep SNNU Wi-Fi connected and auto-login to portal."

    def __init__(self, args):
        super().__init__(args)
        self.hWaitStop = win32event.CreateEvent(None, 0, 0, None)
        self.proc: subprocess.Popen[str] | None = None

    def SvcStop(self):
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        win32event.SetEvent(self.hWaitStop)
        self._stop_child()

    def SvcDoRun(self):
        servicemanager.LogInfoMsg("SNNUWifiKeepalive service starting.")
        self._start_child()
        while True:
            rc = win32event.WaitForSingleObject(self.hWaitStop, 1000)
            if rc == win32event.WAIT_OBJECT_0:
                break
            if self.proc and self.proc.poll() is not None:
                servicemanager.LogInfoMsg("Child process exited. Restarting...")
                time.sleep(2)
                self._start_child()
        self._stop_child()
        servicemanager.LogInfoMsg("SNNUWifiKeepalive service stopped.")

    def _start_child(self):
        if self.proc and self.proc.poll() is None:
            return
        root = repo_root()
        script = root / "web" / "keepalive.py"
        cfg = root / "config" / "snnu-config.json"
        cmd = [
            resolve_python(root),
            str(script),
            "--config",
            str(cfg),
        ]
        self.proc = subprocess.Popen(
            cmd,
            cwd=str(root),
            creationflags=subprocess.CREATE_NO_WINDOW,
        )

    def _stop_child(self):
        if not self.proc:
            return
        if self.proc.poll() is None:
            try:
                subprocess.run(
                    ["taskkill", "/PID", str(self.proc.pid), "/T", "/F"],
                    capture_output=True,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
            except Exception:
                pass
        self.proc = None


if __name__ == "__main__":
    if len(sys.argv) == 1:
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(SNNUService)
        servicemanager.StartServiceCtrlDispatcher()
    else:
        win32serviceutil.HandleCommandLine(SNNUService)
