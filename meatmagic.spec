# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for MEATMAGIC — bundles the Django + pywebview desktop app
into a single .exe for easy distribution.
"""
import os
import sys

from PyInstaller.building.datastruct import Tree
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# ── project root ─────────────────────────────────────────────────────────
PROJ = os.getcwd()

# ── collect project template & migration files ───────────────────────────
project_data = []

for src_dir, dst_dir in [
    (os.path.join(PROJ, "templates"), "templates"),
    (os.path.join(PROJ, "sales", "templates"), os.path.join("sales", "templates")),
    (os.path.join(PROJ, "sales", "migrations"), os.path.join("sales", "migrations")),
    (os.path.join(PROJ, "static"), "static"),
]:
    if os.path.isdir(src_dir):
        for root, _dirs, files in os.walk(src_dir):
            for f in files:
                full = os.path.join(root, f)
                # destination: preserve relative structure under dst_dir
                rel = os.path.relpath(root, src_dir)
                dest = dst_dir if rel == "." else os.path.join(dst_dir, rel)
                project_data.append((full, dest))

# ── collect Django admin static / template files ─────────────────────────
# These live inside the installed Django package and aren't auto-discovered
# as Python imports, so we collect them as plain data.
django_data = []
for contrib_app in ["admin", "auth"]:
    try:
        django_data.extend(collect_data_files(f"django.contrib.{contrib_app}"))
    except Exception:
        pass

# ── collect Django conf (locale, urls, etc.) ─────────────────────────────
try:
    django_data.extend(collect_data_files("django.conf"))
except Exception:
    pass

# ── collect ReportLab fonts/encodings (invoice PDFs) ──────────────────────
try:
    django_data.extend(collect_data_files("reportlab"))
except Exception:
    pass

all_data = project_data + django_data

# ── hidden imports ───────────────────────────────────────────────────────
# Django lazily imports many modules; tell PyInstaller about them all.
hiddenimports = collect_submodules("django")

# Our own modules
hiddenimports += [
    "frontoffice",
    "frontoffice.settings",
    "frontoffice.urls",
    "frontoffice.wsgi",
    "sales",
    "sales.apps",
    "sales.models",
    "sales.views",
    "sales.views_admin",
    "sales.forms",
    "sales.admin",
    "sales.urls",
    "sales.management",
    "sales.management.commands",
    "sales.management.commands.seed_items",
]

# pywebview internals
hiddenimports += collect_submodules("webview")

# SQLite (bundled Python sqlite3 C extension)
hiddenimports += ["sqlite3"]

# Waitress (pure-Python WSGI server for multithreading)
hiddenimports += ["waitress"]

# ReportLab (pure-Python PDF generation for customer invoices)
hiddenimports += collect_submodules("reportlab")

# ── analysis ─────────────────────────────────────────────────────────────
a = Analysis(
    [os.path.join(PROJ, "build_entry.py")],
    pathex=[PROJ],
    binaries=[],
    datas=all_data,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # strip out things we definitely don't need to shrink the exe
        "tkinter",
        "tcl",
        "tk",
        "ipython",
        "jupyter",
        "notebook",
        "matplotlib",
        "pandas",
        "numpy",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="MEATMAGIC",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
