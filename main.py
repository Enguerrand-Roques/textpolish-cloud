import sys

if sys.platform == "darwin":
    from platforms.macos.main import main
elif sys.platform == "win32":
    from platforms.windows.main import main
else:
    raise RuntimeError(f"Unsupported platform: {sys.platform}")

if __name__ == "__main__":
    main()
