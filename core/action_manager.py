"""Builds all controllers and plugs every action handler into the CommandRouter.

This is the one place that knows about real Windows control. Tests build a router
with fake controllers instead, so automated tests never move your windows.
"""

from __future__ import annotations

from dataclasses import dataclass

from actions import (application_actions, browser_actions, keyboard_actions, media_actions, mouse_actions,
                     system_actions, window_actions)
from controllers.application_controller import ApplicationController
from controllers.browser_controller import BrowserController
from controllers.keyboard_controller import KeyboardController
from controllers.media_controller import MediaController
from controllers.mouse_controller import MouseController
from controllers.system_controller import SystemController
from controllers.window_controller import WindowController
from core.command_router import CommandRouter

MODULES = (application_actions, window_actions, mouse_actions, keyboard_actions, browser_actions, media_actions,
           system_actions)


@dataclass
class Controllers:
    apps: ApplicationController
    windows: WindowController
    keyboard: KeyboardController
    mouse: MouseController
    browser: BrowserController
    media: MediaController
    system: SystemController


def create_controllers() -> Controllers:
    from integrations.windows.windows_apps import AppCatalog

    windows = WindowController()
    windows.tracker.start()  # start remembering which window "this window" means
    catalog = AppCatalog()
    catalog.preload()  # read the Start menu in the background (~1 s)
    return Controllers(
        apps=ApplicationController(catalog, windows), windows=windows, keyboard=KeyboardController(windows),
        mouse=MouseController(windows), browser=BrowserController(), media=MediaController(),
        system=SystemController(),
    )


def build_router(controllers: Controllers | None, confirm=None, confirm_medium: bool = True) -> CommandRouter:
    """controllers=None -> dry run: everything is understood, nothing touches Windows."""
    router = CommandRouter(confirm=confirm, confirm_medium=confirm_medium)
    if controllers is not None:
        for module in MODULES:
            module.register(router, controllers)
    return router
