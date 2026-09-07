"""
Audio Player — Native Windows MCI Background Music Player
===========================================================

Provides background music playback (play, pause, stop, volume control, track switching)
using native Windows MCI (ctypes) with zero external dependency requirements.
"""

from __future__ import annotations

import ctypes
import logging
import os
import sys
from pathlib import Path


class WinAudioPlayer:
    """Native Windows MCI MP3 & WAV background music player."""

    def __init__(self, logger: logging.Logger | None = None):
        self.logger = logger or logging.getLogger("stadium_mapper.audio")
        self.current_track: str = ""
        self.is_playing: bool = False
        self.is_paused: bool = False
        self.volume: int = 50  # 0 to 100

    def _mci_send(self, command: str) -> str:
        """Send MCI command string on Windows."""
        if sys.platform != "win32":
            return ""

        buf = ctypes.create_unicode_buffer(256)
        res = ctypes.windll.winmm.mciSendStringW(command, buf, 255, None)
        if res != 0:
            err_buf = ctypes.create_unicode_buffer(256)
            ctypes.windll.winmm.mciGetErrorStringW(res, err_buf, 255)
            self.logger.debug(f"MCI Command error: '{command}' -> {err_buf.value}")
        return buf.value

    def play(self, music_path: str | Path, loop: bool = True, volume: int = 50) -> bool:
        """Play or loop background music file."""
        if not music_path:
            return False

        track_path = Path(music_path).resolve()
        if not track_path.exists():
            self.logger.warning(f"Audio file not found: {track_path}")
            return False

        self.stop()
        self.current_track = str(track_path)
        self.volume = volume

        try:
            alias = "pes_bg_music"
            # Open MCI device
            self._mci_send(f'open "{self.current_track}" type mpegvideo alias {alias}')

            # Set initial volume (MCI volume range 0-1000)
            vol_mci = max(0, min(1000, int(volume * 10)))
            self._mci_send(f'setaudio {alias} volume to {vol_mci}')

            # Play
            repeat_flag = "repeat" if loop else ""
            self._mci_send(f'play {alias} {repeat_flag}')

            self.is_playing = True
            self.is_paused = False
            self.logger.info(f"Started background music: {track_path.name} (Volume: {volume}%)")
            return True
        except Exception as e:
            self.logger.error(f"Failed to play audio {track_path}: {e}")
            return False

    def pause(self) -> None:
        """Pause playback."""
        if self.is_playing and not self.is_paused:
            self._mci_send("pause pes_bg_music")
            self.is_paused = True
            self.logger.info("Paused background music")

    def resume(self) -> None:
        """Resume playback."""
        if self.is_playing and self.is_paused:
            self._mci_send("resume pes_bg_music")
            self.is_paused = False
            self.logger.info("Resumed background music")

    def toggle_pause(self) -> None:
        """Toggle pause/resume."""
        if self.is_paused:
            self.resume()
        else:
            self.pause()

    def stop(self) -> None:
        """Stop and close audio device."""
        self._mci_send("stop pes_bg_music")
        self._mci_send("close pes_bg_music")
        self.is_playing = False
        self.is_paused = False

    def set_volume(self, volume: int) -> None:
        """Set volume (0 to 100)."""
        self.volume = max(0, min(100, volume))
        vol_mci = int(self.volume * 10)
        self._mci_send(f"setaudio pes_bg_music volume to {vol_mci}")
