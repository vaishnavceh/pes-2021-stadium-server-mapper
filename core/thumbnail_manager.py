from __future__ import annotations

import logging
from pathlib import Path
from typing import Tuple

from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap


class ThumbnailManager:
    """
    Decodes PES 2021 DDS textures via Pillow, converts to PySide6 QPixmap,
    resizes smoothly, and caches thumbnails for table rows and inspector views.
    Handles ID normalization ("9", 9 -> "009") and provides fallback placeholders.
    """

    def __init__(self, logger: logging.Logger | None = None):
        self.logger = logger or logging.getLogger("stadium_mapper.thumbnail")
        self._pixmap_cache: dict[Tuple[str, Tuple[int, int]], QPixmap] = {}
        self._placeholder_cache: dict[Tuple[int, int], QPixmap] = {}

    @staticmethod
    def normalize_stadium_id(stadium_id: str | int) -> str:
        """Normalize stadium ID strings or integers to 3-digit padded format (e.g. '009')."""
        try:
            return f"{int(stadium_id):03d}"
        except (ValueError, TypeError):
            s = str(stadium_id).strip()
            return s.zfill(3) if s.isdigit() else s

    def get_pixmap(self, dds_path: Path | str | None, size: Tuple[int, int] = (52, 30)) -> QPixmap:
        """
        Load or fetch cached QPixmap for a DDS texture file path.
        """
        if not dds_path:
            return self.get_placeholder(size)

        path_obj = Path(dds_path)
        if not path_obj.exists() or not path_obj.is_file():
            return self.get_placeholder(size)

        path_str = str(path_obj.resolve())
        cache_key = (path_str, size)

        if cache_key in self._pixmap_cache:
            return self._pixmap_cache[cache_key]

        try:
            # Decode DDS using Pillow
            pil_img = Image.open(path_str).convert("RGBA")
            w, h = pil_img.size
            data = pil_img.tobytes("raw", "RGBA")

            # Convert to PySide6 QImage -> QPixmap
            qimg = QImage(data, w, h, QImage.Format_RGBA8888)
            pixmap = QPixmap.fromImage(qimg)

            # Smoothly resize to requested target size
            scaled_pixmap = pixmap.scaled(
                size[0],
                size[1],
                Qt.KeepAspectRatioByExpanding,
                Qt.SmoothTransformation,
            )

            # Crop cleanly to exact requested rectangle if necessary
            if scaled_pixmap.width() > size[0] or scaled_pixmap.height() > size[1]:
                x = (scaled_pixmap.width() - size[0]) // 2
                y = (scaled_pixmap.height() - size[1]) // 2
                scaled_pixmap = scaled_pixmap.copy(x, y, size[0], size[1])

            self._pixmap_cache[cache_key] = scaled_pixmap
            return scaled_pixmap

        except Exception as e:
            self.logger.warning(f"Failed to decode DDS thumbnail '{dds_path}': {e}")
            return self.get_placeholder(size)

    def get_placeholder(self, size: Tuple[int, int] = (52, 30)) -> QPixmap:
        """Create and return a dark workstation themed placeholder QPixmap."""
        if size in self._placeholder_cache:
            return self._placeholder_cache[size]

        w, h = size
        pixmap = QPixmap(w, h)
        pixmap.fill(QColor(18, 28, 42))

        painter = QPainter(pixmap)
        painter.setPen(QColor(34, 50, 71))
        painter.drawRect(0, 0, w - 1, h - 1)
        painter.setPen(QColor(100, 116, 139))
        font = painter.font()
        font.setPixelSize(max(9, min(w // 5, h // 3)))
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(pixmap.rect(), Qt.AlignCenter, "STADIUM")
        painter.end()

        self._placeholder_cache[size] = pixmap
        return pixmap

    def clear_cache(self) -> None:
        """Clear cached QPixmaps."""
        self._pixmap_cache.clear()
        self._placeholder_cache.clear()
