from __future__ import annotations

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QWidget


class ToastNotification(QFrame):
    """
    Modern non-blocking toast notification popup overlay.
    Displays at bottom-right of the top-level window. Stacks when multiple toasts are active.
    """

    _active_toasts: list["ToastNotification"] = []

    def __init__(self, parent: QWidget, message: str, toast_type: str = "success", duration_ms: int = 3500):
        # Always anchor to the actual top-level window for reliable positioning
        top_window = parent.window() if parent else parent
        super().__init__(top_window)
        self.setAttribute(Qt.WA_DeleteOnClose)

        colors = {
            "success": ("#122A1E", "#35D07F", "#35D07F"),
            "warning": ("#2A2212", "#FFB547", "#FFB547"),
            "error":   ("#2A1215", "#FF5C6C", "#FF5C6C"),
            "info":    ("#12202A", "#19A7FF", "#19A7FF"),
        }
        bg, fg, border = colors.get(toast_type, colors["info"])

        self.setStyleSheet(f"""
            QFrame {{
                background-color: {bg};
                border: 2px solid {border};
                border-radius: 8px;
            }}
            QLabel {{
                color: {fg};
                font-weight: bold;
                font-size: 12px;
                background: transparent;
                border: none;
                padding: 0px;
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(8)

        prefix = {"success": "✓", "warning": "⚠", "error": "✕", "info": "ℹ"}.get(toast_type, "ℹ")
        self.label = QLabel(f"{prefix}  {message}")
        self.label.setWordWrap(False)
        layout.addWidget(self.label)

        self.adjustSize()

        # Register and stack
        ToastNotification._active_toasts.append(self)
        self._restack_all()
        self.raise_()
        self.show()

        QTimer.singleShot(duration_ms, self._dismiss)

    def _restack_all(self) -> None:
        """Reposition all active toasts so they stack vertically at bottom-right."""
        win = self.parent()
        if not win:
            return
        margin = 20
        gap = 8
        base_y = win.height() - margin
        active = [t for t in ToastNotification._active_toasts if t is not None]
        for toast in reversed(active):
            base_y -= toast.height()
            x = win.width() - toast.width() - margin
            toast.move(x, base_y)
            base_y -= gap

    def _dismiss(self) -> None:
        if self in ToastNotification._active_toasts:
            ToastNotification._active_toasts.remove(self)
        # Restack remaining toasts
        remaining = [t for t in ToastNotification._active_toasts if t is not None]
        if remaining:
            remaining[0]._restack_all()
        self.close()

