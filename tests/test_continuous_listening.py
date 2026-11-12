"""Continuous listening: one click -> unlimited commands (the fix for "it stops after one command").

The fake microphone plays scripted audio (Windows' voice saying commands), the REAL speech
recogniser hears it, and we check what the listening session does with it.

Note on Qt.DirectConnection: our "pretend UI" handlers run immediately on the session's own
thread, like a very fast UI. That keeps the scripted audio in step with the session.
"""

import time

import pytest
from PySide6.QtCore import Qt

from ai.command_classifier import QUIT, STOP_LISTENING, classify_control
from core.state_manager import AssistantState
from services.config_service import ConfigService
from voice.voice_manager import VoiceManager

SILENCE = b"\x00" * 32000  # 1 second


@pytest.mark.parametrize("text, expected", [
    ("stop listening", STOP_LISTENING), ("Stop listening.", STOP_LISTENING), ("please stop listening now", STOP_LISTENING),
    ("jarvis stop listening", STOP_LISTENING), ("pause listening", STOP_LISTENING), ("go to sleep", STOP_LISTENING),
    ("quit jarvis", QUIT), ("Quit Jarvis!", QUIT), ("exit jarvis", QUIT), ("goodbye jarvis", QUIT), ("quit jervis", QUIT),
    ("quick jarvis", QUIT), ("good bye jarvis", QUIT),  # what Vosk actually hears (measured)
    ("good jarvis", None),  # could be praise - must never shut VoiceOS down
    ("stop the music", None), ("close chrome", None), ("quit", None), ("stop", None), ("open notepad", None),
])
def test_control_phrases(text, expected):
    assert classify_control(text) == expected


def wait_for(condition, timeout=20.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.02)
    return False


@pytest.fixture
def session(tmp_path, vosk_recognizer, fake_microphone):
    """Start a continuous session on scripted audio. Returns a helper object."""
    managers = []

    class Session:
        def __init__(self, audio, speech_output=None, auto_finish=True):
            config = ConfigService(tmp_path / "config.json")
            config.load()
            config.set("voice.no_speech_timeout_seconds", 2)
            self.mic = fake_microphone(audio)
            self.voice = VoiceManager(config, microphone_factory=lambda: self.mic, recognizer=vosk_recognizer,
                                      speech_output=speech_output)
            self.heard, self.controls, self.states = [], [], []
            self.auto_finish = auto_finish

            def on_speech(speech):  # pretend UI: run the command, then report it finished
                self.heard.append(speech.text)
                if self.auto_finish:
                    self.voice.command_finished()

            self.voice.speech_recognized.connect(on_speech, Qt.DirectConnection)
            self.voice.control_command.connect(self.controls.append, Qt.DirectConnection)
            self.voice.state_changed.connect(self.states.append, Qt.DirectConnection)
            managers.append(self.voice)
            self.voice.start_listening()

    yield Session
    for manager in managers:
        manager.shutdown()


def test_several_commands_without_clicking_again(session, synth_speech):
    s = session(SILENCE.join(synth_speech(t) for t in ("minimize this window", "open notepad", "take a screenshot")))
    assert wait_for(lambda: len(s.heard) == 3), s.heard
    assert s.heard == ["Minimize this window", "Open Notepad", "Take a screenshot"]
    assert wait_for(lambda: s.voice.state is AssistantState.LISTENING)  # still listening afterwards
    assert s.mic.start_count == 1, "the microphone must not be reopened for every command"


def test_silence_does_not_end_the_session(session):
    s = session(b"")  # nothing but silence; the no-speech timeout is 2 s
    time.sleep(4.5)  # more than two timeouts
    assert s.voice.session_active and s.mic.is_active and s.voice.state is AssistantState.LISTENING


def test_next_command_waits_until_the_previous_one_finished(session, synth_speech):
    """No overlapping or double execution: speech that arrives WHILE a command runs is ignored;
    speech after it has finished is heard."""
    s = session(synth_speech("open notepad") + SILENCE, auto_finish=False)
    assert wait_for(lambda: s.heard == ["Open Notepad"])
    s.mic.feed(synth_speech("open youtube") + SILENCE)  # said while Notepad is still being opened...
    time.sleep(1.5)
    assert s.heard == ["Open Notepad"] and s.voice.state is AssistantState.EXECUTING  # ...ignored
    s.voice.command_finished()
    s.mic.feed(SILENCE + synth_speech("open youtube") + SILENCE)  # said again, after it finished
    assert wait_for(lambda: s.heard == ["Open Notepad", "Open YouTube"])  # Vosk: "you tube" -> corrected


def test_each_command_is_reported_exactly_once(session, synth_speech):
    s = session(synth_speech("open notepad") + SILENCE * 3)
    assert wait_for(lambda: s.heard)
    time.sleep(2.5)
    assert s.heard == ["Open Notepad"]


def test_voiceos_never_hears_its_own_voice(session, synth_speech):
    """While VoiceOS talks, audio is read and thrown away - so its own words are never commands."""
    from tests.test_text_to_speech import make_output

    output, _, player = make_output(block=True)
    output.say("I can open notepad for you")  # VoiceOS is talking...
    assert player.started.wait(5)
    s = session(synth_speech("open notepad"), speech_output=output)  # ...and the mic 'hears' those words
    assert wait_for(lambda: s.mic.frames_read > 200)  # the audio was consumed while talking
    output.stop(wait=True)
    time.sleep(2.0)
    assert s.heard == []  # nothing was treated as a command
    output.shutdown()


def test_stop_listening_pauses_and_closes_the_microphone(session, synth_speech):
    s = session(synth_speech("stop listening") + SILENCE)
    assert wait_for(lambda: s.voice.state is AssistantState.PAUSED)
    assert s.controls == [STOP_LISTENING] and s.heard == []
    assert not s.voice.session_active and not s.mic.is_active
    time.sleep(1.0)
    assert s.voice.state is AssistantState.PAUSED  # it does NOT reactivate by itself


def test_resume_after_pause(session, synth_speech):
    s = session(synth_speech("stop listening") + SILENCE + synth_speech("open notepad") + SILENCE)
    assert wait_for(lambda: s.voice.state is AssistantState.PAUSED)
    s.voice.toggle_listening()  # the mic button
    assert wait_for(lambda: s.heard == ["Open Notepad"])
    assert s.voice.session_active


def test_quit_is_reported_and_session_ends(session, synth_speech):
    s = session(synth_speech("quit jarvis") + SILENCE)
    assert wait_for(lambda: s.controls == [QUIT])
    assert wait_for(lambda: not s.voice.busy)
    assert s.voice.state is AssistantState.SHUTDOWN and not s.mic.is_active


def test_clicking_while_listening_pauses(session):
    s = session(b"")
    assert wait_for(lambda: s.voice.state is AssistantState.LISTENING)
    s.voice.toggle_listening()
    assert s.voice.state is AssistantState.PAUSED and not s.mic.is_active


def test_shutdown_releases_everything(session):
    s = session(b"")
    assert wait_for(lambda: s.mic.is_active)
    s.voice.shutdown()
    assert not s.mic.is_active and not s.voice.busy and s.voice.state is AssistantState.SHUTDOWN
