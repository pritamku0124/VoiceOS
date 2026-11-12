"""Turns spoken words into clean parameter values.

Speech recognisers write what they HEAR, not what you'd type:
    "seventy five percent"      -> 75
    "visual studio code"        -> "Visual Studio Code"
    "github dot com"            -> "https://github.com"
    "my d drive"                -> "D:\\"
"""

from __future__ import annotations

import re

# ---- numbers ---------------------------------------------------------------------------
UNITS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
    "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
}
TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}


def words_to_number(text: str) -> int | None:
    """'70' / 'seventy' / 'seventy five' / 'one hundred' / 'half' -> int, else None."""
    text = text.lower().replace("-", " ").replace("percent", "").replace("%", "").strip()
    if re.fullmatch(r"\d+", text):
        return int(text)
    if text in ("half", "a half"):
        return 50
    if text in ("max", "maximum", "full"):
        return 100
    total, seen = 0, False
    for word in text.split():
        if word in ("and", "a"):
            continue
        if word in UNITS:
            total += UNITS[word]
        elif word in TENS:
            total += TENS[word]
        elif word == "hundred":
            total = (total or 1) * 100
        else:
            return None
        seen = True
    return total if seen else None


# ---- applications ----------------------------------------------------------------------
# spoken form -> the name Windows shows. Phase 6 maps these names to real programs.
APP_ALIASES = {
    "chrome": "Google Chrome", "google chrome": "Google Chrome",
    "edge": "Microsoft Edge", "microsoft edge": "Microsoft Edge",
    "firefox": "Firefox", "brave": "Brave",
    "vs code": "Visual Studio Code", "v s code": "Visual Studio Code", "vscode": "Visual Studio Code",
    "visual studio code": "Visual Studio Code", "code": "Visual Studio Code",
    "whatsapp": "WhatsApp", "whats app": "WhatsApp", "what's app": "WhatsApp",
    "notepad": "Notepad", "note pad": "Notepad", "calculator": "Calculator", "paint": "Paint",
    "file explorer": "File Explorer", "explorer": "File Explorer", "files": "File Explorer",
    "my files": "File Explorer", "this pc": "File Explorer",
    "word": "Microsoft Word", "microsoft word": "Microsoft Word", "excel": "Microsoft Excel",
    "powerpoint": "Microsoft PowerPoint", "power point": "Microsoft PowerPoint", "outlook": "Outlook",
    "teams": "Microsoft Teams", "spotify": "Spotify", "discord": "Discord", "telegram": "Telegram",
    "zoom": "Zoom", "terminal": "Terminal", "windows terminal": "Terminal", "command prompt": "Command Prompt",
    "cmd": "Command Prompt", "powershell": "PowerShell", "power shell": "PowerShell",
    "task manager": "Task Manager", "control panel": "Control Panel", "camera": "Camera",
    "photos": "Photos", "clock": "Clock", "snipping tool": "Snipping Tool", "voiceos": "VoiceOS",
}


def normalize_app(name: str) -> str:
    name = re.sub(r"^(the|my)\s+", "", name.strip(), flags=re.IGNORECASE)
    name = re.sub(r"\s+(app|application|program)$", "", name, flags=re.IGNORECASE)
    key = name.lower()
    return APP_ALIASES.get(key, " ".join(w[:1].upper() + w[1:] for w in name.split()))


# ---- websites --------------------------------------------------------------------------
WEBSITES = {
    "youtube": "https://www.youtube.com", "you tube": "https://www.youtube.com",
    "google": "https://www.google.com", "gmail": "https://mail.google.com", "github": "https://github.com",
    "wikipedia": "https://www.wikipedia.org", "amazon": "https://www.amazon.in", "netflix": "https://www.netflix.com",
    "linkedin": "https://www.linkedin.com", "stack overflow": "https://stackoverflow.com",
    "stackoverflow": "https://stackoverflow.com", "chatgpt": "https://chatgpt.com", "chat gpt": "https://chatgpt.com",
    "claude": "https://claude.ai", "instagram": "https://www.instagram.com", "facebook": "https://www.facebook.com",
    "twitter": "https://x.com", "reddit": "https://www.reddit.com", "google maps": "https://maps.google.com",
    "maps": "https://maps.google.com", "whatsapp web": "https://web.whatsapp.com",
}
SEARCH_SITES = {"google", "youtube", "bing", "wikipedia", "github", "amazon"}


def website_url(name: str) -> str | None:
    """Known site name or spoken domain ('github dot com') -> URL, else None."""
    key = re.sub(r"\s+(website|site|dot com)$", lambda m: " dot com" if "dot" in m.group(0) else "",
                 name.strip().lower())
    key = re.sub(r"^(the)\s+", "", key)
    if key in WEBSITES:
        return WEBSITES[key]
    spoken = re.sub(r"\s+dot\s+", ".", key)  # "github dot com" -> "github.com"
    if re.fullmatch(r"[a-z0-9-]+(\.[a-z0-9-]+)+(/\S*)?", spoken):
        return "https://" + spoken
    return None


# ---- places ----------------------------------------------------------------------------
KNOWN_FOLDERS = {"desktop": "Desktop", "documents": "Documents", "document": "Documents",
                 "downloads": "Downloads", "download": "Downloads", "pictures": "Pictures", "music": "Music",
                 "videos": "Videos", "home": "Home"}


def normalize_location(text: str) -> str:
    """'my d drive' -> 'D:\\', 'the desktop' -> 'Desktop', anything else -> as spoken."""
    t = re.sub(r"^(on|in|inside|to|into)\s+", "", text.strip().lower())
    t = re.sub(r"^(my|the)\s+", "", t)
    t = re.sub(r"\s+folder$", "", t)
    drive = re.fullmatch(r"(?:drive\s+([a-z])|([a-z])\s+drive)", t)
    if drive:
        return f"{(drive.group(1) or drive.group(2)).upper()}:\\"
    return KNOWN_FOLDERS.get(t, text.strip())
