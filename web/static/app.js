const statusIds = {
  ssid: "status-ssid",
  wlanState: "status-wlan",
  adapter: "status-adapter",
  adapterStatus: "status-adapter-status",
  ip: "status-ip",
  gateway: "status-gw",
  connectivityOk: "status-net",
  lastState: "status-last",
  lastOnline: "status-online",
  lastLoginSuccess: "status-login",
};

function setText(id, value) {
  const el = document.getElementById(id);
  if (!el) return;
  el.textContent = value || "";
}

function formatTimestamp(value) {
  if (!value) return "";
  const m = value.match(/^\d{4}-(\d{2}-\d{2})[T ](\d{2}:\d{2})/);
  if (m) {
    return `${m[1]} ${m[2]}`;
  }
  return value;
}

function normalizeWlan(state) {
  if (!state) return "";
  if (state.toLowerCase().includes("connected") || state.includes("已连接")) return "已连接";
  if (state.toLowerCase().includes("disconnected") || state.includes("断开")) return "已断开";
  return state;
}

function normalizeState(state) {
  if (!state) return "";
  const map = {
    INIT: "初始化",
    ONLINE: "在线",
    DISCONNECTED: "未连接",
    NEEDS_LOGIN: "待认证",
    CONNECTED_NO_NET: "已连接但无网",
    OTHER_SSID: "已连接其他网络",
    LOGIN_COOLDOWN: "冷却中",
    LOGIN_FAILED: "登录失败",
    RADIO_OFF: "Wi-Fi 关闭",
    NO_ADAPTER: "无适配器",
    MISSING_CREDENTIALS: "缺少凭据",
    NEEDS_ADMIN: "需要管理员权限",
  };
  return map[state] || state;
}

function setBadge(ok) {
  const el = document.getElementById(statusIds.connectivityOk);
  if (!el) return;
  el.textContent = ok ? "ONLINE" : "OFFLINE";
  el.classList.remove("ok", "fail");
  el.classList.add(ok ? "ok" : "fail");
}

async function refreshStatus() {
  try {
    const res = await fetch("/status", { cache: "no-store" });
    const data = await res.json();
    setText(statusIds.ssid, data.ssid);
    setText(statusIds.wlanState, normalizeWlan(data.wlanState));
    setText(statusIds.adapter, data.adapter);
    setText(statusIds.adapterStatus, data.adapterStatus);
    setText(statusIds.ip, data.ip);
    setText(statusIds.gateway, data.gateway);
    setBadge(Boolean(data.connectivityOk));
    setText(statusIds.lastState, normalizeState(data.lastState));
    setText(statusIds.lastOnline, formatTimestamp(data.lastOnline));
    setText(statusIds.lastLoginSuccess, formatTimestamp(data.lastLoginSuccess));
  } catch (err) {
  }
}

async function refreshLogs() {
  const el = document.getElementById("log-tail");
  if (!el) return;
  try {
    const res = await fetch("/logs?lines=200", { cache: "no-store" });
    const text = await res.text();
    if (text && el.textContent !== text) {
      el.textContent = text;
    }
  } catch (err) {
    // ignore
  }
}

const refreshBtn = document.getElementById("refresh-status");
if (refreshBtn) {
  refreshBtn.addEventListener("click", refreshStatus);
}

setInterval(refreshStatus, 5000);
setInterval(refreshLogs, 5000);
refreshLogs();
