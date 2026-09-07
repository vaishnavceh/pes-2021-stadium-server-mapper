from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QLabel,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
)


class Sidebar(QFrame):
    """
    Left Navigation Sidebar Rail Widget (~240px width).
    Hosts navigation action buttons, research provider selection group, and stadium server root path picker.
    """

    scan_clicked = Signal()
    research_clicked = Signal()
    unresolved_clicked = Signal()
    manager_clicked = Signal()
    write_map_clicked = Signal()
    dry_run_clicked = Signal()
    palette_clicked = Signal()
    provider_changed = Signal(str)
    change_path_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Sidebar")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 16, 12, 16)
        layout.setSpacing(6)

        # Engine Navigation Header
        lbl_nav = QLabel("ENGINE NAVIGATION")
        lbl_nav.setObjectName("SidebarSectionHeader")
        layout.addWidget(lbl_nav)

        # Action Buttons
        self.btn_scan = QPushButton("📊 Scan Stadiums")
        self.btn_scan.setObjectName("BtnScan")
        self.btn_scan.setProperty("class", "NavButton")
        self.btn_scan.clicked.connect(self.scan_clicked.emit)
        layout.addWidget(self.btn_scan)

        self.btn_research = QPushButton("🌐 Live Web Research")
        self.btn_research.setProperty("class", "NavButton")
        self.btn_research.clicked.connect(self.research_clicked.emit)
        layout.addWidget(self.btn_research)

        self.btn_unresolved = QPushButton("⚡ Unresolved Resolver")
        self.btn_unresolved.setObjectName("BtnUnresolved")
        self.btn_unresolved.setProperty("class", "NavButton")
        self.btn_unresolved.clicked.connect(self.unresolved_clicked.emit)
        layout.addWidget(self.btn_unresolved)

        self.btn_manager = QPushButton("🏟 Stadium Server Manager")
        self.btn_manager.setProperty("class", "NavButton")
        self.btn_manager.clicked.connect(self.manager_clicked.emit)
        layout.addWidget(self.btn_manager)

        self.btn_write = QPushButton("💾 Write map_teams.txt")
        self.btn_write.setObjectName("BtnWriteMap")
        self.btn_write.setProperty("class", "NavButton")
        self.btn_write.clicked.connect(self.write_map_clicked.emit)
        layout.addWidget(self.btn_write)

        self.btn_dry_run = QPushButton("📊 Dry Run Report")
        self.btn_dry_run.setProperty("class", "NavButton")
        self.btn_dry_run.clicked.connect(self.dry_run_clicked.emit)
        layout.addWidget(self.btn_dry_run)

        self.btn_palette = QPushButton("⌨ Command Palette")
        self.btn_palette.setProperty("class", "NavButton")
        self.btn_palette.clicked.connect(self.palette_clicked.emit)
        layout.addWidget(self.btn_palette)

        # Research Provider Selector Group
        lbl_prov = QLabel("RESEARCH PROVIDER")
        lbl_prov.setObjectName("SidebarSectionHeader")
        layout.addWidget(lbl_prov)

        self.provider_group = QButtonGroup(self)
        providers = [
            ("DuckDuckGo", "duckduckgo"),
            ("Wikipedia", "wikipedia"),
            ("Google", "google"),
            ("Bing", "bing"),
        ]

        for idx, (label_text, prov_key) in enumerate(providers):
            radio = QRadioButton(label_text)
            radio.setProperty("prov_key", prov_key)
            if idx == 0:
                radio.setChecked(True)
            self.provider_group.addButton(radio, idx)
            layout.addWidget(radio)

        self.provider_group.idToggled.connect(self._on_provider_toggled)

        layout.addStretch(1)

        # Bottom Path Section
        lbl_root = QLabel("STADIUM SERVER ROOT")
        lbl_root.setObjectName("SidebarSectionHeader")
        layout.addWidget(lbl_root)

        self.lbl_path = QLabel("-")
        self.lbl_path.setWordWrap(True)
        self.lbl_path.setStyleSheet("color: #94A3B8; font-size: 10px;")
        layout.addWidget(self.lbl_path)

        self.btn_change_path = QPushButton("Change Path")
        self.btn_change_path.setStyleSheet("background-color: #121C2A; color: #19A7FF; font-weight: bold; border: 1px solid #1E293B; border-radius: 4px; padding: 4px;")
        self.btn_change_path.clicked.connect(self.change_path_clicked.emit)
        layout.addWidget(self.btn_change_path)

    def _on_provider_toggled(self, id_val: int, checked: bool) -> None:
        if checked:
            btn = self.provider_group.button(id_val)
            if btn:
                self.provider_changed.emit(btn.property("prov_key"))

    def set_server_path(self, path_str: str) -> None:
        """Update path display string."""
        self.lbl_path.setText(path_str)

    def update_all_resolved_badge(self, all_resolved: bool, unresolved_count: int) -> None:
        """Update resolver sidebar button appearance reactively based on unresolved status."""
        if all_resolved:
            self.btn_unresolved.setText("✅ All Resolved")
            self.btn_unresolved.setStyleSheet("background-color: #35D07F; color: #FFFFFF; font-weight: bold; border: none; border-radius: 6px; padding: 9px 14px; text-align: left;")
        else:
            self.btn_unresolved.setText(f"⚡ Resolver ({unresolved_count})")
            self.btn_unresolved.setStyleSheet("background-color: #FF5C6C; color: #FFFFFF; font-weight: bold; border: none; border-radius: 6px; padding: 9px 14px; text-align: left;")
