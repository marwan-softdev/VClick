"""Fullscreen overlays for picking a region and a click point.

Both helpers put a *light* semi-transparent window over the whole virtual
desktop so the user can see their **live** screen through it (a compositor
blends whatever is behind the window in real time) and select directly on top
of it.  They block until the user finishes and return absolute screen
coordinates, or ``None`` if cancelled with Escape / right-click.

Tkinter is imported lazily so importing this module never requires a display.
"""

from __future__ import annotations

from typing import Optional, Tuple

from .capture import get_virtual_geometry
from .config import Region

_INSTRUCTION_FONT = ("Sans", 15, "bold")
_HINT = "#ffffff"
_ACCENT = "#28e07a"
# A light tint: low enough that live screen content stays clearly visible,
# high enough to signal "selection mode".
_OVERLAY_ALPHA = 0.25


def _make_overlay(root):
    """Create a borderless, lightly-tinted Toplevel covering all monitors."""
    import tkinter as tk

    geo = get_virtual_geometry()
    top = tk.Toplevel(root)
    top.overrideredirect(True)
    top.attributes("-topmost", True)
    try:
        top.attributes("-alpha", _OVERLAY_ALPHA)
    except tk.TclError:  # pragma: no cover - some WMs lack alpha
        pass
    top.configure(bg="black", cursor="crosshair")
    top.geometry(f"{geo['width']}x{geo['height']}+{geo['left']}+{geo['top']}")
    canvas = tk.Canvas(top, bg="black", highlightthickness=0, cursor="crosshair")
    canvas.pack(fill="both", expand=True)

    # Make keyboard input actually reach us.  An override-redirect window is
    # easy for a WM to skip for focus, so we grab input and force focus; the
    # Escape handler is installed by the caller via _bind_cancel().
    top.grab_set()
    top.focus_force()
    canvas.focus_set()
    return top, canvas, geo


def _bind_cancel(top, canvas, close):
    """Wire up every reliable way to cancel: Esc (app-wide) and right-click."""
    # bind_all catches Escape regardless of which inner widget holds focus.
    top.bind_all("<Escape>", close)
    top.bind("<Escape>", close)
    canvas.bind("<Escape>", close)
    canvas.bind("<ButtonPress-3>", close)  # right-click also cancels


def _teardown(top):
    try:
        top.unbind_all("<Escape>")
    except Exception:  # noqa: BLE001
        pass
    try:
        top.grab_release()
    except Exception:  # noqa: BLE001
        pass
    top.destroy()


def _banner(canvas, geo, text):
    """A readable instruction banner with a dark pill behind it."""
    cx = geo["width"] // 2
    canvas.create_rectangle(cx - 340, 22, cx + 340, 62, fill="#000000", outline=_ACCENT)
    canvas.create_text(cx, 42, text=text, fill=_HINT, font=_INSTRUCTION_FONT)


def select_region(root) -> Optional[Region]:
    """Let the user drag a rectangle. Returns a :class:`Region` or ``None``."""
    top, canvas, geo = _make_overlay(root)
    state = {"x0": 0, "y0": 0, "rect": None, "label": None, "result": None}

    _banner(canvas, geo, "Drag to select the area to watch    •    Esc / right-click to cancel")

    def on_press(event):
        state["x0"], state["y0"] = event.x, event.y
        if state["rect"]:
            canvas.delete(state["rect"])
        state["rect"] = canvas.create_rectangle(
            event.x, event.y, event.x, event.y, outline=_ACCENT, width=3
        )

    def on_drag(event):
        if state["rect"]:
            canvas.coords(state["rect"], state["x0"], state["y0"], event.x, event.y)
            w = abs(event.x - state["x0"])
            h = abs(event.y - state["y0"])
            if state["label"]:
                canvas.delete(state["label"])
            state["label"] = canvas.create_text(
                event.x + 14,
                event.y + 14,
                text=f"{w} × {h}",
                fill=_ACCENT,
                font=("Sans", 13, "bold"),
                anchor="nw",
            )

    def on_release(event):
        x0, y0 = state["x0"], state["y0"]
        left, top_ = min(x0, event.x), min(y0, event.y)
        width, height = abs(event.x - x0), abs(event.y - y0)
        if width >= 3 and height >= 3:
            state["result"] = Region(left + geo["left"], top_ + geo["top"], width, height)
        _teardown(top)

    def _cancel(*_):
        _teardown(top)

    canvas.bind("<ButtonPress-1>", on_press)
    canvas.bind("<B1-Motion>", on_drag)
    canvas.bind("<ButtonRelease-1>", on_release)
    _bind_cancel(top, canvas, _cancel)
    root.wait_window(top)
    return state["result"]


def select_point(root) -> Optional[Tuple[int, int]]:
    """Let the user click a single point. Returns ``(x, y)`` or ``None``."""
    top, canvas, geo = _make_overlay(root)
    state = {"result": None, "cross": []}

    _banner(canvas, geo, "Click the location to auto-click    •    Esc / right-click to cancel")

    def on_move(event):
        for item in state["cross"]:
            canvas.delete(item)
        state["cross"] = [
            canvas.create_line(event.x - 18, event.y, event.x + 18, event.y, fill=_ACCENT, width=2),
            canvas.create_line(event.x, event.y - 18, event.x, event.y + 18, fill=_ACCENT, width=2),
            canvas.create_oval(event.x - 7, event.y - 7, event.x + 7, event.y + 7, outline=_ACCENT, width=2),
        ]

    def on_click(event):
        state["result"] = (event.x + geo["left"], event.y + geo["top"])
        _teardown(top)

    def _cancel(*_):
        _teardown(top)

    canvas.bind("<Motion>", on_move)
    canvas.bind("<ButtonPress-1>", on_click)
    # Right-click cancels here too; it must override the generic cancel binding
    # only for button-3, which _bind_cancel already maps to cancel.
    _bind_cancel(top, canvas, _cancel)
    root.wait_window(top)
    return state["result"]
