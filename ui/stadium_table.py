from __future__ import annotations

from typing import Any, Sequence

from core.models import StadiumState, StadiumStatus
from core.thumbnail_manager import ThumbnailManager
from PySide6.QtCore import QAbstractTableModel, QModelIndex, QRect, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QHeaderView, QStyle, QStyledItemDelegate, QStyleOptionViewItem, QTableView


class StadiumTableModel(QAbstractTableModel):
    """
    QAbstractTableModel displaying authoritative StadiumStates with support for
    Selection, Status Badges, DDS Preview Pixmaps, Stadium Folders, IDs, Clubs, Team IDs, and Confidence Meters.
    """

    HEADERS = [
        "Selection",
        "Status",
        "Preview",
        "Stadium Folder",
        "Stadium ID",
        "Identified Club",
        "PES Team ID",
        "Confidence Meter",
    ]

    def __init__(self, thumbnail_manager: ThumbnailManager, parent=None):
        super().__init__(parent)
        self.thumbnail_mgr = thumbnail_manager
        self._states: list[StadiumState] = []
        self._selected_ids: set[str] = set()

    def set_states(self, states: Sequence[StadiumState]) -> None:
        """Replace model dataset with updated authoritative states."""
        self.beginResetModel()
        self._states = list(states)
        self.endResetModel()

    def get_state(self, row: int) -> StadiumState | None:
        if 0 <= row < len(self._states):
            return self._states[row]
        return None

    def rowCount(self, parent=QModelIndex()) -> int:
        return len(self._states)

    def columnCount(self, parent=QModelIndex()) -> int:
        return len(self.HEADERS)

    def headerData(self, section: int, orientation: Qt.Orientation, role=Qt.DisplayRole) -> Any:
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self.HEADERS[section]
        return None

    def data(self, index: QModelIndex, role=Qt.DisplayRole) -> Any:
        if not index.isValid() or not (0 <= index.row() < len(self._states)):
            return None

        state = self._states[index.row()]
        col = index.column()

        if role == Qt.DisplayRole:
            if col == 3:
                return state.stadium_name
            elif col == 4:
                return state.stadium_id
            elif col == 5:
                return state.identified_clubs
            elif col == 6:
                return state.pes_team_ids
            elif col == 7:
                return f"{int(state.confidence * 100)}%"

        elif role == Qt.DecorationRole:
            if col == 2:
                # DDS Thumbnail Pixmap
                return self.thumbnail_mgr.get_pixmap(state.preview_path, size=(52, 30))

        elif role == Qt.UserRole:
            # Custom State payload for Delegates
            return state

        elif role == Qt.TextAlignmentRole:
            if col in (0, 1, 2, 4, 6, 7):
                return int(Qt.AlignCenter)
            return int(Qt.AlignLeft | Qt.AlignVCenter)

        return None


class StadiumTableDelegate(QStyledItemDelegate):
    """
    QStyledItemDelegate providing custom rendering for Status Badges and Confidence meters.
    """

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        col = index.column()
        state: StadiumState | None = index.data(Qt.UserRole)

        if col == 1 and state:
            # Draw Custom Status Badge
            painter.save()
            rect = option.rect.adjusted(6, 6, -6, -6)

            colors = {
                StadiumStatus.RESOLVED: (QColor(18, 42, 30), QColor(53, 208, 127), "✓ RESOLVED"),
                StadiumStatus.REVIEW: (QColor(42, 34, 18), QColor(255, 181, 71), "⚠ REVIEW"),
                StadiumStatus.UNRESOLVED: (QColor(42, 18, 21), QColor(255, 92, 108), "✕ UNRESOLVED"),
                StadiumStatus.MANUAL: (QColor(25, 40, 65), QColor(37, 99, 235), "✏ MANUAL"),
                StadiumStatus.SKIPPED: (QColor(30, 41, 59), QColor(100, 116, 139), "● SKIPPED"),
            }
            bg, fg, label = colors.get(state.status, colors[StadiumStatus.UNRESOLVED])

            painter.setBrush(bg)
            painter.setPen(fg)
            painter.drawRoundedRect(rect, 4, 4)

            painter.setFont(QFont("Segoe UI", 8, QFont.Bold))
            painter.drawText(rect, Qt.AlignCenter, label)
            painter.restore()

        elif col == 7 and state:
            # Draw Custom Confidence Meter Bar
            painter.save()
            rect = option.rect.adjusted(8, 10, -8, -10)

            # Draw track background
            painter.setBrush(QColor(15, 23, 42))
            painter.setPen(QColor(51, 65, 85))
            painter.drawRoundedRect(rect, 3, 3)

            # Draw active confidence fill
            conf = max(0.0, min(1.0, state.confidence))
            fill_w = int(rect.width() * conf)
            if fill_w > 0:
                fill_rect = QRect(rect.x(), rect.y(), fill_w, rect.height())
                fill_color = QColor(53, 208, 127) if conf >= 0.90 else (QColor(255, 181, 71) if conf >= 0.75 else QColor(255, 92, 108))
                painter.setBrush(fill_color)
                painter.setPen(Qt.NoPen)
                painter.drawRoundedRect(fill_rect, 3, 3)

            # Text overlay
            painter.setPen(QColor(241, 245, 249))
            painter.setFont(QFont("Segoe UI", 8, QFont.Bold))
            painter.drawText(option.rect, Qt.AlignCenter, f"{int(conf * 100)}%")
            painter.restore()

        else:
            super().paint(painter, option, index)


class StadiumTableView(QTableView):
    """
    Modern styled QTableView for displaying stadium mappings.
    Configured with fixed 42px row height and auto-stretching columns.
    """

    stadium_selected_signal = Signal(str)

    def __init__(self, thumbnail_manager: ThumbnailManager, parent=None):
        super().__init__(parent)
        self.setObjectName("StadiumTable")

        self.table_model = StadiumTableModel(thumbnail_manager, self)
        self.setModel(self.table_model)

        self.setItemDelegate(StadiumTableDelegate(self))

        # View configuration
        self.setSelectionBehavior(QTableView.SelectRows)
        self.setSelectionMode(QTableView.SingleSelection)
        self.setShowGrid(True)
        self.setGridStyle(Qt.SolidLine)
        self.setAlternatingRowColors(False)
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(42)

        # Header sizing
        h_header = self.horizontalHeader()
        h_header.setStretchLastSection(True)
        h_header.setSectionResizeMode(0, QHeaderView.Fixed)  # Selection
        h_header.setSectionResizeMode(1, QHeaderView.Fixed)  # Status
        h_header.setSectionResizeMode(2, QHeaderView.Fixed)  # Preview
        h_header.setSectionResizeMode(3, QHeaderView.Stretch) # Folder
        h_header.setSectionResizeMode(4, QHeaderView.Fixed)  # ID
        h_header.setSectionResizeMode(5, QHeaderView.Stretch) # Club
        h_header.setSectionResizeMode(6, QHeaderView.Fixed)  # Team ID
        h_header.setSectionResizeMode(7, QHeaderView.Fixed)  # Confidence

        self.setColumnWidth(0, 45)
        self.setColumnWidth(1, 140)
        self.setColumnWidth(2, 85)
        self.setColumnWidth(4, 90)
        self.setColumnWidth(6, 100)
        self.setColumnWidth(7, 150)

        self.selectionModel().selectionChanged.connect(self._on_selection_changed)

    def _on_selection_changed(self, selected, deselected) -> None:
        indexes = self.selectionModel().selectedRows()
        if indexes:
            row = indexes[0].row()
            state = self.table_model.get_state(row)
            if state:
                self.stadium_selected_signal.emit(state.stadium_name)

    def set_states(self, states: Sequence[StadiumState]) -> None:
        """Update table data states."""
        self.table_model.set_states(states)
