# -*- mode: python ; coding: utf-8 -*-
# PyInstaller 打包：suojian 后端 -> 单个 exe（自带 Python 运行时）
import os
from PyInstaller.utils.hooks import collect_all, collect_submodules

datas, binaries, hiddenimports = [], [], []

# 前端静态文件（app.py 冻结后从 _MEIPASS/frontend 读取）
datas += [(os.path.abspath(os.path.join('..', 'frontend')), 'frontend')]

# 需要连带数据/二进制/子模块的第三方包
for pkg in ('jieba', 'reportlab', 'docx', 'pptx', 'sqlalchemy_dm', 'dmPython'):
    try:
        d, b, h = collect_all(pkg)
        datas += d; binaries += b; hiddenimports += h
    except Exception as e:
        print(f"[spec] collect_all({pkg}) 跳过: {e}")

# 本项目蓝图/服务/工具（create_app 内动态 import，确保全部打进去）
for pkg in ('routes', 'services', 'utils'):
    hiddenimports += collect_submodules(pkg)

hiddenimports += [
    'psycopg2', 'dmPython',
    'sqlalchemy_dm.dmPython', 'sqlalchemy_dm.base', 'sqlalchemy_dm.types',
    'models', 'config', 'validators', 'dm_compat',
]

a = Analysis(
    ['app.py'],
    pathex=[os.path.abspath('.')],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='zhxx_suojian',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
