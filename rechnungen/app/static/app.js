/* Rechnungen – Frontend. Alle URLs relativ, damit es hinter dem HA-Ingress-Pfad funktioniert. */
"use strict";

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

const state = {
  textbausteine: [],
  zahlungsbedingungen: [],
  kundeId: null,      // ID des gewählten Bestandskunden (null = neuer Kunde)
  editId: null,       // ID der Rechnung, die gerade bearbeitet wird
  rechnungen: [],
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
  $$("nav button").forEach(b => b.classList.toggle("active", b.dataset.tab === name));
  $$(".tab").forEach(s => s.classList.toggle("active", s.id === "tab-" + name));
  document.body.classList.toggle("auf-start", name === "start");
  if (name === "liste") loadListe();
  if (name === "start") renderStart();
  const stamm = $(`#tab-${name}[data-stamm]`);
  if (stamm) renderStamm(stamm.dataset.stamm);
}
$$("nav button").forEach(b => b.addEventListener("click", () => showTab(b.dataset.tab)));
$("#logo").addEventListener("click", () => showTab("start"));

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
  sel.innerHTML = state.zahlungsbedingungen
    .map(z => `<option value="${esc(z.text)}">${esc(z.titel)}</option>`).join("");
  if (current && state.zahlungsbedingungen.some(z => z.text === current)) sel.value = current;
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
    nummer: $("#r-nummer").value.trim(),
    datum: $("#r-datum").value,
    zahlungsbedingung: $("#r-zahlung").value,
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
  fillKunde({});
  $("#r-datum").value = today();
  $("#r-nummer").value = (await api("rechnungen/naechste-nummer")).nummer;
  $("#r-zahlung").selectedIndex = 0;
  updateZahlungText();
  $("#positionen").innerHTML = "";
  addPosition();
  $("#btn-speichern").textContent = "Rechnung speichern & PDF öffnen";
}

function loadIntoForm(inv) {
  state.editId = inv.id;
  fillKunde({ ...inv.kunde, id: inv.kunde_id });
  $("#r-nummer").value = inv.nummer;
  $("#r-datum").value = inv.datum;
  const sel = $("#r-zahlung");
  if (![...sel.options].some(o => o.value === inv.zahlungsbedingung)) {
    sel.add(new Option("(gespeicherter Text)", inv.zahlungsbedingung));
  }
  sel.value = inv.zahlungsbedingung;
  updateZahlungText();
  $("#positionen").innerHTML = "";
  inv.positionen.forEach(p => addPosition(p));
  $("#btn-speichern").textContent = `Rechnung ${inv.nummer} aktualisieren & PDF öffnen`;
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
  openPdf(async () => {
    checkPlaceholders(data);
    const res = state.editId
      ? await api("rechnungen/" + state.editId, { method: "PUT", body: data })
      : await api("rechnungen", { method: "POST", body: data });
    state.editId = res.id;
    $("#btn-speichern").textContent = `Rechnung ${data.nummer} aktualisieren & PDF öffnen`;
    toast(`Rechnung ${data.nummer} gespeichert` + (res.datei ? ` → ${res.datei.split("/").pop()}` : ""));
    return api(`rechnungen/${res.id}/pdf`);
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
        ? ` <span class="pl-chip" title="An Paperless übertragen am ${fmtDate(r.paperless_am.slice(0, 10))}">Paperless ✓</span>` : ""}</td>
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
  const ids = [...auswahl];
  if (!ids.length) return;
  if (!state.absender?.paperless) {
    return toast("Paperless ist noch nicht eingerichtet: In Home Assistant unter Einstellungen → Apps → "
      + "DJ Office Studio → Konfiguration „paperless_eingangsordner“ eintragen und die App neu starten.", true);
  }
  const schon = state.rechnungen.filter(r => auswahl.has(r.id) && r.paperless_am);
  if (schon.length && !confirm(`${schon.length === 1 ? `${rechnungsName(schon[0])} wurde` : `${schon.length} der Rechnungen wurden`}`
      + " bereits an Paperless übertragen. Trotzdem erneut senden? (Paperless legt dann ein zweites Dokument an.)")) return;

  const btn = e.currentTarget;
  btn.disabled = true;
  btn.textContent = `Sende ${ids.length} …`;
  try {
    const res = await api("paperless", { method: "POST", body: { ids } });
    await loadListe();
    res.ok.forEach(id => auswahl.delete(id));
    renderListe();
    if (res.fehler.length) {
      const nicht = ids.length - res.ok.length;
      toast(`${res.ok.length ? `${res.ok.length} übertragen, ` : ""}${nicht} nicht übertragen: ${res.fehler[0].error}`, true);
    } else {
      toast(`${res.ok.length} Rechnung${res.ok.length === 1 ? "" : "en"} in den Paperless-Eingang gelegt – Paperless verarbeitet sie jetzt.`);
    }
  } catch (err) {
    toast(err.message, true);
  } finally {
    btn.disabled = false;
    btn.textContent = "⇪ An Paperless senden";
  }
});

$("#btn-auswahl-download").addEventListener("click", () => {
  if (!auswahl.size) return;
  // Normaler Link-Download (Server sendet Content-Disposition: attachment)
  const a = document.createElement("a");
  a.href = `api/rechnungen/download?ids=${[...auswahl].join(",")}`;
  a.download = "";
  document.body.appendChild(a);
  a.click();
  a.remove();
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
    if (btn.dataset.act === "del" && confirm(`${rechnungsName(inv)} wirklich löschen?`)) {
      await api("rechnungen/" + id, { method: "DELETE" });
      if (state.editId === id) resetForm();
      await loadListe();
      toast(`${rechnungsName(inv)} gelöscht`);
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

// ---------- Import alter Rechnungen ----------

const imp = { daten: null };

$("#btn-import").addEventListener("click", () => {
  $("#import").classList.toggle("hidden");
  window.scrollTo(0, 0);
});
$("#import-zu").addEventListener("click", () => $("#import").classList.add("hidden"));

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
    $("#import-status").textContent =
      `${imp.daten.rechnungen.length} von ${files.length} Datei(en) erkannt.`;
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

    <div class="import-block">
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
    </div>

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
    bezahlt: $("#import-bezahlt").checked,
  };
  try {
    const r = await api("import/uebernehmen", { method: "POST", body });
    toast(`Übernommen: ${r.kunden} Empfänger, ${r.textbausteine} Rechnungsposten, ${r.rechnungen} Rechnungen`);
    imp.daten = null;
    $("#import-ergebnis").innerHTML = "";
    $("#import-status").textContent = "";
    $("#import").classList.add("hidden");
    await loadLookups();
    await loadListe();
    if (!state.editId) $("#r-nummer").value = (await api("rechnungen/naechste-nummer")).nummer;
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
      showTab("liste");
      $("#import").classList.remove("hidden");
      window.scrollTo(0, 0);
    } else {
      showTab(tab);
      if (tab === "kunden") setTimeout(() => $("#tab-kunden [name=name]")?.focus(), 100);
    }
    return;
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
    state.rechnungen = await api("rechnungen");
  } catch (e) { return toast("Laden fehlgeschlagen: " + e.message, true); }
  const alle = state.rechnungen;

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
    hinweise.push(["warn", "Absenderdaten fehlen – in Home Assistant unter Apps → DJ Office Studio → Konfiguration eintragen."]);
  }
  for (const r of offen.filter(r => r.ziel && r.ziel.rest < 0)) {
    hinweise.push(["rot", `<a href="#" class="start-rlink" data-id="${r.id}">${esc(rechnungsName(r))}</a> ist seit ${-r.ziel.rest} ${-r.ziel.rest === 1 ? "Tag" : "Tagen"} überfällig (${esc(r.kunde.name)}, ${fmtEuro(r.gesamt)}).`]);
  }
  for (const r of offen.filter(r => r.ziel && r.ziel.rest === 0)) {
    hinweise.push(["gelb", `<a href="#" class="start-rlink" data-id="${r.id}">${esc(rechnungsName(r))}</a> ist heute fällig.`]);
  }
  $("#start-hinweise").innerHTML = hinweise.map(([art, text]) => `<li class="${art}">${text}</li>`).join("");
  $("#start-hinweise").classList.toggle("hidden", !hinweise.length);
}

// ---------- Start ----------

(async () => {
  try {
    const abs = await api("absender");
    state.absender = abs;
    $("#warnung").classList.toggle("hidden", abs.vollstaendig);
    await loadLookups();
    await resetForm();
    await renderStart();
  } catch (e) {
    toast("Laden fehlgeschlagen: " + e.message, true);
  }
})();
