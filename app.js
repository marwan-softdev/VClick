(function () {
  "use strict";

  var appEl = document.getElementById("mockApp");
  if (!appEl) return; // section not on this page

  /* ---------- tabs ---------- */
  var tabs = appEl.querySelectorAll(".mock-tab");
  var panes = appEl.querySelectorAll(".mock-pane");
  tabs.forEach(function (tab) {
    tab.addEventListener("click", function () {
      tabs.forEach(function (t) { t.classList.toggle("active", t === tab); });
      panes.forEach(function (p) {
        p.classList.toggle("active", p.dataset.pane === tab.dataset.pane);
      });
    });
  });

  /* ---------- region / point selection on the preview ---------- */
  var preview = document.getElementById("mockPreview");
  var regionBox = document.getElementById("regionBox");
  var pointDot = document.getElementById("pointDot");
  var regionValue = document.getElementById("regionValue");
  var pointValue = document.getElementById("pointValue");
  var selectHint = document.getElementById("selectHint");
  var selectRegionBtn = document.getElementById("selectRegionBtn");
  var selectPointBtn = document.getElementById("selectPointBtn");

  var selectMode = null; // null | "region" | "point"

  function armSelection(mode, hintText) {
    selectMode = mode;
    selectHint.textContent = hintText;
    selectHint.hidden = false;
    preview.style.outline = "2px solid var(--mock-accent)";
  }

  function disarmSelection() {
    selectMode = null;
    selectHint.hidden = true;
    preview.style.outline = "none";
  }

  selectRegionBtn.addEventListener("click", function () {
    armSelection("region", "Drag on the preview below to draw the region.");
  });
  selectPointBtn.addEventListener("click", function () {
    armSelection("point", "Click on the preview below to place the point.");
  });

  var dragStart = null;

  preview.addEventListener("pointerdown", function (e) {
    if (selectMode !== "region") return;
    var rect = preview.getBoundingClientRect();
    dragStart = { x: e.clientX - rect.left, y: e.clientY - rect.top };
    regionBox.hidden = false;
    regionBox.style.left = dragStart.x + "px";
    regionBox.style.top = dragStart.y + "px";
    regionBox.style.width = "0px";
    regionBox.style.height = "0px";
    preview.setPointerCapture(e.pointerId);
  });

  preview.addEventListener("pointermove", function (e) {
    if (selectMode !== "region" || !dragStart) return;
    var rect = preview.getBoundingClientRect();
    var x = e.clientX - rect.left;
    var y = e.clientY - rect.top;
    var left = Math.min(x, dragStart.x);
    var top = Math.min(y, dragStart.y);
    var w = Math.abs(x - dragStart.x);
    var h = Math.abs(y - dragStart.y);
    regionBox.style.left = left + "px";
    regionBox.style.top = top + "px";
    regionBox.style.width = w + "px";
    regionBox.style.height = h + "px";
  });

  preview.addEventListener("pointerup", function () {
    if (selectMode === "region" && dragStart) {
      var w = Math.round(parseFloat(regionBox.style.width));
      var h = Math.round(parseFloat(regionBox.style.height));
      if (w < 6 || h < 6) {
        w = 110; h = 52;
        regionBox.style.width = w + "px";
        regionBox.style.height = h + "px";
      }
      regionValue.textContent = w + "×" + h + " px";
      dragStart = null;
      disarmSelection();
    }
  });

  preview.addEventListener("click", function (e) {
    if (selectMode !== "point") return;
    var rect = preview.getBoundingClientRect();
    var x = Math.round(e.clientX - rect.left);
    var y = Math.round(e.clientY - rect.top);
    pointDot.hidden = false;
    pointDot.style.left = x + "px";
    pointDot.style.top = y + "px";
    pointValue.textContent = "(" + x + ", " + y + ")";
    disarmSelection();
  });

  /* ---------- sliders paired with numeric inputs ---------- */
  function pairSliderNumber(sliderId, numberId) {
    var slider = document.getElementById(sliderId);
    var number = document.getElementById(numberId);
    if (!slider || !number) return;
    slider.addEventListener("input", function () { number.value = slider.value; });
    number.addEventListener("input", function () { slider.value = number.value; });
  }
  pairSliderNumber("sensitivitySlider", "sensitivityNum");
  pairSliderNumber("fpsSlider", "fpsNum");
  pairSliderNumber("noiseSlider", "noiseNum");

  /* ---------- steppers ---------- */
  appEl.querySelectorAll(".mock-stepper").forEach(function (stepper) {
    var min = parseFloat(stepper.dataset.min);
    var max = parseFloat(stepper.dataset.max);
    var step = parseFloat(stepper.dataset.step);
    var value = parseFloat(stepper.dataset.value);
    var display = stepper.querySelector(".mock-stepper-value");
    var decimals = (String(step).split(".")[1] || "").length;

    function render() { display.textContent = value.toFixed(decimals); }

    stepper.querySelectorAll("button").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var dir = parseFloat(btn.dataset.dir);
        value = Math.min(max, Math.max(min, value + dir * step));
        render();
      });
    });
    render();
  });

  /* ---------- hotkey capture ---------- */
  var captureOverlay = document.getElementById("mockHotkeyCapture");
  var captureCancel = document.getElementById("mockHotkeyCancel");
  var captureTarget = null;

  function comboFromEvent(e) {
    var parts = [];
    if (e.ctrlKey) parts.push("Ctrl");
    if (e.altKey) parts.push("Alt");
    if (e.metaKey) parts.push("Cmd");
    if (e.shiftKey) parts.push("Shift");
    var key = e.key;
    if (["Control", "Alt", "Meta", "Shift"].indexOf(key) === -1) {
      parts.push(key.length === 1 ? key.toUpperCase() : key);
    }
    return parts;
  }

  appEl.querySelectorAll("[data-hotkey]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      captureTarget = btn.dataset.hotkey === "startstop"
        ? document.getElementById("hkStartStop")
        : document.getElementById("hkQuit");
      captureOverlay.hidden = false;
    });
  });

  captureCancel.addEventListener("click", function () {
    captureOverlay.hidden = true;
    captureTarget = null;
  });

  document.addEventListener("keydown", function (e) {
    if (captureOverlay.hidden) return;
    e.preventDefault();
    if (e.key === "Escape") {
      captureOverlay.hidden = true;
      captureTarget = null;
      return;
    }
    if (["Control", "Alt", "Meta", "Shift"].indexOf(e.key) !== -1) return; // wait for a real key
    var parts = comboFromEvent(e);
    if (captureTarget) captureTarget.textContent = parts.join("+");
    captureOverlay.hidden = true;
    captureTarget = null;
  });

  /* ---------- key tester (Hotkeys tab) ---------- */
  var keyTesterValue = document.getElementById("keyTesterValue");
  var hotkeysPane = appEl.querySelector('.mock-pane[data-pane="hotkeys"]');
  document.addEventListener("keydown", function (e) {
    if (!captureOverlay.hidden) return;
    if (!hotkeysPane.classList.contains("active")) return;
    var parts = comboFromEvent(e);
    if (!parts.length) return;
    keyTesterValue.textContent = parts.join("+");
  });

  /* ---------- why / log table ---------- */
  var logRows = appEl.querySelectorAll(".mock-log-table tbody tr");
  var logCaption = document.getElementById("mockLogCaption");
  logRows.forEach(function (row) {
    row.addEventListener("click", function () {
      logRows.forEach(function (r) { r.classList.toggle("active", r === row); });
      var num = row.children[0].textContent;
      logCaption.textContent =
        "Click #" + num + " at " + row.dataset.time +
        " — red marks the " + row.dataset.pct + "% of the region that changed and triggered this click.";
    });
  });

  /* ---------- appearance (theme) ---------- */
  var themeSwitch = document.getElementById("mockThemeSwitch");
  var prefersDark = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)");

  function applyTheme(mode) {
    var dark = mode === "dark" || (mode === "system" && prefersDark && prefersDark.matches);
    appEl.classList.toggle("theme-dark", !!dark);
  }

  themeSwitch.querySelectorAll("button").forEach(function (btn) {
    btn.addEventListener("click", function () {
      themeSwitch.querySelectorAll("button").forEach(function (b) { b.classList.toggle("active", b === btn); });
      applyTheme(btn.dataset.theme);
    });
  });
  applyTheme("system");

  /* ---------- start / stop (cosmetic only — no real detection) ---------- */
  var startBtn = document.getElementById("mockStart");
  var statusDot = document.getElementById("mockStatusDot");
  var statusText = document.getElementById("mockStatusText");
  var running = false;

  startBtn.addEventListener("click", function () {
    running = !running;
    startBtn.textContent = running ? "■ Stop" : "▶ Start";
    startBtn.classList.toggle("running", running);
    statusDot.classList.toggle("watching", running);
    statusText.textContent = running ? "Watching…" : "Idle — select targets to begin.";
  });
})();
