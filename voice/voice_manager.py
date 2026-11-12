"""VoiceManager: the microphone side of VoiceOS - listening, recognising, and the listening session.

CONTINUOUS SESSION (what the mic button and "Hi Jarvis" start)
    One long-lived thread runs _session_loop(). The microphone opens ONCE and stays open:

        loop:
          wait until the previous command has finished AND VoiceOS has stopped talking,
              throwing away all audio from that time       (no double commands, never hears itself)
          LISTENING   capture one utterance (silence = just keep listening, never stop)
          PROCESSING  speech -> text; "stop listening" -> PAUSED, "quit jarvis" -> SHUTDOWN
          EXECUTING   hand the text to the Assistant (via the speech_recognized signal)
          ...repeat until "stop listening", a click on the mic, Esc, or "quit Jarvis".

    Phase 2-5 used "one command per click" (run_once). That is why listening stopped after
    every command: the thread captured ONE utterance, closed the mic, set IDLE and ended.
    run_once() still exists for the terminal check script.

WAKE WORD
    With the wake word on, the session starts by waiting for "Hi Jarvis" (only the
    wake-word detector hears the audio). After "Hi Jarvis" it is the same continuous session.

THREADS
    The GUI thread must never wait for audio, so all of this runs on background threads.
    Results reach the UI as Qt signals, which Qt delivers safely on the GUI thread.

PRIVACY
    Audio stays in memory and is never written to disk. mic_active_changed reports the
    real microphone state, so the on-screen indicator is always truthful.
"""

from __future__ import annotations

import dataclasses
import logging
import threading
import time
from collections import deque
from collections.abc import Callable, Iterable

from PySide6.QtCore import QObject, Signal

from ai.command_classifier import QUIT, STOP_LISTENING, classify_control
from core.state_manager import AssistantState
from services.config_service import ConfigService
from voice.audio_processor import frame_rms, meter_level
from voice.language_detection import resolve_model_dir
from voice.microphone import Microphone
from voice.speech_processor import ProcessedSpeech, process_result
from voice.speech_recognition import SpeechRecognizer, create_recognizer
from voice.voice_activity_detection import UtteranceSegmenter
from voice.wake_word import create_wake_word_detector, strip_wake_phrase
from utils.exceptions import VoiceOSError

logger = logging.getLogger(__name__)

# Audio kept from just before "Hi Jarvis" fired (40 x 30 ms = 1.2 s). It holds the WHOLE wake
# phrase, so "hi jarvis open notepad" is transcribed in full and "hi jarvis" is stripped cleanly.
PREFILL_FRAMES = 40
ECHO_TAIL_FRAMES = 10  # ~0.3 s dropped after VoiceOS stops talking (room echo of its own voice)
COMMAND_TIMEOUT_SECONDS = 120  # safety net if a command never reports back


class VoiceManager(QObject):
    state_changed = Signal(object)  # AssistantState
    level_changed = Signal(float)  # 0..1 loudness for the waveform
    speech_recognized = Signal(object)  # ProcessedSpeech
    error_occurred = Signal(str)
    wake_word_detected = Signal()
    wake_word_active_changed = Signal(bool)  # wake-word setting on/off
    mic_active_changed = Signal(bool)  # the REAL microphone state, for the indicator
    session_changed = Signal(bool)  # continuous session started / ended
    control_command = Signal(str)  # "stop_listening" or "quit"

    def __init__(
        self,
        config: ConfigService,
        microphone_factory: Callable[[], Microphone] | None = None,
        recognizer: SpeechRecognizer | None = None,
        speech_output=None,  # voice.text_to_speech.SpeechOutput, optional
        wake_detector=None,  # voice.wake_word.WakeWordDetector, optional (tests)
        parent: QObject | None = None,
    ):
        super().__init__(parent)
        self.config = config
        self.speech_output = speech_output
        # Dependency injection: tests pass fakes; the app uses the real ones (created lazily).
        self._microphone_factory = microphone_factory or (
            lambda: Microphone(config.get("voice.input_device"), config.get("voice.sample_rate"))
        )
        self._recognizer = recognizer
        self._detector = wake_detector
        self.wake_word_enabled = False
        self.state = AssistantState.IDLE

        self._thread: threading.Thread | None = None  # single-command worker (run_once)
        self._session: threading.Thread | None = None  # continuous session
        self._cancel = threading.Event()  # abort the utterance being captured
        self._stop_session = threading.Event()  # end the continuous session
        self._manual_trigger = threading.Event()  # mic clicked while waiting for the wake word
        self._command_done = threading.Event()  # the last command has finished
        self._command_done.set()
        self._end_state = AssistantState.IDLE  # state to show when the session ends

    # =====================================================================================
    # Called from the UI (GUI thread)
    # =====================================================================================
    @property
    def session_active(self) -> bool:
        return self._session is not None and self._session.is_alive() and not self._stop_session.is_set()

    @property
    def busy(self) -> bool:
        return self.session_active or (self._thread is not None and self._thread.is_alive())

    @property
    def wake_word_active(self) -> bool:  # kept for compatibility with earlier code
        return self.wake_word_enabled and self.session_active

    def toggle_listening(self) -> None:
        """Mic button / Ctrl+Space."""
        if self.session_active:
            if self._speaking():
                self.speech_output.stop()  # barge-in: cut VoiceOS off; the session keeps listening
            elif self.state is AssistantState.WAKE_LISTENING:
                self._manual_trigger.set()  # skip "Hi Jarvis"
            else:
                self.pause()  # click while listening = pause
        elif self._thread is not None and self._thread.is_alive():
            self.cancel()
        else:
            self.start_listening()

    def start_listening(self, wait_for_wake: bool = False) -> None:
        """Start (or resume) the continuous session. One click -> unlimited commands."""
        if self.session_active:
            if not wait_for_wake and self.state is AssistantState.WAKE_LISTENING:
                self._manual_trigger.set()
            return
        if self._session is not None:
            self._session.join(2.0)  # make sure an old session has fully released the mic
        self._stop_session.clear()
        self._manual_trigger.clear()
        self._cancel.clear()
        self._command_done.set()
        self._end_state = AssistantState.IDLE
        self._session = threading.Thread(target=self._session_loop, args=(wait_for_wake,),
                                         name="ListeningSession", daemon=True)
        self._session.start()

    def pause(self) -> None:
        """Stop listening until the mic button is clicked again (microphone closes)."""
        self._end_session(AssistantState.PAUSED)

    def set_wake_word_enabled(self, enabled: bool) -> None:
        self.wake_word_enabled = enabled
        if enabled and not self.session_active:
            self.start_listening(wait_for_wake=True)
        elif not enabled and self.session_active and self.state is AssistantState.WAKE_LISTENING:
            self._end_session(AssistantState.IDLE)
        self.wake_word_active_changed.emit(enabled)

    def command_finished(self) -> None:
        """The UI calls this when a command's reply is under way, so listening may continue."""
        self._command_done.set()

    def cancel(self) -> None:
        self._cancel.set()

    def listen_once(self) -> None:
        """Single-command mode (kept for scripts). The UI uses start_listening()."""
        if self.busy:
            return
        self._cancel.clear()
        self._thread = threading.Thread(target=self.run_once, name="VoiceWorker", daemon=True)
        self._thread.start()

    def wait(self, timeout: float | None = None) -> None:
        if self._thread is not None:
            self._thread.join(timeout)

    def shutdown(self, timeout: float = 3.0) -> None:
        """Stop everything and wait until the microphone is released (used on quit)."""
        self._end_session(AssistantState.SHUTDOWN, timeout)
        self.cancel()
        self.wait(timeout)

    def _end_session(self, end_state: AssistantState, timeout: float = 3.0) -> None:
        self._end_state = end_state
        self._stop_session.set()
        self._cancel.set()
        self._command_done.set()  # don't stay stuck waiting for a reply
        if self._session is not None and self._session is not threading.current_thread():
            self._session.join(timeout)
        if self._session is None or not self._session.is_alive():
            self._set_state(end_state)

    # =====================================================================================
    # Shared helpers (background threads)
    # =====================================================================================
    def _set_state(self, state: AssistantState) -> None:
        self.state = state
        self.state_changed.emit(state)

    def _speaking(self) -> bool:
        return self.speech_output is not None and self.speech_output.is_speaking

    def _stopping(self) -> bool:
        return self._stop_session.is_set()

    def _get_recognizer(self) -> SpeechRecognizer:
        if self._recognizer is None:
            self._set_state(AssistantState.LOADING)
            model_dir = resolve_model_dir(self.config.get("voice.language"), self.config.get("voice.model"))
            self._recognizer = create_recognizer(
                self.config.get("voice.engine"), model_dir, self.config.get("voice.sample_rate"))
        return self._recognizer

    def _get_detector(self):
        if self._detector is None:
            self._set_state(AssistantState.LOADING)
            self._detector = create_wake_word_detector(self.config)
        return self._detector

    def _open_mic(self) -> Microphone:
        microphone = self._microphone_factory()
        microphone.start()
        self.mic_active_changed.emit(True)
        return microphone

    def _close_mic(self, microphone: Microphone | None) -> None:
        if microphone is not None:
            microphone.stop()
            self.mic_active_changed.emit(False)
        self.level_changed.emit(0.0)

    def _report(self, exc: BaseException) -> None:
        if isinstance(exc, VoiceOSError):
            logger.error("Voice error: %s", exc)
            message = str(exc)
        else:
            logger.exception("Unexpected error in voice worker")
            message = "Something went wrong while listening. Details are in logs\\voiceos.log."
        self._set_state(AssistantState.ERROR)
        self.error_occurred.emit(message)

    def _recognize(self, recognizer, audio: bytes, strip_wake: bool) -> ProcessedSpeech:
        result = recognizer.transcribe(audio)
        if strip_wake:
            result = dataclasses.replace(result, text=strip_wake_phrase(result.text, self.config.get("wake_word.model")))
        processed = process_result(result, self.config.get("voice.min_confidence"))
        logger.info("Heard %r (confidence %.2f, %.1fs audio, %.2fs to recognise, accepted=%s)",
                    result.text, result.confidence, result.audio_seconds, result.processing_seconds, processed.accepted)
        return processed

    def _capture_utterance(self, microphone: Microphone, prefill: Iterable[bytes] = ()) -> bytes | None:
        """Listen until one utterance is complete. b'' = nothing said before the timeout, None = cancelled."""
        segmenter = UtteranceSegmenter(
            sample_rate=self.config.get("voice.sample_rate"),
            aggressiveness=self.config.get("voice.vad_aggressiveness"),
            end_silence_ms=self.config.get("voice.end_silence_ms"),
            max_seconds=self.config.get("voice.max_utterance_seconds"),
        )
        no_speech_timeout = self.config.get("voice.no_speech_timeout_seconds")
        self._set_state(AssistantState.LISTENING)
        for frame in prefill:
            utterance = segmenter.process(frame)
            if utterance:
                return utterance

        started = time.monotonic()
        while not self._cancel.is_set() and not self._stopping():
            frame = microphone.read_frame(timeout=0.5)
            if frame is None:
                continue
            self.level_changed.emit(meter_level(frame_rms(frame)))
            utterance = segmenter.process(frame)
            if utterance:
                return utterance
            if not segmenter.in_speech and time.monotonic() - started > no_speech_timeout:
                return b""
        return None

    # =====================================================================================
    # Continuous session
    # =====================================================================================
    def _session_loop(self, wait_for_wake: bool) -> None:
        self.session_changed.emit(True)
        microphone = None
        try:
            recognizer = self._get_recognizer()
            detector = self._get_detector() if wait_for_wake else None
            microphone = self._open_mic()
            logger.info("Listening session started on %s (wake word first: %s)", microphone.device_name, wait_for_wake)

            prefill: list[bytes] = []
            if detector is not None:
                prefill = self._wait_for_wake_word(microphone, detector)
                if prefill is None:
                    return
                self.wake_word_detected.emit()

            while not self._stopping():
                self._wait_until_ready(microphone)  # previous command finished, VoiceOS silent
                if self._stopping():
                    break
                self._cancel.clear()
                audio = self._capture_utterance(microphone, prefill)
                prefill = []
                if audio is None:
                    if self._stopping():
                        break
                    continue  # utterance cancelled (e.g. Esc) - keep the session
                if not audio:
                    continue  # silence: keep listening, never stop because of a timeout

                self._set_state(AssistantState.PROCESSING)
                speech = self._recognize(recognizer, audio, strip_wake=True)
                if not speech.text:
                    continue  # noise, or only "Hi Jarvis" - keep listening for the command

                control = classify_control(speech.text)
                if control == STOP_LISTENING:
                    logger.info("Voice command: stop listening")
                    self._end_state = AssistantState.PAUSED
                    self.control_command.emit(STOP_LISTENING)
                    break
                if control == QUIT:
                    logger.info("Voice command: quit")
                    self._end_state = AssistantState.SHUTDOWN
                    self.control_command.emit(QUIT)
                    break

                if speech.accepted:
                    self._command_done.clear()  # the next command waits until this one finishes
                    self._set_state(AssistantState.EXECUTING)
                self.speech_recognized.emit(speech)  # rejected speech is shown, never executed
        except Exception as exc:  # VoiceOSError = expected problem; anything else = bug (logged)
            self._report(exc)
            self._end_state = AssistantState.IDLE
        finally:
            self._close_mic(microphone)
            self._stop_session.set()
            self._set_state(self._end_state)
            self.session_changed.emit(False)
            logger.info("Listening session ended (%s)", self._end_state.value)

    def _wait_until_ready(self, microphone: Microphone) -> None:
        """Block while a command runs or VoiceOS talks. Audio from that time is read and DROPPED,
        so a command is never heard twice and VoiceOS never hears its own voice."""
        waited_for_voice = False
        started = time.monotonic()
        while not self._stopping():
            speaking = self._speaking()
            if self._command_done.is_set() and not speaking:
                break
            waited_for_voice = waited_for_voice or speaking
            if time.monotonic() - started > COMMAND_TIMEOUT_SECONDS:
                logger.warning("No reply after %s s - listening again", COMMAND_TIMEOUT_SECONDS)
                self._command_done.set()
            microphone.read_frame(timeout=0.1)  # drop
        if waited_for_voice:
            for _ in range(ECHO_TAIL_FRAMES):  # the room still echoes VoiceOS's last word
                microphone.read_frame(timeout=0.1)
        microphone.discard_pending()

    def _wait_for_wake_word(self, microphone: Microphone, detector) -> list[bytes] | None:
        """Feed audio to the wake-word detector only. Returns recent frames when heard, None if stopped."""
        self._set_state(AssistantState.WAKE_LISTENING)
        detector.reset()
        recent: deque[bytes] = deque(maxlen=PREFILL_FRAMES)
        while not self._stopping():
            if self._manual_trigger.is_set():
                self._manual_trigger.clear()
                logger.info("Mic clicked while waiting for the wake word")
                return []
            frame = microphone.read_frame(timeout=0.5)
            if frame is None:
                continue
            if self._speaking():  # VoiceOS is talking: its own "Jarvis" must not wake it
                recent.clear()
                detector.reset()
                continue
            recent.append(frame)
            if detector.process(frame):
                return list(recent)
        return None

    # =====================================================================================
    # Single command (kept for scripts/check_microphone.py)
    # =====================================================================================
    def run_once(self) -> ProcessedSpeech | None:
        """Capture and recognise ONE command, then close the microphone."""
        microphone = None
        try:
            if self._speaking():
                self.speech_output.stop(wait=True)  # never listen while VoiceOS talks
            recognizer = self._get_recognizer()
            microphone = self._open_mic()
            audio = self._capture_utterance(microphone)
            self._close_mic(microphone)  # close the mic BEFORE recognising - it's no longer needed
            microphone = None
            if audio is None:
                return None
            self._set_state(AssistantState.PROCESSING)
            processed = self._recognize(recognizer, audio, strip_wake=False) if audio else process_result(
                None, self.config.get("voice.min_confidence"))
            self.speech_recognized.emit(processed)
            return processed
        except Exception as exc:
            self._report(exc)
            return None
        finally:
            self._close_mic(microphone)
            self._set_state(AssistantState.IDLE)
