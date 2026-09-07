from __future__ import annotations

import datetime
import logging
from pathlib import Path
from typing import Any

from audio_player import WinAudioPlayer
from config import AppConfig, ConfigManager
from core.models import KPIStatistics, MappedRow, StadiumState, StadiumStatus
from core.status_engine import StadiumStatusEngine
from core.thumbnail_manager import ThumbnailManager
from map_generator import DryRunReport, MapGenerator
from stadium_scanner import DiscoveredStadium, StadiumScanner
from team_matcher import TeamMatcher
from team_pdf_parser import TeamPdfParser
from validator import MappingValidator
from web_research import (
    BingSearchProvider,
    DuckDuckGoSearchProvider,
    GoogleSearchProvider,
    StadiumResearchResult,
    WebSearchProvider,
    WebStadiumResearcher,
    WikipediaSearchProvider,
)


class PersistentResearchCache:
    """Auditable research cache stored in settings_PSM/data/research_cache.json."""

    def __init__(self, base_dir: Path, logger: logging.Logger | None = None):
        # Store cache in settings_PSM/data/ for portability
        data_dir = base_dir / "settings_PSM" / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        self.cache_path = data_dir / "research_cache.json"
        self.state_path = data_dir / "app_state.json"
        self.logger = logger or logging.getLogger("stadium_mapper.cache")
        self.cache: dict[str, dict[str, Any]] = {}
        self.load()

    def load(self) -> None:
        """Load cache from disk."""
        if self.cache_path.exists():
            try:
                import json
                with open(self.cache_path, "r", encoding="utf-8") as f:
                    self.cache = json.load(f)
                self.logger.info(f"Loaded {len(self.cache)} entries from research cache")
            except Exception as e:
                self.logger.warning(f"Error loading cache: {e}")
                self.cache = {}

    def save(self) -> None:
        """Save cache to disk."""
        try:
            import json
            with open(self.cache_path, "w", encoding="utf-8") as f:
                json.dump(self.cache, f, indent=2, ensure_ascii=False)
        except Exception as e:
            self.logger.error(f"Error saving cache: {e}")

    def save_state(self, manual_mappings: dict, skipped_stadiums: set, disabled_stadiums: set | None = None) -> None:
        """Persist manual mappings, skipped stadiums, and disabled stadiums to app_state.json."""
        try:
            import json
            state = {
                "manual_mappings": {
                    k: [{"team_id": r.team_id, "stadium_id": r.stadium_id, "stadium_name": r.stadium_name,
                          "stadium_path": r.stadium_path, "status": r.status, "confidence": r.confidence}
                         for r in rows]
                    for k, rows in manual_mappings.items()
                },
                "skipped_stadiums": list(skipped_stadiums),
                "disabled_stadiums": list(disabled_stadiums or set()),
            }
            with open(self.state_path, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2, ensure_ascii=False)
        except Exception as e:
            self.logger.error(f"Error saving app state: {e}")

    def load_state(self) -> tuple[dict, set, set]:
        """Load manual mappings, skipped stadiums, and disabled stadiums from app_state.json."""
        manual_mappings: dict = {}
        skipped: set = set()
        disabled: set = set()
        if not self.state_path.exists():
            return manual_mappings, skipped, disabled
        try:
            import json
            with open(self.state_path, "r", encoding="utf-8") as f:
                state = json.load(f)
            for k, rows_data in state.get("manual_mappings", {}).items():
                manual_mappings[k] = [
                    MappedRow(
                        team_id=r.get("team_id", 0),
                        stadium_id=r.get("stadium_id", "000"),
                        stadium_name=r.get("stadium_name", k),
                        stadium_path=r.get("stadium_path", k),
                        status=r.get("status", "MANUAL"),
                        confidence=r.get("confidence", 1.0),
                    )
                    for r in rows_data
                ]
            skipped = set(state.get("skipped_stadiums", []))
            disabled = set(state.get("disabled_stadiums", []))
            self.logger.info(f"Restored {len(manual_mappings)} manual mappings, {len(skipped)} skipped, {len(disabled)} disabled from state")
        except Exception as e:
            self.logger.warning(f"Error loading app state: {e}")
        return manual_mappings, skipped, disabled


    def get(self, stadium_name: str) -> dict[str, Any] | None:
        """Get cached research for a stadium."""
        return self.cache.get(stadium_name.lower().strip())

    def put(self, stadium_name: str, result: StadiumResearchResult, team_id: int | None = None, stadium_id: str | None = None) -> None:
        """Store research result in cache."""
        key = stadium_name.lower().strip()
        data = result.to_dict()
        data["team_id"] = team_id
        if stadium_id:
            data["stadium_id"] = stadium_id
        data["search_date"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.cache[key] = data
        self.save()

    def put_manual_multi(self, stadium_name: str, rows: list[MappedRow]) -> None:
        """Store multiple manual 4-column overrides persistently in research cache."""
        key = stadium_name.lower().strip()
        manual_rows_data = [
            {
                "team_id": r.team_id,
                "stadium_id": r.stadium_id,
                "stadium_name": r.stadium_name,
                "stadium_path": r.stadium_path,
            }
            for r in rows
        ]
        data = {
            "stadium_name": rows[0].stadium_name if rows else stadium_name,
            "club_name": rows[0].stadium_name if rows else stadium_name,
            "team_id": rows[0].team_id if rows else 0,
            "stadium_id": rows[0].stadium_id if rows else "000",
            "stadium_path": rows[0].stadium_path if rows else stadium_name,
            "manual_rows": manual_rows_data,
            "confidence": 1.0,
            "is_manual": True,
            "resolved": True,
            "reasoning": f"Manually specified {len(rows)} 4-column mapping(s) by user.",
            "search_date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        self.cache[key] = data
        self.save()

    def clear(self) -> None:
        """Clear cache."""
        self.cache.clear()
        self.save()


class StadiumMapperController:
    """
    Central Controller orchestrating scanner, parser, researcher, matcher, generator,
    audio player, configuration, and authoritative status engine.
    """

    def __init__(self, base_dir: Path, logger: logging.Logger | None = None):
        self.base_dir = base_dir.resolve()
        self.logger = logger or logging.getLogger("stadium_mapper")
        self.config_mgr = ConfigManager(self.base_dir, self.logger)
        self.config = self.config_mgr.config
        self.cache = PersistentResearchCache(self.base_dir, self.logger)
        self.thumbnail_mgr = ThumbnailManager(self.logger)

        self.pdf_parser = TeamPdfParser(logger=self.logger)
        self.matcher = TeamMatcher(self.pdf_parser, self.logger)
        self.validator = MappingValidator(self.logger)

        self.discovered_stadiums: list[DiscoveredStadium] = []
        self.research_results: dict[str, StadiumResearchResult] = {}

        # Restore persisted state (manual mappings + skipped + disabled) from previous session
        self.manual_mappings, self.skipped_stadiums, self.disabled_stadiums = self.cache.load_state()

        self.load_pdf()



    def configure_paths(self, server_dir: str, pdf_path: str | None = None) -> None:
        """Update server directory and optionally PDF path."""
        kwargs: dict[str, Any] = {"stadium_server_dir": server_dir}
        if pdf_path:
            kwargs["team_pdf_path"] = pdf_path
        self.config_mgr.update(**kwargs)

    def load_pdf(self) -> bool:
        """Load and parse the specified PDF or fallback to data/team_list.pdf."""
        pdf_path = self.config.team_pdf_path
        if not pdf_path or not Path(pdf_path).exists():
            default_pdf = self.base_dir / "data" / "team_list.pdf"
            if default_pdf.exists():
                pdf_path = str(default_pdf)
                self.config_mgr.update(team_pdf_path=pdf_path)

        if not pdf_path or not Path(pdf_path).exists():
            self.logger.error("Team PDF path not found.")
            return False

        success = self.pdf_parser.load_pdf(pdf_path)
        if success:
            self.matcher._build_alias_index()
        return success

    def scan_stadiums(self) -> list[StadiumState]:
        """Scan stadium server directory and derive authoritative StadiumStates."""
        server_dir = self.config.stadium_server_dir
        if not server_dir or not Path(server_dir).exists():
            self.logger.error("Stadium Server directory not set or path does not exist.")
            return []

        scanner = StadiumScanner(server_dir, self.logger)
        self.discovered_stadiums = scanner.scan()

        # Restore cached research results
        if self.config.enable_cache:
            for s in self.discovered_stadiums:
                cached = self.cache.get(s.display_name)
                if cached and cached.get("club_name"):
                    self.research_results[s.display_name] = StadiumResearchResult(
                        stadium_name=s.display_name,
                        club_name=cached.get("club_name"),
                        alternative_clubs=cached.get("alternative_clubs", []),
                        confidence=cached.get("confidence", 0.90),
                        reasoning=cached.get("reasoning", "Restored from persistent research cache"),
                        is_shared=cached.get("is_shared", False),
                    )

        return self.get_all_states()

    def build_search_provider(self, custom_provider: str | None = None) -> list[WebSearchProvider]:
        """Instantiate search providers based on config or custom provider parameter."""
        providers: list[WebSearchProvider] = []
        prov_name = (custom_provider or self.config.search_provider).lower()

        if prov_name == "google" and self.config.google_api_key and self.config.google_search_engine_id:
            providers.append(GoogleSearchProvider(
                api_key=self.config.google_api_key,
                search_engine_id=self.config.google_search_engine_id,
                logger=self.logger,
            ))
        elif prov_name == "bing" and self.config.bing_api_key:
            providers.append(BingSearchProvider(
                api_key=self.config.bing_api_key,
                logger=self.logger,
            ))
        elif prov_name == "wikipedia":
            providers.append(WikipediaSearchProvider(logger=self.logger))
        else:
            providers.append(DuckDuckGoSearchProvider(logger=self.logger))

        # Add fallbacks
        providers.append(WikipediaSearchProvider(logger=self.logger))
        providers.append(DuckDuckGoSearchProvider(logger=self.logger))
        return providers

    def research_stadium(
        self,
        stadium_name: str,
        force_refresh: bool = False,
        custom_provider: str | None = None,
        custom_query: str | None = None
    ) -> StadiumState:
        """Research a single stadium using cache or live web search and return updated StadiumState."""
        s_obj = next((s for s in self.discovered_stadiums if s.display_name == stadium_name), None)
        search_query = custom_query or (s_obj.search_name if s_obj else stadium_name)

        if not force_refresh and not custom_query and self.config.enable_cache:
            cached = self.cache.get(stadium_name)
            if cached and cached.get("club_name"):
                res = StadiumResearchResult(
                    stadium_name=stadium_name,
                    club_name=cached.get("club_name"),
                    alternative_clubs=cached.get("alternative_clubs", []),
                    confidence=cached.get("confidence", 0.85),
                    reasoning=cached.get("reasoning", "Loaded from research cache"),
                    is_shared=cached.get("is_shared", False),
                )
                self.research_results[stadium_name] = res
                return self.get_stadium_state(stadium_name)

        providers = self.build_search_provider(custom_provider)
        researcher = WebStadiumResearcher(providers=providers, logger=self.logger)

        res = researcher.identify_stadium_club(search_query)
        res.stadium_name = stadium_name

        team_id = None
        if res.club_name:
            team_id = self.matcher.resolve_team_id(res.club_name)

        self.cache.put(stadium_name, res, team_id)
        self.research_results[stadium_name] = res
        return self.get_stadium_state(stadium_name)

    def set_manual_mappings(self, stadium_name: str, rows: list[MappedRow]) -> StadiumState:
        """Set multi-team manual mapping rows for a stadium."""
        self.manual_mappings[stadium_name] = rows
        if stadium_name in self.skipped_stadiums:
            self.skipped_stadiums.remove(stadium_name)
        self.cache.put_manual_multi(stadium_name, rows)
        self.cache.save_state(self.manual_mappings, self.skipped_stadiums, self.disabled_stadiums)
        return self.get_stadium_state(stadium_name)

    def mark_skipped(self, stadium_name: str) -> StadiumState:
        """Mark a stadium to be skipped from map_teams.txt."""
        self.skipped_stadiums.add(stadium_name)
        if stadium_name in self.manual_mappings:
            del self.manual_mappings[stadium_name]
        self.cache.save_state(self.manual_mappings, self.skipped_stadiums, self.disabled_stadiums)
        return self.get_stadium_state(stadium_name)

    def set_stadium_disabled(self, stadium_name: str, disabled: bool) -> None:
        """Mark a stadium as disabled or enabled in map_teams.txt."""
        name_key = stadium_name.strip()
        if disabled:
            self.disabled_stadiums.add(name_key)
        else:
            self.disabled_stadiums.discard(name_key)
            self.disabled_stadiums.discard(name_key.lower())
        self.cache.save_state(self.manual_mappings, self.skipped_stadiums, self.disabled_stadiums)

    def clear_stadium_cache(self, stadium_name: str) -> None:
        """Clear cached research for a single stadium (force re-research on next call)."""
        key = stadium_name.lower().strip()
        if key in self.cache.cache:
            del self.cache.cache[key]
            self.cache.save()
        if stadium_name in self.research_results:
            del self.research_results[stadium_name]

    def get_stadium_state(self, stadium_name: str) -> StadiumState:
        """Single authoritative source of truth for a stadium's mapping state."""
        s_obj = next((s for s in self.discovered_stadiums if s.display_name == stadium_name), None)
        s_ids = s_obj.stadium_ids if s_obj else ["000"]
        s_path = s_obj.full_path if s_obj else None
        thumb_path = s_obj.get_thumbnail_path() if s_obj else None

        cached_data = self.cache.get(stadium_name)

        return StadiumStatusEngine.derive_stadium_state(
            stadium_name=stadium_name,
            stadium_ids=s_ids,
            stadium_full_path=s_path,
            thumbnail_path=thumb_path,
            manual_mappings=self.manual_mappings,
            skipped_stadiums=self.skipped_stadiums,
            research_results=self.research_results,
            cache_data=cached_data,
            pdf_team_names=self.pdf_parser.id_to_name,
            resolve_team_tuples_fn=self.matcher.resolve_multiple_team_ids,
        )

    def get_all_states(self) -> list[StadiumState]:
        """Get authoritative StadiumState list for all discovered stadiums."""
        return [self.get_stadium_state(s.display_name) for s in self.discovered_stadiums]

    def get_statistics(self) -> KPIStatistics:
        """Calculate aggregate KPI metrics directly from current authoritative StadiumStates."""
        states = self.get_all_states()
        return StadiumStatusEngine.calculate_statistics(states)

    def build_mappings(self) -> list[MappedRow]:
        """Build full list of valid 4-column MappedRow entries for map_teams.txt."""
        all_rows: list[MappedRow] = []

        for s in self.discovered_stadiums:
            name = s.display_name
            state = self.get_stadium_state(name)

            if state.is_skipped or state.status == StadiumStatus.UNRESOLVED:
                continue

            all_rows.extend(state.mapped_rows)

        return all_rows

    def generate_map_file(self) -> tuple[bool, str]:
        """Write map_teams.txt file using authoritative mappings."""
        server_dir = self.config.stadium_server_dir
        if not server_dir or not Path(server_dir).exists():
            return False, "Stadium Server directory not set or directory does not exist."

        rows = self.build_mappings()
        generator = MapGenerator(server_dir, self.logger)
        success, msg = generator.write_map_file(
            rows,
            create_backup_first=self.config.backup_existing_map,
            disabled_stadiums=self.disabled_stadiums,
        )
        return success, msg

    def generate_dry_run(self) -> DryRunReport:
        """Generate dry run report."""
        server_dir = self.config.stadium_server_dir or str(self.base_dir)
        rows = self.build_mappings()
        generator = MapGenerator(server_dir, self.logger)
        return generator.generate_dry_run(rows, len(self.discovered_stadiums))

