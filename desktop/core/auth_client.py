from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin

import requests


ONLINE = "ONLINE"
NEED_LOGIN = "NEED_LOGIN"
LOGIN_FAILED = "LOGIN_FAILED"
WRONG_PASSWORD = "WRONG_PASSWORD"
NOT_SNNU_WIFI = "NOT_SNNU_WIFI"
NO_IP = "NO_IP"
MISSING_CREDENTIALS = "MISSING_CREDENTIALS"
PORTAL_UNREACHABLE = "PORTAL_UNREACHABLE"

DEFAULT_ONLINE_MARKERS = [
    "auth_my_state.php",
    "logoff",
    "logout",
    "断开连接",
    "已登录",
    "当前登录账号",
    "当前账号",
]
DEFAULT_WRONG_PASSWORD_MARKERS = [
    "密码错误",
    "账号或密码错误",
    "invalid password",
    "wrong password",
]
DEFAULT_FAILURE_MARKERS = [
    "认证失败",
    "登录失败",
    "账号不存在",
    "invalid",
    "failed",
    "error",
]


@dataclass(frozen=True)
class AuthInput:
    target_ssid: str
    current_ssid: str
    ip: str
    username: str
    password: str
    network_type: str


@dataclass(frozen=True)
class AuthTemplate:
    name: str
    login_page: str
    login_url: str
    method: str
    form: dict[str, str]
    operators: dict[str, str]
    online_markers: list[str]
    wrong_password_markers: list[str]
    failure_markers: list[str]


@dataclass(frozen=True)
class AuthResult:
    status: str
    message: str = ""
    portal: str = ""
    details: dict[str, Any] | None = None


def operator_value(template: AuthTemplate, network_type: str) -> str:
    return template.operators.get(network_type, template.operators.get("campus", ""))


def render_form(template: AuthTemplate, auth: AuthInput) -> dict[str, str]:
    values = {
        "username": auth.username,
        "password": auth.password,
        "operator": operator_value(template, auth.network_type),
        "ip": auth.ip,
        "ssid": auth.target_ssid,
    }
    return {key: value.format(**values) for key, value in template.form.items()}


def ensure_response_encoding(resp: requests.Response) -> None:
    if not resp.encoding or resp.encoding.lower() in {"iso-8859-1", "latin-1"}:
        resp.encoding = resp.apparent_encoding or resp.encoding


def contains_any(text: str, markers: list[str]) -> bool:
    lowered = text.lower()
    return any(marker and marker.lower() in lowered for marker in markers)


def classify_text(text: str, template: AuthTemplate) -> str:
    if contains_any(text, template.online_markers):
        return ONLINE
    if contains_any(text, template.wrong_password_markers):
        return WRONG_PASSWORD
    if contains_any(text, template.failure_markers):
        return LOGIN_FAILED
    return NEED_LOGIN


def check_connectivity(checks: list[dict[str, Any]], timeout: float) -> bool:
    for check in checks:
        url = check.get("url")
        if not url:
            continue
        try:
            resp = requests.get(url, timeout=timeout, allow_redirects=False)
        except Exception:
            continue
        expected_status = check.get("expectStatus")
        if expected_status and resp.status_code != expected_status:
            continue
        expected_body = check.get("expectBody")
        if expected_body:
            ensure_response_encoding(resp)
            if expected_body not in resp.text:
                continue
        return True
    return False


def ensure_online(
    auth: AuthInput,
    templates: list[AuthTemplate],
    connectivity_checks: list[dict[str, Any]],
    timeout: float = 4,
) -> AuthResult:
    if auth.current_ssid != auth.target_ssid:
        return AuthResult(NOT_SNNU_WIFI, f"Connected SSID is {auth.current_ssid or '-'}, not {auth.target_ssid}.")
    if not auth.ip:
        return AuthResult(NO_IP, "Target Wi-Fi has no IPv4 address.")
    if not auth.username or not auth.password:
        return AuthResult(MISSING_CREDENTIALS, "Missing username or password.")
    if check_connectivity(connectivity_checks, timeout):
        return AuthResult(ONLINE, "Connectivity already OK.")

    last_error = ""
    for template in templates:
        try:
            with requests.Session() as session:
                page_resp = session.get(template.login_page, timeout=timeout, allow_redirects=True)
                ensure_response_encoding(page_resp)
                page_state = classify_text(page_resp.text or "", template)
                if page_state == ONLINE:
                    return AuthResult(ONLINE, "Portal page reports already online.", template.name)
                if page_state == WRONG_PASSWORD:
                    return AuthResult(WRONG_PASSWORD, "Portal reported wrong password.", template.name)

                form = render_form(template, auth)
                method = template.method.upper()
                if method == "GET":
                    post_resp = session.get(template.login_url, params=form, timeout=timeout, allow_redirects=True)
                else:
                    post_resp = session.post(template.login_url, data=form, timeout=timeout, allow_redirects=True)
                ensure_response_encoding(post_resp)
                post_state = classify_text(post_resp.text or "", template)
                if post_state == WRONG_PASSWORD:
                    return AuthResult(WRONG_PASSWORD, "Portal reported wrong password.", template.name)
                if post_state == LOGIN_FAILED:
                    return AuthResult(LOGIN_FAILED, "Portal reported login failure.", template.name)
                if post_state == ONLINE and check_connectivity(connectivity_checks, timeout):
                    return AuthResult(ONLINE, "Portal login succeeded.", template.name)
                if check_connectivity(connectivity_checks, timeout):
                    return AuthResult(ONLINE, "Connectivity restored after portal login.", template.name)
                last_error = f"{template.name}: login posted but connectivity is still unavailable"
        except Exception as exc:
            last_error = f"{template.name}: {exc}"
            continue

    if last_error:
        return AuthResult(LOGIN_FAILED, last_error)
    return AuthResult(PORTAL_UNREACHABLE, "No portal template was reachable.")


def auth_templates_from_config(config: dict[str, Any]) -> list[AuthTemplate]:
    raw_templates = config.get("authTemplates") or []
    if not raw_templates:
        raw_templates = legacy_portals_to_templates(config.get("portals") or [])
    templates = []
    for item in raw_templates:
        login_page = str(item.get("loginPage") or "")
        login_url = str(item.get("loginUrl") or item.get("loginPost") or "")
        if not login_url and login_page:
            login_url = urljoin(login_page, "login")
        if not login_page or not login_url:
            continue
        templates.append(
            AuthTemplate(
                name=str(item.get("name") or login_url),
                login_page=login_page,
                login_url=login_url,
                method=str(item.get("method") or "POST"),
                form={str(k): str(v) for k, v in (item.get("form") or {}).items()},
                operators={str(k): str(v) for k, v in (item.get("operators") or {}).items()},
                online_markers=list(item.get("onlineMarkers") or DEFAULT_ONLINE_MARKERS),
                wrong_password_markers=list(item.get("wrongPasswordMarkers") or DEFAULT_WRONG_PASSWORD_MARKERS),
                failure_markers=list(item.get("failureMarkers") or DEFAULT_FAILURE_MARKERS),
            )
        )
    return templates


def legacy_portals_to_templates(portals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    templates = []
    for portal in portals:
        login_page = str(portal.get("loginPage") or "")
        templates.append(
            {
                "name": portal.get("name") or login_page,
                "loginPage": login_page,
                "loginUrl": portal.get("loginPost") or (urljoin(login_page, "login") if login_page else ""),
                "method": "POST",
                "form": {
                    "sourceurl": "null",
                    "account": "{username}",
                    "password": "{password}",
                    "yys": "{operator}",
                    "issave": "",
                },
                "operators": {
                    "campus": "",
                    "unicom": "unicom",
                    "mobile": "mobile",
                },
            }
        )
    return templates
