from __future__ import annotations

import subprocess
from pathlib import Path

from core.controller import StadiumMapperController
from core.models import StadiumState, StadiumStatus
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


class StadiumManagerDialog(QDialog):
    """
    Stadium Server Manager — full-screen dialog showing all discovered stadium folders.
    Per-stadium: folder name, st### IDs, status badge, file count, and action buttons.
    """

    rerearch_requested = Signal(str)   # stadium_name
    edit_mapping_requested = Signal(str)

    def __init__(self, controller: StadiumMapperController, parent=None):
        super().__init__(parent)
        self.ctrl = controller
        self.setWindowTitle("🏟 Stadium Server Manager")
        self.resize(1100, 680)
        self.setStyleSheet("background-color: #0B111C; color: #F1F5F9;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # Header
        hdr = QHBoxLayout()
        lbl_title = QLabel("🏟 STADIUM SERVER MANAGER")
        lbl_title.setStyleSheet("color: #19A7FF; font-size: 15px; font-weight: bold;")
        hdr.addWidget(lbl_title)

        self.lbl_path = QLabel()
        self.lbl_path.setStyleSheet("color: #94A3B8; font-size: 11px;")
        hdr.addWidget(self.lbl_path)
        hdr.addStretch(1)

        # Toolbar buttons
        btn_refresh = QPushButton("🔄 Refresh")
        btn_refresh.setStyleSheet(self._btn_style("#19A7FF"))
        btn_refresh.clicked.connect(self._load_data)
        hdr.addWidget(btn_refresh)

        btn_reresearch_all = QPushButton("🌐 Re-research All Resolved")
        btn_reresearch_all.setStyleSheet(self._btn_style("#9B8CFF"))
        btn_reresearch_all.clicked.connect(self._reresearch_all_resolved)
        hdr.addWidget(btn_reresearch_all)

        btn_open_dir = QPushButton("📁 Open Server Folder")
        btn_open_dir.setStyleSheet(self._btn_style("#35D07F"))
        btn_open_dir.clicked.connect(self._open_server_folder)
        hdr.addWidget(btn_open_dir)

        layout.addLayout(hdr)

        # Search filter bar
        filter_row = QHBoxLayout()
        lbl_f = QLabel("⌕ Search:")
        lbl_f.setStyleSheet("color: #94A3B8; font-weight: bold;")
        filter_row.addWidget(lbl_f)

        self.txt_filter = QLineEdit()
        self.txt_filter.setPlaceholderText("Filter by stadium name, ID, or team...")
        self.txt_filter.setFixedWidth(320)
        self.txt_filter.setStyleSheet("background-color: #121C2A; color: #F1F5F9; border: 1px solid #1E293B; border-radius: 4px; padding: 5px;")
        self.txt_filter.textChanged.connect(self._filter_rows)
        filter_row.addWidget(self.txt_filter)
        filter_row.addStretch(1)
        layout.addLayout(filter_row)

        # Table
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels([
            "Stadium Name", "St### IDs", "Status", "Team(s)", "Confidence", "Actions", "Open"
        ])
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeToContents)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setStyleSheet("""
            QTableWidget {
                background-color: #0B111C;
                color: #F1F5F9;
                gridline-color: #1E293B;
                border: none;
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
                background-color: #0F1826;
            }
            QTableWidget::item:selected {
                background-color: #162232;
            }
        """)
        layout.addWidget(self.table, 1)

        # Status bar
        self.lbl_status = QLabel("")
        self.lbl_status.setStyleSheet("color: #94A3B8; font-size: 11px;")
        layout.addWidget(self.lbl_status)

        # Bottom Close
        close_row = QHBoxLayout()
        close_row.addStretch(1)
        btn_close = QPushButton("Close")
        btn_close.setStyleSheet(self._btn_style("#334155"))
        btn_close.clicked.connect(self.accept)
        close_row.addWidget(btn_close)
        layout.addLayout(close_row)

        self._all_states: list[StadiumState] = []
        self._load_data()

    def _btn_style(self, color: str) -> str:
        return f"background-color: {color}; color: #FFFFFF; font-weight: bold; border-radius: 4px; padding: 6px 12px; border: none;"

    def _load_data(self) -> None:
        """Reload all stadium states into the table."""
        server_dir = self.ctrl.config.stadium_server_dir or ""
        self.lbl_path.setText(f"📁 {server_dir}")
        self._all_states = self.ctrl.get_all_states()
        self._render_table(self._all_states)
        self.lbl_status.setText(f"  {len(self._all_states)} stadiums discovered | Server: {server_dir}")

    def _render_table(self, states: list[StadiumState]) -> None:
        """Populate table with stadium states."""
        self.table.setRowCount(0)
        self.table.setRowCount(len(states))

        STATUS_COLORS = {
            "RESOLVED": "#35D07F",
            "REVIEW": "#FFB547",
            "UNRESOLVED": "#FF5C6C",
            "MANUAL": "#19A7FF",
            "SKIPPED": "#94A3B8",
        }

        for row, st in enumerate(states):
            self.table.setRowHeight(row, 36)

            # Stadium Name
            self.table.setItem(row, 0, QTableWidgetItem(st.stadium_name))

            # Stadium IDs
            self.table.setItem(row, 1, QTableWidgetItem(st.stadium_id))

            # Status badge
            status_val = st.status.value if st.status else "UNRESOLVED"
            status_item = QTableWidgetItem(f"  {status_val}  ")
            status_item.setForeground(Qt.white if True else Qt.white)
            from PySide6.QtGui import QColor
            status_item.setBackground(QColor(STATUS_COLORS.get(status_val, "#334155")))
            self.table.setItem(row, 2, status_item)

            # Team(s)
            self.table.setItem(row, 3, QTableWidgetItem(st.identified_clubs or "—"))

            # Confidence
            conf_text = f"{st.confidence:.0%}" if st.confidence else "—"
            self.table.setItem(row, 4, QTableWidgetItem(conf_text))

            # Action buttons cell
            actions_widget = QWidget()
            actions_layout = QHBoxLayout(actions_widget)
            actions_layout.setContentsMargins(2, 2, 2, 2)
            actions_layout.setSpacing(4)

            btn_edit = QPushButton("✏ Edit")
            btn_edit.setStyleSheet("background-color: #19A7FF; color: #FFF; font-size: 10px; font-weight: bold; border-radius: 3px; padding: 2px 6px;")
            btn_edit.clicked.connect(lambda _, n=st.stadium_name: self._on_edit(n))
            actions_layout.addWidget(btn_edit)

            btn_reresearch = QPushButton("🔬 Re-research")
            btn_reresearch.setStyleSheet("background-color: #9B8CFF; color: #FFF; font-size: 10px; font-weight: bold; border-radius: 3px; padding: 2px 6px;")
            btn_reresearch.clicked.connect(lambda _, n=st.stadium_name: self._on_reresearch(n))
            actions_layout.addWidget(btn_reresearch)

            btn_skip = QPushButton("⏭ Skip")
            btn_skip.setStyleSheet("background-color: #334155; color: #FFF; font-size: 10px; font-weight: bold; border-radius: 3px; padding: 2px 6px;")
            btn_skip.clicked.connect(lambda _, n=st.stadium_name: self._on_skip(n))
            actions_layout.addWidget(btn_skip)

            self.table.setCellWidget(row, 5, actions_widget)

            # Open folder button
            open_widget = QWidget()
            open_layout = QHBoxLayout(open_widget)
            open_layout.setContentsMargins(2, 2, 2, 2)
            btn_open = QPushButton("📁")
            btn_open.setStyleSheet("background-color: #121C2A; color: #94A3B8; font-size: 10px; border-radius: 3px; padding: 2px 4px;")
            btn_open.clicked.connect(lambda _, p=st.full_path: self._open_path(p))
            open_layout.addWidget(btn_open)
            self.table.setCellWidget(row, 6, open_widget)

    def _filter_rows(self, text: str) -> None:
        """Filter table rows based on search text."""
        q = text.lower().strip()
        if not q:
            self._render_table(self._all_states)
            return
        filtered = [
            st for st in self._all_states
            if q in st.stadium_name.lower()
            or q in st.stadium_id.lower()
            or q in st.identified_clubs.lower()
            or q in st.status.value.lower()
        ]
        self._render_table(filtered)

    def _on_edit(self, stadium_name: str) -> None:
        from ui.dialogs import EditManualMapDialog
        dlg = EditManualMapDialog(stadium_name, self.ctrl, self)
        if dlg.exec():
            self._load_data()

    def _on_reresearch(self, stadium_name: str) -> None:
        """Clear cache and force re-research for this stadium."""
        self.ctrl.clear_stadium_cache(stadium_name)
        self.ctrl.research_stadium(stadium_name, force_refresh=True)
        self._load_data()

    def _on_skip(self, stadium_name: str) -> None:
        self.ctrl.mark_skipped(stadium_name)
        self._load_data()

    def _reresearch_all_resolved(self) -> None:
        """Clear cache and re-research all currently resolved stadiums."""
        resolved = [st for st in self._all_states if st.status in (StadiumStatus.RESOLVED, StadiumStatus.REVIEW)]
        for st in resolved:
            self.ctrl.clear_stadium_cache(st.stadium_name)
            self.ctrl.research_stadium(st.stadium_name, force_refresh=True)
        self._load_data()

    def _open_server_folder(self) -> None:
        folder = self.ctrl.config.stadium_server_dir
        if folder:
            self._open_path(folder)

    def _open_path(self, path_str: str | None) -> None:
        if path_str:
            p = Path(path_str)
            if p.exists():
                subprocess.Popen(["explorer", str(p.resolve())])
