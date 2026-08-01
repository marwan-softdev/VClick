"""Live, non-covering overlays for picking a region and a click point.

The screen is **never covered**.  Instead of painting a translucent sheet over
the desktop (which needs a compositing window manager, and renders as solid
black without one), selection works like this:

* a 1×1, effectively invisible window takes a **global pointer grab**, so every
  mouse move/press anywhere on screen is delivered to us with absolute
  coordinates (``x_root``/``y_root``);
* the selection is drawn as a handful of **thin border strip windows** that
  outline the rectangle.

Because nothing is layered over the desktop, the user drags over their **live,
untouched screen** — video keeps playing, UIs keep animating — with or without
a compositor.  If a global grab is unavailable, we fall back to the classic
translucent overlay.

Tkinter is imported lazily so importing this module never requires a display.
"""

from __future__ import annotations

from typing import Optional, Tuple

from .capture import get_virtual_geometry
from .config import Region

_ACCENT = "#00e676"      # selection border
_BANNER_BG = "#101418"
_BANNER_FG = "#ffffff"
_BORDER = 2              # selection outline thickness, px
_INSTRUCTION_FONT = ("Sans", 13, "bold")
_OVERLAY_ALPHA = 0.25    # only used by the legacy fallback


def _rect_from_points(x0: int, y0: int, x1: int, y1: int) -> Tuple[int, int, int, int]:
    """Normalise two drag corners into ``(left, top, width, height)``."""
    return min(x0, x1), min(y0, y1), abs(x1 - x0), abs(y1 - y0)


def _strip(root, color: str):
    """A borderless, always-on-top solid-colour window used to draw lines."""
    import tkinter as tk

    w = tk.Toplevel(root)
    w.overrideredirect(True)
    try:
        w.attributes("-topmost", True)
    except tk.TclError:  # pragma: no cover
        pass
    w.configure(bg=color)
    w.withdraw()
    return w


def _place(win, x: int, y: int, w: int, h: int) -> None:
    """Move/resize a strip window; Tk rejects zero-sized geometry."""
    win.geometry(f"{max(1, int(w))}x{max(1, int(h))}+{int(x)}+{int(y)}")
    win.deiconify()


class _LiveSelector:
    """Shared machinery: invisible grab window, banner, cleanup, event loop."""

    def __init__(self, root, instruction: str):
        import tkinter as tk

        self.tk = tk
        self.root = root
        self.geo = get_virtual_geometry()
        self.result = None
        self._windows = []
        self._done = tk.BooleanVar(root, value=False)

        # 1x1 grab window: stays mapped for the whole selection (unmapping it
        # would drop the pointer grab), but is far too small to obscure
        # anything.  It also holds keyboard focus so Escape reaches us.
        self.grab_win = tk.Toplevel(root)
        self.grab_win.overrideredirect(True)
        self.grab_win.geometry(f"1x1+{self.geo['left']}+{self.geo['top']}")
        try:
            self.grab_win.attributes("-topmost", True)
        except tk.TclError:  # pragma: no cover
            pass
        self.grab_win.configure(bg=_ACCENT, cursor="crosshair")
        self.grab_win.deiconify()
        self._windows.append(self.grab_win)

        self.banner = self._make_banner(instruction)
        self.root.update_idletasks()

    def _make_banner(self, text: str):
        tk = self.tk
        win = tk.Toplevel(self.root)
        win.overrideredirect(True)
        try:
            win.attributes("-topmost", True)
        except tk.TclError:  # pragma: no cover
            pass
        win.configure(bg=_BANNER_BG, cursor="crosshair")
        label = tk.Label(win, text=text, bg=_BANNER_BG, fg=_BANNER_FG,
                         font=_INSTRUCTION_FONT, padx=22, pady=10)
        label.pack()
        win.update_idletasks()
        w, h = win.winfo_reqwidth(), win.winfo_reqheight()
        x = self.geo["left"] + (self.geo["width"] - w) // 2
        y = self.geo["top"] + 30
        win.geometry(f"{w}x{h}+{x}+{y}")
        win.deiconify()
        self._windows.append(win)
        return win

    def hide_banner(self) -> None:
        """Get the instructions out of the way once the drag starts."""
        try:
            self.banner.withdraw()
        except Exception:  # noqa: BLE001
            pass

    def grab(self) -> bool:
        """Take a global pointer grab. Returns False if the WM refuses."""
        try:
            self.grab_win.grab_set_global()
        except Exception:  # noqa: BLE001 - fall back to the tinted overlay
            return False
        self.grab_win.focus_force()
        return True

    def bind(self, sequence: str, handler) -> None:
        self.grab_win.bind(sequence, handler)

    def finish(self, result=None) -> None:
        self.result = result
        self._done.set(True)

    def wait(self):
        """Block until a handler calls :meth:`finish`, then clean up."""
        self.root.wait_variable(self._done)
        try:
            self.grab_win.grab_release()
        except Exception:  # noqa: BLE001
            pass
        for win in self._windows:
            try:
                win.destroy()
            except Exception:  # noqa: BLE001
                pass
        return self.result

    def track(self, win):
        self._windows.append(win)
        return win


def select_region(root) -> Optional[Region]:
    """Let the user drag a rectangle over the **live** screen.

    Returns a :class:`Region` in absolute screen coordinates, or ``None`` if
    cancelled (Escape / right-click) or if the drag was too small to be useful.
    """
    sel = _LiveSelector(root, "Drag to select the area to watch    •    Esc / right-click to cancel")
    if not sel.grab():
        sel.finish(None)
        sel.wait()
        return _select_region_overlay(root)  # compositor-style fallback

    # Four strips outline the selection; a fifth window shows live dimensions.
    edges = [sel.track(_strip(root, _ACCENT)) for _ in range(4)]
    size_win = sel.track(_strip(root, _BANNER_BG))
    size_lbl = sel.tk.Label(size_win, text="", bg=_BANNER_BG, fg=_ACCENT,
                            font=("Sans", 11, "bold"), padx=8, pady=3)
    size_lbl.pack()

    state = {"x0": 0, "y0": 0, "dragging": False}

    def draw(left, top, w, h):
        # top, bottom, left, right strips forming a hollow rectangle
        _place(edges[0], left, top, w, _BORDER)
        _place(edges[1], left, top + h - _BORDER, w, _BORDER)
        _place(edges[2], left, top, _BORDER, h)
        _place(edges[3], left + w - _BORDER, top, _BORDER, h)
        size_lbl.configure(text=f"{w} × {h}")
        size_win.update_idletasks()
        _place(size_win, left + 6, top + h + 8,
               size_win.winfo_reqwidth(), size_win.winfo_reqheight())

    def on_press(event):
        state["x0"], state["y0"] = event.x_root, event.y_root
        state["dragging"] = True
        sel.hide_banner()  # whole screen is now unobstructed

    def on_drag(event):
        if not state["dragging"]:
            return
        draw(*_rect_from_points(state["x0"], state["y0"], event.x_root, event.y_root))

    def on_release(event):
        if not state["dragging"]:
            return
        left, top, w, h = _rect_from_points(state["x0"], state["y0"],
                                            event.x_root, event.y_root)
        sel.finish(Region(left, top, w, h) if w >= 3 and h >= 3 else None)

    sel.bind("<ButtonPress-1>", on_press)
    sel.bind("<B1-Motion>", on_drag)
    sel.bind("<Motion>", on_drag)
    sel.bind("<ButtonRelease-1>", on_release)
    sel.bind("<ButtonPress-3>", lambda e: sel.finish(None))
    sel.bind("<Escape>", lambda e: sel.finish(None))
    sel.bind("<KeyPress-Escape>", lambda e: sel.finish(None))
    return sel.wait()


def select_point(root) -> Optional[Tuple[int, int]]:
    """Let the user click a point on the **live** screen. Returns ``(x, y)``."""
    sel = _LiveSelector(root, "Click the location to auto-click    •    Esc / right-click to cancel")
    if not sel.grab():
        sel.finish(None)
        sel.wait()
        return _select_point_overlay(root)

    # A full-width and full-height 1px line following the cursor: a crosshair
    # that never hides what is underneath it.
    hline = sel.track(_strip(root, _ACCENT))
    vline = sel.track(_strip(root, _ACCENT))
    g = sel.geo

    def on_move(event):
        _place(hline, g["left"], event.y_root, g["width"], 1)
        _place(vline, event.x_root, g["top"], 1, g["height"])

    sel.bind("<Motion>", on_move)
    sel.bind("<ButtonPress-1>", lambda e: sel.finish((e.x_root, e.y_root)))
    sel.bind("<ButtonPress-3>", lambda e: sel.finish(None))
    sel.bind("<Escape>", lambda e: sel.finish(None))
    sel.bind("<KeyPress-Escape>", lambda e: sel.finish(None))
    return sel.wait()


# ---------------------------------------------------------------------------
# Legacy translucent-overlay fallback, used only when a global pointer grab is
# refused.  Requires a compositing WM to be see-through.
# ---------------------------------------------------------------------------
def _make_overlay(root):
    import tkinter as tk

    geo = get_virtual_geometry()
    top = tk.Toplevel(root)
    top.overrideredirect(True)
    top.attributes("-topmost", True)
    try:
        top.attributes("-alpha", _OVERLAY_ALPHA)
    except tk.TclError:  # pragma: no cover
        pass
    top.configure(bg="black", cursor="crosshair")
    top.geometry(f"{geo['width']}x{geo['height']}+{geo['left']}+{geo['top']}")
    canvas = tk.Canvas(top, bg="black", highlightthickness=0, cursor="crosshair")
    canvas.pack(fill="both", expand=True)
    top.grab_set()
    top.focus_force()
    canvas.focus_set()
    return top, canvas, geo


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


def _bind_cancel(top, canvas, close):
    top.bind_all("<Escape>", close)
    top.bind("<Escape>", close)
    canvas.bind("<Escape>", close)
    canvas.bind("<ButtonPress-3>", close)


def _select_region_overlay(root) -> Optional[Region]:
    top, canvas, geo = _make_overlay(root)
    state = {"x0": 0, "y0": 0, "rect": None, "result": None}

    def on_press(event):
        state["x0"], state["y0"] = event.x, event.y
        if state["rect"]:
            canvas.delete(state["rect"])
        state["rect"] = canvas.create_rectangle(event.x, event.y, event.x, event.y,
                                                outline=_ACCENT, width=3)

    def on_drag(event):
        if state["rect"]:
            canvas.coords(state["rect"], state["x0"], state["y0"], event.x, event.y)

    def on_release(event):
        left, top_, w, h = _rect_from_points(state["x0"], state["y0"], event.x, event.y)
        if w >= 3 and h >= 3:
            state["result"] = Region(left + geo["left"], top_ + geo["top"], w, h)
        _teardown(top)

    canvas.bind("<ButtonPress-1>", on_press)
    canvas.bind("<B1-Motion>", on_drag)
    canvas.bind("<ButtonRelease-1>", on_release)
    _bind_cancel(top, canvas, lambda *_: _teardown(top))
    root.wait_window(top)
    return state["result"]


def _select_point_overlay(root) -> Optional[Tuple[int, int]]:
    top, canvas, geo = _make_overlay(root)
    state = {"result": None}

    def on_click(event):
        state["result"] = (event.x + geo["left"], event.y + geo["top"])
        _teardown(top)

    canvas.bind("<ButtonPress-1>", on_click)
    _bind_cancel(top, canvas, lambda *_: _teardown(top))
    root.wait_window(top)
    return state["result"]
