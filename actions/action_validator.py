"""Checks every Intent against the allowlist before anything can act on it.

Rule of thumb: treat AI output like input from a stranger on the internet.
It may be well-meaning, but it can be wrong, truncated, or (if someone manages to
inject instructions into it) hostile. So we check:

    - the action exists in the registry (allowlist)       -> else reject
    - no unexpected parameters                              -> else reject
    - required parameters are present                       -> else reject
    - each value has the right type and is within limits   -> else reject (or safely convert)

The result is a NEW, cleaned Intent. The original is never trusted afterwards.
"""

from __future__ import annotations

import re
import unicodedata
from urllib.parse import urlparse

from actions.action_registry import get_spec
from actions.action_schema import Intent, Param, ParamKind
from utils.exceptions import VoiceOSError


class ActionValidationError(VoiceOSError):
    """The intent is not allowed or its parameters are invalid."""


def _clean_text(value: object, param: Param) -> str:
    if not isinstance(value, (str, int, float)) or isinstance(value, bool):
        raise ActionValidationError(f"'{param.name}' must be text, got {type(value).__name__}")
    text = str(value)
    # Remove invisible control characters (e.g. newlines, escape codes) - they have no
    # business in an app name and are a classic trick for smuggling extra commands.
    text = "".join(ch for ch in text if unicodedata.category(ch)[0] != "C")
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        raise ActionValidationError(f"'{param.name}' is empty")
    if len(text) > param.max_length:
        raise ActionValidationError(f"'{param.name}' is too long ({len(text)} > {param.max_length} characters)")
    return text


def _clean_int(value: object, param: Param) -> int:
    if isinstance(value, bool):
        raise ActionValidationError(f"'{param.name}' must be a number")
    try:
        number = float(value)  # accepts 70, 70.0 and "70"
    except (TypeError, ValueError):
        raise ActionValidationError(f"'{param.name}' must be a number, got {value!r}") from None
    if not number.is_integer():
        raise ActionValidationError(f"'{param.name}' must be a whole number, got {value!r}")
    number = int(number)
    if param.minimum is not None and not param.minimum <= number <= param.maximum:
        raise ActionValidationError(f"'{param.name}' must be between {param.minimum} and {param.maximum}, got {number}")
    return number


def _clean_choice(value: object, param: Param) -> str:
    text = str(value).strip().lower().replace(" ", "_").replace("-", "_")
    if text not in param.choices:
        raise ActionValidationError(f"'{param.name}' must be one of {', '.join(param.choices)}; got {value!r}")
    return text


def _clean_url(value: object, param: Param) -> str:
    text = _clean_text(value, param)
    error = ActionValidationError(f"'{param.name}' must be a web address (http/https), got {value!r}")
    # Any OTHER scheme is refused outright: javascript:..., file:..., mailto:..., ms-settings:...
    # (A colon followed by a digit is a port, as in "localhost:8080", not a scheme.)
    has_scheme = re.match(r"^[a-z][a-z0-9+.-]*:(?!\d)", text, re.IGNORECASE)
    if has_scheme and not re.match(r"^https?://", text, re.IGNORECASE):
        raise error
    if not has_scheme:
        text = "https://" + text  # "youtube.com" -> "https://youtube.com"
    parsed = urlparse(text)
    # The host may only contain normal hostname characters (and an optional :port).
    if parsed.scheme not in ("http", "https") or not re.fullmatch(r"[A-Za-z0-9.-]+(:\d{1,5})?", parsed.netloc or ""):
        raise error
    return text


CLEANERS = {ParamKind.TEXT: _clean_text, ParamKind.INT: _clean_int, ParamKind.CHOICE: _clean_choice,
            ParamKind.URL: _clean_url}


def validate_intent(action: object, params: object = None) -> Intent:
    """Return a cleaned Intent, or raise ActionValidationError explaining what's wrong."""
    if not isinstance(action, str):
        raise ActionValidationError("Action name must be text")
    spec = get_spec(action.strip().upper())
    if spec is None:
        raise ActionValidationError(f"'{action}' is not an allowed action")
    params = {} if params is None else params
    if not isinstance(params, dict):
        raise ActionValidationError(f"Parameters for {spec.name} must be an object")

    allowed = {p.name for p in spec.params}
    unexpected = set(params) - allowed
    if unexpected:
        raise ActionValidationError(f"{spec.name} does not accept: {', '.join(sorted(map(str, unexpected)))}")

    clean = {}
    for param in spec.params:
        value = params.get(param.name)
        if value is None or (isinstance(value, str) and not value.strip()):
            if param.required:
                raise ActionValidationError(f"{spec.name} needs '{param.name}'")
            if param.default is not None:
                clean[param.name] = param.default
            continue
        clean[param.name] = CLEANERS[param.kind](value, param)
    return Intent(spec.name, clean)
