from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from desktop.constants import APP_ROOT, BUNDLE_ROOT, NETWORK_LABELS, SOURCE_ROOT, STATE_LABELS


def config_path() -> Path:
    return APP_ROOT / "config" / "snnu-config.json"


def bundled_config_template() -> Path:
    return BUNDLE_ROOT / "config" / "snnu-config.example.json"


def ensure_config() -> Path:
    path = config_path()
    if path.exists():
        return path

    example = bundled_config_template()
    if not example.exists():
        example = SOURCE_ROOT / "config" / "snnu-config.example.json"

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(example.read_text(encoding="utf-8"), encoding="utf-8")
    return path


def load_config() -> dict[str, Any]:
    return json.loads(ensure_config().read_text(encoding="utf-8-sig"))


def save_config(cfg: dict[str, Any]) -> None:
    ensure_config().write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


def apply_network_type(options: dict[str, Any], network_type: str) -> None:
    network_type = network_type if network_type in NETWORK_LABELS else "campus"
    options["networkType"] = network_type
    options["campusNet"] = network_type == "campus"
    options["isp"] = "" if network_type == "campus" else network_type


def display(value: Any, fallback: str = "-") -> str:
    if value is None or value == "":
        return fallback
    if isinstance(value, bool):
        return "是" if value else "否"
    return str(value)


def masked_username(username: str) -> str:
    if not username:
        return "-"
    return username[:2] + "*" * max(len(username) - 4, 2) + username[-2:]


def normalize_state(state: Any) -> str:
    if not state:
        return "-"
    return STATE_LABELS.get(str(state), str(state))
