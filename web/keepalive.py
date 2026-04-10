from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

from portal import attempt_portal_login, load_config


CONNECTED_RE = re.compile(r"connected|已连接", re.I)
WIFI_DESC_RE = re.compile(r"Wireless|Wi-Fi|WLAN", re.I)


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def powershell_path() -> str:
    windir = os.environ.get("WINDIR", r"C:\Windows")
    return str(Path(windir) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe")


def resolve_path(root: Path, value: str, default_rel: str) -> Path:
    if not value:
        return root / default_rel
    path = Path(value)
    if path.is_absolute():
        return path
    return root / path


def run_command(cmd: list[str], timeout: int = 30) -> subprocess.CompletedProcess[str]:
    kwargs: dict[str, Any] = {
        "capture_output": True,
        "text": True,
        "errors": "replace",
        "timeout": timeout,
    }
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    return subprocess.run(cmd, **kwargs)


def run_powershell(script: str, timeout: int = 30) -> subprocess.CompletedProcess[str]:
    return run_command([powershell_path(), "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script], timeout)


def parse_json_output(output: str) -> Any:
    text = (output or "").strip()
    if not text:
        return None
    return json.loads(text)


def now_iso() -> str:
    return datetime.now().astimezone().isoformat()


def is_admin() -> bool:
    if os.name != "nt":
        return os.geteuid() == 0
    try:
        import ctypes

        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def process_exists(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        result = run_command(["tasklist", "/FI", f"PID eq {pid}", "/NH"], timeout=10)
        return str(pid) in (result.stdout or "")
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


class KeepaliveManager:
    def __init__(self, config_path: Path | str | None = None):
        self.root = repo_root()
        self.config_path = self.resolve_config_path(config_path)
        self.config = self.ensure_config_defaults(load_config(self.config_path))
        self.log_path = resolve_path(self.root, self.config.get("logPath", ""), "logs/wifi-keepalive.log")
        self.state_path = resolve_path(self.root, self.config.get("statePath", ""), "logs/state.json")
        self.trigger_path = resolve_path(self.root, self.config.get("triggerPath", ""), "logs/trigger.once")
        self.log_rotate_bytes = int(self.config.get("logRotateMB", 5)) * 1024 * 1024
        self.log_rotate_keep = int(self.config.get("logRotateKeep", 3))

    def resolve_config_path(self, config_path: Path | str | None) -> Path:
        if not config_path:
            return self.root / "config" / "snnu-config.json"
        path = Path(config_path)
        if path.is_absolute():
            return path
        return self.root / path

    def ensure_config_defaults(self, config: dict[str, Any]) -> dict[str, Any]:
        config.setdefault("intervalSeconds", 60)
        config.setdefault("loginCooldownSeconds", 60)
        config.setdefault("loginMaxCooldownSeconds", 600)
        config.setdefault("logRotateMB", 5)
        config.setdefault("logRotateKeep", 3)
        config.setdefault("statePath", "logs\\state.json")
        config.setdefault("triggerPath", "logs\\trigger.once")
        config.setdefault("connectivityChecks", [])
        config.setdefault("credentials", {})
        config.setdefault("portalOptions", {})
        return config

    def rotate_log(self) -> None:
        if self.log_rotate_bytes <= 0 or not self.log_path.exists():
            return
        if self.log_path.stat().st_size < self.log_rotate_bytes:
            return
        for index in range(self.log_rotate_keep - 1, 0, -1):
            src = Path(f"{self.log_path}.{index}")
            dst = Path(f"{self.log_path}.{index + 1}")
            if src.exists():
                if dst.exists():
                    dst.unlink()
                src.rename(dst)
        dst = Path(f"{self.log_path}.1")
        if dst.exists():
            dst.unlink()
        self.log_path.rename(dst)

    def log(self, message: str, level: str = "INFO") -> None:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{timestamp}][{level}] {message}"
        print(line, flush=True)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.rotate_log()
        with self.log_path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    def default_state(self) -> dict[str, Any]:
        return {
            "lastState": "INIT",
            "lastError": "",
            "lastLoginAttempt": "",
            "lastLoginSuccess": "",
            "lastOnline": "",
            "currentCooldownSeconds": int(self.config.get("loginCooldownSeconds", 60)),
            "nextLoginAfter": "",
            "lastAdapter": "",
            "lastSsid": "",
            "lastIp": "",
            "lastGateway": "",
            "lastPortal": "",
            "lastConnectivityOk": False,
        }

    def load_state(self) -> dict[str, Any]:
        if not self.state_path.exists():
            return self.default_state()
        try:
            state = json.loads(self.state_path.read_text(encoding="utf-8"))
        except Exception:
            return self.default_state()
        if not isinstance(state, dict):
            return self.default_state()
        state.setdefault("currentCooldownSeconds", int(self.config.get("loginCooldownSeconds", 60)))
        return state

    def save_state(self, state: dict[str, Any]) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    def update_state(
        self,
        state: dict[str, Any],
        new_state: str,
        error_message: str = "",
        adapter: str = "",
        ssid: str = "",
        ip: str = "",
        gateway: str = "",
        connectivity_ok: bool = False,
    ) -> None:
        state["lastState"] = new_state
        if error_message:
            state["lastError"] = error_message
        if adapter:
            state["lastAdapter"] = adapter
        if ssid:
            state["lastSsid"] = ssid
        if ip:
            state["lastIp"] = ip
        if gateway:
            state["lastGateway"] = gateway
        state["lastConnectivityOk"] = connectivity_ok

    def adapter_list(self) -> list[dict[str, Any]]:
        script = (
            "Get-NetAdapter -Physical -ErrorAction SilentlyContinue | "
            "Select-Object Name,Status,InterfaceDescription,NdisPhysicalMedium | ConvertTo-Json -Depth 4"
        )
        try:
            result = run_powershell(script)
            data = parse_json_output(result.stdout)
        except Exception:
            return []
        if data is None:
            return []
        if isinstance(data, dict):
            rows = [data]
        else:
            rows = data
        adapters = []
        for row in rows:
            medium = str(row.get("NdisPhysicalMedium", ""))
            desc = str(row.get("InterfaceDescription", ""))
            adapters.append(
                {
                    "Name": row.get("Name", ""),
                    "Status": row.get("Status", ""),
                    "Description": desc,
                    "IsWireless": medium == "Native 802.11" or bool(WIFI_DESC_RE.search(desc)),
                }
            )
        return adapters

    def wifi_adapter(self) -> dict[str, Any] | None:
        preferred = str(self.config.get("adapterName") or "")
        adapters = self.adapter_list()
        if preferred:
            for adapter in adapters:
                if adapter.get("Name") == preferred:
                    return adapter
        for adapter in adapters:
            if adapter.get("IsWireless"):
                return adapter
        return None

    def ensure_adapter_enabled(self, adapter: dict[str, Any]) -> bool:
        if adapter.get("Status") != "Disabled":
            return True
        name = str(adapter.get("Name", ""))
        self.log(f"Adapter {name} is disabled. Enabling...", "WARN")
        escaped = name.replace("'", "''")
        result = run_powershell(f"Enable-NetAdapter -Name '{escaped}' -Confirm:$false -ErrorAction Stop", timeout=20)
        if result.returncode == 0:
            time.sleep(3)
            return True
        self.log("Failed to enable adapter. Admin permission may be required.", "ERROR")
        return False

    def ensure_autoconfig(self, interface_name: str) -> None:
        if not interface_name:
            return
        run_command(["netsh", "wlan", "set", "autoconfig", "enabled=yes", f"interface={interface_name}"], timeout=15)

    def wlan_state(self, interface_name: str = "") -> dict[str, Any] | None:
        try:
            result = run_command(["netsh", "wlan", "show", "interfaces"], timeout=20)
        except Exception:
            return None
        output = result.stdout or ""
        if not output.strip():
            return None
        state = ""
        ssid = ""
        profile = ""
        radio_off = False
        for line in output.splitlines():
            m = re.match(r"^\s*(State|状态)\s*:\s*(.+)$", line)
            if m:
                state = m.group(2).strip()
            m = re.match(r"^\s*SSID\s*:\s*(.+)$", line)
            if m:
                ssid = m.group(1).strip()
            m = re.match(r"^\s*(Profile|配置文件)\s*:\s*(.+)$", line)
            if m:
                profile = m.group(2).strip()
            if re.search(r"Software\s+Off|软件\s*关闭|无线\s*电源\s*已关闭", line, re.I):
                radio_off = True
        return {"State": state, "Ssid": ssid, "Profile": profile, "RadioSoftwareOff": radio_off}

    def wlan_profiles(self) -> list[str]:
        try:
            result = run_command(["netsh", "wlan", "show", "profiles"], timeout=20)
        except Exception:
            return []
        profiles = []
        for line in (result.stdout or "").splitlines():
            m = re.search(r"(All User Profile|所有用户配置文件)\s*:\s*(.+)$", line)
            if m:
                profiles.append(m.group(2).strip())
        return profiles

    def all_user_profile(self, profile: str) -> bool:
        return bool(profile) and profile in self.wlan_profiles()

    def connect_to_ssid(self, ssid: str, profile_name: str = "", interface_name: str = "") -> bool:
        if not ssid:
            return False
        name_to_use = profile_name or ssid
        if name_to_use not in self.wlan_profiles():
            self.log(f"Wi-Fi profile not found: {name_to_use}. Connect once manually to create it.", "WARN")
            return False
        self.log(f"Connecting to SSID {ssid} (profile {name_to_use})...", "INFO")
        cmd = ["netsh", "wlan", "connect", f"name={name_to_use}", f"ssid={ssid}"]
        if interface_name:
            cmd.append(f"interface={interface_name}")
        try:
            result = run_command(cmd, timeout=20)
            time.sleep(5)
            return result.returncode == 0
        except Exception as exc:
            self.log(f"Failed to connect to {ssid}. {exc}", "ERROR")
            return False

    def disconnect_wifi(self, interface_name: str = "") -> None:
        cmd = ["netsh", "wlan", "disconnect"]
        if interface_name:
            cmd.append(f"interface={interface_name}")
        try:
            run_command(cmd, timeout=15)
        except Exception:
            return

    def ip_status(self, interface_alias: str) -> dict[str, str]:
        if not interface_alias:
            return {"IP": "", "Gateway": ""}
        escaped = interface_alias.replace("'", "''")
        script = (
            f"$cfg = Get-NetIPConfiguration -InterfaceAlias '{escaped}' -ErrorAction SilentlyContinue; "
            "if ($cfg) { $cfg | Select-Object "
            "@{n='IP';e={($_.IPv4Address.IPAddress -join ',')}},"
            "@{n='Gateway';e={($_.IPv4DefaultGateway.NextHop -join ',')}} | ConvertTo-Json -Depth 3 }"
        )
        try:
            result = run_powershell(script)
            data = parse_json_output(result.stdout)
        except Exception:
            return {"IP": "", "Gateway": ""}
        if not isinstance(data, dict):
            return {"IP": "", "Gateway": ""}
        return {"IP": str(data.get("IP") or ""), "Gateway": str(data.get("Gateway") or "")}

    def test_connectivity(self) -> bool:
        for check in self.config.get("connectivityChecks", []):
            url = check.get("url")
            if not url:
                continue
            try:
                resp = requests.get(url, timeout=8, allow_redirects=False)
            except Exception:
                continue
            expected_status = check.get("expectStatus")
            if expected_status and resp.status_code != expected_status:
                continue
            expected_body = check.get("expectBody")
            if expected_body and expected_body not in resp.text:
                continue
            if urlparse(resp.url).hostname == "202.117.144.205":
                continue
            return True
        return False

    def portal_login(self) -> bool:
        portals = self.config.get("portals", [])
        if not portals:
            self.log("Portal login: no portal configured.", "ERROR")
            return False
        creds = self.config.get("credentials") or {}
        username = creds.get("username", "")
        password = creds.get("password", "")
        if not username or not password:
            self.log("Portal login: missing credentials.", "ERROR")
            return False
        for portal in portals:
            name = portal.get("name")
            self.log(f"Portal login attempt: {name}")
            debug_path = self.root / "logs" / f"portal-{name or 'portal'}-last.html"
            ok, msg, info = attempt_portal_login(
                portal=portal,
                username=username,
                password=password,
                portal_options=self.config.get("portalOptions", {}),
                timeout=10,
                debug=True,
                debug_path=debug_path,
            )
            result = {
                "ok": ok,
                "message": msg,
                "portal": name,
                "info": {
                    "action_url": info.get("action_url"),
                    "username_field": info.get("username_field"),
                    "password_field": info.get("password_field"),
                    "inputs": info.get("inputs", []),
                },
            }
            self.log(f"Portal login output: {json.dumps(result, ensure_ascii=False)}", "INFO" if ok else "WARN")
            if ok:
                self.log(f"Portal login success: {name} ({msg})")
                return True
            self.log(f"Portal login failed: {name} ({msg})", "WARN")
        self.log("Portal login failed on all portals.", "ERROR")
        return False

    def status(self) -> dict[str, Any]:
        adapter = self.wifi_adapter()
        wlan = self.wlan_state(adapter.get("Name", "")) if adapter else None
        ip = self.ip_status(adapter.get("Name", "")) if adapter else {"IP": "", "Gateway": ""}
        try:
            connectivity_ok = self.test_connectivity()
        except Exception:
            connectivity_ok = False
        state = self.load_state()
        profile_name = self.config.get("profileName") or self.config.get("ssid", "")
        return {
            "adapter": adapter.get("Name", "") if adapter else "",
            "adapterStatus": adapter.get("Status", "") if adapter else "",
            "wlanState": wlan.get("State", "") if wlan else "",
            "ssid": wlan.get("Ssid", "") if wlan else "",
            "ip": ip.get("IP", ""),
            "gateway": ip.get("Gateway", ""),
            "connectivityOk": connectivity_ok,
            "lastState": state.get("lastState", ""),
            "lastError": state.get("lastError", ""),
            "lastLoginAttempt": state.get("lastLoginAttempt", ""),
            "lastLoginSuccess": state.get("lastLoginSuccess", ""),
            "lastOnline": state.get("lastOnline", ""),
            "currentCooldownSeconds": state.get("currentCooldownSeconds", ""),
            "nextLoginAfter": state.get("nextLoginAfter", ""),
            "adapters": self.adapter_list(),
            "allUserProfile": self.all_user_profile(profile_name),
        }

    def run_once(self) -> None:
        config = self.config
        state = self.load_state()
        now = datetime.now().astimezone()
        admin = is_admin()

        try:
            run_powershell(
                "$svc = Get-Service -Name WlanSvc -ErrorAction SilentlyContinue; "
                "if ($svc -and $svc.Status -ne 'Running') { Start-Service -Name WlanSvc -ErrorAction SilentlyContinue }",
                timeout=15,
            )
        except Exception:
            pass

        adapter = self.wifi_adapter()
        if not adapter:
            self.update_state(state, "NO_ADAPTER", "Wi-Fi adapter not found.")
            self.save_state(state)
            self.log("Wi-Fi adapter not found.", "ERROR")
            return

        adapter_name = str(adapter.get("Name", ""))
        if not self.ensure_adapter_enabled(adapter):
            self.update_state(state, "NEEDS_ADMIN", "Adapter disabled. Admin required.", adapter=adapter_name)
            self.save_state(state)
            return
        self.ensure_autoconfig(adapter_name)

        wlan = self.wlan_state(adapter_name)
        if wlan and wlan.get("RadioSoftwareOff"):
            self.log("Wi-Fi radio is off. Attempting to enable...", "WARN")
            if admin:
                escaped = adapter_name.replace("'", "''")
                run_powershell(f"Enable-NetAdapter -Name '{escaped}' -Confirm:$false -ErrorAction SilentlyContinue", timeout=20)
                run_command(["netsh", "interface", "set", "interface", f"name={adapter_name}", "admin=enabled"], timeout=15)
                time.sleep(3)
                wlan = self.wlan_state(adapter_name)
            if wlan and wlan.get("RadioSoftwareOff"):
                self.update_state(state, "RADIO_OFF", "Wi-Fi radio is off.", adapter=adapter_name)
                self.save_state(state)
                self.log("Wi-Fi radio is off. Please enable Wi-Fi manually.", "WARN")
                return

        is_connected = bool(wlan and CONNECTED_RE.search(str(wlan.get("State", ""))) and str(wlan.get("Ssid", "")).strip())
        target_ssid = str(config.get("ssid", "SNNU"))

        if is_connected and wlan and wlan.get("Ssid") != target_ssid:
            previous_state = state.get("lastState")
            previous_ssid = state.get("lastSsid")
            self.update_state(state, "OTHER_SSID", adapter=adapter_name, ssid=str(wlan.get("Ssid", "")))
            self.save_state(state)
            if previous_state != "OTHER_SSID" or previous_ssid != wlan.get("Ssid"):
                self.log(f"Connected to other SSID ({wlan.get('Ssid')}). No action.")
            return

        if not is_connected:
            self.update_state(state, "DISCONNECTED", adapter=adapter_name, ssid=str((wlan or {}).get("Ssid", "")))
            self.connect_to_ssid(target_ssid, str(config.get("profileName", "")), adapter_name)
            wlan = self.wlan_state(adapter_name)
            is_connected = bool(wlan and CONNECTED_RE.search(str(wlan.get("State", ""))))

        ip = self.ip_status(adapter_name)
        connectivity_ok = self.test_connectivity()
        connected_to_target = bool(
            wlan and CONNECTED_RE.search(str(wlan.get("State", ""))) and wlan.get("Ssid") == target_ssid
        )

        if connectivity_ok:
            self.update_state(
                state,
                "ONLINE",
                adapter=adapter_name,
                ssid=str((wlan or {}).get("Ssid", "")),
                ip=ip.get("IP", ""),
                gateway=ip.get("Gateway", ""),
                connectivity_ok=True,
            )
            state["lastOnline"] = now_iso()
            state["currentCooldownSeconds"] = int(config.get("loginCooldownSeconds", 60))
            state["nextLoginAfter"] = ""
            self.save_state(state)
            self.log("Connectivity OK.")
            return

        if connected_to_target:
            self.update_state(
                state,
                "CONNECTED_NO_NET",
                adapter=adapter_name,
                ssid=str((wlan or {}).get("Ssid", "")),
                ip=ip.get("IP", ""),
                gateway=ip.get("Gateway", ""),
            )
            self.log(f"Connected to {target_ssid} but no internet. Will re-login.", "WARN")
        else:
            self.update_state(
                state,
                "DISCONNECTED",
                adapter=adapter_name,
                ssid=str((wlan or {}).get("Ssid", "")),
                ip=ip.get("IP", ""),
                gateway=ip.get("Gateway", ""),
            )
            self.save_state(state)
            self.log("Not connected to target SSID. Skip portal login.")
            return

        creds = config.get("credentials") or {}
        if not creds.get("username") or not creds.get("password"):
            self.update_state(state, "MISSING_CREDENTIALS", "Missing credentials in config.")
            self.save_state(state)
            self.log("Missing credentials in config. Run set-credentials.ps1.", "ERROR")
            return

        next_login_after = state.get("nextLoginAfter")
        if next_login_after:
            try:
                next_time = datetime.fromisoformat(str(next_login_after))
                if now < next_time:
                    self.update_state(state, "LOGIN_COOLDOWN", "Cooldown active.")
                    self.save_state(state)
                    self.log(f"Login cooldown active until {next_time.strftime('%H:%M:%S')}")
                    return
            except ValueError:
                pass

        self.log("Attempting portal login via Python...")
        login_ok = self.portal_login()
        state["lastLoginAttempt"] = now_iso()
        if login_ok:
            state["lastLoginSuccess"] = now_iso()
            state["currentCooldownSeconds"] = int(config.get("loginCooldownSeconds", 60))
        else:
            current = int(state.get("currentCooldownSeconds") or config.get("loginCooldownSeconds", 60))
            max_cooldown = int(config.get("loginMaxCooldownSeconds", 600))
            state["currentCooldownSeconds"] = min(max(current * 2, 1), max_cooldown)

        state["nextLoginAfter"] = (now + timedelta(seconds=int(state["currentCooldownSeconds"]))).isoformat()

        time.sleep(3)
        connectivity_ok = self.test_connectivity()
        if connectivity_ok:
            self.update_state(
                state,
                "ONLINE",
                adapter=adapter_name,
                ssid=str((wlan or {}).get("Ssid", "")),
                ip=ip.get("IP", ""),
                gateway=ip.get("Gateway", ""),
                connectivity_ok=True,
            )
            state["lastOnline"] = now_iso()
            self.log("Connectivity restored after portal login.")
        else:
            if connected_to_target:
                self.log("Still offline. Disconnecting and reconnecting Wi-Fi...", "WARN")
                self.disconnect_wifi(adapter_name)
                time.sleep(2)
                self.connect_to_ssid(target_ssid, str(config.get("profileName", "")), adapter_name)
            error = "Connectivity still failing." if login_ok else "Portal login failed."
            self.update_state(
                state,
                "LOGIN_FAILED",
                error,
                adapter=adapter_name,
                ssid=str((wlan or {}).get("Ssid", "")),
                ip=ip.get("IP", ""),
                gateway=ip.get("Gateway", ""),
            )
            self.log("Connectivity still failing. Will retry.", "WARN")
        self.save_state(state)

    def test_trigger(self) -> bool:
        if not self.trigger_path.exists():
            return False
        try:
            self.trigger_path.unlink()
        except Exception:
            pass
        return True

    def sleep_with_trigger(self, seconds: int) -> bool:
        for _ in range(max(seconds, 0)):
            time.sleep(1)
            if self.test_trigger():
                return True
        return False

    def lock_path(self) -> Path:
        return self.state_path.parent / "wifi-keepalive.lock"

    def acquire_lock(self) -> int | None:
        path = self.lock_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            try:
                old_pid = int(path.read_text(encoding="utf-8").strip() or "0")
            except ValueError:
                old_pid = 0
            if not process_exists(old_pid):
                try:
                    path.unlink()
                except Exception:
                    pass
        try:
            fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            return None
        os.write(fd, str(os.getpid()).encode("utf-8"))
        return fd

    def release_lock(self, fd: int) -> None:
        try:
            os.close(fd)
        except Exception:
            pass
        try:
            self.lock_path().unlink()
        except Exception:
            pass

    def run_forever(self) -> None:
        lock_fd = self.acquire_lock()
        if lock_fd is None:
            self.log("Another instance is already running. Exiting.", "WARN")
            return
        self.log("SNNU Wi-Fi keepalive started.")
        try:
            while True:
                try:
                    self.run_once()
                except Exception as exc:
                    self.log(str(exc), "ERROR")
                if self.sleep_with_trigger(int(self.config.get("intervalSeconds", 60))):
                    self.log("Trigger received. Running immediate cycle.")
        finally:
            self.release_lock(lock_fd)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--status", action="store_true")
    args = parser.parse_args()

    manager = KeepaliveManager(args.config or None)
    if args.status:
        print(json.dumps(manager.status(), ensure_ascii=False))
        return 0
    if args.once:
        manager.run_once()
        return 0
    manager.run_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
