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
    """Loads, saves, and updates application settings with portable relative path resolution."""

    DEFAULT_CONFIG_FILE = "stadium_mapper_config.json"

    def __init__(self, base_dir: str | Path | None = None, logger: logging.Logger | None = None):
        self.base_dir = Path(base_dir or ".").resolve()
        self.config_path = self.base_dir / self.DEFAULT_CONFIG_FILE
        self.logger = logger or logging.getLogger("stadium_mapper.config")
        self.config = AppConfig()
        self.load()

    def _resolve_portable_path(self, path_str: str, default_subpath: str) -> str:
        """Resolve a path flexibly so configuration remains portable across different PCs."""
        meipass = getattr(sys, "_MEIPASS", None)

        if path_str:
            p = Path(path_str)
            if p.exists():
                return str(p)

            # Try resolving relative to base_dir
            rel_p = self.base_dir / p.name
            if rel_p.exists():
                return str(rel_p)

            # Try matching subpaths (e.g. pdf/PES2021_Team_IDs.pdf or audio/pes2021_theme.mp3)
            parts = p.parts
            if len(parts) >= 2:
                sub_p = self.base_dir / Path(*parts[-2:])
                if sub_p.exists():
                    return str(sub_p)

        # Check default_subpath relative to base_dir or settings_PSM
        def_p = self.base_dir / default_subpath
        if def_p.exists():
            return str(def_p)

        alt_p = self.base_dir / "settings_PSM" / default_subpath
        if alt_p.exists():
            return str(alt_p)

        # PyInstaller bundled asset fallback (_MEIPASS) for standalone distribution
        if meipass:
            bundled_p = Path(meipass) / "settings_PSM" / default_subpath
            if not bundled_p.exists():
                bundled_p = Path(meipass) / default_subpath

            if bundled_p.exists():
                # Auto-extract to local disk if local settings_PSM is missing
                try:
                    target_local = self.base_dir / "settings_PSM" / default_subpath
                    if not target_local.exists():
                        target_local.parent.mkdir(parents=True, exist_ok=True)
                        import shutil
                        shutil.copy2(bundled_p, target_local)
                        self.logger.info(f"Auto-extracted bundled asset to local disk: {target_local}")
                        return str(target_local)
                except Exception as e:
                    self.logger.debug(f"Could not extract bundled asset: {e}")
                return str(bundled_p)

        return path_str

    def get_display_path(self, path_str: str) -> str:
        """Return clean portable display path relative to settings package if inside base_dir."""
        if not path_str:
            return ""
        try:
            p = Path(path_str).resolve()
            if self.base_dir in p.parents or p.parent == self.base_dir:
                return str(p.relative_to(self.base_dir.parent if self.base_dir.name == "settings_PSM" else self.base_dir))
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

        # Portable path resolution for assets
        self.config.team_pdf_path = self._resolve_portable_path(self.config.team_pdf_path, "pdf/PES2021_Team_IDs.pdf")
        self.config.custom_music_path = self._resolve_portable_path(self.config.custom_music_path, "audio/pes2021_theme.mp3")
        self.config.custom_logo_path = self._resolve_portable_path(self.config.custom_logo_path, "misc/logo.png")

        # Environment variable overrides
        env_provider = os.getenv("SEARCH_PROVIDER")
        if env_provider:
            self.config.search_provider = env_provider.lower()

        env_g_key = os.getenv("SEARCH_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if env_g_key:
            self.config.google_api_key = env_g_key

        env_cx = os.getenv("SEARCH_ENGINE_ID") or os.getenv("GOOGLE_SEARCH_ENGINE_ID")
        if env_cx:
            self.config.google_search_engine_id = env_cx

        env_bing = os.getenv("BING_API_KEY")
        if env_bing:
            self.config.bing_api_key = env_bing

        return self.config

    def save(self) -> bool:
        """Save configuration to disk."""
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self.config.to_dict(), f, indent=2, ensure_ascii=False)
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
