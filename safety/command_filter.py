"""Deterministic rules that AI-produced plans must pass (the start of the Phase 8 safety layer).

Why code and not just prompt instructions?
    Real test (Phase 5) with qwen2.5:1.5b, even after the prompt said "never work around
    missing abilities":
        "send a message to rahul on whatsapp"  -> OPEN_APPLICATION(WhatsApp) + TYPE_TEXT("Hello Rahul, I am here.")
        "run the command format c drive"       -> OPEN_APPLICATION(Command Prompt)
    Every action was on the allowlist, but the COMBINATION was not what the user should
    get without asking. A prompt is a request; this file is a guarantee.

Policies (apply to AI plans only - commands understood by the explicit rules are what
the user literally said):
    1. The AI may not put words in your mouth: TYPE_TEXT is kept only if its text was
       actually spoken by the user.
    2. The AI may not open command shells or system tools that can run arbitrary commands.

Phase 8 adds risk-based confirmation (delete, close, lock...) for ALL plans.
"""

from __future__ import annotations

import re

from actions.action_schema import Intent

SHELL_APPS = {"command prompt", "cmd", "powershell", "windows powershell", "terminal", "windows terminal",
              "registry editor", "regedit", "run", "group policy editor", "gpedit"}


def _words(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9']+", text.lower()))


def filter_ai_plan(intents: list[Intent], user_text: str) -> tuple[list[Intent], list[str]]:
    """Return (allowed intents, reasons for anything removed)."""
    spoken = _words(user_text)
    kept, removed = [], []
    for intent in intents:
        if intent.action == "TYPE_TEXT" and _words(intent.params.get("text", "")) not in spoken:
            removed.append(f"Refused to type text you didn't dictate: {intent.params.get('text')!r}")
        elif intent.action in ("OPEN_APPLICATION", "SWITCH_APPLICATION") and \
                intent.params.get("app", "").lower() in SHELL_APPS:
            removed.append(f"The AI may not open {intent.params['app']} (it can run arbitrary commands). "
                           f"Say \"open {intent.params['app'].lower()}\" yourself if you want it.")
        else:
            kept.append(intent)
    return kept, removed
