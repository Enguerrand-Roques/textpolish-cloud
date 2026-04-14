# TextPolish Cloud configuration
# Copy this file to config.py and fill in your own values.

# Google Gemini API key — get one free at https://aistudio.google.com
GEMINI_API_KEY = "YOUR_GEMINI_API_KEY_HERE"

# Model to use (gemini-2.5-flash-lite is free and fast)
GEMINI_MODEL = "gemini-2.5-flash-lite"

# Global keyboard shortcut (pynput format)
# macOS: <cmd> = Command key
SHORTCUT = "<cmd>+<shift>+p"

# Windows override — Ctrl+Shift+P conflicts with many apps (VS Code, browsers…)
# Uses <ctrl>+<alt>+p by default. Set to None to fall back to SHORTCUT.
SHORTCUT_WINDOWS = "<ctrl>+<alt>+p"
