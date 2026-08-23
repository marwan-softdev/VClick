(function () {
  "use strict";

  var screenEl = document.getElementById("mockScreen");
  var decoyEl = document.getElementById("mockDecoy");
  var regionEl = document.getElementById("mockRegion");
  var pointEl = document.getElementById("mockPoint");
  var sensitivityEl = document.getElementById("mockSensitivity");
  var sensitivityLabelEl = document.getElementById("mockSensitivityLabel");
  var startBtn = document.getElementById("mockStart");
  var stopBtn = document.getElementById("mockStop");
  var logEl = document.getElementById("mockLog");

  if (!screenEl) return; // section not on this page

  var SENSITIVITY_LABELS = ["Low", "Medium", "High"];

  function clamp(value, min, max) {
    return Math.min(Math.max(value, min), max);
  }

  function makeDraggable(el, onMove) {
    var dragging = false;
    var offsetX = 0;
    var offsetY = 0;

    el.addEventListener("pointerdown", function (e) {
      dragging = true;
      var elRect = el.getBoundingClientRect();
      offsetX = e.clientX - elRect.left;
      offsetY = e.clientY - elRect.top;
      el.setPointerCapture(e.pointerId);
      e.preventDefault();
    });

    el.addEventListener("pointermove", function (e) {
      if (!dragging) return;
      var screenRect = screenEl.getBoundingClientRect();
      var elRect = el.getBoundingClientRect();
      var x = e.clientX - screenRect.left - offsetX;
      var y = e.clientY - screenRect.top - offsetY;
      onMove(
        clamp(x, 0, screenRect.width - elRect.width),
        clamp(y, 0, screenRect.height - elRect.height)
      );
    });

    function stop(e) {
      if (dragging) {
        dragging = false;
        try { el.releasePointerCapture(e.pointerId); } catch (err) {}
      }
    }
    el.addEventListener("pointerup", stop);
    el.addEventListener("pointercancel", stop);
  }

  makeDraggable(regionEl, function (x, y) {
    regionEl.style.left = x + "px";
    regionEl.style.top = y + "px";
  });

  makeDraggable(pointEl, function (x, y) {
    var w = pointEl.offsetWidth;
    var h = pointEl.offsetHeight;
    pointEl.style.left = x + w / 2 + "px";
    pointEl.style.top = y + h / 2 + "px";
  });

  sensitivityEl.addEventListener("input", function () {
    sensitivityLabelEl.textContent = SENSITIVITY_LABELS[Number(sensitivityEl.value)] || "Medium";
  });

  function addLogLine(text) {
    var li = document.createElement("li");
    var time = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
    li.textContent = "[" + time + "] " + text;
    logEl.insertBefore(li, logEl.firstChild);
    while (logEl.children.length > 6) {
      logEl.removeChild(logEl.lastChild);
    }
  }

  var runTimeoutId = null;

  function runOneCycle() {
    addLogLine("Watching region …");

    runTimeoutId = setTimeout(function () {
      decoyEl.classList.add("changed");

      var x = Math.round(pointEl.offsetLeft);
      var y = Math.round(pointEl.offsetTop);
      pointEl.classList.remove("pulse");
      // force reflow so the animation can retrigger
      void pointEl.offsetWidth;
      pointEl.classList.add("pulse");

      addLogLine("Detected change → clicked at (" + x + ", " + y + ")");

      setTimeout(function () {
        decoyEl.classList.remove("changed");
        setIdle();
      }, 900);
    }, 1400 + Math.random() * 900);
  }

  function setRunning() {
    startBtn.disabled = true;
    stopBtn.disabled = false;
    runOneCycle();
  }

  function setIdle() {
    startBtn.disabled = false;
    stopBtn.disabled = true;
  }

  startBtn.addEventListener("click", setRunning);

  stopBtn.addEventListener("click", function () {
    if (runTimeoutId) {
      clearTimeout(runTimeoutId);
      runTimeoutId = null;
    }
    decoyEl.classList.remove("changed");
    addLogLine("Stopped.");
    setIdle();
  });
})();
