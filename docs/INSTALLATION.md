# Installation

## Requirements

- Windows 10 or 11 (64-bit)
- Python 3.11+ (developed on **3.14.10**)
- About 300 MB free for Phase 1; later phases add speech/AI models (100 MB – 2 GB)
- Microphone (Phase 2+)
- [Ollama](https://ollama.com) (Phase 5+)

## Setup

```powershell
cd D:\project\VoiceOS
.\scripts\setup_environment.ps1
```

This creates `.venv` (a private Python environment for this project only), installs `requirements-dev.txt`, and runs `scripts\check_environment.py`.

**If PowerShell refuses to run the script** ("running scripts is disabled on this system"), allow scripts for your user only. This changes a per-user policy, not a system-wide one:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

## Local AI (Phase 5)

Install Ollama (official package via winget) and the small model:

```powershell
winget install --id Ollama.Ollama --exact
ollama pull qwen2.5:1.5b
```

No sign-in is needed. Ollama runs in the system tray and VoiceOS talks to it on `http://localhost:11434`, which must stay local; VoiceOS refuses any other address. Without Ollama, VoiceOS still understands the common commands through its built-in rules.

## Python 3.14 compatibility (checked 2026-11-12)

Every planned dependency publishes a Windows wheel usable on Python 3.14, so no second Python install is needed:

| Package | Version | Wheel type | Phase |
|---|---|---|---|
| PySide6-Essentials | 6.12.0 | abi3 win_amd64 | 1 |
| pytest | 9.2.0 | pure Python | 1 |
| sounddevice | 0.5.6 | pure Python (bundles PortAudio) | 2 |
| numpy | 2.5.4 | cp314 win_amd64 | 2 |
| vosk | 0.3.45 | py3 win_amd64 | 2 |
| webrtcvad-wheels | 2.0.14.post1 | cp314 win_amd64 | 2 |
| faster-whisper / ctranslate2 | 1.2.1 / 4.9.0 | pure / cp314 | 2 (optional) |
| comtypes | 1.5.0 | pure Python | 3 |
| ~~piper-tts~~ | 1.8.0 | abi3 win_amd64 — **installs, but Smart App Control blocks its DLL** | 3 (not used) |
| openwakeword / onnxruntime | 0.6.0 / 1.31.1 | pure / cp314 — onnxruntime **loads OK** under Smart App Control | 4 |
| ollama | 0.6.3 | pure Python | 5 |
| pydantic | 2.14.3 | pure (+ compiled core) | 5 |
| pywin32 | 312 | cp314 win_amd64 | 6 |
| pyautogui | 0.9.54 | source only, pure Python | 6 |
| psutil | 7.2.2 | cp314 win_amd64 | 6 |
| pycaw | 20260927 | pure Python | 7 |

**Second compatibility check: Smart App Control.** A wheel existing for Python 3.14 isn't enough. Windows 11's Smart App Control refuses to load unsigned native DLLs it doesn't recognise. Phase 3 found this out with Piper. Before adopting a package with compiled parts, run `python -c "import <package>"` inside `.venv` and watch for *"An Application Control policy has blocked this file"*. Already checked and OK: PySide6, sounddevice, numpy, vosk, webrtcvad, onnxruntime.

"Wheel" = a pre-built package. *cp314* wheels are built for Python 3.14 specifically; *abi3* wheels work on any Python 3 from a minimum version; *pure Python* packages work everywhere. If a package only offers a source archive with C code, pip must compile it, which needs Visual Studio Build Tools. We avoid those.

## Hardware notes for this machine

- ~7.3 GB RAM. Choose small models: Vosk small English (~40 MB), Whisper *base*, and LLMs around 1–3B parameters.
- AMD Radeon integrated graphics, no NVIDIA CUDA. All AI runs on the CPU, which is fine at these model sizes.
