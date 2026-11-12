"""Tests for VAD segmentation, text clean-up, model selection and end-to-end recognition.

End-to-end tests use Windows' built-in voice (synth_speech fixture) as a stand-in
for a person, and FakeMicrophone instead of hardware. They are skipped
automatically if the Vosk model isn't downloaded.
"""

import pytest

from core.state_manager import AssistantState
from services.config_service import ConfigService
from utils.exceptions import SpeechRecognitionError
from voice.language_detection import resolve_model_dir
from voice.speech_processor import clean_transcript, process_result
from voice.speech_recognition import RecognitionResult, create_recognizer
from voice.voice_activity_detection import UtteranceSegmenter
from voice.voice_manager import VoiceManager

SPEECH, SILENCE = b"S" * 960, b"\x00" * 960


def fake_vad(frame: bytes) -> bool:
    return frame == SPEECH


# ---- VAD segmenter (deterministic fake VAD) ------------------------------------------
def run(segmenter, frames):
    for frame in frames:
        out = segmenter.process(frame)
        if out:
            return out
    return None


def test_segmenter_returns_utterance_after_trailing_silence():
    seg = UtteranceSegmenter(end_silence_ms=300, is_speech=fake_vad)  # 300 ms = 10 frames
    out = run(seg, [SILENCE] * 20 + [SPEECH] * 30 + [SILENCE] * 15)
    assert out is not None
    assert out.count(SPEECH) == 30  # every speech frame, including the pre-roll that triggered it


def test_segmenter_ignores_short_clicks():
    seg = UtteranceSegmenter(is_speech=fake_vad)
    assert run(seg, ([SPEECH] * 2 + [SILENCE] * 8) * 10) is None  # 60 ms blips never start speech


def test_segmenter_stops_at_max_length():
    seg = UtteranceSegmenter(max_seconds=2, is_speech=fake_vad)
    out = run(seg, [SPEECH] * 500)
    assert out is not None and len(out) <= 2 * 16000 * 2 + 960


# ---- text clean-up -------------------------------------------------------------------
@pytest.mark.parametrize(
    "raw, expected",
    [
        ("open  chrome", "Open Chrome"),
        ("um open uh notepad", "Open Notepad"),
        ("search you tube for robots", "Search YouTube for robots"),
        ("open whats app", "Open WhatsApp"),
        ("", ""),
    ],
)
def test_clean_transcript(raw, expected):
    assert clean_transcript(raw) == expected


def test_low_confidence_is_rejected_with_reason():
    result = process_result(RecognitionResult("open chrome", 0.3), min_confidence=0.55)
    assert not result.accepted and "repeat" in result.reason


def test_noise_word_is_rejected():
    assert not process_result(RecognitionResult("the", 0.9), 0.55).accepted


def test_nothing_heard():
    assert process_result(None, 0.55).reason == "I didn't hear anything."


# ---- model selection -----------------------------------------------------------------
def test_unsupported_language(tmp_path):
    with pytest.raises(SpeechRecognitionError, match="not supported"):
        resolve_model_dir("fr-FR", models_dir=tmp_path)


def test_missing_model_explains_how_to_download(tmp_path):
    with pytest.raises(SpeechRecognitionError, match="download_speech_model.py"):
        resolve_model_dir("en-US", models_dir=tmp_path)


def test_faster_whisper_not_yet_available(tmp_path):
    with pytest.raises(SpeechRecognitionError, match="faster-whisper"):
        create_recognizer("faster-whisper", tmp_path)


# ---- real recognition ----------------------------------------------------------------
@pytest.mark.parametrize("phrase", ["open notepad", "minimize this window", "take a screenshot"])
def test_vosk_recognizes_synthesized_speech(vosk_recognizer, synth_speech, phrase):
    result = vosk_recognizer.transcribe(synth_speech(phrase))
    assert result.text == phrase
    assert result.confidence > 0.8


def make_manager(tmp_path, mic, recognizer):
    config = ConfigService(tmp_path / "config.json")
    config.load()
    config.set("voice.no_speech_timeout_seconds", 2)
    return VoiceManager(config, microphone_factory=lambda: mic, recognizer=recognizer)


def test_full_pipeline_with_fake_microphone(tmp_path, vosk_recognizer, synth_speech, fake_microphone):
    mic = fake_microphone(synth_speech("open notepad"))
    manager = make_manager(tmp_path, mic, vosk_recognizer)
    states, results = [], []
    manager.state_changed.connect(states.append)
    manager.speech_recognized.connect(results.append)

    processed = manager.run_once()  # synchronous: no thread needed in a test

    assert processed.accepted and processed.text == "Open Notepad"
    assert results == [processed]
    assert states == [AssistantState.LISTENING, AssistantState.PROCESSING, AssistantState.IDLE]
    assert not mic.is_active, "microphone must be closed afterwards"


def test_silence_times_out_and_closes_microphone(tmp_path, vosk_recognizer, fake_microphone):
    mic = fake_microphone(b"")  # nothing but silence
    manager = make_manager(tmp_path, mic, vosk_recognizer)
    processed = manager.run_once()
    assert not processed.accepted and processed.reason == "I didn't hear anything."
    assert not mic.is_active


def test_cancel_stops_listening(tmp_path, vosk_recognizer, fake_microphone):
    mic = fake_microphone(b"")
    manager = make_manager(tmp_path, mic, vosk_recognizer)
    manager.cancel()  # cancelled before the loop runs -> returns immediately
    assert manager.run_once() is None
    assert not mic.is_active


def test_missing_microphone_reports_error(tmp_path, vosk_recognizer):
    from utils.exceptions import MicrophoneError

    def no_mic():
        raise MicrophoneError("No microphone found.")

    config = ConfigService(tmp_path / "config.json")
    config.load()
    manager = VoiceManager(config, microphone_factory=no_mic, recognizer=vosk_recognizer)
    errors, states = [], []
    manager.error_occurred.connect(errors.append)
    manager.state_changed.connect(states.append)
    assert manager.run_once() is None
    assert errors == ["No microphone found."]
    assert states[-1] is AssistantState.IDLE  # recovers, ready to try again
