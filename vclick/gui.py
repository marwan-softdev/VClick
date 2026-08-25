"""The VClick desktop GUI (CustomTkinter, with a couple of plain-ttk
widgets embedded where CustomTkinter has no equivalent — see the comment
in :meth:`VClickApp._build_style`).

Kept in one file for easy distribution. CustomTkinter/Tkinter are imported at
call time inside :func:`run` (and the app class's own methods) so this module
can still be imported for tooling/tests without a display.
"""

from __future__ import annotations

import queue
import threading
from typing import Optional

from . import __app_name__, __version__
from .config import (CLICK_BUTTONS, CLICK_TYPES, THEME_MODES, Config,
                     default_config_path)
from .history import DetectionHistory
from .hotkeys import HotkeyManager, is_valid, parse_hotkey, pretty
from .monitor import Monitor, MonitorEvent
from .sound import Beeper
from .updates import UpdateCheckResult, check_for_update

PAD = 14

# Config stores lowercase theme keys; the picker shows capitalised labels.
_THEME_LABELS = {"system": "System", "light": "Light", "dark": "Dark"}
_THEME_MODE_BY_LABEL = {v: k for k, v in _THEME_LABELS.items()}
CARD_GAP = 8

# ---------------------------------------------------------------------------
# Design tokens: inspired by Raycast's and CleanShot X's preference panes --
# a neutral canvas, bordered "cards" that group related fields (so it's
# obvious at a glance where one setting group ends and the next begins), one
# accent color reserved for the single primary action and for "this value is
# set" badges, and everything else in quiet neutrals so the accent still
# stands out where it's used.
#
# Every token is a ``(light, dark)`` pair, which is CustomTkinter's own
# convention: hand a widget a tuple and it picks the right half for the
# current appearance mode, then re-picks automatically when the mode changes.
# That means the whole app themes itself from this block alone -- widget
# construction below passes these tokens and never needs to know which mode
# is active. The two exceptions are the plain-ttk widgets in the Why/Log tab
# (ttk has no idea what a CTk tuple is) -- see _apply_ttk_theme, which
# resolves tokens by hand for those.
#
# Dark values are a deliberate palette, not a mechanical inversion, and every
# text/background pair below was contrast-checked against WCAG AA (4.5:1 for
# body text, 3:1 for large/bold) on the surface it actually sits on.
# ---------------------------------------------------------------------------
#                        light        dark
_BG           = ("#f2f2f5", "#141416")  # window canvas
_CARD         = ("#ffffff", "#1e1e21")  # card surface, raised off the canvas
_CARD_BORDER  = ("#e4e4e9", "#333338")  # hairline card border
_CARD_HOVER   = ("#d5d5da", "#3d3d44")  # hover for bordered/secondary controls
_SUBTLE       = ("#fafafb", "#26262b")  # faintly-tinted rows (table headers,
                                        # zebra striping) -- barely off _CARD
_DIVIDER      = ("#ececef", "#2a2a2e")  # subtle in-card divider
_TEXT         = ("#1c1c1e", "#f2f2f5")  # primary text (17:1 / 14.9:1)
# Muted text: the light half was darkened from an earlier #8a8a8e (~3.4:1 on
# white, under the AA 4.5:1 floor) to one that actually clears it.
_MUTED        = ("#6e6e73", "#9a9aa2")  # secondary text (5.1:1 / 5.95:1)
_MUTED2       = ("#c2c2c7", "#4a4a52")  # faint borders ONLY (unchecked
                                        # checkbox/radio outlines) -- far too
                                        # low-contrast for text either side
_ACCENT       = ("#0a84ff", "#1f86e8")  # accent FILLS only (Start button,
                                        # slider/progress fill, checkbox
                                        # fill). White sits on this, so the
                                        # dark half is deliberately not the
                                        # brighter #3b9dff: white on that is
                                        # 2.82:1, under even the large-text
                                        # 3:1 bar. #1f86e8 gives 3.73:1.
_ACCENT_HOVER = ("#0071e3", "#3b9dff")
_ACCENT_TEXT  = ("#0a5fc0", "#7ab8ff")  # accent as TEXT, on _ACCENT_TINT
                                        # (5.5:1 / 6.5:1) -- badges and the
                                        # slider value fields
_ACCENT_TINT  = ("#e8f2ff", "#16304d")  # tinted fill behind accent text
_TRACK        = ("#e4e4e9", "#333338")  # slider / progress-bar track

# Status colors. The vivid *dot* tones are used for small indicator dots
# (fine at any contrast, since they carry no text); the *_TEXT variants are
# tuned per mode so status wording stays readable on a card either side.
_OK,    _OK_TEXT    = ("#12b76a", "#3ddc97"), ("#067647", "#4ade80")
_WARN,  _WARN_TEXT  = ("#f79009", "#fdb022"), ("#b54708", "#fbbf24")
_ERROR, _ERROR_TEXT = ("#f04438", "#f97066"), ("#b42318", "#f87171")
_ERROR_HOVER = ("#d92d20", "#e5544a")

_STATUS_TEXT_COLORS = {_OK: _OK_TEXT, _WARN: _WARN_TEXT, _ERROR: _ERROR_TEXT}


def _status_text_color(color):
    """Map a status dot color to its readable-on-a-card text counterpart;
    anything not in the map passes through unchanged. Tokens are tuples,
    which are hashable, so they work as dict keys directly."""
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


class VClickApp:
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
        self._update_queue: "queue.Queue[UpdateCheckResult]" = queue.Queue()
        self.monitor = Monitor(self.config, on_event=self._events.put)
        self.hotkeys = HotkeyManager()
        self._history = DetectionHistory(self.config.log_history)
        self._beeper = Beeper(root)
        self._row_seq = 0           # monotonic, unique per window (see _log_detection)
        self._selected = None       # the Detection currently shown
        self._preview_photo = None  # keep a ref so Tk doesn't GC the image
        self._slider_labels = {}    # slider label text -> its value entry's StringVar
        self._autosave_job = None   # pending debounced save (see _schedule_autosave)
        self._update_check_running = False
        self._update_check_manual = False
        self._latest_release_url = None
        self._update_check_after_id = None

        root.title(f"{__app_name__} — auto-click on change")
        # Height in particular is much lower than the window's natural
        # size now on purpose: tab content scrolls (see _scrollable_tab),
        # so shrinking the window no longer hides anything -- this floor
        # only guards against genuinely too-small-to-use (buttons/labels
        # need some minimum room), not against fitting all content at once.
        root.minsize(480, 420)
        root.protocol("WM_DELETE_WINDOW", self.on_close)

        self._build_style()
        self._build_widgets()
        self._sync_widgets_from_config()

        self._apply_hotkeys()
        self.root.after(100, self._poll)
        # A short delay so the launch check doesn't compete with the
        # window's initial render.
        if self.config.auto_check_updates:
            self._update_check_after_id = self.root.after(
                1500, lambda: self._start_update_check(manual=False))

    # ------------------------------------------------------------------ UI
    def _mode_color(self, token):
        """Resolve a ``(light, dark)`` design token to the single hex string
        that plain-Tk/ttk widgets need. CustomTkinter widgets take the tuple
        directly and pick a half themselves; ttk has no such concept, so
        anything ttk-styled has to be resolved here and re-resolved whenever
        the appearance mode changes (see :meth:`_apply_ttk_theme`)."""
        return token[1] if self.ctk.get_appearance_mode() == "Dark" else token[0]

    def _build_style(self) -> None:
        self.ctk.set_default_color_theme("blue")
        # A tuple, so the canvas follows an appearance-mode change by itself.
        self.root.configure(fg_color=_BG)
        self.apply_theme(self.config.theme)

    def _apply_ttk_theme(self) -> None:
        """Restyle the plain-ttk widgets for the current appearance mode.

        ttk.Treeview/PanedWindow have no CustomTkinter equivalent (it ships
        no table/tree widget), so the Why/Log tab keeps them as real ttk
        widgets, hand-styled to match the surrounding cards instead of
        looking like a stray system-themed widget dropped into an otherwise
        custom window. Unlike every CTk widget, they do NOT follow an
        appearance-mode change on their own, so this runs again on every
        theme switch rather than once at startup.
        """
        c = self._mode_color
        style = self.ttk.Style()
        for theme in ("clam", "alt", "default"):
            if theme in style.theme_names():
                style.theme_use(theme)
                break
        style.configure("Treeview", background=c(_CARD), fieldbackground=c(_CARD),
                         foreground=c(_TEXT), borderwidth=0, rowheight=26)
        style.configure("Treeview.Heading", background=c(_SUBTLE), foreground=c(_MUTED),
                         borderwidth=0, relief="flat", font=("Sans", 10, "bold"))
        style.map("Treeview", background=[("selected", c(_ACCENT_TINT))],
                   foreground=[("selected", c(_TEXT))])
        style.configure("TPanedwindow", background=c(_BG))
        # Zebra striping lives on the tree's own tags, not the ttk style, so
        # it needs re-applying here too. Guarded because _apply_ttk_theme
        # runs once from _build_style before any tab exists.
        tree = getattr(self, "log_tree", None)
        if tree is not None:
            tree.tag_configure("even", background=c(_CARD))
            tree.tag_configure("odd", background=c(_SUBTLE))

    def apply_theme(self, mode: str) -> None:
        """Switch the whole window between light/dark/system, live.

        CustomTkinter repaints every one of its own widgets by itself when
        the appearance mode changes (each was handed a ``(light, dark)``
        token, so it just re-picks a half) -- no rebuild, no restart. Only
        the ttk widgets need a manual nudge afterwards.
        """
        self.ctk.set_appearance_mode(mode)
        self._apply_ttk_theme()

    # There is deliberately no menu bar. It held only File (Save settings /
    # Reload settings / Quit) and Help (About), and every one of those is now
    # either automatic or reachable in the window itself: settings save
    # themselves (see _schedule_autosave), "reload" is better expressed as
    # the Settings tab's explicit "Reset to defaults", About moved into the
    # Settings tab, and Quit was always available from the window's own close
    # button and the quit hotkey. A native tk.Menu was also the one surface
    # CustomTkinter can't theme, so dropping it removes the last widget that
    # couldn't follow the light/dark setting.

    def _build_widgets(self) -> None:
        ctk = self.ctk
        root = self.root

        header = ctk.CTkFrame(root, fg_color="transparent")
        header.pack(fill="x", padx=PAD, pady=(PAD, 4))
        ctk.CTkLabel(header, text="VisualClick", font=("Sans", 21, "bold"),
                     text_color=_TEXT, anchor="w").pack(fill="x")
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
            segmented_button_unselected_hover_color=_CARD_HOVER,
            text_color=_TEXT, text_color_disabled=_MUTED,
            # Left-aligned (CTkTabview centers by default) so the tab pill
            # shares the cards' left margin below it instead of floating
            # centered and narrower than everything it governs -- the two
            # tiers read as one layout system now, not a disconnected strip
            # on top of a grid (confirmed in a screenshot review).
            anchor="w",
        )
        tabview.pack(fill="both", expand=True, padx=PAD, pady=(4, PAD))
        self._build_tab_watch(tabview)
        self._build_tab_clicking(tabview)
        self._build_tab_hotkeys(tabview)
        self._build_tab_why(tabview)
        self._build_tab_settings(tabview)

        # Locks the window to a fixed initial size so switching tabs never
        # resizes it -- confirmed for real that it otherwise does: with no
        # geometry() call at all, Tk keeps auto-fitting the toplevel to
        # whichever tab's content is currently mapped, and CTkTabview only
        # ever shows one tab's frame at a time, so the window visibly grew
        # and shrank on every switch.
        #
        # This can't be computed from winfo_reqwidth()/reqheight() the way
        # it could before every tab held a CTkScrollableFrame: a scrollable
        # frame is designed to be handed an external size and scroll
        # whatever doesn't fit, so its own reqheight reflects its widget
        # defaults, not the true height of the cards inside it -- confirmed
        # for real (not assumed): asking for it here read as low as 573px
        # even though the Targets+Detection tab alone needs ~860 to show
        # without scrolling. 560x860 is that value, found empirically by
        # rendering the tallest tab (Targets & Detection) at a few
        # candidate heights and checking its scroll canvas's own content
        # bbox against its viewport until the smallest one that fits
        # without scrolling. Bump it if that tab's content grows later.
        root.geometry("560x860")

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

        # A bare, unlabeled bar here read as a stuck/broken progress
        # indicator (what is it counting up to?), especially at rest --
        # confirmed in a screenshot review. It's real signal once running
        # (live change intensity vs. the click threshold, from
        # _handle_event's ev.score), just needed a caption to say so.
        activity_row = ctk.CTkFrame(card, fg_color="transparent")
        activity_row.pack(fill="x", padx=16, pady=(0, 10))
        ctk.CTkLabel(activity_row, text="Activity", text_color=_MUTED,
                     font=("Sans", 9), width=44, anchor="w").pack(side="left")
        self.activity = ctk.CTkProgressBar(activity_row, height=5, corner_radius=3,
                                            fg_color=_TRACK, progress_color=_ACCENT)
        self.activity.set(0)
        self.activity.pack(side="left", fill="x", expand=True)

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
        visible at a glance, not just from reading the words. The font
        weight follows too: bold read as a real value either way at a
        glance (confirmed in a screenshot review -- "Not set" looked as
        prominent as an actual badge), so only a real value is bold now."""
        font = ("Sans", 12, "bold" if is_set else "normal")
        if is_set:
            label.configure(text=text, font=font, fg_color=_ACCENT_TINT, text_color=_ACCENT_TEXT)
        else:
            label.configure(text=text, font=font, fg_color="transparent", text_color=_MUTED)

    def _scrollable_tab(self, tabview, name):
        """A tab whose content scrolls instead of silently clipping when
        the window is resized smaller than its natural height. The window
        opens at a size that fits everything with no scrolling needed, but
        it's still a regular resizable window -- shrink it by hand (a
        smaller screen, wanting a more compact layout) and, before this,
        cards past the bottom edge just vanished with no scrollbar and no
        other way to reach them (confirmed for real, not assumed: this was
        reported as reproducible on a real window, not something this
        sandbox's own Xvfb testing had surfaced). Also used for the Why/Log
        tab -- its resizable split and the log table's own internal
        scrolling only cover the log rows themselves; the split as a whole,
        and the Save/View buttons and caption below it, could still get
        squashed off the bottom of the window with nothing able to reach
        them (see the note above that tab's own split for how its content
        still grows to fill extra room instead of just sitting at a fixed
        size once wrapped in this)."""
        ctk = self.ctk
        tab = tabview.add(name)
        scroll = ctk.CTkScrollableFrame(
            tab, fg_color="transparent",
            scrollbar_button_color=_CARD_BORDER, scrollbar_button_hover_color=_CARD_HOVER,
        )
        scroll.pack(fill="both", expand=True)
        return scroll

    def _build_tab_watch(self, tabview) -> None:
        ctk = self.ctk
        tab = self._scrollable_tab(tabview, "Targets & Detection")

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
                     hint="higher = reacts to smaller changes", steps=99, integer=True)
        self.fps_var = self.tk.DoubleVar()
        self._slider(detect, 4, "Check rate (fps)", self.fps_var, 0.5, 30,
                     hint="lower = less CPU", fmt="{:.1f}")
        self.threshold_var = self.tk.IntVar()
        self._slider(detect, 6, "Noise filter", self.threshold_var, 0, 100,
                     hint="ignore per-pixel changes below this", steps=100, integer=True)

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
        tab = self._scrollable_tab(tabview, "Clicking")

        behavior = self._section(tab, "Click Behavior")
        behavior.pack(fill="x", pady=(0, CARD_GAP))
        behavior.columnconfigure(3, weight=1)

        ctk.CTkLabel(behavior, text="Button", text_color=_MUTED, anchor="w").grid(
            row=2, column=0, sticky="w", padx=(16, 0), pady=(0, 14))
        self.button_var = self.tk.StringVar()
        ctk.CTkComboBox(behavior, variable=self.button_var, values=list(CLICK_BUTTONS),
                         width=110, state="readonly", fg_color=_CARD, border_color=_CARD_BORDER,
                         # A quiet gray, not the primary accent -- the
                         # dropdown arrow is routine chrome, not an action,
                         # and rendering it in Start-button blue competed
                         # for attention it hadn't earned (confirmed in a
                         # screenshot review). The arrow glyph itself
                         # renders dark regardless of this background.
                         button_color=_CARD_BORDER, button_hover_color=_CARD_HOVER,
                         dropdown_fg_color=_CARD, dropdown_text_color=_TEXT, text_color=_TEXT,
                         command=lambda _v: self._on_setting_change()).grid(
            row=2, column=1, sticky="w", padx=8, pady=(0, 14))
        ctk.CTkLabel(behavior, text="Type", text_color=_MUTED, anchor="w").grid(
            row=2, column=2, sticky="w", padx=(16, 0), pady=(0, 14))
        self.type_var = self.tk.StringVar()
        ctk.CTkComboBox(behavior, variable=self.type_var, values=list(CLICK_TYPES),
                         width=110, state="readonly", fg_color=_CARD, border_color=_CARD_BORDER,
                         # A quiet gray, not the primary accent -- the
                         # dropdown arrow is routine chrome, not an action,
                         # and rendering it in Start-button blue competed
                         # for attention it hadn't earned (confirmed in a
                         # screenshot review). The arrow glyph itself
                         # renders dark regardless of this background.
                         button_color=_CARD_BORDER, button_hover_color=_CARD_HOVER,
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
        tab = self._scrollable_tab(tabview, "Hotkeys")

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
                                               fg_color=_ACCENT_TINT, text_color=_ACCENT_TEXT,
                                               corner_radius=6, anchor="w")
        self.toggle_hotkey_lbl.grid(row=3, column=1, sticky="w", padx=8, pady=(0, 14))
        self._btn(card, "Change…", lambda: self._capture_hotkey("toggle"), width=90).grid(
            row=3, column=2, sticky="e", padx=(0, 16), pady=(0, 14))

        ctk.CTkLabel(card, text="Quit", text_color=_MUTED, anchor="w").grid(
            row=4, column=0, sticky="w", padx=(16, 0), pady=(0, 16))
        self.quit_hotkey_lbl = ctk.CTkLabel(card, text="", font=("Sans", 12, "bold"),
                                             fg_color=_ACCENT_TINT, text_color=_ACCENT_TEXT,
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
        tab = self._scrollable_tab(tabview, "Why / Log")

        top = ctk.CTkFrame(tab, fg_color="transparent")
        top.pack(fill="x", pady=(0, 10))
        self.preview_var = tk.BooleanVar()
        ctk.CTkCheckBox(top, text="Explain detections (capture an image of what changed)",
                        variable=self.preview_var, command=self._on_setting_change,
                        fg_color=_ACCENT, hover_color=_ACCENT_HOVER, border_color=_MUTED2,
                        checkmark_color="white", text_color=_TEXT).pack(anchor="w")
        ctk.CTkLabel(top, text="Click any row in the log to see why that click happened.",
                    text_color=_MUTED, anchor="w").pack(anchor="w", pady=(4, 0))

        # Packed before the split (which takes all remaining space below
        # it) so these rows always get the room they need instead of being
        # squeezed by the panes -- a ttk.PanedWindow divides its *already
        # allocated* space by each pane's weight once at layout time and
        # doesn't grow a pane to fit new content added to it later, so
        # anything placed inside a pane can silently overflow its frozen
        # bounds. Confirmed for real while building this: both the caption
        # (once it held a real, longer two-line message instead of the
        # short placeholder) and a button row briefly lived inside the
        # picture pane below and were clipped/overlapped the window's
        # bottom bar instead of the pane growing for them. Both live here
        # as normal siblings instead, in reading order under the pane they
        # describe/act on: image -> caption -> the actions that use it.
        pic_btns = ctk.CTkFrame(tab, fg_color="transparent")
        pic_btns.pack(side="bottom", fill="x", pady=(CARD_GAP, 0))
        self.save_btn = self._btn(pic_btns, "Save image…", self.save_preview_image,
                                  width=112, state="disabled")
        self.save_btn.pack(side="right", padx=(4, 0))
        self.view_btn = self._btn(pic_btns, "View larger ⤢", self.open_preview_window,
                                  width=112, state="disabled")
        self.view_btn.pack(side="right", padx=(4, 0))
        self.preview_caption = ctk.CTkLabel(tab, text="Red = what changed · cyan box = where.",
                                            text_color=_MUTED, wraplength=520, justify="left",
                                            anchor="w")
        self.preview_caption.pack(side="bottom", fill="x", pady=(4, 0))

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
        # height=4 (not more): the log/preview split has a fixed total
        # budget (the window doesn't grow when this tab is selected -- see
        # the note above the split), and every extra visible row here is
        # real height taken from the image pane below. The table scrolls,
        # so fewer visible rows doesn't lose access to older entries.
        self.log_tree = ttk.Treeview(logframe, columns=cols, show="headings",
                                     height=4, selectmode="browse")
        for col, text, width, anchor in (
            ("click", "#", 50, "center"),
            ("time", "Time", 90, "center"),
            ("change", "Changed", 90, "e"),
            ("image", "Image", 70, "center"),
        ):
            # anchor passed to both: ttk.Treeview.heading() defaults to
            # centered text regardless of the column's own data anchor, so
            # without this the "Changed" header sat centered while its
            # right-aligned percentage values sat under "Image" instead --
            # confirmed in a real screenshot, not assumed.
            self.log_tree.heading(col, text=text, anchor=anchor)
            self.log_tree.column(col, width=width, anchor=anchor, stretch=(col == "change"))
        # Zebra-stripe colors are applied by _apply_ttk_theme (which also
        # re-applies them on every theme switch), called below now that
        # self.log_tree exists for it to find.
        self._apply_ttk_theme()
        # A CTkScrollbar, not ttk.Scrollbar -- ttk's is the platform's own
        # native widget (visible up/down arrow buttons, a chunky 3D-look
        # thumb on Windows), which looked out of place next to everything
        # else here and isn't fully overridden by the ttk theme/style calls
        # above. CTkScrollbar still drives the Treeview's real yview/
        # yscrollcommand scroll protocol -- that part of the interface is a
        # standard Tk convention every scrollable widget implements, not
        # something specific to ttk's own scrollbar.
        scroll = ctk.CTkScrollbar(logframe, orientation="vertical", command=self.log_tree.yview,
                                   fg_color="transparent", button_color=_CARD_BORDER,
                                   button_hover_color=_CARD_HOVER)
        self.log_tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.log_tree.pack(side="left", fill="both", expand=True)
        self.log_tree.bind("<<TreeviewSelect>>", self._on_log_select)
        self.log_tree.bind("<Double-1>", lambda e: self.open_preview_window())
        # X11 reports the wheel as buttons 4/5 (harmless no-ops on Windows,
        # which instead sends <MouseWheel>, bound below); bind both so the
        # log scrolls under the cursor on every platform without needing focus.
        def _scroll_log_tree(units):
            self.log_tree.yview_scroll(units, "units")
            # This whole tab now lives inside the same CTkScrollableFrame as
            # every other tab (see _scrollable_tab / the note above split's
            # construction), which drives its own scrolling from a bind_all
            # that fires for a wheel event over *any* descendant, this table
            # included. Without "break" here to stop that bind_all handler
            # from also firing, one wheel notch over the table scrolled the
            # table's rows *and* the surrounding tab underneath it at the
            # same time -- confirmed for real, not assumed. "break" scopes
            # the wheel back to just the table while the cursor is over it,
            # exactly like it already was over every other widget.
            return "break"

        self.log_tree.bind("<Button-4>", lambda e: _scroll_log_tree(-3))
        self.log_tree.bind("<Button-5>", lambda e: _scroll_log_tree(3))
        self.log_tree.bind("<MouseWheel>", lambda e: _scroll_log_tree(-3 if e.delta > 0 else 3))

        # --- controls that act on the log/table itself ---
        btns = ctk.CTkFrame(logcard, fg_color="transparent")
        btns.pack(fill="x", padx=12, pady=(0, 12))
        self.follow_var = tk.BooleanVar(value=True)
        ctk.CTkCheckBox(btns, text="Follow newest", variable=self.follow_var,
                        fg_color=_ACCENT, hover_color=_ACCENT_HOVER, border_color=_MUTED2,
                        checkmark_color="white", text_color=_TEXT).pack(side="left")
        self._btn(btns, "Clear", self.clear_log, width=70).pack(side="right")

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

        # ttk.PanedWindow only negotiates each pane's *initial* size from
        # `weight`, using whatever its children happen to need at that one
        # moment -- confirmed unreliable here (the image pane ended up
        # shorter than its own required height in practice, clipping the
        # preview). Forcing the sash to the log card's own natural height
        # fixes that, but only once this tab has actually been mapped --
        # tried doing it unconditionally shortly after construction and
        # got the opposite failure instead: queried while "Why / Log" was
        # still hidden behind the default tab, logcard.winfo_reqheight()
        # came back near-zero (an unmapped widget's own children haven't
        # had a real geometry pass yet), which squeezed the log table
        # itself down to almost nothing when the sash "fixed" itself.
        # Deferring this to the tab actually being selected -- a real
        # geometry pass has happened by then -- gives an accurate reading.
        # Runs once; a user who drags the sash afterwards keeps their own
        # sash position, since this only fires again on hotkeys/*other*
        # tab switches when self._why_split_fixed is still False.
        self._why_split_fixed = False

        # _scrollable_tab's CTkScrollableFrame (see its own docstring) only
        # ever sizes itself to its content's *natural* height -- it never
        # stretches to fill extra room, which is fine for the other tabs (a
        # plain stack of fixed-height cards, nothing in them wants to grow)
        # but wrong here: this tab's picture pane is meant to expand and use
        # whatever space is available, the way it always did back when this
        # tab wasn't scrollable at all. Force the frame to at least the
        # canvas viewport's height -- never below its own natural content
        # height -- so `split`'s own expand=True still has real extra space
        # to grow into when the window is tall enough (unchanged from
        # before), while still letting the frame exceed the viewport, and
        # scroll, when the window is too small for everything to fit.
        # Confirmed for real this was needed: without it, shrinking the
        # window pushed the Save/View buttons and the caption below the
        # split off the bottom of the window with no scrollbar able to
        # reach them -- the exact "squashed and I can't scroll" bug this
        # whole tab conversion to _scrollable_tab exists to fix.
        canvas = tab._parent_canvas

        def _stretch_why_tab(_event=None):
            tab.update_idletasks()
            target = max(tab.winfo_reqheight(), canvas.winfo_height())
            canvas.itemconfigure(tab._create_window_id, height=target)

        canvas.bind("<Configure>", _stretch_why_tab, add="+")
        tab.bind("<Configure>", _stretch_why_tab, add="+")

        def _on_tab_changed():
            if tabview.get() != "Why / Log":
                return
            self.root.update_idletasks()
            _stretch_why_tab()
            if not self._why_split_fixed:
                self._why_split_fixed = True
                split.sashpos(0, logcard.winfo_reqheight())

        tabview.configure(command=_on_tab_changed)

    def _build_tab_settings(self, tabview) -> None:
        ctk = self.ctk
        tab = self._scrollable_tab(tabview, "Settings")

        # --- Appearance -----------------------------------------------------
        appearance = self._section(tab, "Appearance")
        appearance.pack(fill="x", pady=(0, CARD_GAP))
        ctk.CTkLabel(appearance, text="Theme", text_color=_MUTED, anchor="w").grid(
            row=2, column=0, sticky="w", padx=(16, 0), pady=(0, 6))
        self.theme_btn = ctk.CTkSegmentedButton(
            appearance, values=[_THEME_LABELS[m] for m in THEME_MODES],
            command=self._on_theme_change,
            fg_color=_CARD_BORDER, selected_color=_ACCENT,
            selected_hover_color=_ACCENT_HOVER, unselected_color=_CARD_BORDER,
            unselected_hover_color=_CARD_HOVER, text_color=_TEXT,
        )
        self.theme_btn.grid(row=2, column=1, columnspan=2, sticky="e",
                             padx=(8, 16), pady=(0, 6))
        ctk.CTkLabel(
            appearance,
            text="“System” follows your OS light/dark setting where the desktop\n"
                 "reports one, and falls back to light where it doesn't.",
            text_color=_MUTED, font=("Sans", 10), justify="left", anchor="w",
        ).grid(row=3, column=0, columnspan=3, sticky="w", padx=16, pady=(0, 16))

        # --- General --------------------------------------------------------
        general = self._section(tab, "General")
        general.pack(fill="x", pady=(0, CARD_GAP))
        ctk.CTkLabel(general, text="Detections to keep", text_color=_MUTED, anchor="w").grid(
            row=2, column=0, sticky="w", padx=(16, 0), pady=(0, 4))
        self.loghistory_var = self.tk.IntVar()
        self._stepper(general, 2, 1, self.loghistory_var, step=5, lo=5, hi=200, integer=True)
        ctk.CTkLabel(
            general,
            text="How many past detections stay browsable in the Why / Log tab.\n"
                 "Each keeps its image, so a lower number uses less memory.",
            text_color=_MUTED, font=("Sans", 10), justify="left", anchor="w",
        ).grid(row=3, column=0, columnspan=3, sticky="w", padx=16, pady=(0, 12))

        ctk.CTkFrame(general, height=1, fg_color=_DIVIDER).grid(
            row=4, column=0, columnspan=3, sticky="ew", padx=16, pady=(0, 12))
        ctk.CTkLabel(general, text="Reset everything", text_color=_MUTED, anchor="w").grid(
            row=5, column=0, sticky="w", padx=(16, 0), pady=(0, 16))
        self._btn(general, "Reset to defaults…", self.reset_settings, width=150).grid(
            row=5, column=2, sticky="e", padx=(0, 16), pady=(0, 16))

        # --- Updates ----------------------------------------------------------
        updates = self._section(tab, "Updates")
        updates.pack(fill="x", pady=(0, CARD_GAP))
        self.autocheck_var = self.tk.BooleanVar()
        ctk.CTkCheckBox(updates, text="Automatically check for updates on launch",
                         variable=self.autocheck_var, command=self._on_setting_change,
                         fg_color=_ACCENT, hover_color=_ACCENT_HOVER, border_color=_MUTED2,
                         checkmark_color="white", text_color=_TEXT).grid(
            row=2, column=0, columnspan=3, sticky="w", padx=(16, 0), pady=(0, 16))

        row3 = ctk.CTkFrame(updates, fg_color="transparent")
        row3.grid(row=3, column=0, columnspan=3, sticky="ew", padx=16, pady=(0, 8))
        self.update_status_lbl = ctk.CTkLabel(row3, text="Not checked yet", font=("Sans", 12, "bold"),
                                               fg_color="transparent", text_color=_MUTED,
                                               corner_radius=6, anchor="w")
        self.update_status_lbl.pack(side="left")
        self._style_chip(self.update_status_lbl, "Not checked yet", False)
        self.check_updates_btn = self._btn(
            row3, "Check for Updates", lambda: self._start_update_check(manual=True), width=150)
        self.check_updates_btn.pack(side="right")

        self.view_release_btn = self._btn(
            updates, "View release ↗", self._open_release_page, width=150)
        self.view_release_btn.grid(row=4, column=0, sticky="w", padx=(16, 0), pady=(0, 16))
        self.view_release_btn.grid_remove()

        # --- About ----------------------------------------------------------
        # Folded in from what used to be a native "Help > About" messagebox:
        # a modal system dialog was the one surface that could never match
        # the app's own styling, and the tips below are more useful sitting
        # in the window than hidden behind a menu.
        about = self._section(tab, f"About {__app_name__}")
        about.pack(fill="x", pady=(0, CARD_GAP))
        ctk.CTkLabel(about, text=f"Version {__version__}", text_color=_TEXT,
                     font=("Sans", 12, "bold"), anchor="w").grid(
            row=2, column=0, columnspan=3, sticky="w", padx=16, pady=(0, 8))
        ctk.CTkLabel(
            about,
            text="Watches a chosen screen area and clicks a chosen point the\n"
                 "moment that area changes visually.",
            text_color=_MUTED, justify="left", anchor="w",
        ).grid(row=3, column=0, columnspan=3, sticky="w", padx=16, pady=(0, 12))
        # Only tips that aren't already stated inline next to the control
        # they describe -- the old About box also explained Sensitivity and
        # Check rate, which the Detection tab's own hints under each slider
        # now cover, so repeating them here was pure duplication.
        ctk.CTkLabel(
            about,
            text="• Cooldown prevents rapid repeat clicks.\n"
                 "• “Previous frame” reacts to any motion; “Start frame” reacts to a\n"
                 "   deviation from how the area looked when you pressed Start.\n"
                 "• The Why / Log tab shows exactly which pixels changed.",
            text_color=_MUTED, font=("Sans", 11), justify="left", anchor="w",
        ).grid(row=4, column=0, columnspan=3, sticky="w", padx=16, pady=(0, 12))
        ctk.CTkLabel(about, text="Settings are saved automatically to:",
                     text_color=_MUTED, font=("Sans", 10), anchor="w").grid(
            row=5, column=0, columnspan=3, sticky="w", padx=16, pady=(0, 2))
        path_lbl = ctk.CTkLabel(about, text=default_config_path(), text_color=_MUTED,
                                 font=("Sans", 10), anchor="w", wraplength=470,
                                 justify="left")
        path_lbl.grid(row=6, column=0, columnspan=3, sticky="w", padx=16, pady=(0, 16))

    def _on_theme_change(self, label: str) -> None:
        """Apply a theme picked in Settings, immediately and permanently."""
        mode = _THEME_MODE_BY_LABEL.get(label, "system")
        self.config.theme = mode
        self.apply_theme(mode)
        self._schedule_autosave()

    def reset_settings(self) -> None:
        """Restore every setting to its default, after confirming."""
        from tkinter import messagebox

        if not messagebox.askyesno(
            "Reset settings",
            "Reset all settings back to their defaults?\n\n"
            "This clears the watch region, click point, hotkeys and every\n"
            "preference. It can't be undone.",
            parent=self.root,
        ):
            return
        self.monitor.stop()
        self.config = Config()
        self.monitor = Monitor(self.config, on_event=self._events.put)
        self._history.set_capacity(self.config.log_history)
        self._sync_widgets_from_config()
        self.apply_theme(self.config.theme)
        self._apply_hotkeys()
        self._update_running_ui()
        self._schedule_autosave()
        self._set_status("Settings reset to defaults.", _OK)

    def _slider(self, parent, row, label, var, lo, hi, hint="", fmt="{:.0f}",
                steps=None, integer=False):
        ctk = self.ctk
        ctk.CTkLabel(parent, text=label, text_color=_MUTED, anchor="w").grid(
            row=row, column=0, sticky="w", padx=(16, 0))

        # A real editable field, not a read-only badge -- so a value can be
        # typed exactly rather than only dragged, which matters for anyone
        # who can't reliably land a slider thumb on a precise point. It
        # keeps a visible border (unlike the flat, borderless "value is
        # set" badges used elsewhere for read-only info) so it reads as
        # something to click into, not just a status display.
        value_var = self.tk.StringVar(value=fmt.format(var.get()))
        entry = ctk.CTkEntry(parent, textvariable=value_var, width=56, height=26,
                              justify="center", fg_color=_CARD, border_color=_CARD_BORDER,
                              text_color=_ACCENT_TEXT, font=("Sans", 12, "bold"))
        entry.grid(row=row, column=2, sticky="e", padx=(0, 16))

        def _clamp(v):
            v = max(lo, min(hi, v))
            return int(round(v)) if integer else round(v, 2)

        def _from_slider(_val=None):
            value_var.set(fmt.format(var.get()))
            self._on_setting_change()

        def _from_entry(_evt=None):
            try:
                v = _clamp(float(value_var.get()))
            except (ValueError, self.tk.TclError):
                v = var.get()
            var.set(v)
            value_var.set(fmt.format(var.get()))
            self._on_setting_change()

        entry.bind("<Return>", _from_entry)
        entry.bind("<FocusOut>", _from_entry)

        extra = {"number_of_steps": steps} if steps else {}
        ctk.CTkSlider(parent, from_=lo, to=hi, variable=var, command=_from_slider,
                      fg_color=_TRACK, progress_color=_ACCENT, button_color=_ACCENT,
                      button_hover_color=_ACCENT_HOVER, **extra).grid(
            row=row, column=1, sticky="ew", padx=10)
        if hint:
            ctk.CTkLabel(parent, text=hint, text_color=_MUTED, font=("Sans", 10), anchor="w").grid(
                row=row + 1, column=1, columnspan=2, sticky="w", pady=(0, 10))
        self._slider_labels[label] = value_var

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

        # 32x32 (not the initial 28x28): a larger click target for anyone
        # with imprecise pointing, closer to the commonly-cited 24-44px
        # comfortable range for a mouse/trackpad target.
        self._btn(frame, "−", lambda: _step(-step), width=32, height=32,
                  corner_radius=16, font=("Sans", 15)).grid(row=0, column=0)
        entry = ctk.CTkEntry(frame, textvariable=var, width=60, height=32,
                              fg_color=_CARD, border_color=_CARD_BORDER, text_color=_TEXT,
                              justify="center")
        entry.grid(row=0, column=1, padx=6)
        entry.bind("<Return>", _on_commit)
        entry.bind("<FocusOut>", _on_commit)
        self._btn(frame, "+", lambda: _step(step), width=32, height=32,
                  corner_radius=16, font=("Sans", 15)).grid(row=0, column=2)

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
        self.loghistory_var.set(c.log_history)
        self.theme_btn.set(_THEME_LABELS.get(c.theme, "System"))
        self.autocheck_var.set(c.auto_check_updates)
        self._refresh_target_labels()
        self._refresh_hotkey_labels()
        for label, var, fmt in (
            ("Sensitivity", self.sensitivity_var, "{:.0f}"),
            ("Check rate (fps)", self.fps_var, "{:.1f}"),
            ("Noise filter", self.threshold_var, "{:.0f}"),
        ):
            value_var = self._slider_labels.get(label)
            if value_var is not None:
                value_var.set(fmt.format(var.get()))

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
        try:
            c.log_history = int(self.loghistory_var.get())
        except (ValueError, self.tk.TclError):
            pass  # mid-edit garbage in the entry; keep the last good value
        c.auto_check_updates = bool(self.autocheck_var.get())
        c.clamp()
        self._history.set_capacity(c.log_history)

    def _on_setting_change(self, *_args) -> None:
        # Live-apply while running; the Monitor reads the same Config object.
        self._pull_config_from_widgets()
        self._schedule_autosave()

    def _schedule_autosave(self, delay_ms: int = 800) -> None:
        """Persist settings shortly after the last change.

        There's no explicit "Save settings" action any more (the File menu
        it lived on is gone), so settings have to persist on their own. This
        is debounced rather than saving on every change because a single
        slider drag fires a change per pixel of travel -- that would be
        hundreds of disk writes for one gesture. Any pending save is
        cancelled and re-scheduled, so the write happens once things settle.
        """
        if self._autosave_job is not None:
            try:
                self.root.after_cancel(self._autosave_job)
            except Exception:  # noqa: BLE001 - a stale id must not break saving
                pass
        self._autosave_job = self.root.after(delay_ms, self._autosave_now)

    def _autosave_now(self) -> None:
        self._autosave_job = None
        try:
            self.config.save()
        except OSError as exc:
            # Never interrupt the user mid-task for this; on_close retries.
            self._set_status(f"Could not save settings: {exc}", _WARN)

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

        geo = self.root.geometry()
        self.root.withdraw()
        self.root.update()
        try:
            region = select_region(self.root)
        finally:
            self._restore_window(geo)
        if region is not None:
            self.config.region = region
            self._refresh_target_labels()

    def select_point(self) -> None:
        from .region_selector import select_point

        geo = self.root.geometry()
        self.root.withdraw()
        self.root.update()
        try:
            point = select_point(self.root)
        finally:
            self._restore_window(geo)
        if point is not None:
            self.config.click_x, self.config.click_y = point
            self._refresh_target_labels()

    def _restore_window(self, geo: str) -> None:
        """Bring the window back after it was withdrawn for a screen
        selection, at the exact position it was at before -- not wherever
        the window manager decides to place it.

        ``root.geometry("560x860")`` at startup only ever requests a size,
        never a position, so Tk never records an explicit position request
        for this window. withdraw()/deiconify() unmaps and remaps it, and on
        remap a window with no requested position gets re-placed by the
        window manager's own initial-placement policy -- confirmed for real:
        under a real WM this consistently snapped the window back to the
        same spot every time, discarding wherever the user had dragged it.
        Re-applying the geometry captured just before withdraw() (which,
        once the window has been shown at least once, includes its current
        position) pins it back to that same spot instead.
        """
        self.root.deiconify()
        self.root.geometry(geo)

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

                while True:
                    try:
                        result = self._update_queue.get_nowait()
                    except queue.Empty:
                        break
                    try:
                        self._handle_update_result(result)
                    except Exception as exc:  # noqa: BLE001 - one bad result
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

    # ---------------------------------------------------------- updates
    def _start_update_check(self, manual: bool) -> None:
        """Kick off a background check; the result lands on ``_update_queue``
        and is picked up by ``_poll`` -- the network call itself never
        touches Tk, mirroring how ``Monitor`` only ever calls back into a
        thread-safe queue."""
        if self._update_check_running:
            return
        self._update_check_running = True
        self._update_check_manual = manual
        self.check_updates_btn.configure(state="disabled")
        self._style_chip(self.update_status_lbl, "Checking…", False)
        threading.Thread(
            target=lambda: self._update_queue.put(check_for_update()),
            daemon=True,
        ).start()

    def _handle_update_result(self, result: UpdateCheckResult) -> None:
        self._update_check_running = False
        self.check_updates_btn.configure(state="normal")
        self._latest_release_url = result.release_url

        if result.status == "update_available":
            self._style_chip(self.update_status_lbl, "Update available", True)
            self.view_release_btn.grid()
        else:
            text = {
                "up_to_date": "You're up to date",
                "not_applicable": "Not available for this build",
                "error": "Couldn't check for updates",
            }.get(result.status, result.message)
            self._style_chip(self.update_status_lbl, text, False)
            self.view_release_btn.grid_remove()

        # An unrequested background check staying quiet on "nothing to
        # report" (or a network hiccup) matches how autosave failures are
        # already handled -- a manual click always gets a response.
        if self._update_check_manual:
            color = _OK if result.status == "update_available" else _MUTED
            if result.status == "error":
                color = _WARN
            self._set_status(result.message, color)
        elif result.status == "update_available":
            self._set_status("Update available — see Settings ▸ Updates.", _WARN)

    def _open_release_page(self) -> None:
        if self._latest_release_url:
            import webbrowser

            webbrowser.open(self._latest_release_url)

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
            initialfile=f"vclick-click-{det.click_no}.png",
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
            self._set_hotkey_status("Global hotkeys are disabled.", _MUTED, bar_text="")
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
            # Doesn't repeat the combos here -- they're already the two
            # badges directly above, in the Start/Stop and Quit rows. The
            # control bar (visible from every tab, where those badges
            # aren't on screen) is the one place that still spells them
            # out, so the combos exist on screen exactly twice, not three
            # times, and each occurrence earns its place.
            self._set_hotkey_status("Active — hotkeys are working.", _OK,
                bar_text=f"{pretty(t)} start/stop · {pretty(q)} quit")
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

    def _set_hotkey_status(self, text: str, color: str, bar_text: Optional[str] = None) -> None:
        self.hotkey_status_lbl.configure(text=text, text_color=_status_text_color(color))
        # The control bar is visible from every tab; callers pass a
        # distinct, terser bar_text where the full sentence would just be
        # duplicate clutter, defaulting to the same text for warnings that
        # are genuinely worth surfacing everywhere verbatim.
        self.hotkey_lbl.configure(text=text if bar_text is None else bar_text)

    def _capture_hotkey(self, which: str) -> None:
        ctk = self.ctk
        dlg = ctk.CTkToplevel(self.root)
        dlg.title("Set hotkey")
        dlg.configure(fg_color=_BG)
        dlg.transient(self.root)
        dlg.resizable(False, False)

        # A real card, not bare text on the plain canvas -- this was the
        # one surface in the app with no border, no card, and no visible
        # button (Esc-only dismissal), breaking from the card language
        # used everywhere else (confirmed in a screenshot review).
        card = ctk.CTkFrame(dlg, corner_radius=14, fg_color=_CARD,
                             border_width=1, border_color=_CARD_BORDER)
        card.pack(padx=20, pady=20)
        ctk.CTkLabel(card, text="Press the key combination you want.",
                     font=("Sans", 13, "bold"), text_color=_TEXT).pack(padx=32, pady=(26, 4))
        ctk.CTkLabel(card, text="Esc also cancels", font=("Sans", 11),
                     text_color=_MUTED).pack(padx=32, pady=(0, 18))
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

        self._btn(card, "Cancel", dlg.destroy).pack(padx=32, pady=(0, 22))

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

    # --------------------------------------------------------------- close
    def on_close(self) -> None:
        try:
            self.monitor.stop()
        finally:
            self.hotkeys.stop()
            # Drop any debounced save still in flight -- it would fire against
            # a destroyed window. The unconditional save below covers it, and
            # is also the backstop for changes made inside the debounce window.
            if self._autosave_job is not None:
                try:
                    self.root.after_cancel(self._autosave_job)
                except Exception:  # noqa: BLE001
                    pass
                self._autosave_job = None
            if self._update_check_after_id is not None:
                try:
                    self.root.after_cancel(self._update_check_after_id)
                except Exception:  # noqa: BLE001
                    pass
                self._update_check_after_id = None
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
    # rest lowercase" (verified: "VClick" in -> "Vclick" out), so
    # the .desktop file's StartupWMClass is set to match that real value.
    # CTk is a genuine tkinter.Tk subclass, so className/iconbitmap/
    # iconphoto all still work exactly as they did with plain tk.Tk.
    root = ctk.CTk(className="VClick")
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
    VClickApp(root, config)
    root.mainloop()
