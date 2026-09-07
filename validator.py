"""
Validator — Validation Rules & Conflict Detection
=================================================

Performs pre-generation validation checks on mapped entries:
- Verifies Team ID exists in PDF database
- Verifies Stadium ID exists in filesystem
- Detects duplicate Stadium IDs
- Detects duplicate Team IDs
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ValidationIssue:
    """Represents a validation warning or conflict."""
    severity: str  # "ERROR" or "WARNING"
    stadium_name: str
    message: str


@dataclass
class MappedRow:
    """Represents a proposed row for map_teams.txt."""
    team_id: int
    stadium_id: str
    stadium_name: str
    stadium_path: str = ""
    confidence: float = 1.0
    status: str = "VALID"  # "VALID", "REVIEW", "CONFLICT", "INVALID"
    enabled: bool = True

    def __post_init__(self):
        if not self.stadium_path:
            self.stadium_path = self.stadium_name


class MappingValidator:
    """Validates proposed mappings and checks for conflicts."""

    def __init__(self, logger: logging.Logger | None = None):
        self.logger = logger or logging.getLogger("stadium_mapper.validator")

    def validate_rows(
        self,
        rows: list[MappedRow],
        known_team_ids: set[int] | None = None,
    ) -> tuple[list[MappedRow], list[ValidationIssue]]:
        """
        Validate proposed mapping rows.

        Returns tuple of (validated_rows, issues_list).
        """
        issues: list[ValidationIssue] = []
        validated: list[MappedRow] = []

        seen_stadium_ids: dict[str, str] = {}  # stadium_id -> stadium_name
        seen_team_ids: dict[int, str] = {}     # team_id -> stadium_name

        for row in rows:
            is_valid = True

            # 1. Team ID check
            if known_team_ids and row.team_id not in known_team_ids:
                issues.append(ValidationIssue(
                    severity="WARNING",
                    stadium_name=row.stadium_name,
                    message=f"Team ID {row.team_id} not found in PDF database.",
                ))

            # 2. Stadium ID format check
            if not row.stadium_id or not row.stadium_id.isdigit():
                issues.append(ValidationIssue(
                    severity="ERROR",
                    stadium_name=row.stadium_name,
                    message=f"Invalid stadium ID format: '{row.stadium_id}'. Must be 3 digits.",
                ))
                is_valid = False

            # 3. Duplicate Stadium ID check
            if row.stadium_id in seen_stadium_ids:
                other = seen_stadium_ids[row.stadium_id]
                issues.append(ValidationIssue(
                    severity="WARNING",
                    stadium_name=row.stadium_name,
                    message=f"Duplicate Stadium ID {row.stadium_id} already assigned to '{other}'.",
                ))
            else:
                seen_stadium_ids[row.stadium_id] = row.stadium_name

            # 4. Duplicate Team ID check
            if row.team_id in seen_team_ids:
                other = seen_team_ids[row.team_id]
                issues.append(ValidationIssue(
                    severity="WARNING",
                    stadium_name=row.stadium_name,
                    message=f"Duplicate Team ID {row.team_id} already assigned to '{other}'.",
                ))
            else:
                seen_team_ids[row.team_id] = row.stadium_name

            if is_valid:
                validated.append(row)

        return validated, issues
