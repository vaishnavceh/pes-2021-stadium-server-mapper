from __future__ import annotations

import datetime
import logging
from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QColor, QTextCharFormat
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout


class LogSignalEmitter(QObject):
    log_signal = Signal(str, str)  # msg, level


class QtLogConsoleHandler(logging.Handler):
    """Logging handler that streams syntax-highlighted output to PySide6 Live Terminal."""

    def __init__(self, emitter: LogSignalEmitter):
        super().__init__()
        self.emitter = emitter

    def emit(self, record: logging.LogRecord) -> None:
        msg = self.format(record)
        self.emitter.log_signal.emit(msg, record.levelname)


class LiveTerminal(QFrame):
    """
    Monospace Live Terminal Console Panel.
    Streams real-time application and web research logs with syntax highlighting.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("TerminalConsole")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)

        # Header Bar
        hdr_layout = QHBoxLayout()
        lbl_title = QLabel("LIVE TERMINAL CONSOLE")
        lbl_title.setStyleSheet("color: #19A7FF; font-size: 11px; font-weight: bold;")
        hdr_layout.addWidget(lbl_title)

        lbl_live = QLabel("● LIVE")
        lbl_live.setStyleSheet("color: #35D07F; font-size: 10px; font-weight: bold;")
        hdr_layout.addWidget(lbl_live)
        hdr_layout.addStretch(1)

        btn_clear = QPushButton("Clear Log")
        btn_clear.setStyleSheet("background-color: #162232; color: #94A3B8; font-size: 10px; border: none; padding: 2px 6px; border-radius: 3px;")
        btn_clear.clicked.connect(self.clear_log)
        hdr_layout.addWidget(btn_clear)
        layout.addLayout(hdr_layout)

        # Text Console
        self.text_edit = QPlainTextEdit()
        self.text_edit.setReadOnly(True)
        self.text_edit.setMaximumBlockCount(300)
        self.text_edit.setStyleSheet("""
            QPlainTextEdit {
                background-color: #05080D;
                color: #56E39F;
                font-family: 'Cascadia Mono', 'Consolas', monospace;
                font-size: 12px;
                border: none;
            }
        """)
        layout.addWidget(self.text_edit)

        # Setup Logging Emitter — QueuedConnection ensures thread-safe delivery from worker threads
        self.emitter = LogSignalEmitter()
        self.emitter.log_signal.connect(self.append_log, Qt.QueuedConnection)

    def append_log(self, msg: str, level_name: str) -> None:
        """Append log message with syntax highlighting colors."""
        fmt = QTextCharFormat()

        if level_name == "ERROR" or "FAIL" in msg:
            fmt.setForeground(QColor("#FF5C6C"))
        elif level_name == "WARNING" or "WARN" in msg or "⚠️" in msg:
            fmt.setForeground(QColor("#FFB547"))
        elif "SUCCESS" in msg or "✓" in msg or "✅" in msg or "complete" in msg.lower():
            fmt.setForeground(QColor("#35D07F"))
        elif "RESEARCH" in msg or "🌐" in msg:
            fmt.setForeground(QColor("#9B8CFF"))
        else:
            fmt.setForeground(QColor("#56C7FF"))

        self.text_edit.mergeCurrentCharFormat(fmt)
        self.text_edit.appendPlainText(msg)
        self.text_edit.verticalScrollBar().setValue(self.text_edit.verticalScrollBar().maximum())

    def clear_log(self) -> None:
        """Clear text console."""
        self.text_edit.clear()
        timestamp = datetime.datetime.now().strftime('%H:%M:%S')
        self.append_log(f"[{timestamp}] > Terminal Console Cleared. Ready for research stream...", "INFO")
