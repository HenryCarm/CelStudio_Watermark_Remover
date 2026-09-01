import os

lines = open("MS WR S6.py.bak", "r", encoding="utf-8").read().replace("_BaseCanvas", "BaseCanvas").splitlines()

imports = []
in_imports = False
in_qtgui = False
for i, line in enumerate(lines):
    if line.startswith("import sys, os, json"):
        in_imports = True
    if in_imports:
        imports.append(line)
        if "from PySide6.QtGui import" in line:
            in_qtgui = True
        if in_qtgui and line.startswith(")"):
            break
import_block = "\n".join(imports) + "\n\n"

def get_section(start_str):
    start_idx = -1
    for i, line in enumerate(lines):
        if line.startswith(start_str):
            start_idx = i
            break
    if start_idx == -1: return ""
    
    end_idx = len(lines)
    for i in range(start_idx + 1, len(lines)):
        if lines[i].startswith("# ─── "):
            end_idx = i
            break
    return "\n".join(lines[start_idx:end_idx]) + "\n\n"

def get_sections(titles):
    return "\n".join(get_section(t).strip() for t in titles) + "\n\n"

os.makedirs("core", exist_ok=True)
os.makedirs("ui", exist_ok=True)

with open("core/constants.py", "w", encoding="utf-8") as f:
    f.write(import_block)
    f.write(get_sections(["# ─── Paths", "# ─── Colors"]))

with open("core/settings_manager.py", "w", encoding="utf-8") as f:
    f.write(import_block)
    f.write("from .constants import *\n\n")
    f.write(get_sections(["# ─── Settings"]))

with open("core/logger.py", "w", encoding="utf-8") as f:
    f.write(import_block)
    f.write("from .constants import *\nfrom .settings_manager import *\n\n")
    f.write(get_sections(["# ─── Live Diagnostics & Crash Logger"]))

with open("core/utils.py", "w", encoding="utf-8") as f:
    f.write(import_block)
    f.write("from .constants import *\nfrom .settings_manager import *\n\n")
    f.write(get_sections(["# ─── Mask encode/decode"]))
    
with open("core/engine.py", "w", encoding="utf-8") as f:
    f.write(import_block)
    f.write("from .constants import *\nfrom .settings_manager import *\nfrom .logger import *\nfrom .utils import *\n\n")
    f.write(get_sections(["# ─── Smart Watermark Detection", "# ─── Inpaint", "# ─── Workers"]))

with open("core/__init__.py", "w", encoding="utf-8") as f:
    f.write("from .constants import *\nfrom .settings_manager import *\nfrom .logger import *\nfrom .utils import *\nfrom .engine import *\n")

with open("ui/theme.py", "w", encoding="utf-8") as f:
    f.write(import_block)
    f.write("from core import *\n\n")

with open("ui/canvas.py", "w", encoding="utf-8") as f:
    f.write(import_block)
    f.write("from core import *\n\n")
    f.write(get_sections(["# ─── Base Canvas", "# ─── Image Canvas", "# ─── Video Canvas"]))

with open("ui/components.py", "w", encoding="utf-8") as f:
    f.write(import_block)
    f.write("from core import *\n\n")
    f.write(get_sections(["# ─── HelpBubble", "# ─── KeyCapture button", "# ─── Compact tool button"]))

with open("ui/dialogs.py", "w", encoding="utf-8") as f:
    f.write(import_block)
    f.write("from core import *\nfrom .components import *\n\n")
    f.write(get_sections(["# ─── Settings dialog", "# ─── Preset save dialog", "# ─── About dialog"]))

with open("ui/panels.py", "w", encoding="utf-8") as f:
    f.write(import_block)
    f.write("from core import *\nfrom .components import *\n\n")
    f.write(get_sections(["# ─── Presets panel (slide-out)", "# ─── Tasks & Background Queue (\"Files In Progress\")"]))

with open("ui/tabs.py", "w", encoding="utf-8") as f:
    f.write(import_block)
    f.write("from core import *\nfrom .canvas import *\nfrom .components import *\n\n")
    f.write(get_sections(["# ─── Video Tab", "# ─── Gallery"]))

with open("ui/main_window.py", "w", encoding="utf-8") as f:
    f.write(import_block)
    f.write("from core import *\nfrom .canvas import *\nfrom .dialogs import *\nfrom .panels import *\nfrom .tabs import *\nfrom .components import *\n\n")
    f.write(get_sections(["# ─── Main Window"]))

with open("ui/__init__.py", "w", encoding="utf-8") as f:
    f.write("from .theme import *\nfrom .components import *\nfrom .canvas import *\nfrom .dialogs import *\nfrom .panels import *\nfrom .tabs import *\nfrom .main_window import *\n")

bootstrap = []
for line in lines:
    bootstrap.append(line)
    if line.startswith("# ───────────"):
        break

with open("main.py", "w", encoding="utf-8") as f:
    f.write("\n".join(bootstrap) + "\n\n")
    f.write(import_block)
    f.write("from core import *\nfrom ui import *\n\n")
    f.write(get_sections(["# ─── Entry point"]))
    
print("Splitting complete!")
