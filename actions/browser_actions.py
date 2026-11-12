"""Handlers for OPEN_WEBSITE, WEB_SEARCH and the tab / back / forward shortcuts."""

from __future__ import annotations

from urllib.parse import urlparse

from actions.action_schema import Intent


def register(router, c) -> None:
    def open_site(i: Intent) -> str:
        c.browser.open_url(i.params["url"])
        host = urlparse(i.params["url"]).netloc.removeprefix("www.")
        return f"Opening {host}."

    def search(i: Intent) -> str:
        site = i.params.get("site", "google")
        c.browser.search(i.params["query"], site)
        return f"Searching {site.capitalize()} for {i.params['query']}."

    def key(shortcut: str, said: str):
        def handler(i: Intent) -> str:
            c.keyboard.shortcut(shortcut)
            return said
        return handler

    router.register("OPEN_WEBSITE", open_site)
    router.register("WEB_SEARCH", search)
    router.register("NEW_TAB", key("new_tab", "New tab."))
    router.register("CLOSE_TAB", key("close_tab", "Tab closed."))
    router.register("NEXT_TAB", key("next_tab", "Next tab."))
    router.register("PREVIOUS_TAB", key("previous_tab", "Previous tab."))
    router.register("BROWSER_BACK", key("back", "Going back."))
    router.register("BROWSER_FORWARD", key("forward", "Going forward."))
