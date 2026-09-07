from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Ensure source directory is on sys.path
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# Resolve root directory containing settings_PSM or stadium-server files
ROOT_DIR = BASE_DIR.parent if (BASE_DIR.parent / "settings_PSM").exists() else BASE_DIR

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

    # PySide6 Presentation Layer GUI Entry Point
    from PySide6.QtWidgets import QApplication
    from ui.main_window import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName("PES 2021 Stadium Server Mapper")
    app.setOrganizationName("PES Modding Tools")

    main_win = MainWindow(controller)
    main_win.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
