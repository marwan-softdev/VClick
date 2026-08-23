"""The ScreenWatch desktop GUI (CustomTkinter, with a couple of plain-ttk
widgets embedded where CustomTkinter has no equivalent — see the comment
in :meth:`ScreenWatchApp._build_style`).

Kept in one file for easy distribution. CustomTkinter/Tkinter are imported at
call time inside :func:`run` (and the app class's own methods) so this module
can still be imported for tooling/tests without a display.
"""

from __future__ import annotations

import queue
from typing import Optional

from . import __app_name__, __version__
from .config import CLICK_BUTTONS, CLICK_TYPES, Config
from .history import DetectionHistory
from .hotkeys import HotkeyManager, is_valid, parse_hotkey, pretty
from .monitor import Monitor, MonitorEvent
from .sound import Beeper

PAD = 14
CARD_GAP = 8

# ---------------------------------------------------------------------------
# Design tokens: a light theme inspired by Raycast's and CleanShot X's
# preference panes -- a neutral canvas, white bordered "cards" that group
# related fields (so it's obvious at a glance where one setting group ends
# and the next begins), one accent color reserved for the single primary
# action and for "this value is set" badges, and everything else rendered
# in quiet neutrals so the accent still stands out where it's used.
# ---------------------------------------------------------------------------
_BG = "#f2f2f5"            # window canvas
_CARD = "#ffffff"          # card surface
_CARD_BORDER = "#e4e4e9"   # hairline card border
_DIVIDER = "#ececef"       # subtle in-card divider (header vs. content)
_TEXT = "#1c1c1e"          # primary text
_MUTED = "#8a8a8e"         # secondary/muted text
_MUTED2 = "#c2c2c7"        # faint borders only (e.g. unchecked checkbox/radio
                           # outlines) -- too low-contrast for text on white
                           # (~1.8:1); use _MUTED for anything meant to be read
_ACCENT = "#0a84ff"        # primary accent -- the Start button, badges, links
_ACCENT_HOVER = "#0071e3"
_ACCENT_TINT = "#e8f2ff"   # light accent fill for "value is set" badges
_TRACK = "#e4e4e9"         # slider / progress-bar track

# Status colors. The vivid tones below are used for small dot indicators
# (fine at any contrast); *_TEXT variants are darker so status text stays
# readable on a white card instead of the washed-out look pastel-on-white
# status text gets.
_OK, _OK_TEXT = "#12b76a", "#067647"
_WARN, _WARN_TEXT = "#f79009", "#b54708"
_ERROR, _ERROR_TEXT = "#f04438", "#b42318"
_ERROR_HOVER = "#d92d20"

_STATUS_TEXT_COLORS = {_OK: _OK_TEXT, _WARN: _WARN_TEXT, _ERROR: _ERROR_TEXT}


def _status_text_color(color: str) -> str:
    """Map a status dot color to a readable-on-white text color; anything
    not in the map (e.g. a plain "gray50") passes through unchanged."""
    return _STATUS_TEXT_COLORS.get(color, color)


# Keysyms that are modifiers themselves — ignored while capturing a hotkey.
_MODIFIER_KEYSYMS = {
    "Control_L", "Control_R", "Shift_L", "Shift_R", "Alt_L", "Alt_R",
    "Super_L", "Super_R", "Meta_L", "Meta_R", "ISO_Level3_Shift",
}
_SPECIAL_KEYS = {
    "Return": "<enter>", "space": "<space>", "Tab": "<tab>",
    "BackSpace": "<backspace>", "Delete": "<delete>", "Up": "<up>",
    "Down": "<down>", "Left": "<left>", "Right": "<right>", "Home": "<home>",
    "End": "<end>", "Prior": "<page_up>", "Next": "<page_down>",
    "Insert": "<insert>",
}


def _fmt_uptime(seconds: float) -> str:
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h {m:02d}m {s:02d}s"
    if m:
        return f"{m}m {s:02d}s"
    return f"{s}s"


def _keysym_to_token(keysym: str) -> Optional[str]:
    if len(keysym) == 1 and keysym.isprintable():
        return keysym.lower()
    if keysym in _SPECIAL_KEYS:
        return _SPECIAL_KEYS[keysym]
    if len(keysym) >= 2 and keysym[0] in "Ff" and keysym[1:].isdigit():
        return f"<{keysym.lower()}>"
    return None


def _event_to_hotkey(event) -> Optional[str]:
    """Turn a Tk key event into a pynput hotkey string, or ``None`` if unusable."""
    state = event.state
    mods = []
    if state & 0x4:
        mods.append("<ctrl>")
    if state & 0x8:
        mods.append("<alt>")
    if state & 0x40:
        mods.append("<cmd>")
    if state & 0x1:
        mods.append("<shift>")
    key = _keysym_to_token(event.keysym)
    if key is None:
        return None
    combo = "+".join(mods + [key])
    # Validate with our own parser (the one that will do the matching), not
    # pynput's — that keeps capture working without a display and guarantees
    # the captured string is exactly what HotkeyManager can match.
    return combo if parse_hotkey(combo) is not None else None


class ScreenWatchApp:
    """Builds the window, wires widgets to a shared :class:`Config`, and drives
    a :class:`Monitor` worker."""

    def __init__(self, root, config: Optional[Config] = None) -> None:
        import tkinter as tk
        from tkinter import ttk

        import customtkinter as ctk

        self.tk = tk
        self.ttk = ttk
        self.ctk = ctk
        self.root = root
        self.config = config or Config.load()
        self.config.clamp()

        self._events: "queue.Queue[MonitorEvent]" = queue.Queue()
        self._actions: "queue.Queue[str]" = queue.Queue()
        self._observed: "queue.Queue[str]" = queue.Queue()
        self.monitor = Monitor(self.config, on_event=self._events.put)
        self.hotkeys = HotkeyManager()
        self._history = DetectionHistory(self.config.log_history)
        self._beeper = Beeper(root)
        self._row_seq = 0           # monotonic, unique per window (see _log_detection)
        self._selected = None       # the Detection currently shown
        self._preview_photo = None  # keep a ref so Tk doesn't GC the image
        self._slider_labels = {}    # slider label text -> its value badge

        root.title(f"{__app_name__} — auto-click on change")
        root.minsize(560, 760)
        root.protocol("WM_DELETE_WINDOW", self.on_close)

        self._build_style()
        self._build_menu()
        self._build_widgets()
        self._sync_widgets_from_config()

        self._apply_hotkeys()
        self.root.after(100, self._poll)

    # ------------------------------------------------------------------ UI
    def _build_style(self) -> None:
        ctk = self.ctk
        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("blue")
        self.root.configure(fg_color=_BG)

        # ttk.Treeview/PanedWindow/Scrollbar have no CustomTkinter equivalent
        # (it doesn't ship a table/tree widget), so the Why/Log tab keeps
        # them as plain ttk -- restyled by hand to match the app's light
        # card palette so they blend in instead of looking like a stray
        # system-themed widget dropped into an otherwise custom window.
        style = self.ttk.Style()
        for theme in ("clam", "alt", "default"):
            if theme in style.theme_names():
                style.theme_use(theme)
                break
        style.configure("Treeview", background=_CARD, fieldbackground=_CARD,
                         foreground=_TEXT, borderwidth=0, rowheight=26)
        style.configure("Treeview.Heading", background="#fafafb", foreground=_MUTED,
                         borderwidth=0, relief="flat", font=("Sans", 10, "bold"))
        style.map("Treeview", background=[("selected", _ACCENT_TINT)],
                   foreground=[("selected", _TEXT)])
        style.configure("TPanedwindow", background=_BG)
        style.configure("Vertical.TScrollbar", background=_CARD_BORDER,
                         troughcolor=_CARD, borderwidth=0, arrowsize=12)

    def _build_menu(self) -> None:
        # Native OS menu bar -- CustomTkinter doesn't theme tk.Menu (no
        # custom-rendered equivalent exists), so this is the one part of the
        # window that keeps the platform's native look. Functionally
        # unaffected either way.
        menubar = self.tk.Menu(self.root)
        filemenu = self.tk.Menu(menubar, tearoff=0)
        filemenu.add_command(label="Save settings", command=self.save_settings)
        filemenu.add_command(label="Reload settings", command=self.reload_settings)
        filemenu.add_separator()
        filemenu.add_command(label="Quit", command=self.on_close)
        menubar.add_cascade(label="File", menu=filemenu)

        helpmenu = self.tk.Menu(menubar, tearoff=0)
        helpmenu.add_command(label="About / Help", command=self.show_about)
        menubar.add_cascade(label="Help", menu=helpmenu)
        self.root.config(menu=menubar)

    def _build_widgets(self) -> None:
        ctk = self.ctk
        root = self.root

        header = ctk.CTkFrame(root, fg_color="transparent")
        header.pack(fill="x", padx=PAD, pady=(PAD, 4))
        title_row = ctk.CTkFrame(header, fg_color="transparent")
        title_row.pack(fill="x")
        mark = ctk.CTkFrame(title_row, width=10, height=10, corner_radius=5, fg_color=_ACCENT)
        mark.pack(side="left", padx=(2, 8))
        mark.pack_propagate(False)
        ctk.CTkLabel(title_row, text="ScreenWatch", font=("Sans", 21, "bold"),
                     text_color=_TEXT, anchor="w").pack(side="left")
        ctk.CTkLabel(header, text="Watches a screen area and clicks the instant it changes.",
                     text_color=_MUTED, anchor="w").pack(fill="x", pady=(2, 0))

        # Persistent control bar pinned to the bottom.
        self._build_control_bar(root)

        # Tabbed settings fill the middle, styled as a light segmented
        # control (selected tab = a raised white pill) instead of the
        # default theme's tab strip.
        tabview = ctk.CTkTabview(
            root, fg_color=_BG, border_width=0,
            segmented_button_fg_color=_CARD_BORDER,
            segmented_button_selected_color=_CARD,
            segmented_button_selected_hover_color=_CARD,
            segmented_button_unselected_color=_CARD_BORDER,
            segmented_button_unselected_hover_color="#dadade",
            text_color=_TEXT, text_color_disabled=_MUTED,
        )
        tabview.pack(fill="both", expand=True, padx=PAD, pady=(4, PAD))
        self._build_tab_watch(tabview)
        self._build_tab_clicking(tabview)
        self._build_tab_hotkeys(tabview)
        self._build_tab_why(tabview)

    def _build_control_bar(self, root) -> None:
        ctk = self.ctk
        outer = ctk.CTkFrame(root, fg_color="transparent")
        outer.pack(side="bottom", fill="x", padx=PAD, pady=(0, PAD))

        card = ctk.CTkFrame(outer, corner_radius=14, fg_color=_CARD,
                             border_width=1, border_color=_CARD_BORDER)
        card.pack(fill="x")

        self.start_btn = self._btn(card, "▶  Start", self.toggle, kind="primary",
                                    font=("Sans", 14, "bold"), height=42, corner_radius=12)
        self.start_btn.pack(fill="x", padx=16, pady=(14, 8))

        self.activity = ctk.CTkProgressBar(card, height=5, corner_radius=3,
                                            fg_color=_TRACK, progress_color=_ACCENT)
        self.activity.set(0)
        self.activity.pack(fill="x", padx=16, pady=(0, 10))

        # A colored dot carries the state at a glance (green = watching,
        # red = error, gray = idle) so it doesn't rely on pastel status
        # text, which reads poorly against a white card.
        status_row = ctk.CTkFrame(card, fg_color="transparent")
        status_row.pack(fill="x", padx=16)
        self.status_dot = ctk.CTkFrame(status_row, width=8, height=8, corner_radius=4,
                                        fg_color=_MUTED)
        self.status_dot.pack(side="left", padx=(0, 8))
        self.status_dot.pack_propagate(False)
        self.status_lbl = ctk.CTkLabel(status_row, text="Idle — select targets to begin.",
                                        font=("Sans", 12, "bold"), text_color=_MUTED, anchor="w")
        self.status_lbl.pack(side="left", fill="x", expand=True)

        self.stats_lbl = ctk.CTkLabel(card, text="", text_color=_MUTED, anchor="w")
        self.stats_lbl.pack(fill="x", padx=16, pady=(4, 0))
        self.hotkey_lbl = ctk.CTkLabel(card, text="", text_color=_MUTED,
                                        font=("Sans", 10), anchor="w")
        self.hotkey_lbl.pack(fill="x", padx=16, pady=(4, 10))

    def _btn(self, parent, text, command, kind="secondary", **kw):
        """CTkButton preset to one of the app's two visual roles: a single
        filled 'primary' action per view (Raycast/CleanShot convention --
        one obvious thing to press) and neutral outlined 'secondary'
        actions for everything else, so the important control doesn't get
        lost among a row of equally-weighted buttons. (The Start/Stop
        button is the one exception that needs a third, red "danger" look
        while running -- handled by _update_running_ui reconfiguring the
        same button directly, since it must restyle an existing widget
        rather than construct a new one.)"""
        ctk = self.ctk
        if kind == "primary":
            style = dict(fg_color=_ACCENT, hover_color=_ACCENT_HOVER, text_color="white",
                         corner_radius=10, border_width=0)
        else:
            style = dict(fg_color="transparent", hover_color=_BG, text_color=_TEXT,
                         border_width=1, border_color=_CARD_BORDER, corner_radius=8)
        style.update(kw)
        return ctk.CTkButton(parent, text=text, command=command, **style)

    def _section(self, parent, title):
        """A bordered white card with a small accent dot + bold title in its
        header, divided from its content by a hairline — the visual
        grouping CustomTkinter has no LabelFrame equivalent for. Content is
        gridded into the returned frame starting at row 2 (0 = header,
        1 = divider); column 1 is preset to expand, matching the 3-column
        layouts below."""
        ctk = self.ctk
        frame = ctk.CTkFrame(parent, corner_radius=14, fg_color=_CARD,
                              border_width=1, border_color=_CARD_BORDER)
        header = ctk.CTkFrame(frame, fg_color="transparent")
        header.grid(row=0, column=0, columnspan=3, sticky="ew", padx=16, pady=(12, 8))
        dot = ctk.CTkFrame(header, width=7, height=7, corner_radius=4, fg_color=_ACCENT)
        dot.pack(side="left", padx=(2, 8))
        dot.pack_propagate(False)
        ctk.CTkLabel(header, text=title, font=("Sans", 13, "bold"), text_color=_TEXT,
                     anchor="w").pack(side="left")
        ctk.CTkFrame(frame, height=1, fg_color=_DIVIDER).grid(
            row=1, column=0, columnspan=3, sticky="ew", padx=16, pady=(0, 4))
        frame.columnconfigure(1, weight=1)
        return frame

    def _style_chip(self, label, text, is_set: bool) -> None:
        """Toggle a value label between a filled accent 'badge' (something
        is set) and plain muted text (nothing set yet) — so the state is
        visible at a glance, not just from reading the words."""
        if is_set:
            label.configure(text=text, fg_color=_ACCENT_TINT, text_color=_ACCENT)
        else:
            label.configure(text=text, fg_color="transparent", text_color=_MUTED)

    def _build_tab_watch(self, tabview) -> None:
        ctk = self.ctk
        tab = tabview.add("Targets & Detection")

        targets = self._section(tab, "Targets")
        targets.pack(fill="x", pady=(0, CARD_GAP))
        ctk.CTkLabel(targets, text="Watch region", text_color=_MUTED, anchor="w").grid(
            row=2, column=0, sticky="w", padx=(16, 0), pady=(0, 8))
        self.region_lbl = ctk.CTkLabel(targets, text="Not set", font=("Sans", 12, "bold"),
                                        fg_color="transparent", text_color=_MUTED,
                                        corner_radius=6, anchor="w")
        self.region_lbl.grid(row=2, column=1, sticky="w", padx=8, pady=(0, 8))
        self.region_btn = self._btn(targets, "Select…", self.select_region, width=90)
        self.region_btn.grid(row=2, column=2, sticky="e", padx=(0, 16), pady=(0, 8))
        ctk.CTkLabel(targets, text="Click point", text_color=_MUTED, anchor="w").grid(
            row=3, column=0, sticky="w", padx=(16, 0), pady=(0, 12))
        self.point_lbl = ctk.CTkLabel(targets, text="Not set", font=("Sans", 12, "bold"),
                                       fg_color="transparent", text_color=_MUTED,
                                       corner_radius=6, anchor="w")
        self.point_lbl.grid(row=3, column=1, sticky="w", padx=8, pady=(0, 12))
        self.point_btn = self._btn(targets, "Select…", self.select_point, width=90)
        self.point_btn.grid(row=3, column=2, sticky="e", padx=(0, 16), pady=(0, 12))

        detect = self._section(tab, "Detection")
        detect.pack(fill="x", pady=(0, CARD_GAP))

        self.sensitivity_var = self.tk.IntVar()
        self._slider(detect, 2, "Sensitivity", self.sensitivity_var, 1, 100,
                     hint="higher = reacts to smaller changes", steps=99)
        self.fps_var = self.tk.DoubleVar()
        self._slider(detect, 4, "Check rate (fps)", self.fps_var, 0.5, 30,
                     hint="lower = less CPU", fmt="{:.1f}")
        self.threshold_var = self.tk.IntVar()
        self._slider(detect, 6, "Noise filter", self.threshold_var, 0, 100,
                     hint="ignore per-pixel changes below this", steps=100)

        ctk.CTkFrame(detect, height=1, fg_color=_DIVIDER).grid(
            row=8, column=0, columnspan=3, sticky="ew", padx=16, pady=(2, 8))

        ctk.CTkLabel(detect, text="Compare against", text_color=_MUTED, anchor="nw").grid(
            row=9, column=0, sticky="nw", padx=(16, 0), pady=(0, 12))
        self.compare_var = self.tk.StringVar()
        cmp_frame = ctk.CTkFrame(detect, fg_color="transparent")
        cmp_frame.grid(row=9, column=1, columnspan=2, sticky="w", padx=8, pady=(0, 12))
        ctk.CTkRadioButton(cmp_frame, text="Previous frame (any change)", value="previous",
                            variable=self.compare_var, command=self._on_setting_change,
                            fg_color=_ACCENT, hover_color=_ACCENT_HOVER,
                            border_color=_MUTED2, text_color=_TEXT).pack(anchor="w", pady=3)
        ctk.CTkRadioButton(cmp_frame, text="Start frame (deviation from state)", value="baseline",
                            variable=self.compare_var, command=self._on_setting_change,
                            fg_color=_ACCENT, hover_color=_ACCENT_HOVER,
                            border_color=_MUTED2, text_color=_TEXT).pack(anchor="w", pady=3)

    def _build_tab_clicking(self, tabview) -> None:
        ctk = self.ctk
        tab = tabview.add("Clicking")

        behavior = self._section(tab, "Click Behavior")
        behavior.pack(fill="x", pady=(0, CARD_GAP))
        behavior.columnconfigure(3, weight=1)

        ctk.CTkLabel(behavior, text="Button", text_color=_MUTED, anchor="w").grid(
            row=2, column=0, sticky="w", padx=(16, 0), pady=(0, 14))
        self.button_var = self.tk.StringVar()
        ctk.CTkComboBox(behavior, variable=self.button_var, values=list(CLICK_BUTTONS),
                         width=110, state="readonly", fg_color=_CARD, border_color=_CARD_BORDER,
                         button_color=_ACCENT, button_hover_color=_ACCENT_HOVER,
                         dropdown_fg_color=_CARD, dropdown_text_color=_TEXT, text_color=_TEXT,
                         command=lambda _v: self._on_setting_change()).grid(
            row=2, column=1, sticky="w", padx=8, pady=(0, 14))
        ctk.CTkLabel(behavior, text="Type", text_color=_MUTED, anchor="w").grid(
            row=2, column=2, sticky="w", padx=(16, 0), pady=(0, 14))
        self.type_var = self.tk.StringVar()
        ctk.CTkComboBox(behavior, variable=self.type_var, values=list(CLICK_TYPES),
                         width=110, state="readonly", fg_color=_CARD, border_color=_CARD_BORDER,
                         button_color=_ACCENT, button_hover_color=_ACCENT_HOVER,
                         dropdown_fg_color=_CARD, dropdown_text_color=_TEXT, text_color=_TEXT,
                         command=lambda _v: self._on_setting_change()).grid(
            row=2, column=3, sticky="w", padx=(8, 16), pady=(0, 14))

        self.sound_var = self.tk.BooleanVar()
        ctk.CTkCheckBox(behavior, text="Beep on each click", variable=self.sound_var,
                         command=self._on_setting_change, fg_color=_ACCENT,
                         hover_color=_ACCENT_HOVER, border_color=_MUTED2,
                         checkmark_color="white", text_color=_TEXT).grid(
            row=3, column=0, columnspan=4, sticky="w", padx=(16, 0), pady=(0, 16))

        timing = self._section(tab, "Timing")
        timing.pack(fill="x", pady=(0, CARD_GAP))
        for c in (1, 3):
            timing.columnconfigure(c, weight=1)

        ctk.CTkLabel(timing, text="Cooldown (s)", text_color=_MUTED, anchor="w").grid(
            row=2, column=0, sticky="w", padx=(16, 0), pady=(0, 16))
        self.cooldown_var = self.tk.DoubleVar()
        self._stepper(timing, 2, 1, self.cooldown_var, step=0.5, lo=0, hi=3600)
        ctk.CTkLabel(timing, text="Delay (s)", text_color=_MUTED, anchor="w").grid(
            row=2, column=2, sticky="w", padx=(16, 0), pady=(0, 16))
        self.delay_var = self.tk.DoubleVar()
        self._stepper(timing, 2, 3, self.delay_var, step=0.1, lo=0, hi=60)

        ctk.CTkLabel(timing, text="Max clicks", text_color=_MUTED, anchor="w").grid(
            row=3, column=0, sticky="w", padx=(16, 0), pady=(0, 18))
        self.maxclicks_var = self.tk.IntVar()
        self._stepper(timing, 3, 1, self.maxclicks_var, step=1, lo=0, hi=1_000_000, integer=True)
        ctk.CTkLabel(timing, text="0 = unlimited", text_color=_MUTED, anchor="w").grid(
            row=3, column=2, columnspan=2, sticky="w", padx=(16, 0), pady=(0, 18))

    def _build_tab_hotkeys(self, tabview) -> None:
        ctk = self.ctk
        tab = tabview.add("Hotkeys")

        card = self._section(tab, "Global Hotkeys")
        card.pack(fill="x", pady=(0, CARD_GAP))

        self.hotkey_enabled_var = self.tk.BooleanVar()
        ctk.CTkCheckBox(card, text="Enable global hotkeys", variable=self.hotkey_enabled_var,
                         command=self._apply_hotkeys, fg_color=_ACCENT, hover_color=_ACCENT_HOVER,
                         border_color=_MUTED2, checkmark_color="white", text_color=_TEXT).grid(
            row=2, column=0, columnspan=3, sticky="w", padx=(16, 0), pady=(0, 16))

        ctk.CTkLabel(card, text="Start / Stop", text_color=_MUTED, anchor="w").grid(
            row=3, column=0, sticky="w", padx=(16, 0), pady=(0, 14))
        self.toggle_hotkey_lbl = ctk.CTkLabel(card, text="", font=("Sans", 12, "bold"),
                                               fg_color=_ACCENT_TINT, text_color=_ACCENT,
                                               corner_radius=6, anchor="w")
        self.toggle_hotkey_lbl.grid(row=3, column=1, sticky="w", padx=8, pady=(0, 14))
        self._btn(card, "Change…", lambda: self._capture_hotkey("toggle"), width=90).grid(
            row=3, column=2, sticky="e", padx=(0, 16), pady=(0, 14))

        ctk.CTkLabel(card, text="Quit", text_color=_MUTED, anchor="w").grid(
            row=4, column=0, sticky="w", padx=(16, 0), pady=(0, 16))
        self.quit_hotkey_lbl = ctk.CTkLabel(card, text="", font=("Sans", 12, "bold"),
                                             fg_color=_ACCENT_TINT, text_color=_ACCENT,
                                             corner_radius=6, anchor="w")
        self.quit_hotkey_lbl.grid(row=4, column=1, sticky="w", padx=8, pady=(0, 16))
        self._btn(card, "Change…", lambda: self._capture_hotkey("quit"), width=90).grid(
            row=4, column=2, sticky="e", padx=(0, 16), pady=(0, 16))

        ctk.CTkFrame(card, height=1, fg_color=_DIVIDER).grid(
            row=5, column=0, columnspan=3, sticky="ew", padx=16, pady=(0, 12))
        self.hotkey_status_lbl = ctk.CTkLabel(card, text="", text_color=_MUTED, anchor="w",
                                               wraplength=440, justify="left")
        self.hotkey_status_lbl.grid(row=6, column=0, columnspan=3, sticky="w",
                                     padx=(16, 16), pady=(0, 16))

        tester = self._section(tab, "Key Tester")
        tester.pack(fill="x", pady=(0, CARD_GAP))
        tester.columnconfigure(0, weight=1)

        ctk.CTkLabel(tester, text="Press any combination:", text_color=_MUTED, anchor="w").grid(
            row=2, column=0, sticky="w", padx=(16, 0), pady=(0, 14))
        self.hotkey_seen_lbl = ctk.CTkLabel(tester, text="Nothing yet", font=("Sans", 12, "bold"),
                                             fg_color="transparent", text_color=_MUTED,
                                             corner_radius=6, anchor="e")
        self.hotkey_seen_lbl.grid(row=2, column=1, sticky="e", padx=(0, 16), pady=(0, 14))
        ctk.CTkLabel(
            tester,
            text="Global hotkeys work on Windows and Linux X11. On Linux Wayland the\n"
                 "system usually blocks them — use the Start button instead.",
            text_color=_MUTED, font=("Sans", 10), justify="left", anchor="w",
        ).grid(row=3, column=0, columnspan=2, sticky="w", padx=(16, 16), pady=(0, 16))

    def _build_tab_why(self, tabview) -> None:
        ctk, ttk, tk = self.ctk, self.ttk, self.tk
        tab = tabview.add("Why / Log")

        top = ctk.CTkFrame(tab, fg_color="transparent")
        top.pack(fill="x", pady=(0, 10))
        self.preview_var = tk.BooleanVar()
        ctk.CTkCheckBox(top, text="Explain detections (capture an image of what changed)",
                        variable=self.preview_var, command=self._on_setting_change,
                        fg_color=_ACCENT, hover_color=_ACCENT_HOVER, border_color=_MUTED2,
                        checkmark_color="white", text_color=_TEXT).pack(anchor="w")
        ctk.CTkLabel(top, text="Click any row in the log to see why that click happened.",
                    text_color=_MUTED, anchor="w").pack(anchor="w", pady=(4, 0))

        # A resizable split: the log on top, the picture below, so neither can
        # crowd the other out and the user can drag the divider. No
        # CustomTkinter equivalent exists, so this stays plain ttk (restyled
        # to match in _build_style); each pane is itself a CTkFrame "card"
        # so the split still reads as two clearly separate sections.
        split = ttk.PanedWindow(tab, orient="vertical")
        split.pack(fill="both", expand=True)

        # --- the log itself: one selectable row per detection ---
        logcard = ctk.CTkFrame(split, corner_radius=14, fg_color=_CARD,
                                border_width=1, border_color=_CARD_BORDER)
        split.add(logcard, weight=1)
        logframe = ctk.CTkFrame(logcard, fg_color="transparent")
        logframe.pack(fill="both", expand=True, padx=12, pady=12)
        cols = ("click", "time", "change", "image")
        self.log_tree = ttk.Treeview(logframe, columns=cols, show="headings",
                                     height=6, selectmode="browse")
        for col, text, width, anchor in (
            ("click", "#", 50, "center"),
            ("time", "Time", 90, "center"),
            ("change", "Changed", 90, "e"),
            ("image", "Image", 70, "center"),
        ):
            self.log_tree.heading(col, text=text)
            self.log_tree.column(col, width=width, anchor=anchor, stretch=(col == "change"))
        self.log_tree.tag_configure("even", background=_CARD)
        self.log_tree.tag_configure("odd", background="#fafafb")
        scroll = ttk.Scrollbar(logframe, orient="vertical", command=self.log_tree.yview)
        self.log_tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.log_tree.pack(side="left", fill="both", expand=True)
        self.log_tree.bind("<<TreeviewSelect>>", self._on_log_select)
        self.log_tree.bind("<Double-1>", lambda e: self.open_preview_window())
        # X11 reports the wheel as buttons 4/5 (harmless no-ops on Windows,
        # which instead sends <MouseWheel>, bound below); bind both so the
        # log scrolls under the cursor on every platform without needing focus.
        self.log_tree.bind("<Button-4>", lambda e: self.log_tree.yview_scroll(-3, "units"))
        self.log_tree.bind("<Button-5>", lambda e: self.log_tree.yview_scroll(3, "units"))
        self.log_tree.bind("<MouseWheel>",
                           lambda e: self.log_tree.yview_scroll(-3 if e.delta > 0 else 3, "units"))

        # --- controls ---
        btns = ctk.CTkFrame(logcard, fg_color="transparent")
        btns.pack(fill="x", padx=12, pady=(0, 12))
        self.follow_var = tk.BooleanVar(value=True)
        ctk.CTkCheckBox(btns, text="Follow newest", variable=self.follow_var,
                        fg_color=_ACCENT, hover_color=_ACCENT_HOVER, border_color=_MUTED2,
                        checkmark_color="white", text_color=_TEXT).pack(side="left")
        self._btn(btns, "Clear", self.clear_log, width=70).pack(side="right")
        self.save_btn = self._btn(btns, "Save image…", self.save_preview_image,
                                  width=112, state="disabled")
        self.save_btn.pack(side="right", padx=4)
        self.view_btn = self._btn(btns, "View larger ⤢", self.open_preview_window,
                                  width=112, state="disabled")
        self.view_btn.pack(side="right", padx=4)

        # --- the picture for the selected row (lower half of the split) ---
        piccard = ctk.CTkFrame(split, corner_radius=14, fg_color=_CARD,
                                border_width=1, border_color=_CARD_BORDER)
        split.add(piccard, weight=2)
        picframe = ctk.CTkFrame(piccard, fg_color=_BG, corner_radius=10)
        picframe.pack(fill="both", expand=True, padx=12, pady=12)
        self.preview_lbl = ctk.CTkLabel(
            picframe,
            text="No detection selected yet.\nWhen a click is triggered it appears in the log above.",
            text_color=_MUTED, fg_color="transparent")
        self.preview_lbl.pack(fill="both", expand=True)
        self.preview_caption = ctk.CTkLabel(piccard, text="Red = what changed · cyan box = where.",
                                            text_color=_MUTED, wraplength=460, justify="left",
                                            anchor="w")
        self.preview_caption.pack(anchor="w", padx=12, pady=(0, 12))

    def _slider(self, parent, row, label, var, lo, hi, hint="", fmt="{:.0f}", steps=None):
        ctk = self.ctk
        ctk.CTkLabel(parent, text=label, text_color=_MUTED, anchor="w").grid(
            row=row, column=0, sticky="w", padx=(16, 0))
        value_lbl = ctk.CTkLabel(parent, text="", font=("Sans", 12, "bold"),
                                  fg_color=_ACCENT_TINT, text_color=_ACCENT,
                                  corner_radius=6, width=48, anchor="center")
        value_lbl.grid(row=row, column=2, sticky="e", padx=(0, 16))

        def _changed(_val=None):
            value_lbl.configure(text=fmt.format(var.get()))
            self._on_setting_change()

        extra = {"number_of_steps": steps} if steps else {}
        ctk.CTkSlider(parent, from_=lo, to=hi, variable=var, command=_changed,
                      fg_color=_TRACK, progress_color=_ACCENT, button_color=_ACCENT,
                      button_hover_color=_ACCENT_HOVER, **extra).grid(
            row=row, column=1, sticky="ew", padx=10)
        if hint:
            ctk.CTkLabel(parent, text=hint, text_color=_MUTED, font=("Sans", 10), anchor="w").grid(
                row=row + 1, column=1, columnspan=2, sticky="w", pady=(0, 10))
        self._slider_labels[label] = value_lbl

    def _stepper(self, parent, row, col, var, step, lo, hi, integer=False):
        """A CTkEntry with +/- buttons — CustomTkinter has no Spinbox."""
        ctk = self.ctk
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.grid(row=row, column=col, sticky="w", padx=8, pady=(0, 16))

        def _clamp(v):
            v = max(lo, min(hi, v))
            return int(v) if integer else round(v, 2)

        def _step(delta):
            try:
                cur = var.get()
            except (self.tk.TclError, ValueError):
                cur = lo
            var.set(_clamp(cur + delta))
            self._on_setting_change()

        def _on_commit(_evt=None):
            try:
                var.set(_clamp(var.get()))
            except (self.tk.TclError, ValueError):
                var.set(lo)
            self._on_setting_change()

        self._btn(frame, "−", lambda: _step(-step), width=28, height=28,
                  corner_radius=14, font=("Sans", 14)).grid(row=0, column=0)
        entry = ctk.CTkEntry(frame, textvariable=var, width=60, height=28,
                              fg_color=_CARD, border_color=_CARD_BORDER, text_color=_TEXT,
                              justify="center")
        entry.grid(row=0, column=1, padx=6)
        entry.bind("<Return>", _on_commit)
        entry.bind("<FocusOut>", _on_commit)
        self._btn(frame, "+", lambda: _step(step), width=28, height=28,
                  corner_radius=14, font=("Sans", 14)).grid(row=0, column=2)

    # ------------------------------------------------------- config <-> UI
    def _sync_widgets_from_config(self) -> None:
        c = self.config
        self.sensitivity_var.set(c.sensitivity)
        self.fps_var.set(c.fps)
        self.threshold_var.set(c.pixel_threshold)
        self.compare_var.set(c.compare_mode)
        self.button_var.set(c.click_button)
        self.type_var.set(c.click_type)
        self.cooldown_var.set(c.cooldown)
        self.delay_var.set(c.click_delay)
        self.maxclicks_var.set(c.max_clicks)
        self.sound_var.set(c.play_sound)
        self.hotkey_enabled_var.set(c.hotkeys_enabled)
        self.preview_var.set(c.show_detection_preview)
        self._refresh_target_labels()
        self._refresh_hotkey_labels()
        for label, var, fmt in (
            ("Sensitivity", self.sensitivity_var, "{:.0f}"),
            ("Check rate (fps)", self.fps_var, "{:.1f}"),
            ("Noise filter", self.threshold_var, "{:.0f}"),
        ):
            lbl = self._slider_labels.get(label)
            if lbl is not None:
                lbl.configure(text=fmt.format(var.get()))

    def _pull_config_from_widgets(self) -> None:
        c = self.config
        c.sensitivity = int(self.sensitivity_var.get())
        c.fps = float(self.fps_var.get())
        c.pixel_threshold = int(self.threshold_var.get())
        c.compare_mode = self.compare_var.get()
        c.click_button = self.button_var.get()
        c.click_type = self.type_var.get()
        c.cooldown = float(self.cooldown_var.get())
        c.click_delay = float(self.delay_var.get())
        try:
            c.max_clicks = int(self.maxclicks_var.get())
        except (ValueError, self.tk.TclError):
            c.max_clicks = 0
        c.play_sound = bool(self.sound_var.get())
        c.hotkeys_enabled = bool(self.hotkey_enabled_var.get())
        c.show_detection_preview = bool(self.preview_var.get())
        c.clamp()

    def _on_setting_change(self, *_args) -> None:
        # Live-apply while running; the Monitor reads the same Config object.
        self._pull_config_from_widgets()

    def _refresh_target_labels(self) -> None:
        c = self.config
        if c.region:
            self._style_chip(self.region_lbl, str(c.region), True)
        else:
            self._style_chip(self.region_lbl, "Not set", False)
        if c.click_x is not None and c.click_y is not None:
            self._style_chip(self.point_lbl, f"({c.click_x}, {c.click_y})", True)
        else:
            self._style_chip(self.point_lbl, "Not set", False)

    def _refresh_hotkey_labels(self) -> None:
        self._style_chip(self.toggle_hotkey_lbl, pretty(self.config.hotkey_toggle), True)
        self._style_chip(self.quit_hotkey_lbl, pretty(self.config.hotkey_quit), True)

    # ---------------------------------------------------------- selection
    def select_region(self) -> None:
        from .region_selector import select_region

        self.root.withdraw()
        self.root.update()
        try:
            region = select_region(self.root)
        finally:
            self.root.deiconify()
        if region is not None:
            self.config.region = region
            self._refresh_target_labels()

    def select_point(self) -> None:
        from .region_selector import select_point

        self.root.withdraw()
        self.root.update()
        try:
            point = select_point(self.root)
        finally:
            self.root.deiconify()
        if point is not None:
            self.config.click_x, self.config.click_y = point
            self._refresh_target_labels()

    # ------------------------------------------------------------- control
    def toggle(self) -> None:
        if self.monitor.is_running:
            self.monitor.stop()
        else:
            self._pull_config_from_widgets()
            if not self.config.is_ready:
                self._set_status("Select a region and a click point first.", _ERROR)
                return
            self.monitor.start()
        self._update_running_ui()

    def _update_running_ui(self) -> None:
        running = self.monitor.is_running
        if running:
            self.start_btn.configure(text="■  Stop", fg_color=_ERROR, hover_color=_ERROR_HOVER)
        else:
            self.start_btn.configure(text="▶  Start", fg_color=_ACCENT, hover_color=_ACCENT_HOVER)
        state = "disabled" if running else "normal"
        self.region_btn.configure(state=state)
        self.point_btn.configure(state=state)

    # -------------------------------------------------------------- events
    def _poll(self) -> None:
        """Drain hotkey actions and monitor events onto the Tk main loop.

        This must never raise: if it does, the ``after`` chain below is not
        rescheduled and the whole UI silently stops updating (log, status *and*
        global hotkeys, which are delivered through ``self._actions``).  So the
        body is fully guarded and rescheduling happens in ``finally``.
        """
        quitting = False
        try:
            while True:
                try:
                    action = self._actions.get_nowait()
                except queue.Empty:
                    break
                try:
                    if action == "toggle":
                        self._note_hotkey("start/stop")
                        self.toggle()
                    elif action == "quit":
                        quitting = True
                        self.on_close()
                        break
                except Exception as exc:  # noqa: BLE001
                    self._set_status(f"Hotkey action failed: {exc}", _ERROR)

            if not quitting:
                last_seen = None
                while True:
                    try:
                        last_seen = self._observed.get_nowait()
                    except queue.Empty:
                        break
                if last_seen is not None:
                    self._style_chip(self.hotkey_seen_lbl, last_seen, True)

                while True:
                    try:
                        ev = self._events.get_nowait()
                    except queue.Empty:
                        break
                    try:
                        self._handle_event(ev)
                    except Exception as exc:  # noqa: BLE001 - one bad event
                        # must never kill the loop
                        self._set_status(f"UI error: {exc}", _ERROR)
        finally:
            if not quitting:
                self.root.after(100, self._poll)

    def _handle_event(self, ev: MonitorEvent) -> None:
        if ev.kind == "started":
            self._set_status("● Watching…", _OK)
            self._update_running_ui()
        elif ev.kind == "stopped":
            self._set_status("Stopped.", _MUTED)
            self._update_running_ui()
        elif ev.kind == "clicked":
            self._set_status(ev.message, _OK)
            self._flash()
            if self.config.play_sound:
                self._beeper.play()
            # Records the detection and, when following, selects it — which
            # renders its image via the tree's selection handler.
            self._log_detection(ev)
        elif ev.kind == "limit":
            self._set_status(ev.message, _WARN)
        elif ev.kind == "error":
            self._set_status(ev.message, _ERROR)
            self._update_running_ui()

        if ev.kind in ("tick", "clicked", "started"):
            self.activity.set(min(1.0, ev.score * 3))
            self.stats_lbl.configure(
                text=f"clicks: {ev.clicks}   ·   uptime: {_fmt_uptime(ev.elapsed)}"
                     f"   ·   change: {ev.score * 100:.2f}%"
            )

    def _log_detection(self, ev: MonitorEvent) -> None:
        """Record a detection and add a selectable row for it."""
        self._history.set_capacity(self.config.log_history)
        # Row ids must be unique for the lifetime of the window.  The monitor's
        # click counter restarts at 1 every time monitoring is restarted, so
        # using it directly would collide with an existing row.
        self._row_seq += 1
        det = self._history.add(index=self._row_seq, score=ev.score, preview=ev.preview,
                                click_no=ev.clicks)

        self.log_tree.insert(
            "", "end", iid=str(det.index),
            values=(ev.clicks, det.time_str, det.score_str, "🖼" if det.has_image else "—"),
            tags=("even" if det.index % 2 == 0 else "odd",),
        )
        # Drop rows whose records have aged out of the bounded history.
        live = {str(d.index) for d in self._history}
        for iid in self.log_tree.get_children():
            if iid not in live:
                self.log_tree.delete(iid)

        if self.follow_var.get():
            self.log_tree.selection_set(str(det.index))
            self.log_tree.see(str(det.index))

    def _on_log_select(self, _event=None) -> None:
        """Show the picture for whichever detection the user picked."""
        sel = self.log_tree.selection()
        if not sel:
            return
        det = self._history.by_index(int(sel[0]))
        if det is None:
            return
        self._selected = det
        self._render_preview(det)

    def _render_preview(self, det) -> None:
        if not det.has_image:
            self._preview_photo = None
            self.preview_lbl.configure(
                image=None, text="No image was captured for this detection.\n"
                                "Enable “Explain detections” to capture them.")
            self.preview_caption.configure(
                text=f"Click #{det.click_no} at {det.time_str} — {det.score_str} of the region changed.")
            self.view_btn.configure(state="disabled")
            self.save_btn.configure(state="disabled")
            return
        try:
            import base64
            import io

            from PIL import Image

            pil_img = Image.open(io.BytesIO(base64.b64decode(det.preview)))
        except Exception:  # noqa: BLE001 - never let a bad image break the UI
            return
        # Shrink to fit the panel so a large region can never blow up the
        # layout (never upscale beyond the source image).
        avail_w = max(120, self.preview_lbl.winfo_width() - 16)
        avail_h = max(90, self.preview_lbl.winfo_height() - 16)
        scale = 1.0
        if pil_img.width and pil_img.height:
            scale = min(1.0, avail_w / pil_img.width, avail_h / pil_img.height)
        disp_size = (max(1, int(pil_img.width * scale)), max(1, int(pil_img.height * scale)))
        ctk_img = self.ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=disp_size)
        self._preview_photo = ctk_img  # hold a reference against GC
        self.preview_lbl.configure(image=ctk_img, text="")
        self.preview_caption.configure(
            text=f"Click #{det.click_no} at {det.time_str} — red marks the {det.score_str} "
                 f"of the region that changed and triggered this click.")
        self.view_btn.configure(state="normal")
        self.save_btn.configure(state="normal")

    def open_preview_window(self) -> None:
        """Open the selected detection's image in a larger, magnified window."""
        det = self._selected
        if det is None or not det.has_image:
            return
        ctk = self.ctk
        win = ctk.CTkToplevel(self.root)
        win.title(f"Why click #{det.click_no} fired — {det.time_str}")
        win.configure(fg_color=_BG)
        try:
            import base64
            import io

            from PIL import Image

            pil_img = Image.open(io.BytesIO(base64.b64decode(det.preview)))
        except Exception:  # noqa: BLE001
            win.destroy()
            return
        # Nearest-neighbour-ish magnify so small regions are actually readable.
        size = (pil_img.width, pil_img.height)
        if pil_img.width < 500:
            size = (pil_img.width * 2, pil_img.height * 2)
        photo = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=size)
        win._photo = photo  # keep a reference on the window itself
        ctk.CTkLabel(win, image=photo, text="").pack(padx=10, pady=(10, 4))
        ctk.CTkLabel(
            win,
            text=f"{det.score_str} of the watched region changed at {det.time_str}. "
                 f"Red = the pixels responsible.",
            wraplength=max(360, size[0]), text_color=_MUTED,
        ).pack(padx=10, pady=(0, 8))
        self._btn(win, "Close", win.destroy, kind="primary").pack(pady=(0, 10))
        win.bind("<Escape>", lambda e: win.destroy())
        win.transient(self.root)

    def save_preview_image(self) -> None:
        """Export the selected detection's image as a PNG."""
        import base64
        from tkinter import filedialog, messagebox

        det = self._selected
        if det is None or not det.has_image:
            return
        path = filedialog.asksaveasfilename(
            parent=self.root, defaultextension=".png",
            initialfile=f"screenwatch-click-{det.click_no}.png",
            filetypes=[("PNG image", "*.png")],
        )
        if not path:
            return
        try:
            with open(path, "wb") as fh:
                fh.write(base64.b64decode(det.preview))
            self._set_status(f"Saved image to {path}", _OK)
        except (OSError, ValueError) as exc:
            messagebox.showerror("Save failed", str(exc))

    def clear_log(self) -> None:
        self._history.clear()
        self._selected = None
        self._preview_photo = None
        for iid in self.log_tree.get_children():
            self.log_tree.delete(iid)
        self.preview_lbl.configure(image=None, text="Log cleared.")
        self.preview_caption.configure(text="Red highlights = the pixels that changed.")
        self.view_btn.configure(state="disabled")
        self.save_btn.configure(state="disabled")

    def _set_status(self, text: str, color: str = _MUTED) -> None:
        self.status_dot.configure(fg_color=color)
        self.status_lbl.configure(text=text, text_color=_status_text_color(color))

    def _flash(self) -> None:
        self.activity.set(1.0)
        self.root.after(120, lambda: self.activity.set(0))

    # -------------------------------------------------------------- hotkeys
    def _apply_hotkeys(self) -> None:
        self.hotkeys.stop()
        self.config.hotkeys_enabled = bool(self.hotkey_enabled_var.get())
        if not self.config.hotkeys_enabled:
            self._set_hotkey_status("Global hotkeys are disabled.", _MUTED)
            return
        t, q = self.config.hotkey_toggle, self.config.hotkey_quit
        if not (is_valid(t) and is_valid(q)):
            self._set_hotkey_status("Invalid hotkey combination.", _ERROR)
            return
        self.hotkeys.on_observed = self._observed.put
        ok = self.hotkeys.start({
            t: lambda: self._actions.put("toggle"),
            q: lambda: self._actions.put("quit"),
        })
        if ok:
            self._set_hotkey_status(
                f"Active — {pretty(t)} start/stop · {pretty(q)} quit", _OK)
        else:
            self._set_hotkey_status(
                f"Unavailable (Wayland or blocked). Use the Start button. {self.hotkeys.error or ''}",
                _ERROR)

    def _note_hotkey(self, which: str) -> None:
        """Confirm on screen that a global hotkey was actually received."""
        import time as _time

        stamp = _time.strftime("%H:%M:%S")
        self.hotkey_status_lbl.configure(
            text=f"✔ {which} hotkey received at {stamp}", text_color=_status_text_color(_OK))

    def _set_hotkey_status(self, text: str, color: str) -> None:
        self.hotkey_status_lbl.configure(text=text, text_color=_status_text_color(color))
        # Mirror a compact version on the always-visible control bar.
        self.hotkey_lbl.configure(text=text)

    def _capture_hotkey(self, which: str) -> None:
        ctk = self.ctk
        dlg = ctk.CTkToplevel(self.root)
        dlg.title("Set hotkey")
        dlg.configure(fg_color=_BG)
        dlg.transient(self.root)
        dlg.resizable(False, False)
        ctk.CTkLabel(dlg, text="Press the key combination you want.\n\n(Esc to cancel)",
                     font=("Sans", 12), text_color=_TEXT).pack(padx=28, pady=24)
        captured = {"combo": None}

        def on_key(event):
            if event.keysym in _MODIFIER_KEYSYMS:
                return  # wait for a real (non-modifier) key
            if event.keysym == "Escape" and not (event.state & 0x4C):
                dlg.destroy()
                return
            combo = _event_to_hotkey(event)
            if combo is None:
                return
            captured["combo"] = combo
            dlg.destroy()

        dlg.bind("<KeyPress>", on_key)
        dlg.grab_set()
        dlg.focus_force()
        self.root.wait_window(dlg)

        combo = captured["combo"]
        if combo:
            if which == "toggle":
                self.config.hotkey_toggle = combo
            else:
                self.config.hotkey_quit = combo
            self._refresh_hotkey_labels()
            self._apply_hotkeys()

    # ------------------------------------------------------------- menu ops
    def save_settings(self) -> None:
        self._pull_config_from_widgets()
        try:
            path = self.config.save()
            self._set_status(f"Settings saved to {path}", _OK)
        except OSError as exc:
            self._set_status(f"Could not save settings: {exc}", _ERROR)

    def reload_settings(self) -> None:
        self.monitor.stop()
        self.config = Config.load()
        self.monitor = Monitor(self.config, on_event=self._events.put)
        self._history.set_capacity(self.config.log_history)
        self._sync_widgets_from_config()
        self._apply_hotkeys()
        self._update_running_ui()
        self._set_status("Settings reloaded.", _OK)

    def show_about(self) -> None:
        # Native OS message box -- CustomTkinter has no themed equivalent
        # (nor does it need one; a system dialog is the expected UX here).
        from tkinter import messagebox

        messagebox.showinfo(
            f"About {__app_name__}",
            f"{__app_name__} {__version__}\n\n"
            "Watches a chosen screen area and clicks a chosen point the moment\n"
            "the area changes visually.\n\n"
            "Tips\n"
            "• Sensitivity high = reacts to tiny changes; low = only big ones.\n"
            "• Check rate low keeps CPU usage minimal for long sessions.\n"
            "• Cooldown prevents rapid repeat clicks.\n"
            "• 'Previous frame' reacts to any motion; 'Start frame' reacts to a\n"
            "  deviation from how the area looked when you pressed Start.\n"
            "• The 'Why / Log' tab shows exactly which pixels changed.\n\n"
            "Hotkeys are customizable in the Hotkeys tab.",
        )

    # --------------------------------------------------------------- close
    def on_close(self) -> None:
        try:
            self.monitor.stop()
        finally:
            self.hotkeys.stop()
            self._pull_config_from_widgets()
            try:
                self.config.save()
            except OSError:
                pass
            self.root.destroy()


def run(config: Optional[Config] = None) -> None:
    """Launch the GUI event loop."""
    import customtkinter as ctk

    # className sets WM_CLASS on X11, which desktop launchers use (via the
    # .desktop file's StartupWMClass) to match this window back to its icon
    # in the taskbar/alt-tab switcher. Ignored harmlessly on Windows. Tk
    # normalises whatever string is passed to "First letter capitalised,
    # rest lowercase" (verified: "ScreenWatch" in -> "Screenwatch" out), so
    # the .desktop file's StartupWMClass is set to match that real value.
    # CTk is a genuine tkinter.Tk subclass, so className/iconbitmap/
    # iconphoto all still work exactly as they did with plain tk.Tk.
    root = ctk.CTk(className="ScreenWatch")
    try:
        import sys
        import tkinter as tk

        from .paths import icon_ico_path, icon_path

        if sys.platform == "win32":
            ico = icon_ico_path()
            if ico:
                root.iconbitmap(default=ico)
        png = icon_path()
        if png:
            root.iconphoto(True, tk.PhotoImage(file=png))
    except Exception:  # noqa: BLE001 - a missing/bad icon must never block startup
        pass
    ScreenWatchApp(root, config)
    root.mainloop()
