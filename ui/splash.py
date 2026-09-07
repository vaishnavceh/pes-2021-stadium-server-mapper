from __future__ import annotations

from pathlib import Path
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPixmap, QPainter, QColor, QFont
from PySide6.QtWidgets import QSplashScreen, QApplication


class SplashScreen(QSplashScreen):
    """
    Branded splash screen shown on application startup.
    Displays logo + animated loading text for 2.5 seconds before MainWindow appears.
    """

    def __init__(self, logo_path: str = ""):
        pixmap = self._build_pixmap(logo_path)
        super().__init__(pixmap, Qt.WindowStaysOnTopHint)
        self.setWindowFlags(Qt.SplashScreen | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self._dots = 0

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._animate)
        self._timer.start(500)

    def _build_pixmap(self, logo_path: str) -> QPixmap:
        """Build the splash pixmap from logo file or fallback gradient."""
        W, H = 540, 300
        px = QPixmap(W, H)
        px.fill(QColor("#070B12"))

        painter = QPainter(px)
        painter.setRenderHint(QPainter.Antialiasing)

        # Dark gradient background panel
        painter.setBrush(QColor("#0B111C"))
        painter.setPen(QColor("#19A7FF"))
        painter.drawRoundedRect(20, 20, W - 40, H - 40, 14, 14)

        # Try loading user logo
        logo_loaded = False
        if logo_path:
            p = Path(logo_path)
            if p.exists():
                logo_px = QPixmap(str(p))
                if not logo_px.isNull():
                    scaled = logo_px.scaled(120, 120, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    lx = (W - scaled.width()) // 2
                    painter.drawPixmap(lx, 50, scaled)
                    logo_loaded = True

        if not logo_loaded:
            # Draw a stylized "PSM" badge
            font = QFont("Arial", 48, QFont.Bold)
            painter.setFont(font)
            painter.setPen(QColor("#19A7FF"))
            painter.drawText(px.rect().adjusted(0, 40, 0, -80), Qt.AlignHCenter | Qt.AlignTop, "PSM")

        # Title text
        title_font = QFont("Arial", 16, QFont.Bold)
        painter.setFont(title_font)
        painter.setPen(QColor("#F1F5F9"))
        painter.drawText(px.rect().adjusted(0, 170, 0, -60), Qt.AlignHCenter | Qt.AlignTop,
                         "PES 2021 Stadium Server Mapper")

        sub_font = QFont("Arial", 10)
        painter.setFont(sub_font)
        painter.setPen(QColor("#19A7FF"))
        painter.drawText(px.rect().adjusted(0, 200, 0, -40), Qt.AlignHCenter | Qt.AlignTop,
                         "Nightly Build 1.0.0")

        # Loading bar track
        painter.setBrush(QColor("#121C2A"))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(60, 255, W - 120, 12, 6, 6)
        painter.setBrush(QColor("#19A7FF"))
        painter.drawRoundedRect(60, 255, (W - 120) // 2, 12, 6, 6)

        painter.end()
        return px

    def _animate(self) -> None:
        """Update loading dots animation."""
        self._dots = (self._dots + 1) % 4
        self.showMessage(
            "Loading" + "." * self._dots,
            Qt.AlignBottom | Qt.AlignHCenter,
            QColor("#19A7FF"),
        )

    def stop_animation(self) -> None:
        """Stop the animation timer."""
        self._timer.stop()
