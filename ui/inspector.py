from __future__ import annotations

from core.models import StadiumState
from core.thumbnail_manager import ThumbnailManager
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)


class Inspector(QFrame):
    """
    Right Research Inspector Panel (~300px width).
    Displays enlarged 160x90 DDS stadium preview, folder metadata, analysis/evidence, and quick action buttons.
    """

    edit_manual_clicked = Signal(str)
    reverify_clicked = Signal(str)
    skip_clicked = Signal(str)
    preview_clicked = Signal(object)  # Path | None


    def __init__(self, thumbnail_manager: ThumbnailManager, parent=None):
        super().__init__(parent)
        self.setObjectName("Inspector")
        self.thumbnail_mgr = thumbnail_manager
        self.current_stadium_name: str | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 16, 12, 16)
        layout.setSpacing(10)

        # Header Title
        lbl_title = QLabel("RESEARCH INSPECTOR")
        lbl_title.setObjectName("InspectorSectionTitle")
        layout.addWidget(lbl_title)

        # Enlarged DDS Stadium Preview Frame (160x90)
        self.preview_frame = QFrame()
        self.preview_frame.setObjectName("InspectorPreviewBox")
        preview_layout = QVBoxLayout(self.preview_frame)
        preview_layout.setContentsMargins(0, 0, 0, 0)

        self.lbl_preview = QLabel("NO PREVIEW")
        self.lbl_preview.setAlignment(Qt.AlignCenter)
        self.lbl_preview.setStyleSheet("color: #64748B; font-weight: bold; font-size: 10px;")
        preview_layout.addWidget(self.lbl_preview)
        layout.addWidget(self.preview_frame)

        # Metadata Readout Card
        meta_card = QFrame()
        meta_card.setObjectName("InspectorCard")
        meta_layout = QGridLayout(meta_card)
        meta_layout.setContentsMargins(8, 8, 8, 8)
        meta_layout.setSpacing(6)

        def add_meta_row(r: int, label_text: str) -> QLabel:
            lbl_key = QLabel(label_text)
            lbl_key.setStyleSheet("color: #64748B; font-weight: bold; font-size: 11px;")
            lbl_val = QLabel("-")
            lbl_val.setStyleSheet("color: #F1F5F9; font-weight: bold; font-size: 12px;")
            lbl_val.setWordWrap(True)
            meta_layout.addWidget(lbl_key, r, 0)
            meta_layout.addWidget(lbl_val, r, 1)
            return lbl_val

        self.lbl_folder = add_meta_row(0, "Folder:")
        self.lbl_id = add_meta_row(1, "Stadium ID:")
        self.lbl_club = add_meta_row(2, "Identified:")
        self.lbl_tid = add_meta_row(3, "Team ID:")
        self.lbl_conf = add_meta_row(4, "Confidence:")
        self.lbl_status = add_meta_row(5, "Status:")
        layout.addWidget(meta_card)

        # Analysis & Evidence Box
        lbl_analysis = QLabel("ANALYSIS & EVIDENCE")
        lbl_analysis.setStyleSheet("color: #64748B; font-size: 11px; font-weight: bold;")
        layout.addWidget(lbl_analysis)

        evidence_card = QFrame()
        evidence_card.setObjectName("InspectorCard")
        ev_layout = QVBoxLayout(evidence_card)
        ev_layout.setContentsMargins(8, 8, 8, 8)

        self.lbl_evidence = QLabel("Select a stadium row to inspect research evidence.")
        self.lbl_evidence.setWordWrap(True)
        self.lbl_evidence.setStyleSheet("color: #94A3B8; font-size: 11px;")
        ev_layout.addWidget(self.lbl_evidence)
        layout.addWidget(evidence_card)

        layout.addStretch(1)

        # Action Buttons Section
        lbl_actions = QLabel("STADIUM ACTIONS")
        lbl_actions.setStyleSheet("color: #64748B; font-size: 11px; font-weight: bold;")
        layout.addWidget(lbl_actions)

        self.btn_edit = QPushButton("✏ Edit Manual Map")
        self.btn_edit.setStyleSheet("background-color: #19A7FF; color: #FFFFFF; font-weight: bold; border-radius: 5px; padding: 8px;")
        self.btn_edit.clicked.connect(self._on_edit_clicked)
        layout.addWidget(self.btn_edit)

        self.btn_reverify = QPushButton("🔄 Re-verify Research")
        self.btn_reverify.setStyleSheet("background-color: #121C2A; color: #F1F5F9; font-weight: bold; border: 1px solid #1E293B; border-radius: 5px; padding: 8px;")
        self.btn_reverify.clicked.connect(self._on_reverify_clicked)
        layout.addWidget(self.btn_reverify)

        self.btn_skip = QPushButton("🚫 Skip Selected")
        self.btn_skip.setStyleSheet("background-color: #FF5C6C; color: #FFFFFF; font-weight: bold; border-radius: 5px; padding: 8px;")
        self.btn_skip.clicked.connect(self._on_skip_clicked)
        layout.addWidget(self.btn_skip)

    def set_stadium_state(self, state: StadiumState | None) -> None:
        """Update inspector fields from authoritative StadiumState model."""
        if not state:
            self.current_stadium_name = None
            self.lbl_folder.setText("-")
            self.lbl_id.setText("-")
            self.lbl_club.setText("-")
            self.lbl_tid.setText("-")
            self.lbl_conf.setText("-")
            self.lbl_status.setText("-")
            self.lbl_evidence.setText("Select a stadium row to inspect research evidence.")
            pixmap = self.thumbnail_mgr.get_placeholder(size=(160, 90))
            self.lbl_preview.setPixmap(pixmap)
            return

        self.current_stadium_name = state.stadium_name
        self.current_preview_path = state.preview_path
        self.lbl_folder.setText(state.stadium_name)
        self.lbl_id.setText(state.stadium_id)
        self.lbl_club.setText(state.identified_clubs)
        self.lbl_tid.setText(state.pes_team_ids)
        self.lbl_conf.setText(f"{int(state.confidence * 100)}%")
        self.lbl_status.setText(state.status.value)

        evidence_text = state.reasoning or "Identified via web research provider."
        if state.integrity_warnings:
            evidence_text += "\n\n⚠️ FOLDER INTEGRITY WARNINGS:\n• " + "\n• ".join(state.integrity_warnings)
        self.lbl_evidence.setText(evidence_text)

        # Update enlarged DDS preview pixmap (160x90)
        pixmap = self.thumbnail_mgr.get_pixmap(state.preview_path, size=(160, 90))
        self.lbl_preview.setPixmap(pixmap)

    def mousePressEvent(self, event) -> None:
        if getattr(self, "current_preview_path", None):
            self.preview_clicked.emit(self.current_preview_path)


    def _on_edit_clicked(self) -> None:
        if self.current_stadium_name:
            self.edit_manual_clicked.emit(self.current_stadium_name)

    def _on_reverify_clicked(self) -> None:
        if self.current_stadium_name:
            self.reverify_clicked.emit(self.current_stadium_name)

    def _on_skip_clicked(self) -> None:
        if self.current_stadium_name:
            self.skip_clicked.emit(self.current_stadium_name)
