"""
Team Matcher — Web Club to PES Team ID Resolver
===============================================

Matches web-discovered football club names to official PES Team IDs from the PDF database.
Uses exact matching, alias lookups, descriptor cleaning, and fuzzy matching.
"""

from __future__ import annotations

import difflib
import logging
import re
from typing import Optional

from team_pdf_parser import TeamPdfParser


class TeamMatcher:
    """Matches club names to PES Team IDs."""

    # Generic fake teams in default PES databases that should never be fuzzy-matched
    GENERIC_TEAM_IDS = {199, 200, 902, 903, 904, 905, 906, 907, 908, 140, 141, 142, 1796, 2511, 2512, 2513}

    # Built-in aliases mapping web club names to standard PDF team names
    CLUB_ALIASES: dict[str, list[str]] = {
        "Manchester United": ["Man Utd", "Man United", "Man U", "MUFC", "United", "Manchester United Football Club", "Manchester United FC"],
        "Arsenal": ["The Gunners", "ARS", "Arsenal FC", "Arsenal Football Club"],
        "Chelsea": ["Chelsea FC", "The Blues", "CFC", "Chelsea Football Club"],
        "Liverpool": ["Liverpool FC", "LFC", "The Reds", "Liverpool Football Club"],
        "West Ham United FC": ["West Ham", "West Ham United", "WHUFC", "The Hammers", "West Ham United Football Club"],
        "Newcastle United": ["Newcastle", "NUFC", "The Magpies", "The Toon", "Newcastle United Football Club"],
        "Aston Villa": ["Villa", "AVFC", "Aston Villa Football Club", "Aston Villa FC"],
        "FC Barcelona": ["Barcelona", "Barca", "Barça", "FCB", "Futbol Club Barcelona"],
        "Real Madrid": ["Real Madrid CF", "Madrid", "RMCF", "Los Blancos", "Real Madrid Club de Fútbol"],
        "Manchester City": ["Man City", "City", "MCFC", "Citizens", "Manchester City FC", "Manchester City Football Club"],
        "Tottenham Hotspur FC": ["Tottenham", "Tottenham Hotspur", "Spurs", "THFC", "Tottenham Hotspur Football Club"],
        "Everton": ["Everton FC", "The Toffees", "EFC", "Everton Football Club"],
        "Southampton FC": ["Southampton", "Saints", "Soton", "Southampton Football Club"],
        "Crystal Palace": ["Palace", "CPFC", "The Eagles", "Crystal Palace FC", "Crystal Palace Football Club"],
        "Burnley": ["Burnley FC", "The Clarets", "Burnley Football Club"],
        "Stoke City FC": ["Stoke City", "Stoke", "The Potters", "Stoke City Football Club"],
        "Sunderland AFC": ["Sunderland", "The Black Cats", "Sunderland Football Club"],
        "West Bromich": ["West Brom", "West Bromwich Albion", "WBA", "The Baggies"],
        "Leichester": ["Leicester", "Leicester City", "LCFC", "The Foxes", "Leicester City Football Club"],
        "Inter": ["Inter Milan", "Internazionale", "FC Internazionale", "Inter FC", "FC Internazionale Milano"],
        "AC Milan": ["Milan", "ACM", "Rossoneri", "Associazione Calcio Milan"],
        "Juventus": ["Juve", "Juventus FC", "The Old Lady", "Juventus Football Club"],
        "Bayern Munchen": ["Bayern Munich", "Bayern München", "FC Bayern", "FCB Munich", "FC Bayern München"],
        "Paris Saint-Germain": ["PSG", "Paris SG", "Paris Saint Germain", "Paris Saint-Germain FC"],
        "Atletico Madrid": ["Atletico", "Atlético Madrid", "Atlético", "Atleti", "Club Atlético de Madrid"],
        "S.S. Lazio": ["Lazio", "SS Lazio", "Società Sportiva Lazio"],
        "AS Roma": ["Roma", "AS Roma", "Associazione Sportiva Roma"],
        "ACF Fiorentina": ["Fiorentina", "La Viola"],
    }

    # Extended team IDs for Premier League Option File teams not present in default base PDF
    EXTENDED_MOD_TEAMS: dict[int, str] = {
        377: "Brighton & Hove Albion",
        378: "Brentford",
        379: "Fulham",
        382: "Leeds United",
        387: "Nottingham Forest",
        389: "Wolverhampton Wanderers",
        390: "AFC Bournemouth",
    }

    def __init__(self, pdf_parser: TeamPdfParser, logger: logging.Logger | None = None):
        self.pdf_parser = pdf_parser
        self.logger = logger or logging.getLogger("stadium_mapper.matcher")
        self.alias_map: dict[str, int] = {}
        self._build_alias_index()

    def _build_alias_index(self) -> None:
        """Index PDF names and aliases into normalized lookup table."""
        self.alias_map.clear()

        # Add extended mod teams first
        for tid, name in self.EXTENDED_MOD_TEAMS.items():
            norm = TeamPdfParser.normalize_name(name)
            self.alias_map[norm] = tid

        # Add PDF parsed teams
        for tid, name in self.pdf_parser.id_to_name.items():
            norm = TeamPdfParser.normalize_name(name)
            self.alias_map[norm] = tid

        # Add aliases
        for pdf_name, aliases in self.CLUB_ALIASES.items():
            norm_pdf = TeamPdfParser.normalize_name(pdf_name)
            tid = self.alias_map.get(norm_pdf) or self.pdf_parser.get_id(pdf_name)
            if tid is not None:
                for alias in aliases:
                    norm_alias = TeamPdfParser.normalize_name(alias)
                    self.alias_map[norm_alias] = tid

    def resolve_team_id(self, club_name: str) -> int | None:
        """
        Resolve a web-discovered club name to a PES Team ID.

        Order: Exact match -> Alias match -> Cleaned match -> Fuzzy match.
        """
        if not club_name:
            return None

        # Re-index if PDF parser updated
        if not self.alias_map:
            self._build_alias_index()

        norm = TeamPdfParser.normalize_name(club_name)

        # 1. Exact / Normalized Alias Match
        if norm in self.alias_map:
            return self.alias_map[norm]

        # 2. PDF direct lookup
        pdf_id = self.pdf_parser.get_id(club_name)
        if pdf_id is not None:
            return pdf_id

        # Clean national team descriptors if present
        clean_name = re.sub(r"\b(?:national football team|national team|football team|national)\b", "", club_name, flags=re.I).strip()
        if clean_name and clean_name != club_name:
            clean_norm = TeamPdfParser.normalize_name(clean_name)
            if clean_norm in self.alias_map:
                return self.alias_map[clean_norm]
            clean_pdf_id = self.pdf_parser.get_id(clean_name)
            if clean_pdf_id is not None:
                return clean_pdf_id

        # 3. Fuzzy match across non-generic teams
        valid_candidates = {
            k: v for k, v in self.alias_map.items() if v not in self.GENERIC_TEAM_IDS
        }
        matches = difflib.get_close_matches(norm, list(valid_candidates.keys()), n=1, cutoff=0.70)
        if matches:
            matched_key = matches[0]
            matched_id = valid_candidates[matched_key]
            self.logger.debug(f"Fuzzy matched '{club_name}' -> '{matched_key}' (TID {matched_id})")
            return matched_id

        # 4. Word overlap scoring
        query_words = set(norm.split()) - {"fc", "cf", "sc", "club", "the", "of"}
        if query_words:
            best_score = 0.0
            best_id = None
            for key, tid in valid_candidates.items():
                key_words = set(key.split()) - {"fc", "cf", "sc", "club", "the", "of"}
                if not key_words:
                    continue
                overlap = len(query_words & key_words)
                score = overlap / max(len(query_words), len(key_words))
                if score > best_score and score >= 0.5:
                    best_score = score
                    best_id = tid

            if best_id is not None:
                self.logger.debug(f"Word overlap matched '{club_name}' -> TID {best_id} (score={best_score:.2f})")
                return best_id

        return None

    def resolve_multiple_team_ids(self, club_str: str) -> list[tuple[int, str]]:
        """
        Extract and resolve multiple team IDs from compound strings like:
        'Real Madrid CF and the Spain national football team' or 'AC Milan / Inter Milan'.
        Returns list of (team_id, official_team_name) tuples.
        """
        if not club_str:
            return []

        # Fix concatenated words like 'CFand', 'FCand', 'Madridand' by inserting a space
        prepared = re.sub(r"([a-zA-Z]{2,})(and|&)", r"\1 \2", club_str, flags=re.I)
        parts = re.split(r"\s+(?:and\s+the|and\s+a|and|&|/|,)\s+", prepared, flags=re.I)
        results: list[tuple[int, str]] = []
        seen: set[int] = set()

        for part in parts:
            part_clean = part.strip()
            if not part_clean:
                continue

            tid = self.resolve_team_id(part_clean)
            if tid is not None and tid not in seen:
                seen.add(tid)
                official_name = self.pdf_parser.get_name(tid) or part_clean
                results.append((tid, official_name))

        # Fallback to single lookup if splitting yielded no matches
        if not results:
            tid = self.resolve_team_id(club_str)
            if tid is not None:
                results.append((tid, self.pdf_parser.get_name(tid) or club_str))

        return results
