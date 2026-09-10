"""
Map Generator — map_teams.txt Writer & Backup Manager
=====================================================

Writes the final map_teams.txt file adhering to the 4-column format:
    TEAM_ID,STADIUM_ID,STADIUM_NAME,STADIUM_PATH

Where STADIUM_PATH is the folder name (e.g., Anfield Road).
Saves backups inside a dedicated backup_map folder.
"""

from __future__ import annotations

import datetime
import logging
import shutil
from dataclasses import dataclass
from pathlib import Path

from validator import MappedRow


@dataclass
class DryRunReport:
    """Summary of changes for dry run mode."""
    total_stadiums_found: int
    high_confidence_count: int
    review_count: int
    unresolved_count: int
    proposed_rows: list[MappedRow]
    existing_rows_count: int
    backup_file_path: str | None = None


class MapGenerator:
    """Writes 4-column map_teams.txt and creates backups inside backup_map folder."""

    MAP_FILENAME = "map_teams.txt"
    BACKUP_FOLDER = "settings_PSM/backup_map"

    def __init__(self, stadium_server_dir: str | Path, logger: logging.Logger | None = None):
        self.server_dir = Path(stadium_server_dir).resolve()
        self.map_file_path = self.server_dir / self.MAP_FILENAME
        self.backup_dir = self.server_dir / self.BACKUP_FOLDER
        self.logger = logger or logging.getLogger("stadium_mapper.generator")

    def create_backup(self) -> Path | None:
        """Create a timestamped backup of map_teams.txt inside backup_map directory."""
        if not self.map_file_path.exists():
            return None

        try:
            content = self.map_file_path.read_text(encoding="utf-8").strip()
            if not content:
                return None
        except Exception:
            return None

        # Ensure backup_map folder exists
        self.backup_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        backup_name = f"map_teams_backup_{timestamp}.txt"
        backup_path = self.backup_dir / backup_name

        try:
            shutil.copy2(str(self.map_file_path), str(backup_path))
            self.logger.info(f"Created timestamped backup in backup_map: {backup_path}")
            return backup_path
        except Exception as e:
            self.logger.error(f"Failed to create backup: {e}")
            return None

    def generate_dry_run(
        self,
        rows: list[MappedRow],
        total_discovered: int,
    ) -> DryRunReport:
        """Generate a dry run report without touching any files on disk."""
        high_conf = sum(1 for r in rows if r.confidence >= 0.90)
        review = sum(1 for r in rows if 0.75 <= r.confidence < 0.90)
        unresolved = total_discovered - len(rows)

        existing_count = 0
        if self.map_file_path.exists():
            try:
                lines = [
                    line for line in self.map_file_path.read_text(encoding="utf-8").splitlines()
                    if line.strip() and not line.strip().startswith("#")
                ]
                existing_count = len(lines)
            except Exception:
                existing_count = 0

        report = DryRunReport(
            total_stadiums_found=total_discovered,
            high_confidence_count=high_conf,
            review_count=review,
            unresolved_count=unresolved,
            proposed_rows=rows,
            existing_rows_count=existing_count,
        )
        return report

    def write_map_file(
        self,
        rows: list[MappedRow],
        create_backup_first: bool = True,
        backup: bool | None = None,
        disabled_stadiums: set[str] | None = None,
    ) -> tuple[bool, str]:
        """
        Write rows to map_teams.txt in 4-column format:
            TEAM_ID,STADIUM_ID,STADIUM_NAME,STADIUM_PATH
        Preserves commented-out (#) disabled states from Stadium Server Manager or existing map_teams.txt.
        Returns: (success: bool, message: str)
        """
        if backup is not None:
            create_backup_first = backup

        disabled_keys: set[tuple[int, str]] = set()
        disabled_paths: set[str] = set()

        # 1. Read existing disabled entries (#) from map_teams.txt
        if self.map_file_path.exists():
            try:
                with open(self.map_file_path, "r", encoding="utf-8") as f:
                    for line in f:
                        sline = line.strip()
                        if sline.startswith("#"):
                            clean = sline.lstrip("#").strip()
                            parts = [p.strip() for p in clean.split(",")]
                            if len(parts) >= 4 and parts[0].isdigit():
                                try:
                                    tid = int(parts[0])
                                    path_str = parts[3].lower()
                                    disabled_keys.add((tid, path_str))
                                    disabled_paths.add(path_str)
                                    disabled_paths.add(parts[2].lower())
                                except ValueError:
                                    pass
            except Exception as e:
                self.logger.warning(f"Could not read existing disabled states from map_teams.txt: {e}")

        # 2. Also incorporate controller's disabled_stadiums
        if disabled_stadiums:
            for s in disabled_stadiums:
                disabled_paths.add(s.lower().strip())

        if create_backup_first:
            self.create_backup()

        try:
            active_count = 0
            disabled_count = 0

            with open(self.map_file_path, "w", encoding="utf-8") as f:
                # Write header documentation
                f.write("# PES 2021 Stadium Server - Team-to-Stadium Mapping\n")
                f.write("# Generated automatically by Intelligent Stadium Mapper\n")
                f.write(f"# Date: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write("# Format: TEAM_ID,STADIUM_ID,STADIUM_NAME,STADIUM_PATH\n")
                f.write("#\n")

                # Sort by Team ID
                sorted_rows = sorted(rows, key=lambda r: r.team_id)

                for row in sorted_rows:
                    path_val = row.stadium_path or row.stadium_name
                    p_lower = path_val.lower().strip()
                    n_lower = row.stadium_name.lower().strip()

                    row_enabled = getattr(row, "enabled", True)
                    is_disabled = (
                        (not row_enabled)
                        or (p_lower in disabled_paths)
                        or (n_lower in disabled_paths)
                        or ((row.team_id, p_lower) in disabled_keys)
                    )

                    prefix = "#" if is_disabled else ""
                    if is_disabled:
                        disabled_count += 1
                    else:
                        active_count += 1

                    line = f"{prefix}{row.team_id},{row.stadium_id},{row.stadium_name},{path_val}\n"
                    f.write(line)

            msg = f"Successfully generated {len(rows)} entries in map_teams.txt ({active_count} Active, {disabled_count} Disabled)."
            self.logger.info(msg)
            return True, msg
        except Exception as e:
            err_msg = f"Failed to write map_teams.txt: {e}"
            self.logger.error(err_msg)
            return False, err_msg

    def write_competitions_map(self, comp_entries: list[dict[str, str]]) -> tuple[bool, str]:
        """Write map_competitions.txt file (COMP_ID, STADIUM_ID, STADIUM_NAME, STADIUM_PATH)."""
        comp_file = self.server_dir / "map_competitions.txt"
        try:
            with open(comp_file, "w", encoding="utf-8") as f:
                f.write("# PES 2021 Stadium Server - Competition Mapping\n")
                f.write(f"# Date: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write("# Format: COMP_ID,STADIUM_ID,STADIUM_NAME,STADIUM_PATH\n#\n")
                for entry in comp_entries:
                    prefix = "#" if entry.get("disabled") else ""
                    line = f"{prefix}{entry['comp_id']},{entry['stadium_id']},{entry['stadium_name']},{entry['stadium_path']}\n"
                    f.write(line)
            msg = f"Successfully updated map_competitions.txt ({len(comp_entries)} entries)."
            self.logger.info(msg)
            return True, msg
        except Exception as e:
            err_msg = f"Failed to write map_competitions.txt: {e}"
            self.logger.error(err_msg)
            return False, err_msg

    def write_comp_finals_map(self, finals_entries: list[dict[str, str]]) -> tuple[bool, str]:
        """Write map_comp_finals.txt file (COMP_ID, STADIUM_ID, STADIUM_NAME, STADIUM_PATH)."""
        finals_file = self.server_dir / "map_comp_finals.txt"
        try:
            with open(finals_file, "w", encoding="utf-8") as f:
                f.write("# PES 2021 Stadium Server - Competition Finals Mapping\n")
                f.write(f"# Date: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write("# Format: COMP_ID,STADIUM_ID,STADIUM_NAME,STADIUM_PATH\n#\n")
                for entry in finals_entries:
                    prefix = "#" if entry.get("disabled") else ""
                    line = f"{prefix}{entry['comp_id']},{entry['stadium_id']},{entry['stadium_name']},{entry['stadium_path']}\n"
                    f.write(line)
            msg = f"Successfully updated map_comp_finals.txt ({len(finals_entries)} entries)."
            self.logger.info(msg)
            return True, msg
        except Exception as e:
            err_msg = f"Failed to write map_comp_finals.txt: {e}"
            self.logger.error(err_msg)
            return False, err_msg


