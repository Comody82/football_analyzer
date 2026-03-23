# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec per analysis_engine.exe
# Esegui: pyinstaller build_engine.spec

import sys

# Aumenta recursion per moduli profondi (torch, yolox)
sys.setrecursionlimit(max(3000, sys.getrecursionlimit() * 2))

block_cipher = None

# Hidden imports per PyTorch, YOLOX, analysis
hiddenimports = [
    "torch",
    "torchvision",
    "cv2",
    "numpy",
    "scipy",
    "scipy.optimize",
    "scipy.optimize.linear_sum_assignment",
    "sklearn",
    "sklearn.cluster",
    "sklearn.cluster.k_means_",
    "yolox",
    "yolox.exp",
    "yolox.exp.default",
    "yolox.tools",
    "yolox.tools.demo",
    "yolox.data",
    "yolox.data.datasets",
    "yolox.models",
    "yolox.utils",
    "psutil",
    "analysis",
    "analysis.config",
    "analysis.field_calibration",
    "analysis.video_preprocessing",
    "analysis.player_detection",
    "analysis.player_tracking",
    "analysis.ball_detection",
    "analysis.ball_tracking",
    "analysis.team_classifier",
]

# Dati da includere: cartella models (vuota o con yolox_s.pth opzionale)
# I pesi YOLOX vengono scaricati a runtime se mancanti
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

datas = []
# Opzionale: include models se esiste yolox_s.pth
try:
    from pathlib import Path
    models_dir = Path("models")
    if (models_dir / "yolox_s.pth").exists():
        datas.append((str(models_dir / "yolox_s.pth"), "models"))
except Exception:
    pass

a = Analysis(
    ["analysis_engine.py"],
    pathex=["."],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "PyQt5", "PyQt6", "tkinter",  # non servono per engine
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# onedir: più affidabile con PyTorch (onefile può dare problemi)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="analysis_engine",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="analysis_engine",
)
