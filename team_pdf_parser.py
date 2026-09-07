"""
Team PDF Parser — Runtime Team Database Parser
===============================================

Parses PES team-ID PDF files at runtime into searchable team databases.
Provides forward (ID -> Team Name) and reverse (Team Name -> ID) lookups.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional

try:
    import pymupdf  # PyMuPDF
except ImportError:
    try:
        import fitz as pymupdf
    except ImportError:
        pymupdf = None


class TeamPdfParser:
    """Parses team IDs dynamically from the supplied PES team-list PDF."""

    def __init__(self, pdf_path: str | Path | None = None, logger: logging.Logger | None = None):
        self.logger = logger or logging.getLogger("stadium_mapper.pdf_parser")
        self.id_to_name: dict[int, str] = {}
        self.name_to_id: dict[str, int] = {}
        self.pdf_path = Path(pdf_path) if pdf_path else None

        if self.pdf_path:
            self.load_pdf(self.pdf_path)

    def load_pdf(self, pdf_path: str | Path) -> bool:
        """Parse a team-ID PDF file."""
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            self.logger.error(f"Team PDF file not found: {pdf_path}")
            return False

        if pymupdf is None:
            self.logger.error("PyMuPDF (pymupdf) is required to parse team PDF files.")
            return False

        self.logger.info(f"Parsing team-ID PDF: {pdf_path}")
        try:
            doc = pymupdf.open(str(pdf_path))
            full_text = "\n".join(page.get_text() for page in doc)
            doc.close()
            return self._parse_text(full_text)
        except Exception as e:
            self.logger.error(f"Error reading PDF {pdf_path}: {e}")
            return False

    def _parse_text(self, text: str) -> bool:
        """Extract team IDs and team names using regex."""
        self.id_to_name.clear()
        self.name_to_id.clear()

        pattern = re.compile(r"id:\s+(\d+)\s+\(0x[0-9a-fA-F]+\)\s+(.+)")
        count = 0

        for match in pattern.finditer(text):
            team_id = int(match.group(1))
            team_name = match.group(2).strip()

            # Filter out invalid / placeholder entries
            if not team_name or team_name.lower() in ("(null)", "null"):
                continue
            if "MASTERLEAGUE" in team_name.upper():
                continue

            self.id_to_name[team_id] = team_name
            norm_key = self.normalize_name(team_name)
            self.name_to_id[norm_key] = team_id
            count += 1

        self.logger.info(f"Successfully loaded {count} team IDs from PDF")
        return count > 0

    @staticmethod
    def normalize_name(name: str) -> str:
        """Normalize team name for reverse lookup."""
        name = name.lower().strip()
        # Remove common FC/CF/SC suffixes
        name = re.sub(r"\b(?:fc|cf|sc|afc|fk|sk|club)\b", "", name)
        name = re.sub(r"\s+", " ", name).strip()
        return name

    def get_name(self, team_id: int) -> str | None:
        """Get official team name for a given team ID."""
        return self.id_to_name.get(team_id)

    def get_id(self, team_name: str) -> int | None:
        """Get team ID for a given team name using normalized matching."""
        norm = self.normalize_name(team_name)
        return self.name_to_id.get(norm)

    def get_all(self) -> dict[int, str]:
        """Return all parsed team ID -> name mappings."""
        return dict(self.id_to_name)

    def get_team_suggestions(self, query: str, limit: int = 15) -> list[tuple[int, str]]:
        """Return list of (team_id, team_name) tuples matching search query for live suggestions."""
        if not query or len(query.strip()) < 1:
            return []

        q_norm = query.lower().strip()
        results: list[tuple[int, str]] = []
        seen: set[int] = set()

        if q_norm.isdigit():
            tid = int(q_norm)
            if tid in self.id_to_name:
                results.append((tid, self.id_to_name[tid]))
                seen.add(tid)

        for tid, name in self.id_to_name.items():
            if tid in seen:
                continue
            if q_norm in name.lower() or q_norm in str(tid):
                results.append((tid, name))
                seen.add(tid)

        results.sort(key=lambda x: (0 if x[1].lower().startswith(q_norm) else 1, x[1]))
        return results[:limit]
