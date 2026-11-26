/* DJ Office Studio – seit 1.15: Menüleiste unten auf dem Handy (schmale Fenster). Oben bleiben Logo, Suche und ⚙;
   die Leiste öffnet je Bereich ein Blatt mit den Unterpunkten. Am Computer und Tablet bleibt das Menü oben. */
"use strict";

const HANDY_ICON = {
  start: `<path d="M3 11 12 4l9 7"/><path d="M5 10v10h5v-6h4v6h5V10"/>`,
  rechnungen: `<path d="M6 3h9l4 4v14H6z"/><path d="M14 3v5h5M9 13h7M9 17h5"/>`,
  angebote: `<path d="M4 20h4L19 9l-4-4L4 16v4z"/><path d="m13.5 6.5 4 4"/>`,
  finanzen: `<path d="M4 20V10M10 20V4M16 20v-8M22 20H2"/>`,
  mehr: `<circle cx="5" cy="12" r="1.6"/><circle cx="12" cy="12" r="1.6"/><circle cx="19" cy="12" r="1.6"/>`,
};
const HANDY_GRUPPEN = {
  rechnungen: [["Rechnungen", [["＋", "Neue Rechnung", "neu"], ["☰", "Rechnungen", "liste"]]]],
  angebote: [["Angebote", [["✎", "Neues Angebot", "angebot-neu"], ["❐", "Angebote", "angebote"]]]],
  finanzen: [["Finanzen", [["◔", "Übersicht", "finanzen"], ["↧", "Ausgaben", "ausgaben"], ["➜", "Fahrten", "fahrten"],
    ["▣", "Anschaffungen", "anschaffungen"], ["§", "EÜR & Export", "euer"]]]],
  mehr: [["Dokumente", [["＋", "Neuer Vertrag", "vertrag-neu"], ["✍", "Verträge", "vertraege"], ["§", "Vertragsvorlage", "vertragsvorlage"]]],
    ["Stammdaten", [["◉", "Kunden", "kunden"], ["♪", "Rechnungsposten", "textbausteine"], ["€", "Zahlungsbedingungen", "zahlungsbedingungen"]]],
    ["App", [["◐", "Hell / Dunkel", ":theme"]]]],
};
const HANDY_ZU = { start: "start", neu: "rechnungen", liste: "rechnungen", "angebot-neu": "angebote", angebote: "angebote",
  finanzen: "finanzen", ausgaben: "finanzen", fahrten: "finanzen", anschaffungen: "finanzen", euer: "finanzen" };

document.body.insertAdjacentHTML("beforeend", `<div class="unten-schleier"></div><div class="unten-blatt" role="menu"></div>
  <div class="unten-leiste" role="navigation" aria-label="Menü">${[["start", "Start"], ["rechnungen", "Rechnungen"], ["angebote", "Angebote"],
    ["finanzen", "Finanzen"], ["mehr", "Mehr"]].map(([k, t]) => `<button type="button" data-unten="${k}"><svg viewBox="0 0 24 24" fill="none"
    stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${HANDY_ICON[k]}</svg><span>${t}</span></button>`).join("")}</div>`);

const handyBlatt = $(".unten-blatt"), handySchleier = $(".unten-schleier");
const handyTab = () => ($(".tab.active")?.id || "").replace("tab-", "");

function handyMarkieren() {
  const t = handyTab();
  const g = HANDY_ZU[t === "neu" && state.modus === "angebot" ? "angebot-neu" : t] || (t && t !== "einstellungen" ? "mehr" : t ? "" : "start");
  $$(".unten-leiste button").forEach(b => b.classList.toggle("aktiv", b.dataset.unten === g));
}
function handyZu() {
  handyBlatt.classList.remove("offen");
  handySchleier.classList.remove("offen");
  handyMarkieren();
}
$(".unten-leiste").addEventListener("click", e => {
  const b = e.target.closest("[data-unten]");
  if (!b) return;
  const g = b.dataset.unten;
  if (g === "start") { handyZu(); return showTab("start"); }
  if (handyBlatt.classList.contains("offen") && handyBlatt.dataset.gruppe === g) return handyZu();
  handyBlatt.dataset.gruppe = g;
  const t = handyTab();
  handyBlatt.innerHTML = HANDY_GRUPPEN[g].map(([titel, liste]) => `<h4>${titel}</h4>${liste.map(([s, n, tab]) =>
    `<button type="button" data-ziel="${tab}"${tab === t ? ' class="aktiv"' : ""}><span class="sym">${s}</span>${n}</button>`).join("")}`).join("");
  handyBlatt.classList.add("offen");
  handySchleier.classList.add("offen");
  $$(".unten-leiste button").forEach(x => x.classList.toggle("aktiv", x === b));
});
handySchleier.addEventListener("click", handyZu);
document.addEventListener("keydown", e => { if (e.key === "Escape" && handyBlatt.classList.contains("offen")) handyZu(); });
handyBlatt.addEventListener("click", e => {
  const b = e.target.closest("[data-ziel]");
  if (!b) return;
  handyZu();
  if (b.dataset.ziel === ":theme") return $("#theme-toggle").click();
  $(`nav [data-tab="${b.dataset.ziel}"]`).click();   // wie ein Klick im Menü oben (neue Rechnung, neuer Vertrag …)
  setTimeout(handyMarkieren, 50);
});
handyMarkieren();
