from __future__ import annotations

import json
import os
import secrets
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, redirect, render_template, request, url_for
import requests

from keepalive import KeepaliveManager
from portal import attempt_portal_login, debug_info

APP_PORT = int(os.environ.get("SNNU_WEB_PORT", "8608"))
SERVICE_NAME = os.environ.get("SNNU_SERVICE_NAME", "SNNUWifiKeepalive")
HELPER_NAME = os.environ.get("SNNU_HELPER_NAME", "SNNUAdminHelper")
HELPER_PORT = int(os.environ.get("SNNU_HELPER_PORT", "18609"))
NETWORK_TYPES = {"campus", "unicom", "mobile"}

REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = REPO_ROOT / "config" / "snnu-config.json"
ACTION_PATH = REPO_ROOT / "logs" / "last_action.json"
SCRIPT_SERVICE_INSTALL = REPO_ROOT / "scripts" / "install-service.ps1"
SCRIPT_SERVICE_UNINSTALL = REPO_ROOT / "scripts" / "uninstall-service.ps1"
TOKEN_PATH = REPO_ROOT / "config" / "admin-token.txt"

app = Flask(__name__)


def load_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        return {}
    cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8-sig"))
    creds = cfg.setdefault("credentials", {})
    changed = False
    if "protectedPassword" in creds:
        creds.pop("protectedPassword", None)
        changed = True
    if changed:
        save_config(cfg)
    return cfg


def save_config(cfg: dict[str, Any]) -> None:
    CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


def resolve_path(path_value: str, default_rel: str) -> Path:
    if not path_value:
        return REPO_ROOT / default_rel
    p = Path(path_value)
    if p.is_absolute():
        return p
    return REPO_ROOT / p


def get_log_path(cfg: dict[str, Any] | None = None) -> Path:
    if cfg is None:
        cfg = load_config()
    return resolve_path(cfg.get("logPath", ""), "logs/wifi-keepalive.log")


def ensure_admin_token() -> str:
    if TOKEN_PATH.exists():
        return TOKEN_PATH.read_text(encoding="utf-8").strip()
    token = secrets.token_urlsafe(24)
    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_PATH.write_text(token, encoding="utf-8")
    return token


def append_log(message: str, level: str = "INFO") -> None:
    log_path = get_log_path()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_path.write_text("", encoding="utf-8") if not log_path.exists() else None
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(f"[{stamp}][{level}] {message}\n")


def normalize_output(result: subprocess.CompletedProcess) -> str:
    out = (result.stdout or "").strip()
    err = (result.stderr or "").strip()
    if out and err:
        return f"{out}\n{err}"
    return out or err


def _run_hidden(cmd: list[str]) -> subprocess.CompletedProcess:
    kwargs: dict[str, Any] = {"capture_output": True, "text": True, "errors": "replace"}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    return subprocess.run(cmd, **kwargs)


def run_powershell_file(path: Path, args: list[str] | None = None) -> subprocess.CompletedProcess:
    args = args or []
    cmd = [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(path),
        *args,
    ]
    return _run_hidden(cmd)


def run_once() -> str:
    manager = KeepaliveManager(CONFIG_PATH)
    manager.run_once()
    return "Python keepalive cycle completed."


def service_status_raw() -> str:
    cmd = ["sc.exe", "query", SERVICE_NAME]
    result = _run_hidden(cmd)
    if result.returncode != 0:
        return "NotInstalled"
    for line in result.stdout.splitlines():
        if "STATE" in line:
            upper = line.upper()
            if "RUNNING" in upper:
                return "Running"
            if "STOPPED" in upper:
                return "Stopped"
            if "START_PENDING" in upper:
                return "StartPending"
            if "STOP_PENDING" in upper:
                return "StopPending"
    return "Unknown"


def service_status_display(raw: str) -> str:
    mapping = {
        "NotInstalled": "未安装",
        "Running": "已安装（运行中）",
        "Stopped": "已安装（已停止）",
        "StartPending": "正在启动",
        "StopPending": "正在停止",
        "Unknown": "未知",
    }
    return mapping.get(raw, raw)


def service_start_type_raw() -> str:
    cmd = ["sc.exe", "qc", SERVICE_NAME]
    result = _run_hidden(cmd)
    if result.returncode != 0:
        return "NotInstalled"
    for line in result.stdout.splitlines():
        if "START_TYPE" in line:
            upper = line.upper()
            if "AUTO_START" in upper:
                return "Auto"
            if "DEMAND_START" in upper:
                return "Manual"
            if "DISABLED" in upper:
                return "Disabled"
    return "Unknown"


def service_start_type_display(raw: str) -> str:
    mapping = {
        "NotInstalled": "未安装",
        "Auto": "自动",
        "Manual": "手动",
        "Disabled": "已禁用",
        "Unknown": "未知",
    }
    return mapping.get(raw, raw)


def get_service_info() -> dict[str, Any]:
    state_raw = service_status_raw()
    start_raw = service_start_type_raw()
    return {
        "installed": state_raw != "NotInstalled",
        "running": state_raw == "Running",
        "state_raw": state_raw,
        "state_display": service_status_display(state_raw),
        "start_raw": start_raw,
        "start_display": service_start_type_display(start_raw),
        "autostart": start_raw == "Auto",
    }


def helper_status_raw() -> str:
    cmd = ["sc.exe", "query", HELPER_NAME]
    result = _run_hidden(cmd)
    if result.returncode != 0:
        return "NotInstalled"
    for line in result.stdout.splitlines():
        if "STATE" in line:
            upper = line.upper()
            if "RUNNING" in upper:
                return "Running"
            if "STOPPED" in upper:
                return "Stopped"
            if "START_PENDING" in upper:
                return "StartPending"
            if "STOP_PENDING" in upper:
                return "StopPending"
    return "Unknown"


def helper_status_display(raw: str) -> str:
    mapping = {
        "NotInstalled": "未安装",
        "Running": "运行中",
        "Stopped": "已停止",
        "StartPending": "正在启动",
        "StopPending": "正在停止",
        "Unknown": "未知",
    }
    return mapping.get(raw, raw)


def get_helper_info() -> dict[str, Any]:
    state_raw = helper_status_raw()
    return {
        "installed": state_raw != "NotInstalled",
        "running": state_raw == "Running",
        "state_raw": state_raw,
        "state_display": helper_status_display(state_raw),
    }


def call_helper(action: str, payload: dict[str, Any] | None = None) -> tuple[bool, str]:
    info = get_helper_info()
    if not info.get("running"):
        return False, "Admin helper not running. Install and start helper service first."
    token = ensure_admin_token()
    data = {"action": action}
    if payload:
        data.update(payload)
    try:
        resp = requests.post(
            f"http://127.0.0.1:{HELPER_PORT}/",
            json=data,
            headers={"X-Admin-Token": token},
            timeout=8,
        )
        text = resp.text.strip()
        if resp.status_code != 200:
            return False, f"HTTP {resp.status_code}: {text}"
        try:
            body = resp.json()
        except ValueError:
            return False, text or "Invalid helper response."
        return bool(body.get("ok")), body.get("message") or ""
    except Exception as exc:
        return False, str(exc)


def install_service(run_now: bool = True) -> subprocess.CompletedProcess:
    args = ["-RunNow"] if run_now else []
    return run_powershell_file(SCRIPT_SERVICE_INSTALL, args)


def uninstall_service() -> subprocess.CompletedProcess:
    return run_powershell_file(SCRIPT_SERVICE_UNINSTALL)


def start_service() -> subprocess.CompletedProcess:
    cmd = ["sc.exe", "start", SERVICE_NAME]
    return _run_hidden(cmd)


def stop_service() -> subprocess.CompletedProcess:
    cmd = ["sc.exe", "stop", SERVICE_NAME]
    return _run_hidden(cmd)


def set_service_autostart(enable: bool) -> subprocess.CompletedProcess:
    start_value = "auto" if enable else "demand"
    cmd = ["sc.exe", "config", SERVICE_NAME, "start=", start_value]
    return _run_hidden(cmd)


def read_log_tail(lines: int = 200) -> str:
    log_path = get_log_path()
    if not log_path.exists():
        return ""
    content = log_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    return "\n".join(content[-lines:])


def write_last_action(action: str, ok: bool, message: str) -> None:
    ACTION_PATH.parent.mkdir(parents=True, exist_ok=True)
    append_log(f"{action} {'OK' if ok else 'FAILED'}: {message}", "INFO" if ok else "ERROR")
    ACTION_PATH.write_text(
        json.dumps({"action": action, "ok": ok, "message": message}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def read_last_action() -> dict[str, Any]:
    if not ACTION_PATH.exists():
        return {}
    try:
        return json.loads(ACTION_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def reconcile_last_action(last_action: dict[str, Any], service_info: dict[str, Any]) -> dict[str, Any]:
    if not last_action:
        return last_action
    action = last_action.get("action", "")
    if action in {"install-service", "start-service"} and service_info.get("running"):
        return {"action": action, "ok": True, "message": "已安装并运行（已恢复）"}
    if action == "install-service" and service_info.get("installed"):
        return {"action": action, "ok": True, "message": "已安装（已恢复）"}
    if action == "stop-service" and not service_info.get("running") and service_info.get("installed"):
        return {"action": action, "ok": True, "message": "已停止（已恢复）"}
    return last_action


def format_action_label(action: str) -> str:
    mapping = {
        "install-service": "安装服务",
        "uninstall-service": "卸载服务",
        "start-service": "启动服务",
        "stop-service": "停止服务",
        "service-autostart": "设置自启动",
        "run-once": "立即运行",
        "connect-test": "连接测试",
    }
    return mapping.get(action, action)


def resolve_network_type(options: dict[str, Any] | None) -> str:
    options = options or {}
    network_type = options.get("networkType")
    if network_type in NETWORK_TYPES:
        return network_type
    isp = options.get("isp")
    if isp in NETWORK_TYPES:
        return isp
    if options.get("campusNet"):
        return "campus"
    return "campus"


def apply_network_type(options: dict[str, Any], network_type: str) -> None:
    if network_type not in NETWORK_TYPES:
        network_type = "campus"
    options["networkType"] = network_type
    options["campusNet"] = network_type == "campus"
    options["isp"] = "" if network_type == "campus" else network_type


def format_short_timestamp(value: Any) -> str:
    text = str(value or "")
    if len(text) >= 16 and text[4] == "-" and text[7] == "-":
        return f"{text[5:10]} {text[11:16]}"
    return text


def compact_status_timestamps(status_data: dict[str, Any]) -> dict[str, Any]:
    compacted = dict(status_data)
    for key in ("lastOnline", "lastLoginSuccess"):
        compacted[key] = format_short_timestamp(compacted.get(key))
    return compacted


def get_status_data() -> dict[str, Any]:
    try:
        return KeepaliveManager(CONFIG_PATH).status()
    except Exception as exc:
        return {"error": str(exc)}


def get_portal_by_name(cfg: dict[str, Any], name: str) -> dict[str, Any] | None:
    for portal in cfg.get("portals", []):
        if portal.get("name") == name:
            return portal
    return None


def trigger_run_once() -> None:
    cfg = load_config()
    trigger_path = resolve_path(cfg.get("triggerPath", ""), "logs/trigger.once")
    trigger_path.parent.mkdir(parents=True, exist_ok=True)
    trigger_path.write_text("1", encoding="utf-8")


@app.get("/")
def index():
    cfg = load_config()
    service_info = get_service_info()
    helper_info = get_helper_info()
    log_tail = read_log_tail()
    last_action = reconcile_last_action(read_last_action(), service_info)
    if last_action:
        last_action["label"] = format_action_label(last_action.get("action", ""))
    status_data = compact_status_timestamps(get_status_data())
    adapters = status_data.get("adapters", []) if isinstance(status_data, dict) else []
    return render_template(
        "index.html",
        config=cfg,
        network_type=resolve_network_type(cfg.get("portalOptions")),
        service_info=service_info,
        helper_info=helper_info,
        last_action=last_action,
        log_tail=log_tail,
        service_name=SERVICE_NAME,
        status_data=status_data,
        adapters=adapters,
    )


@app.get("/service")
def service_page():
    service_info = get_service_info()
    helper_info = get_helper_info()
    last_action = reconcile_last_action(read_last_action(), service_info)
    if last_action:
        last_action["label"] = format_action_label(last_action.get("action", ""))
    return render_template(
        "service.html",
        service_info=service_info,
        helper_info=helper_info,
        last_action=last_action,
        service_name=SERVICE_NAME,
    )


@app.get("/tasks")
def tasks_redirect():
    return redirect(url_for("service_page"))


@app.get("/status")
def status_route():
    return jsonify(get_status_data())


@app.get("/logs")
def logs_route():
    try:
        lines = int(request.args.get("lines", "200"))
    except ValueError:
        lines = 200
    text = read_log_tail(lines)
    return app.response_class(text, mimetype="text/plain; charset=utf-8")


@app.post("/config")
def update_config():
    cfg = load_config()
    cfg.setdefault("credentials", {})

    cfg["ssid"] = request.form.get("ssid", "").strip() or cfg.get("ssid", "SNNU")
    cfg["profileName"] = request.form.get("profileName", "").strip()
    cfg["adapterName"] = request.form.get("adapterName", "").strip()
    apply_network_type(cfg.setdefault("portalOptions", {}), request.form.get("networkType", "campus").strip())

    interval = request.form.get("intervalSeconds", "60").strip()
    try:
        cfg["intervalSeconds"] = max(10, int(interval))
    except ValueError:
        cfg["intervalSeconds"] = 60

    cfg["credentials"]["username"] = request.form.get("username", "").strip()

    save_config(cfg)
    return redirect(url_for("index"))


@app.post("/credentials")
def update_credentials():
    cfg = load_config()
    cfg.setdefault("credentials", {})

    password = request.form.get("password", "")
    if password:
        cfg["credentials"]["password"] = password
        if "protectedPassword" in cfg["credentials"]:
            cfg["credentials"].pop("protectedPassword", None)

    save_config(cfg)
    return redirect(url_for("index"))


@app.post("/run-once")
def run_once_route():
    if service_status_raw().lower() == "running":
        trigger_run_once()
        write_last_action("run-once", True, "Triggered service cycle.")
    else:
        output = run_once()
        ok = True
        msg = output or "OK"
        if "ERROR" in msg.upper():
            ok = False
        write_last_action("run-once", ok, msg)
    return redirect(url_for("index"))


@app.post("/service/install")
def install_service_route():
    ok, msg = call_helper("service_install")
    if not msg:
        msg = "OK" if ok else "Install failed."
    write_last_action("install-service", ok, msg)
    return redirect(url_for("service_page"))


@app.post("/service/start")
def start_service_route():
    ok, msg = call_helper("service_start")
    if not msg:
        msg = "OK" if ok else "Start failed."
    write_last_action("start-service", ok, msg)
    return redirect(url_for("service_page"))


@app.post("/service/stop")
def stop_service_route():
    ok, msg = call_helper("service_stop")
    if not msg:
        msg = "OK" if ok else "Stop failed."
    write_last_action("stop-service", ok, msg)
    return redirect(url_for("service_page"))


@app.post("/service/uninstall")
def uninstall_service_route():
    ok, msg = call_helper("service_uninstall")
    if not msg:
        msg = "OK" if ok else "Uninstall failed."
    write_last_action("uninstall-service", ok, msg)
    return redirect(url_for("service_page"))


@app.post("/service/autostart")
def service_autostart_route():
    enable = request.form.get("enable") == "1"
    ok, msg = call_helper("service_autostart", {"enable": "1" if enable else "0"})
    if not msg:
        msg = "OK" if ok else "Set startup failed."
    write_last_action("service-autostart", ok, msg)
    return redirect(url_for("service_page"))


@app.post("/status/check")
def status_check_route():
    data = get_status_data()
    ok = False
    msg = ""
    if isinstance(data, dict):
        ok = bool(data.get("connectivityOk"))
        msg = f"Connectivity {'OK' if ok else 'FAILED'}."
    write_last_action("connect-test", ok, msg)
    return redirect(url_for("index"))


@app.get("/portal/debug")
def portal_debug():
    cfg = load_config()
    portals = cfg.get("portals", [])
    name = request.args.get("name") or (portals[0]["name"] if portals else "")
    portal = get_portal_by_name(cfg, name) if name else None
    info = debug_info(portal, timeout=10) if portal else {"error": "portal not found"}
    return render_template(
        "portal_debug.html",
        config=cfg,
        network_type=resolve_network_type(cfg.get("portalOptions")),
        portals=portals,
        selected=name,
        portal=portal or {},
        info=info,
    )


@app.post("/portal/debug")
def portal_debug_save():
    cfg = load_config()
    name = request.form.get("name", "")
    portal = get_portal_by_name(cfg, name)
    if not portal:
        return redirect(url_for("portal_debug"))

    portal["loginPost"] = request.form.get("loginPost", "").strip()
    portal["usernameField"] = request.form.get("usernameField", "").strip()
    portal["passwordField"] = request.form.get("passwordField", "").strip()
    portal["successRegex"] = request.form.get("successRegex", "").strip()

    extra_raw = request.form.get("extraFields", "").strip()
    if extra_raw:
        try:
            portal["extraFields"] = json.loads(extra_raw)
        except json.JSONDecodeError:
            pass

    cfg.setdefault("portalOptions", {})
    cfg["portalOptions"]["rememberPassword"] = request.form.get("rememberPassword") == "on"
    network_type = request.form.get("networkType")
    if not network_type:
        network_type = "campus" if request.form.get("campusNet") == "on" else request.form.get("isp", "unicom")
    apply_network_type(cfg["portalOptions"], network_type.strip())

    save_config(cfg)
    return redirect(url_for("portal_debug", name=name))


@app.post("/portal/test")
def portal_test():
    cfg = load_config()
    name = request.form.get("name", "")
    portal = get_portal_by_name(cfg, name)
    if not portal:
        return redirect(url_for("portal_debug"))

    creds = cfg.get("credentials") or {}
    username = creds.get("username", "")
    password = creds.get("password", "")

    ok, msg, _info = attempt_portal_login(
        portal=portal,
        username=username,
        password=password,
        portal_options=cfg.get("portalOptions", {}),
        timeout=10,
        debug=True,
        debug_path=REPO_ROOT / "logs" / f"portal-{portal.get('name','portal')}-last.html",
    )

    result = "OK" if ok else "FAILED"
    return redirect(url_for("portal_debug", name=name, result=result, message=msg))


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=APP_PORT, debug=False)
