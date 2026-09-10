"""
Stadium Scanner — Filesystem Discovery & ID Extraction
======================================================

Recursively scans any given Stadium Server directory to discover installed stadiums,
extracts st### IDs (preserving leading zeros), and normalizes stadium names for web search.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class DiscoveredStadium:
    """Represents a stadium discovered on the user's filesystem."""
    folder_name: str
    display_name: str     # Actual folder name used in map_teams.txt
    search_name: str      # Cleaned name for web queries (e.g. strips "2025 UHD")
    stadium_ids: list[str]  # e.g. ["004", "007"]
    full_path: Path
    relative_path: str
    has_valid_assets: bool = True
    warnings: list[str] = field(default_factory=list)

    def check_integrity(self) -> list[str]:
        """Perform non-blocking folder structure health checks."""
        self.warnings.clear()
        if not self.full_path or not self.full_path.exists():
            self.warnings.append("Folder does not exist on disk")
            self.has_valid_assets = False
            return self.warnings

        asset_bg = self.full_path / "Asset" / "model" / "bg"
        common_bg = self.full_path / "common" / "bg"
        if not asset_bg.exists() and not common_bg.exists():
            self.warnings.append("Missing standard Asset/model/bg or common/bg structure")

        # Check for empty folder or zero files
        try:
            file_count = sum(1 for _ in self.full_path.rglob("*") if _.is_file())
            if file_count < 2:
                self.warnings.append("Folder contains no stadium model files")
        except Exception:
            pass

        self.has_valid_assets = (len(self.warnings) == 0)
        return self.warnings

    def primary_id(self) -> str:
        """Return the primary (first) stadium ID."""
        return self.stadium_ids[0] if self.stadium_ids else "000"


    def get_thumbnail_path(self) -> Path | None:
        """Find the DDS thumbnail file for this stadium if present."""
        if not self.full_path or not self.full_path.exists():
            return None

        # Check standard priority path: common/render/thumbnail/stadium/st{sid}.dds
        thumb_dir = self.full_path / "common" / "render" / "thumbnail" / "stadium"
        if thumb_dir.exists() and thumb_dir.is_dir():
            for sid in self.stadium_ids:
                dds_file = thumb_dir / f"st{sid}.dds"
                if dds_file.exists():
                    return dds_file

            # Fallback: check any .dds file in thumb_dir
            for f in thumb_dir.iterdir():
                if f.is_file() and f.suffix.lower() == ".dds":
                    return f

        # Fallback: recursive search for st*.dds inside stadium folder
        try:
            for root, _, files in os.walk(str(self.full_path)):
                for file in files:
                    if file.lower().endswith(".dds") and file.lower().startswith("st"):
                        return Path(root) / file
        except Exception:
            pass

        return None


class StadiumScanner:
    """Generic directory walker and stadium extractor."""

    # Regex to match stadium model folders like st004, st009, st123
    ST_PATTERN = re.compile(r"^st(\d+)$", re.IGNORECASE)

    # Mod suffixes to remove when preparing web search queries
    STRIP_SUFFIXES = [
        "2025", "2024", "2023", "2022", "2021", "2020",
        "uhd", "4k", "hd", "8k",
        "v1", "v2", "v3", "v4", "v5",
        "final", "update", "updated", "remastered",
        "day", "night", "summer", "winter", "rain",
        "new", "old", "fix", "fixed",
    ]

    SEPARATORS = [" - ", " _ ", "_", "-"]

    def __init__(self, root_dir: str | Path, logger: logging.Logger | None = None):
        self.root_dir = Path(root_dir).resolve()
        self.logger = logger or logging.getLogger("stadium_mapper.scanner")

    def scan(self) -> list[DiscoveredStadium]:
        """
        Recursively scan the stadium server directory.

        Finds top-level stadium folders containing st### directories.
        """
        stadiums: list[DiscoveredStadium] = []

        if not self.root_dir.exists():
            self.logger.error(f"Stadium server path does not exist: {self.root_dir}")
            return stadiums

        self.logger.info(f"Scanning Stadium Server root: {self.root_dir}")

        for entry in sorted(self.root_dir.iterdir()):
            if not entry.is_dir():
                continue

            # Skip common non-stadium system/temporary folders
            if entry.name.lower() in ("epl", "pes_stadium_mapper", "__pycache__", ".git", ".vscode", "logs", "data"):
                continue

            # Find st### directories under this stadium folder
            st_ids = self._extract_stadium_ids(entry)
            if not st_ids:
                self.logger.debug(f"Skipping directory '{entry.name}': no st### ID found")
                continue

            display_name = entry.name
            search_name = self.normalize_for_search(display_name)
            rel_path = f".\\{display_name}"

            stadium = DiscoveredStadium(
                folder_name=entry.name,
                display_name=display_name,
                search_name=search_name,
                stadium_ids=st_ids,
                full_path=entry,
                relative_path=rel_path,
            )
            stadium.check_integrity()
            stadiums.append(stadium)
            self.logger.info(
                f"Discovered: '{display_name}' → IDs: {', '.join(st_ids)} | Search Query: '{search_name}' | Warnings: {len(stadium.warnings)}"
            )


        self.logger.info(f"Total stadiums discovered: {len(stadiums)}")
        return stadiums

    def _extract_stadium_ids(self, stadium_dir: Path) -> list[str]:
        """
        Search for st### directories inside a stadium folder.
        Uses exact priority ordering matching stadium_scanner.exe:
        1. common/render/thumbnail/stadium/st*
        2. common/bg/model/bg/draw_parameter/st*
        3. common/bg/model/bg/st*
        4. Asset/model/bg/st*
        5. Fallback recursive walk
        """
        st_ids: list[str] = []
        seen: set[str] = set()

        priority_subpaths = [
            stadium_dir / "common" / "render" / "thumbnail" / "stadium",
            stadium_dir / "common" / "bg" / "model" / "bg" / "draw_parameter",
            stadium_dir / "common" / "bg" / "model" / "bg",
            stadium_dir / "Asset" / "model" / "bg",
        ]

        for subpath in priority_subpaths:
            if subpath.exists() and subpath.is_dir():
                for child in subpath.iterdir():
                    if child.is_dir():
                        m = self.ST_PATTERN.match(child.name)
                        if m:
                            sid = m.group(1).zfill(3)
                            if sid not in seen:
                                seen.add(sid)
                                st_ids.append(sid)
                if st_ids:
                    # High priority path found (draw_parameter / thumbnail)!
                    return st_ids

        # Fallback to recursive directory walk if not found at priority locations
        if not st_ids:
            for root, dirs, _ in os.walk(str(stadium_dir)):
                for d in dirs:
                    m = self.ST_PATTERN.match(d)
                    if m:
                        sid = m.group(1).zfill(3)
                        if sid not in seen:
                            seen.add(sid)
                            st_ids.append(sid)

        return sorted(st_ids)

    def normalize_for_search(self, folder_name: str) -> str:
        """
        Clean mod version suffixes from folder name for internet queries.

        Does NOT alter the original display name used in map_teams.txt.
        """
        name = folder_name.strip()
        name = name.replace("_", " ")

        # Remove version/mod words
        for suffix in self.STRIP_SUFFIXES:
            pattern = re.compile(r"\s*\b" + suffix + r"\b\s*", re.IGNORECASE)
            name = pattern.sub(" ", name)

        # Strip extra separators and spaces
        for sep in self.SEPARATORS:
            name = name.strip(sep)

        name = re.sub(r"\s+", " ", name).strip()
        return name if name else folder_name
