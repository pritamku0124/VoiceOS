"""Understands what you said: text -> list of validated Intents.

Two layers:
    1. RULES (this file): regular expressions for common commands. Instant, predictable,
       work offline with no AI. "open whatsapp", "volume to seventy percent", ...
    2. AI fallback (ai/ollama_client.py): only when no rule matches, e.g.
       "copy the report from downloads into my documents folder".

Compound commands: "open whatsapp and minimize chrome" is split on and/then, but ONLY
if every part is understood - otherwise "search for salt and pepper" would break apart.

Everything a rule produces still goes through action_validator, exactly like AI output.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field

from actions.action_schema import Intent
from actions.action_validator import ActionValidationError, validate_intent
from ai.conversation_manager import ConversationContext
from ai.entity_extractor import SEARCH_SITES, normalize_app, normalize_location, website_url, words_to_number

logger = logging.getLogger(__name__)

RuleFn = Callable[[re.Match, ConversationContext], "Intent | None"]
RULES: list[tuple[re.Pattern, RuleFn]] = []


def rule(pattern: str):
    """Decorator: registers the function below it as the handler for `pattern`.

    @rule(r"^mute$")
    def _mute(m, ctx): ...
    is the same as writing  RULES.append((re.compile(r"^mute$"), _mute))  after the function.
    """
    def register(fn: RuleFn) -> RuleFn:
        RULES.append((re.compile(pattern, re.IGNORECASE), fn))
        return fn

    return register


def I(action: str, **params) -> Intent:  # noqa: E743 - short helper name keeps the rules readable
    return Intent(action, {k: v for k, v in params.items() if v is not None})


PRONOUNS = {"it", "that", "this app", "that app", "this application"}
CURRENT = {"this", "this window", "the window", "current window", "the current window", "active window",
           "the active window", "window"}


def target_of(text: str, ctx: ConversationContext) -> str:
    t = text.strip().lower()
    if t in PRONOUNS:
        return ctx.resolve_target(t)
    if t in CURRENT:
        return "current"
    return normalize_app(text)


# ---- conversation & information ------------------------------------------------------------
@rule(r"^(hi|hello|hey|good (morning|afternoon|evening))( there)?$")
def _greet(m, ctx): return I("GREETING")


@rule(r"^(thanks|thank you)( very much| so much| a lot)?$")
def _thanks(m, ctx): return I("THANKS")


@rule(r"^(help|what can you do|what are you able to do|what do you do|what can i say)$")
def _help(m, ctx): return I("HELP")


@rule(r"^(what time is it( now)?|what'?s the time( now)?|what is the time( now)?|tell me the time|time)$")
def _time(m, ctx): return I("GET_TIME")


@rule(r"^(what'?s|what is) (the |today'?s )?date( today)?$|^what day is (it|today)( today)?$|^what is today$")
def _date(m, ctx): return I("GET_DATE")


@rule(r"^((what'?s|what is|check) (my |the )?battery( level| status| percentage)?|how much battery( is left| do i have)?)$")
def _battery(m, ctx): return I("GET_BATTERY")


# ---- system ----------------------------------------------------------------------------------
@rule(r"^(take|capture|grab) (a |the )?screen ?shot( of (the |my )?screen)?$")
def _screenshot(m, ctx): return I("TAKE_SCREENSHOT")


@rule(r"^lock (the |my )?(computer|screen|pc|windows|laptop)$")
def _lock(m, ctx): return I("LOCK_SCREEN")


SETTINGS_PAGES = {"display": "display", "screen": "display", "sound": "sound", "audio": "sound",
                  "bluetooth": "bluetooth", "wifi": "wifi", "wi fi": "wifi", "network": "wifi", "internet": "wifi",
                  "apps": "apps", "privacy": "privacy", "update": "update", "windows update": "update"}


@rule(r"^open (the )?(windows |system )?settings$")
def _settings(m, ctx): return I("OPEN_SETTINGS")


@rule(r"^open (the )?(" + "|".join(SETTINGS_PAGES) + r") settings$")
def _settings_page(m, ctx): return I("OPEN_SETTINGS", page=SETTINGS_PAGES[m.group(2).lower()])


# ---- volume & media ------------------------------------------------------------------------------
@rule(r"^(set|change|increase|decrease|raise|lower|turn|put|make) (the )?(volume|sound)( up| down)? to (?P<n>.+?)( percent|%)?$"
      r"|^(volume|sound) (to )?(?P<n2>.+?)( percent|%)$")
def _set_volume(m, ctx):
    level = words_to_number(m.group("n") or m.group("n2"))
    return I("SET_VOLUME", level=level) if level is not None else None


@rule(r"^((turn|increase|raise|lower|decrease|reduce) (the )?(volume|sound)( up| down)?|(turn )?(the )?volume (up|down)"
      r"|(make it |make the sound )?(louder|quieter|softer))$")
def _change_volume(m, ctx):
    text = m.group(0).lower()
    down = any(w in text for w in ("lower", "decrease", "reduce", "down", "quieter", "softer"))
    return I("CHANGE_VOLUME", direction="down" if down else "up")


@rule(r"^(mute|silence)( (the )?(sound|volume|audio|computer))?$")
def _mute(m, ctx): return I("MUTE")


@rule(r"^unmute( (the )?(sound|volume|audio|computer))?$")
def _unmute(m, ctx): return I("UNMUTE")


@rule(r"^(play|pause|resume)( the)?( music| song| video| media| playback)?$")
def _play_pause(m, ctx): return I("MEDIA_PLAY_PAUSE")


@rule(r"^(next|skip)( the)?( song| track| video)?$|^(play )?(the )?next (song|track|video)$")
def _next(m, ctx): return I("MEDIA_NEXT")


@rule(r"^(previous|last)( song| track| video)$|^(play |go to )?(the )?previous (song|track|video)$")
def _previous(m, ctx): return I("MEDIA_PREVIOUS")


# ---- mouse & keyboard ------------------------------------------------------------------------------
@rule(r"^scroll (up|down)( a (?P<size>lot|little|bit))?$")
def _scroll(m, ctx):
    size = (m.group("size") or "").lower()
    return I("MOUSE_SCROLL", direction=m.group(1).lower(), amount={"lot": 15, "little": 2, "bit": 2}.get(size, 5))


@rule(r"^(left )?click( here| it| that)?$")
def _click(m, ctx): return I("MOUSE_CLICK", button="left")


@rule(r"^(right|double|middle) click$")
def _click2(m, ctx): return I("MOUSE_CLICK", button=m.group(1).lower())


@rule(r"^move (the )?(mouse|cursor|pointer) (up|down|left|right)( a (?P<size>lot|little|bit))?$")
def _move_mouse(m, ctx):
    size = (m.group("size") or "").lower()
    return I("MOUSE_MOVE", direction=m.group(3).lower(), distance={"lot": 400, "little": 30, "bit": 30}.get(size, 100))


@rule(r"^(type|write|dictate) (?P<text>.+)$")
def _type(m, ctx): return I("TYPE_TEXT", text=m.group("text"))


KEYS = {"enter": "enter", "return": "enter", "escape": "escape", "esc": "escape", "tab": "tab", "space": "space",
        "spacebar": "space", "backspace": "backspace", "back space": "backspace", "delete": "delete", "up": "up",
        "down": "down", "left": "left", "right": "right", "home": "home", "end": "end", "page up": "page_up",
        "page down": "page_down", "f5": "f5", "f 5": "f5"}


@rule(r"^(press|hit) (the )?(?P<key>" + "|".join(sorted(KEYS, key=len, reverse=True)) + r")( key)?$")
def _press(m, ctx): return I("PRESS_KEY", key=KEYS[m.group("key").lower()])


SHORTCUTS = {"copy": "copy", "paste": "paste", "cut": "cut", "undo": "undo", "redo": "redo", "save": "save",
             "refresh": "refresh", "reload": "refresh", "find": "find"}


@rule(r"^(?P<s>copy|paste|cut|undo|redo|save|refresh|reload)( (this|that|it|the file|the page|text|the text|selection|the selection))?$")
def _shortcut(m, ctx): return I("KEYBOARD_SHORTCUT", shortcut=SHORTCUTS[m.group("s").lower()])


@rule(r"^select all( (the )?text)?$|^select everything$")
def _select_all(m, ctx): return I("KEYBOARD_SHORTCUT", shortcut="select_all")


# ---- browser ----------------------------------------------------------------------------------------
@rule(r"^(open )?(a )?new tab$")
def _new_tab(m, ctx): return I("NEW_TAB")


@rule(r"^close (this |the )?tab$")
def _close_tab(m, ctx): return I("CLOSE_TAB")


@rule(r"^(go to |switch to )?(the )?next tab$")
def _next_tab(m, ctx): return I("NEXT_TAB")


@rule(r"^(go to |switch to )?(the )?previous tab$")
def _prev_tab(m, ctx): return I("PREVIOUS_TAB")


@rule(r"^(go )?back( a page)?$")
def _back(m, ctx): return I("BROWSER_BACK")


@rule(r"^(go )?forward( a page)?$")
def _forward(m, ctx): return I("BROWSER_FORWARD")


SITE_GROUP = "(?P<site>" + "|".join(SEARCH_SITES) + ")"


@rule(r"^search " + SITE_GROUP + r" for (?P<q>.+)$|^search (for )?(?P<q2>.+?) on " + SITE_GROUP.replace("site", "site2") + "$")
def _search_site(m, ctx):
    return I("WEB_SEARCH", query=m.group("q") or m.group("q2"), site=(m.group("site") or m.group("site2")).lower())


@rule(r"^" + SITE_GROUP + r" (?P<q>.+)$")  # "google python tutorials", "youtube lofi music"
def _site_query(m, ctx): return I("WEB_SEARCH", query=m.group("q"), site=m.group("site").lower())


# ---- files (before generic search, so "look for my handos project" is a FILE search) ----------------
@rule(r"^(find|locate|look for|search for|where is|where's) (my |the )?(?P<q>.+?)( (?P<kind>project|folder|file|document)s?)?"
      r"( (on|in) (my |the )?(?P<loc>.+))?$")
def _find(m, ctx):
    if not (m.group("kind") or m.group(2) or m.group(1).lower() in ("find", "locate", "where is", "where's")):
        return None  # "search for robots" is a web search, not a file search
    query = m.group("q") + (f" {m.group('kind')}" if m.group("kind") else "")
    return I("FIND_FILE", query=query, location=normalize_location(m.group("loc")) if m.group("loc") else None)


# Longer alternatives FIRST: regex tries "a|b|c" left to right, so "search|search for" would match
# just "search" and leave "for" inside the query.
@rule(r"^(search for|google for|look up|search) (?P<q>.+?)( online| on the web| on the internet)?$")
def _search(m, ctx): return I("WEB_SEARCH", query=m.group("q"), site=ctx.last_site or "google")


@rule(r"^(create|make) (a )?(new )?(?P<kind>folder|directory|file)( named| called)? (?P<name>.+?)( (on|in|inside) (?P<loc>.+))?$")
def _create(m, ctx):
    action = "CREATE_FILE" if m.group("kind").lower() == "file" else "CREATE_FOLDER"
    return I(action, name=m.group("name"), location=normalize_location(m.group("loc")) if m.group("loc") else None)


# ---- windows & applications --------------------------------------------------------------------------
WINDOW_VERBS = {"minimize": "MINIMIZE_WINDOW", "minimise": "MINIMIZE_WINDOW", "maximize": "MAXIMIZE_WINDOW",
                "maximise": "MAXIMIZE_WINDOW", "restore": "RESTORE_WINDOW"}


@rule(r"^(?P<v>minimize|minimise|maximize|maximise|restore) (?P<t>.+)$")
def _window(m, ctx): return I(WINDOW_VERBS[m.group("v").lower()], target=target_of(m.group("t"), ctx))


@rule(r"^(snap|move|put) (?P<t>.+?) to the (?P<p>left|right|top|bottom)( side)?( of the screen)?$")
def _snap(m, ctx): return I("SNAP_WINDOW", target=target_of(m.group("t"), ctx), position=m.group("p").lower())


@rule(r"^(what|which) (apps|applications|programs|windows) are (currently )?(running|open)( right now)?$"
      r"|^(list|show) (me )?(the |all )?(running|open) (apps|applications|programs|windows)$")
def _list_apps(m, ctx): return I("LIST_APPLICATIONS")


@rule(r"^(close|quit|exit|kill) (?P<t>.+)$")
def _close(m, ctx):
    t = m.group("t").strip().lower()
    if t in CURRENT:
        return I("CLOSE_WINDOW", target="current")
    if t in PRONOUNS:
        return I("CLOSE_APPLICATION", app=ctx.resolve_target(t)) if ctx.last_app else I("CLOSE_WINDOW", target="current")
    return I("CLOSE_APPLICATION", app=normalize_app(m.group("t")))


# Not "show me ..." - real test: "show me what is on my screen" became SWITCH_APPLICATION.
@rule(r"^(switch|go|change|bring up) (to )?(?P<t>.+)$")
def _switch(m, ctx):
    url = website_url(m.group("t"))
    if url:
        return I("OPEN_WEBSITE", url=url)
    if not m.group(2) and m.group(1).lower() in ("switch", "change", "go"):
        return None  # "go home"? too vague without "to"
    return I("SWITCH_APPLICATION", app=target_of(m.group("t"), ctx))


@rule(r"^(open|launch|start|run|visit|go to|navigate to) (up )?(?P<t>.+)$")
def _open(m, ctx):
    t = m.group("t")
    url = website_url(t)
    if url:
        return I("OPEN_WEBSITE", url=url)
    if re.search(r"\b(my|project|folder|file|document|drive)\b", t, re.IGNORECASE):
        return None  # "open my handos project" needs a file search - let the AI plan it
    return I("OPEN_APPLICATION", app=normalize_app(t))


# ---- the recognizer --------------------------------------------------------------------------------------
FILLERS = re.compile(r"^(please |can you |could you |would you |will you |i want to |i'd like to |i would like to |"
                     r"jarvis |voiceos |ok |okay |now |just )+|( please| for me| now)+$", re.IGNORECASE)
SPLIT = re.compile(r",? (?:and then|and also|and|then|after that|also) ", re.IGNORECASE)


def normalize(text: str) -> str:
    text = re.sub(r"[.!?]+$", "", text.strip())
    text = re.sub(r"\s+", " ", text)
    previous = None
    while previous != text:  # remove several fillers: "please can you just open..."
        previous = text
        text = FILLERS.sub("", text).strip()
    return text


@dataclass
class Recognition:
    intents: list[Intent]
    source: str  # "rules", "ai" or "none"
    answer: str = ""  # direct answer from the AI to a question that needs no action
    errors: list[str] = field(default_factory=list)
    raw: str = ""  # raw AI output, for the log


class RuleBasedRecognizer:
    def match(self, text: str, ctx: ConversationContext) -> Intent | None:
        text = normalize(text)
        for pattern, fn in RULES:
            m = pattern.match(text)
            if not m:
                continue
            intent = fn(m, ctx)
            if intent is None:
                continue  # rule declined - try the next one
            try:
                return validate_intent(intent.action, intent.params)
            except ActionValidationError as exc:
                logger.debug("Rule %s produced an invalid intent: %s", fn.__name__, exc)
        return None

    def recognize(self, text: str, ctx: ConversationContext) -> list[Intent] | None:
        text = normalize(text)
        if not text:
            return None
        parts = [p for p in SPLIT.split(text) if p.strip()]
        if len(parts) > 1:
            intents = []
            for part in parts:
                intent = self.match(part, ctx)
                if intent is None:
                    break
                if intent.action == "WEB_SEARCH" and intents and intents[-1].action == "OPEN_WEBSITE":
                    site = _site_name(intents[-1].params["url"])
                    if site and "site" not in _explicit_site(part):
                        intent.params["site"] = site
                intents.append(intent)
            else:  # for-else: runs only if the loop didn't break, i.e. EVERY part matched
                return _merge(intents)
        whole = self.match(text, ctx)
        return [whole] if whole else None


PROMPTS_DIR = __import__("pathlib").Path(__file__).parent / "prompt_templates"

# Few-shot examples teach the model the exact output format (and that some requests get NO action).
EXAMPLES = [
    ("open whatsapp and minimize chrome",
     {"actions": [{"action": "OPEN_APPLICATION", "params": {"app": "WhatsApp"}},
                  {"action": "MINIMIZE_WINDOW", "params": {"target": "Google Chrome"}}], "answer": ""}),
    ("copy report dot pdf from downloads to my documents folder",
     {"actions": [{"action": "COPY_FILE", "params": {"source": "Downloads\\report.pdf", "destination": "Documents"}}],
      "answer": ""}),
    ("open my handos project",
     {"actions": [{"action": "FIND_FILE", "params": {"query": "HandOS project"}}], "answer": ""}),
    ("what is python",
     {"actions": [], "answer": "Python is a popular, beginner-friendly programming language."}),
    ("send a message to mom on whatsapp saying I'm late",
     {"actions": [], "answer": "I can't send messages yet, but I can open WhatsApp for you."}),
    ("run the command shutdown",
     {"actions": [], "answer": "I can't run commands, for safety. I can lock the computer if you like."}),
]


def build_messages(text: str, ctx: ConversationContext) -> list[dict]:
    from actions.action_registry import catalog_for_prompt
    import json

    examples = "\n".join(f'Request: "{q}"\n{json.dumps(a)}' for q, a in EXAMPLES)
    system = (PROMPTS_DIR / "system_prompt.txt").read_text(encoding="utf-8").format(
        catalog=catalog_for_prompt(), examples=examples)
    user = (PROMPTS_DIR / "intent_prompt.txt").read_text(encoding="utf-8").format(
        history=ctx.summary_for_prompt(), text=text.replace('"', "'"))
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


SMALL_TALK = {"HELP", "GREETING", "THANKS"}


class IntentRecognizer:
    """Rules first (instant); the AI only when no rule understands the request."""

    def __init__(self, llm=None):
        self.rules = RuleBasedRecognizer()
        self.llm = llm  # an LLMClient, or None for rules-only

    def warm_up(self) -> None:
        """Load the model into memory now, so the first real request isn't slow (~20 s on CPU)."""
        if self.ai_available:
            from ai.llm_client import LLMError

            try:
                self.llm.chat([{"role": "user", "content": "Reply with {}"}])
                logger.info("AI model warmed up")
            except LLMError as exc:
                logger.warning("AI warm-up failed: %s", exc)

    @property
    def ai_available(self) -> bool:
        return self.llm is not None and self.llm.is_available()

    def recognize(self, text: str, ctx: ConversationContext) -> Recognition:
        intents = self.rules.recognize(text, ctx)
        if intents:
            return Recognition(intents, "rules")
        if not self.ai_available:
            return Recognition([], "none")

        from ai.intent_parser import parse_llm_reply
        from ai.llm_client import LLMError

        try:
            raw = self.llm.chat(build_messages(normalize(text), ctx))
        except LLMError as exc:
            logger.warning("AI request failed: %s", exc)
            return Recognition([], "none", errors=[str(exc)])
        parsed = parse_llm_reply(raw)
        # Real test: "what is an embedded system" came back as HELP + a correct answer. When the
        # only actions are small talk but there IS an answer, the answer is what the user wants.
        if parsed.answer and parsed.intents and all(i.action in SMALL_TALK for i in parsed.intents):
            parsed.intents = []
        from safety.command_filter import filter_ai_plan

        parsed.intents, removed = filter_ai_plan(parsed.intents, text)
        parsed.errors += removed
        if parsed.intents or parsed.errors:
            # An answer next to actions tends to claim they already happened; and if something
            # was rejected, the answer may describe the rejected thing ("Here's a screenshot").
            parsed.answer = ""
        for error in parsed.errors:
            logger.warning("Rejected from AI reply: %s", error)
        logger.info("AI interpreted %r as %s (answer=%r)", text, [str(i) for i in parsed.intents], parsed.answer)
        return Recognition(parsed.intents, "ai", parsed.answer, parsed.errors, raw)


def _site_name(url: str) -> str | None:
    host = re.sub(r"^https?://(www\.)?", "", url).split("/")[0].split(".")[0]
    return host if host in SEARCH_SITES else None


def _explicit_site(part: str) -> dict:
    return {"site": True} if re.search(" on (" + "|".join(SEARCH_SITES) + ")$", part, re.IGNORECASE) else {}


def _merge(intents: list[Intent]) -> list[Intent]:
    """'open youtube' + 'search youtube for X' -> just the search (it opens YouTube anyway)."""
    merged: list[Intent] = []
    for intent in intents:
        if (merged and intent.action == "WEB_SEARCH" and merged[-1].action == "OPEN_WEBSITE"
                and _site_name(merged[-1].params["url"]) == intent.params.get("site")):
            merged[-1] = intent
        else:
            merged.append(intent)
    return merged
