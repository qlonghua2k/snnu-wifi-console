from __future__ import annotations


def build_styles(theme: str) -> str:
    if theme == "dark":
        return """
        QWidget { font-size: 13px; color: #f2f8ff; }
        #eyebrow { color: #6ecfff; font-size: 12px; font-weight: 800; }
        #title { color: #ffffff; font-size: 30px; font-weight: 900; letter-spacing: 0px; }
        #subtitle { color: rgba(226, 242, 255, 0.84); font-size: 13px; }
        #footerStatus { color: #b6e8ff; font-size: 12px; font-weight: 700; }
        QFrame[class="card"] {
            background: rgba(8, 20, 34, 0.80);
            border: 1px solid rgba(94, 186, 230, 0.34);
            border-left: 4px solid #45b9ee;
            border-radius: 10px;
        }
        #cardTitle, QLabel#cardTitle { color: #f4fbff; font-size: 16px; font-weight: 900; }
        #formLabel { color: #9ab8cd; font-size: 12px; font-weight: 800; }
        #fieldValue { color: #ffffff; font-size: 15px; font-weight: 800; }
        #switchName { color: #ecf7ff; font-size: 14px; font-weight: 900; }
        #switchState { color: #9bd9f2; font-size: 12px; font-weight: 800; }
        #hudState { color: #6ecfff; font-size: 38px; font-weight: 900; padding-top: 0; }
        #hudDetail {
            color: #d7f3ff; font-size: 12px; font-weight: 800;
            border-top: 1px solid rgba(105, 215, 255, 0.28);
            padding-top: 8px;
        }
        #warningText, #hintText {
            color: #ffe2a0; background: rgba(255, 202, 79, 0.14);
            border: 1px solid rgba(255, 202, 79, 0.36); border-radius: 6px; padding: 5px 8px;
            font-size: 12px; font-weight: 700;
        }
        QLineEdit, QComboBox {
            min-height: 36px; color: #ecf7ff; background: rgba(3, 13, 25, 0.9);
            border: 1px solid rgba(105, 215, 255, 0.45); border-radius: 6px; padding: 4px 10px;
        }
        QLineEdit:focus, QComboBox:focus { border: 1px solid #69d7ff; }
        QCheckBox { color: #e5f8ff; }
        QCheckBox::indicator { width: 16px; height: 16px; }
        QCheckBox#toggleSwitch::indicator {
            width: 54px; height: 26px; border-radius: 13px;
            background: rgba(107, 126, 149, 0.76);
            border: 1px solid rgba(214, 239, 255, 0.28);
        }
        QCheckBox#toggleSwitch::indicator:checked {
            background: #42bcea;
            border: 1px solid #a7e9ff;
        }
        QCheckBox#toggleSwitch::indicator:disabled {
            background: rgba(107, 126, 149, 0.36);
            border: 1px solid rgba(214, 239, 255, 0.16);
        }
        QPushButton {
            border-radius: 8px; padding: 4px 10px; font-weight: 900; letter-spacing: 0px;
            font-size: 13px;
        }
        #primaryButton { color: #061521; background: #42bcea; border: 1px solid #a7e9ff; }
        #primaryButton:hover { background: #68cefa; }
        #secondaryButton {
            color: #f2f8ff; background: rgba(16, 38, 58, 0.84); border: 1px solid rgba(105, 205, 248, 0.42);
        }
        #secondaryButton:hover { color: #061521; background: #42bcea; }
        #iconButton {
            color: #f2f8ff; background: rgba(16, 38, 58, 0.84); border: 1px solid rgba(105, 205, 248, 0.42);
        }
        #iconButton:hover { background: rgba(66, 188, 234, 0.32); }
        QMenu {
            color: #f2f8ff; background: rgba(8, 20, 34, 0.96);
            border: 1px solid rgba(105, 205, 248, 0.42); padding: 6px;
        }
        QMenu::item { padding: 7px 28px 7px 12px; border-radius: 6px; }
        QMenu::item:selected { color: #061521; background: #42bcea; }
        QMenu::item:disabled { color: rgba(242, 248, 255, 0.34); background: transparent; }
        QMenu::item:selected:disabled { color: rgba(242, 248, 255, 0.34); background: transparent; }
        #statusPill {
            border-radius: 10px; padding: 0;
            font-size: 16px; font-weight: 900;
        }
        #statusPill[state="online"] { color: #061521; background: #42bcea; border: 1px solid #a7e9ff; }
        #statusPill[state="warning"] { color: #241600; background: #ffd56b; border: 1px solid #ffe6aa; }
        #statusPill[state="offline"] { color: #ffffff; background: #f05267; border: 1px solid #ff9baa; }
        #healthDot { border-radius: 6px; background: #6b7e95; }
        #healthDot[state="online"] { background: #69d7ff; }
        #healthDot[state="warning"] { background: #ffd56b; }
        #healthDot[state="offline"] { background: #f05267; }
        #logView {
            color: #f2f8ff; background: rgba(4, 13, 23, 0.90);
            border: 1px solid rgba(92, 190, 235, 0.26); border-radius: 10px; padding: 12px;
            selection-background-color: #237ec5;
        }
        #logView QScrollBar:vertical {
            background: rgba(255, 255, 255, 0.04); width: 10px; margin: 6px 2px 6px 0;
            border-radius: 5px;
        }
        #logView QScrollBar::handle:vertical {
            background: rgba(242, 248, 255, 0.38); min-height: 42px; border-radius: 5px;
        }
        #logView QScrollBar::add-line:vertical, #logView QScrollBar::sub-line:vertical { height: 0; }
        #logView QScrollBar::add-page:vertical, #logView QScrollBar::sub-page:vertical { background: transparent; }
        """

    return """
    QWidget { font-size: 13px; color: #102033; }
    #eyebrow { color: #0878b9; font-size: 12px; font-weight: 900; }
    #title { color: #0c1828; font-size: 30px; font-weight: 900; letter-spacing: 0px; }
    #subtitle { color: rgba(17, 39, 64, 0.82); font-size: 13px; }
    #footerStatus { color: #0f6397; font-size: 12px; font-weight: 700; }
    QFrame[class="card"] {
        background: rgba(255, 255, 255, 0.68);
        border: 1px solid rgba(14, 96, 150, 0.28);
        border-left: 4px solid #1788c9;
        border-radius: 10px;
    }
    #cardTitle, QLabel#cardTitle { color: #0d1c2f; font-size: 16px; font-weight: 900; }
    #formLabel { color: #50677f; font-size: 12px; font-weight: 900; }
    #fieldValue { color: #0d1c2f; font-size: 15px; font-weight: 800; }
    #switchName { color: #15304b; font-size: 14px; font-weight: 900; }
    #switchState { color: #41627e; font-size: 12px; font-weight: 900; }
    #hudState { color: #0878b9; font-size: 38px; font-weight: 900; padding-top: 0; }
    #hudDetail {
        color: #174767; font-size: 12px; font-weight: 800;
        border-top: 1px solid rgba(14, 96, 150, 0.22);
        padding-top: 8px;
    }
    #warningText, #hintText {
        color: #785000; background: rgba(255, 238, 185, 0.62);
        border: 1px solid rgba(200, 148, 38, 0.34); border-radius: 6px; padding: 5px 8px;
        font-size: 12px; font-weight: 700;
    }
    QLineEdit, QComboBox {
        min-height: 36px; color: #0d1c2f; background: rgba(255, 255, 255, 0.82);
        border: 1px solid rgba(42, 131, 194, 0.38); border-radius: 6px; padding: 4px 10px;
    }
    QLineEdit:focus, QComboBox:focus { border: 1px solid #0e7dbd; }
    QCheckBox { color: #15304b; }
    QCheckBox::indicator { width: 16px; height: 16px; }
    QCheckBox#toggleSwitch::indicator {
        width: 54px; height: 26px; border-radius: 13px;
        background: rgba(120, 144, 168, 0.48);
        border: 1px solid rgba(42, 131, 194, 0.30);
    }
    QCheckBox#toggleSwitch::indicator:checked {
        background: #0f80c2;
        border: 1px solid #55aee2;
    }
    QCheckBox#toggleSwitch::indicator:disabled {
        background: rgba(120, 144, 168, 0.22);
        border: 1px solid rgba(42, 131, 194, 0.16);
    }
    QPushButton {
        border-radius: 8px; padding: 4px 10px; font-weight: 900; letter-spacing: 0px;
        font-size: 13px;
    }
    #primaryButton { color: #ffffff; background: #0f80c2; border: 1px solid #55aee2; }
    #primaryButton:hover { background: #0a6fab; }
    #secondaryButton {
        color: #0d3150; background: rgba(255, 255, 255, 0.66); border: 1px solid rgba(42, 131, 194, 0.38);
    }
    #secondaryButton:hover { color: #ffffff; background: #0f80c2; }
    #iconButton {
        color: #0d3150; background: rgba(255, 255, 255, 0.66); border: 1px solid rgba(42, 131, 194, 0.38);
    }
    #iconButton:hover { background: rgba(15, 128, 194, 0.16); }
    QMenu {
        color: #102033; background: rgba(250, 253, 255, 0.98);
        border: 1px solid rgba(42, 131, 194, 0.34); padding: 6px;
    }
    QMenu::item { padding: 7px 28px 7px 12px; border-radius: 6px; }
    QMenu::item:selected { color: #ffffff; background: #0f80c2; }
    QMenu::item:disabled { color: rgba(16, 32, 51, 0.34); background: transparent; }
    QMenu::item:selected:disabled { color: rgba(16, 32, 51, 0.34); background: transparent; }
    #statusPill {
        border-radius: 10px; padding: 0;
        font-size: 16px; font-weight: 900;
    }
    #statusPill[state="online"] { color: #ffffff; background: #0f80c2; border: 1px solid #58b3e8; }
    #statusPill[state="warning"] { color: #241600; background: #ffd56b; border: 1px solid #ffe6aa; }
    #statusPill[state="offline"] { color: #ffffff; background: #df4057; border: 1px solid #ff94a3; }
    #healthDot { border-radius: 6px; background: #7890a8; }
    #healthDot[state="online"] { background: #0f80c2; }
    #healthDot[state="warning"] { background: #d49a25; }
    #healthDot[state="offline"] { background: #df4057; }
    #logView {
        color: #102033; background: rgba(250, 253, 255, 0.82);
        border: 1px solid rgba(52, 116, 160, 0.24); border-radius: 10px; padding: 12px;
        selection-background-color: #0f80c2;
    }
    #logView QScrollBar:vertical {
        background: rgba(16, 32, 51, 0.06); width: 10px; margin: 6px 2px 6px 0;
        border-radius: 5px;
    }
    #logView QScrollBar::handle:vertical {
        background: rgba(16, 32, 51, 0.26); min-height: 42px; border-radius: 5px;
    }
    #logView QScrollBar::add-line:vertical, #logView QScrollBar::sub-line:vertical { height: 0; }
    #logView QScrollBar::add-page:vertical, #logView QScrollBar::sub-page:vertical { background: transparent; }
    """
