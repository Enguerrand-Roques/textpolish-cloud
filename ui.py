import sys

if sys.platform == "darwin":
    from ui_macos import setup, TextPolishPanel  # noqa: F401
elif sys.platform == "win32":
    from ui_windows import setup, TextPolishPanel  # noqa: F401
else:
    raise RuntimeError(f"Unsupported platform: {sys.platform}")
