from __future__ import annotations

import sys
from pathlib import Path


APP_TITLE = "SNNU Wi-Fi 控制台"
SERVICE_NAME = "SNNUWifiKeepalive"
STARTUP_ENTRY_NAME = APP_TITLE

SOURCE_ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else SOURCE_ROOT
BUNDLE_ROOT = Path(getattr(sys, "_MEIPASS", SOURCE_ROOT))
DESKTOP_ASSETS_DIR = BUNDLE_ROOT / "desktop" / "assets"
APP_ICON_PNG = DESKTOP_ASSETS_DIR / "app.png"

NETWORK_LABELS = {
    "campus": "校园网",
    "unicom": "联通",
    "mobile": "移动",
}

STATE_LABELS = {
    "INIT": "初始化",
    "ONLINE": "在线",
    "DISCONNECTED": "未连接",
    "NEEDS_LOGIN": "待认证",
    "CONNECTED_NO_NET": "已连接但无网",
    "OTHER_SSID": "已连接其他网络",
    "LOGIN_COOLDOWN": "冷却中",
    "LOGIN_FAILED": "认证失败",
    "WRONG_PASSWORD": "密码错误",
    "NOT_SNNU_WIFI": "非 SNNU Wi-Fi",
    "NO_IP": "无 IP",
    "RADIO_OFF": "Wi-Fi 已关闭",
    "NO_ADAPTER": "未找到无线网卡",
    "MISSING_CREDENTIALS": "缺少账号密码",
    "NEEDS_ADMIN": "需要管理员权限",
    "UNKNOWN": "未知",
}
