# VoiceOS Architecture

## The big picture

Every voice command flows through the same pipeline. Each box is a package folder.

```
 Microphone ──► voice/ ──────────► ai/ ─────────────► actions/ ──► safety/ ──► controllers/ ──► Windows
 (sound)        capture, VAD,      text → intent      allowlist +   risk check,   real mouse,
                wake word,         e.g. "open Chrome" schema +      permission,   keyboard,
                speech-to-text     → OPEN_APPLICATION validation    confirmation  windows, files
                                     {name:"Chrome"}
                                                                                       │
 Speaker ◄──── voice/text_to_speech ◄── ai/response_generator ◄──── result ◄───────────┘
```

`core/` orchestrates this flow. `services/` provides shared infrastructure (config, logging, database). `dashboard/` is the UI that shows it all.

## Why this layering?

| Layer | Knows about | Never does |
|---|---|---|
| `voice/` | audio, text | decide what to do |
| `ai/` | language, intents | touch Windows |
| `actions/` | the allowlist of what's permitted | run anything not in it |
| `safety/` | risk, permissions | carry out actions itself |
| `controllers/` | Windows APIs | make decisions |

The key safety idea: **the AI only produces data** (an intent name + parameters). That data is checked against a fixed allowlist and validated before any controller runs. AI output is never executed as code.

## Folder guide

| Folder | Role |
|---|---|
| `main.py` | Entry point. Parses options, starts `core.application`. |
| `core/` | Start-up, the assistant loop, routing intents to actions, global state. |
| `voice/` | Microphone, voice activity detection, wake word, speech-to-text, text-to-speech. |
| `ai/` | Ollama client, intent recognition/parsing, conversation context, replies. |
| `actions/` | Action registry (allowlist), schemas, validation, action definitions. |
| `safety/` | Command filter, risk classes, permissions, confirmations, emergency stop, audit log. |
| `controllers/` | Thin wrappers that perform real Windows operations. |
| `integrations/` | Adapters for external systems: Ollama, browsers, Win32 APIs. |
| `services/` | Config, logging, database, history, profiles, notifications. |
| `dashboard/` | PySide6 UI: main window, pages, widgets, dialogs, QSS styles. |
| `utils/` | Constants, exceptions, platform checks, small helpers. |
| `profiles/` | Preset setting bundles (default / developer / accessibility). |
| `scripts/` | Setup, environment checks, model downloads, build. |
| `tests/` | Pytest test suite. |
| `assets/` | Icons, sounds, fonts, downloaded models (models are git-ignored). |

Files that say *"Status: planned for Phase N"* are placeholders that show where future code goes.

## Phase 1 start-up sequence

```
main.py
  └─ VoiceOSApplication.setup()          core/application.py
       ├─ assert_supported_platform()     utils/platform_utils.py
       ├─ setup_logging()                 services/logging_service.py  → logs/voiceos.log
       ├─ ConfigService.load()            services/config_service.py   ← config.json
       ├─ QApplication + dark_theme.qss   dashboard/styles/
       └─ MainWindow(config)              dashboard/main_window.py
            ├─ Sidebar (nav buttons)
            └─ QStackedWidget
                 ├─ DashboardPage         dashboard/dashboard_page.py
                 │    ├─ MicrophoneButton dashboard/widgets/microphone_widget.py
                 │    └─ WaveformWidget   dashboard/widgets/waveform_widget.py
                 └─ PlaceholderPage × 5   (built in later phases)
  └─ VoiceOSApplication.run()  → app.exec() event loop
```

## Phase 2 voice pipeline

```
 GUI thread                              VoiceWorker thread                       PortAudio audio thread
 ──────────                              ──────────────────                       ──────────────────────
 mic button / Ctrl+Space
   └─► VoiceManager.toggle_listening ──► run_once()
                                           ├─ load Vosk model (first time)  [LOADING]
                                           ├─ Microphone.start() ─────────────────► AudioCapture._callback
                                           │                                        every 30 ms: bytes → queue
                                           ├─ loop: read_frame() ◄──────── queue ──┘
                                           │     ├─ level_changed ──► waveform     [LISTENING]  ● Mic on
                                           │     └─ UtteranceSegmenter.process()   (webrtcvad + noise floor)
                                           ├─ Microphone.stop()                    mic closed immediately
                                           ├─ VoskRecognizer.transcribe()          [PROCESSING]
                                           ├─ process_result()  (clean text, confidence check)
                                           └─ speech_recognized ──► "Recognized speech" card   [IDLE]
```

Signals emitted on the worker thread are queued by Qt and delivered on the GUI thread, which is the only thread allowed to touch widgets.

| File | Responsibility |
|---|---|
| `voice/audio_device_manager.py` | List microphones (default host API only) and resolve the configured one |
| `voice/audio_capture.py` | Raw 16 kHz mono int16 stream; the audio callback pushes 30 ms frames to a queue |
| `voice/microphone.py` | Device + stream behind a small interface (tests replace it with `FakeMicrophone`) |
| `voice/audio_processor.py` | RMS loudness, decibels, 0–1 meter value |
| `voice/noise_reduction.py` | Running background-noise estimate (moving average) |
| `voice/voice_activity_detection.py` | `UtteranceSegmenter`: start/end-of-speech state machine with pre-roll |
| `voice/speech_recognition.py` | `SpeechRecognizer` interface + `VoskRecognizer` + factory |
| `voice/speech_processor.py` | Filler removal, brand-name corrections, confidence gate → `ProcessedSpeech` |
| `voice/language_detection.py` | Language setting → model folder |
| `voice/voice_manager.py` | Background thread orchestration and Qt signals |
| `core/state_manager.py` | `AssistantState` enum |
| `dashboard/widgets/listening_indicator.py` | Top-bar mic pill: red exactly while LISTENING |

## Phase 3 speech output

```
 VoiceManager.speech_recognized ─► MainWindow.on_speech
                                     ├─ reply_for_speech()          ai/response_generator.py (simple rules for now)
                                     ├─ show_reply()  → "VoiceOS replied" card
                                     └─ SpeechOutput.say(reply) ──► queue ──► SpeechOutput worker thread
                                                                               ├─ TTSEngine.synthesize()  WindowsTTS (SAPI via COM)
                                                                               └─ AudioPlayer.play()      50 ms blocks, stoppable
 speaking_changed(True/False) ─► SPEAKING / IDLE state in the UI
```

**Never hear yourself:** `VoiceManager.run_once()` first calls `SpeechOutput.stop(wait=True)` when VoiceOS is talking, so the microphone only opens once the speakers are silent. Clicking the mic while VoiceOS talks therefore interrupts it ("barge-in"). **Esc** stops both speech and listening.

**Engines:** `TTSEngine` has two implementations. `WindowsTTS` (the default) is signed by Microsoft, so it works with Smart App Control. `PiperTTS` is optional, because Smart App Control blocks its unsigned DLL on this PC.

## Phase 4 wake word ("Hi Jarvis")

```
WakeWordLoop thread (only while the wake word is ON)
  ├─ VoiceOS speaking?  → keep the mic CLOSED, wait
  ├─ open mic           [WAKE_LISTENING]  purple "● Mic on - wake word"
  ├─ every 30 ms frame → WakeWordDetector.process()     (nothing is recognised or stored)
  │      melspectrogram.onnx → embedding_model.onnx → hey_jarvis_v0.1.onnx → score 0..1
  │      score ≥ threshold for `patience` chunks in a row → detected
  │      (mic button = manual trigger)
  ├─ capture command    [LISTENING]  red "● Mic on"     prefill = last 1.2 s (contains "hi jarvis")
  │      transcript only "hi jarvis"? → keep listening for the command once more
  ├─ close mic → recognise → strip "hi jarvis" → speech_recognized  [PROCESSING]
  └─ wait for the reply to be spoken → back to the top
```

| File | Responsibility |
|---|---|
| `voice/wake_word.py` | `WakeWordDetector` (three ONNX models via onnxruntime), `strip_wake_phrase`, model lookup |
| `voice/voice_manager.py` | `_wake_loop`, `_wait_for_wake_word`, `_wake_command`, plus push-to-talk `run_once` |
| `scripts/download_wake_word_model.py` | Fetches the three model files (~3.5 MB) |

We don't use the `openwakeword` *package*, only its models and its documented inference steps. Importing the package also imports scipy and scikit-learn, which are only needed for training.

## Phase 5 understanding commands

```
text (spoken or typed)
  └─ Assistant.submit()  ──► background worker (ThreadPoolExecutor, 1 thread, in order)
       ├─ IntentRecognizer
       │    ├─ 1. rules (ai/intent_recognition.py)  ~60 regex rules, instant, offline
       │    │        compound "X and Y" split only if EVERY part matches
       │    └─ 2. AI fallback (ai/ollama_client.py → local Ollama, qwen2.5:1.5b, ~5-8 s on CPU)
       │             prompt = allowlist (generated from the registry) + examples + recent turns
       │             reply  → intent_parser (untrusted JSON) → action_validator → safety/command_filter
       ├─ CommandRouter      runs only GET_TIME / GET_DATE / HELP / GREETING / THANKS now; others "planned"
       ├─ build_reply        template sentence (never claims something happened that didn't)
       ├─ ConversationContext   "it" = last app, last search site
       └─ HistoryService     SQLite database\voiceos.db (if privacy.save_history)
  └─ response_ready ──► Home page: reply card + "Understood as" card ──► spoken reply
```

Three gates stand between AI output and your computer:
1. **Allowlist** (`actions/action_registry.py`): unknown action names are rejected.
2. **Validator** (`actions/action_validator.py`): types, ranges, lengths and URL schemes are checked; unexpected parameters are rejected.
3. **AI plan filter** (`safety/command_filter.py`): no invented typing, no shells. Phase 8 adds confirmations.

## Phase 6 Windows control

```
CommandRouter.route(intent)
  ├─ risk MEDIUM/HIGH? → ConfirmationManager.ask() ──signal──► GUI: "Do you want me to close Google Chrome?" [Yes/No]
  └─ handler (actions/*_actions.py) → controller (controllers/*) → integrations/windows/*
                                                                 ├─ win32_api.py   ctypes → user32/kernel32/dwmapi
                                                                 └─ windows_apps.py Get-StartApps → shell:AppsFolder\<AppID>
```

| Layer | Files | Job |
|---|---|---|
| Handlers | `actions/application_actions.py`, `window_actions.py`, `mouse_actions.py`, `keyboard_actions.py`, `browser_actions.py`, `media_actions.py`, `system_actions.py` | Intent → controller call → sentence to speak |
| Wiring | `core/action_manager.py` | Builds controllers and registers handlers (or none, in **dry-run** mode) |
| Controllers | `controllers/*_controller.py` | Find the right app/window and act. No decisions about permission. |
| Windows | `integrations/windows/win32_api.py`, `windows_apps.py` | Raw Windows calls; the Start-menu app list |
| Safety | `safety/confirmation_manager.py` | Thread-safe "Are you sure?" (MEDIUM: optional, HIGH: always) |

**"This window"** = the last active window that isn't VoiceOS (`FocusTracker`), so clicking VoiceOS's mic doesn't make VoiceOS the target. Typing and clicks focus that window first.

**Apps** can only be launched from your Start menu list: no file paths and no commands.

## Continuous listening (v0.6.1): one click → unlimited commands

Before v0.6.1, a click ran `run_once()` on a short-lived thread: capture ONE utterance, close the mic, set IDLE, end. That's why listening stopped after every command. Now a click (or "Hi Jarvis") starts one **listening session**:

```
ListeningSession thread (voice/voice_manager.py::_session_loop) - microphone opened ONCE
  loop:
    _wait_until_ready   previous command finished (Assistant busy → False) AND VoiceOS silent;
                        audio from that time is read and DROPPED   → no double commands, never hears itself
    LISTENING           capture an utterance (silence/timeout = keep listening)
    PROCESSING          speech → text → classify_control():
                          "stop listening" → PAUSED (mic closed; only a click resumes)
                          "quit jarvis"    → SHUTDOWN (window closes, all workers stop)
    EXECUTING           speech_recognized → Assistant → router → reply → command_finished()
```

| Who | Ends the session with |
|---|---|
| "stop listening" / "pause listening" / "go to sleep", a click on the mic, or Esc | PAUSED |
| "quit Jarvis" / "exit Jarvis" / "goodbye Jarvis" | SHUTDOWN → `MainWindow.quit_application()` |
| turning the wake word off while waiting for it | IDLE |

The top bar shows the real microphone (`mic_active_changed`) and the assistant state (`StatusPill`: Ready / Listening / Processing / Executing / Speaking / Paused).

## Technology choices

| Need | Choice | Why |
|---|---|---|
| Language | Python 3.14 | Rich ecosystem for audio, AI and Windows automation; readable for learning. |
| UI | PySide6 (Qt 6) | Native desktop widgets, stylable with QSS, official Qt binding, LGPL. |
| Speech-to-text | Vosk (default), faster-whisper (optional) | Both offline. Vosk is light and real-time on CPU; Whisper is more accurate but heavier. |
| Wake word | openWakeWord's "hey jarvis" ONNX models, run directly with onnxruntime | Offline, ~1% of one CPU core. "Hi Jarvis" scores 0.99 on this PC. Models are CC BY-NC-SA (personal use). |
| AI | Rules first, then Ollama + qwen2.5:1.5b (stdlib `urllib`, no SDK) | Local, free, private. 1.5B answers in ~5–8 s on this CPU; 3B is smarter but ~2x slower. |
| History | SQLite (`sqlite3`, built in) | One local file, parameterised queries. |
| Text-to-speech | Windows SAPI via comtypes (Piper optional) | Built into Windows, offline, allowed by Smart App Control. Piper sounds more natural, but its unsigned DLL is blocked here. |
| Windows control | Python's built-in `ctypes` + PowerShell `Get-StartApps` | Calls Windows' own user32/kernel32 directly: no extra native packages, nothing for Smart App Control to block. |
| Storage | SQLite | Built into Python, single file, no server. |
| Tests | pytest | The standard Python test tool. |

## Development phases

1. Environment and project structure ✅
2. Microphone and speech recognition ✅
3. Text-to-speech ✅
4. Wake-word detection ✅ ("Hi Jarvis")
5. AI intent recognition ✅
6. Global Windows automation ✅
7. File, browser and system control
8. Safety and permissions
9. UI/UX implementation and integration
10. AI Project Assistant and learning mode
11. Full testing and Windows packaging
