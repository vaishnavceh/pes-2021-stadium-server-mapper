"""
Config Manager — Configuration & Environment Settings
=====================================================

Manages user settings, API keys, path configurations, themes, logo, and audio settings.
Supports portable relative path resolution so settings work across different PCs.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass
class AppConfig:
    """Application configuration settings."""
    stadium_server_dir: str = ""
    team_pdf_path: str = ""
    search_provider: str = "duckduckgo"  # "google", "bing", "duckduckgo", "wikipedia"
    google_api_key: str = ""
    google_search_engine_id: str = ""
    bing_api_key: str = ""
    auto_accept_threshold: float = 0.90
    review_threshold: float = 0.75
    enable_cache: bool = True
    max_search_queries_per_stadium: int = 4
    cache_max_age_days: int = 30
    backup_existing_map: bool = True

    # Customization & Theme Options
    theme: str = "pes_night"
    play_music_on_start: bool = True
    music_volume: int = 50  # 0 to 100
    custom_music_path: str = ""
    custom_logo_path: str = ""

    def mask_secret(self, secret: str) -> str:
        """Mask an API key for safe display in UI/logs."""
        if not secret or len(secret) <= 6:
            return "******" if secret else ""
        return secret[:3] + "..." + secret[-3:]

    def to_dict(self) -> dict[str, Any]:
        """Convert config to dictionary."""
        return asdict(self)



class ConfigManager:
    """
    Loads, saves, and updates application settings.
    Stores asset paths as RELATIVE to settings_PSM folder.
    Resolves them to ABSOLUTE at runtime based on exe/script location.
    This makes the config fully portable across different PCs and drives.
    """

    DEFAULT_CONFIG_FILE = "stadium_mapper_config.json"

    def __init__(self, base_dir: str | Path | None = None, logger: logging.Logger | None = None):
        self.base_dir = Path(base_dir or ".").resolve()
        # Config lives in settings_PSM subfolder (next to exe)
        self.settings_dir = self.base_dir / "settings_PSM"
        self.settings_dir.mkdir(exist_ok=True)
        self.config_path = self.settings_dir / self.DEFAULT_CONFIG_FILE
        self.logger = logger or logging.getLogger("stadium_mapper.config")
        self.config = AppConfig()
        self.load()

    def _exe_dir(self) -> Path:
        """Return directory of the running exe (frozen) or script (dev)."""
        if getattr(sys, "frozen", False):
            return Path(sys.executable).resolve().parent
        return Path(__file__).resolve().parent

    def _resolve_portable_path(self, stored_path: str, default_subpath: str) -> str:
        """
        Resolve a stored path to an absolute path.
        Priority:
          1. If stored_path is already absolute and exists → use it
          2. If stored_path is relative → resolve from settings_PSM
          3. Try default_subpath relative to settings_PSM
          4. Try default_subpath relative to exe dir / settings_PSM
          5. Return stored_path unchanged (caller handles missing)
        """
        settings_dir = self._exe_dir() / "settings_PSM"
        base_settings = settings_dir if settings_dir.exists() else self.settings_dir

        if stored_path:
            p = Path(stored_path)
            # If absolute and exists → return as-is
            if p.is_absolute() and p.exists():
                return str(p)
            # If relative, try from settings_PSM
            rel_p = base_settings / p
            if rel_p.exists():
                return str(rel_p.resolve())
            # Try just the filename in settings_PSM tree
            for candidate in base_settings.rglob(p.name):
                return str(candidate.resolve())

        # Fallback: default subpath relative to settings_PSM
        def_p = base_settings / default_subpath
        if def_p.exists():
            return str(def_p.resolve())

        # Try old-style absolute path still on this machine
        if stored_path:
            p = Path(stored_path)
            if p.exists():
                return str(p)

        return stored_path or ""

    def _make_portable(self, abs_path: str) -> str:
        """
        Convert an absolute path to a path relative to settings_PSM if possible.
        This ensures the saved config is portable.
        """
        if not abs_path:
            return ""
        try:
            p = Path(abs_path).resolve()
            settings_dir = self._exe_dir() / "settings_PSM"
            if not settings_dir.exists():
                settings_dir = self.settings_dir
            try:
                rel = p.relative_to(settings_dir)
                return str(rel)
            except ValueError:
                pass
            # If in same tree as base_dir, store relative
            try:
                rel = p.relative_to(self._exe_dir())
                return str(rel)
            except ValueError:
                pass
        except Exception:
            pass
        return abs_path

    def get_display_path(self, path_str: str) -> str:
        """Return a short display-friendly path."""
        if not path_str:
            return ""
        try:
            p = Path(path_str).resolve()
            settings_dir = self._exe_dir() / "settings_PSM"
            try:
                return str(p.relative_to(settings_dir.parent))
            except ValueError:
                pass
        except Exception:
            pass
        return path_str

    def load(self) -> AppConfig:
        """Load configuration from file and environment variables."""
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for k, v in data.items():
                        if hasattr(self.config, k):
                            setattr(self.config, k, v)
                self.logger.info(f"Loaded configuration from {self.config_path}")
            except Exception as e:
                self.logger.warning(f"Error loading config file: {e}")

        # Resolve all asset paths to absolute, portable to this machine
        self.config.team_pdf_path = self._resolve_portable_path(
            self.config.team_pdf_path, "pdf/PES2021_Team_IDs.pdf"
        )
        self.config.custom_music_path = self._resolve_portable_path(
            self.config.custom_music_path, "audio/pes2021_theme.mp3"
        )
        self.config.custom_logo_path = self._resolve_portable_path(
            self.config.custom_logo_path, "misc/logo.png"
        )

        # Default stadium_server_dir to exe parent directory if not set or missing
        if not self.config.stadium_server_dir or not Path(self.config.stadium_server_dir).exists():
            exe_dir = self._exe_dir()
            # Check exe dir first (most common: exe sits next to stadium server)
            if (exe_dir / "map_teams.txt").exists() or (exe_dir / "Anfield Road").exists():
                self.config.stadium_server_dir = str(exe_dir)
            elif (exe_dir.parent / "map_teams.txt").exists():
                self.config.stadium_server_dir = str(exe_dir.parent)
            else:
                self.config.stadium_server_dir = str(exe_dir)

        # Environment variable overrides
        for env_key, cfg_key in [
            ("SEARCH_PROVIDER", "search_provider"),
            ("GOOGLE_API_KEY", "google_api_key"),
            ("GOOGLE_SEARCH_ENGINE_ID", "google_search_engine_id"),
            ("BING_API_KEY", "bing_api_key"),
        ]:
            val = os.getenv(env_key)
            if val:
                setattr(self.config, cfg_key, val.lower() if cfg_key == "search_provider" else val)

        return self.config

    def save(self) -> bool:
        """Save configuration to disk with portable (relative) asset paths."""
        try:
            data = self.config.to_dict()
            # Convert absolute asset paths to portable relative paths before saving
            for field in ("team_pdf_path", "custom_music_path", "custom_logo_path"):
                if data.get(field):
                    data[field] = self._make_portable(data[field])
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            self.logger.debug(f"Saved config to {self.config_path}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to save config: {e}")
            return False

    def update(self, **kwargs: Any) -> None:
        """Update specific configuration keys and save."""
        for k, v in kwargs.items():
            if hasattr(self.config, k):
                setattr(self.config, k, v)
        self.save()


