from __future__ import annotations

import datetime
from pathlib import Path
from typing import Any

from core.controller import StadiumMapperController
from map_generator import MapGenerator
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

COMMON_COMP_IDS = [
    ("1", "Premier League (England)"),
    ("2", "UEFA Champions League"),
    ("3", "Copa Libertadores"),
    ("5", "Serie A (Italy)"),
    ("6", "La Liga (Spain)"),
    ("7", "Ligue 1 (France)"),
    ("8", "Bundesliga (Germany)"),
    ("12", "UEFA Europa League"),
    ("13", "UEFA Super Cup"),
    ("101", "FIFA World Cup"),
    ("102", "UEFA Euro Championship"),
    ("103", "Copa America"),
]


class CompetitionManagerDialog(QDialog):
    """
    Competition & Cup Finals Stadium Manager Subform Modal.
    Allows mapping stadiums to Competition IDs for map_competitions.txt & map_comp_finals.txt.
    """

    def __init__(self, controller: StadiumMapperController, parent=None):
        super().__init__(parent)
        self.ctrl = controller
        self.setWindowTitle("🏆 Competition & Finals Stadium Manager")
        self.resize(920, 640)
        self.setStyleSheet("background-color: #0B111C; color: #F1F5F9;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # Header
        hdr_f = QFrame()
        hdr_f.setStyleSheet("background-color: #121C2A; border: 1px solid #1E293B; border-radius: 6px; padding: 10px;")
        hdr_l = QVBoxLayout(hdr_f)
        hdr_l.setContentsMargins(8, 8, 8, 8)

        lbl_t = QLabel("🏆 COMPETITION & FINALS STADIUM MANAGER")
        lbl_t.setStyleSheet("color: #19A7FF; font-size: 14px; font-weight: bold;")
        hdr_l.addWidget(lbl_t)

        lbl_sub = QLabel("Assign stadiums to competition IDs (map_competitions.txt) and cup finals (map_comp_finals.txt)")
        lbl_sub.setStyleSheet("color: #94A3B8; font-size: 11px;")
        hdr_l.addWidget(lbl_sub)

        layout.addWidget(hdr_f)

        # Tabs
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane { border: 1px solid #1E293B; background: #0B111C; }
            QTabBar::tab { background: #121C2A; color: #94A3B8; padding: 8px 16px; font-weight: bold; border: none; }
            QTabBar::tab:selected { background: #19A7FF; color: #FFFFFF; }
        """)

        # Tab 1: map_competitions.txt
        self.tab_comp = QWidget()
        self._build_tab_ui(self.tab_comp, "map_competitions.txt")
        self.tabs.addTab(self.tab_comp, "⚽ Competitions Map (map_competitions.txt)")

        # Tab 2: map_comp_finals.txt
        self.tab_finals = QWidget()
        self._build_tab_ui(self.tab_finals, "map_comp_finals.txt")
        self.tabs.addTab(self.tab_finals, "🏆 Cup Finals Map (map_comp_finals.txt)")

        layout.addWidget(self.tabs, 1)

        # Bottom Actions
        bottom_row = QHBoxLayout()
        bottom_row.addStretch(1)

        btn_close = QPushButton("Close")
        btn_close.setStyleSheet("background-color: #334155; color: #FFFFFF; font-weight: bold; padding: 8px 16px; border-radius: 4px;")
        btn_close.clicked.connect(self.accept)
        bottom_row.addWidget(btn_close)

        layout.addLayout(bottom_row)

    def _build_tab_ui(self, tab_widget: QWidget, target_filename: str) -> None:
        layout = QVBoxLayout(tab_widget)
        layout.setContentsMargins(10, 10, 10, 10)

        # Add Row Control Frame
        add_frame = QFrame()
        add_frame.setStyleSheet("background-color: #121C2A; border: 1px solid #1E293B; border-radius: 6px; padding: 6px;")
        add_l = QHBoxLayout(add_frame)

        lbl_c = QLabel("Comp ID:")
        lbl_c.setStyleSheet("color: #94A3B8; font-weight: bold;")
        add_l.addWidget(lbl_c)

        combo_comp = QComboBox()
        combo_comp.setEditable(True)
        for cid, cname in COMMON_COMP_IDS:
            combo_comp.addItem(f"{cid} — {cname}", cid)
        add_l.addWidget(combo_comp, 1)

        lbl_s = QLabel("Stadium:")
        lbl_s.setStyleSheet("color: #94A3B8; font-weight: bold;")
        add_l.addWidget(lbl_s)

        combo_stad = QComboBox()
        for s in self.ctrl.discovered_stadiums:
            combo_stad.addItem(s.display_name, s.display_name)
        add_l.addWidget(combo_stad, 1)

        btn_add = QPushButton("➕ Add Row")
        btn_add.setStyleSheet("background-color: #19A7FF; color: #FFF; font-weight: bold; padding: 6px 12px; border-radius: 4px;")
        add_l.addWidget(btn_add)

        btn_rem = QPushButton("❌ Remove Selected")
        btn_rem.setStyleSheet("background-color: #FF5C6C; color: #FFF; font-weight: bold; padding: 6px 12px; border-radius: 4px;")
        add_l.addWidget(btn_rem)

        layout.addWidget(add_frame)

        # Table
        table = QTableWidget(0, 5)
        table.setHorizontalHeaderLabels(["STATUS", "COMP ID", "STADIUM ID", "STADIUM NAME", "STADIUM PATH"])
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setStyleSheet("background-color: #0B111C; color: #F1F5F9; gridline-color: #1E293B;")
        layout.addWidget(table, 1)

        # Bottom Bar
        b_bar = QHBoxLayout()
        btn_save = QPushButton(f"💾 Save {target_filename}")
        btn_save.setStyleSheet("background-color: #35D07F; color: #FFF; font-weight: bold; padding: 8px 16px; border-radius: 4px;")
        b_bar.addWidget(btn_save)
        b_bar.addStretch(1)
        layout.addLayout(b_bar)

        # Wire handlers
        btn_add.clicked.connect(lambda: self._add_comp_row(table, combo_comp, combo_stad))
        btn_rem.clicked.connect(lambda: self._remove_comp_row(table))
        btn_save.clicked.connect(lambda: self._save_comp_file(table, target_filename))

        # Load file
        self._load_file_to_table(table, target_filename)

    def _add_comp_row(self, table: QTableWidget, combo_comp: QComboBox, combo_stad: QComboBox) -> None:
        raw_cid = combo_comp.currentText().split("—")[0].strip()
        sname = combo_stad.currentText()
        if not raw_cid or not sname:
            return

        s_obj = next((s for s in self.ctrl.discovered_stadiums if s.display_name == sname), None)
        sid = s_obj.primary_id() if s_obj else "000"

        r = table.rowCount()
        table.insertRow(r)
        table.setItem(r, 0, QTableWidgetItem("  ✅ ACTIVE  "))
        table.setItem(r, 1, QTableWidgetItem(raw_cid))
        table.setItem(r, 2, QTableWidgetItem(sid))
        table.setItem(r, 3, QTableWidgetItem(sname))
        table.setItem(r, 4, QTableWidgetItem(sname))

    def _remove_comp_row(self, table: QTableWidget) -> None:
        curr = table.currentRow()
        if curr >= 0:
            table.removeRow(curr)

    def _load_file_to_table(self, table: QTableWidget, filename: str) -> None:
        server_dir = Path(self.ctrl.config.stadium_server_dir or str(self.ctrl.base_dir))
        file_path = server_dir / filename
        table.setRowCount(0)

        if not file_path.exists():
            return

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                for line in f:
                    sline = line.strip()
                    if not sline:
                        continue
                    is_disabled = sline.startswith("#")
                    clean = sline.lstrip("#").strip()
                    parts = [p.strip() for p in clean.split(",")]
                    if len(parts) >= 4:
                        r = table.rowCount()
                        table.insertRow(r)
                        st_item = QTableWidgetItem("  🚫 DISABLED  " if is_disabled else "  ✅ ACTIVE  ")
                        st_item.setForeground(QColor("#FF5C6C" if is_disabled else "#35D07F"))
                        table.setItem(r, 0, st_item)
                        table.setItem(r, 1, QTableWidgetItem(parts[0]))
                        table.setItem(r, 2, QTableWidgetItem(parts[1]))
                        table.setItem(r, 3, QTableWidgetItem(parts[2]))
                        table.setItem(r, 4, QTableWidgetItem(parts[3]))
        except Exception as e:
            self.ctrl.logger.warning(f"Could not read {filename}: {e}")

    def _save_comp_file(self, table: QTableWidget, filename: str) -> None:
        entries: list[dict[str, Any]] = []
        for r in range(table.rowCount()):
            it_status = table.item(r, 0)
            it_cid = table.item(r, 1)
            it_sid = table.item(r, 2)
            it_sname = table.item(r, 3)
            it_spath = table.item(r, 4)
            if not (it_cid and it_sid and it_sname and it_spath):
                continue
            is_disabled = "DISABLED" in (it_status.text() if it_status else "")
            entries.append({
                "comp_id": it_cid.text().strip(),
                "stadium_id": it_sid.text().strip(),
                "stadium_name": it_sname.text().strip(),
                "stadium_path": it_spath.text().strip(),
                "disabled": is_disabled,
            })

        server_dir = Path(self.ctrl.config.stadium_server_dir or str(self.ctrl.base_dir))
        generator = MapGenerator(server_dir, self.ctrl.logger)

        if filename == "map_competitions.txt":
            success, msg = generator.write_competitions_map(entries)
        else:
            success, msg = generator.write_comp_finals_map(entries)

        if success:
            QMessageBox.information(self, "Saved", f"✅ {msg}")
        else:
            QMessageBox.critical(self, "Error", f"❌ {msg}")
