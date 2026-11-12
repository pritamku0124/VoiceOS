"""Open websites and searches in your default browser.

Python's built-in `webbrowser` module hands the URL to Windows, which opens it in
whatever browser you've set as default. Tab and back/forward commands are keyboard
shortcuts sent to the browser window (see keyboard_controller.SHORTCUTS).
"""

from __future__ import annotations

import webbrowser
from urllib.parse import quote_plus

SEARCH_URLS = {
    "google": "https://www.google.com/search?q={}",
    "youtube": "https://www.youtube.com/results?search_query={}",
    "bing": "https://www.bing.com/search?q={}",
    "wikipedia": "https://en.wikipedia.org/w/index.php?search={}",
    "github": "https://github.com/search?q={}",
    "amazon": "https://www.amazon.in/s?k={}",
}


def search_url(query: str, site: str = "google") -> str:
    # quote_plus makes the text safe inside a URL: "c++ & you" -> "c%2B%2B+%26+you"
    return SEARCH_URLS[site].format(quote_plus(query))


class BrowserController:
    def __init__(self, opener=webbrowser.open):
        self._open = opener

    def open_url(self, url: str) -> None:
        self._open(url)  # url was already checked by action_validator (http/https only)

    def search(self, query: str, site: str = "google") -> str:
        url = search_url(query, site)
        self._open(url)
        return url
