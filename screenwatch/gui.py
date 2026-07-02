"""The ScreenWatch desktop GUI (Tkinter/ttk).

Kept in one file for easy distribution.  Tkinter is imported at call time inside
:func:`run` so the module can be imported for tooling/tests without a display.
"""

from __future__ import annotations

import queue
from typing import Optional

from . import __app_name__, __version__
from .config import CLICK_BUTTONS, CLICK_TYPES, Config
from .hotkeys import HotkeyManager
from .monitor import Monitor, MonitorEvent

# Toggle / quit hotkeys (pynput syntax).
HOTKEY_TOGGLE = "<ctrl>+<shift>+s"
HOTKEY_QUIT = "<ctrl>+<shift>+q"

PAD = 8


def _fmt_uptime(seconds: float) -> str:
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h {m:02d}m {s:02d}s"
    if m:
        return f"{m}m {s:02d}s"
    return f"{s}s"


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

        root.title(f"{__app_name__} — auto-click on change")
        root.minsize(460, 640)
        root.protocol("WM_DELETE_WINDOW", self.on_close)

        self._build_style()
        self._build_menu()
        self._build_widgets()
        self._sync_widgets_from_config()

        self._start_hotkeys()
        self.root.after(100, self._poll)

    # ------------------------------------------------------------------ UI
    def _build_style(self) -> None:
        style = self.ttk.Style()
        for theme in ("clam", "alt", "default"):
            if theme in style.theme_names():
                style.theme_use(theme)
                break
        style.configure("Header.TLabel", font=("Sans", 15, "bold"))
        style.configure("Section.TLabelframe.Label", font=("Sans", 10, "bold"))
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

        outer = ttk.Frame(root, padding=PAD)
        outer.pack(fill="both", expand=True)

        ttk.Label(outer, text="ScreenWatch", style="Header.TLabel").pack(anchor="w")
        ttk.Label(
            outer,
            text="Watches a screen area and clicks the instant it changes.",
            foreground="#555",
        ).pack(anchor="w", pady=(0, PAD))

        # --- Targets -----------------------------------------------------
        targets = ttk.LabelFrame(outer, text="1 · Targets", style="Section.TLabelframe", padding=PAD)
        targets.pack(fill="x", pady=(0, PAD))
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

        # --- Detection ---------------------------------------------------
        detect = ttk.LabelFrame(outer, text="2 · Detection", style="Section.TLabelframe", padding=PAD)
        detect.pack(fill="x", pady=(0, PAD))
        detect.columnconfigure(1, weight=1)

        self.sensitivity_var = tk.IntVar()
        self._slider(detect, 0, "Sensitivity", self.sensitivity_var, 1, 100, self._on_setting_change,
                     hint="higher = reacts to smaller changes")

        self.fps_var = tk.DoubleVar()
        self._slider(detect, 2, "Check rate (fps)", self.fps_var, 0.5, 30, self._on_setting_change,
                     hint="lower = less CPU", fmt="{:.1f}")

        self.threshold_var = tk.IntVar()
        self._slider(detect, 4, "Noise filter", self.threshold_var, 0, 100, self._on_setting_change,
                     hint="ignore per-pixel changes below this")

        ttk.Label(detect, text="Compare against:").grid(row=6, column=0, sticky="w", pady=(6, 0))
        self.compare_var = tk.StringVar()
        cmp_frame = ttk.Frame(detect)
        cmp_frame.grid(row=6, column=1, columnspan=2, sticky="w", pady=(6, 0))
        ttk.Radiobutton(cmp_frame, text="Previous frame (any change)", value="previous",
                        variable=self.compare_var, command=self._on_setting_change).pack(anchor="w")
        ttk.Radiobutton(cmp_frame, text="Start frame (deviation from state)", value="baseline",
                        variable=self.compare_var, command=self._on_setting_change).pack(anchor="w")

        # --- Click behaviour --------------------------------------------
        behave = ttk.LabelFrame(outer, text="3 · Click behaviour", style="Section.TLabelframe", padding=PAD)
        behave.pack(fill="x", pady=(0, PAD))
        for c in (1, 3):
            behave.columnconfigure(c, weight=1)

        ttk.Label(behave, text="Button:").grid(row=0, column=0, sticky="w")
        self.button_var = tk.StringVar()
        ttk.Combobox(behave, textvariable=self.button_var, values=list(CLICK_BUTTONS),
                     state="readonly", width=8).grid(row=0, column=1, sticky="w", padx=(4, PAD))

        ttk.Label(behave, text="Type:").grid(row=0, column=2, sticky="w")
        self.type_var = tk.StringVar()
        ttk.Combobox(behave, textvariable=self.type_var, values=list(CLICK_TYPES),
                     state="readonly", width=8).grid(row=0, column=3, sticky="w", padx=4)

        ttk.Label(behave, text="Cooldown (s):").grid(row=1, column=0, sticky="w", pady=(6, 0))
        self.cooldown_var = tk.DoubleVar()
        ttk.Spinbox(behave, from_=0, to=3600, increment=0.5, width=8,
                    textvariable=self.cooldown_var, command=self._on_setting_change
                    ).grid(row=1, column=1, sticky="w", padx=(4, PAD), pady=(6, 0))

        ttk.Label(behave, text="Delay (s):").grid(row=1, column=2, sticky="w", pady=(6, 0))
        self.delay_var = tk.DoubleVar()
        ttk.Spinbox(behave, from_=0, to=60, increment=0.1, width=8,
                    textvariable=self.delay_var, command=self._on_setting_change
                    ).grid(row=1, column=3, sticky="w", padx=4, pady=(6, 0))

        ttk.Label(behave, text="Max clicks:").grid(row=2, column=0, sticky="w", pady=(6, 0))
        self.maxclicks_var = tk.IntVar()
        ttk.Spinbox(behave, from_=0, to=1_000_000, increment=1, width=8,
                    textvariable=self.maxclicks_var, command=self._on_setting_change
                    ).grid(row=2, column=1, sticky="w", padx=(4, PAD), pady=(6, 0))
        ttk.Label(behave, text="(0 = unlimited)", foreground="#777").grid(
            row=2, column=2, columnspan=2, sticky="w", pady=(6, 0))

        self.sound_var = tk.BooleanVar()
        ttk.Checkbutton(behave, text="Beep on each click", variable=self.sound_var,
                        command=self._on_setting_change).grid(
            row=3, column=0, columnspan=4, sticky="w", pady=(6, 0))

        # --- Control -----------------------------------------------------
        control = ttk.Frame(outer)
        control.pack(fill="x", pady=(4, 0))
        self.start_btn = ttk.Button(control, text="▶  Start", style="Start.TButton", command=self.toggle)
        self.start_btn.pack(fill="x")

        self.activity = ttk.Progressbar(outer, maximum=100, mode="determinate")
        self.activity.pack(fill="x", pady=(PAD, 2))

        self.status_lbl = ttk.Label(outer, text="Idle — select targets to begin.", style="Status.TLabel")
        self.status_lbl.pack(anchor="w")
        self.stats_lbl = ttk.Label(outer, text="", foreground="#555")
        self.stats_lbl.pack(anchor="w")

        self.hotkey_lbl = ttk.Label(
            outer,
            text="Global hotkeys: Ctrl+Shift+S start/stop · Ctrl+Shift+Q quit",
            foreground="#777",
            font=("Sans", 9),
        )
        self.hotkey_lbl.pack(anchor="w", pady=(PAD, 0))

    def _slider(self, parent, row, label, var, lo, hi, cmd, hint="", fmt="{:.0f}"):
        ttk = self.ttk
        ttk.Label(parent, text=label + ":").grid(row=row, column=0, sticky="w", pady=(4, 0))
        value_lbl = ttk.Label(parent, text="", style="Value.TLabel", width=6)
        value_lbl.grid(row=row, column=2, sticky="e", pady=(4, 0))

        def _changed(_evt=None):
            value_lbl.configure(text=fmt.format(var.get()))
            cmd()

        scale = ttk.Scale(parent, from_=lo, to=hi, variable=var, command=lambda _e: _changed())
        scale.grid(row=row, column=1, sticky="ew", padx=PAD, pady=(4, 0))
        if hint:
            ttk.Label(parent, text=hint, foreground="#777", font=("Sans", 8)).grid(
                row=row + 1, column=1, columnspan=2, sticky="w")
        # Remember the value label so initial sync can populate it.
        setattr(self, f"_vallbl_{label}", value_lbl)
        setattr(self, f"_valfmt_{label}", fmt)

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
        self._refresh_target_labels()
        # Populate slider value labels.
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
        # Drain hotkey actions first (they may start/stop the monitor).
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
        elif ev.kind == "limit":
            self._set_status(ev.message, "#b8860b")
        elif ev.kind == "error":
            self._set_status(ev.message, "#c0392b")
            self._update_running_ui()

        # Update the activity meter + stats on any event that carries data.
        if ev.kind in ("tick", "clicked", "started"):
            self.activity["value"] = min(100.0, ev.score * 100.0 * 3)  # scale for visibility
            self.stats_lbl.configure(
                text=f"clicks: {ev.clicks}   ·   uptime: {_fmt_uptime(ev.elapsed)}"
                     f"   ·   change: {ev.score * 100:.2f}%"
            )

    def _set_status(self, text: str, color: str = "#333") -> None:
        self.status_lbl.configure(text=text, foreground=color)

    def _flash(self) -> None:
        self.activity["value"] = 100
        self.root.after(120, lambda: self.activity.configure(value=0))

    # -------------------------------------------------------------- hotkeys
    def _start_hotkeys(self) -> None:
        ok = self.hotkeys.start({
            HOTKEY_TOGGLE: lambda: self._actions.put("toggle"),
            HOTKEY_QUIT: lambda: self._actions.put("quit"),
        })
        if not ok:
            self.hotkey_lbl.configure(text="Global hotkeys unavailable (Wayland?) — use the buttons.")

    # ------------------------------------------------------------- menu ops
    def save_settings(self) -> None:
        self._pull_config_from_widgets()
        try:
            path = self.config.save()
            self._set_status(f"Settings saved to {path}", "#207a3f")
        except OSError as exc:
            self._set_status(f"Could not save settings: {exc}", "#c0392b")

    def reload_settings(self) -> None:
        self.monitor.stop()  # never leave an orphaned worker on the old config
        self.config = Config.load()
        self.monitor = Monitor(self.config, on_event=self._events.put)
        self._sync_widgets_from_config()
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
            "  deviation from how the area looked when you pressed Start.\n\n"
            "Hotkeys: Ctrl+Shift+S start/stop · Ctrl+Shift+Q quit",
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
