from __future__ import annotations

import argparse
import sys
from pathlib import Path

# ─────────────────────────────────────────────────────────────────
# Determine BASE_DIR (source code location) and ROOT_DIR (exe/data location)
# BASE_DIR: where the Python source files live (always the .py directory)
# ROOT_DIR: where settings_PSM + stadium server data lives (exe parent when frozen)
# ─────────────────────────────────────────────────────────────────
if getattr(sys, "frozen", False):
    # Running as PyInstaller standalone exe
    BASE_DIR = Path(sys._MEIPASS).resolve()
    ROOT_DIR = Path(sys.executable).resolve().parent
else:
    BASE_DIR = Path(__file__).resolve().parent
    ROOT_DIR = BASE_DIR

if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from core.controller import StadiumMapperController


def run_cli_mode(ctrl: StadiumMapperController, args: argparse.Namespace) -> int:
    """Execute command-line automation workflow without GUI."""
    print("============================================================")
    print("  PES 2021 Stadium Server Intelligent Mapper — PySide6 Build")
    print("============================================================")

    stadiums = ctrl.scan_stadiums()
    print(f"[+] Discovered {len(stadiums)} stadium folders.")

    if args.refresh or args.auto:
        print("[*] Performing live web research...")
        for s in ctrl.discovered_stadiums:
            res = ctrl.research_stadium(s.display_name, force_refresh=args.refresh)
            print(f"  [{s.display_name}] -> {res.identified_clubs} (TID {res.pes_team_ids}) | Conf: {res.confidence:.2f}")

    if args.dry_run:
        report = ctrl.generate_dry_run()
        print("\n=== DRY RUN REPORT ===")
        print(f"Discovered: {report.total_stadiums_found}")
        print(f"High Confidence: {report.high_confidence_count}")
        print(f"Review Required: {report.review_count}")
        print(f"Unresolved: {report.unresolved_count}")
        print(f"Proposed Lines: {len(report.proposed_rows)}")
        return 0

    if args.auto:
        success, msg = ctrl.generate_map_file()
        print(f"\nWrite Output: {'SUCCESS' if success else 'FAILED'} - {msg}")
        return 0 if success else 1

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="PES 2021 Stadium Server Intelligent Mapper — PySide6 Build")
    parser.add_argument("--no-gui", "--cli", action="store_true", help="Run in command-line mode without GUI")
    parser.add_argument("--auto", action="store_true", help="Automatically perform research and write map_teams.txt")
    parser.add_argument("--dry-run", action="store_true", help="Generate dry-run mapping report without modifying files")
    parser.add_argument("--refresh", action="store_true", help="Force refresh web research cache")
    args = parser.parse_args()

    controller = StadiumMapperController(ROOT_DIR)

    if args.no_gui or args.auto or args.dry_run:
        return run_cli_mode(controller, args)

    # ── PySide6 GUI Entry Point ──────────────────────────────────
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QTimer

    app = QApplication(sys.argv)
    app.setApplicationName("PES 2021 Stadium Server Mapper")
    app.setOrganizationName("PES Modding Tools")

    # Splash Screen
    from ui.splash import SplashScreen
    logo_path = controller.config.custom_logo_path or ""
    splash = SplashScreen(logo_path)
    splash.show()
    app.processEvents()

    # Build MainWindow
    from ui.main_window import MainWindow
    main_win = MainWindow(controller)

    # Show main window and close splash after a short delay
    def _show_main():
        splash.stop_animation()
        splash.finish(main_win)
        main_win.show()

        # Auto-start music if configured
        if controller.config.play_music_on_start:
            music_path = controller.config.custom_music_path
            if music_path and Path(music_path).exists():
                main_win.audio_player.play(music_path, volume=controller.config.music_volume)
                main_win.topbar.btn_music.setText("⏸ Pause")
                main_win.ctrl.logger.info("Auto-started background music on launch.")

    QTimer.singleShot(2500, _show_main)

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())

