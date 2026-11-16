/* Rechnungen – Frontend. Alle URLs relativ, damit es hinter dem HA-Ingress-Pfad funktioniert. */
"use strict";

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

const state = {
  textbausteine: [],
  zahlungsbedingungen: [],
  kundeId: null,      // ID des gewählten Bestandskunden (null = neuer Kunde)
  editId: null,       // ID der Rechnung bzw. des Angebots, das gerade bearbeitet wird
  rechnungen: [],
  angebote: [],
  modus: "rechnung",  // Editor schreibt eine "rechnung" oder ein "angebot"
  ausAngebot: null,   // Angebot, aus dem die Rechnung im Editor erzeugt wird
  gueltigAuto: true,  // „Gültig bis“ folgt dem Angebotsdatum, bis es von Hand geändert wird
};

// ---------- Hilfsfunktionen ----------

async function api(path, opts = {}) {
  const res = await fetch("api/" + path, {
    headers: opts.body ? { "Content-Type": "application/json" } : {},
    ...opts,
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  if (!res.ok) {
    let msg = `Fehler ${res.status}`;
    try { msg = (await res.json()).error || msg; } catch (_) { /* kein JSON */ }
    throw new Error(msg);
  }
  const type = res.headers.get("Content-Type") || "";
  if (type.includes("application/json")) return res.json();
  if (type.includes("application/pdf")) return res.blob();
  return null;
}

function toast(msg, error = false) {
  const t = $("#toast");
  t.textContent = msg;
  t.classList.toggle("error", error);
  t.classList.remove("hidden");
  clearTimeout(toast._t);
  toast._t = setTimeout(() => t.classList.add("hidden"), error ? 6000 : 3000);
}

function fmtEuro(v) {
  v = Math.round((Number(v) || 0) * 100) / 100;
  const s = Number.isInteger(v)
    ? v.toLocaleString("de-DE") + ",-"
    : v.toLocaleString("de-DE", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return s + " Euro";
}

function fmtDate(iso) {
  if (!iso) return "";
  const [y, m, d] = iso.split("-");
  return `${d}.${m}.${y.slice(2)}`;
}

const today = () => new Date().toISOString().slice(0, 10);

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

/* Öffnet ein PDF in neuem Tab. Das Fenster wird sofort (synchron zum Klick) geöffnet,
   damit Popup-Blocker nicht eingreifen. */
async function openPdf(loader) {
  const win = window.open("", "_blank");
  try {
    const blob = await loader();
    const url = URL.createObjectURL(blob);
    if (win) win.location = url; else window.location = url;
  } catch (e) {
    if (win) win.close();
    toast(e.message, true);
  }
}

// ---------- Tabs ----------

function showTab(name) {
  const navName = name === "neu" && state.modus === "angebot" ? "angebot-neu" : name;
  $$("nav [data-tab]").forEach(b => b.classList.toggle("active", b.dataset.tab === navName));
  // Hauptpunkt (Rechnungen / Angebote / Stammdaten) markieren, wenn ein Unterpunkt aktiv ist
  $$("nav .menu").forEach(m => $(".menu-kopf", m).classList.toggle("active", !!$("[data-tab].active", m)));
  schliesseMenues();
  $$(".tab").forEach(s => s.classList.toggle("active", s.id === "tab-" + name));
  document.body.classList.toggle("auf-start", name === "start");
  if (name === "liste") loadListe();
  if (name === "angebote") loadAngebote();
  if (name === "einstellungen") ladeEinstellungen();
  $("#einstellungen-btn").classList.toggle("active", name === "einstellungen");
  if (name === "start") renderStart();
  const stamm = $(`#tab-${name}[data-stamm]`);
  if (stamm) renderStamm(stamm.dataset.stamm);
}
$$("nav [data-tab]").forEach(b => b.addEventListener("click", () => {
  const tab = b.dataset.tab;
  if (tab === "neu") neueRechnung();
  else if (tab === "angebot-neu") neuesAngebot();
  else showTab(tab);
}));

// Untermenüs: Klick auf den Hauptpunkt öffnet/schließt, Klick daneben oder Esc schließt
function schliesseMenues(ausser) {
  $$("nav .menu").forEach(m => { if (m !== ausser) m.classList.remove("offen"); });
}
$$("nav .menu-kopf").forEach(k => k.addEventListener("click", e => {
  e.stopPropagation();
  const menu = k.closest(".menu");
  schliesseMenues(menu);
  menu.classList.toggle("offen");
}));
document.addEventListener("click", e => { if (!e.target.closest("nav .menu")) schliesseMenues(); });
document.addEventListener("keydown", e => { if (e.key === "Escape") schliesseMenues(); });

// ---------- Editor-Modus: Rechnung oder Angebot ----------

function setModus(modus) {
  state.modus = modus;
  document.body.classList.toggle("modus-angebot", modus === "angebot");
  fillZahlungSelect();
}

const istAngebot = () => state.modus === "angebot";

function speichernText() {
  const art = istAngebot() ? "Angebot" : "Rechnung";
  $("#btn-speichern").textContent = state.editId
    ? `${art} ${$("#r-nummer").value} aktualisieren & PDF öffnen`
    : `${art} speichern & PDF öffnen`;
}

/* „Neue Rechnung“: Ein angefangenes Rechnungsformular bleibt erhalten, ein Angebot wird verlassen. */
async function neueRechnung() {
  if (istAngebot()) { setModus("rechnung"); await resetForm(); }
  showTab("neu");
}

async function neuesAngebot() {
  setModus("angebot");
  await resetForm();
  showTab("neu");
  window.scrollTo(0, 0);
}

function addDays(iso, n) {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d + n)).toISOString().slice(0, 10);
}
const gueltigkeitTage = () => Number(state.absender?.angebot_gueltigkeit_tage) || 30;

$("#r-datum").addEventListener("change", e => {
  if (istAngebot() && state.gueltigAuto && e.target.value) $("#a-gueltig").value = addDays(e.target.value, gueltigkeitTage());
});
$("#a-gueltig").addEventListener("input", () => { state.gueltigAuto = false; });
$("#logo").addEventListener("click", () => showTab("start"));

// ---------- Einstellungen ----------

$("#einstellungen-btn").addEventListener("click", () => showTab("einstellungen"));
document.addEventListener("click", e => {
  if (e.target.closest(".zu-einstellungen")) { e.preventDefault(); showTab("einstellungen"); }
});

async function ladeEinstellungen() {
  const werte = await api("einstellungen");
  const form = $("#einstellungen");
  for (const [k, v] of Object.entries(werte)) {
    const feld = form.elements[k];
    if (!feld) continue;
    if (feld.type === "checkbox") feld.checked = !!v; else feld.value = v ?? "";
  }
}

$("#einstellungen-verwerfen").addEventListener("click", () => {
  ladeEinstellungen();
  toast("Änderungen verworfen");
});

$("#einstellungen").addEventListener("submit", async e => {
  e.preventDefault();
  const form = e.target;
  const daten = {};
  [...form.elements].filter(f => f.name).forEach(f => {
    daten[f.name] = f.type === "checkbox" ? f.checked : f.value;
  });
  try {
    const res = await api("einstellungen", { method: "PUT", body: daten });
    await ladeAbsender();
    pruefeUpdate();
    toast(res.hinweise.length ? `Gespeichert. Hinweis: ${res.hinweise.join(" ")}` : "Einstellungen gespeichert", !!res.hinweise.length);
    // Neue Startnummern sofort im Editor berücksichtigen
    if (!state.editId) $("#r-nummer").value = (await api(istAngebot() ? "angebote/naechste-nummer" : "rechnungen/naechste-nummer")).nummer;
  } catch (err) { toast(err.message, true); }
});

/* Desktop-Version: nach neuer Version suchen und ggf. Hinweis zeigen (ausgeblendete Version wird gemerkt). */
async function pruefeUpdate() {
  if (!state.absender?.desktop) return;
  let u;
  try { u = await api("update"); } catch (_) { return; }
  const status = $("#update-status");
  status.innerHTML = !u.aktiv ? "" : u.fehler ? `· <span class="hint">Update-Prüfung nicht möglich (offline?)</span>`
    : u.verfuegbar ? `· <a href="${esc(u.url)}" target="_blank" rel="noopener"><b>Update auf ${esc(u.neueste)} verfügbar ↗</b></a>`
    : `· <span class="frist gruen">aktuell</span>`;
  const zeigen = u.aktiv && u.verfuegbar && localStorage.getItem("update-ausgeblendet") !== u.neueste;
  if (zeigen) {
    $("#update-version").textContent = u.neueste;
    $("#update-installiert").textContent = u.installiert;
    $("#update-link").href = u.url;
  }
  $("#update-banner").classList.toggle("hidden", !zeigen);
}
$("#update-zu").addEventListener("click", () => {
  localStorage.setItem("update-ausgeblendet", $("#update-version").textContent);
  $("#update-banner").classList.add("hidden");
});

/* Absender-Infos laden und alles aktualisieren, was davon abhängt (Hinweis-Banner, Paperless-Buttons …). */
async function ladeAbsender() {
  const abs = await api("absender");
  state.absender = abs;
  $("#app-version").textContent = abs.version || "–";
  document.body.classList.toggle("desktop", !!abs.desktop);   // Desktop-Version: HA-spezifische Hinweise ausblenden
  $("#warnung").classList.toggle("hidden", abs.vollstaendig);
  $$(".pl-button").forEach(b => b.classList.toggle("hidden", !abs.paperless));   // nur mit „Paperless installiert“
  return abs;
}

// ---------- Hell/Dunkel ----------
$("#theme-toggle").addEventListener("click", () => {
  const neu = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
  document.documentElement.dataset.theme = neu;
  try { localStorage.setItem("theme", neu); } catch (e) {}
});

// ---------- Stammdaten für den Editor laden ----------

async function loadLookups() {
  [state.textbausteine, state.zahlungsbedingungen] = await Promise.all([
    api("textbausteine"), api("zahlungsbedingungen"),
  ]);
  fillZahlungSelect();
  $$("#positionen .pos").forEach(fillTbSelect);
}

function fillZahlungSelect() {
  const sel = $("#r-zahlung");
  const current = sel.value;
  sel.innerHTML = (istAngebot() ? `<option value="">– keine Angabe im Angebot –</option>` : "") +
    state.zahlungsbedingungen.map(z => `<option value="${esc(z.text)}">${esc(z.titel)}</option>`).join("");
  if ([...sel.options].some(o => o.value === current)) sel.value = current;
  updateZahlungText();
}

function updateZahlungText() {
  $("#r-zahlung-text").textContent = $("#r-zahlung").value;
}
$("#r-zahlung").addEventListener("change", updateZahlungText);

// ---------- Kunde mit Autovervollständigung ----------

const acList = $("#ac-list");
let acItems = [], acIndex = -1, acTimer;

function setKundeHinweis() {
  $("#k-hinweis").textContent = state.kundeId
    ? "Bestandskunde – Adressänderungen werden beim Speichern übernommen."
    : ($("#k-name").value.trim() ? "Neuer Kunde – wird beim Speichern angelegt." : "");
}

function fillKunde(k) {
  state.kundeId = k.id || null;
  $("#k-name").value = k.name || "";
  $("#k-zusatz").value = k.zusatz || "";
  $("#k-strasse").value = k.strasse || "";
  $("#k-plz").value = k.plz || "";
  $("#k-ort").value = k.ort || "";
  setKundeHinweis();
}

function closeAc() { acList.classList.add("hidden"); acIndex = -1; }

function renderAc() {
  if (!acItems.length) return closeAc();
  acList.innerHTML = acItems.map((k, i) =>
    `<li data-i="${i}" class="${i === acIndex ? "active" : ""}">${esc(k.name)}` +
    `<small>${esc([k.strasse, [k.plz, k.ort].filter(Boolean).join(" ")].filter(Boolean).join(", "))}</small></li>`
  ).join("");
  acList.classList.remove("hidden");
}

$("#k-name").addEventListener("input", e => {
  state.kundeId = null;           // Name geändert → nicht mehr automatisch derselbe Kunde
  setKundeHinweis();
  const q = e.target.value.trim();
  clearTimeout(acTimer);
  if (!q) return closeAc();
  acTimer = setTimeout(async () => {
    acItems = await api("kunden?q=" + encodeURIComponent(q));
    acIndex = -1;
    renderAc();
  }, 150);
});

$("#k-name").addEventListener("keydown", e => {
  if (acList.classList.contains("hidden")) return;
  if (e.key === "ArrowDown") { acIndex = Math.min(acIndex + 1, acItems.length - 1); renderAc(); e.preventDefault(); }
  else if (e.key === "ArrowUp") { acIndex = Math.max(acIndex - 1, 0); renderAc(); e.preventDefault(); }
  else if (e.key === "Enter" && acIndex >= 0) { fillKunde(acItems[acIndex]); closeAc(); e.preventDefault(); }
  else if (e.key === "Escape") closeAc();
});

acList.addEventListener("mousedown", e => {
  const li = e.target.closest("li");
  if (!li) return;
  e.preventDefault();
  fillKunde(acItems[li.dataset.i]);
  closeAc();
});
$("#k-name").addEventListener("blur", () => setTimeout(closeAc, 100));

// ---------- Positionen ----------

function fillTbSelect(pos) {
  const sel = $(".tb", pos);
  const current = sel.value;
  sel.innerHTML = `<option value="">Rechnungsposten wählen …</option>` +
    state.textbausteine.map(t => `<option value="${t.id}">${esc(t.titel)}</option>`).join("") +
    `<option value="frei">Freitext (eigener Text)</option>`;
  sel.value = current;
}

/* Zeitfelder nur zeigen, wenn die Vorlage des Anlasses {von}/{bis} enthält. */
function updatePosMode(pos) {
  const zeiten = !!(pos._tb && hasTimes(pos._tb.text));
  $$(".calc", pos).forEach(el => el.classList.toggle("hidden", !zeiten));
  $(".text-hinweis", pos).textContent = pos._tb ? "(wird automatisch erzeugt – anpassbar)" : "";
}

const hasTimes = text => /\{von\}|\{bis\}/.test(text || "");
const shortTime = t => (t || "").replace(/^0(\d)/, "$1");   // "02:00" → "2:00"

/* Dauer in Stunden, über Mitternacht hinweg (17:00 → 02:00 = 9 h). */
function hoursBetween(von, bis) {
  if (!von || !bis) return null;
  const [h1, m1] = von.split(":").map(Number);
  const [h2, m2] = bis.split(":").map(Number);
  let min = (h2 * 60 + m2) - (h1 * 60 + m1);
  if (min <= 0) min += 24 * 60;
  return min / 60;
}

/* Text einer Position aus dem gewählten Textbaustein + Uhrzeiten erzeugen.
   Der Preis wird bewusst nicht gesetzt – er wird pro Rechnung individuell eingetragen. */
function applyTb(pos) {
  const tb = pos._tb;
  if (!tb) return;
  const von = $(".von", pos).value, bis = $(".bis", pos).value;
  $(".beschreibung", pos).value = tb.text
    .replaceAll("{von}", von ? shortTime(von) : "{von}")
    .replaceAll("{bis}", bis ? shortTime(bis) : "{bis}");

  const h = hoursBetween(von, bis);
  $(".stunden", pos).textContent = h ? `= ${String(h).replace(".", ",")} Std.` : "";
}

function addPosition(p = {}) {
  const pos = $("#tpl-position").content.firstElementChild.cloneNode(true);
  fillTbSelect(pos);
  const prev = $$("#positionen .pos").at(-1);
  $(".beschreibung", pos).value = p.beschreibung || "";
  $(".lieferdatum", pos).value = p.lieferdatum ?? (prev ? $(".lieferdatum", prev).value : "");
  $(".preis", pos).value = p.preis ?? "";

  updatePosMode(pos);
  $(".tb", pos).addEventListener("change", e => {
    pos._tb = state.textbausteine.find(t => String(t.id) === e.target.value) || null;
    updatePosMode(pos);
    if (pos._tb) {
      applyTb(pos);                      // Zeiten bleiben beim Wechsel des Anlasses erhalten
      if (hasTimes(pos._tb.text) && !$(".von", pos).value) $(".von", pos).focus();
    } else if (e.target.value === "frei") {
      $(".beschreibung", pos).value = "";
      $(".beschreibung", pos).focus();
    }
  });
  $(".von", pos).addEventListener("input", () => applyTb(pos));
  $(".bis", pos).addEventListener("input", () => applyTb(pos));
  $(".preis", pos).addEventListener("input", updateTotal);
  $(".del", pos).addEventListener("click", () => {
    pos.remove();
    if (!$$("#positionen .pos").length) addPosition();
    updateTotal();
  });

  $("#positionen").append(pos);
  updateTotal();
  return pos;
}
$("#pos-add").addEventListener("click", () => addPosition());

function updateTotal() {
  const sum = $$("#positionen .preis").reduce((s, i) => s + (Number(i.value) || 0), 0);
  $("#gesamt").textContent = fmtEuro(sum);
}

// ---------- Formular lesen / setzen ----------

function readForm() {
  return {
    art: state.modus,
    nummer: $("#r-nummer").value.trim(),
    datum: $("#r-datum").value,
    zahlungsbedingung: $("#r-zahlung").value,
    gueltig_bis: istAngebot() ? $("#a-gueltig").value : undefined,
    hinweise: istAngebot() ? $("#a-hinweise").value : undefined,
    angebot_id: !istAngebot() && state.ausAngebot ? state.ausAngebot : undefined,
    kunde: {
      id: state.kundeId,
      name: $("#k-name").value, zusatz: $("#k-zusatz").value, strasse: $("#k-strasse").value,
      plz: $("#k-plz").value, ort: $("#k-ort").value,
    },
    positionen: $$("#positionen .pos").map(pos => ({
      beschreibung: $(".beschreibung", pos).value,
      lieferdatum: $(".lieferdatum", pos).value,
      preis: $(".preis", pos).value,
    })),
  };
}

function checkPlaceholders(data) {
  const bad = data.positionen.find(p => hasTimes(p.beschreibung));
  if (bad) throw new Error("Bitte bei der Position die Uhrzeiten (von/bis) eintragen.");
}

async function resetForm() {
  state.editId = null;
  setAusAngebot(null);
  fillKunde({});
  $("#r-datum").value = today();
  $("#r-nummer").value = (await api(istAngebot() ? "angebote/naechste-nummer" : "rechnungen/naechste-nummer")).nummer;
  $("#r-zahlung").selectedIndex = 0;
  updateZahlungText();
  state.gueltigAuto = true;
  $("#a-gueltig").value = addDays(today(), gueltigkeitTage());
  $("#a-hinweise").value = "";
  $("#positionen").innerHTML = "";
  addPosition();
  speichernText();
}

/* Hinweis im Editor, wenn eine Rechnung aus einem Angebot erzeugt wird. */
function setAusAngebot(a) {
  state.ausAngebot = a ? a.id : null;
  $("#aus-angebot").classList.toggle("hidden", !a);
  $("#aus-angebot").textContent = a
    ? `Aus Angebot ${a.nummer} übernommen – beim Speichern wird das Angebot als „angenommen“ markiert.` : "";
}

function setZahlung(text) {
  const sel = $("#r-zahlung");
  if (text && ![...sel.options].some(o => o.value === text)) sel.add(new Option("(gespeicherter Text)", text));
  if (text || istAngebot()) sel.value = text || "";
  updateZahlungText();
}

function loadIntoForm(inv) {
  setModus("rechnung");
  setAusAngebot(null);
  state.editId = inv.id;
  fillKunde({ ...inv.kunde, id: inv.kunde_id });
  $("#r-nummer").value = inv.nummer;
  $("#r-datum").value = inv.datum;
  setZahlung(inv.zahlungsbedingung);
  $("#positionen").innerHTML = "";
  inv.positionen.forEach(p => addPosition(p));
  speichernText();
  showTab("neu");
  window.scrollTo(0, 0);
}

function loadAngebotIntoForm(a) {
  setModus("angebot");
  setAusAngebot(null);
  state.editId = a.id;
  fillKunde({ ...a.kunde, id: a.kunde_id });
  $("#r-nummer").value = a.nummer;
  $("#r-datum").value = a.datum;
  state.gueltigAuto = false;
  $("#a-gueltig").value = a.gueltig_bis || "";
  $("#a-hinweise").value = a.hinweise || "";
  setZahlung(a.zahlungsbedingung);
  $("#positionen").innerHTML = "";
  a.positionen.forEach(p => addPosition(p));
  speichernText();
  showTab("neu");
  window.scrollTo(0, 0);
}

/* Angebot → neue Rechnung: Kunde, Positionen und ggf. Zahlungsbedingung übernehmen. */
async function angebotZuRechnung(a) {
  setModus("rechnung");
  await resetForm();
  fillKunde({ ...a.kunde, id: a.kunde_id });
  if (a.zahlungsbedingung) setZahlung(a.zahlungsbedingung);
  $("#positionen").innerHTML = "";
  a.positionen.forEach(p => addPosition(p));
  setAusAngebot(a);
  showTab("neu");
  window.scrollTo(0, 0);
}

$("#btn-neu").addEventListener("click", () => resetForm());

$("#btn-vorschau").addEventListener("click", () => {
  const data = readForm();
  openPdf(() => { checkPlaceholders(data); return api("vorschau", { method: "POST", body: data }); });
});

$("#rechnung").addEventListener("submit", e => {
  e.preventDefault();
  const data = readForm();
  const pfad = istAngebot() ? "angebote" : "rechnungen";
  const art = istAngebot() ? "Angebot" : "Rechnung";
  openPdf(async () => {
    checkPlaceholders(data);
    const res = state.editId
      ? await api(`${pfad}/${state.editId}`, { method: "PUT", body: data })
      : await api(pfad, { method: "POST", body: data });
    state.editId = res.id;
    if (data.angebot_id) setAusAngebot(null);   // Angebot ist jetzt als angenommen markiert
    speichernText();
    toast(`${art} ${data.nummer} gespeichert` + (res.datei ? ` → ${res.datei.split("/").pop()}` : ""));
    return api(`${pfad}/${res.id}/pdf`);
  });
});

// ---------- Rechnungsliste ----------

async function loadListe() {
  state.rechnungen = await api("rechnungen");
  renderListe();
}

/* Archiv-Sortierung: Feld + Richtung, wird im Browser gemerkt. */
const SORT_DEFAULT = { feld: "datum", richtung: "desc" };
const ERSTE_RICHTUNG = { datum: "desc", nummer: "desc", gesamt: "desc", kunde: "asc" };

const vergleich = {
  nummer: (a, b) => a.nummer.localeCompare(b.nummer, "de", { numeric: true }),
  datum: (a, b) => a.datum.localeCompare(b.datum),
  gesamt: (a, b) => a.gesamt - b.gesamt,
  kunde: (a, b) => (a.kunde.name || "").localeCompare(b.kunde.name || "", "de", { sensitivity: "base" }),
};

let sortierung = (() => {
  try {
    const s = JSON.parse(localStorage.getItem("liste-sort"));
    return s && vergleich[s.feld] ? s : SORT_DEFAULT;
  } catch (_) { return SORT_DEFAULT; }
})();

function sortiere(list) {
  const { feld, richtung } = sortierung;
  const dir = richtung === "asc" ? 1 : -1;
  // Bei Gleichstand: neueste Rechnung zuerst
  return [...list].sort((a, b) => dir * vergleich[feld](a, b) || -vergleich.datum(a, b) || -vergleich.nummer(a, b));
}

function setSortierung(feld, richtung) {
  sortierung = { feld, richtung };
  localStorage.setItem("liste-sort", JSON.stringify(sortierung));
  renderListe();
}

$("#liste-sort").addEventListener("change", e => {
  const [feld, richtung] = e.target.value.split(":");
  setSortierung(feld, richtung);
});
$$("#tab-liste th[data-sort]").forEach(th => th.addEventListener("click", () => {
  const feld = th.dataset.sort;
  const richtung = sortierung.feld === feld
    ? (sortierung.richtung === "asc" ? "desc" : "asc")   // gleiche Spalte → umdrehen
    : ERSTE_RICHTUNG[feld];
  setSortierung(feld, richtung);
}));

// ---------- Offene Rechnungen & Zahlungsfristen ----------

const TAG_MS = 24 * 60 * 60 * 1000;
const isoToUtc = iso => { const [y, m, d] = iso.split("-").map(Number); return Date.UTC(y, m - 1, d); };
const heuteUtc = () => { const n = new Date(); return Date.UTC(n.getFullYear(), n.getMonth(), n.getDate()); };
const utcToDe = t => fmtDate(new Date(t).toISOString().slice(0, 10));
const rechnungsName = r => r.name || `Rechnung_${r.nummer}`;

/* Zahlungsziel aus der Zahlungsbedingung („… innerhalb der nächsten 8 Tage …“). */
function zahlungsziel(r) {
  const m = /(\d+)\s*Tage?n?\b/i.exec(r.zahlungsbedingung || "");
  if (!m || !r.datum) return null;
  const faellig = isoToUtc(r.datum) + Number(m[1]) * TAG_MS;
  return { faellig, rest: Math.round((faellig - heuteUtc()) / TAG_MS) };
}

function fristBadge(z) {
  if (!z) return `<span class="frist neutral">ohne Frist</span>`;
  if (z.rest < 0) return `<span class="frist rot">${-z.rest} ${-z.rest === 1 ? "Tag" : "Tage"} überfällig</span>`;
  if (z.rest === 0) return `<span class="frist gelb">heute fällig</span>`;
  if (z.rest <= 3) return `<span class="frist gelb">noch ${z.rest} ${z.rest === 1 ? "Tag" : "Tage"}</span>`;
  return `<span class="frist gruen">noch ${z.rest} Tage</span>`;
}

const aktionen = (...welche) => welche.map(a => ({
  pdf: `<button class="small secondary" data-act="pdf">PDF</button>`,
  edit: `<button class="small secondary" data-act="edit">Bearbeiten</button>`,
  del: `<button class="small danger" data-act="del">Löschen</button>`,
}[a])).join("");

function renderOffen() {
  const offen = state.rechnungen.filter(r => !r.bezahlt).map(r => ({ ...r, ziel: zahlungsziel(r) }));
  // Überfällige zuerst, dann nach Fälligkeit, Rechnungen ohne Frist am Ende
  offen.sort((a, b) => (a.ziel ? a.ziel.faellig : Infinity) - (b.ziel ? b.ziel.faellig : Infinity)
    || a.datum.localeCompare(b.datum));

  const summe = offen.reduce((s, r) => s + r.gesamt, 0);
  const dringendste = offen[0];   // Liste ist nach Fälligkeit sortiert

  $("#offen").innerHTML = `
    <h2>Offene Rechnungen</h2>
    ${offen.length ? `<table class="list offen-liste">
      <thead><tr><th>Rechnung</th><th class="num">Betrag</th><th>Verbleibende Zeit</th><th class="haken-spalte">Bezahlt</th><th class="loesch-spalte"></th></tr></thead>
      <tbody>
      <tr class="summen-zeile">
        <td>${offen.length} offene Rechnung${offen.length === 1 ? "" : "en"}</td>
        <td class="num">${fmtEuro(summe)}</td>
        <td><span class="naechste">nächste Frist:</span> ${fristBadge(dringendste.ziel)}</td>
        <td></td><td></td>
      </tr>
      ${offen.map(r => `<tr data-id="${r.id}">
        <td><a href="#" class="rlink" title="Im Editor öffnen">${esc(rechnungsName(r))}</a></td>
        <td class="num">${fmtEuro(r.gesamt)}</td>
        <td title="${r.ziel ? `fällig am ${utcToDe(r.ziel.faellig)}` : ""}">${fristBadge(r.ziel)}</td>
        <td class="haken-spalte"><input type="checkbox" class="offen-haken" title="Als bezahlt markieren → ins Archiv"></td>
        <td class="loesch-spalte"><button type="button" class="icon del" data-act="del" title="Rechnung löschen">✕</button></td>
      </tr>`).join("")}
      </tbody></table>`
    : `<p class="hint alles-bezahlt">Keine offenen Rechnungen – alles bezahlt.</p>`}`;
}

// ---------- Archiv (bezahlte Rechnungen) ----------

const plChip = r => ` <button type="button" class="pl-chip" data-act="pl-reset" title="An Paperless übertragen am ${
  fmtDate(r.paperless_am.slice(0, 10))} – klicken zum Zurücksetzen"><span class="pl-ok">Paperless ✓</span><span class="pl-x">Paperless ✕</span></button>`;

/* Link-Download (Server sendet Content-Disposition: attachment) */
function ladeHerunter(url) {
  const a = document.createElement("a");
  a.href = url;
  a.download = "";
  document.body.appendChild(a);
  a.click();
  a.remove();
}

/* Markierte Belege in den Paperless-Eingang legen. art: "rechnung" | "angebot" */
async function anPaperless({ btn, ids, art, belege, name, neuLaden }) {
  if (!ids.length) return [];
  const wort = art === "angebot" ? ["Angebot", "Angebote"] : ["Rechnung", "Rechnungen"];
  const schon = belege.filter(r => ids.includes(r.id) && r.paperless_am);
  if (schon.length && !confirm(`${schon.length === 1 ? `${name(schon[0])} wurde` : `${schon.length} der ${wort[1]} wurden`}`
      + " bereits an Paperless übertragen. Trotzdem erneut senden? (Paperless legt dann ein zweites Dokument an.)")) return [];
  btn.disabled = true;
  btn.textContent = `Sende ${ids.length} …`;
  try {
    const res = await api("paperless", { method: "POST", body: { ids, art } });
    await neuLaden();
    if (res.fehler.length) {
      const nicht = ids.length - res.ok.length;
      toast(`${res.ok.length ? `${res.ok.length} übertragen, ` : ""}${nicht} nicht übertragen: ${res.fehler[0].error}`, true);
    } else {
      toast(`${res.ok.length} ${res.ok.length === 1 ? wort[0] : wort[1]} in den Paperless-Eingang gelegt – Paperless verarbeitet sie jetzt.`);
    }
    return res.ok;
  } catch (err) {
    toast(err.message, true);
    return [];
  } finally {
    btn.disabled = false;
    btn.textContent = "⇪ An Paperless senden";
  }
}

const auswahl = new Set();   // IDs der im Archiv markierten Rechnungen

function renderListe() {
  renderOffen();
  const q = $("#liste-suche").value.trim().toLowerCase();
  const list = sortiere(state.rechnungen.filter(r => r.bezahlt &&
    (!q || [rechnungsName(r), r.nummer, r.kunde.name, r.kunde.ort, ...r.positionen.map(p => p.beschreibung)]
      .join(" ").toLowerCase().includes(q))));

  $("#liste-sort").value = `${sortierung.feld}:${sortierung.richtung}`;
  $$("#tab-liste th[data-sort]").forEach(th => {
    const aktiv = th.dataset.sort === sortierung.feld;
    th.classList.toggle("sortiert", aktiv);
    th.dataset.pfeil = aktiv ? (sortierung.richtung === "asc" ? "▲" : "▼") : "";
  });
  $("#liste-body").innerHTML = list.map(r => `
    <tr data-id="${r.id}"${auswahl.has(r.id) ? ' class="markiert"' : ""}>
      <td class="auswahl-spalte"><input type="checkbox" class="auswahl"${auswahl.has(r.id) ? " checked" : ""} title="Markieren (Herunterladen / Paperless)"></td>
      <td>${esc(r.nummer)}${r.paperless_am
        ? plChip(r) : ""}</td>
      <td>${fmtDate(r.datum)}</td>
      <td>${esc(r.kunde.name)}<br><small>${esc(r.kunde.ort)}</small></td>
      <td class="num">${fmtEuro(r.gesamt)}</td>
      <td><input type="checkbox" class="bezahlt" checked title="Haken entfernen = zurück zu den offenen Rechnungen"></td>
      <td class="btns">${aktionen("pdf", "edit", "del")}</td>
    </tr>`).join("") ||
    `<tr><td colspan="7" class="hint">${q ? "Keine Treffer im Archiv." : "Noch keine bezahlten Rechnungen im Archiv."}</td></tr>`;
  $("#liste-summe").textContent = list.length
    ? `${list.length} Rechnung${list.length === 1 ? "" : "en"} · Summe ${fmtEuro(list.reduce((s, r) => s + r.gesamt, 0))}` : "";
  renderAuswahl();
}

/* Auswahl-Leiste + „Alle“-Checkbox passend zur aktuellen Auswahl. */
function renderAuswahl() {
  // Nur Rechnungen behalten, die noch existieren und im Archiv sind
  const archivIds = new Set(state.rechnungen.filter(r => r.bezahlt).map(r => r.id));
  [...auswahl].forEach(id => { if (!archivIds.has(id)) auswahl.delete(id); });

  const n = auswahl.size;
  $("#auswahl-leiste").classList.toggle("hidden", !n);
  $("#auswahl-anzahl").textContent = `${n} Rechnung${n === 1 ? "" : "en"} ausgewählt`;
  const sichtbar = $$("#liste-body tr[data-id]").map(tr => Number(tr.dataset.id));
  const markiert = sichtbar.filter(id => auswahl.has(id)).length;
  const alle = $("#auswahl-alle");
  alle.checked = sichtbar.length > 0 && markiert === sichtbar.length;
  alle.indeterminate = markiert > 0 && markiert < sichtbar.length;
  alle.disabled = !sichtbar.length;
}

$("#auswahl-alle").addEventListener("change", e => {
  $$("#liste-body tr[data-id]").forEach(tr => {
    const id = Number(tr.dataset.id);
    if (e.target.checked) auswahl.add(id); else auswahl.delete(id);
  });
  renderListe();
});

$("#btn-auswahl-aufheben").addEventListener("click", () => { auswahl.clear(); renderListe(); });

$("#btn-auswahl-paperless").addEventListener("click", async e => {
  const ok = await anPaperless({ btn: e.currentTarget, ids: [...auswahl], art: "rechnung",
    belege: state.rechnungen, name: rechnungsName, neuLaden: loadListe });
  ok.forEach(id => auswahl.delete(id));
  renderListe();
});

$("#btn-auswahl-download").addEventListener("click", () => {
  if (!auswahl.size) return;
  ladeHerunter(`api/rechnungen/download?ids=${[...auswahl].join(",")}`);
  toast(auswahl.size === 1 ? "PDF wird heruntergeladen …"
                           : `${auswahl.size} Rechnungen werden als ZIP heruntergeladen …`);
});
$("#liste-suche").addEventListener("input", renderListe);

async function setBezahlt(id, bezahlt) {
  const inv = state.rechnungen.find(r => r.id === id);
  await api(`rechnungen/${id}/bezahlt`, { method: "PATCH", body: { bezahlt } });
  inv.bezahlt = bezahlt;
  renderListe();
  toast(bezahlt ? `${rechnungsName(inv)} ist bezahlt → ins Archiv verschoben`
                : `${rechnungsName(inv)} ist wieder offen`);
}

// Klick auf den Rechnungsnamen → im Editor öffnen
$("#offen").addEventListener("click", e => {
  const a = e.target.closest("a.rlink");
  if (!a) return;
  e.preventDefault();
  loadIntoForm(state.rechnungen.find(r => r.id === Number(a.closest("tr").dataset.id)));
});

// Haken in „Offene Rechnungen“ → bezahlt → ins Archiv
$("#offen").addEventListener("change", async e => {
  if (!e.target.classList.contains("offen-haken")) return;
  try { await setBezahlt(Number(e.target.closest("tr").dataset.id), true); }
  catch (err) { toast(err.message, true); e.target.checked = false; }
});

// Schalter im Archiv: Haken entfernen → zurück zu den offenen Rechnungen
$("#liste-body").addEventListener("change", async e => {
  if (e.target.classList.contains("auswahl")) {   // Markierung zum Herunterladen
    const tr = e.target.closest("tr");
    const id = Number(tr.dataset.id);
    if (e.target.checked) auswahl.add(id); else auswahl.delete(id);
    tr.classList.toggle("markiert", e.target.checked);
    return renderAuswahl();
  }
  if (!e.target.classList.contains("bezahlt")) return;
  try { await setBezahlt(Number(e.target.closest("tr").dataset.id), e.target.checked); }
  catch (err) { toast(err.message, true); e.target.checked = !e.target.checked; }
});

// Buttons im Archiv
$("#tab-liste").addEventListener("click", async e => {
  const btn = e.target.closest("tr[data-id] button[data-act]");
  if (!btn) return;
  const id = Number(btn.closest("tr").dataset.id);
  const inv = state.rechnungen.find(r => r.id === id);
  try {
    if (btn.dataset.act === "pdf") window.open(`api/rechnungen/${id}/pdf`, "_blank");
    if (btn.dataset.act === "edit") loadIntoForm(inv);
    if (btn.dataset.act === "pl-reset" && confirm(`Paperless-Markierung bei ${rechnungsName(inv)} zurücksetzen?\n\n`
        + "Die Rechnung gilt dann wieder als nicht übertragen und kann erneut an Paperless gesendet werden. "
        + "Die Datei in Paperless selbst bleibt davon unberührt.")) {
      await api(`rechnungen/${id}/paperless`, { method: "DELETE" });
      inv.paperless_am = null;
      renderListe();
      toast(`Paperless-Markierung bei ${rechnungsName(inv)} zurückgesetzt`);
    }
    if (btn.dataset.act === "del" && confirm(`${rechnungsName(inv)} wirklich löschen?`)) {
      await api("rechnungen/" + id, { method: "DELETE" });
      if (state.editId === id) resetForm();
      await loadListe();
      toast(`${rechnungsName(inv)} gelöscht`);
    }
  } catch (err) { toast(err.message, true); }
});

// ---------- Angebote ----------

const STATUS_TEXT = { offen: "offen", angenommen: "angenommen", abgelehnt: "abgelehnt" };
const auswahlA = new Set();   // IDs der markierten Angebote
const angebotName = a => a.name || `Angebot_${a.nummer}`;

async function loadAngebote() {
  try {
    [state.angebote, state.rechnungen] = await Promise.all([api("angebote"), api("rechnungen")]);
  } catch (e) { return toast("Laden fehlgeschlagen: " + e.message, true); }
  renderAngebote();
}

function gueltigBadge(a) {
  if (a.status === "angenommen") {
    const r = a.rechnung_id && state.rechnungen.find(x => x.id === a.rechnung_id);
    return r ? `<a href="#" class="rlink nowrap" data-rechnung="${r.id}" title="${esc(rechnungsName(r))} öffnen">→ Rechnung ${esc(r.nummer)}</a>`
             : `<span class="frist gruen">angenommen</span>`;
  }
  if (a.status === "abgelehnt") return `<span class="frist neutral">abgelehnt</span>`;
  if (!a.gueltig_bis) return `<span class="frist neutral">ohne Frist</span>`;
  const rest = Math.round((isoToUtc(a.gueltig_bis) - heuteUtc()) / TAG_MS);
  const bis = `title="gültig bis ${fmtDate(a.gueltig_bis)}"`;
  if (rest < 0) return `<span class="frist rot" ${bis}>abgelaufen</span>`;
  if (rest === 0) return `<span class="frist gelb" ${bis}>endet heute</span>`;
  if (rest <= 7) return `<span class="frist gelb" ${bis}>noch ${rest} ${rest === 1 ? "Tag" : "Tage"}</span>`;
  return `<span class="frist gruen" ${bis}>bis ${fmtDate(a.gueltig_bis)}</span>`;
}

/* Offene Angebote mit Restlaufzeit: noch gültige zuerst (bald ablaufende oben), dann ohne Frist,
   dann abgelaufene (zuletzt abgelaufene oben). */
function offeneAngebote() {
  const rang = a => a.rest === null ? 1 : a.rest < 0 ? 2 : 0;
  return state.angebote.filter(a => a.status === "offen")
    .map(a => ({ ...a, rest: a.gueltig_bis ? Math.round((isoToUtc(a.gueltig_bis) - heuteUtc()) / TAG_MS) : null }))
    .sort((a, b) => rang(a) - rang(b) || (rang(a) === 2 ? b.rest - a.rest : (a.rest ?? 0) - (b.rest ?? 0))
      || b.datum.localeCompare(a.datum));
}

function restBadge(a) {
  const bis = a.gueltig_bis ? `title="gültig bis ${fmtDate(a.gueltig_bis)}"` : "";
  if (a.rest === null) return `<span class="frist neutral">ohne Frist</span>`;
  if (a.rest < 0) return `<span class="frist rot" ${bis}>seit ${-a.rest} ${-a.rest === 1 ? "Tag" : "Tagen"} abgelaufen</span>`;
  if (a.rest === 0) return `<span class="frist gelb" ${bis}>endet heute</span>`;
  return `<span class="frist ${a.rest <= 7 ? "gelb" : "gruen"}" ${bis}>noch ${a.rest} ${a.rest === 1 ? "Tag" : "Tage"}</span>`;
}

function renderAngeboteOffen() {
  const offen = offeneAngebote();
  const gueltig = offen.filter(a => a.rest === null || a.rest >= 0);
  const summe = gueltig.reduce((s, a) => s + a.gesamt, 0);
  $("#angebote-offen").innerHTML = `
    <h2>Offene Angebote</h2>
    ${offen.length ? `<table class="list offen-liste">
      <thead><tr><th>Angebot</th><th>Angeboten am</th><th class="num">Betrag</th><th>Gültigkeit</th><th></th></tr></thead>
      <tbody>
      <tr class="summen-zeile">
        <td>${gueltig.length} noch gültige${offen.length > gueltig.length ? ` · ${offen.length - gueltig.length} abgelaufen` : ""}</td>
        <td></td>
        <td class="num">${fmtEuro(summe)}</td>
        <td>${gueltig.length ? `<span class="naechste">nächster Ablauf:</span> ${restBadge(gueltig[0])}` : ""}</td>
        <td></td>
      </tr>
      ${offen.map(a => `<tr data-id="${a.id}">
        <td><a href="#" class="rlink" title="Im Editor öffnen">${esc(angebotName(a))}</a><br><small>${esc(a.kunde.name)}</small></td>
        <td>${fmtDate(a.datum)}</td>
        <td class="num">${fmtEuro(a.gesamt)}</td>
        <td>${restBadge(a)}</td>
        <td class="btns"><button class="small" data-act="rechnung" title="Rechnung aus diesem Angebot erstellen">→ Rechnung</button></td>
      </tr>`).join("")}
      </tbody></table>`
    : `<p class="hint alles-bezahlt">Keine offenen Angebote.</p>`}`;
}

$("#angebote-offen").addEventListener("click", async e => {
  const tr = e.target.closest("tr[data-id]");
  if (!tr) return;
  const a = state.angebote.find(x => x.id === Number(tr.dataset.id));
  if (e.target.closest("a.rlink")) { e.preventDefault(); loadAngebotIntoForm(a); }
  if (e.target.closest("button[data-act='rechnung']")) {
    try { await angebotZuRechnung(a); } catch (err) { toast(err.message, true); }
  }
});

function renderAngebote() {
  renderAngeboteOffen();
  const q = $("#angebote-suche").value.trim().toLowerCase();
  const list = state.angebote.filter(a =>
    !q || [angebotName(a), a.nummer, a.kunde.name, a.kunde.ort, ...a.positionen.map(p => p.beschreibung)]
      .join(" ").toLowerCase().includes(q));
  $("#angebote-body").innerHTML = list.map(a => `
    <tr data-id="${a.id}" class="${a.status === "offen" ? "" : "angebot-zu"}${auswahlA.has(a.id) ? " markiert" : ""}">
      <td class="auswahl-spalte"><input type="checkbox" class="auswahl"${auswahlA.has(a.id) ? " checked" : ""} title="Markieren (Herunterladen / Paperless)"></td>
      <td>${esc(a.nummer)}${a.paperless_am ? plChip(a) : ""}</td>
      <td>${fmtDate(a.datum)}</td>
      <td>${esc(a.kunde.name)}<br><small>${esc(a.kunde.ort)}</small></td>
      <td class="num">${fmtEuro(a.gesamt)}</td>
      <td>${gueltigBadge(a)}</td>
      <td><select class="status-select ${a.status}" title="Status des Angebots">${Object.entries(STATUS_TEXT)
        .map(([k, t]) => `<option value="${k}"${k === a.status ? " selected" : ""}>${t}</option>`).join("")}</select></td>
      <td class="btns">
        <button class="small secondary" data-act="pdf">PDF</button>
        <button class="small secondary" data-act="edit">Bearbeiten</button>
        ${a.rechnung_id ? "" : `<button class="small" data-act="rechnung" title="Rechnung aus diesem Angebot erstellen">→ Rechnung</button>`}
        <button class="small danger" data-act="del">Löschen</button>
      </td>
    </tr>`).join("") ||
    `<tr><td colspan="8" class="hint">${q ? "Keine Treffer." : "Noch keine Angebote – mit „＋ Neues Angebot“ das erste schreiben."}</td></tr>`;
  const offen = state.angebote.filter(a => a.status === "offen");
  $("#angebote-summe").textContent = state.angebote.length
    ? `${state.angebote.length} Angebot${state.angebote.length === 1 ? "" : "e"} · ${offen.length} offen`
      + (offen.length ? ` (${fmtEuro(offen.reduce((s, a) => s + a.gesamt, 0))})` : "") : "";
  renderAuswahlA();
}

function renderAuswahlA() {
  const vorhanden = new Set(state.angebote.map(a => a.id));
  [...auswahlA].forEach(id => { if (!vorhanden.has(id)) auswahlA.delete(id); });
  const n = auswahlA.size;
  $("#a-auswahl-leiste").classList.toggle("hidden", !n);
  $("#a-auswahl-anzahl").textContent = `${n} Angebot${n === 1 ? "" : "e"} ausgewählt`;
  const sichtbar = $$("#angebote-body tr[data-id]").map(tr => Number(tr.dataset.id));
  const markiert = sichtbar.filter(id => auswahlA.has(id)).length;
  const alle = $("#a-auswahl-alle");
  alle.checked = sichtbar.length > 0 && markiert === sichtbar.length;
  alle.indeterminate = markiert > 0 && markiert < sichtbar.length;
  alle.disabled = !sichtbar.length;
}

$("#a-auswahl-alle").addEventListener("change", e => {
  $$("#angebote-body tr[data-id]").forEach(tr => {
    const id = Number(tr.dataset.id);
    if (e.target.checked) auswahlA.add(id); else auswahlA.delete(id);
  });
  renderAngebote();
});
$("#btn-a-auswahl-aufheben").addEventListener("click", () => { auswahlA.clear(); renderAngebote(); });
$("#btn-a-auswahl-download").addEventListener("click", () => {
  if (!auswahlA.size) return;
  ladeHerunter(`api/angebote/download?ids=${[...auswahlA].join(",")}`);
  toast(auswahlA.size === 1 ? "PDF wird heruntergeladen …" : `${auswahlA.size} Angebote werden als ZIP heruntergeladen …`);
});
$("#btn-a-auswahl-paperless").addEventListener("click", async e => {
  const ok = await anPaperless({ btn: e.currentTarget, ids: [...auswahlA], art: "angebot",
    belege: state.angebote, name: angebotName, neuLaden: loadAngebote });
  ok.forEach(id => auswahlA.delete(id));
  renderAngebote();
});
$("#angebote-suche").addEventListener("input", renderAngebote);
$("#btn-angebot-neu").addEventListener("click", neuesAngebot);

$("#angebote-body").addEventListener("change", async e => {
  if (e.target.classList.contains("auswahl")) {   // Markierung
    const tr = e.target.closest("tr");
    const id = Number(tr.dataset.id);
    if (e.target.checked) auswahlA.add(id); else auswahlA.delete(id);
    tr.classList.toggle("markiert", e.target.checked);
    return renderAuswahlA();
  }
  if (!e.target.classList.contains("status-select")) return;
  const id = Number(e.target.closest("tr").dataset.id);
  const a = state.angebote.find(x => x.id === id);
  try {
    await api(`angebote/${id}/status`, { method: "PATCH", body: { status: e.target.value } });
    a.status = e.target.value;
    renderAngebote();
    toast(`${angebotName(a)}: ${STATUS_TEXT[a.status]}`);
  } catch (err) { toast(err.message, true); e.target.value = a.status; }
});

$("#angebote-body").addEventListener("click", async e => {
  const link = e.target.closest("a[data-rechnung]");
  if (link) {
    e.preventDefault();
    return loadIntoForm(state.rechnungen.find(r => r.id === Number(link.dataset.rechnung)));
  }
  const btn = e.target.closest("button[data-act]");
  if (!btn) return;
  const id = Number(btn.closest("tr").dataset.id);
  const a = state.angebote.find(x => x.id === id);
  try {
    if (btn.dataset.act === "pdf") window.open(`api/angebote/${id}/pdf`, "_blank");
    if (btn.dataset.act === "edit") loadAngebotIntoForm(a);
    if (btn.dataset.act === "pl-reset" && confirm(`Paperless-Markierung bei ${angebotName(a)} zurücksetzen?\n\n`
        + "Das Angebot gilt dann wieder als nicht übertragen und kann erneut an Paperless gesendet werden. "
        + "Die Datei in Paperless selbst bleibt davon unberührt.")) {
      await api(`angebote/${id}/paperless`, { method: "DELETE" });
      a.paperless_am = null;
      renderAngebote();
      toast(`Paperless-Markierung bei ${angebotName(a)} zurückgesetzt`);
    }
    if (btn.dataset.act === "rechnung") await angebotZuRechnung(a);
    if (btn.dataset.act === "del" && confirm(`${angebotName(a)} wirklich löschen?`)) {
      await api("angebote/" + id, { method: "DELETE" });
      if (istAngebot() && state.editId === id) await resetForm();
      await loadAngebote();
      toast(`${angebotName(a)} gelöscht`);
    }
  } catch (err) { toast(err.message, true); }
});

// ---------- Stammdaten-Tabs (Kunden, Textbausteine, Zahlungsbedingungen) ----------

const STAMM = {
  kunden: {
    titel: "Kunden", einzahl: "Kunde",
    felder: [
      ["name", "Name"], ["zusatz", "Zusatz"], ["strasse", "Straße"],
      ["plz", "PLZ"], ["ort", "Ort"], ["email", "E-Mail"],
    ],
    zeile: k => `${esc(k.name)}${k.zusatz ? `<br><small>${esc(k.zusatz)}</small>` : ""}`,
    info: k => esc([k.strasse, [k.plz, k.ort].filter(Boolean).join(" ")].filter(Boolean).join(", ")),
  },
  textbausteine: {
    titel: "Rechnungsposten", einzahl: "Rechnungsposten",
    hinweis: "Im Editor wählst du den Rechnungsposten und trägst die Zeiten ein – daraus entsteht der Rechnungstext. " +
      "Bleibt die Text-Vorlage leer, wird „DJ – Tätigkeit <Bezeichnung> – {von} Uhr bis {bis} Uhr“ verwendet. " +
      "{von} und {bis} werden durch die Uhrzeiten ersetzt.",
    felder: [["titel", "Bezeichnung (z. B. Hochzeit)"], ["text", "Text-Vorlage (optional)", "textarea"]],
    zeile: t => `${esc(t.titel)}<br><small>${esc(t.text)}</small>`,
    info: () => "",
  },
  zahlungsbedingungen: {
    titel: "Zahlungsbedingungen", einzahl: "Zahlungsbedingung",
    felder: [["titel", "Titel (Auswahl im Editor)"], ["text", "Text auf der Rechnung", "textarea"],
             ["sortierung", "Reihenfolge", "number"]],
    zeile: z => `${esc(z.titel)}<br><small>${esc(z.text)}</small>`,
    info: () => "",
  },
};

async function renderStamm(table) {
  const cfg = STAMM[table];
  const sec = $("#tab-" + table);
  const items = await api(table);
  sec.innerHTML = `
    <div class="card">
      <h2 class="form-titel">Neuer ${cfg.einzahl}</h2>
      ${cfg.hinweis ? `<p class="hint" style="margin-bottom:12px">${esc(cfg.hinweis)}</p>` : ""}
      <form class="stamm-form" autocomplete="off">
        ${cfg.felder.map(([k, label, type]) => type === "textarea"
          ? `<label>${label}<textarea name="${k}" rows="2"></textarea></label>`
          : `<label>${label}<input name="${k}" ${type === "number" ? 'type="number" step="any"' : ""}></label>`
        ).join("")}
        <div class="actions">
          <button type="button" class="secondary abbrechen">Abbrechen</button>
          <button type="submit">Speichern</button>
        </div>
      </form>
    </div>
    <div class="card">
      <h2>${cfg.titel}</h2>
      <table class="list"><tbody>
        ${items.map(it => `<tr data-id="${it.id}"><td>${cfg.zeile(it)}</td><td>${cfg.info(it)}</td>
          <td class="btns"><button class="small secondary" data-act="edit">Bearbeiten</button>
          <button class="small danger" data-act="del">Löschen</button></td></tr>`).join("")
          || `<tr><td class="hint">Noch keine Einträge.</td></tr>`}
      </tbody></table>
    </div>`;

  const form = $(".stamm-form", sec);
  let editId = null;
  const setForm = (it = {}) => {
    editId = it.id || null;
    cfg.felder.forEach(([k]) => { form.elements[k].value = it[k] ?? ""; });
    $(".form-titel", sec).textContent = editId ? `${cfg.einzahl} bearbeiten` : `Neuer ${cfg.einzahl}`;
  };

  $(".abbrechen", sec).addEventListener("click", () => setForm());
  form.addEventListener("submit", async e => {
    e.preventDefault();
    const data = Object.fromEntries(cfg.felder.map(([k]) => [k, form.elements[k].value]));
    try {
      await api(editId ? `${table}/${editId}` : table, { method: editId ? "PUT" : "POST", body: data });
      toast("Gespeichert");
      await renderStamm(table);
      if (table !== "kunden") loadLookups();
    } catch (err) { toast(err.message, true); }
  });
  $("tbody", sec).addEventListener("click", async e => {
    const btn = e.target.closest("button[data-act]");
    if (!btn) return;
    const it = items.find(i => i.id === Number(btn.closest("tr").dataset.id));
    if (btn.dataset.act === "edit") { setForm(it); window.scrollTo(0, 0); }
    if (btn.dataset.act === "del" && confirm(`„${it.titel || it.name}“ wirklich löschen?`)) {
      await api(`${table}/${it.id}`, { method: "DELETE" });
      await renderStamm(table);
      if (table !== "kunden") loadLookups();
    }
  });
}

// ---------- Import alter Rechnungen & Angebote ----------

const imp = { daten: null };

$("#btn-import").addEventListener("click", () => {
  $("#import").classList.toggle("hidden");
  window.scrollTo(0, 0);
});
$("#import-zu").addEventListener("click", () => $("#import").classList.add("hidden"));

// Import-Bereich liegt im Tab „Rechnungen“ – aus den Angeboten dorthin springen und öffnen
function oeffneImport() {
  showTab("liste");
  $("#import").classList.remove("hidden");
  window.scrollTo(0, 0);
}
$("#btn-angebot-import").addEventListener("click", oeffneImport);

$("#import-dateien").addEventListener("change", e => analyseImport(e.target.files));
const dz = $("#dropzone");
dz.addEventListener("dragover", e => { e.preventDefault(); dz.classList.add("over"); });
dz.addEventListener("dragleave", () => dz.classList.remove("over"));
dz.addEventListener("drop", e => {
  e.preventDefault();
  dz.classList.remove("over");
  analyseImport(e.dataTransfer.files);
});

async function analyseImport(files) {
  files = [...files].filter(f => f.name.toLowerCase().endsWith(".pdf"));
  if (!files.length) return toast("Bitte PDF-Dateien auswählen.", true);
  const fd = new FormData();
  files.forEach(f => fd.append("dateien", f));
  $("#import-status").textContent = `${files.length} Datei(en) werden gelesen …`;
  $("#import-ergebnis").innerHTML = "";
  try {
    const res = await fetch("api/import/analyse", { method: "POST", body: fd });
    if (!res.ok) throw new Error(`Fehler ${res.status}`);
    imp.daten = await res.json();
    const nR = imp.daten.rechnungen.length, nA = imp.daten.angebote.length;
    $("#import-status").textContent = `${nR + nA} von ${files.length} Datei(en) erkannt`
      + ` (${nR} Rechnung${nR === 1 ? "" : "en"}, ${nA} Angebot${nA === 1 ? "" : "e"}).`;
    renderImport();
  } catch (e) {
    $("#import-status").textContent = "";
    toast("Import fehlgeschlagen: " + e.message, true);
  } finally {
    $("#import-dateien").value = "";
  }
}

function renderImport() {
  const d = imp.daten;
  const adr = k => esc([k.zusatz, k.strasse, [k.plz, k.ort].filter(Boolean).join(" ")].filter(Boolean).join(", "));
  const check = (grp, i, on) => `<input type="checkbox" data-grp="${grp}" data-i="${i}" ${on ? "checked" : ""}>`;

  $("#import-ergebnis").innerHTML = `
    ${d.fehler.length ? `<div class="import-fehler">
      <strong>Nicht lesbar:</strong>
      ${d.fehler.map(f => `<div>${esc(f.datei)} – ${esc(f.fehler)}</div>`).join("")}
      <div class="hint">Gescannte PDFs (Bilder ohne Text) können nicht ausgelesen werden.</div>
    </div>` : ""}

    <div class="import-block">
      <h3>Empfänger <span class="badge">${d.kunden.length}</span></h3>
      <table class="list"><tbody>
        ${d.kunden.map((k, i) => `<tr><td class="chk">${check("kunden", i, !k.vorhanden)}</td>
          <td>${esc(k.name)}<br><small>${adr(k)}</small></td>
          <td class="num">${k.vorhanden ? `<span class="tag">schon vorhanden</span>` : `<span class="tag neu">neu</span>`}</td></tr>`).join("")
          || `<tr><td class="hint">Keine Empfänger erkannt.</td></tr>`}
      </tbody></table>
    </div>

    <div class="import-block">
      <h3>Vorschläge für Rechnungsposten <span class="badge">${d.textbausteine.length}</span></h3>
      <p class="hint">Uhrzeiten wurden durch {von}/{bis} ersetzt. Preisangaben wurden entfernt. Name und Vorlage kannst du hier noch anpassen.</p>
      ${d.textbausteine.map((t, i) => `<div class="tb-vorschlag">
          ${check("textbausteine", i, true)}
          <div class="grow">
            <input class="tb-titel" data-i="${i}" value="${esc(t.titel)}">
            <textarea class="tb-text" data-i="${i}" rows="2">${esc(t.text)}</textarea>
          </div>
          <span class="tag">${t.anzahl}×</span>
        </div>`).join("") || `<p class="hint">Keine neuen Rechnungsposten – alle gibt es schon.</p>`}
    </div>

    ${d.rechnungen.length ? `<div class="import-block">
      <h3>Rechnungen in die Liste übernehmen <span class="badge">${d.rechnungen.length}</span></h3>
      <p class="hint">Optional: alte Rechnungen als Archiv in der Rechnungsliste anzeigen.
        Bereits vorhandene Nummern werden übersprungen.</p>
      <table class="list"><tbody>
        ${d.rechnungen.map((r, i) => `<tr><td class="chk">${check("rechnungen", i, !r.nummer_vorhanden)}</td>
          <td>${esc(r.nummer)}</td><td>${fmtDate(r.datum)}</td>
          <td>${esc(r.kunde.name)}<br><small>${esc(r.datei)}</small></td>
          <td class="num">${fmtEuro(r.gesamt)}${r.nummer_vorhanden ? `<br><span class="tag">Nr. vorhanden</span>` : ""}</td></tr>`).join("")}
      </tbody></table>
      <label class="inline"><input type="checkbox" id="import-bezahlt" checked> als bezahlt markieren</label>
    </div>` : ""}

    ${d.angebote.length ? `<div class="import-block">
      <h3>Angebote in die Angebotsliste übernehmen <span class="badge">${d.angebote.length}</span></h3>
      <p class="hint">Bereits vorhandene Angebotsnummern werden übersprungen. Angebote ohne Nummer bekommen beim
        Übernehmen die nächste freie Nummer.</p>
      <table class="list"><tbody>
        ${d.angebote.map((a, i) => `<tr><td class="chk">${check("angebote", i, !a.nummer_vorhanden)}</td>
          <td>${a.nummer ? esc(a.nummer) : `<span class="tag neu">neue Nr.</span>`}</td><td>${fmtDate(a.datum)}</td>
          <td>${esc(a.kunde.name)}<br><small>${esc(a.datei)}${a.gueltig_bis ? ` · gültig bis ${fmtDate(a.gueltig_bis)}` : ""}</small></td>
          <td class="num">${fmtEuro(a.gesamt)}${a.nummer_vorhanden ? `<br><span class="tag">Nr. vorhanden</span>` : ""}</td></tr>`).join("")}
      </tbody></table>
      <label class="inline">Status der übernommenen Angebote:
        <select id="import-angebot-status" class="status-select">
          <option value="offen">offen</option><option value="angenommen">angenommen</option><option value="abgelehnt">abgelehnt</option>
        </select>
      </label>
    </div>` : ""}

    <div class="actions">
      <button type="button" class="secondary" id="import-abbrechen">Verwerfen</button>
      <button type="button" id="import-ok">Ausgewählte übernehmen</button>
    </div>`;

  $("#import-abbrechen").addEventListener("click", () => {
    imp.daten = null;
    $("#import-ergebnis").innerHTML = "";
    $("#import-status").textContent = "";
  });
  $("#import-ok").addEventListener("click", uebernehmeImport);
}

async function uebernehmeImport() {
  const d = imp.daten;
  const sel = grp => $$(`#import-ergebnis input[data-grp="${grp}"]:checked`).map(c => Number(c.dataset.i));
  const body = {
    kunden: sel("kunden").map(i => d.kunden[i]),
    textbausteine: sel("textbausteine").map(i => ({
      titel: $(`.tb-titel[data-i="${i}"]`).value,
      text: $(`.tb-text[data-i="${i}"]`).value,
    })),
    rechnungen: sel("rechnungen").map(i => d.rechnungen[i]),
    bezahlt: $("#import-bezahlt")?.checked ?? true,
    angebote: sel("angebote").map(i => d.angebote[i]),
    angebot_status: $("#import-angebot-status")?.value || "offen",
  };
  try {
    const r = await api("import/uebernehmen", { method: "POST", body });
    toast(`Übernommen: ${r.kunden} Empfänger, ${r.textbausteine} Rechnungsposten, ${r.rechnungen} Rechnungen, ${r.angebote} Angebote`);
    imp.daten = null;
    $("#import-ergebnis").innerHTML = "";
    $("#import-status").textContent = "";
    $("#import").classList.add("hidden");
    await loadLookups();
    await loadListe();
    state.angebote = await api("angebote");
    if (!state.editId) $("#r-nummer").value = (await api(istAngebot() ? "angebote/naechste-nummer" : "rechnungen/naechste-nummer")).nummer;
    if (r.angebote && !r.rechnungen) showTab("angebote");   // nur Angebote übernommen → gleich dorthin
  } catch (e) { toast(e.message, true); }
}

// ---------- Startseite ----------

const MONATE = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August",
  "September", "Oktober", "November", "Dezember"];

$("#tab-start").addEventListener("click", e => {
  const ziel = e.target.closest("[data-goto]");
  if (ziel) {
    e.preventDefault();
    const tab = ziel.dataset.goto;
    if (tab === "import") {
      oeffneImport();
    } else if (tab === "neu") {
      neueRechnung();
    } else if (tab === "angebot-neu") {
      neuesAngebot();
    } else {
      showTab(tab);
      if (tab === "kunden") setTimeout(() => $("#tab-kunden [name=name]")?.focus(), 100);
    }
    return;
  }
  const al = e.target.closest("a.start-alink");
  if (al) {
    e.preventDefault();
    return loadAngebotIntoForm(state.angebote.find(a => a.id === Number(al.dataset.id)));
  }
  const rl = e.target.closest("a.start-rlink");
  if (rl) {
    e.preventDefault();
    loadIntoForm(state.rechnungen.find(r => r.id === Number(rl.dataset.id)));
  }
});

async function renderStart() {
  const jetzt = new Date();
  const h = jetzt.getHours();
  const vorname = (state.absender?.name || "").trim().split(/\s+/)[0];
  const gruss = h < 11 ? "Guten Morgen" : h < 18 ? "Hallo" : "Guten Abend";
  $("#start-gruss").textContent = vorname ? `${gruss}, ${vorname}!` : `${gruss}!`;
  $("#start-datum").textContent = jetzt.toLocaleDateString("de-DE",
    { weekday: "long", day: "numeric", month: "long", year: "numeric" });

  try {
    [state.rechnungen, state.angebote] = await Promise.all([api("rechnungen"), api("angebote")]);
  } catch (e) { return toast("Laden fehlgeschlagen: " + e.message, true); }
  const alle = state.rechnungen;

  // Offene Angebote (Kurzfassung)
  const offeneAng = offeneAngebote();
  const gueltigeAng = offeneAng.filter(a => a.rest === null || a.rest >= 0);
  $("#start-angebote").innerHTML = offeneAng.length ? `
    <div class="stat-gross">${fmtEuro(gueltigeAng.reduce((s, a) => s + a.gesamt, 0))}<small>${gueltigeAng.length} noch gültige${
      gueltigeAng.length === 1 ? "s Angebot" : " Angebote"}${offeneAng.length > gueltigeAng.length
      ? ` · ${offeneAng.length - gueltigeAng.length} abgelaufen` : ""}</small></div>
    <ul class="mini-liste">${offeneAng.slice(0, 4).map(a => `<li>
      <div class="ml-text"><a href="#" class="start-alink" data-id="${a.id}">${esc(angebotName(a))}</a>
        <small>${esc(a.kunde.name)} · angeboten am ${fmtDate(a.datum)}</small></div>
      <span class="num">${fmtEuro(a.gesamt)}</span>${restBadge(a)}</li>`).join("")}</ul>
    ${offeneAng.length > 4 ? `<p class="hint">+ ${offeneAng.length - 4} weitere</p>` : ""}`
    : `<p class="hint">Keine offenen Angebote.</p>`;

  // Offene Rechnungen (Kurzfassung)
  const offen = alle.filter(r => !r.bezahlt).map(r => ({ ...r, ziel: zahlungsziel(r) }))
    .sort((a, b) => (a.ziel ? a.ziel.faellig : Infinity) - (b.ziel ? b.ziel.faellig : Infinity));
  const summeOffen = offen.reduce((s, r) => s + r.gesamt, 0);
  $("#start-offen").innerHTML = offen.length ? `
    <div class="stat-gross">${fmtEuro(summeOffen)}<small>${offen.length} offene Rechnung${offen.length === 1 ? "" : "en"}</small></div>
    <ul class="mini-liste">${offen.slice(0, 4).map(r => `<li>
      <div class="ml-text"><a href="#" class="start-rlink" data-id="${r.id}">${esc(rechnungsName(r))}</a>
        <small>${esc(r.kunde.name)}</small></div>
      <span class="num">${fmtEuro(r.gesamt)}</span>${fristBadge(r.ziel)}</li>`).join("")}</ul>
    ${offen.length > 4 ? `<p class="hint">+ ${offen.length - 4} weitere</p>` : ""}`
    : `<p class="hint">Keine offenen Rechnungen – alles bezahlt.</p>`;

  // Umsatz nach Rechnungsdatum
  const jahr = String(jetzt.getFullYear());
  const monat = `${jahr}-${String(jetzt.getMonth() + 1).padStart(2, "0")}`;
  const vorjahr = String(jetzt.getFullYear() - 1);
  const summeVon = praefix => alle.filter(r => r.datum.startsWith(praefix)).reduce((s, r) => s + r.gesamt, 0);
  const anzahlVon = praefix => alle.filter(r => r.datum.startsWith(praefix)).length;
  $("#start-umsatz").innerHTML = [
    [`${MONATE[jetzt.getMonth()]} ${jahr}`, summeVon(monat), anzahlVon(monat)],
    [`Jahr ${jahr}`, summeVon(jahr), anzahlVon(jahr)],
    [`Jahr ${vorjahr}`, summeVon(vorjahr), anzahlVon(vorjahr)],
  ].map(([titel, summe, n]) => `<div class="stat-zeile"><span>${titel}</span>
      <strong>${fmtEuro(summe)}</strong><small>${n} Rechnung${n === 1 ? "" : "en"}</small></div>`).join("");

  // Letzte Rechnungen
  const letzte = [...alle].sort((a, b) => b.datum.localeCompare(a.datum) || b.nummer.localeCompare(a.nummer, "de", { numeric: true })).slice(0, 5);
  $("#start-letzte").innerHTML = letzte.map(r => `<li>
      <div class="ml-text"><a href="#" class="start-rlink" data-id="${r.id}">${esc(rechnungsName(r))}</a>
        <small>${esc(r.kunde.name)} · ${fmtDate(r.datum)}</small></div>
      <span class="num">${fmtEuro(r.gesamt)}</span>
      ${r.bezahlt ? `<span class="frist gruen">bezahlt</span>` : `<span class="frist neutral">offen</span>`}</li>`).join("")
    || `<li class="leer">Noch keine Rechnungen.</li>`;

  // Hinweise, die die App selbst erkennt
  const hinweise = [];
  if (state.absender && !state.absender.vollstaendig) {
    hinweise.push(["warn", `Absenderdaten fehlen – bitte unter <a href="#" class="zu-einstellungen">⚙ Einstellungen</a> eintragen.`]);
  }
  for (const r of offen.filter(r => r.ziel && r.ziel.rest < 0)) {
    hinweise.push(["rot", `<a href="#" class="start-rlink" data-id="${r.id}">${esc(rechnungsName(r))}</a> ist seit ${-r.ziel.rest} ${-r.ziel.rest === 1 ? "Tag" : "Tagen"} überfällig (${esc(r.kunde.name)}, ${fmtEuro(r.gesamt)}).`]);
  }
  for (const r of offen.filter(r => r.ziel && r.ziel.rest === 0)) {
    hinweise.push(["gelb", `<a href="#" class="start-rlink" data-id="${r.id}">${esc(rechnungsName(r))}</a> ist heute fällig.`]);
  }
  const angHinweise = [];
  for (const a of offeneAng.filter(a => a.rest !== null && a.rest >= 0 && a.rest <= 3)) {
    angHinweise.push(["gelb", `Angebot <a href="#" class="start-alink" data-id="${a.id}">${esc(angebotName(a))}</a> (${esc(a.kunde.name)}) `
      + (a.rest === 0 ? "läuft heute ab." : `läuft in ${a.rest} ${a.rest === 1 ? "Tag" : "Tagen"} ab.`)]);
  }
  $("#start-hinweise").innerHTML = hinweise.map(([art, text]) => `<li class="${art}">${text}</li>`).join("");
  $("#start-hinweise").classList.toggle("hidden", !hinweise.length);
  $("#start-ang-hinweise").innerHTML = angHinweise.map(([art, text]) => `<li class="${art}">${text}</li>`).join("");
  $("#start-ang-hinweise").classList.toggle("hidden", !angHinweise.length);
}

// ---------- Start ----------

(async () => {
  try {
    await ladeAbsender();
    pruefeUpdate();   // läuft im Hintergrund
    await loadLookups();
    await resetForm();
    await renderStart();
  } catch (e) {
    toast("Laden fehlgeschlagen: " + e.message, true);
  }
})();
