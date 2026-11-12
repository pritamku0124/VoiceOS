"""The ALLOWLIST: every action VoiceOS is permitted to perform. Nothing else can ever run.

This is the most important safety idea in the project:
    The AI does not write code or commands. It may only *choose* from this list and
    fill in parameters, and every choice is checked by action_validator.py. A request
    the list can't express is answered with "I can't do that", never improvised.

To add a capability later: add an ActionSpec here, then a handler in Phase 6/7.
"""

from __future__ import annotations

from actions.action_schema import ActionSpec, Param, ParamKind, Risk

T, I, C, U = ParamKind.TEXT, ParamKind.INT, ParamKind.CHOICE, ParamKind.URL

TARGET = Param("target", T, required=False, default="current",
               description='window/app name, or "current" for the active window')
DIRECTION_UD = Param("direction", C, choices=("up", "down"))
SITES = ("google", "youtube", "bing", "wikipedia", "github", "amazon")

ACTIONS: tuple[ActionSpec, ...] = (
    # --- Applications -----------------------------------------------------------------------
    ActionSpec("OPEN_APPLICATION", "Applications", "Launch an installed application.", "open {app}",
               (Param("app", T, description="application name, e.g. WhatsApp"),),
               examples=("open whatsapp", "launch visual studio code")),
    ActionSpec("CLOSE_APPLICATION", "Applications", "Close a running application.", "close {app}",
               (Param("app", T),), Risk.MEDIUM, examples=("close chrome",)),
    ActionSpec("SWITCH_APPLICATION", "Applications", "Bring a running application to the front.", "switch to {app}",
               (Param("app", T),), examples=("switch to chrome",)),
    ActionSpec("LIST_APPLICATIONS", "Applications", "Say which applications are running.", "list running applications",
               examples=("which applications are running",)),
    # --- Window management ------------------------------------------------------------------
    ActionSpec("MINIMIZE_WINDOW", "Window management", "Minimize a window.", "minimize {target}", (TARGET,),
               examples=("minimize this window", "minimize chrome")),
    ActionSpec("MAXIMIZE_WINDOW", "Window management", "Maximize a window.", "maximize {target}", (TARGET,)),
    ActionSpec("RESTORE_WINDOW", "Window management", "Restore a minimized/maximized window.", "restore {target}", (TARGET,)),
    ActionSpec("CLOSE_WINDOW", "Window management", "Close a window.", "close {target}", (TARGET,), Risk.MEDIUM,
               examples=("close this window",)),
    ActionSpec("SNAP_WINDOW", "Window management", "Snap a window to one side of the screen.",
               "snap {target} to the {position}",
               (TARGET, Param("position", C, choices=("left", "right", "top", "bottom")))),
    # --- Mouse ------------------------------------------------------------------------------
    ActionSpec("MOUSE_CLICK", "Mouse control", "Click the mouse at its current position.", "{button} click",
               (Param("button", C, required=False, default="left", choices=("left", "right", "double", "middle")),)),
    ActionSpec("MOUSE_SCROLL", "Mouse control", "Scroll the page or window under the mouse.", "scroll {direction}",
               (DIRECTION_UD, Param("amount", I, required=False, default=5, minimum=1, maximum=50)),
               examples=("scroll down",)),
    ActionSpec("MOUSE_MOVE", "Mouse control", "Move the mouse pointer in a direction.", "move the mouse {direction}",
               (Param("direction", C, choices=("up", "down", "left", "right")),
                Param("distance", I, required=False, default=100, minimum=1, maximum=2000))),
    # --- Keyboard ---------------------------------------------------------------------------
    ActionSpec("TYPE_TEXT", "Keyboard control", "Type text into the active window.", 'type "{text}"',
               (Param("text", T, max_length=1000),), examples=("type hello world",)),
    ActionSpec("PRESS_KEY", "Keyboard control", "Press one key.", "press {key}",
               (Param("key", C, choices=("enter", "escape", "tab", "space", "backspace", "delete", "up", "down",
                                          "left", "right", "home", "end", "page_up", "page_down", "f5")),)),
    ActionSpec("KEYBOARD_SHORTCUT", "Keyboard control", "Run a common editing shortcut.", "{shortcut}",
               (Param("shortcut", C, choices=("copy", "paste", "cut", "undo", "redo", "select_all", "save",
                                               "find", "refresh")),),
               examples=("copy this", "select all")),
    # --- Files and folders ------------------------------------------------------------------
    ActionSpec("CREATE_FOLDER", "Files and folders", "Create a new folder.", "create folder {name} in {location}",
               (Param("name", T, max_length=120), Param("location", T, required=False, default="Desktop")),
               phase=7, examples=("create a folder named electronics on my d drive",)),
    ActionSpec("CREATE_FILE", "Files and folders", "Create a new empty file.", "create file {name} in {location}",
               (Param("name", T, max_length=120), Param("location", T, required=False, default="Desktop")), phase=7),
    ActionSpec("FIND_FILE", "Files and folders", "Search for files or folders by name.", "find {query}",
               (Param("query", T), Param("location", T, required=False)), phase=7,
               examples=("find my handos project",)),
    ActionSpec("OPEN_FILE", "Files and folders", "Open a file or folder.", "open file {path}", (Param("path", T),),
               phase=7),
    ActionSpec("RENAME_FILE", "Files and folders", "Rename a file or folder.", "rename {source} to {new_name}",
               (Param("source", T), Param("new_name", T, max_length=120)), Risk.MEDIUM, phase=7),
    ActionSpec("COPY_FILE", "Files and folders", "Copy a file or folder.", "copy {source} to {destination}",
               (Param("source", T), Param("destination", T)), Risk.MEDIUM, phase=7),
    ActionSpec("MOVE_FILE", "Files and folders", "Move a file or folder.", "move {source} to {destination}",
               (Param("source", T), Param("destination", T)), Risk.MEDIUM, phase=7),
    ActionSpec("DELETE_FILE", "Files and folders", "Delete a file or folder (always asks first).", "delete {path}",
               (Param("path", T),), Risk.HIGH, phase=7),
    # --- Browser ----------------------------------------------------------------------------
    ActionSpec("OPEN_WEBSITE", "Browser control", "Open a website in the default browser.", "open {url}",
               (Param("url", U),), phase=6, examples=("open youtube",)),
    ActionSpec("WEB_SEARCH", "Browser control", "Search the web or a specific site.", "search {site} for {query}",
               (Param("query", T), Param("site", C, required=False, default="google", choices=SITES)), phase=6,
               examples=("search youtube for embedded systems", "google python tutorials")),
    ActionSpec("NEW_TAB", "Browser control", "Open a new browser tab.", "open a new tab", phase=6),
    ActionSpec("CLOSE_TAB", "Browser control", "Close the current browser tab.", "close the tab", phase=6),
    ActionSpec("NEXT_TAB", "Browser control", "Switch to the next tab.", "next tab", phase=6),
    ActionSpec("PREVIOUS_TAB", "Browser control", "Switch to the previous tab.", "previous tab", phase=6),
    ActionSpec("BROWSER_BACK", "Browser control", "Go back a page.", "go back", phase=6),
    ActionSpec("BROWSER_FORWARD", "Browser control", "Go forward a page.", "go forward", phase=6),
    # --- Media and volume -------------------------------------------------------------------
    ActionSpec("MEDIA_PLAY_PAUSE", "Media control", "Play or pause media.", "play/pause", phase=6),
    ActionSpec("MEDIA_NEXT", "Media control", "Next track.", "next track", phase=6),
    ActionSpec("MEDIA_PREVIOUS", "Media control", "Previous track.", "previous track", phase=6),
    ActionSpec("SET_VOLUME", "Volume control", "Set the volume to a percentage.", "set the volume to {level}%",
               (Param("level", I, minimum=0, maximum=100),), phase=7,
               examples=("increase the volume to 70 percent",)),
    ActionSpec("CHANGE_VOLUME", "Volume control", "Turn the volume up or down.", "turn the volume {direction}",
               (DIRECTION_UD, Param("amount", I, required=False, default=10, minimum=1, maximum=100)), phase=6),
    ActionSpec("MUTE", "Volume control", "Mute the sound.", "mute", phase=7),
    ActionSpec("UNMUTE", "Volume control", "Unmute the sound.", "unmute", phase=7),
    # --- System -----------------------------------------------------------------------------
    ActionSpec("TAKE_SCREENSHOT", "System operations", "Save a screenshot.", "take a screenshot", phase=7),
    ActionSpec("GET_BATTERY", "System operations", "Say the battery level.", "check the battery", phase=6),
    ActionSpec("GET_TIME", "System operations", "Say the current time.", "tell the time", phase=5),
    ActionSpec("GET_DATE", "System operations", "Say today's date.", "tell the date", phase=5),
    ActionSpec("OPEN_SETTINGS", "System operations", "Open Windows Settings.", "open Windows settings {page}",
               (Param("page", C, required=False, default="home",
                      choices=("home", "display", "sound", "bluetooth", "wifi", "apps", "privacy", "update")),),
               phase=6),
    ActionSpec("LOCK_SCREEN", "System operations", "Lock Windows (always asks first).", "lock the computer",
               risk=Risk.HIGH, phase=6),
    # --- Assistant (talking with VoiceOS itself) --------------------------------------------
    ActionSpec("HELP", "AI assistance", "Explain what VoiceOS can do.", "explain what I can do", phase=5),
    ActionSpec("GREETING", "AI assistance", "Respond to a greeting.", "say hello", phase=5),
    ActionSpec("THANKS", "AI assistance", "Respond to thanks.", "say you're welcome", phase=5),
)

REGISTRY: dict[str, ActionSpec] = {spec.name: spec for spec in ACTIONS}


def get_spec(name: str) -> ActionSpec | None:
    return REGISTRY.get(name)


def categories() -> dict[str, list[ActionSpec]]:
    grouped: dict[str, list[ActionSpec]] = {}
    for spec in ACTIONS:
        grouped.setdefault(spec.category, []).append(spec)
    return grouped


def catalog_for_prompt() -> str:
    """The action list in a compact text form for the AI prompt (generated, so it never goes stale)."""
    lines = []
    for spec in ACTIONS:
        params = []
        for p in spec.params:
            kind = "|".join(p.choices) if p.choices else p.kind.value
            if p.minimum is not None:
                kind += f" {p.minimum}-{p.maximum}"
            params.append(f"{p.name}{'' if p.required else '?'}: {kind}")
        lines.append(f"- {spec.name}({', '.join(params)}): {spec.description}")
    return "\n".join(lines)
