"""Turns a raw RecognitionResult into clean text and decides whether to trust it.

Why reject anything?
    Later phases will ACT on this text (open apps, move files). Acting on a
    mis-heard command is worse than asking the user to repeat. So low-confidence
    or empty results are marked accepted=False with a human-readable reason.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from voice.speech_recognition import RecognitionResult

FILLER_WORDS = {"um", "uh", "er", "erm", "hmm", "ah", "mm"}
# Vosk often hears a lone "the" or "huh" in background noise.
NOISE_ONLY = {"the", "huh", "a", "i", "but", "and"}


@dataclass
class ProcessedSpeech:
    text: str  # cleaned text ("" if nothing usable)
    raw_text: str
    confidence: float
    accepted: bool
    reason: str = ""  # why it was rejected, shown to the user


# The speech model spells some brand names as separate words. Fix the common ones so
# later phases can match app names. \b = "word boundary", so "you tube" inside
# "your tuber" is not touched.
CORRECTIONS = {
    r"\byou tube\b": "YouTube",
    r"\bwhats? app\b": "WhatsApp",
    r"\bnote ?pad\b": "Notepad",  # " ?" = optional space: matches "notepad" and "note pad"
    r"\bvisual studio code\b": "Visual Studio Code",
    r"\bv s code\b": "VS Code",
    r"\bchrome\b": "Chrome",
}


def clean_transcript(text: str) -> str:
    words = re.sub(r"\s+", " ", text).strip().split(" ")
    words = [w for w in words if w and w.lower() not in FILLER_WORDS]
    cleaned = " ".join(words)
    for pattern, replacement in CORRECTIONS.items():
        cleaned = re.sub(pattern, replacement, cleaned, flags=re.IGNORECASE)
    return cleaned[:1].upper() + cleaned[1:] if cleaned else ""


def process_result(result: RecognitionResult | None, min_confidence: float) -> ProcessedSpeech:
    if result is None:
        return ProcessedSpeech("", "", 0.0, accepted=False, reason="I didn't hear anything.")

    cleaned = clean_transcript(result.text)
    if not cleaned or cleaned.lower() in NOISE_ONLY:
        return ProcessedSpeech("", result.text, result.confidence, False, "I couldn't make out any words.")
    if result.confidence < min_confidence:
        return ProcessedSpeech(
            cleaned, result.text, result.confidence, False,
            f"I'm not sure I heard that right ({result.confidence:.0%} confident). Please repeat.",
        )
    return ProcessedSpeech(cleaned, result.text, result.confidence, accepted=True)
