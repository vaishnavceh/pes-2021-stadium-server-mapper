# PES 2021 Stadium Server Mapper — Nightly Build 1.0.0

[![CI/CD Pipeline](https://github.com/vaishnavceh/pes-2021-stadium-server-mapper/actions/workflows/ci.yml/badge.svg)](https://github.com/vaishnavceh/pes-2021-stadium-server-mapper/actions/workflows/ci.yml)
[![Python Version](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/platform-Windows-0078D6.svg)](https://www.microsoft.com/windows)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

An intelligent, multi-threaded python workstation application that automatically scans PES 2021 Sider Stadium Server directories, resolves home team assignments via live web research (Wikipedia + DuckDuckGo), parses official PES team ID databases, decodes stadium DDS thumbnails, and generates valid 4-column `map_teams.txt` configurations.

---

## 🌟 Key Features

- **🔍 Automatic Directory Scanner**: Recursively scans stadium folders for `st###` model IDs (`Asset/model/bg/st###`).
- **🌐 Web Research Engine**: Multi-stage web resolution (Wikipedia API + DuckDuckGo) with intelligent title cleaning, mod suffix stripping (2025, UHD, V2), and persistent caching (`stadium_research_cache.json`).
- **🏟️ Multi-Team / Shared Venue Support**: Automatically splits compound research results (e.g. Real Madrid & Spain NT) into multiple 4-column `map_teams.txt` mapping entries.
- **🖼️ Real DDS Thumbnail Rendering**: Decodes native PES 2021 `st###.dds` texture files via Pillow (`PIL.Image`) into 52x30 treeview row previews and 160x90 enlarged inspector previews.
- **⚡ Single Authoritative Status Engine**: Standardized `StadiumStatus` enum (`RESOLVED`, `REVIEW`, `UNRESOLVED`, `MANUAL`, `SKIPPED`) ensuring 100% synchronization across dashboard KPI cards, status badge, table rows, and file output.
- **💡 Live Team Autocomplete**: Real-time suggestion dropdown as you type, querying the 350+ official PES team ID database.
- **🎛️ Stadium Server Manager**: Toggle individual stadiums on/off (`#` commented lines) without losing explicit user enablement states.
- **🎵 Built-in Ambient Audio Player**: Integrated background audio player using Windows `winmm.dll` MCI architecture.
- **📦 Single-File Executable**: Compiles cleanly into a self-contained Windows binary (`Pes stadium mapper.exe`).

---

## 📁 Repository Structure

```text
.
├── .github/
│   └── workflows/
│       └── ci.yml             # GitHub Actions CI/CD Pipeline (Lint, Test, PyInstaller Build)
├── audio_player.py            # Windows MCI background ambient music player
├── config.py                  # Configuration loader & persistent JSON manager
├── logo.ico                   # Application icon asset
├── map_generator.py           # 4-column map_teams.txt generator with backup rotation
├── Pes stadium mapper.spec    # PyInstaller single-file build specification
├── README.md                  # Project documentation
├── requirements.txt           # Python dependencies
├── stadium_mapper.py          # Main GUI & CLI application entry point
├── stadium_scanner.py         # Stadium directory scanner & DDS path finder
├── team_matcher.py            # Fuzzy string matching engine for team names
├── team_pdf_parser.py         # PyMuPDF parser for PES Team-ID reference PDFs
├── validator.py               # Map row format validator & duplicate checker
└── web_research.py            # Wikipedia & DuckDuckGo live research scraper
```

---

## 🚀 Quick Start

### 1. Requirements
- Python 3.8+
- Windows OS (Tkinter & WinMM MCI support)

### 2. Installation
```powershell
git clone https://github.com/vaishnavceh/pes-2021-stadium-server-mapper.git
cd pes-2021-stadium-server-mapper
pip install -r requirements.txt
```

### 3. Usage

#### GUI Workstation Mode (Default)
```powershell
python stadium_mapper.py
```

#### CLI Automation Commands
```powershell
# Full automatic research and map generation
python stadium_mapper.py --no-gui --auto

# Scan directories and print dry-run report
python stadium_mapper.py --no-gui --dry-run

# Interactive resolution in terminal
python stadium_mapper.py --no-gui --interactive

# Force refresh web research cache
python stadium_mapper.py --no-gui --refresh
```

---

## ⚙️ Building Standalone Executable

To compile into a single executable file `Pes stadium mapper.exe`:

```powershell
pip install pyinstaller
pyinstaller --noconfirm "Pes stadium mapper.spec"
```

The compiled binary will be placed inside `dist/Pes stadium mapper.exe`.

---

## 🤖 CI/CD Workflow

The repository includes a automated GitHub Actions workflow (`.github/workflows/ci.yml`) that runs on every `push` and `pull_request`:
1. Checks Python syntax and compiles all modules (`py_compile`).
2. Validates CLI argument parsing and help execution.
3. Builds the standalone Windows `.exe` using PyInstaller.
4. Uploads the compiled binary artifact to GitHub Action run summary.

---

## 📜 License

Distributed under the MIT License. See `LICENSE` for more information.
