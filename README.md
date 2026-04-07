# TextPolish Cloud

TextPolish Cloud is a macOS menubar helper that grabs the currently selected text, sends it to Google Gemini for rewriting, and pastes the polished version back into the active app.

It keeps the native macOS flow from the original TextPolish project while replacing the local Ollama backend with a cloud-based Gemini API call.

## Features

- Global macOS shortcut to trigger rewriting
- Native `NSPanel` UI that stays visible above fullscreen apps
- Google Gemini backend via `google-genai`
- Prompt modes in `prompts/` (`pro`, `casual`, `custom`)
- Clipboard-based capture and paste workflow

## Requirements

- macOS
- Python 3.13 recommended
- A Google Gemini API key from https://aistudio.google.com
- Accessibility permission for the global hotkey and copy/paste automation

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp config.example.py config.py
```

Then edit `config.py` and set your Gemini API key.

## Configuration

Example configuration:

```python
GEMINI_API_KEY = "YOUR_GEMINI_API_KEY_HERE"
GEMINI_MODEL = "gemini-2.5-flash-lite"
SHORTCUT = "<cmd>+<shift>+p"
```

Config values:

- `GEMINI_API_KEY`: required API key for Gemini
- `GEMINI_MODEL`: Gemini model used for rewriting
- `SHORTCUT`: global keyboard shortcut in `pynput` format

`config.py` is intentionally excluded from Git.

## Run

```bash
./run.sh
```

Or manually:

```bash
python3 main.py
```

When the app starts, use the configured shortcut to capture the selected text and open the panel.

## macOS Permissions

On first launch, make sure the terminal or Python app you use has:

- Accessibility permission
- Permission to control the keyboard / simulate copy-paste when prompted

Without these permissions, the global shortcut or paste-back step may fail.

## How It Works

1. Select text in any macOS app.
2. Press the configured shortcut.
3. TextPolish Cloud copies the current selection.
4. The text is sent to Gemini with the selected prompt mode.
5. The rewritten text is pasted back into the original app.

## Project Structure

- `main.py`: Cocoa app bootstrap and event loop
- `ui.py`: native `NSPanel` interface and rewrite actions
- `hotkey.py`: global hotkey listener based on Quartz `CGEventTap`
- `clipboard.py`: selected text capture and paste-back helpers
- `llm.py`: Gemini request layer
- `prompts/`: prompt templates for each rewrite mode
- `config.example.py`: example local configuration
- `run.sh`: bootstrap script that creates the virtualenv on first launch

## Notes

- `benchmark_models.py` is inherited from the original local-model project and is not yet migrated to the Gemini backend.
- No API key or local config file is committed in this repository.
