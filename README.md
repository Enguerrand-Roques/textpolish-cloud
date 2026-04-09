# TextPolish Cloud

**TextPolish Cloud** is a macOS menubar utility that polishes your text using Google Gemini. Select any text in any app, press a shortcut, choose a rewrite mode — the corrected text is pasted back instantly.

No local model required. Just a free Gemini API key.

---

## How It Works

1. Select text in any macOS app
2. Press `Cmd+Shift+P`
3. Pick a mode — **Professional**, **Casual**, or **Custom**
4. The rewritten text is automatically pasted back

TextPolish Cloud runs silently in the menubar. No Dock icon, no Terminal window.

---

## Requirements

- macOS 13+
- Python 3.13
- A **free** Google Gemini API key → [Get one at aistudio.google.com](https://aistudio.google.com)
- macOS **Accessibility** permission (for the global shortcut and clipboard automation)

---

## Installation

```bash
git clone https://github.com/Enguerrand-Roques/textpolish-cloud.git
cd textpolish-cloud
bash setup.sh
```

`setup.sh` handles everything automatically:
- Creates the Python virtual environment
- Installs dependencies
- Creates `config.py` from the template
- Registers the macOS Launch Agent
- Creates **TextPolishCloud.app** on your Desktop

Then open `config.py` and paste your Gemini API key:

```python
GEMINI_API_KEY = "your-key-here"
```

---

## Daily Use

**Start:** Double-click **TextPolishCloud.app** on your Desktop.  
A ✏️ icon appears in the menubar — that means it's running.

**Stop:** Click the ✏️ icon → **Quit TextPolish Cloud**.

**Auto-start on login:** In `~/Library/LaunchAgents/com.user.textpolish-cloud.plist`, set `RunAtLoad` to `<true/>`, then re-run `bash setup.sh`.

---

## Configuration

Edit `config.py` (excluded from Git):

```python
GEMINI_API_KEY = "your-key-here"
GEMINI_MODEL   = "gemini-2.5-flash-lite"   # free and fast
SHORTCUT       = "<cmd>+<shift>+p"
```

Available models (all free tier):
- `gemini-2.5-flash-lite` — fastest, recommended
- `gemini-2.5-flash` — higher quality, slightly slower
- `gemini-2.0-flash` — good alternative

---

## macOS Permissions

On first launch, macOS will ask for:

- **Accessibility** — required for the global shortcut and simulated copy/paste
- **Input Monitoring** — may be requested alongside Accessibility

Grant both in **System Settings → Privacy & Security**.

---

## Rewrite Modes

| Mode | Description |
|------|-------------|
| Professional | Full rewrite for emails, reports, LinkedIn posts |
| Casual | Light typo fix, keeps your tone (SMS, WhatsApp, DMs) |
| Custom | Free-form instruction you type in the panel |

---

## Project Structure

```
textpolish-cloud/
├── main.py          # Cocoa app bootstrap and event loop
├── ui.py            # NSPanel UI + menubar status item
├── hotkey.py        # Global shortcut via CGEventTap
├── clipboard.py     # Selected text capture and paste-back
├── llm.py           # Gemini request layer
├── prompts/         # Prompt templates (pro, casual, custom)
├── config.py        # Local config — excluded from Git
├── config.example.py
└── setup.sh         # One-command installer
```

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `Invalid API key` | Double-check your key in `config.py` |
| Shortcut not detected | Grant Accessibility in System Settings |
| Text not pasted back | Keep the source app focused; allow clipboard permissions |
| App won't start | Check `/tmp/textpolish-cloud.log` for errors |

---

## Related

- [TextPolish](https://github.com/Enguerrand-Roques/textpolish) — same tool, runs fully offline with a local Ollama model
