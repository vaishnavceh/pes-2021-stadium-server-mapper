from __future__ import annotations

import datetime
from pathlib import Path
from typing import Any, Sequence

from core.models import KPIStatistics, MappedRow, StadiumState, StadiumStatus


class StadiumStatusEngine:
    """
    Central Authoritative Status Engine for PES Stadium Server Mapper.
    Calculates single source of truth StadiumState for stadium folders and aggregate statistics.
    Prevents stale counters and status mismatches across Dashboard, Table, Sidebar, and Inspector.
    """

    @staticmethod
    def derive_stadium_state(
        stadium_name: str,
        stadium_ids: list[str],
        stadium_full_path: Path | None,
        thumbnail_path: Path | None,
        manual_mappings: dict[str, list[MappedRow]],
        skipped_stadiums: set[str],
        research_results: dict[str, Any],
        cache_data: dict[str, Any] | None,
        pdf_team_names: dict[int, str],
        resolve_team_tuples_fn: Any,
        integrity_warnings: list[str] | None = None,
    ) -> StadiumState:
        """Derive authoritative StadiumState for a single stadium folder."""
        st_id = stadium_ids[0] if stadium_ids else "000"
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        warns = integrity_warnings or []


        # 1. Check explicitly skipped stadiums
        if stadium_name in skipped_stadiums:
            return StadiumState(
                stadium_name=stadium_name,
                stadium_id=st_id,
                status=StadiumStatus.SKIPPED,
                mapped_rows=[],
                confidence=0.0,
                identified_clubs="[SKIPPED]",
                pes_team_ids="N/A",
                reasoning="User explicitly chose to skip stadium from map_teams.txt output.",
                is_manual=False,
                is_skipped=True,
                preview_path=thumbnail_path,
                integrity_warnings=warns,
                last_updated=timestamp,
            )

        # 2. Check multi-team manual override mappings
        if stadium_name in manual_mappings and manual_mappings[stadium_name]:
            rows = manual_mappings[stadium_name]
            tids_str = ", ".join(str(r.team_id) for r in rows)
            clubs_str = " / ".join(pdf_team_names.get(r.team_id, f"Team_{r.team_id}") for r in rows)
            return StadiumState(
                stadium_name=stadium_name,
                stadium_id=rows[0].stadium_id if rows else st_id,
                status=StadiumStatus.MANUAL,
                mapped_rows=rows,
                confidence=1.0,
                identified_clubs=clubs_str,
                pes_team_ids=tids_str,
                reasoning=f"User defined {len(rows)} manual 4-column mapping(s).",
                is_manual=True,
                is_skipped=False,
                preview_path=thumbnail_path,
                integrity_warnings=warns,
                last_updated=timestamp,
            )

        # 3. Check live web research results and cache fallback
        res = research_results.get(stadium_name)
        c_entry = cache_data or {}

        club_name = res.club_name if (res and res.club_name) else c_entry.get("club_name")
        conf_val = res.confidence if res else c_entry.get("confidence", 0.0)
        reasoning = res.reasoning if res else c_entry.get("reasoning", "No web research data available.")

        team_tuples = resolve_team_tuples_fn(club_name) if club_name else []

        if team_tuples:
            tids_str = ", ".join(str(t[0]) for t in team_tuples)
            clubs_str = " / ".join(t[1] for t in team_tuples)
            mapped_rows = [
                MappedRow(
                    team_id=t[0],
                    stadium_id=st_id,
                    stadium_name=stadium_name,
                    stadium_path=stadium_name,
                    confidence=conf_val,
                    status="RESOLVED" if conf_val >= 0.90 else "REVIEW",
                    enabled=True,
                )
                for t in team_tuples
            ]
        else:
            tids_str = "N/A"
            clubs_str = club_name or "Unassigned"
            mapped_rows = []

        # Categorize status based on confidence threshold
        if conf_val >= 0.90 and team_tuples:
            status = StadiumStatus.RESOLVED
        elif club_name and team_tuples:
            status = StadiumStatus.REVIEW
        else:
            status = StadiumStatus.UNRESOLVED

        return StadiumState(
            stadium_name=stadium_name,
            stadium_id=st_id,
            status=status,
            mapped_rows=mapped_rows,
            confidence=conf_val,
            identified_clubs=clubs_str,
            pes_team_ids=tids_str,
            reasoning=reasoning,
            is_manual=False,
            is_skipped=False,
            preview_path=thumbnail_path,
            integrity_warnings=warns,
            last_updated=timestamp,
        )


    @staticmethod
    def calculate_statistics(states: Sequence[StadiumState]) -> KPIStatistics:
        """Calculate aggregate KPI metrics directly from current authoritative StadiumState list."""
        stats = KPIStatistics(total=len(states))

        for state in states:
            if state.status == StadiumStatus.RESOLVED:
                stats.resolved += 1
            elif state.status == StadiumStatus.REVIEW:
                stats.review += 1
            elif state.status == StadiumStatus.MANUAL:
                stats.manual += 1
            elif state.status == StadiumStatus.SKIPPED:
                stats.skipped += 1
            else:
                stats.unresolved += 1

        return stats
