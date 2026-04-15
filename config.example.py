# TextPolish Cloud configuration
# Copy this file to config.py and fill in your own values.

# Google Gemini API key — get one free at https://aistudio.google.com
GEMINI_API_KEY = "YOUR_GEMINI_API_KEY_HERE"

# Model to use (gemini-2.5-flash-lite is free and fast)
GEMINI_MODEL = "gemini-2.5-flash-lite"

# Global keyboard shortcut (pynput format)
# macOS: Cmd+Option+G  |  Windows: Ctrl+Alt+G  (no known conflicts)
SHORTCUT = "<cmd>+<alt>+g"

# Windows override — uses SHORTCUT with <cmd> replaced by <ctrl> by default.
# Override here if needed.
SHORTCUT_WINDOWS = "<ctrl>+<alt>+g"
