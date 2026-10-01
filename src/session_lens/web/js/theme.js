// Loaded synchronously in <head> so the saved theme applies before first paint.
(function () {
  try {
    const t = localStorage.getItem("session-lens.theme");
    if (t === "light" || t === "dark") document.documentElement.dataset.theme = t;
  } catch {
    /* follow the system theme */
  }
})();
