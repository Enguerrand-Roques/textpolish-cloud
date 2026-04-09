# TextPolish Cloud

**TextPolish Cloud** polishes your text using Google Gemini — free, fast, no local model needed.

Select any text in any app, press `Cmd+Shift+P` (macOS) or `Ctrl+Shift+P` (Windows), pick a rewrite mode, and the corrected text is pasted back instantly. TextPolish Cloud runs silently in the menubar / system tray.

> **Prefer a fully offline version?** → [TextPolish](https://github.com/Enguerrand-Roques/textpolish) uses a local Ollama model — no internet required.

---

## Requirements

| | macOS | Windows |
|---|---|---|
| OS | macOS 13+ | Windows 10+ |
| Python | 3.13 | 3.11+ |
| API key | Free Gemini key | Free Gemini key |
| Permission | Accessibility | — |

**Get a free Gemini API key** (no credit card): [aistudio.google.com](https://aistudio.google.com) → Sign in → Get API key. Takes 30 seconds.

---

## Installation

### macOS

```bash
git clone https://github.com/Enguerrand-Roques/textpolish-cloud.git
cd textpolish-cloud
bash setup.sh
```

`setup.sh` does everything automatically:
- Creates the Python virtual environment and installs dependencies
- Copies `config.example.py` → `config.py`
- Registers the macOS Launch Agent
- Creates **TextPolishCloud.app** on your Desktop

Then open `config.py` and paste your API key:

```python
GEMINI_API_KEY = "your-key-here"
```

**Start the app:** double-click **TextPolishCloud.app** on your Desktop. A ✏️ icon appears in the menubar.

---

### Windows

```bash
git clone https://github.com/Enguerrand-Roques/textpolish-cloud.git
cd textpolish-cloud
python -m venv venv
venv\Scripts\activate
pip install -r requirements-windows.txt
copy config.example.py config.py
```

Open `config.py` and paste your API key:

```python
GEMINI_API_KEY = "your-key-here"
```

**Start the app:**

```bash
python main.py
```

A ✏️ icon appears in the system tray.

---

## Configuration

Edit `config.py` (excluded from Git):

```python
GEMINI_API_KEY = "your-key-here"
GEMINI_MODEL   = "gemini-2.5-flash-lite"   # free and fast (recommended)
SHORTCUT       = "<cmd>+<shift>+p"         # becomes Ctrl+Shift+P on Windows automatically
```

Available models (all free tier):

| Model | Speed | Quality |
|-------|-------|---------|
| `gemini-2.5-flash-lite` | Fastest | Good — recommended |
| `gemini-2.5-flash` | Fast | Better |
| `gemini-2.0-flash` | Fast | Good alternative |

---

## How to use

1. Select text in **any app** (browser, Word, Slack, Notes…)
2. Press `Cmd+Shift+P` (macOS) or `Ctrl+Shift+P` (Windows)
3. A small panel appears — pick a mode:

| Mode | Best for |
|------|----------|
| **Professional** | Emails, reports, LinkedIn, formal writing |
| **Casual** | SMS, WhatsApp, DMs — light touch, keeps your tone |
| **Custom** | Any free-form instruction you type |

4. The rewritten text is pasted back automatically

---

## macOS Permissions

On first launch, macOS will ask for:

- **Accessibility** — required for the global shortcut and simulated copy/paste
- **Input Monitoring** — may appear alongside Accessibility

Grant both in **System Settings → Privacy & Security**.

---

## Auto-start on login (macOS)

In `~/Library/LaunchAgents/com.user.textpolish-cloud.plist`, set `RunAtLoad` to `<true/>`, then reload:

```bash
launchctl bootout gui/$(id -u) com.user.textpolish-cloud
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.user.textpolish-cloud.plist
```

---

## Project Structure

```
textpolish-cloud/
├── main.py              # Entry point — detects OS and starts the right backend
├── clipboard.py         # Copy / paste logic — shared across platforms
├── llm.py               # Google Gemini request layer — shared across platforms
├── prompts/             # Prompt templates (pro, casual, custom)
├── config.py            # Your local config — excluded from Git
├── config.example.py    # Config template to copy
│
├── platforms/
│   ├── macos/           # macOS-specific code (PyObjC, NSPanel, CGEventTap)
│   │   ├── ui.py        #   Native floating panel + menubar icon
│   │   ├── main.py      #   Cocoa event loop
│   │   └── hotkey.py    #   Global shortcut via CGEventTap
│   └── windows/         # Windows-specific code (PyQt6, QSystemTrayIcon)
│       ├── ui.py        #   Qt floating window + system tray icon
│       ├── main.py      #   Qt event loop
│       └── hotkey.py    #   Global shortcut via pynput
│
├── requirements.txt         # macOS dependencies
└── requirements-windows.txt # Windows dependencies
```

`main.py` is the only entry point. It reads `sys.platform` and loads the right implementation from `platforms/`. Everything in the root is shared between both platforms.

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `Invalid API key` | Double-check your key in `config.py` — no extra spaces |
| `API quota exceeded` | Free tier: 1 500 requests/day. Wait until tomorrow or switch model |
| Shortcut not working (macOS) | Grant Accessibility in System Settings |
| Text not pasted back | Keep the source app focused; check clipboard permissions |
| App won't start (macOS) | Check `/tmp/textpolish-cloud.log` for errors |

---

## Related

- [TextPolish](https://github.com/Enguerrand-Roques/textpolish) — same tool, runs fully offline with a local Ollama model
