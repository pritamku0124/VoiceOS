"""Microphone diagnostics from the terminal - no UI needed.

Run from the project folder (virtual environment active):
    python scripts\\check_microphone.py                 # list microphones
    python scripts\\check_microphone.py --level 5       # live volume meter for 5 seconds
    python scripts\\check_microphone.py --recognize     # say one command, print what was heard
    python scripts\\check_microphone.py --level 3 --save  # also save recordings\\mic_test.wav
    python scripts\\check_microphone.py --say "Hello"   # test the speakers / text-to-speech
    python scripts\\check_microphone.py --wake 20       # live "Hi Jarvis" scores for 20 seconds

Privacy: audio is only written to disk with --save (your explicit choice).
"""

import argparse
import sys
import time
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from utils.platform_utils import require_virtualenv  # noqa: E402

require_virtualenv()  # must run BEFORE importing anything that needs sounddevice/vosk

from services.config_service import ConfigService  # noqa: E402
from utils.constants import CONFIG_FILE, RECORDINGS_DIR  # noqa: E402
from utils.exceptions import VoiceOSError  # noqa: E402
from voice.audio_device_manager import list_input_devices  # noqa: E402
from voice.audio_processor import frame_rms, meter_level, rms_to_db  # noqa: E402
from voice.microphone import Microphone  # noqa: E402


def show_devices() -> None:
    print("Microphones (* = Windows default):")
    for d in list_input_devices():
        print(f"  {'*' if d.is_default else ' '} [{d.index:2}] {d.name}")
    print('\nTo pick one, set "input_device" in config.json to its number or part of its name.')


def level_meter(config: ConfigService, seconds: float, save: bool) -> None:
    mic = Microphone(config.get("voice.input_device"))
    print(f"Using: {mic.device_name}. Speak now... (Ctrl+C to stop)")
    frames = []
    mic.start()
    try:
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            frame = mic.read_frame()
            if frame is None:
                continue
            if save:
                frames.append(frame)
            rms = frame_rms(frame)
            bar = "#" * int(meter_level(rms) * 40)
            print(f"\r  {rms_to_db(rms):6.1f} dB |{bar:<40}|", end="", flush=True)
    finally:
        mic.stop()
    print("\nDone. Normal speech is roughly -35 to -15 dB. Below -50 dB while talking = mic too quiet/muted.")
    if save:
        RECORDINGS_DIR.mkdir(exist_ok=True)
        path = RECORDINGS_DIR / "mic_test.wav"
        with wave.open(str(path), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)  # 2 bytes = 16-bit
            wav.setframerate(16000)
            wav.writeframes(b"".join(frames))
        print(f"Saved {path}")


def recognize(config: ConfigService) -> None:
    # VoiceManager is a QObject; signals work without a running Qt app when called directly.
    from voice.voice_manager import VoiceManager

    manager = VoiceManager(config)
    manager.state_changed.connect(lambda s: print(f"  [{s.value}]"))
    print("Say a command (e.g. 'open notepad')...")
    result = manager.run_once()
    if result is None:
        print("Nothing recognised (see message above).")
    elif result.accepted:
        print(f'Heard: "{result.text}"  (confidence {result.confidence:.0%})')
    else:
        print(f"Not accepted: {result.reason}  (raw: {result.raw_text!r})")


def say(config: ConfigService, text: str) -> None:
    """Speak text through the configured TTS engine and the default speakers."""
    import threading

    from voice.text_to_speech import AudioPlayer, WindowsTTS, create_tts_engine

    if config.get("tts.engine") == "windows":
        print("Windows voices:", ", ".join(WindowsTTS.available_voices()))
    engine = create_tts_engine(config)
    audio = engine.synthesize(text)
    print(f'Saying "{text}" ({audio.seconds:.1f} s)...')
    AudioPlayer().play(audio, threading.Event())
    print("Done. Change the voice/speed/volume under 'tts' in config.json.")


def wake(config: ConfigService, seconds: float) -> None:
    """Show live wake-word scores so you can see how well your voice triggers it."""
    from voice.wake_word import create_wake_word_detector, wake_phrase

    detector = create_wake_word_detector(config)
    detector.patience = 10_000  # never "fire" - we only want to watch the score here
    mic = Microphone(config.get("voice.input_device"))
    threshold = config.get("wake_word.threshold")
    print(f'Say "{wake_phrase(config.get("wake_word.model"))}" a few times. '
          f"Score must reach {threshold} (config wake_word.threshold). Ctrl+C to stop.")
    mic.start()
    best = 0.0
    try:
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            frame = mic.read_frame()
            if frame is None:
                continue
            detector.process(frame)
            score = detector.last_score
            best = max(best, score)
            bar = "#" * int(score * 40)
            mark = "  <-- WAKE" if score >= threshold else ""
            print(f"\r  score {score:4.2f} |{bar:<40}| best {best:4.2f}{mark}   ", end="", flush=True)
    finally:
        mic.stop()
    print(f"\nBest score: {best:.2f}. If it rarely passes {threshold}, lower wake_word.threshold (e.g. 0.5).")


def main() -> int:
    parser = argparse.ArgumentParser(description="VoiceOS microphone and speaker check")
    parser.add_argument("--wake", type=float, metavar="SECONDS", help="live wake-word scores (say 'Hi Jarvis')")
    parser.add_argument("--say", metavar="TEXT", help="speak TEXT through the speakers (tests text-to-speech)")
    parser.add_argument("--level", type=float, metavar="SECONDS", help="show a live volume meter")
    parser.add_argument("--save", action="store_true", help="save the --level recording to recordings/")
    parser.add_argument("--recognize", action="store_true", help="recognise one spoken command")
    args = parser.parse_args()

    config = ConfigService(CONFIG_FILE)
    try:
        config.load()
        show_devices()
        if args.level:
            print()
            level_meter(config, args.level, args.save)
        if args.recognize:
            print()
            recognize(config)
        if args.say:
            print()
            say(config, args.say)
        if args.wake:
            print()
            wake(config, args.wake)
    except VoiceOSError as exc:
        print(f"\nProblem: {exc}")
        return 1
    except KeyboardInterrupt:
        print("\nStopped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
