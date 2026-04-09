import sys

if sys.platform == "darwin":
    from main_macos import main
elif sys.platform == "win32":
    from main_windows import main
else:
    raise RuntimeError(f"Unsupported platform: {sys.platform}")

if __name__ == "__main__":
    main()
