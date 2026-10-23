# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_submodules

hiddenimports = collect_submodules('uvicorn') + collect_submodules('fastapi') + collect_submodules('starlette')


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('static', 'static')],
    hiddenimports=hiddenimports + [
        'multipart', 'python_multipart', 'openpyxl', 'openpyxl.cell._writer',
        'pandas', 'h11', 'httptools', 'anyio', 'anyio._backends._asyncio',
    ],
    hookspath=[], hooksconfig={}, runtime_hooks=[],
    excludes=['matplotlib', 'scipy', 'PIL', 'gi', 'tkinter', 'PyQt5', 'PySide2', 'PySide6', 'PyQt6', 'IPython', 'notebook'],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [],
    name='Configuration_Comparison_Tool',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    version='version_info.txt',
)
