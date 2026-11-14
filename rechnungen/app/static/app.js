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
  if (name === "liste") loadListe();
  const stamm = $(`#tab-${name}[data-stamm]`);
  if (stamm) renderStamm(stamm.dataset.stamm);
}
$$("nav button").forEach(b => b.addEventListener("click", () => showTab(b.dataset.tab)));

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
  sel.innerHTML = `<option value="">Freitext</option><optgroup label="Textbausteine">` +
    state.textbausteine.map(t => `<option value="${t.id}">${esc(t.titel)}</option>`).join("") + `</optgroup>`;
  sel.value = current;
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

  $(".tb", pos).addEventListener("change", e => {
    pos._tb = state.textbausteine.find(t => String(t.id) === e.target.value) || null;
    $(".calc", pos).classList.toggle("hidden", !(pos._tb && hasTimes(pos._tb.text)));
    $(".von", pos).value = $(".bis", pos).value = "";
    $(".stunden", pos).textContent = "";
    if (pos._tb) applyTb(pos);
    else { $(".beschreibung", pos).value = ""; $(".beschreibung", pos).focus(); }
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
    toast(`Rechnung ${data.nummer} gespeichert` + (res.datei ? ` (${res.datei})` : ""));
    return api(`rechnungen/${res.id}/pdf`);
  });
});

// ---------- Rechnungsliste ----------

async function loadListe() {
  state.rechnungen = await api("rechnungen");
  renderListe();
}

function renderListe() {
  const q = $("#liste-suche").value.trim().toLowerCase();
  const list = state.rechnungen.filter(r => !q ||
    [r.nummer, r.kunde.name, r.kunde.ort, ...r.positionen.map(p => p.beschreibung)]
      .join(" ").toLowerCase().includes(q));
  $("#liste-body").innerHTML = list.map(r => `
    <tr data-id="${r.id}">
      <td>${esc(r.nummer)}</td>
      <td>${fmtDate(r.datum)}</td>
      <td>${esc(r.kunde.name)}<br><small>${esc(r.kunde.ort)}</small></td>
      <td class="num">${fmtEuro(r.gesamt)}</td>
      <td><input type="checkbox" class="bezahlt" ${r.bezahlt ? "checked" : ""} style="width:auto"></td>
      <td class="btns">
        <button class="small secondary" data-act="pdf">PDF</button>
        <button class="small secondary" data-act="edit">Bearbeiten</button>
        <button class="small danger" data-act="del">Löschen</button>
      </td>
    </tr>`).join("") || `<tr><td colspan="6" class="hint">Keine Rechnungen gefunden.</td></tr>`;
  const sum = list.reduce((s, r) => s + r.gesamt, 0);
  const offen = list.filter(r => !r.bezahlt).reduce((s, r) => s + r.gesamt, 0);
  $("#liste-summe").textContent = list.length
    ? `${list.length} Rechnung(en) · Summe ${fmtEuro(sum)} · offen ${fmtEuro(offen)}` : "";
}
$("#liste-suche").addEventListener("input", renderListe);

$("#liste-body").addEventListener("change", async e => {
  if (!e.target.classList.contains("bezahlt")) return;
  const id = Number(e.target.closest("tr").dataset.id);
  try {
    await api(`rechnungen/${id}/bezahlt`, { method: "PATCH", body: { bezahlt: e.target.checked } });
    state.rechnungen.find(r => r.id === id).bezahlt = e.target.checked;
    renderListe();
  } catch (err) { toast(err.message, true); e.target.checked = !e.target.checked; }
});

$("#liste-body").addEventListener("click", async e => {
  const btn = e.target.closest("button[data-act]");
  if (!btn) return;
  const id = Number(btn.closest("tr").dataset.id);
  const inv = state.rechnungen.find(r => r.id === id);
  if (btn.dataset.act === "pdf") window.open(`api/rechnungen/${id}/pdf`, "_blank");
  if (btn.dataset.act === "edit") loadIntoForm(inv);
  if (btn.dataset.act === "del" && confirm(`Rechnung ${inv.nummer} wirklich löschen?`)) {
    await api("rechnungen/" + id, { method: "DELETE" });
    if (state.editId === id) resetForm();
    loadListe();
  }
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
    titel: "Textbausteine", einzahl: "Textbaustein",
    hinweis: "Platzhalter {von} und {bis} im Text werden im Editor durch Uhrzeiten ersetzt. " +
      "Der Preis wird bei jeder Rechnung individuell eingetragen.",
    felder: [["titel", "Titel"], ["text", "Text", "textarea"]],
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

// ---------- Start ----------

(async () => {
  try {
    const abs = await api("absender");
    $("#warnung").classList.toggle("hidden", abs.vollstaendig);
    await loadLookups();
    await resetForm();
  } catch (e) {
    toast("Laden fehlgeschlagen: " + e.message, true);
  }
})();
