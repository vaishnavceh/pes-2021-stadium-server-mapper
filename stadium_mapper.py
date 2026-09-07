#!/usr/bin/env python3
"""
PES 2021 Stadium Server Intelligent map_teams.txt Generator
============================================================
Version: Nightly Build 1.0.0 — PES NIGHT COMMAND Master Edition

A production-grade, generic, dynamic application that automatically scans installed
PES 2021 stadiums, identifies real football clubs using LIVE WEB SEARCH,
cross-references official PES Team IDs from a supplied PDF, and generates
a strict 4-column map_teams.txt:

    TEAM_ID,STADIUM_ID,STADIUM_NAME,STADIUM_PATH

Zero hardcoded stadiums. Zero hardcoded team databases.

Usage:
    python stadium_mapper.py                              # GUI mode (default)
    python stadium_mapper.py --stadium-server "V:\\..." --auto
    python stadium_mapper.py --help
"""

from __future__ import annotations

import argparse
import datetime
import json
import logging
import os
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from pathlib import Path
from typing import Any, Optional

from PIL import Image, ImageTk

# UTF-8 Console Fix for Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Import modular application components
from audio_player import WinAudioPlayer
from config import AppConfig, ConfigManager
from stadium_scanner import DiscoveredStadium, StadiumScanner
from team_pdf_parser import TeamPdfParser
from web_research import (
    BingSearchProvider,
    DuckDuckGoSearchProvider,
    GoogleSearchProvider,
    StadiumResearchResult,
    WebSearchProvider,
    WebStadiumResearcher,
    WikipediaSearchProvider,
)
from team_matcher import TeamMatcher
from validator import MappingValidator, MappedRow, ValidationIssue
from map_generator import DryRunReport, MapGenerator


from enum import Enum
from dataclasses import dataclass, field

APP_VERSION = "Nightly Build 1.0.0"


# ---------------------------------------------------------------------------
# Authoritative Stadium Mapping State Model
# ---------------------------------------------------------------------------

class StadiumStatus(str, Enum):
    RESOLVED = "RESOLVED"       # High confidence match (>=0.90) or validated match
    REVIEW = "REVIEW"           # Match needs user verification (0.75 <= conf < 0.90)
    UNRESOLVED = "UNRESOLVED"   # No team match found or confidence < 0.75
    MANUAL = "MANUAL"           # User manually set 4-column mapping
    SKIPPED = "SKIPPED"         # User explicitly chose to skip from map file


@dataclass
class StadiumState:
    stadium_name: str
    stadium_id: str
    status: StadiumStatus
    mapped_rows: list[MappedRow]
    confidence: float
    identified_clubs: str
    pes_team_ids: str
    reasoning: str
    is_manual: bool
    is_skipped: bool
    preview_path: Path | None
    last_updated: str


# ---------------------------------------------------------------------------
# DDS Thumbnail Decoding & Caching Pipeline
# ---------------------------------------------------------------------------

class DdsThumbnailLoader:
    """
    Decodes, converts, resizes, and caches DDS stadium thumbnails for Tkinter UI.
    """
    def __init__(self):
        self.cache: dict[tuple[str, tuple[int, int]], ImageTk.PhotoImage] = {}
        self.placeholders: dict[tuple[int, int], ImageTk.PhotoImage] = {}

    def get_thumbnail(self, dds_path: Path | str | None, size: tuple[int, int] = (52, 30)) -> ImageTk.PhotoImage:
        """Get or load PhotoImage thumbnail for a DDS file path."""
        if not dds_path:
            return self.get_placeholder(size)

        path_str = str(dds_path)
        cache_key = (path_str, size)
        if cache_key in self.cache:
            return self.cache[cache_key]

        try:
            if not Path(path_str).exists():
                return self.get_placeholder(size)

            img = Image.open(path_str).convert("RGBA")
            img_resized = img.resize(size, Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(img_resized)
            self.cache[cache_key] = photo
            return photo
        except Exception:
            return self.get_placeholder(size)

    def get_placeholder(self, size: tuple[int, int] = (52, 30)) -> ImageTk.PhotoImage:
        """Return generic stadium placeholder thumbnail."""
        if size not in self.placeholders:
            w, h = size
            img = Image.new("RGBA", (w, h), color=(18, 28, 42, 255))
            for x in range(w):
                img.putpixel((x, 0), (34, 50, 71, 255))
                img.putpixel((x, h - 1), (34, 50, 71, 255))
            for y in range(h):
                img.putpixel((0, y), (34, 50, 71, 255))
                img.putpixel((w - 1, y), (34, 50, 71, 255))
            self.placeholders[size] = ImageTk.PhotoImage(img)
        return self.placeholders[size]


# ---------------------------------------------------------------------------
# "PES NIGHT COMMAND" Visual System Design Tokens & Theme Engine
# ---------------------------------------------------------------------------

THEMES: dict[str, dict[str, str]] = {
    "pes_night": {
        "name": "PES Night Command (Default)",
        "bg": "#070B12",
        "bg_secondary": "#0B111C",
        "sidebar_bg": "#09101A",
        "sidebar_fg": "#94A3B8",
        "panel_bg": "#101824",
        "glass_bg": "#121C2A",
        "glass_border": "#223247",
        "elevated_bg": "#162232",
        "card_bg": "#121C2A",
        "inspector_bg": "#0B111C",
        "header_bg": "#0B111C",
        "header_fg": "#19A7FF",
        "fg": "#F1F5F9",
        "fg_secondary": "#94A3B8",
        "fg_muted": "#64748B",
        "accent": "#19A7FF",
        "accent_hover": "#42B8FF",
        "accent_deep": "#0878C9",
        "btn_bg": "#19A7FF",
        "btn_fg": "#FFFFFF",
        "tree_bg": "#0B111C",
        "tree_fg": "#F1F5F9",
        "tree_select": "#0878C9",
        "console_bg": "#05080D",
        "console_fg": "#56E39F",
        "badge_accept": "#35D07F",
        "badge_review": "#FFB547",
        "badge_unresolved": "#FF5C6C",
        "badge_manual": "#9B8CFF",
    },
    "cyber_blue": {
        "name": "Cyber Blue Neon",
        "bg": "#060A14",
        "bg_secondary": "#0B1426",
        "sidebar_bg": "#081020",
        "sidebar_fg": "#00F0FF",
        "panel_bg": "#0F1E36",
        "glass_bg": "#122442",
        "glass_border": "#1B3A6B",
        "elevated_bg": "#172E54",
        "card_bg": "#122442",
        "inspector_bg": "#0B1426",
        "header_bg": "#081020",
        "header_fg": "#00F0FF",
        "fg": "#E0F7FF",
        "fg_secondary": "#70C8E6",
        "fg_muted": "#4088A6",
        "accent": "#00F0FF",
        "accent_hover": "#33F3FF",
        "accent_deep": "#00A3B0",
        "btn_bg": "#00F0FF",
        "btn_fg": "#060A14",
        "tree_bg": "#0B1426",
        "tree_fg": "#E0F7FF",
        "tree_select": "#00A3B0",
        "console_bg": "#03060C",
        "console_fg": "#00FFCC",
        "badge_accept": "#00FF66",
        "badge_review": "#FFB454",
        "badge_unresolved": "#FF3366",
        "badge_manual": "#B266FF",
    },
    "midnight_gold": {
        "name": "Midnight Gold",
        "bg": "#0F0E0C",
        "bg_secondary": "#171512",
        "sidebar_bg": "#14120F",
        "sidebar_fg": "#D4AF37",
        "panel_bg": "#1F1B16",
        "glass_bg": "#26221C",
        "glass_border": "#3B342A",
        "elevated_bg": "#2E2A22",
        "card_bg": "#26221C",
        "inspector_bg": "#171512",
        "header_bg": "#14120F",
        "header_fg": "#D4AF37",
        "fg": "#F7F3E9",
        "fg_secondary": "#C5BCAE",
        "fg_muted": "#8A8070",
        "accent": "#D4AF37",
        "accent_hover": "#E5C158",
        "accent_deep": "#A38424",
        "btn_bg": "#D4AF37",
        "btn_fg": "#0F0E0C",
        "tree_bg": "#171512",
        "tree_fg": "#F7F3E9",
        "tree_select": "#A38424",
        "console_bg": "#0A0907",
        "console_fg": "#D4AF37",
        "badge_accept": "#35D07F",
        "badge_review": "#FFB547",
        "badge_unresolved": "#FF5C6C",
        "badge_manual": "#9B8CFF",
    },
    "graphite": {
        "name": "Enterprise Graphite",
        "bg": "#121417",
        "bg_secondary": "#1A1D21",
        "sidebar_bg": "#16191D",
        "sidebar_fg": "#9EA5B0",
        "panel_bg": "#202429",
        "glass_bg": "#272C33",
        "glass_border": "#373E47",
        "elevated_bg": "#2E343D",
        "card_bg": "#272C33",
        "inspector_bg": "#1A1D21",
        "header_bg": "#16191D",
        "header_fg": "#38BDF8",
        "fg": "#F1F5F9",
        "fg_secondary": "#94A3B8",
        "fg_muted": "#64748B",
        "accent": "#0284C7",
        "accent_hover": "#38BDF8",
        "accent_deep": "#0369A1",
        "btn_bg": "#0284C7",
        "btn_fg": "#FFFFFF",
        "tree_bg": "#1A1D21",
        "tree_fg": "#F1F5F9",
        "tree_select": "#0369A1",
        "console_bg": "#0B0C0E",
        "console_fg": "#56E39F",
        "badge_accept": "#35D07F",
        "badge_review": "#FFB547",
        "badge_unresolved": "#FF5C6C",
        "badge_manual": "#9B8CFF",
    },
    "light": {
        "name": "Light Classic",
        "bg": "#F8FAFC",
        "bg_secondary": "#EDF2F7",
        "sidebar_bg": "#E2E8F0",
        "sidebar_fg": "#334155",
        "panel_bg": "#FFFFFF",
        "glass_bg": "#FFFFFF",
        "glass_border": "#CBD5E1",
        "elevated_bg": "#F1F5F9",
        "card_bg": "#FFFFFF",
        "inspector_bg": "#FFFFFF",
        "header_bg": "#E2E8F0",
        "header_fg": "#0F172A",
        "fg": "#1E293B",
        "fg_secondary": "#475569",
        "fg_muted": "#64748B",
        "accent": "#2563EB",
        "accent_hover": "#3B82F6",
        "accent_deep": "#1D4ED8",
        "btn_bg": "#2563EB",
        "btn_fg": "#FFFFFF",
        "tree_bg": "#FFFFFF",
        "tree_fg": "#1E293B",
        "tree_select": "#2563EB",
        "console_bg": "#0F172A",
        "console_fg": "#22C55E",
        "badge_accept": "#16A34A",
        "badge_review": "#CA8A04",
        "badge_unresolved": "#DC2626",
        "badge_manual": "#2563EB",
    },
}


# ---------------------------------------------------------------------------
# Logging Setup & Syntax-Highlighted Terminal Console Handler
# ---------------------------------------------------------------------------

class TextConsoleHandler(logging.Handler):
    """Logging handler that streams syntax-highlighted output to Tkinter Text console widget."""

    def __init__(self, text_widget: tk.Text):
        super().__init__()
        self.text_widget = text_widget

    def emit(self, record: logging.LogRecord) -> None:
        msg = self.format(record)
        level_name = record.levelname

        def append():
            try:
                self.text_widget.configure(state=tk.NORMAL)
                
                # Cap log size to max 300 lines for fast UI rendering
                try:
                    num_lines = int(self.text_widget.index("end-1c").split(".")[0])
                    if num_lines > 300:
                        self.text_widget.delete("1.0", f"{num_lines - 250}.0")
                except Exception:
                    pass

                # Tag mapping
                tag = "INFO"
                if level_name == "ERROR" or "FAIL" in msg:
                    tag = "ERROR"
                elif level_name == "WARNING" or "WARN" in msg or "⚠️" in msg:
                    tag = "WARNING"
                elif "SUCCESS" in msg or "✓" in msg or "✅" in msg or "complete" in msg.lower():
                    tag = "SUCCESS"
                elif "RESEARCH" in msg or "🌐" in msg:
                    tag = "RESEARCH"

                self.text_widget.insert(tk.END, msg + "\n", tag)
                self.text_widget.see(tk.END)
                self.text_widget.configure(state=tk.DISABLED)
            except Exception:
                pass

        try:
            self.text_widget.after(0, append)
        except Exception:
            pass


def setup_app_logging(base_dir: Path) -> logging.Logger:
    """Setup application log file in logs/ directory."""
    log_dir = base_dir / "logs"
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / "stadium_mapper.log"

    logger = logging.getLogger("stadium_mapper")
    logger.setLevel(logging.DEBUG)

    if not logger.handlers:
        fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s", "%Y-%m-%d %H:%M:%S")

        # File handler
        fh = logging.FileHandler(str(log_file), encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(fmt)
        logger.addHandler(fh)

        # Console handler
        ch = logging.StreamHandler(sys.stdout)
        ch.setLevel(logging.INFO)
        ch.setFormatter(fmt)
        logger.addHandler(ch)

    return logger


# ---------------------------------------------------------------------------
# Frameless Animated Modern Splash Screen
# ---------------------------------------------------------------------------

class SplashScreen:
    """Frameless modern splash screen with subtle Canvas node visual & non-blocking progress sequence."""

    def __init__(self, root: tk.Tk, logo_path: str, title: str = "PES STADIUM MAPPER", version: str = APP_VERSION):
        self.root = root
        self.splash = tk.Toplevel(root)
        self.splash.overrideredirect(True)
        self.splash.configure(bg="#070B12")

        # Center splash window (520 x 340)
        width, height = 520, 340
        sw = self.splash.winfo_screenwidth()
        sh = self.splash.winfo_screenheight()
        x = (sw - width) // 2
        y = (sh - height) // 2
        self.splash.geometry(f"{width}x{height}+{x}+{y}")

        # Outer border frame
        box = tk.Frame(self.splash, bg="#121C2A", bd=1, relief=tk.SOLID)
        box.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)

        # Canvas Glow / Node Art
        self.canvas = tk.Canvas(box, bg="#070B12", highlightthickness=0, height=110)
        self.canvas.pack(fill=tk.X, pady=(12, 0))

        # Draw abstract stadium node glow on canvas
        cw = width - 4
        self.canvas.create_oval(cw // 2 - 80, 10, cw // 2 + 80, 100, fill="#0F1B2E", outline="#19A7FF", width=1)
        self.canvas.create_oval(cw // 2 - 45, 30, cw // 2 + 45, 80, fill="#12233D", outline="#42B8FF", width=1)
        self.canvas.create_line(cw // 2 - 70, 55, cw // 2 + 70, 55, fill="#19A7FF", width=1, dash=(4, 4))
        self.canvas.create_text(cw // 2, 55, text="⚽", font=("Segoe UI Emoji", 20), fill="#19A7FF")

        # Check logo image fallback
        splash_img_path = logo_path
        p_splash = Path(logo_path).parent / "splash.png" if logo_path else None
        if p_splash and p_splash.exists():
            splash_img_path = str(p_splash)

        if splash_img_path and Path(splash_img_path).exists():
            try:
                img = Image.open(splash_img_path)
                img.thumbnail((72, 72), Image.Resampling.LANCZOS)
                self.photo = ImageTk.PhotoImage(img)
                self.canvas.create_image(cw // 2, 55, image=self.photo)
            except Exception:
                pass

        # Title & Subtitle
        tk.Label(box, text=title, font=("Segoe UI", 16, "bold"), fg="#19A7FF", bg="#121C2A").pack(pady=(4, 0))
        tk.Label(box, text="INTELLIGENT STADIUM RESEARCH ENGINE", font=("Segoe UI", 8, "bold"), fg="#94A3B8", bg="#121C2A").pack()
        tk.Label(box, text=version, font=("Segoe UI", 9, "bold"), fg="#35D07F", bg="#121C2A").pack(pady=(2, 8))

        # Status text
        self.lbl_status = tk.Label(box, text=f"Initializing {APP_VERSION}...", font=("Segoe UI", 9), fg="#64748B", bg="#121C2A")
        self.lbl_status.pack(pady=(0, 6))

        # Modern Custom Progress Bar Track
        self.progress_frame = tk.Frame(box, bg="#070B12", height=6)
        self.progress_frame.pack(fill=tk.X, padx=50, pady=(0, 16))
        self.progress_frame.pack_propagate(False)

        self.progress_fill = tk.Frame(self.progress_frame, bg="#19A7FF", height=6, width=0)
        self.progress_fill.pack(side=tk.LEFT, fill=tk.Y)

    def update_progress(self, val: float, msg: str):
        target_w = int((val / 100.0) * 416)
        self.progress_fill.configure(width=target_w)
        self.lbl_status.configure(text=msg)
        self.splash.update()

    def close(self):
        self.splash.destroy()


# ---------------------------------------------------------------------------
# Auditable Persistent Research Cache
# ---------------------------------------------------------------------------

class PersistentResearchCache:
    """Auditable research cache stored in data/research_cache.json."""

    def __init__(self, base_dir: Path, logger: logging.Logger | None = None):
        self.data_dir = base_dir / "data"
        self.data_dir.mkdir(exist_ok=True)
        self.cache_path = self.data_dir / "research_cache.json"
        self.logger = logger or logging.getLogger("stadium_mapper.cache")
        self.cache: dict[str, dict[str, Any]] = {}
        self.load()

    def load(self) -> None:
        """Load cache from disk."""
        if self.cache_path.exists():
            try:
                with open(self.cache_path, "r", encoding="utf-8") as f:
                    self.cache = json.load(f)
                self.logger.info(f"Loaded {len(self.cache)} entries from research cache")
            except Exception as e:
                self.logger.warning(f"Error loading cache: {e}")
                self.cache = {}

    def save(self) -> None:
        """Save cache to disk."""
        try:
            with open(self.cache_path, "w", encoding="utf-8") as f:
                json.dump(self.cache, f, indent=2, ensure_ascii=False)
        except Exception as e:
            self.logger.error(f"Error saving cache: {e}")

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

    def put_manual_multi(
        self,
        stadium_name: str,
        rows: list[MappedRow]
    ) -> None:
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
            "search_date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        self.cache[key] = data
        self.save()

    def put_manual(
        self,
        stadium_name: str,
        team_id: int,
        stadium_id: str,
        stadium_name_out: str,
        stadium_path: str,
        club_name: str = ""
    ) -> None:
        """Store manual 4-column override persistently in research cache."""
        row = MappedRow(
            team_id=team_id,
            stadium_id=stadium_id,
            stadium_name=stadium_name_out or stadium_name,
            stadium_path=stadium_path or stadium_name,
            confidence=1.0,
            status="MANUAL",
            enabled=True
        )
        self.put_manual_multi(stadium_name, [row])

    def clear(self) -> None:
        """Clear cache."""
        self.cache.clear()
        self.save()


# ---------------------------------------------------------------------------
# Core Application Controller
# ---------------------------------------------------------------------------

class StadiumMapperController:
    """Controller orchestrating scanner, parser, researcher, matcher, and generator."""

    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self.logger = setup_app_logging(base_dir)
        self.config_mgr = ConfigManager(base_dir, self.logger)
        self.config = self.config_mgr.config
        self.cache = PersistentResearchCache(base_dir, self.logger)

        self.pdf_parser = TeamPdfParser(logger=self.logger)
        self.matcher = TeamMatcher(self.pdf_parser, self.logger)
        self.validator = MappingValidator(self.logger)

        self.discovered_stadiums: list[DiscoveredStadium] = []
        self.research_results: dict[str, StadiumResearchResult] = {}
        self.manual_mappings: dict[str, list[MappedRow]] = {}  # stadium_name -> list of MappedRow
        self.skipped_stadiums: set[str] = set()  # stadiums user explicitly chose to skip
        self.mapped_rows: list[MappedRow] = []

        # Auto-load PDF on init if configured or available
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

    def scan_stadiums(self) -> list[DiscoveredStadium]:
        """Scan stadium server directory and restore cached resolved states."""
        server_dir = self.config.stadium_server_dir
        if not server_dir or not Path(server_dir).exists():
            self.logger.error("Stadium Server directory not set or path does not exist.")
            return []

        scanner = StadiumScanner(server_dir, self.logger)
        self.discovered_stadiums = scanner.scan()

        # Restore cached resolved states
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

        return self.discovered_stadiums

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

    def research_stadium(self, stadium: DiscoveredStadium, force_refresh: bool = False, custom_provider: str | None = None, custom_query: str | None = None) -> StadiumResearchResult:
        """Research a single stadium using cache or live web search."""
        search_query = custom_query or stadium.search_name

        if not force_refresh and not custom_query and self.config.enable_cache:
            cached = self.cache.get(stadium.display_name)
            if cached and cached.get("club_name"):
                res = StadiumResearchResult(
                    stadium_name=stadium.display_name,
                    club_name=cached.get("club_name"),
                    alternative_clubs=cached.get("alternative_clubs", []),
                    confidence=cached.get("confidence", 0.85),
                    reasoning=cached.get("reasoning", "Loaded from research cache"),
                    is_shared=cached.get("is_shared", False),
                )
                self.research_results[stadium.display_name] = res
                return res

        providers = self.build_search_provider(custom_provider)
        researcher = WebStadiumResearcher(providers=providers, logger=self.logger)

        res = researcher.identify_stadium_club(search_query)
        res.stadium_name = stadium.display_name

        team_id = None
        if res.club_name:
            team_id = self.matcher.resolve_team_id(res.club_name)

        self.cache.put(stadium.display_name, res, team_id)
        self.research_results[stadium.display_name] = res
        return res

    def set_manual_mappings(self, stadium_name: str, rows: list[MappedRow]) -> list[MappedRow]:
        """Set multi-team manual mapping rows for a stadium."""
        self.manual_mappings[stadium_name] = rows
        if stadium_name in self.skipped_stadiums:
            self.skipped_stadiums.remove(stadium_name)
        self.cache.put_manual_multi(stadium_name, rows)
        return rows

    def set_manual_mapping(
        self,
        stadium_name: str,
        team_id: int,
        stadium_id: str = "",
        stadium_name_out: str = "",
        stadium_path: str = "",
        club_name: str = ""
    ) -> MappedRow:
        """Manually override a single team stadium mapping."""
        s_obj = next((s for s in self.discovered_stadiums if s.display_name == stadium_name), None)
        sid = str(stadium_id) if stadium_id else (s_obj.primary_id() if s_obj else "000")
        sname = stadium_name_out or stadium_name
        spath = stadium_path or sname

        row = MappedRow(
            team_id=team_id,
            stadium_id=sid,
            stadium_name=sname,
            stadium_path=spath,
            confidence=1.0,
            status="MANUAL",
            enabled=True
        )
        self.set_manual_mappings(stadium_name, [row])
        return row

    def mark_skipped(self, stadium_name: str) -> None:
        """Mark a stadium to be skipped from map_teams.txt."""
        self.skipped_stadiums.add(stadium_name)
        if stadium_name in self.manual_mappings:
            del self.manual_mappings[stadium_name]

    def get_stadium_state(self, stadium_name: str) -> StadiumState:
        """
        Single authoritative source of truth for a stadium's mapping state.
        Derived directly from current mapped rows, research cache, matcher, and skip lists.
        """
        s_obj = next((s for s in self.discovered_stadiums if s.display_name == stadium_name), None)
        st_id = s_obj.primary_id() if s_obj else "000"
        thumb_path = s_obj.get_thumbnail_path() if s_obj else None

        # 1. Check explicitly skipped stadiums
        if stadium_name in self.skipped_stadiums:
            return StadiumState(
                stadium_name=stadium_name,
                stadium_id=st_id,
                status=StadiumStatus.SKIPPED,
                mapped_rows=[],
                confidence=0.0,
                identified_clubs="[SKIPPED]",
                pes_team_ids="N/A",
                reasoning="User explicitly chose to skip stadium from output.",
                is_manual=False,
                is_skipped=True,
                preview_path=thumb_path,
                last_updated=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            )

        # 2. Check in-memory manual mappings
        if stadium_name in self.manual_mappings and self.manual_mappings[stadium_name]:
            rows = self.manual_mappings[stadium_name]
            tids_str = ", ".join(str(r.team_id) for r in rows)
            clubs_str = " / ".join(self.pdf_parser.id_to_name.get(r.team_id, f"Team_{r.team_id}") for r in rows)
            return StadiumState(
                stadium_name=stadium_name,
                stadium_id=rows[0].stadium_id if rows else st_id,
                status=StadiumStatus.MANUAL,
                mapped_rows=rows,
                confidence=1.0,
                identified_clubs=clubs_str,
                pes_team_ids=tids_str,
                reasoning=f"4-Column Manual Override ({len(rows)} team line(s)).",
                is_manual=True,
                is_skipped=False,
                preview_path=thumb_path,
                last_updated=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            )

        # 3. Check persistent research cache for saved manual mappings
        cached_data = self.cache.get(stadium_name)
        if cached_data and cached_data.get("is_manual"):
            rows = []
            if "manual_rows" in cached_data:
                for rdata in cached_data["manual_rows"]:
                    rows.append(MappedRow(
                        team_id=rdata.get("team_id", 0),
                        stadium_id=rdata.get("stadium_id", st_id),
                        stadium_name=rdata.get("stadium_name", stadium_name),
                        stadium_path=rdata.get("stadium_path", stadium_name),
                        confidence=1.0,
                        status="MANUAL",
                        enabled=True
                    ))
            else:
                rows.append(MappedRow(
                    team_id=cached_data.get("team_id", 0),
                    stadium_id=cached_data.get("stadium_id", st_id),
                    stadium_name=cached_data.get("stadium_name", stadium_name),
                    stadium_path=cached_data.get("stadium_path", stadium_name),
                    confidence=1.0,
                    status="MANUAL",
                    enabled=True
                ))
            self.manual_mappings[stadium_name] = rows
            tids_str = ", ".join(str(r.team_id) for r in rows)
            clubs_str = " / ".join(self.pdf_parser.id_to_name.get(r.team_id, f"Team_{r.team_id}") for r in rows)
            return StadiumState(
                stadium_name=stadium_name,
                stadium_id=rows[0].stadium_id if rows else st_id,
                status=StadiumStatus.MANUAL,
                mapped_rows=rows,
                confidence=1.0,
                identified_clubs=clubs_str,
                pes_team_ids=tids_str,
                reasoning="Loaded 4-column manual mapping from research cache.",
                is_manual=True,
                is_skipped=False,
                preview_path=thumb_path,
                last_updated=cached_data.get("search_date", "")
            )

        # 4. Check web research results
        res = self.research_results.get(stadium_name)
        if res and res.club_name:
            team_tuples = self.matcher.resolve_multiple_team_ids(res.club_name)
            if team_tuples:
                status = StadiumStatus.RESOLVED if res.confidence >= self.config.review_threshold else StadiumStatus.REVIEW
                rows = [
                    MappedRow(
                        team_id=tid,
                        stadium_id=st_id,
                        stadium_name=stadium_name,
                        stadium_path=stadium_name,
                        confidence=res.confidence,
                        status=status.value,
                        enabled=True
                    )
                    for tid, tname in team_tuples
                ]
                tids_str = ", ".join(str(t[0]) for t in team_tuples)
                clubs_str = " / ".join(t[1] for t in team_tuples)
                return StadiumState(
                    stadium_name=stadium_name,
                    stadium_id=st_id,
                    status=status,
                    mapped_rows=rows,
                    confidence=res.confidence,
                    identified_clubs=clubs_str,
                    pes_team_ids=tids_str,
                    reasoning=res.reasoning or "Identified via web research.",
                    is_manual=False,
                    is_skipped=False,
                    preview_path=thumb_path,
                    last_updated=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                )

        # 5. Default: UNRESOLVED
        reason = res.reasoning if res else "Not researched yet or no matching PES team ID found."
        return StadiumState(
            stadium_name=stadium_name,
            stadium_id=st_id,
            status=StadiumStatus.UNRESOLVED,
            mapped_rows=[],
            confidence=res.confidence if res else 0.0,
            identified_clubs=res.club_name if res and res.club_name else "???",
            pes_team_ids="N/A",
            reasoning=reason,
            is_manual=False,
            is_skipped=False,
            preview_path=thumb_path,
            last_updated=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )

    def refresh_all_states(self) -> list[StadiumState]:
        """Evaluate authoritative states for all discovered stadiums and sync mapped_rows."""
        states = [self.get_stadium_state(s.display_name) for s in self.discovered_stadiums]
        self.mapped_rows = []
        for st in states:
            if not st.is_skipped and st.mapped_rows:
                for row in st.mapped_rows:
                    self.mapped_rows.append(row)
        return states

    def build_mappings(self) -> list[MappedRow]:
        """Build MappedRow list for all researched & manually mapped stadiums from authoritative states."""
        self.refresh_all_states()
        return self.mapped_rows

    def run_dry_run(self) -> DryRunReport:
        """Generate a dry run report."""
        self.build_mappings()
        generator = MapGenerator(self.config.stadium_server_dir, self.logger)
        return generator.generate_dry_run(self.mapped_rows, len(self.discovered_stadiums))

    def write_map_file(self) -> bool:
        """Write final map_teams.txt in 4-column format."""
        if not self.mapped_rows:
            self.build_mappings()

        generator = MapGenerator(self.config.stadium_server_dir, self.logger)
        return generator.write_map_file(self.mapped_rows, create_backup_first=True)


# ---------------------------------------------------------------------------
# Live Autocomplete Suggestion Widget
# ---------------------------------------------------------------------------

class TeamAutocompleteEntry(tk.Frame):
    """
    Tkinter entry widget equipped with live fuzzy and prefix autocomplete listbox
    that updates dynamically as the user types, querying TeamPdfParser.
    """
    def __init__(self, parent, pdf_parser: TeamPdfParser, on_select=None, bg="#121C2A", fg="#F1F5F9", **kwargs):
        super().__init__(parent, bg=bg)
        self.pdf_parser = pdf_parser
        self.on_select = on_select
        self.bg = bg
        self.fg = fg
        self._current_suggestions: list[tuple[int, str]] = []

        self.var = tk.StringVar()
        self.entry = ttk.Entry(self, textvariable=self.var, font=("Segoe UI", 10), width=35)
        self.entry.pack(fill=tk.X, expand=True)

        self.listbox_frame = tk.Frame(self, bg=bg, bd=1, relief=tk.SOLID)
        self.listbox = tk.Listbox(
            self.listbox_frame,
            bg="#0B111C",
            fg=fg,
            selectbackground="#19A7FF",
            selectforeground="#FFFFFF",
            font=("Segoe UI", 9),
            height=4,
            bd=0,
            highlightthickness=0,
        )
        self.listbox.pack(fill=tk.BOTH, expand=True)

        self.entry.bind("<KeyRelease>", self._on_key_release)
        self.entry.bind("<Down>", self._on_down)
        self.listbox.bind("<ButtonRelease-1>", self._on_click_select)
        self.listbox.bind("<Return>", self._on_click_select)
        self.listbox.bind("<Escape>", lambda e: self.hide_suggestions())

    def _on_key_release(self, event):
        if event.keysym in ("Up", "Down", "Return", "Escape", "Tab"):
            return
        q = self.var.get().strip()
        if not q:
            self.hide_suggestions()
            if self.on_select:
                self.on_select(None, None)
            return

        suggestions = self.pdf_parser.get_team_suggestions(q, limit=10)
        if suggestions:
            self._current_suggestions = suggestions
            self.listbox.delete(0, tk.END)
            for tid, tname in suggestions:
                self.listbox.insert(tk.END, f"  {tname} (ID: {tid})")
            self.listbox_frame.pack(fill=tk.X, expand=True, pady=(2, 0))
        else:
            self.hide_suggestions()
            if self.on_select:
                self.on_select(None, None)

    def _on_down(self, event):
        if self.listbox_frame.winfo_ismapped() and self.listbox.size() > 0:
            self.listbox.focus_set()
            self.listbox.selection_clear(0, tk.END)
            self.listbox.selection_set(0)

    def _on_click_select(self, event):
        sel = self.listbox.curselection()
        if sel and hasattr(self, "_current_suggestions"):
            idx = sel[0]
            tid, tname = self._current_suggestions[idx]
            self.var.set(tname)
            self.hide_suggestions()
            if self.on_select:
                self.on_select(tid, tname)
            self.entry.focus_set()

    def hide_suggestions(self):
        self.listbox_frame.pack_forget()

    def get(self) -> str:
        return self.var.get().strip()

    def set(self, val: str):
        self.var.set(val)


# ---------------------------------------------------------------------------
# "PES NIGHT COMMAND" Modern Workstation GUI Interface
# ---------------------------------------------------------------------------

class StadiumMapperGUI:
    """3-Pane Modern Football Analytics Workstation (Top Command Bar + Sidebar + Workspace + Inspector + Live Terminal)."""

    def __init__(self, controller: StadiumMapperController):
        self.ctrl = controller
        self.root = tk.Tk()
        self.root.title(f"PES 2021 Stadium Server Mapper — {APP_VERSION}")
        self.root.geometry("1380x900")
        self.root.minsize(1100, 720)

        # Hide main window during splash screen
        self.root.withdraw()

        # Native Audio Player & DDS Thumbnail Loader
        self.audio_player = WinAudioPlayer(logger=self.ctrl.logger)
        self.dds_loader = DdsThumbnailLoader()

        self.style = ttk.Style()
        self.style.theme_use("clam")

        # Auto detect server directory
        default_s_dir = self.ctrl.config.stadium_server_dir
        if not default_s_dir or not Path(default_s_dir).exists():
            parent = Path("..").resolve()
            if (parent / "map_teams.txt").exists() or any(p.is_dir() for p in parent.iterdir() if p.name not in ("pes_stadium_mapper", "settings_PSM", "__pycache__", ".git")):
                default_s_dir = str(parent)
            else:
                default_s_dir = str(Path(".").resolve())

        self.server_dir_var = tk.StringVar(value=default_s_dir)
        self.provider_var = tk.StringVar(value=self.ctrl.config.search_provider)
        self.status_var = tk.StringVar(value="● READY")
        self.progress_var = tk.DoubleVar(value=0.0)

        # Search & Filter variables
        self.search_var = tk.StringVar()
        self.status_filter_var = tk.StringVar(value="ALL")

        # Accessibility options
        self.reduce_transparency = tk.BooleanVar(value=False)
        self.reduce_motion = tk.BooleanVar(value=False)

        # KPI Counter Variables
        self.kpi_total_var = tk.StringVar(value="0")
        self.kpi_accept_var = tk.StringVar(value="0")
        self.kpi_review_var = tk.StringVar(value="0")
        self.kpi_unresolved_var = tk.StringVar(value="0")

        # Inspector Variables
        self.insp_folder_var = tk.StringVar(value="-")
        self.insp_id_var = tk.StringVar(value="-")
        self.insp_club_var = tk.StringVar(value="-")
        self.insp_tid_var = tk.StringVar(value="-")
        self.insp_conf_var = tk.StringVar(value="-")
        self.insp_status_var = tk.StringVar(value="-")
        self.insp_reason_var = tk.StringVar(value="Select a stadium to view identity analysis.")

        self.logo_img: Optional[ImageTk.PhotoImage] = None

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # Window Icon (Replaces default Tkinter feather icon with logo.png across main window and dialogs)
        logo_path = self.ctrl.config.custom_logo_path
        if logo_path and Path(logo_path).exists():
            try:
                icon_img = Image.open(logo_path)
                self.app_icon = ImageTk.PhotoImage(icon_img)
                self.root.iconphoto(True, self.app_icon)
            except Exception:
                pass

        # Global Keyboard Shortcuts
        self.root.bind("<Control-k>", lambda e: self._open_command_palette())
        self.root.bind("<Control-f>", lambda e: self.search_entry.focus_set() if hasattr(self, "search_entry") else None)
        self.root.bind("<F5>", lambda e: self._cmd_scan())
        self.root.bind("<Control-g>", lambda e: self._cmd_generate())

        # Show Splash Screen first
        self._run_splash_sequence()

        self._build_ui()

        # Stream logger messages to live search terminal console
        console_handler = TextConsoleHandler(self.console_text)
        console_handler.setFormatter(logging.Formatter("[%(asctime)s] > %(message)s", datefmt="%H:%M:%S"))
        self.ctrl.logger.addHandler(console_handler)

        # Audio start
        if self.ctrl.config.play_music_on_start and self.ctrl.config.custom_music_path:
            self.audio_player.play(
                music_path=self.ctrl.config.custom_music_path,
                volume=self.ctrl.config.music_volume,
            )

        # Apply active theme
        active_theme_key = self.ctrl.config.theme if self.ctrl.config.theme in THEMES else "pes_night"
        self._apply_theme(active_theme_key)

        # Log startup info to live terminal console
        self.ctrl.logger.info(f"PES Stadium Mapper {APP_VERSION} Workstation Active.")
        self.ctrl.logger.info(f"Settings Package Directory: {self.ctrl.base_dir}")
        self.ctrl.logger.info(f"Stadium Server Root: {self.server_dir_var.get()}")
        self.ctrl.logger.info(f"Team ID PDF Database: {self.ctrl.config.team_pdf_path}")
        self.ctrl.logger.info(f"Loaded {len(self.ctrl.pdf_parser.id_to_name)} teams from PDF.")

        # Auto-scan stadiums on launch
        self.root.after(300, self._cmd_scan)

    def _run_splash_sequence(self) -> None:
        """Run smooth non-blocking splash screen before deiconifying main window."""
        splash = SplashScreen(self.root, self.ctrl.config.custom_logo_path)

        steps = [
            (15, f"Initializing {APP_VERSION}..."),
            (40, "Parsing Team-ID Database..."),
            (70, "Preparing Web Research Provider Engine..."),
            (95, "Building PES Night Command Dashboard..."),
        ]

        for val, msg in steps:
            splash.update_progress(val, msg)
            time.sleep(0.30)

        splash.close()
        self.root.deiconify()

    def _apply_theme(self, theme_key: str) -> None:
        """Apply color theme design tokens across all Tkinter and TTK widgets."""
        t = THEMES.get(theme_key, THEMES["pes_night"])
        self.ctrl.config_mgr.update(theme=theme_key)

        bg = t["bg"]
        bg_sec = t["bg_secondary"]
        fg = t["fg"]
        fg_sec = t["fg_secondary"]
        sidebar_bg = t["sidebar_bg"]
        sidebar_fg = t["sidebar_fg"]
        panel_bg = t["panel_bg"]
        card_bg = t["card_bg"] if not self.reduce_transparency.get() else panel_bg
        header_bg = t["header_bg"]
        header_fg = t["header_fg"]
        entry_bg = t.get("entry_bg", card_bg)
        entry_fg = t.get("entry_fg", fg)

        self.root.configure(bg=bg)

        # Style TTK widgets for high contrast across dark and light themes
        self.style.configure(".", background=bg, foreground=fg)
        self.style.configure("TFrame", background=bg)
        self.style.configure("Card.TFrame", background=card_bg, relief=tk.FLAT)
        self.style.configure("TLabelframe", background=bg, foreground=fg)
        self.style.configure("TLabelframe.Label", background=bg, foreground=fg, font=("Segoe UI", 9, "bold"))
        self.style.configure("TLabel", background=bg, foreground=fg)
        self.style.configure("TRadiobutton", background=bg_sec, foreground=fg, font=("Segoe UI", 9))
        self.style.map("TRadiobutton", background=[("active", bg_sec)], foreground=[("active", t["accent"])])
        self.style.configure("TCheckbutton", background=bg, foreground=fg, font=("Segoe UI", 9))
        
        self.style.configure("TEntry", fieldbackground=entry_bg, foreground=entry_fg, insertcolor=fg)
        self.style.configure("TCombobox", fieldbackground=entry_bg, foreground=entry_fg)
        self.style.map("TCombobox", fieldbackground=[("readonly", entry_bg)], foreground=[("readonly", entry_fg)])

        self.style.configure("TButton", background=t["btn_bg"], foreground=t["btn_fg"], font=("Segoe UI", 9, "bold"))
        self.style.map("TButton", background=[("active", t["accent_hover"])])

        if hasattr(self, "main_box"):
            self.main_box.configure(bg=bg)

        if hasattr(self, "top_bar"):
            self.top_bar.configure(bg=header_bg)

        if hasattr(self, "sidebar_frame"):
            self.sidebar_frame.configure(bg=sidebar_bg)

        if hasattr(self, "inspector_frame"):
            self.inspector_frame.configure(bg=t["inspector_bg"])

        # Treeview styling
        self.style.configure("Treeview", background=t["tree_bg"], foreground=t["tree_fg"], fieldbackground=t["tree_bg"], rowheight=28, font=("Segoe UI", 9))
        self.style.configure("Treeview.Heading", background=header_bg, foreground=header_fg, font=("Segoe UI", 9, "bold"))
        self.style.map("Treeview", background=[("selected", t["tree_select"])], foreground=[("selected", "#FFFFFF")])

        if hasattr(self, "console_text"):
            self.console_text.configure(bg=t["console_bg"], fg=t["console_fg"], insertbackground=t["console_fg"])
            self.console_text.tag_configure("INFO", foreground=t.get("console_cyan", "#56C7FF"))
            self.console_text.tag_configure("SUCCESS", foreground=t.get("badge_accept", "#35D07F"))
            self.console_text.tag_configure("WARNING", foreground=t.get("badge_review", "#FFB547"))
            self.console_text.tag_configure("ERROR", foreground=t.get("badge_unresolved", "#FF5C6C"))
            self.console_text.tag_configure("RESEARCH", foreground=t.get("badge_manual", "#9B8CFF"))

        # Tag colors in treeview
        if hasattr(self, "tree"):
            self.tree.tag_configure("ACCEPT", foreground=t["badge_accept"])
            self.tree.tag_configure("REVIEW", foreground=t["badge_review"])
            self.tree.tag_configure("UNRESOLVED", foreground=t["badge_unresolved"])
            self.tree.tag_configure("MANUAL", foreground=t["badge_manual"])

        # Dynamically recolor built subtrees
        if hasattr(self, "center_frame"):
            self.center_frame.configure(bg=bg)
        if hasattr(self, "kpi_bar"):
            self.kpi_bar.configure(bg=bg)
            for card in self.kpi_bar.winfo_children():
                try:
                    card.configure(bg=card_bg)
                    for cw in card.winfo_children():
                        try:
                            cw.configure(bg=card_bg)
                            if cw.winfo_class() == "Label" and str(cw.cget("fg")) not in ("#19A7FF", "#35D07F", "#FFB547", "#FF5C6C"):
                                cw.configure(fg=fg)
                        except Exception:
                            pass
                except Exception:
                    pass
        if hasattr(self, "filter_bar"):
            self.filter_bar.configure(bg=bg_sec)
            for w in self.filter_bar.winfo_children():
                try:
                    if w.winfo_class() == "Label":
                        w.configure(bg=bg_sec, fg=fg_sec)
                except Exception:
                    pass

    def _build_ui(self) -> None:
        """Construct responsive 3-pane workstation UI."""
        # Main Container
        main_box = tk.Frame(self.root, bg="#070B12")
        main_box.pack(fill=tk.BOTH, expand=True)

        # ===================================================================
        # TOP COMMAND BAR (Height 48px)
        # ===================================================================
        self.top_bar = tk.Frame(main_box, bg="#0B111C", height=48, padx=16)
        self.top_bar.pack(side=tk.TOP, fill=tk.X)
        self.top_bar.pack_propagate(False)

        # Brand / Title Left
        brand_f = tk.Frame(self.top_bar, bg="#0B111C")
        brand_f.pack(side=tk.LEFT)

        tk.Label(brand_f, text="⚽ PES STADIUM MAPPER", font=("Segoe UI", 12, "bold"), fg="#19A7FF", bg="#0B111C").pack(side=tk.LEFT, padx=(0, 8))
        tk.Label(brand_f, text=APP_VERSION, font=("Segoe UI", 8, "bold"), fg="#35D07F", bg="#162232", padx=6, pady=2).pack(side=tk.LEFT)

        # Status Center Indicator
        self.lbl_op_status = tk.Label(self.top_bar, textvariable=self.status_var, font=("Segoe UI", 9, "bold"), fg="#19A7FF", bg="#0B111C")
        self.lbl_op_status.pack(side=tk.LEFT, expand=True)

        # Controls Right
        top_ctrl = tk.Frame(self.top_bar, bg="#0B111C")
        top_ctrl.pack(side=tk.RIGHT)

        tk.Label(top_ctrl, text="Theme:", font=("Segoe UI", 8, "bold"), fg="#94A3B8", bg="#0B111C").pack(side=tk.LEFT, padx=(0, 4))
        theme_names = {k: v["name"] for k, v in THEMES.items()}
        inv_theme_names = {v["name"]: k for k, v in THEMES.items()}

        combo_theme_top = ttk.Combobox(top_ctrl, values=list(theme_names.values()), state="readonly", width=22)
        combo_theme_top.set(theme_names.get(self.ctrl.config.theme, "PES Night Command (Default)"))
        combo_theme_top.pack(side=tk.LEFT, padx=(0, 12))
        combo_theme_top.bind("<<ComboboxSelected>>", lambda e: self._apply_theme(inv_theme_names.get(combo_theme_top.get(), "pes_night")))

        self.btn_audio = tk.Button(
            top_ctrl,
            text="🎵 Music",
            command=self._toggle_audio,
            bg="#162232",
            fg="#F1F5F9",
            font=("Segoe UI", 8, "bold"),
            relief=tk.FLAT,
            padx=8,
            pady=3,
        )
        self.btn_audio.pack(side=tk.LEFT, padx=4)

        tk.Button(
            top_ctrl,
            text="⚙️ Settings",
            command=self._open_customization_dialog,
            bg="#162232",
            fg="#F1F5F9",
            font=("Segoe UI", 8, "bold"),
            relief=tk.FLAT,
            padx=8,
            pady=3,
        ).pack(side=tk.LEFT, padx=4)

        tk.Button(
            top_ctrl,
            text="💬 Contact Admin",
            command=self._open_contact_admin_dialog,
            bg="#162232",
            fg="#F1F5F9",
            font=("Segoe UI", 8, "bold"),
            relief=tk.FLAT,
            padx=8,
            pady=3,
        ).pack(side=tk.LEFT, padx=4)

        # Middle Workspace Container
        body_box = tk.Frame(main_box, bg="#070B12")
        body_box.pack(fill=tk.BOTH, expand=True)

        # ===================================================================
        # PANE 1: LEFT NAVIGATION RAIL
        # ===================================================================
        self.sidebar_frame = tk.Frame(body_box, bg="#09101A", width=240, padx=12, pady=16)
        self.sidebar_frame.pack(side=tk.LEFT, fill=tk.Y)
        self.sidebar_frame.pack_propagate(False)

        # Navigation Header
        tk.Label(self.sidebar_frame, text="ENGINE NAVIGATION", font=("Segoe UI", 9, "bold"), fg="#64748B", bg="#09101A").pack(anchor=tk.W, pady=(0, 8))

        def make_side_btn(txt: str, cmd: Any, bg_c: str = "#121C2A"):
            b = tk.Button(
                self.sidebar_frame,
                text=txt,
                command=cmd,
                bg=bg_c,
                fg="#F1F5F9",
                font=("Segoe UI", 9, "bold"),
                relief=tk.FLAT,
                anchor="w",
                padx=12,
                pady=7,
                activebackground="#19A7FF",
                activeforeground="#FFFFFF",
            )
            b.pack(fill=tk.X, pady=3)
            return b

        make_side_btn("📊 Scan Stadiums", self._cmd_scan, "#19A7FF")
        make_side_btn("🌐 Live Web Research", self._cmd_research)
        self.btn_unresolved = make_side_btn("⚡ Unresolved Resolver", self._open_unresolved_resolver_dialog, "#FF5C6C")
        make_side_btn("🏟️ Stadium Server Manager", self._open_stadium_server_manager_dialog, "#162232")
        make_side_btn("💾 Write map_teams.txt", self._cmd_generate, "#35D07F")
        make_side_btn("📊 Dry Run Report", self._cmd_dry_run)
        make_side_btn("💬 Contact Admin", self._open_contact_admin_dialog, "#162232")
        make_side_btn("⌨️ Command Palette", self._open_command_palette, "#162232")

        # Search Provider Selector Section
        tk.Label(self.sidebar_frame, text="RESEARCH PROVIDER", font=("Segoe UI", 9, "bold"), fg="#64748B", bg="#09101A").pack(anchor=tk.W, pady=(16, 6))

        for prov in ["duckduckgo", "wikipedia", "google", "bing"]:
            r = ttk.Radiobutton(
                self.sidebar_frame,
                text=prov.capitalize(),
                value=prov,
                variable=self.provider_var,
                command=self._on_provider_change,
            )
            r.pack(anchor=tk.W, pady=2, padx=6)

        # Compact Path Display Box
        path_box = tk.Frame(self.sidebar_frame, bg="#121C2A", pady=8, padx=8)
        path_box.pack(side=tk.BOTTOM, fill=tk.X)

        tk.Label(path_box, text="STADIUM SERVER ROOT", font=("Segoe UI", 7, "bold"), fg="#64748B", bg="#121C2A").pack(anchor=tk.W)
        lbl_path = tk.Label(path_box, textvariable=self.server_dir_var, font=("Segoe UI", 8), fg="#94A3B8", bg="#121C2A", wraplength=200, justify=tk.LEFT)
        lbl_path.pack(anchor=tk.W, pady=(2, 4))

        tk.Button(
            path_box,
            text="Change Path",
            command=self._browse_server_dir,
            bg="#162232",
            fg="#F1F5F9",
            font=("Segoe UI", 8),
            relief=tk.FLAT,
            pady=2,
        ).pack(fill=tk.X)

        # ===================================================================
        # PANE 2: CENTER WORKSPACE
        # ===================================================================
        center_frame = tk.Frame(body_box, bg="#070B12", padx=12, pady=12)
        center_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # 4 Glass KPI Cards Bar
        kpi_bar = tk.Frame(center_frame, bg="#070B12")
        kpi_bar.pack(fill=tk.X, pady=(0, 12))

        def make_kpi_card(parent: tk.Frame, label: str, var: tk.StringVar, color: str, subtext: str) -> tk.Frame:
            card = tk.Frame(parent, bg="#121C2A", bd=1, relief=tk.SOLID, padx=12, pady=10)
            card.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=4)

            tk.Label(card, text=label, font=("Segoe UI", 8, "bold"), fg="#64748B", bg="#121C2A").pack(anchor=tk.W)
            tk.Label(card, textvariable=var, font=("Segoe UI", 22, "bold"), fg=color, bg="#121C2A").pack(anchor=tk.W)
            tk.Label(card, text=subtext, font=("Segoe UI", 7), fg="#94A3B8", bg="#121C2A").pack(anchor=tk.W)
            return card

        make_kpi_card(kpi_bar, "TOTAL STADIUMS", self.kpi_total_var, "#19A7FF", "Discovered in Directory")
        make_kpi_card(kpi_bar, "HIGH CONFIDENCE", self.kpi_accept_var, "#35D07F", "Auto-Accepted Mappings")
        make_kpi_card(kpi_bar, "NEEDS REVIEW", self.kpi_review_var, "#FFB547", "Requires User Verification")
        make_kpi_card(kpi_bar, "UNRESOLVED", self.kpi_unresolved_var, "#FF5C6C", "Missing Team Match")

        # Command & Search / Filter Bar
        filter_bar = tk.Frame(center_frame, bg="#0B111C", padx=10, pady=8)
        filter_bar.pack(fill=tk.X, pady=(0, 8))

        tk.Label(filter_bar, text="⌕ Filter:", font=("Segoe UI", 9, "bold"), fg="#94A3B8", bg="#0B111C").pack(side=tk.LEFT, padx=(0, 6))
        self.search_entry = ttk.Entry(filter_bar, textvariable=self.search_var, width=28)
        self.search_entry.pack(side=tk.LEFT, padx=(0, 12))
        self.search_entry.bind("<KeyRelease>", lambda e: self._apply_filter())

        tk.Label(filter_bar, text="Status:", font=("Segoe UI", 9, "bold"), fg="#94A3B8", bg="#0B111C").pack(side=tk.LEFT, padx=(0, 6))
        for st in ["ALL", "ACCEPT", "REVIEW", "UNRESOLVED", "MANUAL"]:
            r = ttk.Radiobutton(
                filter_bar,
                text=st,
                value=st,
                variable=self.status_filter_var,
                command=self._apply_filter,
            )
            r.pack(side=tk.LEFT, padx=3)

        # Stadiums Data Grid (Treeview)
        table_frame = tk.Frame(center_frame, bg="#0B111C", bd=1, relief=tk.SOLID, padx=4, pady=4)
        table_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 8))

        cols = ("status", "stadium_name", "stadium_id", "web_club", "team_id", "confidence")
        self.tree = ttk.Treeview(table_frame, columns=cols, show="tree headings", height=12)

        self.tree.heading("#0", text="PREVIEW")
        self.tree.heading("status", text="STATUS")
        self.tree.heading("stadium_name", text="STADIUM FOLDER")
        self.tree.heading("stadium_id", text="STADIUM ID")
        self.tree.heading("web_club", text="IDENTIFIED CLUB")
        self.tree.heading("team_id", text="PES TEAM ID")
        self.tree.heading("confidence", text="CONFIDENCE METER")

        self.tree.column("#0", width=75, minwidth=60, anchor=tk.CENTER)
        self.tree.column("status", width=120, anchor=tk.CENTER)
        self.tree.column("stadium_name", width=200)
        self.tree.column("stadium_id", width=90, anchor=tk.CENTER)
        self.tree.column("web_club", width=220)
        self.tree.column("team_id", width=95, anchor=tk.CENTER)
        self.tree.column("confidence", width=140, anchor=tk.CENTER)

        scrollbar = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=scrollbar.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self.tree.bind("<Double-1>", self._on_double_click)

        # Live Terminal Search Console
        console_hdr = tk.Frame(center_frame, bg="#0B111C", padx=8, pady=4)
        console_hdr.pack(fill=tk.X)

        tk.Label(console_hdr, text="LIVE TERMINAL CONSOLE", font=("Segoe UI", 8, "bold"), fg="#19A7FF", bg="#0B111C").pack(side=tk.LEFT)
        tk.Label(console_hdr, text="● LIVE", font=("Segoe UI", 7, "bold"), fg="#35D07F", bg="#0B111C").pack(side=tk.LEFT, padx=(8, 0))

        tk.Button(
            console_hdr,
            text="Clear Log",
            command=self._clear_console,
            bg="#162232",
            fg="#94A3B8",
            font=("Segoe UI", 7),
            relief=tk.FLAT,
            padx=6,
        ).pack(side=tk.RIGHT)

        console_frame = tk.Frame(center_frame, bg="#05080D", bd=1, relief=tk.SOLID)
        console_frame.pack(fill=tk.X, pady=(0, 4))

        self.console_text = tk.Text(
            console_frame,
            height=6,
            wrap=tk.WORD,
            font=("Cascadia Mono", 9),
            bg="#05080D",
            fg="#56E39F",
            insertbackground="#56E39F",
            bd=0,
            padx=8,
            pady=6,
        )
        self.console_text.pack(fill=tk.BOTH, expand=True)
        self.console_text.insert("1.0", f"[{datetime.datetime.now().strftime('%H:%M:%S')}] > Terminal Console Initialized [{APP_VERSION}]. Ready for research stream...\n")
        self.console_text.configure(state=tk.DISABLED)

        # Progress Track
        self.prog_bar = ttk.Progressbar(center_frame, variable=self.progress_var, maximum=100)
        self.prog_bar.pack(fill=tk.X, pady=(2, 0))

        # ===================================================================
        # PANE 3: RIGHT PROPERTY INSPECTOR PANEL
        # ===================================================================
        self.inspector_frame = tk.Frame(body_box, bg="#0B111C", width=300, padx=12, pady=16)
        self.inspector_frame.pack(side=tk.RIGHT, fill=tk.Y)
        self.inspector_frame.pack_propagate(False)

        tk.Label(self.inspector_frame, text="RESEARCH INSPECTOR", font=("Segoe UI", 11, "bold"), fg="#19A7FF", bg="#0B111C").pack(anchor=tk.W, pady=(0, 10))

        # Enlarged DDS Stadium Thumbnail Box
        self.insp_thumb_frame = tk.Frame(self.inspector_frame, bg="#070B12", bd=1, relief=tk.SOLID, height=100)
        self.insp_thumb_frame.pack(fill=tk.X, pady=(0, 10))
        self.insp_thumb_frame.pack_propagate(False)

        self.insp_thumb_label = tk.Label(self.insp_thumb_frame, text="NO DDS PREVIEW", font=("Segoe UI", 8, "bold"), fg="#64748B", bg="#070B12")
        self.insp_thumb_label.pack(fill=tk.BOTH, expand=True)

        # Metadata Card
        meta_f = tk.Frame(self.inspector_frame, bg="#121C2A", bd=1, relief=tk.SOLID, padx=10, pady=10)
        meta_f.pack(fill=tk.X, pady=(0, 12))

        def add_prop_row(parent: tk.Frame, r_idx: int, prop_lbl: str, var: tk.StringVar):
            tk.Label(parent, text=prop_lbl, font=("Segoe UI", 8, "bold"), fg="#64748B", bg="#121C2A").grid(row=r_idx, column=0, sticky=tk.W, pady=3, padx=2)
            tk.Label(parent, textvariable=var, font=("Segoe UI", 9, "bold"), fg="#F1F5F9", bg="#121C2A", wraplength=160, justify=tk.LEFT).grid(row=r_idx, column=1, sticky=tk.W, pady=3, padx=2)

        add_prop_row(meta_f, 0, "Folder:", self.insp_folder_var)
        add_prop_row(meta_f, 1, "Stadium ID:", self.insp_id_var)
        add_prop_row(meta_f, 2, "Identified:", self.insp_club_var)
        add_prop_row(meta_f, 3, "Team ID:", self.insp_tid_var)
        add_prop_row(meta_f, 4, "Confidence:", self.insp_conf_var)
        add_prop_row(meta_f, 5, "Status:", self.insp_status_var)
        meta_f.columnconfigure(1, weight=1)

        # Research Reasoning & Evidence Box
        tk.Label(self.inspector_frame, text="ANALYSIS & EVIDENCE", font=("Segoe UI", 9, "bold"), fg="#64748B", bg="#0B111C").pack(anchor=tk.W, pady=(0, 4))
        
        reason_f = tk.Frame(self.inspector_frame, bg="#121C2A", bd=1, relief=tk.SOLID, padx=8, pady=8)
        reason_f.pack(fill=tk.X, pady=(0, 14))

        tk.Label(reason_f, textvariable=self.insp_reason_var, font=("Segoe UI", 8), fg="#94A3B8", bg="#121C2A", wraplength=260, justify=tk.LEFT).pack(anchor=tk.W)

        # Inspector Quick Actions
        tk.Label(self.inspector_frame, text="STADIUM ACTIONS", font=("Segoe UI", 9, "bold"), fg="#64748B", bg="#0B111C").pack(anchor=tk.W, pady=(0, 6))

        def make_insp_btn(txt: str, cmd: Any, bg_c: str = "#19A7FF"):
            b = tk.Button(
                self.inspector_frame,
                text=txt,
                command=cmd,
                bg=bg_c,
                fg="#FFFFFF",
                font=("Segoe UI", 9, "bold"),
                relief=tk.FLAT,
                pady=7,
                activebackground="#42B8FF",
                activeforeground="#FFFFFF",
            )
            b.pack(fill=tk.X, pady=3)
            return b

        make_insp_btn("✏️ Edit Manual Map", self._cmd_insp_edit, "#19A7FF")
        make_insp_btn("🌐 Re-verify Research", self._cmd_insp_research, "#162232")
        make_insp_btn("🚫 Skip Selected", self._cmd_insp_skip, "#FF5C6C")

    def _on_provider_change(self) -> None:
        """Handle search provider toggle."""
        prov = self.provider_var.get()
        self.ctrl.config_mgr.update(search_provider=prov)
        self.ctrl.logger.info(f"Active Search Provider set to: {prov.capitalize()}")

    def _toggle_audio(self) -> None:
        """Toggle background music play/pause."""
        if not self.audio_player.is_playing:
            if self.ctrl.config.custom_music_path:
                self.audio_player.play(self.ctrl.config.custom_music_path, volume=self.ctrl.config.music_volume)
                self.btn_audio.configure(text="🎵 Pause Music")
        else:
            self.audio_player.toggle_pause()
            if self.audio_player.is_paused:
                self.btn_audio.configure(text="▶ Play Music")
            else:
                self.btn_audio.configure(text="🎵 Pause Music")

    def _clear_console(self) -> None:
        """Clear the terminal console widget."""
        self.console_text.configure(state=tk.NORMAL)
        self.console_text.delete("1.0", tk.END)
        self.console_text.configure(state=tk.DISABLED)

    def _browse_server_dir(self) -> None:
        """Browse for Stadium Server root directory."""
        d = filedialog.askdirectory(title="Select PES 2021 Stadium Server Root Directory", initialdir=self.server_dir_var.get())
        if d:
            self.server_dir_var.set(d)
            self.ctrl.configure_paths(d)
            self._cmd_scan()

    def _cmd_scan(self) -> None:
        """Execute stadium directory scan."""
        self.status_var.set("● SCANNING DIRECTORY...")
        stadiums = self.ctrl.scan_stadiums()
        self._populate_tree(stadiums)
        self.ctrl.logger.info(f"Filesystem scan complete. Discovered {len(stadiums)} stadiums.")
        self.status_var.set("● READY")

    def _update_kpi_counts(self) -> None:
        """Update KPI stat counters."""
        total = len(self.ctrl.discovered_stadiums)
        accept = 0
        review = 0
        unresolved = 0

        for s in self.ctrl.discovered_stadiums:
            name = s.display_name
            if name in self.ctrl.manual_mappings:
                accept += 1
                continue
            if name in self.ctrl.skipped_stadiums:
                unresolved += 1
                continue

            res = self.ctrl.research_results.get(name)
            if not res or not res.club_name:
                unresolved += 1
            elif res.confidence >= 0.90:
                accept += 1
            else:
                review += 1

        self.kpi_total_var.set(str(total))
        self.kpi_accept_var.set(str(accept))
        self.kpi_review_var.set(str(review))
        self.kpi_unresolved_var.set(str(unresolved))

        if unresolved > 0:
            self.btn_unresolved.configure(bg="#FF5C6C", text=f"⚡ Resolver ({unresolved})")
        else:
            self.btn_unresolved.configure(bg="#35D07F", text="✅ All Resolved")

    def _apply_filter(self) -> None:
        """Debounced table filtering to maintain smooth UI responsiveness."""
        if hasattr(self, "_search_timer") and self._search_timer:
            try:
                self.root.after_cancel(self._search_timer)
            except Exception:
                pass
        self._search_timer = self.root.after(100, self._do_apply_filter)

    def _do_apply_filter(self) -> None:
        """Execute table view filter."""
        q = self.search_var.get().lower().strip()
        st_filter = self.status_filter_var.get()

        for item in self.tree.get_children():
            name = item
            s_obj = next((s for s in self.ctrl.discovered_stadiums if s.display_name == name), None)
            res = self.ctrl.research_results.get(name)
            club_str = res.club_name if res and res.club_name else ""

            # Check status tag
            tags = self.tree.item(item, "tags")
            status_tag = tags[0] if tags else ""

            match_status = (st_filter == "ALL" or status_tag == st_filter)
            match_search = (not q or q in name.lower() or q in club_str.lower() or (s_obj and q in s_obj.primary_id()))

            if match_status and match_search:
                self.tree.reattach(item, "", tk.END)
            else:
                self.tree.detach(item)

    def _populate_tree(self, stadiums: list[DiscoveredStadium]) -> None:
        """Populate treeview with discovered stadiums and live DDS thumbnails."""
        for item in self.tree.get_children():
            self.tree.delete(item)

        for s in stadiums:
            name = s.display_name
            thumb_path = s.get_thumbnail_path()
            photo = self.dds_loader.get_thumbnail(thumb_path, size=(52, 30))

            if name in self.ctrl.manual_mappings and self.ctrl.manual_mappings[name]:
                rows = self.ctrl.manual_mappings[name]
                tids_str = ", ".join(str(r.team_id) for r in rows)
                clubs_str = " / ".join(self.ctrl.pdf_parser.id_to_name.get(r.team_id, f"Team_{r.team_id}") for r in rows)
                meter = "100% ██████████"
                self.tree.insert("", tk.END, iid=name, image=photo, values=(
                    "✏️ MANUAL", rows[0].stadium_name, rows[0].stadium_id, clubs_str, tids_str, meter
                ), tags=("MANUAL",))
                continue

            if name in self.ctrl.skipped_stadiums:
                self.tree.insert("", tk.END, iid=name, image=photo, values=(
                    "● SKIPPED", name, s.primary_id(), "[SKIPPED]", "N/A", "0%"
                ), tags=("UNRESOLVED",))
                continue

            res = self.ctrl.research_results.get(name)
            cached_data = self.ctrl.cache.get(name)

            if res and res.club_name:
                team_tuples = self.ctrl.matcher.resolve_multiple_team_ids(res.club_name)
            else:
                team_tuples = []

            conf_val = res.confidence if res and res.club_name else (1.0 if cached_data and cached_data.get("is_manual") else 0.0)

            # Confidence meter representation
            bars = int(conf_val * 10)
            meter = f"{int(conf_val * 100)}% " + ("█" * bars) + ("░" * (10 - bars))

            if team_tuples:
                tids_str = ", ".join(str(t[0]) for t in team_tuples)
                clubs_str = " / ".join(t[1] for t in team_tuples)
            else:
                tids_str = "N/A"
                clubs_str = res.club_name if res and res.club_name else ("Custom Team" if cached_data and cached_data.get("is_manual") else "???")

            st_id = (cached_data.get("stadium_id") if cached_data else None) or s.primary_id()

            if res and res.confidence >= 0.90 and team_tuples:
                tag = "ACCEPT"
                status = "✅ ALREADY RESOLVED"
            elif res and res.club_name and team_tuples:
                tag = "REVIEW"
                status = "⚠️ REVIEW"
            elif cached_data and cached_data.get("is_manual"):
                tag = "MANUAL"
                status = "✏️ MANUAL"
            else:
                tag = "UNRESOLVED"
                status = "❓ UNRESOLVED"

            self.tree.insert("", tk.END, iid=name, image=photo, values=(
                status, name, st_id, clubs_str, tids_str, meter
            ), tags=(tag,))

        self._update_kpi_counts()

    def _cmd_research(self) -> None:
        """Execute live web research on all discovered stadiums."""
        if not self.ctrl.discovered_stadiums:
            self.ctrl.scan_stadiums()

        self.status_var.set("● RESEARCHING IDENTITY...")

        def worker():
            total = len(self.ctrl.discovered_stadiums)
            self.ctrl.logger.info(f"Starting live web research for {total} stadiums...")
            for i, stadium in enumerate(self.ctrl.discovered_stadiums, 1):
                self.progress_var.set((i / total) * 100)
                self.ctrl.logger.info(f"[{i}/{total}] Web Researching: '{stadium.display_name}'...")
                res = self.ctrl.research_stadium(stadium)
                self.root.after(0, lambda s=stadium, r=res: self._update_tree_row(s, r))

            self.ctrl.logger.info("Live web research complete!")
            self.progress_var.set(100.0)
            self.root.after(0, self._update_kpi_counts)
            self.root.after(0, lambda: self.status_var.set("● READY"))

        threading.Thread(target=worker, daemon=True).start()

    def _update_tree_row(self, stadium: DiscoveredStadium, res: StadiumResearchResult) -> None:
        """Update single tree row with research result."""
        name = stadium.display_name
        tid = self.ctrl.matcher.resolve_team_id(res.club_name) if res.club_name else None
        tid_str = str(tid) if tid is not None else "N/A"

        bars = int(res.confidence * 10)
        meter = f"{int(res.confidence * 100)}% " + ("█" * bars) + ("░" * (10 - bars))

        if res.confidence >= 0.90 and tid is not None:
            tag = "ACCEPT"
            status = "✅ ALREADY RESOLVED"
        elif res.club_name and tid is not None:
            tag = "REVIEW"
            status = "● REVIEW"
        else:
            tag = "UNRESOLVED"
            status = "● UNRESOLVED"

        try:
            self.tree.item(name, values=(
                status, name, stadium.primary_id(), res.club_name or "???", tid_str, meter
            ), tags=(tag,))
        except Exception:
            pass

    def _cmd_dry_run(self) -> None:
        """Generate and display dry run report."""
        if not self.ctrl.discovered_stadiums:
            self.ctrl.scan_stadiums()

        report = self.ctrl.run_dry_run()

        msg = (
            f"=== DRY RUN REPORT ===\n\n"
            f"Total Stadiums Discovered: {report.total_stadiums_found}\n"
            f"High Confidence (≥0.90): {report.high_confidence_count}\n"
            f"Review Needed (0.75-0.89): {report.review_count}\n"
            f"Unresolved / Skipped: {report.unresolved_count}\n"
            f"Proposed Entries for map_teams.txt: {len(report.proposed_rows)}\n\n"
            f"No files were modified."
        )
        messagebox.showinfo("Dry Run Report", msg)

    def _cmd_generate(self) -> None:
        """Generate map_teams.txt file."""
        self.status_var.set("● GENERATING MAP FILE...")
        if not self.ctrl.mapped_rows:
            self.ctrl.build_mappings()

        if not self.ctrl.mapped_rows:
            messagebox.showwarning("Warning", "No mapped entries available to write.")
            self.status_var.set("● READY")
            return

        if self.ctrl.write_map_file():
            messagebox.showinfo(
                "Success",
                f"map_teams.txt written with {len(self.ctrl.mapped_rows)} entries in 4-column format!\n\n"
                f"Format: TEAM_ID,STADIUM_ID,STADIUM_NAME,STADIUM_PATH\n"
                f"Location: {self.ctrl.config.stadium_server_dir}\\map_teams.txt\n"
                f"Backup Saved in: {self.ctrl.config.stadium_server_dir}\\settings_PSM\\backup_map"
            )
        self.status_var.set("● READY")

    def _on_tree_select(self, event) -> None:
        """Handle tree item selection to update inspector."""
        item_id = self.tree.focus()
        if not item_id:
            return

        # Update Inspector Panel
        self.insp_folder_var.set(item_id)
        s_obj = next((s for s in self.ctrl.discovered_stadiums if s.display_name == item_id), None)
        cached_data = self.ctrl.cache.get(item_id) if item_id else None

        # Update enlarged DDS thumbnail image in Inspector
        if s_obj:
            thumb_path = s_obj.get_thumbnail_path()
            photo_large = self.dds_loader.get_thumbnail(thumb_path, size=(160, 90))
            self.insp_thumb_label.configure(image=photo_large, text="")
            self.insp_thumb_label.image = photo_large
        else:
            placeholder = self.dds_loader.get_placeholder(size=(160, 90))
            self.insp_thumb_label.configure(image=placeholder, text="")
            self.insp_thumb_label.image = placeholder

        current_sid = (cached_data.get("stadium_id") if cached_data else None) or (s_obj.primary_id() if s_obj else "-")
        self.insp_id_var.set(current_sid)

        if item_id in self.ctrl.manual_mappings and self.ctrl.manual_mappings[item_id]:
            rows = self.ctrl.manual_mappings[item_id]
            r = rows[0]
            club_n = self.ctrl.pdf_parser.id_to_name.get(r.team_id, f"Team_{r.team_id}")
            self.insp_club_var.set(f"{r.stadium_name} ({club_n})")
            self.insp_tid_var.set(", ".join(str(rw.team_id) for rw in rows))
            self.insp_id_var.set(r.stadium_id)
            self.insp_conf_var.set("1.00 (Manual)")
            self.insp_status_var.set("● MANUAL OVERRIDE")
            self.insp_reason_var.set(f"4-Column Override: {len(rows)} mapping(s) defined.")
            return

        if item_id in self.ctrl.skipped_stadiums:
            self.insp_club_var.set("[SKIPPED]")
            self.insp_tid_var.set("N/A")
            self.insp_conf_var.set("0.00")
            self.insp_status_var.set("● SKIPPED")
            self.insp_reason_var.set("User chose to skip stadium from output.")
            return

        res = self.ctrl.research_results.get(item_id)
        if res:
            self.insp_club_var.set(res.club_name or "???")
            tid = (cached_data.get("team_id") if cached_data else None)
            if tid is None and res.club_name:
                tid = self.ctrl.matcher.resolve_team_id(res.club_name)
            self.insp_tid_var.set(str(tid) if tid is not None else "N/A")
            self.insp_conf_var.set(f"{res.confidence:.2f}")
            self.insp_reason_var.set(res.reasoning or "Identified via web research provider.")

            if res.confidence >= 0.90 and tid is not None:
                self.insp_status_var.set("● ACCEPT")
            elif res.club_name and tid is not None:
                self.insp_status_var.set("● REVIEW")
            else:
                self.insp_status_var.set("● UNRESOLVED")

    def _on_double_click(self, event) -> None:
        """Handle tree item double click to open 4-column editor."""
        item_id = self.tree.focus()
        if not item_id:
            return

        s_obj = next((s for s in self.ctrl.discovered_stadiums if s.display_name == item_id), None)
        if s_obj:
            self._open_4column_editor_dialog(target_stadium=s_obj)

    def _cmd_insp_edit(self) -> None:
        """Open 4-Column Manual Editor for selected stadium."""
        item_id = self.tree.focus()
        s_obj = next((s for s in self.ctrl.discovered_stadiums if s.display_name == item_id), None) if item_id else None
        self._open_4column_editor_dialog(target_stadium=s_obj)

    def _cmd_insp_research(self) -> None:
        item_id = self.tree.focus()
        s_obj = next((s for s in self.ctrl.discovered_stadiums if s.display_name == item_id), None) if item_id else None
        if s_obj:
            def worker():
                self.ctrl.logger.info(f"Re-verifying '{s_obj.display_name}'...")
                res = self.ctrl.research_stadium(s_obj, force_refresh=True)
                self.root.after(0, lambda: self._update_tree_row(s_obj, res))
                self.root.after(0, self._update_kpi_counts)

            threading.Thread(target=worker, daemon=True).start()

    def _cmd_insp_skip(self) -> None:
        item_id = self.tree.focus()
        if item_id:
            self.ctrl.mark_skipped(item_id)
            self._populate_tree(self.ctrl.discovered_stadiums)

    # ===================================================================
    # COMMAND PALETTE MODAL (Ctrl+K)
    # ===================================================================
    def _open_command_palette(self) -> None:
        """Open modern command launcher palette."""
        dlg = tk.Toplevel(self.root)
        dlg.title("Command Palette")
        dlg.geometry("540x360")
        dlg.configure(bg="#0B111C")
        dlg.resizable(False, False)
        dlg.grab_set()

        # Input
        tk.Label(dlg, text="COMMAND PALETTE (Ctrl+K)", font=("Segoe UI", 9, "bold"), fg="#19A7FF", bg="#0B111C").pack(anchor=tk.W, padx=16, pady=(12, 4))
        cmd_var = tk.StringVar()
        entry = ttk.Entry(dlg, textvariable=cmd_var, font=("Segoe UI", 11))
        entry.pack(fill=tk.X, padx=16, pady=(0, 8))
        entry.focus_set()

        # Command List Box
        list_box = tk.Listbox(dlg, bg="#121C2A", fg="#F1F5F9", selectbackground="#19A7FF", font=("Segoe UI", 10), bd=0)
        list_box.pack(fill=tk.BOTH, expand=True, padx=16, pady=(0, 12))

        commands = [
            ("Scan Stadium Server Directory", self._cmd_scan),
            ("Run Live Web Research on Stadiums", self._cmd_research),
            ("Open Unresolved Stadium Resolver", lambda: self._open_unresolved_resolver_dialog()),
            ("Generate map_teams.txt File", self._cmd_generate),
            ("Generate Dry Run Report", self._cmd_dry_run),
            ("Open Settings & Customization", self._open_customization_dialog),
            ("Contact Admin & Source Access", self._open_contact_admin_dialog),
            ("Clear Terminal Console Log", self._clear_console),
        ]

        for c_text, _ in commands:
            list_box.insert(tk.END, f"  ⚡  {c_text}")

        def execute_selected(e=None):
            idx = list_box.curselection()
            if idx:
                cmd_func = commands[idx[0]][1]
                dlg.destroy()
                cmd_func()

        list_box.bind("<Double-1>", execute_selected)
        dlg.bind("<Return>", execute_selected)
        dlg.bind("<Escape>", lambda e: dlg.destroy())

    def _open_contact_admin_dialog(self) -> None:
        """Open Contact Admin subform modal displaying admin details and source access note."""
        win = tk.Toplevel(self.root)
        win.title("Contact Admin — PES Stadium Mapper")
        win.geometry("520x320")
        win.resizable(False, False)
        win.configure(bg="#0B111C")

        if hasattr(self, "app_icon"):
            win.iconphoto(True, self.app_icon)

        win.transient(self.root)
        win.grab_set()

        # Center dialog
        win.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - 520) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - 320) // 2
        win.geometry(f"+{x}+{y}")

        # Top Banner
        hdr = tk.Frame(win, bg="#121C2A", height=60, padx=20)
        hdr.pack(fill=tk.X)
        hdr.pack_propagate(False)

        tk.Label(hdr, text="💬 CONTACT ADMIN", font=("Segoe UI", 12, "bold"), fg="#19A7FF", bg="#121C2A").pack(side=tk.LEFT, pady=16)

        # Body Container
        body = tk.Frame(win, bg="#0B111C", padx=24, pady=20)
        body.pack(fill=tk.BOTH, expand=True)

        # Main Notice Box
        box = tk.Frame(body, bg="#162232", bd=1, relief=tk.SOLID, padx=16, pady=16)
        box.pack(fill=tk.X, pady=(0, 16))

        tk.Label(
            box,
            text="🔒 Source code is private. Contact admin for access.",
            font=("Segoe UI", 10, "bold"),
            fg="#FF5C6C",
            bg="#162232",
            justify=tk.LEFT
        ).pack(anchor=tk.W, pady=(0, 8))

        tk.Label(
            box,
            text="For source code access, custom feature requests, bug reports, or technical support, please reach out to the project administrator via Reddit:",
            font=("Segoe UI", 9),
            fg="#94A3B8",
            bg="#162232",
            wraplength=440,
            justify=tk.LEFT
        ).pack(anchor=tk.W, pady=(0, 12))

        # Reddit Link Row
        link_frame = tk.Frame(box, bg="#0F172A", padx=10, pady=8)
        link_frame.pack(fill=tk.X)

        tk.Label(link_frame, text="Reddit User:", font=("Segoe UI", 9, "bold"), fg="#19A7FF", bg="#0F172A").pack(side=tk.LEFT, padx=(0, 8))

        reddit_url = "https://www.reddit.com/user/Available_Chipmunk27/"
        lbl_url = tk.Label(link_frame, text=reddit_url, font=("Segoe UI", 9, "underline"), fg="#35D07F", bg="#0F172A", cursor="hand2")
        lbl_url.pack(side=tk.LEFT)

        import webbrowser
        lbl_url.bind("<Button-1>", lambda e: webbrowser.open_new_tab(reddit_url))

        # Action Buttons
        btn_frame = tk.Frame(body, bg="#0B111C")
        btn_frame.pack(fill=tk.X)

        def copy_url():
            self.root.clipboard_clear()
            self.root.clipboard_append(reddit_url)
            messagebox.showinfo("Copied", "Reddit profile URL copied to clipboard!", parent=win)

        tk.Button(
            btn_frame,
            text="📋 Copy Link",
            command=copy_url,
            bg="#19A7FF",
            fg="#FFFFFF",
            font=("Segoe UI", 9, "bold"),
            relief=tk.FLAT,
            padx=14,
            pady=6
        ).pack(side=tk.LEFT, padx=(0, 8))

        tk.Button(
            btn_frame,
            text="🌐 Open in Browser",
            command=lambda: webbrowser.open_new_tab(reddit_url),
            bg="#35D07F",
            fg="#FFFFFF",
            font=("Segoe UI", 9, "bold"),
            relief=tk.FLAT,
            padx=14,
            pady=6
        ).pack(side=tk.LEFT)

        tk.Button(
            btn_frame,
            text="Close",
            command=win.destroy,
            bg="#334155",
            fg="#FFFFFF",
            font=("Segoe UI", 9, "bold"),
            relief=tk.FLAT,
            padx=14,
            pady=6
        ).pack(side=tk.RIGHT)

    # ===================================================================
    # FULL 4-COLUMN MANUAL STADIUM MAPPER EDITOR MODAL
    # ===================================================================
    def _open_4column_editor_dialog(self, target_stadium: DiscoveredStadium | None = None) -> None:
        """Modal dialog allowing direct manual editing of all 4 columns: TEAM_ID, STADIUM_ID, STADIUM_NAME, STADIUM_PATH with multi-team support and live autocomplete."""
        if not target_stadium:
            item_id = self.tree.focus()
            if item_id:
                target_stadium = next((s for s in self.ctrl.discovered_stadiums if s.display_name == item_id), None)

        if not target_stadium:
            messagebox.showwarning("Select Stadium", "Please select a stadium from the table first.")
            return

        dlg = tk.Toplevel(self.root)
        dlg.title(f"✏️ 4-Column Mapping Editor — {target_stadium.display_name}")
        dlg.geometry("700x640")
        dlg.configure(bg="#0B111C")
        dlg.resizable(True, True)
        dlg.grab_set()

        # Header
        hdr_f = tk.Frame(dlg, bg="#0B111C", padx=16, pady=12)
        hdr_f.pack(fill=tk.X)
        tk.Label(hdr_f, text="✏️ FULL 4-COLUMN MANUAL MAPPER", font=("Segoe UI", 12, "bold"), fg="#19A7FF", bg="#0B111C").pack(anchor=tk.W)
        tk.Label(hdr_f, text=f"Customize exact TEAM_ID, STADIUM_ID, STADIUM_NAME, and STADIUM_PATH for '{target_stadium.display_name}'. Supports multiple teams.", font=("Segoe UI", 8), fg="#94A3B8", bg="#0B111C").pack(anchor=tk.W)

        # Existing mapped rows or default
        existing_rows: list[MappedRow] = []
        if target_stadium.display_name in self.ctrl.manual_mappings:
            existing_rows = list(self.ctrl.manual_mappings[target_stadium.display_name])
        else:
            cached_data = self.ctrl.cache.get(target_stadium.display_name)
            if cached_data and cached_data.get("is_manual") and "manual_rows" in cached_data:
                for rdata in cached_data["manual_rows"]:
                    existing_rows.append(MappedRow(
                        team_id=rdata.get("team_id", 0),
                        stadium_id=rdata.get("stadium_id", target_stadium.primary_id()),
                        stadium_name=rdata.get("stadium_name", target_stadium.display_name),
                        stadium_path=rdata.get("stadium_path", target_stadium.display_name),
                        confidence=1.0,
                        status="MANUAL",
                        enabled=True
                    ))
            elif target_stadium.display_name in self.ctrl.research_results:
                res = self.ctrl.research_results[target_stadium.display_name]
                if res.club_name:
                    team_tuples = self.ctrl.matcher.resolve_multiple_team_ids(res.club_name)
                    for tid, tname in team_tuples:
                        existing_rows.append(MappedRow(
                            team_id=tid,
                            stadium_id=target_stadium.primary_id(),
                            stadium_name=target_stadium.display_name,
                            stadium_path=target_stadium.display_name,
                            confidence=res.confidence,
                            status="VALID" if res.confidence >= 0.90 else "REVIEW",
                            enabled=True
                        ))

        if not existing_rows:
            existing_rows.append(MappedRow(
                team_id=102,
                stadium_id=target_stadium.primary_id(),
                stadium_name=target_stadium.display_name,
                stadium_path=target_stadium.display_name,
                confidence=1.0,
                status="MANUAL",
                enabled=True
            ))

        assigned_rows: list[MappedRow] = list(existing_rows)

        # Main Form Frame
        form_f = tk.Frame(dlg, bg="#121C2A", bd=1, relief=tk.SOLID, padx=16, pady=16)
        form_f.pack(fill=tk.BOTH, expand=True, padx=16, pady=8)

        # Stadium Metadata Fields
        meta_grid = tk.Frame(form_f, bg="#121C2A")
        meta_grid.pack(fill=tk.X, pady=(0, 12))

        tk.Label(meta_grid, text="STADIUM ID:", font=("Segoe UI", 9, "bold"), fg="#F1F5F9", bg="#121C2A").grid(row=0, column=0, sticky=tk.W, pady=4)
        var_sid = tk.StringVar(value=assigned_rows[0].stadium_id if assigned_rows else target_stadium.primary_id())
        ent_sid = ttk.Entry(meta_grid, textvariable=var_sid, font=("Segoe UI", 10), width=18)
        ent_sid.grid(row=0, column=1, sticky=tk.W, padx=8, pady=4)

        tk.Label(meta_grid, text="STADIUM NAME:", font=("Segoe UI", 9, "bold"), fg="#F1F5F9", bg="#121C2A").grid(row=1, column=0, sticky=tk.W, pady=4)
        var_sname = tk.StringVar(value=assigned_rows[0].stadium_name if assigned_rows else target_stadium.display_name)
        ent_sname = ttk.Entry(meta_grid, textvariable=var_sname, font=("Segoe UI", 10), width=35)
        ent_sname.grid(row=1, column=1, sticky=tk.W, padx=8, pady=4)

        tk.Label(meta_grid, text="STADIUM PATH:", font=("Segoe UI", 9, "bold"), fg="#F1F5F9", bg="#121C2A").grid(row=2, column=0, sticky=tk.W, pady=4)
        var_spath = tk.StringVar(value=assigned_rows[0].stadium_path if assigned_rows else target_stadium.display_name)
        ent_spath = ttk.Entry(meta_grid, textvariable=var_spath, font=("Segoe UI", 10), width=35)
        ent_spath.grid(row=2, column=1, sticky=tk.W, padx=8, pady=4)

        # Multi-Team Section
        tk.Label(form_f, text="MAPPED TEAMS (Shared Stadium Support):", font=("Segoe UI", 10, "bold"), fg="#19A7FF", bg="#121C2A").pack(anchor=tk.W, pady=(10, 4))

        team_add_f = tk.Frame(form_f, bg="#121C2A")
        team_add_f.pack(fill=tk.X, pady=(0, 8))

        lbl_matched_team = tk.Label(team_add_f, text="[Type team name or ID above]", font=("Segoe UI", 8, "italic"), fg="#35D07F", bg="#121C2A")
        lbl_matched_team.pack(anchor=tk.W, pady=(0, 4))

        def on_autocomplete_select(tid, tname):
            if tid is not None:
                var_add_tid.set(str(tid))
                lbl_matched_team.configure(text=f"✅ Matched: {tname} (ID: {tid})")
            elif tname:
                resolved_tid = self.ctrl.matcher.resolve_team_id(tname)
                if resolved_tid is not None:
                    var_add_tid.set(str(resolved_tid))
                    real_n = self.ctrl.pdf_parser.id_to_name.get(resolved_tid, tname)
                    lbl_matched_team.configure(text=f"✅ Matched: {real_n} (ID: {resolved_tid})")
                else:
                    lbl_matched_team.configure(text="⚠️ Team not found in PDF database")
            else:
                lbl_matched_team.configure(text="")

        auto_entry = TeamAutocompleteEntry(team_add_f, self.ctrl.pdf_parser, on_select=on_autocomplete_select, bg="#121C2A")
        auto_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))

        var_add_tid = tk.StringVar()
        ent_add_tid = ttk.Entry(team_add_f, textvariable=var_add_tid, font=("Segoe UI", 10), width=10)
        ent_add_tid.pack(side=tk.LEFT, padx=(0, 6))

        def add_team_row():
            raw_t = var_add_tid.get().strip() or auto_entry.get()
            if not raw_t:
                messagebox.showwarning("Input Missing", "Please select or enter a Team ID or Club Name.")
                return

            if raw_t.isdigit():
                tid = int(raw_t)
            else:
                tid = self.ctrl.matcher.resolve_team_id(raw_t)
                if tid is None:
                    messagebox.showerror("Error", f"Could not find Team ID for '{raw_t}'.")
                    return

            sid = var_sid.get().strip() or target_stadium.primary_id()
            sname = var_sname.get().strip() or target_stadium.display_name
            spath = var_spath.get().strip() or sname

            # Check if team already added
            if any(r.team_id == tid for r in assigned_rows):
                messagebox.showinfo("Already Added", f"Team ID {tid} is already mapped to this stadium.")
                return

            new_row = MappedRow(
                team_id=tid,
                stadium_id=sid,
                stadium_name=sname,
                stadium_path=spath,
                confidence=1.0,
                status="MANUAL",
                enabled=True
            )
            assigned_rows.append(new_row)
            refresh_assigned_list()
            auto_entry.set("")
            var_add_tid.set("")
            lbl_matched_team.configure(text="")

        tk.Button(team_add_f, text="➕ Add Team", command=add_team_row, bg="#19A7FF", fg="#FFFFFF", font=("Segoe UI", 9, "bold"), relief=tk.FLAT, padx=10).pack(side=tk.LEFT)

        # Assigned Teams Listbox
        list_frame = tk.Frame(form_f, bg="#0B111C", bd=1, relief=tk.SOLID)
        list_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 6))

        assigned_listbox = tk.Listbox(list_frame, bg="#0B111C", fg="#F1F5F9", selectbackground="#19A7FF", font=("Segoe UI", 9), height=5, bd=0)
        assigned_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        sb_list = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=assigned_listbox.yview)
        assigned_listbox.configure(yscroll=sb_list.set)
        sb_list.pack(side=tk.RIGHT, fill=tk.Y)

        def refresh_assigned_list():
            assigned_listbox.delete(0, tk.END)
            for r in assigned_rows:
                tname = self.ctrl.pdf_parser.id_to_name.get(r.team_id, f"Team_{r.team_id}")
                assigned_listbox.insert(tk.END, f"  Team ID: {r.team_id:<6} | {tname}")

        refresh_assigned_list()

        def remove_selected_team():
            sel = assigned_listbox.curselection()
            if not sel:
                return
            idx = sel[0]
            if len(assigned_rows) <= 1:
                messagebox.showwarning("Warning", "A stadium mapping must have at least one team.")
                return
            del assigned_rows[idx]
            refresh_assigned_list()

        tk.Button(form_f, text="❌ Remove Selected Team", command=remove_selected_team, bg="#FF5C6C", fg="#FFFFFF", font=("Segoe UI", 8, "bold"), relief=tk.FLAT, padx=8, pady=3).pack(anchor=tk.E)

        # Button Bar
        btn_f = tk.Frame(dlg, bg="#0B111C", padx=16, pady=12)
        btn_f.pack(fill=tk.X)

        def save_4col_mapping():
            if not assigned_rows:
                messagebox.showwarning("Input Missing", "Please add at least one team mapping.")
                return

            sid_v = var_sid.get().strip() or target_stadium.primary_id()
            sname_v = var_sname.get().strip() or target_stadium.display_name
            spath_v = var_spath.get().strip() or sname_v

            # Update stadium ID, name, and path across all assigned rows
            for r in assigned_rows:
                r.stadium_id = sid_v
                r.stadium_name = sname_v
                r.stadium_path = spath_v
                r.status = "MANUAL"
                r.confidence = 1.0

            self.ctrl.set_manual_mappings(target_stadium.display_name, assigned_rows)
            self._populate_tree(self.ctrl.discovered_stadiums)
            self.ctrl.logger.info(f"Updated 4-Column Multi-Team Mapping for '{target_stadium.display_name}': {len(assigned_rows)} team(s)")
            messagebox.showinfo("Saved", f"4-Column Mapping for '{target_stadium.display_name}' saved & persisted ({len(assigned_rows)} team line(s))!")
            dlg.destroy()

        tk.Button(btn_f, text="💾 Apply & Persist 4-Column Mappings", command=save_4col_mapping, bg="#35D07F", fg="#FFFFFF", font=("Segoe UI", 9, "bold"), relief=tk.FLAT, padx=12, pady=6).pack(side=tk.RIGHT, padx=4)
        tk.Button(btn_f, text="❌ Cancel", command=dlg.destroy, bg="#162232", fg="#94A3B8", font=("Segoe UI", 9), relief=tk.FLAT, padx=10, pady=6).pack(side=tk.RIGHT, padx=4)

    # ===================================================================
    # INTERACTIVE UNRESOLVED STADIUM RESOLVER DIALOG
    # ===================================================================
    def _open_unresolved_resolver_dialog(self, target_stadium: DiscoveredStadium | None = None) -> None:
        """Interactive Unresolved Stadium Resolver Dialog with live autocomplete and pre-filled search suggestions."""
        unresolved_stadiums: list[DiscoveredStadium] = []

        if target_stadium:
            unresolved_stadiums.append(target_stadium)
        else:
            for s in self.ctrl.discovered_stadiums:
                name = s.display_name
                if name in self.ctrl.manual_mappings or name in self.ctrl.skipped_stadiums:
                    continue
                res = self.ctrl.research_results.get(name)
                team_tuples = self.ctrl.matcher.resolve_multiple_team_ids(res.club_name) if res and res.club_name else []
                if not res or not res.club_name or res.confidence < 0.90 or not team_tuples:
                    unresolved_stadiums.append(s)

        if not unresolved_stadiums:
            messagebox.showinfo("All Resolved", "No unresolved stadiums found!")
            return

        idx = [0]  # Current stadium index tracker
        current_assigned_rows: list[MappedRow] = []

        dlg = tk.Toplevel(self.root)
        dlg.title("⚡ Interactive Unresolved Stadium Resolver")
        dlg.geometry("700x680")
        dlg.configure(bg="#0B111C")
        dlg.resizable(True, True)
        dlg.grab_set()

        hdr_lbl = tk.Label(dlg, text="", font=("Segoe UI", 12, "bold"), fg="#19A7FF", bg="#0B111C")
        hdr_lbl.pack(pady=(12, 4))

        info_box = tk.Text(dlg, height=5, wrap=tk.WORD, font=("Cascadia Mono", 9), bg="#05080D", fg="#56E39F", bd=1)
        info_box.pack(fill=tk.X, padx=16, pady=4)

        # Option Frame: Option 1 (Manual Entry & Autocomplete)
        f_manual = ttk.LabelFrame(dlg, text=" Option 1: Select or Type Football Club / Team ID ", padding=10)
        f_manual.pack(fill=tk.X, padx=16, pady=6)

        lbl_matched_team = ttk.Label(f_manual, text="Matched PES Team: [Type name or ID]", font=("Segoe UI", 9, "italic"))
        lbl_matched_team.pack(anchor=tk.W, pady=(0, 4))

        entry_row = tk.Frame(f_manual)
        entry_row.pack(fill=tk.X, pady=4)

        var_resolver_tid = tk.StringVar()

        def on_resolver_autocomplete_select(tid, tname):
            if tid is not None:
                var_resolver_tid.set(str(tid))
                lbl_matched_team.configure(text=f"✅ Matched ID {tid}: {tname}")
            elif tname:
                resolved_tid = self.ctrl.matcher.resolve_team_id(tname)
                if resolved_tid is not None:
                    var_resolver_tid.set(str(resolved_tid))
                    real_n = self.ctrl.pdf_parser.id_to_name.get(resolved_tid, tname)
                    lbl_matched_team.configure(text=f"✅ Matched '{tname}' -> ID {resolved_tid} ({real_n})")
                else:
                    lbl_matched_team.configure(text=f"⚠️ '{tname}' not in PDF database.")
            else:
                lbl_matched_team.configure(text="")

        auto_entry = TeamAutocompleteEntry(entry_row, self.ctrl.pdf_parser, on_select=on_resolver_autocomplete_select)
        auto_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))

        ent_tid = ttk.Entry(entry_row, textvariable=var_resolver_tid, width=10)
        ent_tid.pack(side=tk.LEFT, padx=(0, 6))

        def add_team_to_resolver():
            s_current = unresolved_stadiums[idx[0]]
            raw_t = var_resolver_tid.get().strip() or auto_entry.get()
            if not raw_t:
                messagebox.showwarning("Input Missing", "Please select or enter a team.")
                return

            if raw_t.isdigit():
                tid = int(raw_t)
            else:
                tid = self.ctrl.matcher.resolve_team_id(raw_t)
                if tid is None:
                    messagebox.showerror("Error", f"Could not find Team ID for '{raw_t}'.")
                    return

            if any(r.team_id == tid for r in current_assigned_rows):
                return

            row = MappedRow(
                team_id=tid,
                stadium_id=s_current.primary_id(),
                stadium_name=s_current.display_name,
                stadium_path=s_current.display_name,
                confidence=1.0,
                status="MANUAL",
                enabled=True
            )
            current_assigned_rows.append(row)
            refresh_resolver_teams()
            auto_entry.set("")
            var_resolver_tid.set("")
            lbl_matched_team.configure(text="")

        ttk.Button(entry_row, text="➕ Add Team", command=add_team_to_resolver).pack(side=tk.LEFT)

        # List of teams for current stadium
        teams_box_f = tk.Frame(f_manual, bg="#0B111C", bd=1, relief=tk.SOLID)
        teams_box_f.pack(fill=tk.X, pady=(6, 4))

        resolver_teams_listbox = tk.Listbox(teams_box_f, bg="#0B111C", fg="#F1F5F9", selectbackground="#19A7FF", font=("Segoe UI", 9), height=3, bd=0)
        resolver_teams_listbox.pack(side=tk.LEFT, fill=tk.X, expand=True)

        def refresh_resolver_teams():
            resolver_teams_listbox.delete(0, tk.END)
            for r in current_assigned_rows:
                tname = self.ctrl.pdf_parser.id_to_name.get(r.team_id, f"Team_{r.team_id}")
                resolver_teams_listbox.insert(tk.END, f"  Team ID: {r.team_id:<6} | {tname}")

        def apply_resolver_and_next():
            s_current = unresolved_stadiums[idx[0]]
            if not current_assigned_rows:
                # Try adding whatever is currently in the entry box
                add_team_to_resolver()
                if not current_assigned_rows:
                    messagebox.showwarning("Input Error", "Please add at least one team for this stadium.")
                    return

            self.ctrl.set_manual_mappings(s_current.display_name, current_assigned_rows)
            self._populate_tree(self.ctrl.discovered_stadiums)
            next_stadium()

        btn_row = tk.Frame(f_manual)
        btn_row.pack(fill=tk.X, pady=(4, 0))

        tk.Button(btn_row, text="💾 Apply Mappings & Next Stadium ⏭️", command=apply_resolver_and_next, bg="#35D07F", fg="#FFFFFF", font=("Segoe UI", 9, "bold"), relief=tk.FLAT, padx=12, pady=4).pack(side=tk.RIGHT)

        # Option Frame: Option 2 (Re-search with custom engine or query)
        f_research = ttk.LabelFrame(dlg, text=" Option 2: Re-search with Custom Search Engine / Query ", padding=10)
        f_research.pack(fill=tk.X, padx=16, pady=6)

        ttk.Label(f_research, text="Engine:").grid(row=0, column=0, sticky=tk.W, pady=4)
        engine_var = tk.StringVar(value="wikipedia")
        combo_eng = ttk.Combobox(f_research, textvariable=engine_var, values=["wikipedia", "duckduckgo", "google", "bing"], state="readonly", width=14)
        combo_eng.grid(row=0, column=1, sticky=tk.W, padx=6, pady=4)

        ttk.Label(f_research, text="Query:").grid(row=1, column=0, sticky=tk.W, pady=4)
        entry_query = ttk.Entry(f_research, width=35)
        entry_query.grid(row=1, column=1, sticky=tk.EW, padx=6, pady=4)

        def run_custom_research():
            s_current = unresolved_stadiums[idx[0]]
            eng = engine_var.get()
            q = entry_query.get().strip() or s_current.search_name
            self.ctrl.logger.info(f"Re-searching '{s_current.display_name}' via {eng}...")

            def worker():
                res = self.ctrl.research_stadium(s_current, force_refresh=True, custom_provider=eng, custom_query=q)
                self.root.after(0, lambda: self._update_tree_row(s_current, res))
                self.root.after(0, load_current_stadium_info)
                self.root.after(0, self._update_kpi_counts)

            threading.Thread(target=worker, daemon=True).start()

        ttk.Button(f_research, text="🔍 Live Re-search", command=run_custom_research).grid(row=1, column=2, padx=4, pady=4)
        f_research.columnconfigure(1, weight=1)

        # Option Frame: Option 3 (Skip & Do Not Add)
        f_skip = ttk.Frame(dlg, bg="#0B111C")
        f_skip.pack(fill=tk.X, padx=16, pady=8)

        def skip_stadium():
            s_current = unresolved_stadiums[idx[0]]
            self.ctrl.mark_skipped(s_current.display_name)
            self._populate_tree(self.ctrl.discovered_stadiums)
            next_stadium()

        btn_skip = tk.Button(
            f_skip,
            text="🚫 Leave As Is & Do NOT Add to map_teams.txt",
            command=skip_stadium,
            bg="#FF5C6C",
            fg="#FFFFFF",
            font=("Segoe UI", 9, "bold"),
            relief=tk.FLAT,
            padx=10,
            pady=6,
        )
        btn_skip.pack(side=tk.LEFT)

        def load_current_stadium_info():
            if idx[0] >= len(unresolved_stadiums):
                messagebox.showinfo("Done", "All unresolved stadiums processed!")
                dlg.destroy()
                return

            s_current = unresolved_stadiums[idx[0]]
            hdr_lbl.configure(text=f"[{idx[0] + 1}/{len(unresolved_stadiums)}] Stadium: {s_current.display_name}")

            current_assigned_rows.clear()
            auto_entry.set("")
            var_resolver_tid.set("")
            lbl_matched_team.configure(text="Matched PES Team: [Type name or ID]")

            entry_query.delete(0, tk.END)
            entry_query.insert(0, s_current.search_name)

            info_box.configure(state=tk.NORMAL)
            info_box.delete("1.0", tk.END)

            res = self.ctrl.research_results.get(s_current.display_name)
            text_str = f"STADIUM FOLDER: {s_current.display_name}\nSTADIUM ID: {s_current.primary_id()}\nSEARCH QUERY: {s_current.search_name}\n"
            if res:
                text_str += f"IDENTIFIED CLUB: {res.club_name or 'None'}\nCONFIDENCE: {res.confidence:.2f}\nREASONING: {res.reasoning}\n"
                if res.club_name:
                    auto_entry.set(res.club_name)
                    team_tuples = self.ctrl.matcher.resolve_multiple_team_ids(res.club_name)
                    for tid, tname in team_tuples:
                        current_assigned_rows.append(MappedRow(
                            team_id=tid,
                            stadium_id=s_current.primary_id(),
                            stadium_name=s_current.display_name,
                            stadium_path=s_current.display_name,
                            confidence=res.confidence,
                            status="VALID" if res.confidence >= 0.90 else "REVIEW",
                            enabled=True
                        ))
                    if team_tuples:
                        var_resolver_tid.set(str(team_tuples[0][0]))
                        lbl_matched_team.configure(text=f"✅ Matched: {team_tuples[0][1]} (ID: {team_tuples[0][0]})")
            else:
                text_str += "STATUS: Not researched yet.\n"

            info_box.insert("1.0", text_str)
            info_box.configure(state=tk.DISABLED)
            refresh_resolver_teams()

        def next_stadium():
            idx[0] += 1
            load_current_stadium_info()

        btn_next = ttk.Button(f_skip, text="⏭️ Next Stadium", command=next_stadium)
        btn_next.pack(side=tk.RIGHT)

        load_current_stadium_info()

    # ===================================================================
    # SETTINGS & ACCESSIBILITY CUSTOMIZATION DIALOG
    # ===================================================================
    def _open_customization_dialog(self) -> None:
        """Open Settings & Customization modal dialog."""
        dlg = tk.Toplevel(self.root)
        dlg.title("⚙️ Workstation Settings & Accessibility")
        dlg.geometry("580x620")
        dlg.configure(bg="#0B111C")
        dlg.resizable(False, False)
        dlg.grab_set()

        # PDF Section
        f_pdf = ttk.LabelFrame(dlg, text=" PES Team-ID PDF Database ", padding=10)
        f_pdf.pack(fill=tk.X, padx=12, pady=6)

        pdf_var = tk.StringVar(value=self.ctrl.config_mgr.get_display_path(self.ctrl.config.team_pdf_path))

        ttk.Label(f_pdf, text="Active PDF:").grid(row=0, column=0, sticky=tk.W, pady=4)
        ttk.Entry(f_pdf, textvariable=pdf_var, width=36).grid(row=0, column=1, sticky=tk.EW, padx=8, pady=4)

        def browse_pdf():
            f = filedialog.askopenfilename(title="Select Custom PES Team-ID PDF File", filetypes=[("PDF files", "*.pdf")])
            if f:
                pdf_var.set(self.ctrl.config_mgr.get_display_path(f))
                self.ctrl.configure_paths(self.ctrl.config.stadium_server_dir, pdf_path=f)
                if self.ctrl.load_pdf():
                    messagebox.showinfo("PDF Loaded", f"Successfully parsed custom PDF!\nLoaded {len(self.ctrl.pdf_parser.id_to_name)} team entries.")

        def reset_pdf():
            def_pdf = str(self.ctrl.base_dir / "data" / "team_list.pdf")
            if Path(def_pdf).exists():
                pdf_var.set(self.ctrl.config_mgr.get_display_path(def_pdf))
                self.ctrl.configure_paths(self.ctrl.config.stadium_server_dir, pdf_path=def_pdf)
                self.ctrl.load_pdf()
                messagebox.showinfo("PDF Reset", "Reset to default settings PDF: settings_PSM/data/team_list.pdf")

        ttk.Button(f_pdf, text="Browse", command=browse_pdf).grid(row=0, column=2, pady=4)
        ttk.Button(f_pdf, text="Default PDF", command=reset_pdf).grid(row=1, column=1, sticky=tk.W, padx=8, pady=2)
        f_pdf.columnconfigure(1, weight=1)

        # Accessibility Section
        f_access = ttk.LabelFrame(dlg, text=" Accessibility & Performance ", padding=10)
        f_access.pack(fill=tk.X, padx=12, pady=6)

        ttk.Checkbutton(
            f_access,
            text="Reduce Transparency (Solid Panel Backgrounds)",
            variable=self.reduce_transparency,
            command=lambda: self._apply_theme(self.ctrl.config.theme),
        ).pack(anchor=tk.W, pady=2)

        ttk.Checkbutton(
            f_access,
            text="Reduce Motion (Disable Non-essential Animations)",
            variable=self.reduce_motion,
        ).pack(anchor=tk.W, pady=2)

        # Audio Section
        f_audio = ttk.LabelFrame(dlg, text=" Background Music ", padding=10)
        f_audio.pack(fill=tk.X, padx=12, pady=6)

        vol_var = tk.IntVar(value=self.ctrl.config.music_volume)
        music_path_var = tk.StringVar(value=self.ctrl.config_mgr.get_display_path(self.ctrl.config.custom_music_path))

        def on_volume_change(val):
            v = int(float(val))
            vol_var.set(v)
            self.audio_player.set_volume(v)
            self.ctrl.config_mgr.update(music_volume=v)

        ttk.Label(f_audio, text="Volume:").grid(row=0, column=0, sticky=tk.W, pady=4)
        scale = ttk.Scale(f_audio, from_=0, to=100, value=self.ctrl.config.music_volume, command=on_volume_change)
        scale.grid(row=0, column=1, sticky=tk.EW, padx=8, pady=4)

        lbl_vol = ttk.Label(f_audio, textvariable=vol_var)
        lbl_vol.grid(row=0, column=2, pady=4)

        ttk.Label(f_audio, text="Audio MP3:").grid(row=1, column=0, sticky=tk.W, pady=4)
        ttk.Entry(f_audio, textvariable=music_path_var, width=32).grid(row=1, column=1, sticky=tk.EW, padx=8, pady=4)

        def browse_music():
            f = filedialog.askopenfilename(title="Select Background Music MP3", filetypes=[("Audio Files", "*.mp3;*.wav")])
            if f:
                music_path_var.set(self.ctrl.config_mgr.get_display_path(f))
                self.ctrl.config_mgr.update(custom_music_path=f)
                self.audio_player.play(f, volume=vol_var.get())
                self.btn_audio.configure(text="🎵 Pause Music")

        ttk.Button(f_audio, text="Browse", command=browse_music).grid(row=1, column=2, pady=4)
        f_audio.columnconfigure(1, weight=1)

        # Close
        ttk.Button(dlg, text="Save & Close Settings", command=dlg.destroy).pack(pady=12)

    # ===================================================================
    # STADIUM SERVER ENABLE / DISABLE MANAGER SUB-APP MODAL
    # ===================================================================
    def _open_stadium_server_manager_dialog(self) -> None:
        """Sub-app form to toggle installed stadiums ON (Active) or OFF (Disabled) in map_teams.txt."""
        server_dir = Path(self.server_dir_var.get())
        map_file = server_dir / "map_teams.txt"

        if not map_file.exists():
            messagebox.showwarning("File Missing", f"map_teams.txt not found in Stadium Server root:\n{server_dir}\n\nPlease generate a map file first.")
            return

        dlg = tk.Toplevel(self.root)
        dlg.title("🏟️ Stadium Server Manager")
        dlg.geometry("740x640")
        dlg.configure(bg="#0B111C")
        dlg.resizable(True, True)
        dlg.grab_set()

        # Header
        hdr_f = tk.Frame(dlg, bg="#0B111C", padx=16, pady=12)
        hdr_f.pack(fill=tk.X)
        tk.Label(hdr_f, text="🏟️ STADIUM SERVER MANAGER", font=("Segoe UI", 12, "bold"), fg="#19A7FF", bg="#0B111C").pack(anchor=tk.W)
        tk.Label(hdr_f, text="Enable (Active) or Disable (Commented with #) stadiums directly in map_teams.txt", font=("Segoe UI", 9), fg="#94A3B8", bg="#0B111C").pack(anchor=tk.W)

        # Parse map_teams.txt lines
        items: list[dict[str, Any]] = []

        try:
            with open(map_file, "r", encoding="utf-8") as f:
                raw_lines = f.readlines()

            for idx, line in enumerate(raw_lines):
                s_line = line.strip()
                if not s_line:
                    continue

                is_enabled = not s_line.startswith("#")
                clean_line = s_line.lstrip("#").strip()

                parts = clean_line.split(",")
                if len(parts) >= 4:
                    items.append({
                        "line_idx": idx,
                        "enabled": is_enabled,
                        "team_id": parts[0].strip(),
                        "stadium_id": parts[1].strip(),
                        "stadium_name": parts[2].strip(),
                        "stadium_path": parts[3].strip(),
                        "raw_line": line,
                    })
        except Exception as e:
            messagebox.showerror("Error", f"Failed to read map_teams.txt: {e}")
            dlg.destroy()
            return

        # Search Bar
        ctrl_f = tk.Frame(dlg, bg="#121C2A", padx=12, pady=8)
        ctrl_f.pack(fill=tk.X, padx=16, pady=(0, 8))

        tk.Label(ctrl_f, text="Search Stadiums:", font=("Segoe UI", 9, "bold"), fg="#94A3B8", bg="#121C2A").pack(side=tk.LEFT, padx=(0, 6))
        mgr_search_var = tk.StringVar()
        entry_mgr_search = ttk.Entry(ctrl_f, textvariable=mgr_search_var, width=28)
        entry_mgr_search.pack(side=tk.LEFT, padx=(0, 12))

        # Table Grid
        table_f = tk.Frame(dlg, bg="#0B111C", padx=16, pady=4)
        table_f.pack(fill=tk.BOTH, expand=True)

        cols = ("enabled", "team_id", "stadium_id", "stadium_name", "stadium_path")
        tree_mgr = ttk.Treeview(table_f, columns=cols, show="headings", height=14)

        tree_mgr.heading("enabled", text="STATUS")
        tree_mgr.heading("team_id", text="TEAM ID")
        tree_mgr.heading("stadium_id", text="STADIUM ID")
        tree_mgr.heading("stadium_name", text="STADIUM NAME")
        tree_mgr.heading("stadium_path", text="STADIUM PATH")

        tree_mgr.column("enabled", width=110, anchor=tk.CENTER)
        tree_mgr.column("team_id", width=90, anchor=tk.CENTER)
        tree_mgr.column("stadium_id", width=95, anchor=tk.CENTER)
        tree_mgr.column("stadium_name", width=200)
        tree_mgr.column("stadium_path", width=200)

        sb_mgr = ttk.Scrollbar(table_f, orient=tk.VERTICAL, command=tree_mgr.yview)
        tree_mgr.configure(yscroll=sb_mgr.set)
        tree_mgr.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb_mgr.pack(side=tk.RIGHT, fill=tk.Y)

        tree_mgr.tag_configure("ENABLED", foreground="#35D07F")
        tree_mgr.tag_configure("DISABLED", foreground="#FF5C6C")

        def populate_mgr_tree():
            for item in tree_mgr.get_children():
                tree_mgr.delete(item)

            q = mgr_search_var.get().lower().strip()
            for item in items:
                status_str = "✅ ENABLED" if item["enabled"] else "🚫 DISABLED"
                tag = "ENABLED" if item["enabled"] else "DISABLED"

                if not q or q in item["stadium_name"].lower() or q in item["team_id"] or q in item["stadium_id"]:
                    tree_mgr.insert("", tk.END, iid=str(item["line_idx"]), values=(
                        status_str, item["team_id"], item["stadium_id"], item["stadium_name"], item["stadium_path"]
                    ), tags=(tag,))

        populate_mgr_tree()
        entry_mgr_search.bind("<KeyRelease>", lambda e: populate_mgr_tree())

        def toggle_selected():
            sel = tree_mgr.selection()
            if not sel:
                return
            for iid in sel:
                idx_num = int(iid)
                target = next((it for it in items if it["line_idx"] == idx_num), None)
                if target:
                    target["enabled"] = not target["enabled"]
            populate_mgr_tree()

        def set_all(state: bool):
            for item in items:
                item["enabled"] = state
            populate_mgr_tree()

        tree_mgr.bind("<Double-1>", lambda e: toggle_selected())

        # Bulk Actions Bar
        btn_bar = tk.Frame(dlg, bg="#0B111C", padx=16, pady=8)
        btn_bar.pack(fill=tk.X)

        tk.Button(btn_bar, text="⚡ Toggle Selected", command=toggle_selected, bg="#162232", fg="#F1F5F9", font=("Segoe UI", 9, "bold"), relief=tk.FLAT, padx=8, pady=4).pack(side=tk.LEFT, padx=4)
        tk.Button(btn_bar, text="✅ Enable All", command=lambda: set_all(True), bg="#162232", fg="#35D07F", font=("Segoe UI", 9, "bold"), relief=tk.FLAT, padx=8, pady=4).pack(side=tk.LEFT, padx=4)
        tk.Button(btn_bar, text="🚫 Disable All", command=lambda: set_all(False), bg="#162232", fg="#FF5C6C", font=("Segoe UI", 9, "bold"), relief=tk.FLAT, padx=8, pady=4).pack(side=tk.LEFT, padx=4)

        def save_mgr_changes():
            new_lines = []
            for item in items:
                line_text = f"{item['team_id']},{item['stadium_id']},{item['stadium_name']},{item['stadium_path']}\n"
                if not item["enabled"]:
                    line_text = "#" + line_text
                new_lines.append(line_text)

            try:
                backup_dir = server_dir / "settings_PSM" / "backup_map"
                backup_dir.mkdir(parents=True, exist_ok=True)
                timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                backup_file = backup_dir / f"map_teams_toggle_backup_{timestamp}.txt"

                with open(map_file, "r", encoding="utf-8") as f_orig:
                    with open(backup_file, "w", encoding="utf-8") as f_bak:
                        f_bak.write(f_orig.read())

                with open(map_file, "w", encoding="utf-8") as f_out:
                    f_out.writelines(new_lines)

                # Sync enabled state to mapped_rows and manual_mappings in memory
                for row in self.ctrl.mapped_rows:
                    path_name = row.stadium_path or row.stadium_name
                    matching_item = next(
                        (it for it in items if it["stadium_path"].lower() == path_name.lower() or it["stadium_name"].lower() == row.stadium_name.lower()),
                        None
                    )
                    if matching_item:
                        row.enabled = matching_item["enabled"]

                for st_name, rows in self.ctrl.manual_mappings.items():
                    for row in rows:
                        path_name = row.stadium_path or row.stadium_name
                        matching_item = next(
                            (it for it in items if it["stadium_path"].lower() == path_name.lower() or it["stadium_name"].lower() == row.stadium_name.lower()),
                            None
                        )
                        if matching_item:
                            row.enabled = matching_item["enabled"]

                active_count = sum(1 for it in items if it["enabled"])
                messagebox.showinfo("Saved", f"map_teams.txt successfully updated!\n\nActive Stadiums: {active_count} / {len(items)}\nBackup saved in: settings_PSM/backup_map/")
                dlg.destroy()
                self._cmd_scan()
            except Exception as ex:
                messagebox.showerror("Error", f"Failed to save map_teams.txt: {ex}")

        tk.Button(btn_bar, text="💾 Save Changes to map_teams.txt", command=save_mgr_changes, bg="#35D07F", fg="#FFFFFF", font=("Segoe UI", 9, "bold"), relief=tk.FLAT, padx=12, pady=5).pack(side=tk.RIGHT, padx=4)

    def _on_close(self) -> None:
        """Clean up resources on window exit."""
        if hasattr(self, "audio_player"):
            self.audio_player.stop()
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


# ---------------------------------------------------------------------------
# CLI Interface
# ---------------------------------------------------------------------------

def run_cli(ctrl: StadiumMapperController, args: argparse.Namespace) -> None:
    """Execute application in command-line interface mode."""
    print("\n" + "=" * 60)
    print(f"  PES 2021 Stadium Server Intelligent Mapper — {APP_VERSION}")
    print("=" * 60 + "\n")

    default_dir = ctrl.config.stadium_server_dir or (str(Path("..").resolve()) if (Path("..") / "map_teams.txt").exists() or (Path("..") / "Anfield Road").exists() else ".")
    server_dir = args.stadium_server or default_dir

    ctrl.configure_paths(server_dir)
    if not ctrl.load_pdf():
        print("❌ Error: Failed to parse Team PDF.")
        return

    print(f"📁 Stadium Server: {server_dir}")
    print(f"📄 Team-ID PDF:    {ctrl.config.team_pdf_path}")
    print(f"✅ Loaded {len(ctrl.pdf_parser.id_to_name)} team entries from PDF.\n")

    # Scan
    stadiums = ctrl.scan_stadiums()
    print(f"🔍 Discovered {len(stadiums)} stadiums.\n")

    if args.scan:
        print(f"{'ID':<6} {'Folder Name':<30} {'Search Query'}")
        print("-" * 65)
        for s in stadiums:
            print(f"{s.primary_id():<6} {s.display_name:<30} {s.search_name}")
        return

    # Research
    print("🌐 Performing live web research...")
    for i, s in enumerate(stadiums, 1):
        res = ctrl.research_stadium(s, force_refresh=args.refresh)
        tid = ctrl.matcher.resolve_team_id(res.club_name) if res.club_name else None
        tid_str = str(tid) if tid is not None else "N/A"
        print(f"  [{i}/{len(stadiums)}] {s.display_name:<25} -> {res.club_name or '???':<25} (TID {tid_str:<5}) | Conf: {res.confidence:.2f}")

    print()

    # Dry Run
    if args.dry_run:
        report = ctrl.run_dry_run()
        print("=== DRY RUN REPORT ===")
        print(f"Discovered Stadiums:     {report.total_stadiums_found}")
        print(f"High Confidence (≥0.90): {report.high_confidence_count}")
        print(f"Review (0.75-0.89):      {report.review_count}")
        print(f"Unresolved:              {report.unresolved_count}")
        print(f"Proposed Map Entries:    {len(report.proposed_rows)}")
        print("\nProposed map_teams.txt Content (4-Column Format):")
        print("-" * 50)
        for r in report.proposed_rows:
            print(f"{r.team_id},{r.stadium_id},{r.stadium_name},{r.stadium_path}")
        print("-" * 50)
        print("No files modified.")
        return

    # Generate
    if args.generate or args.auto:
        rows = ctrl.build_mappings()
        if ctrl.write_map_file():
            print(f"\n✅ map_teams.txt successfully generated with {len(rows)} entries!")
            print(f"   Location: {Path(server_dir) / 'map_teams.txt'}")
            print("\nGenerated map_teams.txt Content:")
            print("-" * 40)
            for r in sorted(rows, key=lambda x: x.team_id):
                print(f"{r.team_id},{r.stadium_id},{r.stadium_name},{r.stadium_path}")


# ---------------------------------------------------------------------------
# Main Entry Point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description=f"PES 2021 Stadium Server Mapper — {APP_VERSION}",
    )
    parser.add_argument("--stadium-server", type=str, help="Path to Stadium Server root directory")
    parser.add_argument("--team-pdf", type=str, help="Path to PES team-ID PDF file")
    parser.add_argument("--scan", action="store_true", help="Only scan filesystem")
    parser.add_argument("--research", action="store_true", help="Perform live research")
    parser.add_argument("--auto", action="store_true", help="Auto scan + research + generate map_teams.txt")
    parser.add_argument("--dry-run", action="store_true", help="Perform dry run without writing files")
    parser.add_argument("--generate", action="store_true", help="Generate map_teams.txt")
    parser.add_argument("--refresh", action="store_true", help="Force refresh research cache")
    parser.add_argument("--no-gui", action="store_true", help="Run in CLI mode")

    args = parser.parse_args()

    if getattr(sys, "frozen", False):
        base_dir = Path(sys.executable).parent
        if (base_dir / "settings_PSM").exists():
            base_dir = base_dir / "settings_PSM"
        elif (base_dir / "pes_stadium_mapper_settings").exists():
            base_dir = base_dir / "pes_stadium_mapper_settings"
    else:
        base_dir = Path(__file__).parent.resolve()
        if (base_dir.parent / "settings_PSM").exists():
            base_dir = base_dir.parent / "settings_PSM"

    ctrl = StadiumMapperController(base_dir)

    if args.no_gui or any([args.scan, args.research, args.auto, args.dry_run, args.generate]):
        run_cli(ctrl, args)
    else:
        gui = StadiumMapperGUI(ctrl)
        gui.run()


if __name__ == "__main__":
    main()
