# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

spec_dir = Path(SPECPATH).resolve()

a = Analysis(
    ['main.py'],
    pathex=[str(spec_dir)],
    binaries=[],
    datas=[
        (str(spec_dir / 'styles'), 'styles'),
        ('V:/Games/eFootball PES 2021/sider/content/stadium-server/settings_PSM', 'settings_PSM'),
    ],
    hiddenimports=[
        'PySide6',
        'PySide6.QtCore',
        'PySide6.QtWidgets',
        'PySide6.QtGui',
        'PIL',
        'PIL.Image',
        'fitz',
        'pymupdf',
        'requests',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='Pes stadium mapper',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=[str(spec_dir / 'logo.ico')],
)
