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
})();
