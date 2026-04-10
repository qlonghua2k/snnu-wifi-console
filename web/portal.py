from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

USER_FIELD_RE = re.compile(r"user|name|account|login|id|uid|username", re.I)
REMEMBER_RE = re.compile(r"remember|save|pwd|pass|auto", re.I)
CAMPUS_RE = re.compile(r"campus|school|net|校园|校内", re.I)
ISP_RE = {
    "unicom": re.compile(r"unicom|cu|联通", re.I),
    "mobile": re.compile(r"mobile|cmcc|移动", re.I),
}
NETWORK_TYPES = {"campus", "unicom", "mobile"}
ALREADY_ONLINE_RE = re.compile(r"logoff|断开连接|已登录|当前登录账号|当前账号|在线", re.I)


@dataclass
class ParsedForm:
    action_url: str
    inputs: list[dict[str, str]]
    username_field: str
    password_field: str


def load_config(path: Path) -> dict[str, Any]:
    cfg = json.loads(path.read_text(encoding="utf-8-sig"))
    creds = cfg.setdefault("credentials", {})
    changed = False
    if "protectedPassword" in creds:
        creds.pop("protectedPassword", None)
        changed = True
    if changed:
        path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    return cfg


def _ensure_encoding(resp: requests.Response) -> None:
    if not resp.encoding or resp.encoding.lower() in {"iso-8859-1", "latin-1"}:
        resp.encoding = resp.apparent_encoding or resp.encoding


def fetch_login_page(url: str, timeout: int = 10) -> requests.Response:
    resp = requests.get(url, timeout=timeout, allow_redirects=True)
    _ensure_encoding(resp)
    return resp


def _extract_label(input_tag) -> str:
    label = ""
    input_id = input_tag.get("id")
    if input_id:
        form = input_tag.find_parent("form")
        if form:
            lbl = form.find("label", attrs={"for": input_id})
            if lbl:
                label = lbl.get_text(strip=True)
    if not label and input_tag.parent and input_tag.parent.name == "label":
        label = input_tag.parent.get_text(strip=True)
    return label


def parse_login_form(html: str, base_url: str) -> ParsedForm:
    soup = BeautifulSoup(html, "html.parser")
    form = soup.find("form")
    if not form:
        return ParsedForm(action_url=base_url, inputs=[], username_field="", password_field="")

    action = form.get("action") or ""
    action_url = urljoin(base_url, action) if action else base_url

    inputs: list[dict[str, str]] = []
    for inp in form.find_all("input"):
        name = (inp.get("name") or inp.get("id") or "").strip()
        if not name:
            continue
        input_type = (inp.get("type") or "text").strip().lower()
        value = (inp.get("value") or "").strip()
        input_id = (inp.get("id") or "").strip()
        label = _extract_label(inp)
        inputs.append(
            {
                "name": name,
                "type": input_type,
                "value": value,
                "id": input_id,
                "label": label,
            }
        )

    for sel in form.find_all("select"):
        name = (sel.get("name") or sel.get("id") or "").strip()
        if not name:
            continue
        selected = sel.find("option", selected=True)
        if not selected:
            selected = sel.find("option")
        value = ""
        label = ""
        if selected:
            value = (selected.get("value") or selected.get_text(strip=True) or "").strip()
            label = selected.get_text(strip=True)
        inputs.append(
            {
                "name": name,
                "type": "select",
                "value": value,
                "id": (sel.get("id") or "").strip(),
                "label": label,
            }
        )

    password_field = ""
    for item in inputs:
        if item["type"] == "password":
            password_field = item["name"]
            break

    username_field = ""
    for item in inputs:
        if item["type"] in {"text", "email", "tel"} and USER_FIELD_RE.search(item["name"]):
            username_field = item["name"]
            break
    if not username_field:
        for item in inputs:
            if item["type"] in {"text", "email", "tel"}:
                username_field = item["name"]
                break

    return ParsedForm(
        action_url=action_url,
        inputs=inputs,
        username_field=username_field,
        password_field=password_field,
    )


def _apply_radio_choice(payload: dict[str, str], inputs: list[dict[str, str]], name: str, matcher: re.Pattern) -> None:
    options = [i for i in inputs if i["type"] == "radio" and i["name"] == name]
    for opt in options:
        hay = " ".join([opt["value"], opt.get("id", ""), opt.get("label", "")])
        if matcher.search(hay):
            payload[name] = opt["value"] or "1"
            return


def _apply_radio_any(payload: dict[str, str], inputs: list[dict[str, str]], matcher: re.Pattern) -> None:
    options = [i for i in inputs if i["type"] == "radio"]
    for opt in options:
        hay = " ".join([opt["value"], opt.get("id", ""), opt.get("label", "")])
        if matcher.search(hay):
            payload[opt["name"]] = opt["value"] or "1"
            return


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


def build_payload(
    parsed: ParsedForm,
    username: str,
    password: str,
    portal: dict[str, Any],
    portal_options: dict[str, Any] | None,
) -> tuple[str, dict[str, str]]:
    payload: dict[str, str] = {}

    for item in parsed.inputs:
        if item["type"] == "hidden":
            payload.setdefault(item["name"], item["value"])
        if item["type"] == "select" and item["name"] not in payload:
            payload[item["name"]] = item["value"]

    overrides = portal.get("extraFields") or {}
    for key, value in overrides.items():
        payload[key] = str(value)

    user_field = portal.get("usernameField") or parsed.username_field
    pass_field = portal.get("passwordField") or parsed.password_field

    if user_field:
        payload[user_field] = username
    if pass_field:
        payload[pass_field] = password

    options = portal_options or {}

    if options.get("rememberPassword"):
        for item in parsed.inputs:
            if item["type"] == "checkbox" and REMEMBER_RE.search(item["name"] + item.get("label", "")):
                payload[item["name"]] = item["value"] or "on"

    network_type = resolve_network_type(options)
    if network_type == "campus":
        groups = {i["name"] for i in parsed.inputs if i["type"] == "radio"}
        for group in groups:
            if CAMPUS_RE.search(group):
                _apply_radio_choice(payload, parsed.inputs, group, CAMPUS_RE)
        _apply_radio_any(payload, parsed.inputs, CAMPUS_RE)
        for item in parsed.inputs:
            if item["type"] == "select" and CAMPUS_RE.search(item["name"]):
                payload[item["name"]] = item["value"] or payload.get(item["name"], "")

    if network_type in ISP_RE:
        groups = {i["name"] for i in parsed.inputs if i["type"] == "radio"}
        for group in groups:
            if re.search(r"isp|operator|provider|线路|运营商", group, re.I):
                _apply_radio_choice(payload, parsed.inputs, group, ISP_RE[network_type])
        _apply_radio_any(payload, parsed.inputs, ISP_RE[network_type])
        for item in parsed.inputs:
            if item["type"] == "select" and re.search(r"isp|operator|provider|线路|运营商", item["name"], re.I):
                payload[item["name"]] = item["value"] or payload.get(item["name"], "")

    return (portal.get("loginPost") or parsed.action_url, payload)


def attempt_portal_login(
    portal: dict[str, Any],
    username: str,
    password: str,
    portal_options: dict[str, Any] | None,
    timeout: int = 10,
    debug: bool = False,
    debug_path: Path | None = None,
) -> tuple[bool, str, dict[str, Any]]:
    login_page = portal.get("loginPage")
    if not login_page:
        return False, "missing loginPage", {}

    try:
        resp = fetch_login_page(login_page, timeout=timeout)
        html = resp.text
    except Exception as exc:
        return False, f"load login page failed: {exc}", {}

    if ALREADY_ONLINE_RE.search(html or ""):
        return True, "already online", {"action_url": login_page}

    if debug and debug_path:
        debug_path.write_text(html, encoding="utf-8")

    parsed = parse_login_form(html, login_page)
    action_url, payload = build_payload(parsed, username, password, portal, portal_options)

    if not (portal.get("usernameField") or parsed.username_field) or not (portal.get("passwordField") or parsed.password_field):
        return False, "unable to detect username/password fields", {
            "action_url": parsed.action_url,
            "inputs": parsed.inputs,
            "username_field": parsed.username_field,
            "password_field": parsed.password_field,
        }

    try:
        post_resp = requests.post(action_url, data=payload, timeout=timeout, allow_redirects=True)
        _ensure_encoding(post_resp)
    except Exception as exc:
        return False, f"login post failed: {exc}", {
            "action_url": action_url,
            "inputs": parsed.inputs,
            "username_field": parsed.username_field,
            "password_field": parsed.password_field,
        }

    success_regex = portal.get("successRegex")
    if success_regex:
        if re.search(success_regex, post_resp.text or ""):
            return True, "success regex matched", {
                "action_url": action_url,
                "inputs": parsed.inputs,
                "username_field": parsed.username_field,
                "password_field": parsed.password_field,
            }
        return False, "success regex not matched", {
            "action_url": action_url,
            "inputs": parsed.inputs,
            "username_field": parsed.username_field,
            "password_field": parsed.password_field,
        }

    return True, "login post sent", {
        "action_url": action_url,
        "inputs": parsed.inputs,
        "username_field": parsed.username_field,
        "password_field": parsed.password_field,
    }


def debug_info(
    portal: dict[str, Any],
    timeout: int = 10,
) -> dict[str, Any]:
    login_page = portal.get("loginPage")
    if not login_page:
        return {"error": "missing loginPage"}

    try:
        resp = fetch_login_page(login_page, timeout=timeout)
        parsed = parse_login_form(resp.text, login_page)
    except Exception as exc:
        return {"error": f"load login page failed: {exc}"}

    return {
        "login_page": login_page,
        "action_url": parsed.action_url,
        "inputs": parsed.inputs,
        "username_field": parsed.username_field,
        "password_field": parsed.password_field,
    }
