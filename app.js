(function () {
  "use strict";

  // Keep the platform download menus mutually exclusive so they never
  // overlap each other when opened side by side.
  var dlOptions = document.querySelectorAll(".dl-option");
  dlOptions.forEach(function (details) {
    details.addEventListener("toggle", function () {
      if (!details.open) return;
      dlOptions.forEach(function (other) {
        if (other !== details) other.open = false;
      });
    });
  });

  // Hero demo video: play/pause, restart, and skip-forward controls.
  // The video keeps its native `loop` attribute so it repeats on its own.
  var video = document.getElementById("hero-video");
  var toggleBtn = document.getElementById("hero-video-toggle");
  var backBtn = document.getElementById("hero-video-back");
  var forwardBtn = document.getElementById("hero-video-forward");
  if (video && toggleBtn && backBtn && forwardBtn) {
    var iconPause = toggleBtn.querySelector(".icon-pause");
    var iconPlay = toggleBtn.querySelector(".icon-play");

    var syncToggleState = function () {
      var playing = !video.paused && !video.ended;
      iconPause.hidden = !playing;
      iconPlay.hidden = playing;
      toggleBtn.setAttribute("aria-pressed", String(playing));
      toggleBtn.setAttribute("aria-label", playing ? "Pause demo" : "Play demo");
    };

    toggleBtn.addEventListener("click", function () {
      if (video.paused || video.ended) {
        video.play();
      } else {
        video.pause();
      }
    });
    video.addEventListener("play", syncToggleState);
    video.addEventListener("pause", syncToggleState);
    syncToggleState();

    backBtn.addEventListener("click", function () {
      video.currentTime = 0;
      video.play();
    });

    forwardBtn.addEventListener("click", function () {
      if (!video.duration) return;
      video.currentTime = Math.min(video.currentTime + 5, video.duration);
    });
  }
})();
