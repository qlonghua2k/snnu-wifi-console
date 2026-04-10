from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from portal import attempt_portal_login, load_config


def log_line(log_path: Path, level: str, message: str) -> None:
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(f"[{ts}][{level}] {message}\n")
    except Exception:
        return


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--portal", default="")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--timeout", type=int, default=10)
    args = parser.parse_args()

    config_path = Path(args.config)
    cfg = load_config(config_path)
    log_path = config_path.parents[1] / "logs" / "wifi-keepalive.log"
    if cfg.get("logPath"):
        lp = Path(cfg.get("logPath"))
        if lp.is_absolute():
            log_path = lp
        else:
            log_path = config_path.parents[1] / lp
    portals = cfg.get("portals", [])
    portal_options = cfg.get("portalOptions", {})

    if args.portal:
        portals = [p for p in portals if p.get("name") == args.portal]

    if not portals:
        log_line(log_path, "ERROR", "Portal login: no portal configured.")
        print(json.dumps({"ok": False, "message": "no portal configured"}, ensure_ascii=False))
        return 2

    creds = cfg.get("credentials") or {}
    username = creds.get("username", "")
    password = creds.get("password", "")

    if not username or not password:
        log_line(log_path, "ERROR", "Portal login: missing credentials.")
        print(json.dumps({"ok": False, "message": "missing credentials"}, ensure_ascii=False))
        return 3

    for portal in portals:
        log_line(log_path, "INFO", f"Portal login attempt: {portal.get('name')}")
        debug_path = None
        if args.debug:
            debug_path = config_path.parents[1] / "logs" / f"portal-{portal.get('name','portal')}-last.html"
        ok, msg, info = attempt_portal_login(
            portal=portal,
            username=username,
            password=password,
            portal_options=portal_options,
            timeout=args.timeout,
            debug=args.debug,
            debug_path=debug_path,
        )
        result = {
            "ok": ok,
            "message": msg,
            "portal": portal.get("name"),
            "info": {
                "action_url": info.get("action_url"),
                "username_field": info.get("username_field"),
                "password_field": info.get("password_field"),
                "inputs": info.get("inputs", []),
            },
        }
        print(json.dumps(result, ensure_ascii=False))
        if ok:
            log_line(log_path, "INFO", f"Portal login success: {portal.get('name')} ({msg})")
            return 0
        log_line(log_path, "WARN", f"Portal login failed: {portal.get('name')} ({msg})")

    log_line(log_path, "ERROR", "Portal login failed on all portals.")
    return 4


if __name__ == "__main__":
    raise SystemExit(main())
