import sys

if sys.platform == "darwin":
    from hotkey_macos import install  # noqa: F401
elif sys.platform == "win32":
    from hotkey_windows import install  # noqa: F401
else:
    raise RuntimeError(f"Unsupported platform: {sys.platform}")
