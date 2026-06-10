# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path


spec_base = Path(SPECPATH).resolve()
repo_root = spec_base if (spec_base / 'desktop' / 'app.py').exists() else spec_base.parent

a = Analysis(
    [str(repo_root / 'desktop' / 'app.py')],
    pathex=[],
    binaries=[],
    datas=[
        (str(repo_root / 'config' / 'snnu-config.example.json'), 'config'),
        (str(repo_root / 'scripts'), 'scripts'),
        (str(repo_root / 'desktop' / 'assets'), 'desktop\\assets'),
    ],
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
    [],
    exclude_binaries=True,
    name='SNNU WiFi Console',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(repo_root / 'desktop' / 'assets' / 'app.ico'),
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='SNNU WiFi Console',
)
