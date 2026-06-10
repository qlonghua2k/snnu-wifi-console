from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
)

from desktop.constants import NETWORK_LABELS
from desktop.models.config_model import apply_network_type


class SettingsDialog(QDialog):
    def __init__(self, cfg: dict[str, Any], parent=None):
        super().__init__(parent)
        self.setWindowTitle("连接设置")
        self.setMinimumWidth(480)
        self.fields: dict[str, QLineEdit | QComboBox | QCheckBox] = {}
        self._build(cfg)

    def _build(self, cfg: dict[str, Any]) -> None:
        creds = cfg.get("credentials") or {}
        options = cfg.get("portalOptions") or {}

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        rows = QGridLayout()
        rows.setHorizontalSpacing(12)
        rows.setVerticalSpacing(10)

        for row, (key, label, value, placeholder) in enumerate(
            [
                ("ssid", "SSID", cfg.get("ssid", "SNNU"), "SNNU"),
                ("profileName", "配置文件", cfg.get("profileName", ""), "默认同 SSID"),
                ("adapterName", "无线网卡", cfg.get("adapterName", ""), "自动识别"),
                ("username", "校园网账号", creds.get("username", ""), "请输入校园网账号"),
                ("password", "新密码", "", "留空则不修改"),
            ]
        ):
            lab = QLabel(label)
            lab.setObjectName("formLabel")
            inp = QLineEdit(str(value))
            inp.setPlaceholderText(placeholder)
            inp.setMinimumHeight(36)
            if key == "password":
                inp.setEchoMode(QLineEdit.Password)
            self.fields[key] = inp
            rows.addWidget(lab, row, 0)
            rows.addWidget(inp, row, 1)

        network = QComboBox()
        for value, label in NETWORK_LABELS.items():
            network.addItem(label, value)
        network.setCurrentIndex(max(0, network.findData(options.get("networkType", "campus"))))
        network.setMinimumHeight(36)
        self.fields["networkType"] = network
        rows.addWidget(QLabel("网络类型"), 5, 0)
        rows.addWidget(network, 5, 1)
        layout.addLayout(rows)

        remember = QCheckBox("门户认证记住密码")
        remember.setChecked(bool(options.get("rememberPassword", False)))
        self.fields["rememberPassword"] = remember
        layout.addWidget(remember)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        if buttons.button(QDialogButtonBox.Save):
            buttons.button(QDialogButtonBox.Save).setText("保存")
        if buttons.button(QDialogButtonBox.Cancel):
            buttons.button(QDialogButtonBox.Cancel).setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def updated_config(self, cfg: dict[str, Any]) -> dict[str, Any]:
        cfg["ssid"] = self.line("ssid").text().strip() or "SNNU"
        cfg["profileName"] = self.line("profileName").text().strip()
        cfg["adapterName"] = self.line("adapterName").text().strip()
        cfg.setdefault("credentials", {})
        cfg["credentials"]["username"] = self.line("username").text().strip()
        password = self.line("password").text()
        if password:
            cfg["credentials"]["password"] = password
            cfg["credentials"].pop("protectedPassword", None)
        apply_network_type(cfg.setdefault("portalOptions", {}), self.combo("networkType").currentData())
        cfg["portalOptions"]["rememberPassword"] = self.check("rememberPassword").isChecked()
        return cfg

    def line(self, key: str) -> QLineEdit:
        return self.fields[key]  # type: ignore[return-value]

    def combo(self, key: str) -> QComboBox:
        return self.fields[key]  # type: ignore[return-value]

    def check(self, key: str) -> QCheckBox:
        return self.fields[key]  # type: ignore[return-value]
