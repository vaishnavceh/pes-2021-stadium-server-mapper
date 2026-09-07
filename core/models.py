from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class StadiumStatus(str, Enum):
    """Authoritative status enum for PES Stadium Server mapping."""
    RESOLVED = "RESOLVED"       # High confidence match (>=0.90) or validated match
    REVIEW = "REVIEW"           # Match needs user verification (0.75 <= conf < 0.90)
    UNRESOLVED = "UNRESOLVED"   # No team match found or confidence < 0.75
    MANUAL = "MANUAL"           # User manually set 4-column mapping
    SKIPPED = "SKIPPED"         # User explicitly chose to skip from map file


@dataclass
class MappedRow:
    """Single 4-column map_teams.txt entry (TEAM_ID, STADIUM_ID, STADIUM_NAME, STADIUM_PATH)."""
    team_id: int
    stadium_id: str
    stadium_name: str
    stadium_path: str
    confidence: float = 1.0
    status: str = "MANUAL"
    enabled: bool = True


@dataclass
class StadiumState:
    """
    Single Authoritative Model representing full state and identity for a stadium folder.
    Guarantees Dashboard == Table == Sidebar == Inspector == Filters at all times.
    """
    stadium_name: str
    stadium_id: str
    status: StadiumStatus
    mapped_rows: list[MappedRow] = field(default_factory=list)
    confidence: float = 0.0
    identified_clubs: str = "Unassigned"
    pes_team_ids: str = "N/A"
    reasoning: str = "No research analysis recorded."
    is_manual: bool = False
    is_skipped: bool = False
    preview_path: Path | None = None
    last_updated: str = field(default_factory=lambda: datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    def primary_team_id(self) -> int | None:
        if self.mapped_rows and self.mapped_rows[0].team_id > 0:
            return self.mapped_rows[0].team_id
        return None


@dataclass
class KPIStatistics:
    """Aggregate dashboard metrics calculated directly from authoritative StadiumState list."""
    total: int = 0
    resolved: int = 0
    review: int = 0
    unresolved: int = 0
    manual: int = 0
    skipped: int = 0

    @property
    def is_all_resolved(self) -> bool:
        return self.total > 0 and (self.resolved + self.manual + self.skipped) == self.total
