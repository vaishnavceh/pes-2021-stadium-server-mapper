from __future__ import annotations

import webbrowser
from typing import Any, Sequence

from core.controller import StadiumMapperController
from core.models import MappedRow, StadiumState, StadiumStatus
from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


class TeamAutocompleteLineEdit(QLineEdit):
    """QLineEdit with live suggestions popup as the user types team names."""

    team_selected_signal = Signal(int, str)  # team_id, official_name

    def __init__(self, pdf_team_dict: dict[int, str], parent=None):
        super().__init__(parent)
        self.pdf_teams = pdf_team_dict  # id -> name

        # Popup list widget
        self.popup = QListWidget(self.window())
        self.popup.setWindowFlags(Qt.Popup)
        self.popup.setFocusPolicy(Qt.NoFocus)
        self.popup.setFocusProxy(self)
        self.popup.itemClicked.connect(self._on_item_clicked)
        self.popup.hide()

        self.textChanged.connect(self._on_text_changed)

    def _on_text_changed(self, text: str) -> None:
        q = text.lower().strip()
        if len(q) < 2:
            self.popup.hide()
            return

        matches: list[tuple[int, str]] = []
        for tid, tname in self.pdf_teams.items():
            if q in tname.lower() or q == str(tid):
                matches.append((tid, tname))
                if len(matches) >= 12:
                    break

        if not matches:
            self.popup.hide()
            return

        self.popup.clear()
        for tid, tname in matches:
            item = QListWidgetItem(f"{tname}  (ID: {tid})")
            item.setData(Qt.UserRole, (tid, tname))
            self.popup.addItem(item)

        # Position popup below line edit
        pos = self.mapToGlobal(self.rect().bottomLeft())
        self.popup.move(pos)
        self.popup.resize(self.width(), min(180, len(matches) * 24 + 10))
        self.popup.show()

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        data = item.data(Qt.UserRole)
        if data:
            tid, tname = data
            self.setText(tname)
            self.popup.hide()
            self.team_selected_signal.emit(tid, tname)


class EditManualMapDialog(QDialog):
    """4-Column Manual Stadium Mapper Editor Modal."""

    def __init__(self, stadium_name: str, controller: StadiumMapperController, parent=None):
        super().__init__(parent)
        self.ctrl = controller
        self.stadium_name = stadium_name

        self.setWindowTitle(f"Edit 4-Column Mapping — {stadium_name}")
        self.resize(680, 440)
        self.setStyleSheet("background-color: #0B111C; color: #F1F5F9;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Top Banner
        lbl_hdr = QLabel(f"⚽ 4-Column Mapping Editor: {stadium_name}")
        lbl_hdr.setStyleSheet("color: #19A7FF; font-size: 14px; font-weight: bold;")
        layout.addWidget(lbl_hdr)

        # Mappings Table
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Team ID", "Stadium ID", "Stadium Name", "Stadium Path"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setStyleSheet("background-color: #121C2A; color: #F1F5F9; gridline-color: #1E293B;")
        layout.addWidget(self.table)

        # Live Autocomplete Row Frame
        auto_frame = QFrame()
        auto_frame.setStyleSheet("background-color: #121C2A; border: 1px solid #1E293B; border-radius: 6px; padding: 8px;")
        auto_layout = QHBoxLayout(auto_frame)
        auto_layout.setContentsMargins(6, 6, 6, 6)

        lbl_auto = QLabel("Team Search:")
        lbl_auto.setStyleSheet("color: #94A3B8; font-weight: bold;")
        auto_layout.addWidget(lbl_auto)

        self.txt_autocomplete = TeamAutocompleteLineEdit(self.ctrl.pdf_parser.id_to_name, self)
        self.txt_autocomplete.setPlaceholderText("Type team name to search PES PDF database (e.g., Real Madrid)...")
        self.txt_autocomplete.team_selected_signal.connect(self._on_team_selected)
        auto_layout.addWidget(self.txt_autocomplete)

        btn_add_team = QPushButton("➕ Add Row")
        btn_add_team.setStyleSheet("background-color: #19A7FF; color: #FFFFFF; font-weight: bold; border-radius: 4px; padding: 6px 12px;")
        btn_add_team.clicked.connect(self._add_row)
        auto_layout.addWidget(btn_add_team)

        btn_rem_team = QPushButton("❌ Remove Row")
        btn_rem_team.setStyleSheet("background-color: #FF5C6C; color: #FFFFFF; font-weight: bold; border-radius: 4px; padding: 6px 12px;")
        btn_rem_team.clicked.connect(self._remove_selected_row)
        auto_layout.addWidget(btn_rem_team)

        layout.addWidget(auto_frame)

        # Action Buttons Bottom
        btn_layout = QHBoxLayout()
        btn_save = QPushButton("💾 Save Mappings")
        btn_save.setStyleSheet("background-color: #35D07F; color: #FFFFFF; font-weight: bold; padding: 8px 16px; border-radius: 4px;")
        btn_save.clicked.connect(self._on_save)
        btn_layout.addWidget(btn_save)

        btn_cancel = QPushButton("Cancel")
        btn_cancel.setStyleSheet("background-color: #334155; color: #FFFFFF; font-weight: bold; padding: 8px 16px; border-radius: 4px;")
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_cancel)

        layout.addLayout(btn_layout)

        self._populate_rows()

    def _populate_rows(self) -> None:
        state = self.ctrl.get_stadium_state(self.stadium_name)
        rows = state.mapped_rows if state.mapped_rows else []

        if not rows:
            s_obj = next((s for s in self.ctrl.discovered_stadiums if s.display_name == self.stadium_name), None)
            st_id = s_obj.primary_id() if s_obj else "000"
            rows = [MappedRow(team_id=0, stadium_id=st_id, stadium_name=self.stadium_name, stadium_path=self.stadium_name)]

        for r in rows:
            self._add_row_values(r.team_id, r.stadium_id, r.stadium_name, r.stadium_path)

    def _add_row_values(self, tid: int, sid: str, sname: str, spath: str) -> None:
        row_idx = self.table.rowCount()
        self.table.insertRow(row_idx)
        self.table.setItem(row_idx, 0, QTableWidgetItem(str(tid)))
        self.table.setItem(row_idx, 1, QTableWidgetItem(str(sid)))
        self.table.setItem(row_idx, 2, QTableWidgetItem(str(sname)))
        self.table.setItem(row_idx, 3, QTableWidgetItem(str(spath)))

    def _add_row(self) -> None:
        s_obj = next((s for s in self.ctrl.discovered_stadiums if s.display_name == self.stadium_name), None)
        st_id = s_obj.primary_id() if s_obj else "000"
        self._add_row_values(0, st_id, self.stadium_name, self.stadium_name)

    def _remove_selected_row(self) -> None:
        curr_row = self.table.currentRow()
        if curr_row >= 0 and self.table.rowCount() > 1:
            self.table.removeRow(curr_row)

    def _on_team_selected(self, tid: int, tname: str) -> None:
        curr_row = self.table.currentRow()
        if curr_row < 0:
            curr_row = self.table.rowCount() - 1
        if curr_row >= 0:
            self.table.setItem(curr_row, 0, QTableWidgetItem(str(tid)))

    def _on_save(self) -> None:
        mapped_rows: list[MappedRow] = []
        for r in range(self.table.rowCount()):
            try:
                item_tid = self.table.item(r, 0)
                item_sid = self.table.item(r, 1)
                item_sname = self.table.item(r, 2)
                item_spath = self.table.item(r, 3)
                if not (item_tid and item_sid and item_sname and item_spath):
                    continue
                tid = int(item_tid.text().strip())
                sid = item_sid.text().strip()
                sname = item_sname.text().strip()
                spath = item_spath.text().strip()
                mapped_rows.append(MappedRow(team_id=tid, stadium_id=sid, stadium_name=sname, stadium_path=spath, status="MANUAL", confidence=1.0))
            except Exception:
                pass

        if mapped_rows:
            self.ctrl.set_manual_mappings(self.stadium_name, mapped_rows)
            self.accept()
        else:
            QMessageBox.warning(self, "No Mappings", "Please add at least one valid Team ID row before saving.")


class UnresolvedResolverDialog(QDialog):
    """
    Interactive Unresolved Stadium Resolver Modal Dialog.
    Steps through all unresolved stadiums with live team search from PDF,
    pre-filled web research clues, multi-team assignment, Skip, and Save & Next.
    """

    def __init__(self, controller: StadiumMapperController, parent=None):
        super().__init__(parent)
        self.ctrl = controller
        self.setWindowTitle("⚡ Interactive Unresolved Stadium Resolver")
        self.resize(780, 620)
        self.setStyleSheet("background-color: #0B111C; color: #F1F5F9;")

        self.unresolved_stadiums: list[str] = []
        self._refresh_unresolved()
        self.current_idx = 0

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # Header
        self.lbl_header = QLabel("⚡ UNRESOLVED STADIUM RESOLVER")
        self.lbl_header.setStyleSheet("color: #19A7FF; font-size: 14px; font-weight: bold;")
        layout.addWidget(self.lbl_header)

        self.lbl_progress = QLabel("")
        self.lbl_progress.setStyleSheet("color: #94A3B8; font-size: 11px;")
        layout.addWidget(self.lbl_progress)

        # Stadium info box
        info_frame = QFrame()
        info_frame.setStyleSheet("background-color: #121C2A; border: 1px solid #1E293B; border-radius: 6px; padding: 10px;")
        info_layout = QVBoxLayout(info_frame)
        info_layout.setContentsMargins(8, 8, 8, 8)
        info_layout.setSpacing(4)

        self.lbl_stadium_title = QLabel("")
        self.lbl_stadium_title.setStyleSheet("color: #F1F5F9; font-size: 13px; font-weight: bold;")
        info_layout.addWidget(self.lbl_stadium_title)

        self.lbl_stadium_meta = QLabel("")
        self.lbl_stadium_meta.setStyleSheet("color: #64748B; font-size: 11px;")
        info_layout.addWidget(self.lbl_stadium_meta)

        self.lbl_web_hint = QLabel("")
        self.lbl_web_hint.setStyleSheet("color: #35D07F; font-size: 11px; font-style: italic;")
        info_layout.addWidget(self.lbl_web_hint)

        layout.addWidget(info_frame)

        # Team Search & Autocomplete
        search_box = QFrame()
        search_box.setStyleSheet("background-color: #121C2A; border: 1px solid #1E293B; border-radius: 6px; padding: 8px;")
        search_layout = QVBoxLayout(search_box)
        search_layout.setContentsMargins(6, 6, 6, 6)
        search_layout.setSpacing(6)

        lbl_s = QLabel("🔍 Search PES Team from PDF Database:")
        lbl_s.setStyleSheet("color: #94A3B8; font-weight: bold; font-size: 11px;")
        search_layout.addWidget(lbl_s)

        search_input_layout = QHBoxLayout()
        self.txt_team_search = QLineEdit()
        self.txt_team_search.setPlaceholderText("Type club or team name (e.g., Bournemouth, Arsenal, Real)...")
        self.txt_team_search.setStyleSheet("background-color: #0B111C; color: #F1F5F9; border: 1px solid #1E293B; border-radius: 4px; padding: 6px;")
        self.txt_team_search.textChanged.connect(self._on_search_text_changed)
        search_input_layout.addWidget(self.txt_team_search, 1)

        self.txt_manual_tid = QLineEdit()
        self.txt_manual_tid.setPlaceholderText("Team ID")
        self.txt_manual_tid.setFixedWidth(80)
        self.txt_manual_tid.setStyleSheet("background-color: #0B111C; color: #F1F5F9; border: 1px solid #1E293B; border-radius: 4px; padding: 6px;")
        search_input_layout.addWidget(self.txt_manual_tid)

        btn_add = QPushButton("➕ Add Team")
        btn_add.setStyleSheet("background-color: #19A7FF; color: #FFF; font-weight: bold; padding: 6px 14px; border-radius: 4px;")
        btn_add.clicked.connect(self._add_team_row)
        search_input_layout.addWidget(btn_add)

        btn_remove = QPushButton("❌ Remove")
        btn_remove.setStyleSheet("background-color: #FF5C6C; color: #FFF; font-weight: bold; padding: 6px 12px; border-radius: 4px;")
        btn_remove.clicked.connect(self._remove_selected_row)
        search_input_layout.addWidget(btn_remove)

        search_layout.addLayout(search_input_layout)

        # List widget for search results
        self.list_teams = QListWidget()
        self.list_teams.setFixedHeight(100)
        self.list_teams.setStyleSheet("background-color: #0B111C; color: #F1F5F9; border: 1px solid #1E293B; border-radius: 4px;")
        self.list_teams.itemClicked.connect(self._on_team_item_clicked)
        self.list_teams.itemDoubleClicked.connect(self._on_team_item_double_clicked)
        search_layout.addWidget(self.list_teams)

        layout.addWidget(search_box)

        # Assigned Mappings Table
        lbl_tbl = QLabel("Assigned 4-Column Rows for this Stadium:")
        lbl_tbl.setStyleSheet("color: #94A3B8; font-weight: bold; font-size: 11px;")
        layout.addWidget(lbl_tbl)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Team ID", "Stadium ID", "Stadium Name", "Stadium Path"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setStyleSheet("background-color: #121C2A; color: #F1F5F9; gridline-color: #1E293B; border-radius: 4px;")
        layout.addWidget(self.table, 1)

        # Buttons Bar
        btn_bar = QHBoxLayout()

        btn_prev = QPushButton("⬅ Previous")
        btn_prev.setStyleSheet("background-color: #1E293B; color: #F1F5F9; font-weight: bold; padding: 8px 14px; border-radius: 4px;")
        btn_prev.clicked.connect(self._prev_stadium)
        btn_bar.addWidget(btn_prev)

        btn_next = QPushButton("Next ➡")
        btn_next.setStyleSheet("background-color: #1E293B; color: #F1F5F9; font-weight: bold; padding: 8px 14px; border-radius: 4px;")
        btn_next.clicked.connect(self._next_stadium)
        btn_bar.addWidget(btn_next)

        btn_skip = QPushButton("⏭ Skip Stadium")
        btn_skip.setStyleSheet("background-color: #475569; color: #FFF; font-weight: bold; padding: 8px 14px; border-radius: 4px;")
        btn_skip.clicked.connect(self._skip_current)
        btn_bar.addWidget(btn_skip)

        btn_bar.addStretch(1)

        btn_save = QPushButton("💾 Save & Next")
        btn_save.setStyleSheet("background-color: #35D07F; color: #FFF; font-weight: bold; padding: 8px 18px; border-radius: 4px;")
        btn_save.clicked.connect(self._save_and_next)
        btn_bar.addWidget(btn_save)

        btn_close = QPushButton("Close")
        btn_close.setStyleSheet("background-color: #334155; color: #FFF; font-weight: bold; padding: 8px 14px; border-radius: 4px;")
        btn_close.clicked.connect(self.accept)
        btn_bar.addWidget(btn_close)

        layout.addLayout(btn_bar)

        self._load_current_stadium()

    def _refresh_unresolved(self) -> None:
        """Find all stadiums with status UNRESOLVED or no confident match."""
        states = self.ctrl.get_all_states()
        self.unresolved_stadiums = [
            s.stadium_name for s in states
            if s.status == StadiumStatus.UNRESOLVED or (s.status == StadiumStatus.REVIEW and not s.mapped_rows)
        ]

    def _load_current_stadium(self) -> None:
        """Load information and existing mappings for the current unresolved stadium."""
        if not self.unresolved_stadiums:
            self.lbl_header.setText("🎉 All Stadiums Resolved!")
            self.lbl_progress.setText("There are no remaining unresolved stadiums.")
            self.lbl_stadium_title.setText("All resolved.")
            self.lbl_stadium_meta.setText("")
            self.lbl_web_hint.setText("")
            self.table.setRowCount(0)
            return

        if self.current_idx >= len(self.unresolved_stadiums):
            self.current_idx = len(self.unresolved_stadiums) - 1
        if self.current_idx < 0:
            self.current_idx = 0

        stadium_name = self.unresolved_stadiums[self.current_idx]
        total = len(self.unresolved_stadiums)
        self.lbl_progress.setText(f"Stadium {self.current_idx + 1} of {total}")
        self.lbl_stadium_title.setText(f"🏟️ {stadium_name}")

        s_obj = next((s for s in self.ctrl.discovered_stadiums if s.display_name == stadium_name), None)
        st_ids = ", ".join(s_obj.stadium_ids) if s_obj and s_obj.stadium_ids else "000"
        rel_path = s_obj.relative_path if s_obj else stadium_name
        self.lbl_stadium_meta.setText(f"Folder: {rel_path} | Stadium IDs: {st_ids}")

        res = self.ctrl.research_results.get(stadium_name)
        if res and res.club_name:
            self.lbl_web_hint.setText(f"💡 Web Research Clue: Identified club '{res.club_name}' (Confidence: {res.confidence:.0%})")
            self.txt_team_search.setText(res.club_name)
        else:
            self.lbl_web_hint.setText("💡 Web Research Clue: No club identified automatically. Please search below.")
            self.txt_team_search.setText(stadium_name)

        # Load existing rows or template row
        self.table.setRowCount(0)
        state = self.ctrl.get_stadium_state(stadium_name)
        primary_id = s_obj.primary_id() if s_obj else "000"

        if state.mapped_rows:
            for r in state.mapped_rows:
                self._add_row_to_table(r.team_id, r.stadium_id, r.stadium_name, r.stadium_path)
        else:
            self._add_row_to_table(0, primary_id, stadium_name, stadium_name)

    def _add_row_to_table(self, tid: int, sid: str, sname: str, spath: str) -> None:
        r = self.table.rowCount()
        self.table.insertRow(r)
        self.table.setItem(r, 0, QTableWidgetItem(str(tid)))
        self.table.setItem(r, 1, QTableWidgetItem(str(sid)))
        self.table.setItem(r, 2, QTableWidgetItem(str(sname)))
        self.table.setItem(r, 3, QTableWidgetItem(str(spath)))

    def _on_search_text_changed(self, text: str) -> None:
        """Filter the team list widget live."""
        self.list_teams.clear()
        q = text.lower().strip()
        if not q or len(q) < 2:
            return

        matches: list[tuple[int, str]] = []
        for tid, tname in self.ctrl.pdf_parser.id_to_name.items():
            if q in tname.lower() or q == str(tid):
                matches.append((tid, tname))
                if len(matches) >= 20:
                    break

        for tid, tname in matches:
            item = QListWidgetItem(f"{tname} (ID: {tid})")
            item.setData(Qt.UserRole, (tid, tname))
            self.list_teams.addItem(item)

    def _on_team_item_clicked(self, item: QListWidgetItem) -> None:
        data = item.data(Qt.UserRole)
        if data:
            tid, tname = data
            self.txt_manual_tid.setText(str(tid))

    def _on_team_item_double_clicked(self, item: QListWidgetItem) -> None:
        data = item.data(Qt.UserRole)
        if data:
            tid, tname = data
            self.txt_manual_tid.setText(str(tid))
            self._add_team_row()

    def _add_team_row(self) -> None:
        """Add the selected/typed team to the mappings table."""
        tid_str = self.txt_manual_tid.text().strip()
        if not tid_str.isdigit():
            # Try to match from search text
            resolved = self.ctrl.matcher.resolve_team_id(self.txt_team_search.text().strip())
            if resolved is not None:
                tid_str = str(resolved)
            else:
                QMessageBox.warning(self, "Invalid Team ID", "Please select a team from the list or enter a numeric Team ID.")
                return

        tid = int(tid_str)
        stadium_name = self.unresolved_stadiums[self.current_idx] if self.unresolved_stadiums else ""
        s_obj = next((s for s in self.ctrl.discovered_stadiums if s.display_name == stadium_name), None)
        primary_id = s_obj.primary_id() if s_obj else "000"

        # Update first empty/zero row if present
        updated = False
        for r in range(self.table.rowCount()):
            it = self.table.item(r, 0)
            if it and it.text().strip() in ("0", ""):
                it.setText(str(tid))
                updated = True
                break

        if not updated:
            self._add_row_to_table(tid, primary_id, stadium_name, stadium_name)

    def _remove_selected_row(self) -> None:
        curr = self.table.currentRow()
        if curr >= 0 and self.table.rowCount() > 1:
            self.table.removeRow(curr)

    def _prev_stadium(self) -> None:
        if self.current_idx > 0:
            self.current_idx -= 1
            self._load_current_stadium()

    def _next_stadium(self) -> None:
        if self.current_idx < len(self.unresolved_stadiums) - 1:
            self.current_idx += 1
            self._load_current_stadium()

    def _skip_current(self) -> None:
        if not self.unresolved_stadiums:
            return
        stadium_name = self.unresolved_stadiums[self.current_idx]
        self.ctrl.mark_skipped(stadium_name)
        self._refresh_unresolved()
        if not self.unresolved_stadiums:
            QMessageBox.information(self, "All Done", "🎉 All stadiums have now been resolved or skipped!")
            self.accept()
        else:
            self._load_current_stadium()

    def _save_and_next(self) -> None:
        if not self.unresolved_stadiums:
            self.accept()
            return

        stadium_name = self.unresolved_stadiums[self.current_idx]
        mapped_rows: list[MappedRow] = []

        for r in range(self.table.rowCount()):
            try:
                it_tid = self.table.item(r, 0)
                it_sid = self.table.item(r, 1)
                it_sname = self.table.item(r, 2)
                it_spath = self.table.item(r, 3)
                if not (it_tid and it_sid and it_sname and it_spath):
                    continue
                tid = int(it_tid.text().strip())
                if tid == 0:
                    continue
                sid = it_sid.text().strip()
                sname = it_sname.text().strip()
                spath = it_spath.text().strip()
                mapped_rows.append(MappedRow(team_id=tid, stadium_id=sid, stadium_name=sname, stadium_path=spath, status="MANUAL", confidence=1.0))
            except Exception:
                pass

        if not mapped_rows:
            QMessageBox.warning(self, "No Team Assigned", "Please assign a valid Team ID before saving, or click 'Skip Stadium'.")
            return

        self.ctrl.set_manual_mappings(stadium_name, mapped_rows)
        self._refresh_unresolved()

        if not self.unresolved_stadiums:
            QMessageBox.information(self, "All Resolved", "🎉 Congratulations! All unresolved stadiums have been resolved!")
            self.accept()
        else:
            self._load_current_stadium()


class ContactAdminDialog(QDialog):

    """Contact Admin & Private Source Access Subform Modal."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Contact Admin — PES Stadium Mapper")
        self.resize(520, 320)
        self.setStyleSheet("background-color: #0B111C; color: #F1F5F9;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)

        # Header Banner
        lbl_hdr = QLabel("💬 CONTACT ADMIN")
        lbl_hdr.setStyleSheet("color: #19A7FF; font-size: 16px; font-weight: bold;")
        layout.addWidget(lbl_hdr)

        # Main Box
        box = QFrame()
        box.setStyleSheet("background-color: #162232; border: 1px solid #1E293B; border-radius: 6px; padding: 14px;")
        box_layout = QVBoxLayout(box)

        lbl_notice = QLabel("🔒 Source code is private. Contact admin for access.")
        lbl_notice.setStyleSheet("color: #FF5C6C; font-size: 13px; font-weight: bold;")
        box_layout.addWidget(lbl_notice)

        lbl_desc = QLabel("For source code access, feature requests, bug reports, or technical support, please contact the project administrator via Reddit:")
        lbl_desc.setWordWrap(True)
        lbl_desc.setStyleSheet("color: #94A3B8; font-size: 11px;")
        box_layout.addWidget(lbl_desc)

        # Link Frame
        link_frame = QFrame()
        link_frame.setStyleSheet("background-color: #0F172A; border-radius: 4px; padding: 6px 10px;")
        link_layout = QHBoxLayout(link_frame)

        lbl_r = QLabel("Reddit User:")
        lbl_r.setStyleSheet("color: #19A7FF; font-weight: bold;")
        link_layout.addWidget(lbl_r)

        reddit_url = "https://www.reddit.com/user/Available_Chipmunk27/"
        self.lbl_link = QLabel(f"<a href='{reddit_url}' style='color: #35D07F; text-decoration: underline;'>{reddit_url}</a>")
        self.lbl_link.setOpenExternalLinks(True)
        link_layout.addWidget(self.lbl_link)
        box_layout.addWidget(link_frame)

        layout.addWidget(box)

        # Action Buttons
        btn_layout = QHBoxLayout()
        btn_copy = QPushButton("📋 Copy Link")
        btn_copy.setStyleSheet("background-color: #19A7FF; color: #FFFFFF; font-weight: bold; padding: 6px 12px; border-radius: 4px;")
        btn_copy.clicked.connect(lambda: self._copy_link(reddit_url))
        btn_layout.addWidget(btn_copy)

        btn_open = QPushButton("🌐 Open in Browser")
        btn_open.setStyleSheet("background-color: #35D07F; color: #FFFFFF; font-weight: bold; padding: 6px 12px; border-radius: 4px;")
        btn_open.clicked.connect(lambda: webbrowser.open_new_tab(reddit_url))
        btn_layout.addWidget(btn_open)

        btn_close = QPushButton("Close")
        btn_close.setStyleSheet("background-color: #334155; color: #FFFFFF; font-weight: bold; padding: 6px 12px; border-radius: 4px;")
        btn_close.clicked.connect(self.close)
        btn_layout.addWidget(btn_close)

        layout.addLayout(btn_layout)

    def _copy_link(self, url: str) -> None:
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText(url)
        QMessageBox.information(self, "Copied", "Reddit profile URL copied to clipboard!")


class CommandPaletteDialog(QDialog):
    """Modern Ctrl+K Command Palette Launcher Modal."""

    def __init__(self, actions: list[tuple[str, Any]], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Command Palette")
        self.resize(540, 360)
        self.setStyleSheet("background-color: #0B111C; color: #F1F5F9;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)

        lbl_hdr = QLabel("COMMAND PALETTE (Ctrl+K)")
        lbl_hdr.setStyleSheet("color: #19A7FF; font-size: 13px; font-weight: bold;")
        layout.addWidget(lbl_hdr)

        self.txt_search = QLineEdit()
        self.txt_search.setPlaceholderText("Type a command to search...")
        self.txt_search.textChanged.connect(self._filter_list)
        layout.addWidget(self.txt_search)

        self.list_widget = QListWidget()
        self.list_widget.setStyleSheet("background-color: #121C2A; color: #F1F5F9; border: none; font-size: 13px;")
        self.list_widget.itemDoubleClicked.connect(self._execute_item)
        layout.addWidget(self.list_widget)

        self.actions = actions
        for text, _ in actions:
            self.list_widget.addItem(f"  ⚡  {text}")

    def _filter_list(self, text: str) -> None:
        q = text.lower().strip()
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            item.setHidden(bool(q and q not in item.text().lower()))

    def _execute_item(self, item: QListWidgetItem) -> None:
        idx = self.list_widget.row(item)
        if 0 <= idx < len(self.actions):
            cmd_func = self.actions[idx][1]
            self.accept()
            cmd_func()


class ImagePreviewDialog(QDialog):
    """Full-screen / HD Image & Media Preview Modal."""

    def __init__(self, image_path: Path | str, title: str = "Stadium Image Preview", parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(800, 520)
        self.setStyleSheet("background-color: #05080D; color: #F1F5F9;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)

        lbl_hdr = QLabel(f"🖼️ {title}")
        lbl_hdr.setStyleSheet("color: #19A7FF; font-size: 14px; font-weight: bold;")
        layout.addWidget(lbl_hdr)

        lbl_img = QLabel()
        lbl_img.setAlignment(Qt.AlignCenter)

        p = Path(image_path)
        if p.exists():
            from PySide6.QtGui import QPixmap
            pix = QPixmap(str(p))
            if not pix.isNull():
                lbl_img.setPixmap(pix.scaled(760, 420, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            else:
                lbl_img.setText(f"Unable to decode image format:\n{p.name}")
        else:
            lbl_img.setText(f"Image file not found:\n{image_path}")

        lbl_img.setStyleSheet("background-color: #0B111C; border: 1px solid #1E293B; border-radius: 6px; color: #94A3B8;")
        layout.addWidget(lbl_img, 1)

        btn_close = QPushButton("Close")
        btn_close.setStyleSheet("background-color: #334155; color: #FFFFFF; font-weight: bold; padding: 6px 16px; border-radius: 4px;")
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close, 0, Qt.AlignRight)


class SettingsDialog(QDialog):
    """Settings configuration dialog for all AppConfig fields."""

    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.ctrl = controller
        self.cfg = controller.config

        self.setWindowTitle("⚙ Settings — PES Stadium Mapper")
        self.resize(640, 580)
        self.setStyleSheet("background-color: #0B111C; color: #F1F5F9;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        lbl_hdr = QLabel("⚙ APPLICATION SETTINGS")
        lbl_hdr.setStyleSheet("color: #19A7FF; font-size: 15px; font-weight: bold;")
        layout.addWidget(lbl_hdr)

        grid = QGridLayout()
        grid.setSpacing(10)
        row = 0

        def add_row(label_text, widget):
            nonlocal row
            lbl = QLabel(label_text)
            lbl.setStyleSheet("color: #94A3B8; font-weight: bold; font-size: 11px;")
            grid.addWidget(lbl, row, 0)
            grid.addWidget(widget, row, 1)
            row += 1

        def styled_edit(placeholder="", text=""):
            w = QLineEdit()
            w.setPlaceholderText(placeholder)
            w.setText(text)
            w.setStyleSheet("background-color: #121C2A; color: #F1F5F9; border: 1px solid #1E293B; border-radius: 4px; padding: 6px;")
            return w

        def browse_row(label_text, attr_name, placeholder):
            nonlocal row
            lbl = QLabel(label_text)
            lbl.setStyleSheet("color: #94A3B8; font-weight: bold; font-size: 11px;")
            grid.addWidget(lbl, row, 0)
            h = QHBoxLayout()
            h.setSpacing(6)
            edit = styled_edit(placeholder, getattr(self.cfg, attr_name, ""))
            edit.setObjectName(attr_name)
            h.addWidget(edit)
            btn = QPushButton("Browse…")
            btn.setFixedWidth(80)
            btn.setStyleSheet("background-color: #162232; color: #19A7FF; font-weight: bold; border: 1px solid #1E293B; border-radius: 4px; padding: 4px;")
            btn.clicked.connect(lambda _, e=edit, is_dir=(attr_name == "stadium_server_dir"): self._browse(e, is_dir))
            h.addWidget(btn)
            container = QWidget()
            container.setLayout(h)
            grid.addWidget(container, row, 1)
            row += 1
            return edit

        # Paths
        lbl_paths = QLabel("── PATHS & LAUNCHER ──────────────────────────")
        lbl_paths.setStyleSheet("color: #334155; font-size: 10px;")
        grid.addWidget(lbl_paths, row, 0, 1, 2); row += 1

        self.ed_server_dir = browse_row("Stadium Server Directory", "stadium_server_dir", "e.g. V:/sider/content/stadium-server")
        self.ed_pdf_path = browse_row("Team IDs PDF Path", "team_pdf_path", "e.g. settings_PSM/pdf/PES2021_Team_IDs.pdf")
        self.ed_sider_exe = browse_row("Sider Executable Path", "sider_exe_path", "e.g. V:/sider/sider.exe")
        self.ed_game_exe = browse_row("Game Executable Path", "game_exe_path", "e.g. V:/sider/FL2025.exe or PES2021.exe")
        self.ed_music_path = browse_row("Custom Music Path", "custom_music_path", "e.g. settings_PSM/audio/theme.mp3")
        self.ed_logo_path = browse_row("Custom Logo Path", "custom_logo_path", "e.g. settings_PSM/misc/logo.png")

        # Thresholds
        lbl_thresh = QLabel("── CONFIDENCE THRESHOLDS ─────────")
        lbl_thresh.setStyleSheet("color: #334155; font-size: 10px;")
        grid.addWidget(lbl_thresh, row, 0, 1, 2); row += 1

        self.ed_auto_accept = styled_edit("0.90", str(self.cfg.auto_accept_threshold))
        add_row("Auto-Accept Threshold (0.0–1.0)", self.ed_auto_accept)
        self.ed_review = styled_edit("0.75", str(self.cfg.review_threshold))
        add_row("Review Threshold (0.0–1.0)", self.ed_review)

        # Music volume
        lbl_misc = QLabel("── AUDIO & DISPLAY ─────────────────")
        lbl_misc.setStyleSheet("color: #334155; font-size: 10px;")
        grid.addWidget(lbl_misc, row, 0, 1, 2); row += 1

        self.ed_volume = styled_edit("0–100", str(self.cfg.music_volume))
        add_row("Music Volume (0–100)", self.ed_volume)

        self.chk_music_start = QCheckBox("Play music on startup")
        self.chk_music_start.setChecked(self.cfg.play_music_on_start)
        self.chk_music_start.setStyleSheet("color: #F1F5F9;")
        add_row("", self.chk_music_start)

        self.chk_cache = QCheckBox("Enable research cache")
        self.chk_cache.setChecked(self.cfg.enable_cache)
        self.chk_cache.setStyleSheet("color: #F1F5F9;")
        add_row("", self.chk_cache)

        # API Keys
        lbl_api = QLabel("── API KEYS (optional) ─────────────")
        lbl_api.setStyleSheet("color: #334155; font-size: 10px;")
        grid.addWidget(lbl_api, row, 0, 1, 2); row += 1

        self.ed_google_key = styled_edit("Google API Key", self.cfg.google_api_key)
        add_row("Google API Key", self.ed_google_key)
        self.ed_google_cx = styled_edit("Google CSE ID", self.cfg.google_search_engine_id)
        add_row("Google CSE ID", self.ed_google_cx)
        self.ed_bing_key = styled_edit("Bing API Key", self.cfg.bing_api_key)
        add_row("Bing API Key", self.ed_bing_key)

        layout.addLayout(grid)
        layout.addStretch(1)

        # Buttons
        btn_row = QHBoxLayout()
        btn_save = QPushButton("💾 Save Settings")
        btn_save.setStyleSheet("background-color: #35D07F; color: #FFFFFF; font-weight: bold; padding: 8px 16px; border-radius: 4px;")
        btn_save.clicked.connect(self._save)
        btn_row.addWidget(btn_save)

        btn_cancel = QPushButton("Cancel")
        btn_cancel.setStyleSheet("background-color: #334155; color: #FFFFFF; font-weight: bold; padding: 8px 16px; border-radius: 4px;")
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_cancel)
        layout.addLayout(btn_row)

    def _browse(self, edit: QLineEdit, is_dir: bool) -> None:
        from PySide6.QtWidgets import QFileDialog
        if is_dir:
            path = QFileDialog.getExistingDirectory(self, "Select Folder", edit.text() or "")
        else:
            path, _ = QFileDialog.getOpenFileName(self, "Select Executable / File", edit.text() or "")
        if path:
            edit.setText(path)

    def _save(self) -> None:
        try:
            self.ctrl.config_mgr.update(
                stadium_server_dir=self.ed_server_dir.text().strip(),
                team_pdf_path=self.ed_pdf_path.text().strip(),
                sider_exe_path=self.ed_sider_exe.text().strip(),
                game_exe_path=self.ed_game_exe.text().strip(),
                custom_music_path=self.ed_music_path.text().strip(),
                custom_logo_path=self.ed_logo_path.text().strip(),
                auto_accept_threshold=float(self.ed_auto_accept.text().strip() or "0.90"),
                review_threshold=float(self.ed_review.text().strip() or "0.75"),
                music_volume=int(self.ed_volume.text().strip() or "50"),
                play_music_on_start=self.chk_music_start.isChecked(),
                enable_cache=self.chk_cache.isChecked(),
                google_api_key=self.ed_google_key.text().strip(),
                google_search_engine_id=self.ed_google_cx.text().strip(),
                bing_api_key=self.ed_bing_key.text().strip(),
            )
            self.accept()
        except ValueError as e:
            QMessageBox.warning(self, "Invalid Value", f"Please check your input values:\n{e}")

