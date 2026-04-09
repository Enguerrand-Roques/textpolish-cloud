#!/bin/bash
# TextPolish Cloud — one-command setup
set -e

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
LABEL="com.user.textpolish-cloud"
PLIST_PATH="$HOME/Library/LaunchAgents/${LABEL}.plist"
APP="$HOME/Desktop/TextPolishCloud.app"

echo "Setting up TextPolish Cloud..."

# ── 1. Python venv ──────────────────────────────────────────────────────────
if [ ! -d "$REPO_DIR/venv" ]; then
    python3 -m venv "$REPO_DIR/venv"
fi
"$REPO_DIR/venv/bin/pip" install -q --upgrade pip
"$REPO_DIR/venv/bin/pip" install -q -r "$REPO_DIR/requirements.txt"
echo "  ✓ Dependencies installed"

# ── 2. Detect the real Python binary (bypass venv symlink for launchd) ──────
REAL_PYTHON=$(python3 -c "
import sysconfig, os
exe = sysconfig.get_config_var('BINDIR') + '/python3'
print(os.path.realpath(exe))
" 2>/dev/null || python3 -c "import sys; print(sys.executable)")

SITE_PACKAGES="$REPO_DIR/venv/lib/$(ls "$REPO_DIR/venv/lib/")/site-packages"

# ── 3. Config ────────────────────────────────────────────────────────────────
if [ ! -f "$REPO_DIR/config.py" ]; then
    cp "$REPO_DIR/config.example.py" "$REPO_DIR/config.py"
    echo "  ✓ config.py created"
    echo ""
    echo "  ⚠️  Open config.py and paste your Gemini API key before starting."
    echo "  Get a free key at: https://aistudio.google.com"
    echo ""
else
    echo "  ✓ config.py already exists"
fi

# ── 4. LaunchAgent plist ─────────────────────────────────────────────────────
mkdir -p "$HOME/Library/LaunchAgents"
cat > "$PLIST_PATH" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${LABEL}</string>
    <key>ProgramArguments</key>
    <array>
        <string>${REAL_PYTHON}</string>
        <string>${REPO_DIR}/main.py</string>
    </array>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PYTHONPATH</key>
        <string>${SITE_PACKAGES}</string>
    </dict>
    <key>RunAtLoad</key>
    <false/>
    <key>KeepAlive</key>
    <false/>
    <key>StandardOutPath</key>
    <string>/tmp/textpolish-cloud.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/textpolish-cloud.log</string>
</dict>
</plist>
EOF
launchctl bootout "gui/$(id -u)/${LABEL}" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST_PATH"
echo "  ✓ LaunchAgent registered"

# ── 5. TextPolishCloud.app on Desktop ─────────────────────────────────────────
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"

cat > "$APP/Contents/MacOS/TextPolishCloud" << 'SCRIPT'
#!/bin/bash
LABEL="com.user.textpolish-cloud"
UID_VAL=$(id -u)
PLIST="$HOME/Library/LaunchAgents/${LABEL}.plist"
if ! launchctl print "gui/${UID_VAL}/${LABEL}" > /dev/null 2>&1; then
    launchctl bootstrap "gui/${UID_VAL}" "$PLIST"
fi
launchctl kickstart "gui/${UID_VAL}/${LABEL}"
SCRIPT
chmod +x "$APP/Contents/MacOS/TextPolishCloud"

cat > "$APP/Contents/Info.plist" << 'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key>
    <string>TextPolishCloud</string>
    <key>CFBundleIdentifier</key>
    <string>com.user.textpolish-cloud</string>
    <key>CFBundleName</key>
    <string>TextPolish Cloud</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleVersion</key>
    <string>1.0</string>
    <key>LSUIElement</key>
    <true/>
</dict>
</plist>
PLIST

find "$APP" -exec xattr -c {} \; 2>/dev/null
codesign --force --deep --sign - "$APP" 2>/dev/null || true
echo "  ✓ TextPolishCloud.app created on Desktop"

echo ""
echo "All done! What's next:"
echo "  1. Edit config.py and set your GEMINI_API_KEY"
echo "     (get a free key at https://aistudio.google.com)"
echo "  2. Double-click TextPolishCloud.app on your Desktop"
echo "  3. Look for the ✏️ icon in your menubar"
echo "  4. Select text anywhere, press Cmd+Shift+P"
echo ""
echo "First launch: macOS may ask for Accessibility permission — grant it in System Settings."
