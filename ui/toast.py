from __future__ import annotations

from PySide6.QtCore import QPropertyAnimation, QTimer, Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QWidget


class ToastNotification(QFrame):
    """
    Modern non-blocking toast notification popup overlay.
    Displays success, warning, or error messages smoothly at the bottom-right of the window.
    """

    def __init__(self, parent: QWidget, message: str, toast_type: str = "success", duration_ms: int = 3500):
        super().__init__(parent)
        self.setAttribute(Qt.WA_DeleteOnClose)

        colors = {
            "success": ("#122A1E", "#35D07F", "#35D07F"),
            "warning": ("#2A2212", "#FFB547", "#FFB547"),
            "error": ("#2A1215", "#FF5C6C", "#FF5C6C"),
            "info": ("#12202A", "#19A7FF", "#19A7FF"),
        }
        bg, fg, border = colors.get(toast_type, colors["info"])

        self.setStyleSheet(f"""
            QFrame {{
                background-color: {bg};
                color: {fg};
                border: 1px solid {border};
                border-radius: 6px;
                padding: 6px 12px;
            }}
            QLabel {{
                color: {fg};
                font-weight: bold;
                font-size: 12px;
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)

        prefix = "✓ " if toast_type == "success" else ("⚠ " if toast_type == "warning" else ("✕ " if toast_type == "error" else "ℹ "))
        self.label = QLabel(f"{prefix}{message}")
        layout.addWidget(self.label)

        self.adjustSize()

        # Position at bottom-right of parent
        parent_rect = parent.rect()
        x = parent_rect.width() - self.width() - 24
        y = parent_rect.height() - self.height() - 24
        self.move(x, y)
        self.show()

        # Auto dismiss timer
        QTimer.singleShot(duration_ms, self.close)
