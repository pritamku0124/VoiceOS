# Troubleshooting

Start with the log: `logs\voiceos.log` records what VoiceOS heard, which microphone it used and any errors.

## "ModuleNotFoundError: No module named 'sounddevice'" (or PySide6, vosk...)

**Cause:** the command ran with the *global* Python, not the project's `.venv`, where the packages are installed. The giveaway is a prompt without `(.venv)` in front.

**Fix (pick one):**

```powershell
.\.venv\Scripts\Activate.ps1          # once per terminal window; prompt becomes (.venv) PS ...
python scripts\check_microphone.py
```

```powershell
.\.venv\Scripts\python.exe scripts\check_microphone.py   # no activation needed
```

If `Activate.ps1` says *"running scripts is disabled on this system"*, allow scripts for your user only, once:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

Since Phase 3, `main.py` and `check_microphone.py` detect this mistake and print these instructions themselves.

## "An Application Control policy has blocked this file"

This is Windows **Smart App Control** blocking an unsigned DLL inside a Python package (it happened with Piper TTS). **Do not turn Smart App Control off.** Use an alternative that is allowed instead. For speech output that means `"tts": {"engine": "windows"}`, which is the default.

## Speech output (text-to-speech)

| Symptom | Fix |
|---|---|
| No sound | Test with `python scripts\check_microphone.py --say "hello"`. Check the Windows output device and volume. |
| Wrong or unwanted voice | Set `"tts": {"voice": "Zira"}` or `"David"` in `config.json` (any part of a name listed by `--say`). |
| Too fast or too slow | `"tts": {"speed": 0.8}` (0.5–2.0). |
| Want silence | `"tts": {"enabled": false}`, or press **Esc** to stop the current reply. |

## Microphone

| Symptom | Likely cause | Fix |
|---|---|---|
| "No microphone found" | Mic disabled or unplugged | Windows Settings → System → Sound → Input. Then run `python scripts\check_microphone.py`. |
| "Could not open the microphone" | Windows privacy setting blocks desktop apps | Settings → Privacy & security → Microphone → turn on **Let desktop apps access your microphone**. |
| Waveform doesn't move / "I didn't hear anything" | Wrong mic chosen, or input volume too low | `python scripts\check_microphone.py --level 5` while talking. Expect about -35 to -15 dB. Pick another mic via `"input_device"` in `config.json` (number or part of the name). |
| Listening stops while I'm still talking | Pauses longer than `end_silence_ms` | Raise `voice.end_silence_ms` (e.g. 1200). |
| It starts on background noise | VAD too permissive | Raise `voice.vad_aggressiveness` to 3. |

## Speech recognition

| Symptom | Fix |
|---|---|
| "Speech model ... is not installed" | `python scripts\download_speech_model.py` |
| "Not sure I heard that right" | Speak a little closer or louder. Or lower `voice.min_confidence` (e.g. 0.45), at the cost of more mistakes. |
| Brand names come out split ("you tube") | Add a rule to `CORRECTIONS` in `voice/speech_processor.py`. |
| Indian-English accent recognised poorly | `python scripts\download_speech_model.py vosk-model-small-en-in-0.4`, then set `"language": "en-IN"`. |

## Wake word ("Hi Jarvis")

| Symptom | Fix |
|---|---|
| "Wake-word model files missing" | `python scripts\download_wake_word_model.py` |
| It doesn't react to "Hi Jarvis" | Run `python scripts\check_microphone.py --wake 20` and say it a few times. If the best score stays below the threshold, lower `wake_word.threshold` (e.g. 0.5) or `patience` to 1. |
| It wakes up by itself (TV, conversation) | Raise `wake_word.threshold` (e.g. 0.85) or `patience` to 3. |
| The first word of my command is missing | Pause briefly after "Hi Jarvis". That pattern is supported too. |
| Text starts with a stray word ("this open...") | Tell us the phrase; the strip pattern lives in `WAKE_WORDS` in `voice/wake_word.py`. |
| I don't want the mic always on | Click **Turn off** in the Wake word card (saved to `config.json`), or set `"wake_word": {"enabled": false}`. Push-to-talk keeps working. |
| It doesn't react while VoiceOS is talking | By design: the mic is closed then. Click the mic or press Esc to interrupt. |

## Understanding commands / AI (Ollama)

| Symptom | Fix |
|---|---|
| "Sorry, I didn't understand that. I only know simple commands until the AI model is installed." | Ollama isn't running, or the model is missing. Start **Ollama** from the Start menu (it then runs in the system tray), and check with `ollama list` that `qwen2.5:1.5b` appears. To download it: `ollama pull qwen2.5:1.5b`. |
| Does Ollama need an account or sign-in? | No. Local models work without signing in. Its sign-in is only for Ollama's optional cloud features, and it's unrelated to any other account. |
| The AI is slow (5–10 s) | Normal for a CPU. Common commands use the instant rules instead. The first AI request after start-up is slower while the model loads (VoiceOS warms it up in the background). |
| Wrong understanding | Look at the **Understood as** card: it shows the actions and whether rules or the AI chose them. Use clearer wording, or add a rule in `ai/intent_recognition.py`. |
| "Rejected: ..." in the Understood-as card | A safety gate removed something the AI proposed. This is intended (see docs/ARCHITECTURE.md). |
| Turn the AI off | Set `"ai": {"enabled": false}` in `config.json`. Only the rules are used. |

## Continuous listening

| Symptom | Fix |
|---|---|
| It stops after one command | Fixed in v0.6.1. One click now listens until you say "stop listening". Check the version at the bottom of the sidebar. |
| It reacts to other people talking or the TV | Expected with continuous listening: everything said nearby is treated as a possible command. Say "stop listening" (or press Esc) when you're not using it, or use the wake word. |
| What I said while it was busy was ignored | By design. Speech that arrives while a command runs or while VoiceOS talks is discarded, so commands never pile up or run twice. Wait for "Listening", then speak. |
| "Stop listening" isn't recognized | Say it as a short phrase on its own. "Pause listening" and "go to sleep" also work. Clicking the mic or pressing Esc pauses too. |
| "Quit Jarvis" isn't recognized | Alternatives: "exit Jarvis", "goodbye Jarvis", or typing "quit jarvis". Closing the window does the same safe shutdown. |

## Windows control (Phase 6)

| Symptom | Fix |
|---|---|
| "I couldn't find an app called X" | VoiceOS opens apps from your **Start menu** list. Check the exact name there. The reply suggests close matches ("Did you mean Notepad?"). A newly installed app appears after restarting VoiceOS. |
| "Minimize this window" acted on the wrong window | "This window" = the last window you used that isn't VoiceOS. Click the window you mean first, or say its name ("minimize chrome"). |
| Typing or keys don't arrive | Some windows run as **administrator** (e.g. Task Manager). Windows blocks normal programs from sending keys to them, by design. |
| It asks "Do you want me to close...?" | Closing apps/windows is MEDIUM risk. Click **Yes**. Set `"confirm_destructive_actions": false` to skip that question. Locking (HIGH risk) always asks. |
| I want to try commands without anything happening | Set `"safety": {"dry_run": true}`. Commands are understood and shown, but nothing is executed. |

## Configuration

| Symptom | Fix |
|---|---|
| "config.json is not valid JSON (line X, column Y)" | Open that line. Usually a missing or extra comma, or quotes around `true`/`null`. |
| "'voice.xxx' must be ..." | The value is outside the allowed range. The message says what is allowed. |
