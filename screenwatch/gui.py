"""The ScreenWatch desktop GUI (Tkinter/ttk).

Kept in one file for easy distribution.  Tkinter is imported at call time inside
:func:`run` so the module can be imported for tooling/tests without a display.
"""

from __future__ import annotations

import queue
from typing import Optional

from . import __app_name__, __version__
from .config import CLICK_BUTTONS, CLICK_TYPES, Config
from .history import DetectionHistory
from .hotkeys import HotkeyManager, is_valid, pretty
from .monitor import Monitor, MonitorEvent

PAD = 8

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
    # Confirm pynput can actually register it before we accept it.
    try:
        from pynput import keyboard

        keyboard.HotKey.parse(combo)
    except Exception:  # noqa: BLE001
        return None
    return combo


class ScreenWatchApp:
    """Builds the window, wires widgets to a shared :class:`Config`, and drives
    a :class:`Monitor` worker."""

    def __init__(self, root, config: Optional[Config] = None) -> None:
        import tkinter as tk
        from tkinter import ttk

        self.tk = tk
        self.ttk = ttk
        self.root = root
        self.config = config or Config.load()
        self.config.clamp()

        self._events: "queue.Queue[MonitorEvent]" = queue.Queue()
        self._actions: "queue.Queue[str]" = queue.Queue()
        self.monitor = Monitor(self.config, on_event=self._events.put)
        self.hotkeys = HotkeyManager()
        self._history = DetectionHistory(self.config.log_history)
        self._selected = None       # the Detection currently shown
        self._preview_photo = None  # keep a ref so Tk doesn't GC the image

        root.title(f"{__app_name__} — auto-click on change")
        root.minsize(500, 660)
        root.protocol("WM_DELETE_WINDOW", self.on_close)

        self._build_style()
        self._build_menu()
        self._build_widgets()
        self._sync_widgets_from_config()

        self._apply_hotkeys()
        self.root.after(100, self._poll)

    # ------------------------------------------------------------------ UI
    def _build_style(self) -> None:
        style = self.ttk.Style()
        for theme in ("clam", "alt", "default"):
            if theme in style.theme_names():
                style.theme_use(theme)
                break
        style.configure("Header.TLabel", font=("Sans", 15, "bold"))
        style.configure("Value.TLabel", foreground="#2b6cb0")
        style.configure("Start.TButton", font=("Sans", 12, "bold"), padding=8)
        style.configure("Status.TLabel", font=("Sans", 11, "bold"))

    def _build_menu(self) -> None:
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
        tk, ttk = self.tk, self.ttk
        root = self.root

        header = ttk.Frame(root, padding=(PAD, PAD, PAD, 0))
        header.pack(fill="x")
        ttk.Label(header, text="ScreenWatch", style="Header.TLabel").pack(anchor="w")
        ttk.Label(header, text="Watches a screen area and clicks the instant it changes.",
                  foreground="#666").pack(anchor="w")

        # Persistent control bar pinned to the bottom.
        self._build_control_bar(root)

        # Tabbed settings fill the middle.
        nb = ttk.Notebook(root)
        nb.pack(fill="both", expand=True, padx=PAD, pady=PAD)
        self._build_tab_watch(nb)
        self._build_tab_clicking(nb)
        self._build_tab_hotkeys(nb)
        self._build_tab_why(nb)

    def _build_control_bar(self, root) -> None:
        ttk = self.ttk
        bar = ttk.Frame(root, padding=PAD)
        bar.pack(side="bottom", fill="x")

        self.start_btn = ttk.Button(bar, text="▶  Start", style="Start.TButton", command=self.toggle)
        self.start_btn.pack(fill="x")
        self.activity = ttk.Progressbar(bar, maximum=100, mode="determinate")
        self.activity.pack(fill="x", pady=(PAD, 2))
        self.status_lbl = ttk.Label(bar, text="Idle — select targets to begin.", style="Status.TLabel")
        self.status_lbl.pack(anchor="w")
        self.stats_lbl = ttk.Label(bar, text="", foreground="#555")
        self.stats_lbl.pack(anchor="w")
        self.hotkey_lbl = ttk.Label(bar, text="", foreground="#777", font=("Sans", 9))
        self.hotkey_lbl.pack(anchor="w", pady=(4, 0))

    def _build_tab_watch(self, nb) -> None:
        tk, ttk = self.tk, self.ttk
        tab = ttk.Frame(nb, padding=PAD)
        nb.add(tab, text="Targets & Detection")

        targets = ttk.LabelFrame(tab, text="Targets", padding=PAD)
        targets.pack(fill="x")
        targets.columnconfigure(1, weight=1)
        ttk.Label(targets, text="Watch region:").grid(row=0, column=0, sticky="w")
        self.region_lbl = ttk.Label(targets, text="(none)", style="Value.TLabel")
        self.region_lbl.grid(row=0, column=1, sticky="w", padx=PAD)
        self.region_btn = ttk.Button(targets, text="Select…", command=self.select_region)
        self.region_btn.grid(row=0, column=2, sticky="e")
        ttk.Label(targets, text="Click point:").grid(row=1, column=0, sticky="w", pady=(6, 0))
        self.point_lbl = ttk.Label(targets, text="(none)", style="Value.TLabel")
        self.point_lbl.grid(row=1, column=1, sticky="w", padx=PAD, pady=(6, 0))
        self.point_btn = ttk.Button(targets, text="Select…", command=self.select_point)
        self.point_btn.grid(row=1, column=2, sticky="e", pady=(6, 0))

        detect = ttk.LabelFrame(tab, text="Detection", padding=PAD)
        detect.pack(fill="x", pady=(PAD, 0))
        detect.columnconfigure(1, weight=1)

        self.sensitivity_var = tk.IntVar()
        self._slider(detect, 0, "Sensitivity", self.sensitivity_var, 1, 100,
                     hint="higher = reacts to smaller changes")
        self.fps_var = tk.DoubleVar()
        self._slider(detect, 2, "Check rate (fps)", self.fps_var, 0.5, 30,
                     hint="lower = less CPU", fmt="{:.1f}")
        self.threshold_var = tk.IntVar()
        self._slider(detect, 4, "Noise filter", self.threshold_var, 0, 100,
                     hint="ignore per-pixel changes below this")

        ttk.Label(detect, text="Compare against:").grid(row=6, column=0, sticky="w", pady=(6, 0))
        self.compare_var = tk.StringVar()
        cmp_frame = ttk.Frame(detect)
        cmp_frame.grid(row=6, column=1, columnspan=2, sticky="w", pady=(6, 0))
        ttk.Radiobutton(cmp_frame, text="Previous frame (any change)", value="previous",
                        variable=self.compare_var, command=self._on_setting_change).pack(anchor="w")
        ttk.Radiobutton(cmp_frame, text="Start frame (deviation from state)", value="baseline",
                        variable=self.compare_var, command=self._on_setting_change).pack(anchor="w")

    def _build_tab_clicking(self, nb) -> None:
        tk, ttk = self.tk, self.ttk
        tab = ttk.Frame(nb, padding=PAD)
        nb.add(tab, text="Clicking")
        for c in (1, 3):
            tab.columnconfigure(c, weight=1)

        ttk.Label(tab, text="Button:").grid(row=0, column=0, sticky="w")
        self.button_var = tk.StringVar()
        ttk.Combobox(tab, textvariable=self.button_var, values=list(CLICK_BUTTONS),
                     state="readonly", width=8).grid(row=0, column=1, sticky="w", padx=(4, PAD))
        ttk.Label(tab, text="Type:").grid(row=0, column=2, sticky="w")
        self.type_var = tk.StringVar()
        ttk.Combobox(tab, textvariable=self.type_var, values=list(CLICK_TYPES),
                     state="readonly", width=8).grid(row=0, column=3, sticky="w", padx=4)

        ttk.Label(tab, text="Cooldown (s):").grid(row=1, column=0, sticky="w", pady=(8, 0))
        self.cooldown_var = tk.DoubleVar()
        ttk.Spinbox(tab, from_=0, to=3600, increment=0.5, width=8, textvariable=self.cooldown_var,
                    command=self._on_setting_change).grid(row=1, column=1, sticky="w", padx=(4, PAD), pady=(8, 0))
        ttk.Label(tab, text="Delay (s):").grid(row=1, column=2, sticky="w", pady=(8, 0))
        self.delay_var = tk.DoubleVar()
        ttk.Spinbox(tab, from_=0, to=60, increment=0.1, width=8, textvariable=self.delay_var,
                    command=self._on_setting_change).grid(row=1, column=3, sticky="w", padx=4, pady=(8, 0))

        ttk.Label(tab, text="Max clicks:").grid(row=2, column=0, sticky="w", pady=(8, 0))
        self.maxclicks_var = tk.IntVar()
        ttk.Spinbox(tab, from_=0, to=1_000_000, increment=1, width=8, textvariable=self.maxclicks_var,
                    command=self._on_setting_change).grid(row=2, column=1, sticky="w", padx=(4, PAD), pady=(8, 0))
        ttk.Label(tab, text="(0 = unlimited)", foreground="#777").grid(
            row=2, column=2, columnspan=2, sticky="w", pady=(8, 0))

        self.sound_var = tk.BooleanVar()
        ttk.Checkbutton(tab, text="Beep on each click", variable=self.sound_var,
                        command=self._on_setting_change).grid(
            row=3, column=0, columnspan=4, sticky="w", pady=(10, 0))

    def _build_tab_hotkeys(self, nb) -> None:
        tk, ttk = self.tk, self.ttk
        tab = ttk.Frame(nb, padding=PAD)
        nb.add(tab, text="Hotkeys")
        tab.columnconfigure(1, weight=1)

        self.hotkey_enabled_var = tk.BooleanVar()
        ttk.Checkbutton(tab, text="Enable global hotkeys", variable=self.hotkey_enabled_var,
                        command=self._apply_hotkeys).grid(row=0, column=0, columnspan=3, sticky="w")

        ttk.Label(tab, text="Start / Stop:").grid(row=1, column=0, sticky="w", pady=(10, 0))
        self.toggle_hotkey_lbl = ttk.Label(tab, text="", style="Value.TLabel")
        self.toggle_hotkey_lbl.grid(row=1, column=1, sticky="w", padx=PAD, pady=(10, 0))
        ttk.Button(tab, text="Change…", command=lambda: self._capture_hotkey("toggle")).grid(
            row=1, column=2, sticky="e", pady=(10, 0))

        ttk.Label(tab, text="Quit:").grid(row=2, column=0, sticky="w", pady=(6, 0))
        self.quit_hotkey_lbl = ttk.Label(tab, text="", style="Value.TLabel")
        self.quit_hotkey_lbl.grid(row=2, column=1, sticky="w", padx=PAD, pady=(6, 0))
        ttk.Button(tab, text="Change…", command=lambda: self._capture_hotkey("quit")).grid(
            row=2, column=2, sticky="e", pady=(6, 0))

        self.hotkey_status_lbl = ttk.Label(tab, text="", foreground="#555", wraplength=440)
        self.hotkey_status_lbl.grid(row=3, column=0, columnspan=3, sticky="w", pady=(12, 0))
        ttk.Label(
            tab,
            text="Global hotkeys work on X11. On Wayland the system usually blocks them —\n"
                 "use the Start button instead.",
            foreground="#777", font=("Sans", 9),
        ).grid(row=4, column=0, columnspan=3, sticky="w", pady=(10, 0))

    def _build_tab_why(self, nb) -> None:
        tk, ttk = self.tk, self.ttk
        tab = ttk.Frame(nb, padding=PAD)
        nb.add(tab, text="Why / Log")

        self.preview_var = tk.BooleanVar()
        ttk.Checkbutton(tab, text="Explain detections (capture an image of what changed)",
                        variable=self.preview_var, command=self._on_setting_change).pack(anchor="w")
        ttk.Label(tab, text="Click any row in the log to see why that click happened.",
                  foreground="#666").pack(anchor="w", pady=(2, PAD))

        # --- the log itself: one selectable row per detection ---
        logframe = ttk.Frame(tab)
        logframe.pack(fill="both", expand=True)
        cols = ("click", "time", "change", "image")
        self.log_tree = ttk.Treeview(logframe, columns=cols, show="headings",
                                     height=7, selectmode="browse")
        for col, text, width, anchor in (
            ("click", "#", 50, "center"),
            ("time", "Time", 90, "center"),
            ("change", "Changed", 90, "e"),
            ("image", "Image", 70, "center"),
        ):
            self.log_tree.heading(col, text=text)
            self.log_tree.column(col, width=width, anchor=anchor, stretch=(col == "change"))
        scroll = ttk.Scrollbar(logframe, orient="vertical", command=self.log_tree.yview)
        self.log_tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.log_tree.pack(side="left", fill="both", expand=True)
        self.log_tree.bind("<<TreeviewSelect>>", self._on_log_select)
        self.log_tree.bind("<Double-1>", lambda e: self.open_preview_window())

        # --- controls ---
        btns = ttk.Frame(tab)
        btns.pack(fill="x", pady=(PAD, 0))
        self.follow_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(btns, text="Follow newest", variable=self.follow_var).pack(side="left")
        ttk.Button(btns, text="Clear", command=self.clear_log).pack(side="right")
        self.save_btn = ttk.Button(btns, text="Save image…", command=self.save_preview_image,
                                   state="disabled")
        self.save_btn.pack(side="right", padx=4)
        self.view_btn = ttk.Button(btns, text="View larger ⤢", command=self.open_preview_window,
                                   state="disabled")
        self.view_btn.pack(side="right", padx=4)

        # --- the picture for the selected row ---
        self.preview_lbl = tk.Label(
            tab,
            text="No detection selected yet.\nWhen a click is triggered it appears in the log above.",
            bg="#20232a", fg="#aaa", height=8, relief="groove", bd=1)
        self.preview_lbl.pack(fill="x", pady=(PAD, 2))
        self.preview_caption = ttk.Label(tab, text="Red highlights = the pixels that changed.",
                                         foreground="#666", wraplength=440)
        self.preview_caption.pack(anchor="w")

    def _slider(self, parent, row, label, var, lo, hi, hint="", fmt="{:.0f}"):
        ttk = self.ttk
        ttk.Label(parent, text=label + ":").grid(row=row, column=0, sticky="w", pady=(4, 0))
        value_lbl = ttk.Label(parent, text="", style="Value.TLabel", width=6)
        value_lbl.grid(row=row, column=2, sticky="e", pady=(4, 0))

        def _changed(_evt=None):
            value_lbl.configure(text=fmt.format(var.get()))
            self._on_setting_change()

        ttk.Scale(parent, from_=lo, to=hi, variable=var, command=lambda _e: _changed()).grid(
            row=row, column=1, sticky="ew", padx=PAD, pady=(4, 0))
        if hint:
            ttk.Label(parent, text=hint, foreground="#777", font=("Sans", 8)).grid(
                row=row + 1, column=1, columnspan=2, sticky="w")
        setattr(self, f"_vallbl_{label}", value_lbl)

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
            lbl = getattr(self, f"_vallbl_{label}", None)
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
        self.region_lbl.configure(text=str(c.region) if c.region else "(none)")
        if c.click_x is not None and c.click_y is not None:
            self.point_lbl.configure(text=f"({c.click_x}, {c.click_y})")
        else:
            self.point_lbl.configure(text="(none)")

    def _refresh_hotkey_labels(self) -> None:
        self.toggle_hotkey_lbl.configure(text=pretty(self.config.hotkey_toggle))
        self.quit_hotkey_lbl.configure(text=pretty(self.config.hotkey_quit))

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
                self._set_status("Select a region and a click point first.", "#c0392b")
                return
            self.monitor.start()
        self._update_running_ui()

    def _update_running_ui(self) -> None:
        running = self.monitor.is_running
        self.start_btn.configure(text="■  Stop" if running else "▶  Start")
        state = "disabled" if running else "normal"
        self.region_btn.configure(state=state)
        self.point_btn.configure(state=state)

    # -------------------------------------------------------------- events
    def _poll(self) -> None:
        try:
            while True:
                action = self._actions.get_nowait()
                if action == "toggle":
                    self.toggle()
                elif action == "quit":
                    self.on_close()
                    return
        except queue.Empty:
            pass

        try:
            while True:
                self._handle_event(self._events.get_nowait())
        except queue.Empty:
            pass
        self.root.after(100, self._poll)

    def _handle_event(self, ev: MonitorEvent) -> None:
        if ev.kind == "started":
            self._set_status("● Watching…", "#207a3f")
            self._update_running_ui()
        elif ev.kind == "stopped":
            self._set_status("Stopped.", "#555")
            self._update_running_ui()
        elif ev.kind == "clicked":
            self._set_status(ev.message, "#207a3f")
            self._flash()
            # Records the detection and, when following, selects it — which
            # renders its image via the tree's selection handler.
            self._log_detection(ev)
        elif ev.kind == "limit":
            self._set_status(ev.message, "#b8860b")
        elif ev.kind == "error":
            self._set_status(ev.message, "#c0392b")
            self._update_running_ui()

        if ev.kind in ("tick", "clicked", "started"):
            self.activity["value"] = min(100.0, ev.score * 100.0 * 3)
            self.stats_lbl.configure(
                text=f"clicks: {ev.clicks}   ·   uptime: {_fmt_uptime(ev.elapsed)}"
                     f"   ·   change: {ev.score * 100:.2f}%"
            )

    def _log_detection(self, ev: MonitorEvent) -> None:
        """Record a detection and add a selectable row for it."""
        self._history.set_capacity(self.config.log_history)
        det = self._history.add(index=ev.clicks, score=ev.score, preview=ev.preview)

        self.log_tree.insert(
            "", "end", iid=str(det.index),
            values=(det.index, det.time_str, det.score_str, "🖼" if det.has_image else "—"),
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
                image="", text="No image was captured for this detection.\n"
                                "Enable “Explain detections” to capture them.")
            self.preview_caption.configure(
                text=f"Click #{det.index} at {det.time_str} — {det.score_str} of the region changed.")
            self.view_btn.configure(state="disabled")
            self.save_btn.configure(state="disabled")
            return
        try:
            photo = self.tk.PhotoImage(data=det.preview)
        except Exception:  # noqa: BLE001 - never let a bad image break the UI
            return
        self._preview_photo = photo  # hold a reference against GC
        self.preview_lbl.configure(image=photo, text="")
        self.preview_caption.configure(
            text=f"Click #{det.index} at {det.time_str} — red marks the {det.score_str} "
                 f"of the region that changed and triggered this click.")
        self.view_btn.configure(state="normal")
        self.save_btn.configure(state="normal")

    def open_preview_window(self) -> None:
        """Open the selected detection's image in a larger, magnified window."""
        det = self._selected
        if det is None or not det.has_image:
            return
        tk = self.tk
        win = tk.Toplevel(self.root)
        win.title(f"Why click #{det.index} fired — {det.time_str}")
        try:
            photo = tk.PhotoImage(data=det.preview)
            # Nearest-neighbour magnify so small regions are actually readable.
            if photo.width() < 500:
                photo = photo.zoom(2)
        except Exception:  # noqa: BLE001
            win.destroy()
            return
        win._photo = photo  # keep a reference on the window itself
        tk.Label(win, image=photo, bd=0).pack(padx=10, pady=(10, 4))
        self.ttk.Label(
            win,
            text=f"{det.score_str} of the watched region changed at {det.time_str}. "
                 f"Red = the pixels responsible.",
            wraplength=max(360, photo.width()), foreground="#444",
        ).pack(padx=10, pady=(0, 8))
        self.ttk.Button(win, text="Close", command=win.destroy).pack(pady=(0, 10))
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
            initialfile=f"screenwatch-click-{det.index}.png",
            filetypes=[("PNG image", "*.png")],
        )
        if not path:
            return
        try:
            with open(path, "wb") as fh:
                fh.write(base64.b64decode(det.preview))
            self._set_status(f"Saved image to {path}", "#207a3f")
        except (OSError, ValueError) as exc:
            messagebox.showerror("Save failed", str(exc))

    def clear_log(self) -> None:
        self._history.clear()
        self._selected = None
        self._preview_photo = None
        for iid in self.log_tree.get_children():
            self.log_tree.delete(iid)
        self.preview_lbl.configure(image="", text="Log cleared.")
        self.preview_caption.configure(text="Red highlights = the pixels that changed.")
        self.view_btn.configure(state="disabled")
        self.save_btn.configure(state="disabled")

    def _set_status(self, text: str, color: str = "#333") -> None:
        self.status_lbl.configure(text=text, foreground=color)

    def _flash(self) -> None:
        self.activity["value"] = 100
        self.root.after(120, lambda: self.activity.configure(value=0))

    # -------------------------------------------------------------- hotkeys
    def _apply_hotkeys(self) -> None:
        self.hotkeys.stop()
        self.config.hotkeys_enabled = bool(self.hotkey_enabled_var.get())
        if not self.config.hotkeys_enabled:
            self._set_hotkey_status("Global hotkeys are disabled.", "#777")
            return
        t, q = self.config.hotkey_toggle, self.config.hotkey_quit
        if not (is_valid(t) and is_valid(q)):
            self._set_hotkey_status("Invalid hotkey combination.", "#c0392b")
            return
        ok = self.hotkeys.start({
            t: lambda: self._actions.put("toggle"),
            q: lambda: self._actions.put("quit"),
        })
        if ok:
            self._set_hotkey_status(
                f"Active — {pretty(t)} start/stop · {pretty(q)} quit", "#207a3f")
        else:
            self._set_hotkey_status(
                f"Unavailable (Wayland or blocked). Use the Start button. {self.hotkeys.error or ''}",
                "#c0392b")

    def _set_hotkey_status(self, text: str, color: str) -> None:
        self.hotkey_status_lbl.configure(text=text, foreground=color)
        # Mirror a compact version on the always-visible control bar.
        self.hotkey_lbl.configure(text=text)

    def _capture_hotkey(self, which: str) -> None:
        tk = self.tk
        dlg = tk.Toplevel(self.root)
        dlg.title("Set hotkey")
        dlg.transient(self.root)
        dlg.resizable(False, False)
        tk.Label(dlg, text="Press the key combination you want.\n\n(Esc to cancel)",
                 padx=28, pady=24, font=("Sans", 11)).pack()
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
            self._set_status(f"Settings saved to {path}", "#207a3f")
        except OSError as exc:
            self._set_status(f"Could not save settings: {exc}", "#c0392b")

    def reload_settings(self) -> None:
        self.monitor.stop()
        self.config = Config.load()
        self.monitor = Monitor(self.config, on_event=self._events.put)
        self._history.set_capacity(self.config.log_history)
        self._sync_widgets_from_config()
        self._apply_hotkeys()
        self._update_running_ui()
        self._set_status("Settings reloaded.", "#207a3f")

    def show_about(self) -> None:
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
    import tkinter as tk

    root = tk.Tk()
    ScreenWatchApp(root, config)
    root.mainloop()
