# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['armory_gui.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=['__future__', 'ast', 'base64', 'binascii', 'bisect', 'bz2', 'calendar', 'codecs', 'collections', 'configparser', 'csv', 'ctypes', 'datetime', 'decimal', 'difflib', 'email', 'encodings', 'fnmatch', 'fractions', 'getpass', 'glob', 'gzip', 'hashlib', 'heapq', 'hmac', 'html', 'io', 'itertools', 'locale', 'lzma', 'mimetypes', 'operator', 'pathlib', 'platform', 'plistlib', 'quopri', 'random', 'secrets', 'shlex', 'shutil', 'socket', 'ssl', 'stat', 'statistics', 'string', 'struct', 'subprocess', 'tarfile', 'tempfile', 'textwrap', 'threading', 'unicodedata', 'urllib', 'uu', 'uuid', 'winsound', 'xml', 'zipfile', 'zlib', 'zoneinfo', 'tzdata'],
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
    name='军火库',
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
)
