"""Playwright browser automation layer with cycle-safe lazy exports."""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .controller import BrowserController, PageState

__all__ = ["BrowserController", "PageState"]


def __getattr__(name: str) -> Any:
    if name in __all__:
        from .controller import BrowserController, PageState

        return {"BrowserController": BrowserController, "PageState": PageState}[name]
    raise AttributeError(name)
