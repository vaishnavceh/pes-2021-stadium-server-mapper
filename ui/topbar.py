from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QComboBox, QFrame, QHBoxLayout, QLabel, QPushButton


class TopBar(QFrame):
    """
    Top Bar Header Widget (Height 48px).
    Displays brand badge, LED status indicator, Theme selector, Music toggle, Settings, and Contact Admin.
    """

    toggle_music_signal = Signal()
    open_settings_signal = Signal()
    open_contact_admin_signal = Signal()
    theme_changed_signal = Signal(str)

    def __init__(self, app_version: str = "Nightly Build 1.0.0", parent=None):
        super().__init__(parent)
        self.setObjectName("TopBar")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(12)

        # Brand / Title Left
        self.lbl_title = QLabel("PES STADIUM MAPPER")
        self.lbl_title.setObjectName("BrandTitle")
        layout.addWidget(self.lbl_title)

        self.lbl_version = QLabel(app_version)
        self.lbl_version.setObjectName("VersionBadge")
        layout.addWidget(self.lbl_version)

        # LED Status Indicator Center
        self.lbl_status = QLabel("● READY")
        self.lbl_status.setObjectName("StatusLED")
        layout.addWidget(self.lbl_status, 1, alignment=None)

        # Theme Selector Right
        lbl_theme = QLabel("Theme:")
        lbl_theme.setStyleSheet("color: #94A3B8; font-weight: bold; font-size: 11px;")
        layout.addWidget(lbl_theme)

        self.combo_theme = QComboBox()
        self.combo_theme.addItems([
            "PES Night Command (Default)",
            "Midnight Gold Workstation",
            "Sider Technical Slate",
            "Emerald Analytics",
        ])
        self.combo_theme.currentTextChanged.connect(self.theme_changed_signal.emit)
        layout.addWidget(self.combo_theme)

        # Action Buttons Right
        self.btn_music = QPushButton("🎵 Music")
        self.btn_music.setStyleSheet("background-color: #162232; font-weight: bold; border: none; padding: 5px 10px; border-radius: 4px;")
        self.btn_music.clicked.connect(self.toggle_music_signal.emit)
        layout.addWidget(self.btn_music)

        self.btn_settings = QPushButton("⚙ Settings")
        self.btn_settings.setStyleSheet("background-color: #162232; font-weight: bold; border: none; padding: 5px 10px; border-radius: 4px;")
        self.btn_settings.clicked.connect(self.open_settings_signal.emit)
        layout.addWidget(self.btn_settings)

        self.btn_contact = QPushButton("💬 Contact Admin")
        self.btn_contact.setStyleSheet("background-color: #162232; font-weight: bold; border: none; padding: 5px 10px; border-radius: 4px;")
        self.btn_contact.clicked.connect(self.open_contact_admin_signal.emit)
        layout.addWidget(self.btn_contact)

    def set_status_text(self, text: str, color: str = "#19A7FF") -> None:
        """Update central LED status text."""
        self.lbl_status.setText(text)
        self.lbl_status.setStyleSheet(f"color: {color}; font-weight: bold; font-size: 12px;")
