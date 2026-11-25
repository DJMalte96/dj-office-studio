/* Theme vor dem ersten Rendern setzen – im <head> geladen, damit nichts aufblitzt (seit 1.13.1 als Datei: die CSP erlaubt keinen Inline-Code). */
(function () {
  var t = null;
  try { t = localStorage.getItem("theme"); } catch (e) {}
  if (t !== "light" && t !== "dark") t = matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  document.documentElement.setAttribute("data-theme", t);
})();
