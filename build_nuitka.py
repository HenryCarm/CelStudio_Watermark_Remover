#!/usr/bin/env python3
"""
MyScreen Watermark Remover - Nuitka Packaging Script
Builds ultra-optimized Standalone and OneFile distributions.
"""

import sys
import os
import shutil
import subprocess
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
VENV_PYTHON = Path("/home/henry/Documents/Projects/Python/venv/bin/python")
MAIN_SCRIPT = PROJECT_DIR / "main.py"
ICON_FILE   = PROJECT_DIR / "icon.png"
DIST_DIR    = PROJECT_DIR / "dist"
APP_NAME    = "CelStudio Watermark Remover"

# Unneeded modules to prune aggressively for size reduction
EXCLUDE_MODULES = [
    "tkinter", "unittest", "pydoc", "doctest", "email", "http", "xmlrpc",
    "distutils", "setuptools", "pip", "pkg_resources", "curses", "idlelib",
    "turtledemo", "sqlite3", "scipy", "matplotlib", "pandas", "torch",
    "tensorflow", "PIL.ImageTk", "PIL.SpiderImagePlugin", "PIL.FitsImagePlugin",
    "PIL.MpoImagePlugin", "PIL.PdfImagePlugin",
    # Unneeded PySide6 modules (pruned for minimal binary size)
    "PySide6.QtNetwork", "PySide6.QtSql", "PySide6.QtQml", "PySide6.QtQuick",
    "PySide6.QtOpenGL", "PySide6.QtSvg", "PySide6.QtTest", "PySide6.QtXml",
    "PySide6.QtDesigner", "PySide6.QtHelp", "PySide6.QtPdf", "PySide6.QtPrintSupport",
    "PySide6.QtBluetooth", "PySide6.QtPositioning", "PySide6.QtSensors", "PySide6.QtNfc"
]

def build(target="onefile"):
    """
    target: 'onefile' or 'standalone'
    """
    if not VENV_PYTHON.exists():
        print(f"❌ Error: Central venv python not found at {VENV_PYTHON}")
        sys.exit(1)

    DIST_DIR.mkdir(parents=True, exist_ok=True)

    cmd = [
        str(VENV_PYTHON), "-m", "nuitka",
        f"--{target}",
        "--enable-plugin=pyside6",
        "--include-qt-plugins=sensible",
        "--enable-plugin=upx",
        f"--output-dir={DIST_DIR}",
        f"--output-filename=CelStudio_Watermark_Remover{'_onefile' if target == 'onefile' else ''}",
        f"--include-data-file={ICON_FILE}=icon.png",
        f"--include-data-file={PROJECT_DIR / 'wallpaper.webp'}=wallpaper.webp",
        f"--include-data-file={PROJECT_DIR / 'banner.png'}=banner.png",
        f"--linux-icon={ICON_FILE}",
        "--assume-yes-for-downloads",
        "--remove-output",
        "--clang",
        "--lto=yes",
        "--python-flag=-OO",
        "--prefer-source-code",
        "--deployment",
        "--noinclude-unittest-mode=nofollow",
        "--noinclude-setuptools-mode=nofollow",
        "--windows-console-mode=disable",
    ]

    # Add nofollow exclusions
    for mod in EXCLUDE_MODULES:
        cmd.append(f"--nofollow-import-to={mod}")

    cmd.append(str(MAIN_SCRIPT))

    print(f"\n🚀 Starting Nuitka {APP_NAME} {target.upper()} build...")
    print(f"📦 Command: {' '.join(cmd)}\n")

    res = subprocess.run(cmd, cwd=str(PROJECT_DIR))
    if res.returncode == 0:
        print(f"\n🎉 {APP_NAME} {target.upper()} build finished successfully in {DIST_DIR}!")
    else:
        print(f"\n❌ {APP_NAME} build failed with exit code {res.returncode}")

def spawn_external_terminal(mode="both"):
    """Spawns an external terminal so Henny can watch the compilation progress in real-time."""
    cmd_str = f"cd '{PROJECT_DIR}' && '{VENV_PYTHON}' build_nuitka.py --run={mode} ; exec bash"
    try:
        subprocess.Popen(['gnome-terminal', '--', 'bash', '-c', cmd_str])
        print(f"🚀 Spawned GNOME Terminal for {APP_NAME} live compilation monitoring!")
    except FileNotFoundError:
        try:
            subprocess.Popen(['x-terminal-emulator', '-e', f'bash -c "{cmd_str}"'])
            print(f"🚀 Spawned x-terminal-emulator for {APP_NAME} live compilation monitoring!")
        except FileNotFoundError:
            try:
                subprocess.Popen(['konsole', '-e', f'bash -c "{cmd_str}"'])
                print(f"🚀 Spawned Konsole for {APP_NAME} live compilation monitoring!")
            except FileNotFoundError:
                print("⚠️ No GUI terminal emulator found. Running inline...")
                if mode in ("onefile", "both"):
                    build("onefile")
                if mode in ("standalone", "both"):
                    build("standalone")

def interactive_menu():
    """Displays an interactive selection prompt when no CLI flags are passed."""
    print(f"\n✨ =========================================")
    print(f"📦  {APP_NAME} - Nuitka Packaging Menu")
    print(f"✨ =========================================")
    print("  [1] OneFile only      (Single portable executable)")
    print("  [2] Standalone only   (Folder with .so files - instant launch)")
    print("  [3] Both              (Build OneFile + Standalone back-to-back)")
    print("  [4] Spawn Terminal    (Launch build in separate GNOME Terminal window)")
    print("  [0 / q] Cancel")
    
    try:
        choice = input("\n👉 Select an option [1-4 / q] (default: 3): ").strip().lower()
    except (KeyboardInterrupt, EOFError):
        print("\n👋 Build cancelled.")
        sys.exit(0)
        
    if choice in ("", "3", "both"):
        build("onefile")
        build("standalone")
    elif choice in ("1", "onefile"):
        build("onefile")
    elif choice in ("2", "standalone"):
        build("standalone")
    elif choice in ("4", "spawn"):
        spawn_external_terminal("both")
    elif choice in ("0", "q", "exit", "quit"):
        print("👋 Build cancelled.")
        sys.exit(0)
    else:
        print(f"❌ Invalid choice '{choice}'. Exiting.")
        sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) == 1:
        interactive_menu()
    elif "--run=onefile" in sys.argv:
        build("onefile")
    elif "--run=standalone" in sys.argv:
        build("standalone")
    elif "--run=both" in sys.argv:
        build("onefile")
        build("standalone")
    elif "--spawn" in sys.argv:
        target = "both"
        for arg in sys.argv:
            if arg.startswith("--target="):
                target = arg.split("=", 1)[1]
        spawn_external_terminal(target)
    else:
        print("Usage:")
        print("  python build_nuitka.py                    (Interactive selection menu)")
        print("  python build_nuitka.py --run=onefile      (Builds single portable binary)")
        print("  python build_nuitka.py --run=standalone   (Builds fast folder distribution)")
        print("  python build_nuitka.py --run=both         (Builds both distributions)")
        print("  python build_nuitka.py --spawn            (Spawns live terminal window)")
