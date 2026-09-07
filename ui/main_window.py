from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from audio_player import WinAudioPlayer
from core.controller import StadiumMapperController
from core.models import StadiumState, StadiumStatus
from core.thumbnail_manager import ThumbnailManager
from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, Signal, Slot
from PySide6.QtGui import QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)
from ui.dashboard import Dashboard
from ui.dialogs import CommandPaletteDialog, ContactAdminDialog, EditManualMapDialog
from ui.inspector import Inspector
from ui.sidebar import Sidebar
from ui.stadium_table import StadiumTableView
from ui.terminal import LiveTerminal, QtLogConsoleHandler
from ui.toast import ToastNotification
from ui.topbar import TopBar


class WorkerSignals(QObject):
    finished = Signal(object)
    log_msg = Signal(str, str)


class AsyncWorker(QRunnable):
    """QRunnable background task for asynchronous web research and stadium scanning."""

    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()

    @Slot()
    def run(self):
        try:
            res = self.fn(*self.args, **self.kwargs)
            self.signals.finished.emit(res)
        except Exception as e:
            self.signals.log_msg.emit(f"Background task failed: {e}", "ERROR")
            self.signals.finished.emit(None)


class MainWindow(QMainWindow):
    """
    3-Pane Modern Football Analytics Workstation QMainWindow Container.
    Integrates TopBar, Sidebar, Dashboard KPI Cards, StadiumTableView, LiveTerminal, and Inspector.
    Guarantees Dashboard == Table == Sidebar == Inspector == Filters at all times.
    """

    def __init__(self, controller: StadiumMapperController, parent=None):
        super().__init__(parent)
        self.ctrl = controller
        self.thumbnail_mgr = self.ctrl.thumbnail_mgr
        self.thread_pool = QThreadPool.globalInstance()

        self.setWindowTitle("PES 2021 Stadium Server Mapper — Nightly Build 1.0.0")
        self.resize(1380, 900)
        self.setMinimumSize(1100, 720)

        # Set Window Icon
        logo_path = self.ctrl.config.custom_logo_path
        if logo_path and Path(logo_path).exists():
            self.setWindowIcon(QIcon(str(logo_path)))

        # Native Audio Player
        self.audio_player = WinAudioPlayer(logger=self.ctrl.logger)

        self._selected_stadium_name: str | None = None
        self._active_status_filter = "ALL"
        self._active_search_query = ""

        self._load_qss_stylesheet()
        self._build_ui()
        self._setup_logging_stream()

        # Keyboard Shortcuts
        QShortcut(QKeySequence("Ctrl+K"), self, self._open_command_palette)
        QShortcut(QKeySequence("F5"), self, self.cmd_scan)
        QShortcut(QKeySequence("Ctrl+G"), self, self.cmd_generate)

        # Auto-scan on launch
        self.cmd_scan()

    def _load_qss_stylesheet(self) -> None:
        """Load centralized QSS stylesheet from styles/main.qss."""
        qss_path = self.ctrl.base_dir / "styles" / "main.qss"
        if qss_path.exists():
            try:
                with open(qss_path, "r", encoding="utf-8") as f:
                    self.setStyleSheet(f.read())
            except Exception as e:
                self.ctrl.logger.warning(f"Failed to load main.qss: {e}")

    def _setup_logging_stream(self) -> None:
        """Connect logging handler to Live Terminal console."""
        console_handler = QtLogConsoleHandler(self.terminal.emitter)
        console_handler.setFormatter(logging.Formatter("[%(asctime)s] > %(message)s", datefmt="%H:%M:%S"))
        self.ctrl.logger.addHandler(console_handler)

    def _build_ui(self) -> None:
        """Construct PySide6 3-pane main workstation layout."""
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 1. TOP BAR
        self.topbar = TopBar(parent=self)
        self.topbar.toggle_music_signal.connect(self._toggle_music)
        self.topbar.open_settings_signal.connect(self._open_settings)
        self.topbar.open_contact_admin_signal.connect(self._open_contact_admin)
        main_layout.addWidget(self.topbar)

        # 2. MIDDLE WORKSPACE SPLITTER (Sidebar | Center Workspace | Inspector)
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(1)

        # PANE 1: Left Navigation Sidebar Rail
        self.sidebar = Sidebar(parent=self)
        self.sidebar.set_server_path(self.ctrl.config.stadium_server_dir or str(self.ctrl.base_dir))
        self.sidebar.scan_clicked.connect(self.cmd_scan)
        self.sidebar.research_clicked.connect(self.cmd_research)
        self.sidebar.unresolved_clicked.connect(self.cmd_open_unresolved_resolver)
        self.sidebar.write_map_clicked.connect(self.cmd_generate)
        self.sidebar.dry_run_clicked.connect(self.cmd_dry_run)
        self.sidebar.palette_clicked.connect(self._open_command_palette)
        self.sidebar.provider_changed.connect(self._on_provider_changed)
        self.sidebar.change_path_clicked.connect(self._cmd_change_server_path)
        splitter.addWidget(self.sidebar)

        # PANE 2: Center Workspace (Dashboard KPI Cards + Search/Filter Bar + Table + Terminal)
        center_widget = QWidget()
        center_layout = QVBoxLayout(center_widget)
        center_layout.setContentsMargins(12, 12, 12, 12)
        center_layout.setSpacing(8)

        # Dashboard KPI Cards
        self.dashboard = Dashboard(parent=self)
        center_layout.addWidget(self.dashboard)

        # Filter Bar
        filter_frame = QFrame()
        filter_frame.setObjectName("FilterBar")
        filter_layout = QHBoxLayout(filter_frame)
        filter_layout.setContentsMargins(8, 4, 8, 4)

        lbl_filter = QLabel("⌕ Filter:")
        lbl_filter.setStyleSheet("color: #94A3B8; font-weight: bold;")
        filter_layout.addWidget(lbl_filter)

        self.txt_search = QLineEdit()
        self.txt_search.setPlaceholderText("Search stadium, team, ID...")
        self.txt_search.setFixedWidth(260)
        self.txt_search.textChanged.connect(self._on_search_text_changed)
        filter_layout.addWidget(self.txt_search)

        lbl_st = QLabel("Status:")
        lbl_st.setStyleSheet("color: #94A3B8; font-weight: bold; margin-left: 12px;")
        filter_layout.addWidget(lbl_st)

        self.filter_group = QButtonGroup(self)
        filters = ["ALL", "RESOLVED", "REVIEW", "UNRESOLVED", "MANUAL"]
        for idx, flt_text in enumerate(filters):
            radio = QRadioButton(flt_text)
            if idx == 0:
                radio.setChecked(True)
            self.filter_group.addButton(radio, idx)
            filter_layout.addWidget(radio)

        self.filter_group.idToggled.connect(self._on_status_filter_changed)
        filter_layout.addStretch(1)
        center_layout.addWidget(filter_frame)

        # Stadium Table View
        self.stadium_table = StadiumTableView(self.thumbnail_mgr, parent=self)
        self.stadium_table.stadium_selected_signal.connect(self._on_stadium_selected)
        center_layout.addWidget(self.stadium_table, 1)

        # Live Terminal Console
        self.terminal = LiveTerminal(parent=self)
        self.terminal.setFixedHeight(140)
        center_layout.addWidget(self.terminal)

        splitter.addWidget(center_widget)

        # PANE 3: Right Research Inspector Panel
        self.inspector = Inspector(self.thumbnail_mgr, parent=self)
        self.inspector.edit_manual_clicked.connect(self._open_edit_manual_dialog)
        self.inspector.reverify_clicked.connect(self._reverify_stadium)
        self.inspector.skip_clicked.connect(self._skip_stadium)
        splitter.addWidget(self.inspector)

        splitter.setSizes([240, 840, 300])
        main_layout.addWidget(splitter, 1)

    # ===================================================================
    # SINGLE AUTHORITATIVE STATE SYNCHRONIZATION ENGINE
    # ===================================================================
    def sync_ui(self) -> None:
        """
        Single Authoritative UI Sync Callback.
        Recalculates states directly from StadiumMapperController, updates StadiumTableView,
        recalculates KPIStatistics for Dashboard, updates Sidebar badges, Inspector, and Filters.
        Guarantees Dashboard == Table == Sidebar == Inspector == Filters at all times.
        """
        states = self.ctrl.get_all_states()

        # 1. Apply active filter rules
        filtered_states: list[StadiumState] = []
        q = self._active_search_query.lower()
        st_flt = self._active_status_filter

        for st in states:
            match_status = (st_flt == "ALL" or st.status.value == st_flt)
            match_search = (
                not q
                or q in st.stadium_name.lower()
                or q in st.identified_clubs.lower()
                or q in st.stadium_id.lower()
                or q in st.pes_team_ids.lower()
            )
            if match_status and match_search:
                filtered_states.append(st)

        # 2. Update StadiumTableView
        self.stadium_table.set_states(filtered_states)

        # 3. Update Dashboard KPI Cards
        stats = self.ctrl.get_statistics()
        self.dashboard.update_metrics(stats)

        # 4. Update Sidebar Resolver Badge
        self.sidebar.update_all_resolved_badge(stats.is_all_resolved, stats.unresolved)

        # 5. Update Inspector if stadium is currently selected
        if self._selected_stadium_name:
            curr_state = self.ctrl.get_stadium_state(self._selected_stadium_name)
            self.inspector.set_stadium_state(curr_state)
        elif filtered_states:
            self._selected_stadium_name = filtered_states[0].stadium_name
            self.inspector.set_stadium_state(filtered_states[0])

    # ===================================================================
    # SLOTS & COMMAND ACTION HANDLERS
    # ===================================================================
    @Slot()
    def cmd_scan(self) -> None:
        """Scan stadium server directory asynchronously."""
        self.topbar.set_status_text("● SCANNING DIRECTORY...", "#19A7FF")

        def task():
            return self.ctrl.scan_stadiums()

        worker = AsyncWorker(task)
        worker.signals.finished.connect(self._on_scan_finished)
        self.thread_pool.start(worker)

    def _on_scan_finished(self, result) -> None:
        self.topbar.set_status_text("● READY", "#19A7FF")
        self.sync_ui()
        ToastNotification(self, f"Scan complete — {len(self.ctrl.discovered_stadiums)} stadiums discovered", "success")

    @Slot()
    def cmd_research(self) -> None:
        """Execute live web research asynchronously."""
        self.topbar.set_status_text("● RESEARCHING IDENTITY...", "#FFB547")

        def task():
            for s in self.ctrl.discovered_stadiums:
                self.ctrl.research_stadium(s.display_name)
            return True

        worker = AsyncWorker(task)
        worker.signals.finished.connect(self._on_research_finished)
        self.thread_pool.start(worker)

    def _on_research_finished(self, result) -> None:
        self.topbar.set_status_text("● READY", "#19A7FF")
        self.sync_ui()
        ToastNotification(self, "Live web research complete!", "success")

    @Slot()
    def cmd_generate(self) -> None:
        """Write map_teams.txt file using authoritative mappings."""
        success, msg = self.ctrl.generate_map_file()
        if success:
            ToastNotification(self, "map_teams.txt written successfully!", "success")
            self.sync_ui()
        else:
            QMessageBox.critical(self, "Write Failed", f"Failed to write map_teams.txt:\n{msg}")

    @Slot()
    def cmd_dry_run(self) -> None:
        """Show dry run report dialog."""
        report = self.ctrl.generate_dry_run()
        QMessageBox.information(self, "Dry Run Report", f"=== DRY RUN REPORT ===\n\nTotal Discovered: {report.total_stadiums_found}\nHigh Confidence: {report.high_confidence_count}\nReview Required: {report.review_count}\nUnresolved: {report.unresolved_count}\nProposed Lines: {len(report.proposed_rows)}")

    @Slot()
    def cmd_open_unresolved_resolver(self) -> None:
        """Open Unresolved Resolver Modal for first unresolved stadium."""
        unresolved = [s for s in self.ctrl.get_all_states() if s.status == StadiumStatus.UNRESOLVED]
        if not unresolved:
            ToastNotification(self, "All stadiums are already resolved!", "success")
            return
        dlg = EditManualMapDialog(unresolved[0].stadium_name, self.ctrl, self)
        if dlg.exec():
            self.sync_ui()

    def _on_stadium_selected(self, stadium_name: str) -> None:
        self._selected_stadium_name = stadium_name
        state = self.ctrl.get_stadium_state(stadium_name)
        self.inspector.set_stadium_state(state)

    def _on_search_text_changed(self, text: str) -> None:
        self._active_search_query = text
        self.sync_ui()

    def _on_status_filter_changed(self, id_val: int, checked: bool) -> None:
        if checked:
            filters = ["ALL", "RESOLVED", "REVIEW", "UNRESOLVED", "MANUAL"]
            if 0 <= id_val < len(filters):
                self._active_status_filter = filters[id_val]
                self.sync_ui()

    def _open_edit_manual_dialog(self, stadium_name: str) -> None:
        dlg = EditManualMapDialog(stadium_name, self.ctrl, self)
        if dlg.exec():
            self.sync_ui()
            ToastNotification(self, f"Updated mapping for {stadium_name}", "success")

    def _reverify_stadium(self, stadium_name: str) -> None:
        self.ctrl.research_stadium(stadium_name, force_refresh=True)
        self.sync_ui()
        ToastNotification(self, f"Re-verified research for {stadium_name}", "info")

    def _skip_stadium(self, stadium_name: str) -> None:
        self.ctrl.mark_skipped(stadium_name)
        self.sync_ui()
        ToastNotification(self, f"Marked {stadium_name} as skipped", "warning")

    def _toggle_music(self) -> None:
        """Toggle ambient music playback. Play if stopped, pause/resume if already playing."""
        if self.audio_player.is_playing and not self.audio_player.is_paused:
            self.audio_player.pause()
            self.topbar.btn_music.setText("▶ Resume")
            ToastNotification(self, "Music paused.", "info")
        elif self.audio_player.is_playing and self.audio_player.is_paused:
            self.audio_player.resume()
            self.topbar.btn_music.setText("⏸ Pause")
            ToastNotification(self, "Music resumed.", "info")
        else:
            music_path = self.ctrl.config.custom_music_path
            if music_path and Path(music_path).exists():
                self.audio_player.play(music_path, volume=self.ctrl.config.music_volume)
                self.topbar.btn_music.setText("⏸ Pause")
                ToastNotification(self, "Playing ambient audio theme...", "info")
            else:
                ToastNotification(self, "No music file configured. Set one in ⚙ Settings.", "warning")

    def _open_settings(self) -> None:
        """Open the Settings configuration dialog."""
        from ui.dialogs import SettingsDialog
        dlg = SettingsDialog(self.ctrl, self)
        if dlg.exec():
            ToastNotification(self, "Settings saved successfully.", "success")
            # Re-apply music volume if music is currently playing
            if self.audio_player.is_playing:
                self.audio_player.set_volume(self.ctrl.config.music_volume)

    def _open_contact_admin(self) -> None:
        dlg = ContactAdminDialog(self)
        dlg.exec()

    def _on_provider_changed(self, prov_key: str) -> None:
        self.ctrl.config_mgr.update(search_provider=prov_key)
        ToastNotification(self, f"Research provider changed to: {prov_key.title()}", "info")

    def _cmd_change_server_path(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select PES Stadium Server Directory", self.ctrl.config.stadium_server_dir or "")
        if folder:
            self.ctrl.configure_paths(server_dir=folder)
            self.sidebar.set_server_path(folder)
            self.cmd_scan()

    def _open_command_palette(self) -> None:
        actions = [
            ("Scan Stadium Server Directory (F5)", self.cmd_scan),
            ("Run Live Web Research on Stadiums", self.cmd_research),
            ("Open Unresolved Stadium Resolver", self.cmd_open_unresolved_resolver),
            ("Generate map_teams.txt File (Ctrl+G)", self.cmd_generate),
            ("Generate Dry Run Report", self.cmd_dry_run),
            ("Contact Admin & Source Access", self._open_contact_admin),
        ]
        dlg = CommandPaletteDialog(actions, self)
        dlg.exec()
