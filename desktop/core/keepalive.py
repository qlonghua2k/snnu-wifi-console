from __future__ import annotations

import argparse
import json
import locale
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

try:
    from .auth_client import (
        LOGIN_FAILED as AUTH_LOGIN_FAILED,
        MISSING_CREDENTIALS as AUTH_MISSING_CREDENTIALS,
        NEED_LOGIN as AUTH_NEED_LOGIN,
        NO_IP as AUTH_NO_IP,
        NOT_SNNU_WIFI as AUTH_NOT_SNNU_WIFI,
        ONLINE as AUTH_ONLINE,
        PORTAL_UNREACHABLE as AUTH_PORTAL_UNREACHABLE,
        WRONG_PASSWORD as AUTH_WRONG_PASSWORD,
        AuthInput,
        auth_templates_from_config,
        check_connectivity,
        ensure_online,
    )
    from .portal import load_config
except ImportError:
    from auth_client import (  # type: ignore
        LOGIN_FAILED as AUTH_LOGIN_FAILED,
        MISSING_CREDENTIALS as AUTH_MISSING_CREDENTIALS,
        NEED_LOGIN as AUTH_NEED_LOGIN,
        NO_IP as AUTH_NO_IP,
        NOT_SNNU_WIFI as AUTH_NOT_SNNU_WIFI,
        ONLINE as AUTH_ONLINE,
        PORTAL_UNREACHABLE as AUTH_PORTAL_UNREACHABLE,
        WRONG_PASSWORD as AUTH_WRONG_PASSWORD,
        AuthInput,
        auth_templates_from_config,
        check_connectivity,
        ensure_online,
    )
    from portal import load_config


CONNECTED_RE = re.compile(r"connected|已连接", re.I)
DISCONNECTED_RE = re.compile(r"disconnected|断开连接|未连接", re.I)
WIFI_DESC_RE = re.compile(r"Wireless|Wi-Fi|WLAN", re.I)
MOJIBAKE_RE = re.compile(r"[锟�]|[鎴鏂鐢绾缃杩][\u3000-\u9fff]")


def repo_root() -> Path:
    override = os.environ.get("SNNU_REPO_ROOT")
    if override:
        return Path(override)
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def bundle_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", repo_root()))
    return repo_root()


def ensure_config_file(path: Path) -> None:
    if path.exists():
        return
    template_candidates = [
        bundle_root() / "config" / "snnu-config.example.json",
        repo_root() / "config" / "snnu-config.example.json",
    ]
    for template in template_candidates:
        if template.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(template.read_text(encoding="utf-8"), encoding="utf-8")
            return
    raise FileNotFoundError(f"Config file not found and template is missing: {path}")


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


def output_encodings() -> list[str]:
    encodings = ["utf-8-sig", "utf-8"]
    preferred = locale.getpreferredencoding(False)
    if preferred:
        encodings.append(preferred)
    if os.name == "nt":
        encodings.extend(["mbcs", "oem"])
    encodings.append("gb18030")
    return list(dict.fromkeys(encodings))


def decode_output(data: bytes) -> str:
    if not data:
        return ""

    candidates: list[tuple[int, str]] = []
    for encoding in output_encodings():
        try:
            text = data.decode(encoding)
        except (LookupError, UnicodeDecodeError):
            continue
        penalty = text.count("\ufffd") * 100
        penalty += len(MOJIBAKE_RE.findall(text)) * 20
        candidates.append((penalty, text))

    if candidates:
        candidates.sort(key=lambda item: item[0])
        return candidates[0][1]

    return data.decode(locale.getpreferredencoding(False) or "utf-8", errors="replace")


def run_command(cmd: list[str], timeout: int = 30) -> subprocess.CompletedProcess[str]:
    kwargs: dict[str, Any] = {
        "capture_output": True,
        "timeout": timeout,
    }
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    result = subprocess.run(cmd, **kwargs)
    return subprocess.CompletedProcess(
        result.args,
        result.returncode,
        decode_output(result.stdout or b""),
        decode_output(result.stderr or b""),
    )


def run_powershell(script: str, timeout: int = 30) -> subprocess.CompletedProcess[str]:
    return run_command([powershell_path(), "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script], timeout)


def parse_json_output(output: str) -> Any:
    text = (output or "").strip()
    if not text:
        return None
    return json.loads(text)


def now_iso() -> str:
    return datetime.now().astimezone().isoformat()


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


def keepalive_process_exists(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name != "nt":
        return process_exists(pid)
    script = (
        f"$p = Get-CimInstance Win32_Process -Filter \"ProcessId = {pid}\" -ErrorAction SilentlyContinue; "
        "if ($p) { $p.CommandLine }"
    )
    try:
        result = run_powershell(script, timeout=10)
    except Exception:
        return False
    command_line = result.stdout or ""
    return "--keepalive" in command_line or "keepalive.py" in command_line


class KeepaliveManager:
    def __init__(self, config_path: Path | str | None = None):
        self.root = repo_root()
        self.config_path = self.resolve_config_path(config_path)
        ensure_config_file(self.config_path)
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
        config.setdefault("connectivityTimeoutSeconds", 4)
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
        adapter: str | None = None,
        ssid: str | None = None,
        ip: str | None = None,
        gateway: str | None = None,
        connectivity_ok: bool | None = None,
    ) -> None:
        state["lastState"] = new_state
        state["lastError"] = error_message
        if adapter is not None:
            state["lastAdapter"] = adapter
        if ssid is not None:
            state["lastSsid"] = ssid
        if ip is not None:
            state["lastIp"] = ip
        if gateway is not None:
            state["lastGateway"] = gateway
        if connectivity_ok is not None:
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

    @staticmethod
    def is_connected_wlan(wlan: dict[str, Any] | None) -> bool:
        if not wlan:
            return False
        state = str(wlan.get("State", ""))
        if state and CONNECTED_RE.search(state):
            return bool(str(wlan.get("Ssid", "")).strip())
        if state and DISCONNECTED_RE.search(state):
            return False
        return bool(str(wlan.get("Ssid", "")).strip())

    def wlan_state(self, interface_name: str = "") -> dict[str, Any] | None:
        try:
            result = run_command(["netsh", "wlan", "show", "interfaces"], timeout=20)
        except Exception:
            return None
        output = result.stdout or ""
        if not output.strip():
            return None

        interfaces: list[dict[str, Any]] = []
        current: dict[str, Any] = {"Name": "", "State": "", "Ssid": "", "Profile": "", "RadioSoftwareOff": False}
        for line in output.splitlines():
            m = re.match(r"^\s*(Name|名称|接口名称)\s*:\s*(.+)$", line, re.I)
            if m:
                if any(current.values()):
                    interfaces.append(current)
                    current = {"Name": "", "State": "", "Ssid": "", "Profile": "", "RadioSoftwareOff": False}
                current["Name"] = m.group(2).strip()
                continue

            m = re.match(r"^\s*(State|状态)\s*:\s*(.+)$", line, re.I)
            if m:
                current["State"] = m.group(2).strip()
                continue

            m = re.match(r"^\s*SSID\s*:\s*(.+)$", line)
            if m:
                current["Ssid"] = m.group(1).strip()
                continue

            m = re.match(r"^\s*(Profile|配置文件)\s*:\s*(.+)$", line, re.I)
            if m:
                current["Profile"] = m.group(2).strip()
                continue

            if re.search(r"Software\s+Off|软件\s*关闭|无线\s*电源\s*已关闭", line, re.I):
                current["RadioSoftwareOff"] = True

        if any(current.values()):
            interfaces.append(current)
        if not interfaces:
            return None
        if interface_name:
            for item in interfaces:
                if item.get("Name") == interface_name:
                    return item
        for item in interfaces:
            if self.is_connected_wlan(item):
                return item
        return interfaces[0]

    def wlan_profiles(self) -> list[str]:
        try:
            result = run_command(["netsh", "wlan", "show", "profiles"], timeout=20)
        except Exception:
            return []
        profiles = []
        for line in (result.stdout or "").splitlines():
            m = re.search(r"(All User Profile|所有用户配置文件|用户配置文件)\s*:\s*(.+)$", line, re.I)
            if m:
                profiles.append(m.group(2).strip())
        return profiles

    def all_user_profile(self, profile: str) -> bool:
        return bool(profile) and profile in self.wlan_profiles()

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
        timeout = float(self.config.get("connectivityTimeoutSeconds", 4) or 4)
        return check_connectivity(self.config.get("connectivityChecks", []), timeout)

    def status(self) -> dict[str, Any]:
        adapter = self.wifi_adapter()
        wlan = self.wlan_state(adapter.get("Name", "")) if adapter else None
        ip = self.ip_status(adapter.get("Name", "")) if adapter else {"IP": "", "Gateway": ""}
        try:
            internet_ok = self.test_connectivity()
        except Exception:
            internet_ok = False
        state = self.load_state()
        profile_name = self.config.get("profileName") or self.config.get("ssid", "")
        target_ssid = str(self.config.get("ssid", "SNNU"))
        connected_wlan = bool(wlan and self.is_connected_wlan(wlan))
        connected_to_target = bool(connected_wlan and wlan and wlan.get("Ssid") == target_ssid)
        connectivity_ok = bool(connected_to_target and internet_ok)
        if connectivity_ok:
            last_state = "ONLINE"
            last_error = ""
        elif connected_wlan and wlan and wlan.get("Ssid") != target_ssid:
            last_state = "OTHER_SSID"
            last_error = ""
        elif not connected_to_target:
            last_state = "DISCONNECTED"
            last_error = ""
        else:
            last_state = state.get("lastState", "") or "CONNECTED_NO_NET"
            last_error = state.get("lastError", "")
        return {
            "adapter": adapter.get("Name", "") if adapter else "",
            "adapterStatus": adapter.get("Status", "") if adapter else "",
            "wlanState": wlan.get("State", "") if wlan else "",
            "ssid": wlan.get("Ssid", "") if wlan else "",
            "ip": ip.get("IP", ""),
            "gateway": ip.get("Gateway", ""),
            "connectivityOk": connectivity_ok,
            "internetOk": internet_ok,
            "connectedToTarget": connected_to_target,
            "lastState": last_state,
            "lastError": last_error,
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

        adapter = self.wifi_adapter()
        if not adapter:
            self.update_state(state, "NO_ADAPTER", "Wi-Fi adapter not found.", adapter="", ssid="", ip="", gateway="", connectivity_ok=False)
            self.save_state(state)
            self.log("Wi-Fi adapter not found.", "ERROR")
            return

        adapter_name = str(adapter.get("Name", ""))
        wlan = self.wlan_state(adapter_name)
        current_ssid = str((wlan or {}).get("Ssid", ""))
        target_ssid = str(config.get("ssid", "SNNU"))
        ip = self.ip_status(adapter_name)
        creds = config.get("credentials") or {}
        options = config.get("portalOptions") or {}
        network_type = str(options.get("networkType") or options.get("isp") or "campus")

        next_login_after = state.get("nextLoginAfter")
        if next_login_after:
            try:
                next_time = datetime.fromisoformat(str(next_login_after))
                if now < next_time:
                    self.update_state(state, "LOGIN_COOLDOWN", "Cooldown active.", connectivity_ok=False)
                    self.save_state(state)
                    self.log(f"Login cooldown active until {next_time.strftime('%H:%M:%S')}")
                    return
            except ValueError:
                pass

        auth = AuthInput(
            target_ssid=target_ssid,
            current_ssid=current_ssid,
            ip=ip.get("IP", ""),
            username=str(creds.get("username", "")),
            password=str(creds.get("password", "")),
            network_type=network_type,
        )
        templates = auth_templates_from_config(config)
        timeout = float(config.get("connectivityTimeoutSeconds", 4) or 4)
        result = ensure_online(auth, templates, config.get("connectivityChecks", []), timeout=timeout)
        state["lastLoginAttempt"] = now_iso()

        state_name = {
            AUTH_ONLINE: "ONLINE",
            AUTH_NOT_SNNU_WIFI: "OTHER_SSID" if current_ssid else "DISCONNECTED",
            AUTH_NO_IP: "CONNECTED_NO_NET",
            AUTH_MISSING_CREDENTIALS: "MISSING_CREDENTIALS",
            AUTH_NEED_LOGIN: "NEEDS_LOGIN",
            AUTH_WRONG_PASSWORD: "WRONG_PASSWORD",
            AUTH_LOGIN_FAILED: "LOGIN_FAILED",
            AUTH_PORTAL_UNREACHABLE: "LOGIN_FAILED",
        }.get(result.status, "UNKNOWN")

        if result.status == AUTH_ONLINE:
            self.update_state(
                state,
                state_name,
                adapter=adapter_name,
                ssid=current_ssid,
                ip=ip.get("IP", ""),
                gateway=ip.get("Gateway", ""),
                connectivity_ok=True,
            )
            state["lastOnline"] = now_iso()
            state["lastLoginSuccess"] = now_iso()
            state["currentCooldownSeconds"] = int(config.get("loginCooldownSeconds", 60))
            state["nextLoginAfter"] = ""
            self.log(f"Auth OK. {result.message}")
        else:
            self.update_state(
                state,
                state_name,
                result.message,
                adapter=adapter_name,
                ssid=current_ssid,
                ip=ip.get("IP", ""),
                gateway=ip.get("Gateway", ""),
                connectivity_ok=False,
            )
            current = int(state.get("currentCooldownSeconds") or config.get("loginCooldownSeconds", 60))
            max_cooldown = int(config.get("loginMaxCooldownSeconds", 600))
            if result.status in {AUTH_LOGIN_FAILED, AUTH_PORTAL_UNREACHABLE, AUTH_NEED_LOGIN}:
                state["currentCooldownSeconds"] = min(max(current * 2, 1), max_cooldown)
                state["nextLoginAfter"] = (now + timedelta(seconds=int(state["currentCooldownSeconds"]))).isoformat()
            elif result.status == AUTH_WRONG_PASSWORD:
                state["currentCooldownSeconds"] = max_cooldown
                state["nextLoginAfter"] = (now + timedelta(seconds=max_cooldown)).isoformat()
            else:
                state["nextLoginAfter"] = ""
            self.log(f"Auth state: {result.status}. {result.message}", "WARN")
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
            if not keepalive_process_exists(old_pid):
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
