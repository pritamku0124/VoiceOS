"""Publish/subscribe event bus so modules communicate without importing each other directly.

Status: planned for Phase 5 (AI intent recognition). In Phase 2, Qt signals on
VoiceManager were enough; a central bus becomes useful once voice, AI, actions and
history all need to react to the same events.
"""
