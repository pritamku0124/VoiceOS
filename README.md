# VoiceOS

A voice-controlled assistant for Windows 11. Speak naturally ("open WhatsApp and minimize Chrome") and VoiceOS turns it into safe, validated actions on your real desktop. Everything runs locally: speech recognition, AI and text-to-speech.

> **Status: Phase 6 of 11.** Say **"Hi Jarvis"** (or click the mic, press Ctrl+Space, or type) and VoiceOS **does it**: opens and switches apps, manages windows, clicks, scrolls, types, opens websites and searches, controls media and volume, checks the battery and opens Settings. Closing apps and locking ask first. Files, exact volume levels and screenshots come in Phase 7. Everything runs offline. Esc stops. AI understanding and Windows automation arrive in later phases (see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)).

## Quick start

From PowerShell in the project folder (`D:\project\VoiceOS`):

```powershell
.\scripts\setup_environment.ps1     # one time: creates .venv and installs packages
.\.venv\Scripts\python.exe scripts\download_speech_model.py   # one time: offline speech model (~40 MB)
.\.venv\Scripts\python.exe scripts\download_wake_word_model.py  # one time: "Hi Jarvis" models (~3.5 MB)
.\scripts\start_voiceos.ps1         # start the app
```

Or step by step with the virtual environment activated:

```powershell
.\.venv\Scripts\Activate.ps1
python main.py                      # start VoiceOS
python main.py --smoke-test         # start, then close after 3 s
python -m pytest                    # run the tests
python scripts\check_environment.py # what's installed / what's missing
python scripts\check_microphone.py --level 5   # live mic volume meter
python scripts\check_microphone.py --recognize # say one command in the terminal
python scripts\check_microphone.py --say "Hello"  # test the speakers / voice
python scripts\check_microphone.py --wake 20      # live "Hi Jarvis" scores
```

## Documentation

| Doc | What's inside |
|---|---|
| [ARCHITECTURE](docs/ARCHITECTURE.md) | How the pieces fit together; the 11 phases |
| [INSTALLATION](docs/INSTALLATION.md) | Requirements, setup, compatibility notes |
| [DEVELOPMENT](docs/DEVELOPMENT.md) | Daily workflow, tests, conventions |
| [LEARNING_LOG](docs/LEARNING_LOG.md) | What was built and learned in each phase |

## Safety principles

The AI never runs code. It can only choose from an allowlist of actions, with validated parameters. Destructive or sensitive actions require confirmation. An emergency stop halts everything. The microphone indicator is always visible.

## License

MIT
