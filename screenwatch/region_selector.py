"""Fullscreen overlays for picking a region and a click point.

Both helpers put a dim, semi-transparent window over the whole virtual desktop
so the user can visually select directly on top of their real screen.  They
block until the user finishes (or presses Escape) and return absolute screen
coordinates.

Tkinter is imported lazily so importing this module never requires a display.
"""

from __future__ import annotations

from typing import Optional, Tuple

from .capture import get_virtual_geometry
from .config import Region

_INSTRUCTION_FONT = ("Sans", 16, "bold")
_HINT = "#e8e8e8"
_ACCENT = "#28c76f"


def _make_overlay(root):
    """Create a borderless, semi-transparent Toplevel covering all monitors."""
    import tkinter as tk

    geo = get_virtual_geometry()
    top = tk.Toplevel(root)
    top.overrideredirect(True)
    top.attributes("-topmost", True)
    try:
        top.attributes("-alpha", 0.35)
    except tk.TclError:  # pragma: no cover - some WMs lack alpha
        pass
    top.configure(bg="black", cursor="crosshair")
    top.geometry(f"{geo['width']}x{geo['height']}+{geo['left']}+{geo['top']}")
    canvas = tk.Canvas(top, bg="black", highlightthickness=0, cursor="crosshair")
    canvas.pack(fill="both", expand=True)
    return top, canvas, geo


def select_region(root) -> Optional[Region]:
    """Let the user drag a rectangle. Returns a :class:`Region` or ``None``."""
    import tkinter as tk

    top, canvas, geo = _make_overlay(root)
    state = {"x0": 0, "y0": 0, "rect": None, "label": None, "result": None}

    canvas.create_text(
        geo["width"] // 2,
        40,
        text="Drag to select the area to watch   •   Esc to cancel",
        fill=_HINT,
        font=_INSTRUCTION_FONT,
    )

    def on_press(event):
        state["x0"], state["y0"] = event.x, event.y
        if state["rect"]:
            canvas.delete(state["rect"])
        state["rect"] = canvas.create_rectangle(
            event.x, event.y, event.x, event.y, outline=_ACCENT, width=2
        )

    def on_drag(event):
        if state["rect"]:
            canvas.coords(state["rect"], state["x0"], state["y0"], event.x, event.y)
            w = abs(event.x - state["x0"])
            h = abs(event.y - state["y0"])
            if state["label"]:
                canvas.delete(state["label"])
            state["label"] = canvas.create_text(
                event.x + 12,
                event.y + 12,
                text=f"{w} × {h}",
                fill=_ACCENT,
                font=("Sans", 12, "bold"),
                anchor="nw",
            )

    def on_release(event):
        x0, y0 = state["x0"], state["y0"]
        x1, y1 = event.x, event.y
        left, top_ = min(x0, x1), min(y0, y1)
        width, height = abs(x1 - x0), abs(y1 - y0)
        if width >= 3 and height >= 3:
            state["result"] = Region(
                left + geo["left"], top_ + geo["top"], width, height
            )
        _close()

    def _close(*_):
        top.grab_release()
        top.destroy()

    canvas.bind("<ButtonPress-1>", on_press)
    canvas.bind("<B1-Motion>", on_drag)
    canvas.bind("<ButtonRelease-1>", on_release)
    top.bind("<Escape>", _close)
    top.grab_set()
    top.focus_force()
    root.wait_window(top)
    return state["result"]


def select_point(root) -> Optional[Tuple[int, int]]:
    """Let the user click a single point. Returns ``(x, y)`` or ``None``."""
    import tkinter as tk

    top, canvas, geo = _make_overlay(root)
    state = {"result": None, "cross": []}

    canvas.create_text(
        geo["width"] // 2,
        40,
        text="Click the location to auto-click   •   Esc to cancel",
        fill=_HINT,
        font=_INSTRUCTION_FONT,
    )

    def on_move(event):
        for item in state["cross"]:
            canvas.delete(item)
        state["cross"] = [
            canvas.create_line(event.x - 15, event.y, event.x + 15, event.y, fill=_ACCENT, width=1),
            canvas.create_line(event.x, event.y - 15, event.x, event.y + 15, fill=_ACCENT, width=1),
            canvas.create_oval(event.x - 6, event.y - 6, event.x + 6, event.y + 6, outline=_ACCENT, width=2),
        ]

    def on_click(event):
        state["result"] = (event.x + geo["left"], event.y + geo["top"])
        _close()

    def _close(*_):
        top.grab_release()
        top.destroy()

    canvas.bind("<Motion>", on_move)
    canvas.bind("<ButtonPress-1>", on_click)
    top.bind("<Escape>", _close)
    top.grab_set()
    top.focus_force()
    root.wait_window(top)
    return state["result"]
