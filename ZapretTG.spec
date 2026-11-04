# -*- mode: python ; coding: utf-8 -*-
# Сборка: pyinstaller ZapretTG.spec           → dist/ZapretTG.exe (один файл)
#         set ONEDIR=1 && pyinstaller ZapretTG.spec → dist/ZapretTG/ (папка, для установщика и portable.zip)
import os
ONEDIR = os.environ.get('ONEDIR') == '1'
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

hidden = collect_submodules('proxy') + ['utils.update_check', 'utils.diagnostics', 'utils.logging_setup',
          'ui.connectivity', 'ui.i18n', 'h2', 'httpx._transports.default',
          'cryptography.hazmat.primitives.ciphers', 'cryptography.hazmat.primitives.ciphers.algorithms',
          'cryptography.hazmat.primitives.ciphers.modes', 'cryptography.hazmat.backends.openssl', 'hpack', 'hyperframe', 'httpx', 'certifi', 'psutil']

a = Analysis(
    ['run.py'],
    pathex=['vendor/tgws', '.'],
    binaries=[],
    datas=[('resources/zapret', 'resources/zapret'),
           ('vendor/tgws/ui/i18n/*.json', 'ui/i18n'),
           ('vendor/tgws/LICENSE', 'licenses/tg-ws-proxy')] + collect_data_files('certifi'),
    hiddenimports=hidden,
    hookspath=[],
    runtime_hooks=[],
    excludes=['tkinter', '_tkinter', 'customtkinter', 'pystray', 'PIL', 'pyperclip',
              'PySide6.QtQml', 'PySide6.QtQuick', 'PySide6.QtPdf', 'PySide6.QtOpenGL',
              'PySide6.QtWebEngineCore', 'PySide6.QtMultimedia', 'PySide6.Qt3DCore',
              'lib2to3'],
    noarchive=False,
    optimize=0,
)
# убрать ненужные части Qt (переводы, лишние плагины) — exe меньше и быстрее стартует
drop = ('translations', 'qtvirtualkeyboard', 'qpdf', 'qtuiotouch', 'opengl32sw', 'Qt6Pdf', 'Qt6Qml',
        'Qt6Quick', 'Qt6OpenGL', 'Qt6VirtualKeyboard', 'qminimal', 'qdirect2d',
        'qtga', 'qtiff', 'qwbmp', 'qwebp', 'qicns', 'qjpeg', 'qgif', 'qpdf', 'qnetworklistmanager')
a.binaries = [b for b in a.binaries if not any(d.lower() in b[0].lower() for d in drop)
              and b[0].lower() not in ('cygwin1.dll', 'windivert.dll')]
a.datas = [d for d in a.datas if not any(x in d[0].lower() for x in ('translations',))]

pyz = PYZ(a.pure)
common = dict(name='ZapretTG', debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
              console=False, uac_admin=True, icon='build_assets/app.ico', version='build_assets/version.txt')
if ONEDIR:
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, **common)
    coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='ZapretTG')
else:
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], runtime_tmpdir=None, **common)
