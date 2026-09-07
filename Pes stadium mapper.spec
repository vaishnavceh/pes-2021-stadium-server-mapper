# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['stadium_mapper.py'],
    pathex=['source_PSM'],
    binaries=[],
    datas=[('V:/Games/eFootball PES 2021/sider/content/stadium-server/settings_PSM', 'settings_PSM')],
    hiddenimports=[],
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
    icon=['V:/Games/eFootball PES 2021/sider/content/stadium-server/source_PSM/logo.ico'],
)
