from __future__ import annotations

import datetime
import shutil
import subprocess
from pathlib import Path
from typing import Any

from core.controller import StadiumMapperController
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)


class StadiumManagerDialog(QDialog):
    """
    Stadium Server Manager — Enable / Disable Stadiums Subform Modal.
    Toggles installed stadiums ON (Active) or OFF (Disabled with #) directly in map_teams.txt.
    """

    def __init__(self, controller: StadiumMapperController, parent=None):
        super().__init__(parent)
        self.ctrl = controller
        self.setWindowTitle("🏟️ Stadium Server Manager — Enable / Disable Stadiums")
        self.resize(920, 640)
        self.setStyleSheet("""
            QDialog {
                background-color: #0B111C;
                color: #F1F5F9;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        # Header Banner
        hdr_frame = QFrame()
        hdr_frame.setStyleSheet("background-color: #121C2A; border: 1px solid #1E293B; border-radius: 6px; padding: 10px;")
        hdr_layout = QVBoxLayout(hdr_frame)
        hdr_layout.setContentsMargins(8, 8, 8, 8)
        hdr_layout.setSpacing(4)

        lbl_title = QLabel("🏟️ STADIUM SERVER MANAGER")
        lbl_title.setStyleSheet("color: #19A7FF; font-size: 14px; font-weight: bold;")
        hdr_layout.addWidget(lbl_title)

        lbl_sub = QLabel("Enable (Active) or Disable (Commented with #) stadiums directly in map_teams.txt")
        lbl_sub.setStyleSheet("color: #94A3B8; font-size: 11px;")
        hdr_layout.addWidget(lbl_sub)

        self.server_dir = Path(self.ctrl.config.stadium_server_dir or str(self.ctrl.base_dir)).resolve()
        lbl_path = QLabel(f"📁 Server Root: {self.server_dir}")
        lbl_path.setStyleSheet("color: #64748B; font-size: 10px;")
        hdr_layout.addWidget(lbl_path)

        layout.addWidget(hdr_frame)

        # Controls & Search Bar
        ctrl_frame = QFrame()
        ctrl_frame.setStyleSheet("background-color: #121C2A; border: 1px solid #1E293B; border-radius: 6px; padding: 6px;")
        ctrl_layout = QHBoxLayout(ctrl_frame)
        ctrl_layout.setContentsMargins(6, 6, 6, 6)
        ctrl_layout.setSpacing(8)

        lbl_search = QLabel("🔍 Search:")
        lbl_search.setStyleSheet("color: #94A3B8; font-weight: bold; font-size: 11px;")
        ctrl_layout.addWidget(lbl_search)

        self.txt_search = QLineEdit()
        self.txt_search.setPlaceholderText("Filter by stadium name, ID, team...")
        self.txt_search.setStyleSheet("background-color: #0B111C; color: #F1F5F9; border: 1px solid #1E293B; border-radius: 4px; padding: 5px;")
        self.txt_search.textChanged.connect(self._filter_table)
        ctrl_layout.addWidget(self.txt_search, 1)

        btn_toggle = QPushButton("⚡ Toggle Selected")
        btn_toggle.setStyleSheet(self._btn_style("#162232", "#F1F5F9"))
        btn_toggle.clicked.connect(self._toggle_selected)
        ctrl_layout.addWidget(btn_toggle)

        btn_enable_all = QPushButton("✅ Enable All")
        btn_enable_all.setStyleSheet(self._btn_style("#162232", "#35D07F"))
        btn_enable_all.clicked.connect(lambda: self._set_all(True))
        ctrl_layout.addWidget(btn_enable_all)

        btn_disable_all = QPushButton("🚫 Disable All")
        btn_disable_all.setStyleSheet(self._btn_style("#162232", "#FF5C6C"))
        btn_disable_all.clicked.connect(lambda: self._set_all(False))
        ctrl_layout.addWidget(btn_disable_all)

        layout.addWidget(ctrl_frame)

        # Table
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["STATUS", "TEAM ID", "STADIUM ID", "STADIUM NAME", "STADIUM PATH"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setStyleSheet("""
            QTableWidget {
                background-color: #0B111C;
                color: #F1F5F9;
                gridline-color: #1E293B;
                border: 1px solid #1E293B;
                border-radius: 4px;
                font-size: 12px;
            }
            QHeaderView::section {
                background-color: #121C2A;
                color: #19A7FF;
                font-weight: bold;
                border: none;
                padding: 6px;
            }
            QTableWidget::item:alternate {
                background-color: #0F172A;
            }
            QTableWidget::item:selected {
                background-color: #1E293B;
            }
        """)
        self.table.itemDoubleClicked.connect(lambda _: self._toggle_selected())
        layout.addWidget(self.table, 1)

        # Footer Actions Bar
        footer_layout = QHBoxLayout()
        self.lbl_stats = QLabel("Loading stadiums...")
        self.lbl_stats.setStyleSheet("color: #94A3B8; font-size: 11px;")
        footer_layout.addWidget(self.lbl_stats)
        footer_layout.addStretch(1)

        btn_open = QPushButton("📁 Open Folder")
        btn_open.setStyleSheet(self._btn_style("#1E293B", "#94A3B8"))
        btn_open.clicked.connect(self._open_server_dir)
        footer_layout.addWidget(btn_open)

        btn_save = QPushButton("💾 Save Changes")
        btn_save.setStyleSheet("background-color: #35D07F; color: #FFFFFF; font-weight: bold; padding: 8px 18px; border-radius: 4px; border: none;")
        btn_save.clicked.connect(self._save_changes)
        footer_layout.addWidget(btn_save)

        btn_close = QPushButton("Close")
        btn_close.setStyleSheet(self._btn_style("#334155", "#FFFFFF"))
        btn_close.clicked.connect(self.accept)
        footer_layout.addWidget(btn_close)

        layout.addLayout(footer_layout)

        self.items: list[dict[str, Any]] = []
        self._load_map_items()

    def _btn_style(self, bg: str, fg: str) -> str:
        return f"background-color: {bg}; color: {fg}; font-weight: bold; border: 1px solid #1E293B; border-radius: 4px; padding: 6px 12px;"

    def _load_map_items(self) -> None:
        """Load stadium lines from map_teams.txt, or from current controller mappings if missing."""
        map_file = self.server_dir / "map_teams.txt"
        self.items = []

        if map_file.exists():
            try:
                with open(map_file, "r", encoding="utf-8") as f:
                    for idx, line in enumerate(f):
                        sline = line.strip()
                        if not sline:
                            continue
                        is_enabled = not sline.startswith("#")
                        clean = sline.lstrip("#").strip()
                        parts = [p.strip() for p in clean.split(",")]
                        if len(parts) >= 4:
                            self.items.append({
                                "line_idx": idx,
                                "enabled": is_enabled,
                                "team_id": parts[0],
                                "stadium_id": parts[1],
                                "stadium_name": parts[2],
                                "stadium_path": parts[3],
                            })
            except Exception as e:
                QMessageBox.warning(self, "Read Error", f"Could not read map_teams.txt: {e}")

        # If map_teams.txt is empty or missing, populate from controller's mapped rows
        if not self.items:
            mapped_rows = self.ctrl.build_mappings()
            for idx, r in enumerate(mapped_rows):
                p_val = r.stadium_path or r.stadium_name
                is_disabled = (
                    p_val.lower() in {s.lower() for s in self.ctrl.disabled_stadiums}
                    or r.stadium_name.lower() in {s.lower() for s in self.ctrl.disabled_stadiums}
                )
                self.items.append({
                    "line_idx": idx,
                    "enabled": not is_disabled,
                    "team_id": str(r.team_id),
                    "stadium_id": str(r.stadium_id),
                    "stadium_name": r.stadium_name,
                    "stadium_path": p_val,
                })

        self._render_table()

    def _render_table(self) -> None:
        """Render items in table widget according to search filter."""
        q = self.txt_search.text().lower().strip()
        filtered = [
            it for it in self.items
            if not q
            or q in it["stadium_name"].lower()
            or q in it["stadium_path"].lower()
            or q in it["team_id"]
            or q in it["stadium_id"]
        ]

        self.table.setRowCount(0)
        self.table.setRowCount(len(filtered))

        for row_idx, it in enumerate(filtered):
            self.table.setRowHeight(row_idx, 32)

            # Status column
            if it["enabled"]:
                status_item = QTableWidgetItem("  ✅ ENABLED  ")
                status_item.setForeground(QColor("#35D07F"))
            else:
                status_item = QTableWidgetItem("  🚫 DISABLED  ")
                status_item.setForeground(QColor("#FF5C6C"))
            status_item.setTextAlignment(Qt.AlignCenter)
            status_item.setData(Qt.UserRole, it["line_idx"])
            self.table.setItem(row_idx, 0, status_item)

            # Team ID
            tid_item = QTableWidgetItem(it["team_id"])
            tid_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row_idx, 1, tid_item)

            # Stadium ID
            sid_item = QTableWidgetItem(it["stadium_id"])
            sid_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row_idx, 2, sid_item)

            # Stadium Name
            self.table.setItem(row_idx, 3, QTableWidgetItem(it["stadium_name"]))

            # Stadium Path
            self.table.setItem(row_idx, 4, QTableWidgetItem(it["stadium_path"]))

        active_count = sum(1 for it in self.items if it["enabled"])
        total_count = len(self.items)
        self.lbl_stats.setText(f"Total: {total_count} stadiums | Active: {active_count} | Disabled: {total_count - active_count}")

    def _filter_table(self) -> None:
        self._render_table()

    def _toggle_selected(self) -> None:
        """Toggle enabled state of selected rows."""
        selected_rows = self.table.selectionModel().selectedRows()
        if not selected_rows:
            curr = self.table.currentRow()
            if curr >= 0:
                selected_rows = [self.table.model().index(curr, 0)]

        for index in selected_rows:
            r = index.row()
            item = self.table.item(r, 0)
            if item:
                line_idx = item.data(Qt.UserRole)
                target = next((it for it in self.items if it["line_idx"] == line_idx), None)
                if target:
                    target["enabled"] = not target["enabled"]

        self._render_table()

    def _set_all(self, enabled: bool) -> None:
        """Set all items to enabled or disabled."""
        for it in self.items:
            it["enabled"] = enabled
        self._render_table()

    def _save_changes(self) -> None:
        """Save enabled/disabled states back to map_teams.txt and create timestamped backup."""
        if not self.items:
            QMessageBox.warning(self, "No Items", "No stadium entries to save.")
            return

        map_file = self.server_dir / "map_teams.txt"
        backup_dir = self.server_dir / "settings_PSM" / "backup_map"
        backup_dir.mkdir(parents=True, exist_ok=True)

        # 1. Create backup if file exists
        if map_file.exists():
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            bak_path = backup_dir / f"map_teams_manager_backup_{timestamp}.txt"
            try:
                shutil.copy2(str(map_file), str(bak_path))
            except Exception as e:
                self.ctrl.logger.warning(f"Could not create backup: {e}")

        # 2. Format lines
        new_lines = [
            "# PES 2021 Stadium Server - Team-to-Stadium Mapping\n",
            "# Updated via Stadium Server Manager\n",
            f"# Date: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n",
            "# Format: TEAM_ID,STADIUM_ID,STADIUM_NAME,STADIUM_PATH\n",
            "#\n",
        ]

        # Update controller disabled_stadiums
        self.ctrl.disabled_stadiums.clear()
        active_count = 0
        disabled_count = 0

        for it in self.items:
            prefix = "" if it["enabled"] else "#"
            line = f"{prefix}{it['team_id']},{it['stadium_id']},{it['stadium_name']},{it['stadium_path']}\n"
            new_lines.append(line)

            if it["enabled"]:
                active_count += 1
            else:
                disabled_count += 1
                self.ctrl.disabled_stadiums.add(it["stadium_path"])
                self.ctrl.disabled_stadiums.add(it["stadium_name"])

        # 3. Write map_teams.txt
        try:
            with open(map_file, "w", encoding="utf-8") as f:
                f.writelines(new_lines)

            # Persist state
            self.ctrl.cache.save_state(self.ctrl.manual_mappings, self.ctrl.skipped_stadiums, self.ctrl.disabled_stadiums)

            QMessageBox.information(
                self,
                "Saved Successfully",
                f"✅ map_teams.txt successfully updated!\n\n"
                f"Active Stadiums: {active_count}\n"
                f"Disabled Stadiums: {disabled_count}\n"
                f"Total: {len(self.items)}\n\n"
                f"Backup saved in: settings_PSM/backup_map/"
            )
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Save Error", f"Failed to save map_teams.txt:\n{e}")

    def _open_server_dir(self) -> None:
        """Open stadium server directory in Windows Explorer."""
        if self.server_dir.exists():
            subprocess.Popen(["explorer", str(self.server_dir)])

