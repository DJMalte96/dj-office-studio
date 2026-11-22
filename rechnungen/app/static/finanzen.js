/* DJ Office Studio – Finanzen (seit 1.1): Ausgaben mit Belegen.
   Nutzt die Hilfsfunktionen aus app.js ($, $$, api, toast, esc, fmtEuro, fmtDate, zeigePdf, ladeHerunter, appFenster). */
"use strict";

const fin = {
  kategorien: [],
  ausgaben: [],
  jahr: String(new Date().getFullYear()),
  ansicht: localStorage.getItem("ausgaben-ansicht") || "gruppiert",
  offen: new Set(),          // aufgeklappte Gruppen (Monat)
  warteschlange: [],         // IDs, die nacheinander geprüft werden
  aktuell: null,             // Ausgabe im Prüfen-Formular (null = neue ohne Beleg)
};

const euro2 = v => (Number(v) || 0).toLocaleString("de-DE", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + " €";
const katName = id => (fin.kategorien.find(k => k.id === id) || {}).name || id;
const TYP_KURZ = { pdf: "PDF", mail: "MAIL", msg: "MAIL", bild: "FOTO", unbekannt: "DATEI" };

async function ladeKategorien() {
  if (fin.kategorien.length) return;
  fin.kategorien = await api("finanzen/kategorien");
  const opts = fin.kategorien.map(k => `<option value="${k.id}">${esc(k.name)}</option>`).join("");
  $("#beleg-form").elements.kategorie.innerHTML = opts;
  $("#ausgaben-kategorie").innerHTML = `<option value="">Alle Kategorien</option>` + opts;
}

/* Wird von showTab() in app.js aufgerufen */
function finanzenTab(name) {
  if (name === "ausgaben") { ladeAusgaben(); ordnerPruefen(); }
  if (name === "fahrten") ladeFahrten();
  if (name === "anschaffungen") ladeAnlagen();
  if (name === "finanzen") ladeUebersicht();
  if (name === "euer") ladeEuer();
}

async function ladeAusgaben() {
  try {
    await ladeKategorien();
    fin.ausgaben = await api(`ausgaben?jahr=${fin.jahr}`);
  } catch (e) { return toast("Laden fehlgeschlagen: " + e.message, true); }
  const jahre = [...new Set([String(new Date().getFullYear()), fin.jahr, ...fin.ausgaben.map(a => a.jahr).filter(Boolean)])].sort().reverse();
  $("#ausgaben-jahr").innerHTML = jahre.map(j => `<option${j === fin.jahr ? " selected" : ""}>${j}</option>`).join("");
  renderAusgaben();
  ocrListeNachladen();
}

function renderAusgaben() {
  const neu = fin.ausgaben.filter(a => a.status === "neu");
  $("#ausgaben-neu-karte").classList.toggle("hidden", !neu.length);
  $("#ausgaben-neu-anzahl").textContent = `${neu.length} Beleg${neu.length === 1 ? "" : "e"}`;
  $("#ausgaben-neu").innerHTML = neu.map(a => {
    const e = a.erkannt || {};
    const erkannt = [e.betrag != null && "Gesamt", e.ust_betrag != null && "MwSt.", e.kategorie && "Kategorie"].filter(Boolean);
    const info = ocrLaeuft(a) ? "Text wird gelesen …"
      : erkannt.length ? `erkannt: ${erkannt.join(", ")}` : "nichts erkannt – bitte Werte eintragen";
    return `<div class="neu-beleg" data-id="${a.id}">
      <div class="datei-icon">${TYP_KURZ[a.beleg_typ] || "DATEI"}</div>
      <div class="was"><strong>${esc(a.lieferant || a.beleg_name)}</strong>
        <small>${esc(a.beschreibung || a.beleg_name)} · ${fmtDate(a.belegdatum)} · ${info}</small></div>
      <div class="betrag">${a.betrag != null ? euro2(a.betrag) : "– €"}</div>
      <button type="button" class="small${a === neu[0] ? "" : " secondary"}" data-act="pruefen">${a.betrag != null || ocrLaeuft(a) ? "Prüfen" : "Eintragen"}</button>
    </div>`;
  }).join("");

  // Liste der übernommenen Ausgaben
  const q = $("#ausgaben-suche").value.trim().toLowerCase();
  const kat = $("#ausgaben-kategorie").value;
  $$("#ausgaben-ansicht button").forEach(b => b.classList.toggle("an", b.dataset.ansicht === fin.ansicht));
  const ok = fin.ausgaben.filter(a => a.status === "ok" && (!kat || a.kategorie === kat)
    && (!q || [a.lieferant, a.beschreibung, a.notiz, a.kategorie_name].join(" ").toLowerCase().includes(q)));
  const zeile = (a, kind = false) => `<tr data-id="${a.id}"${kind ? ' class="kind"' : ""}>
      <td>${fmtDate(a.bezahlt_am || a.belegdatum)}</td><td>${esc(a.lieferant)}</td>
      <td>${esc(a.beschreibung)}${a.privatanteil ? ` <small class="muted">(${a.privatanteil} % privat)</small>` : ""}</td>
      <td><span class="chip k-${a.kategorie}">${esc(a.kategorie_name)}</span></td>
      <td class="num">${euro2(a.betrag)}</td>
      <td>${a.beleg_datei ? `<a href="#" class="beleg-link" data-act="beleg" title="Beleg öffnen">📎</a>`
        : `<span class="muted" title="${esc(a.notiz || "ohne Beleg")}">—</span>`}</td>
      <td class="btns"><button type="button" class="small secondary" data-act="bearbeiten" title="Bearbeiten">✎</button></td>
    </tr>`;
  let html = "";
  if (fin.ansicht === "gruppiert" && !q) {
    // Musikkäufe je Monat zu einer Zeile zusammenfassen (aufklappbar), alles andere einzeln
    const gruppen = {};
    const reihen = [];
    for (const a of ok) {
      const monat = (a.bezahlt_am || a.belegdatum || "").slice(0, 7);
      if (a.kategorie === "musik") {
        if (!gruppen[monat]) { gruppen[monat] = []; reihen.push({ gruppe: monat }); }
        gruppen[monat].push(a);
      } else reihen.push({ a });
    }
    html = reihen.map(r => {
      if (r.a) return zeile(r.a);
      const liste = gruppen[r.gruppe];
      if (liste.length === 1) return zeile(liste[0]);
      const shops = {};
      liste.forEach(a => { shops[a.lieferant] = (shops[a.lieferant] || 0) + 1; });
      const offen = fin.offen.has(r.gruppe);
      const [y, m] = r.gruppe.split("-");
      return `<tr class="gruppe" data-gruppe="${r.gruppe}"><td>${MONATE[Number(m) - 1].slice(0, 3)}. ${y}</td><td>Musik-Käufe</td>
        <td><small>${Object.entries(shops).map(([s, n]) => `${esc(s)} ${n}×`).join(" · ")} – ${offen ? "zuklappen ▾" : "aufklappen ▸"}</small></td>
        <td><span class="chip k-musik">${esc(katName("musik"))}</span></td><td class="num">${euro2(liste.reduce((s, a) => s + a.betrag, 0))}</td><td></td><td></td></tr>`
        + (offen ? liste.map(a => zeile(a, true)).join("") : "");
    }).join("");
  } else {
    html = ok.map(a => zeile(a)).join("");
  }
  $("#ausgaben-body").innerHTML = html
    || `<tr><td colspan="7" class="hint">${q || kat ? "Keine Treffer." : `Noch keine Ausgaben für ${fin.jahr} – Belege oben hineinziehen.`}</td></tr>`;
  const summe = ok.reduce((s, a) => s + (a.betrag || 0), 0);
  $("#ausgaben-summe").textContent = ok.length ? `${fin.jahr}: ${ok.length} Ausgabe${ok.length === 1 ? "" : "n"} · Summe ${euro2(summe)}` : "";
}

// ---------- Hochladen ----------

// Große Mengen werden in Paketen hochgeladen (Server-Grenzen: 1000 Dateien bzw. 100 MB je Anfrage).
const PAKET_DATEIEN = 50, PAKET_BYTES = 20 * 1024 * 1024, MAX_DATEI = 95 * 1024 * 1024;
let hochladenLaeuft = false;

function inPakete(dateien) {
  const pakete = [];
  let paket = [], groesse = 0;
  for (const f of dateien) {
    if (paket.length && (paket.length >= PAKET_DATEIEN || groesse + f.size > PAKET_BYTES)) {
      pakete.push(paket); paket = []; groesse = 0;
    }
    paket.push(f); groesse += f.size;
  }
  if (paket.length) pakete.push(paket);
  return pakete;
}

async function paketHochladen(paket) {
  const fd = new FormData();
  paket.forEach(f => fd.append("dateien", f));
  const res = await fetch("api/ausgaben/belege", { method: "POST", body: fd });
  let d = null;
  try { d = await res.json(); } catch { /* z. B. HTML-Fehlerseite */ }
  if (!res.ok || !d) throw new Error((d && d.error) || `Fehler ${res.status}`);
  return d;
}

async function belegeHochladen(dateien) {
  dateien = [...dateien];
  if (!dateien.length) return;
  if (hochladenLaeuft) { toast("Es wird gerade noch hochgeladen – bitte kurz warten.", true); return; }
  hochladenLaeuft = true;
  const status = $("#beleg-status");
  const gesamt = { neu: 0, doppelt: [], fehler: [] };
  const zuGross = dateien.filter(f => f.size > MAX_DATEI);
  zuGross.forEach(f => gesamt.fehler.push({ datei: f.name, fehler: "größer als 95 MB" }));
  const pakete = inPakete(dateien.filter(f => f.size <= MAX_DATEI));
  const anzahl = dateien.length - zuGross.length;
  let fertig = 0, abbruch = null;
  try {
    for (const paket of pakete) {
      status.textContent = anzahl === 1 ? "1 Beleg wird gelesen …"
        : pakete.length === 1 ? `${anzahl} Belege werden gelesen …` : `${fertig} von ${anzahl} Belegen gelesen …`;
      try {
        const d = await paketHochladen(paket);
        gesamt.neu += d.neu.length;
        gesamt.doppelt.push(...d.doppelt);
        gesamt.fehler.push(...d.fehler);
      } catch (e) { abbruch = e; break; }
      fertig += paket.length;
    }
    const teile = [];
    if (gesamt.neu) teile.push(`${gesamt.neu} neu`);
    if (gesamt.doppelt.length) {
      const namen = gesamt.doppelt.length <= 5 ? ` (${gesamt.doppelt.map(x => x.datei).join(", ")})` : "";
      teile.push(`${gesamt.doppelt.length} schon vorhanden${namen}`);
    }
    if (gesamt.fehler.length) {
      const namen = gesamt.fehler.length <= 3 ? ` (${gesamt.fehler.map(x => x.datei).join(", ")})` : "";
      teile.push(`${gesamt.fehler.length} nicht lesbar${namen}`);
    }
    if (abbruch) {
      const rest = anzahl - fertig;
      toast(`Hochladen abgebrochen: ${abbruch.message}. ${teile.length ? teile.join(" · ") + " · " : ""}`
        + `${rest} Datei${rest === 1 ? "" : "en"} nicht verarbeitet – einfach noch einmal hineinziehen, Doppelte werden erkannt.`, true);
    } else {
      toast(teile.join(" · ") || "Nichts hochgeladen", !!(gesamt.fehler.length && !gesamt.neu));
    }
    if (fertig) await ladeAusgaben();
  } finally {
    hochladenLaeuft = false;
    status.textContent = "oder klicken zum Auswählen";
  }
}

const drop = $("#beleg-drop");
drop.addEventListener("dragover", e => { e.preventDefault(); drop.classList.add("over"); });
drop.addEventListener("dragleave", () => drop.classList.remove("over"));
// Ordner (auch Apple-Mail-Export „….mbox“) werden durchsucht; Hilfsdateien wie table_of_contents bleiben draußen.
const BELEG_ENDUNG = /\.(pdf|eml|msg|mbox|jpe?g|png|heic|heif|webp)$/i;
const brauchbar = f => BELEG_ENDUNG.test(f.name) || f.name === "mbox";

function eintragLesen(eintrag) {
  if (eintrag.isFile) return new Promise(ok => eintrag.file(f => ok([f]), () => ok([])));
  if (!eintrag.isDirectory) return Promise.resolve([]);
  const leser = eintrag.createReader();
  return new Promise(ok => {
    const alle = [];
    const weiter = () => leser.readEntries(async teil => {
      if (!teil.length) return ok((await Promise.all(alle.map(eintragLesen))).flat());
      alle.push(...teil); weiter();           // readEntries liefert große Ordner in Häppchen
    }, () => ok([]));
    weiter();
  });
}

async function abgelegteDateien(dt) {
  const eintraege = [...(dt.items || [])].filter(i => i.kind === "file").map(i => i.webkitGetAsEntry && i.webkitGetAsEntry()).filter(Boolean);
  if (!eintraege.length || !eintraege.some(e => e.isDirectory)) return [...dt.files];
  return (await Promise.all(eintraege.map(eintragLesen))).flat().filter(f => !f.name.startsWith(".") && brauchbar(f));
}

drop.addEventListener("drop", async e => {
  e.preventDefault();
  drop.classList.remove("over");
  const dt = e.dataTransfer;
  const dateien = await abgelegteDateien(dt);
  if (dateien.length) return belegeHochladen(dateien);
  // Nichts angekommen – typisch beim Ziehen direkt aus Apple Mail (liefert dem Browser keine Datei)
  const ausMail = [...dt.types].some(t => /uri-list|text\/plain|message/i.test(t));
  hilfeMails(ausMail ? "Aus dem Mailprogramm ist keine Datei angekommen." : "Es ist keine Datei angekommen.");
});

function hilfeMails(grund) {
  $("#mail-hilfe-grund").textContent = grund;
  $("#mail-hilfe").hidden = false;
  $("#mail-hilfe").scrollIntoView({ block: "nearest", behavior: "smooth" });
}
$("#mail-hilfe-zu").addEventListener("click", () => { $("#mail-hilfe").hidden = true; });
$("#beleg-dateien").addEventListener("change", e => { belegeHochladen(e.target.files); e.target.value = ""; });

// ---------- Liste: Filter, Ansicht, Aktionen ----------

$("#ausgaben-suche").addEventListener("input", renderAusgaben);
$("#ausgaben-kategorie").addEventListener("change", renderAusgaben);
$("#ausgaben-jahr").addEventListener("change", e => { fin.jahr = e.target.value; ladeAusgaben(); });
$("#ausgaben-ansicht").addEventListener("click", e => {
  const b = e.target.closest("button[data-ansicht]");
  if (!b) return;
  fin.ansicht = b.dataset.ansicht;
  localStorage.setItem("ausgaben-ansicht", fin.ansicht);
  renderAusgaben();
});
$("#ausgaben-body").addEventListener("click", e => {
  const gruppe = e.target.closest("tr.gruppe");
  if (gruppe) {
    const g = gruppe.dataset.gruppe;
    if (fin.offen.has(g)) fin.offen.delete(g); else fin.offen.add(g);
    return renderAusgaben();
  }
  const tr = e.target.closest("tr[data-id]");
  const act = e.target.closest("[data-act]")?.dataset.act;
  if (!tr || !act) return;
  e.preventDefault();
  const id = Number(tr.dataset.id);
  if (act === "bearbeiten") oeffneBeleg(id);
  if (act === "beleg") belegOriginal(fin.ausgaben.find(a => a.id === id));
});
$("#ausgaben-neu").addEventListener("click", e => {
  const b = e.target.closest("button[data-act=pruefen]");
  if (b) { fin.warteschlange = []; oeffneBeleg(Number(b.closest("[data-id]").dataset.id)); }
});
$("#alle-pruefen").addEventListener("click", () => {
  const ids = fin.ausgaben.filter(a => a.status === "neu").map(a => a.id);
  fin.warteschlange = ids.slice(1);
  if (ids.length) oeffneBeleg(ids[0]);
});
$("#ausgabe-ohne-beleg").addEventListener("click", () => { fin.warteschlange = []; oeffneBeleg(null); });

function belegOriginal(a) {
  if (!a) return;
  const url = `api/ausgaben/${a.id}/beleg`;
  if (a.beleg_typ === "pdf") return zeigePdf(url);
  if (a.beleg_typ === "bild" && !appFenster()) return window.open(url, "_blank");
  ladeHerunter(url);   // Mails (.eml/.msg) und im App-Fenster auch Fotos: speichern bzw. mit dem Standardprogramm öffnen
}

// ---------- Prüfen / Bearbeiten ----------

async function oeffneBeleg(id) {
  await ladeKategorien();
  let a = null;
  if (id != null) {
    try { a = await api(`ausgaben/${id}`); } catch (e) { return toast(e.message, true); }
  }
  fin.aktuell = a;
  const f = $("#beleg-form");
  f.reset();
  // Rechnungen zum Zuordnen
  if (!state.rechnungen.length) { try { state.rechnungen = await api("rechnungen"); } catch (_) { /* egal */ } }
  f.elements.rechnung_id.innerHTML = `<option value="">– keine –</option>` + state.rechnungen
    .filter(r => !r.storno_von).slice(0, 80).map(r => `<option value="${r.id}">${esc(r.nummer)} – ${esc(r.kunde.name)}</option>`).join("");
  api("ausgaben/lieferanten").then(l => { $("#lieferanten-liste").innerHTML = l.map(n => `<option value="${esc(n)}">`).join(""); }).catch(() => {});

  const neu = !a || a.status === "neu";
  $("#beleg-titel").textContent = !a ? "Ausgabe ohne Beleg" : neu ? "Beleg prüfen" : "Ausgabe bearbeiten";
  const rest = fin.warteschlange.length;
  $("#beleg-fortschritt").textContent = neu && a ? (rest ? `danach noch ${rest} weitere${rest === 1 ? "r" : ""} Beleg${rest === 1 ? "" : "e"}` : "") : "";
  $("#beleg-speichern").textContent = !a || !neu ? "Speichern" : rest ? "✓ Übernehmen & nächster" : "✓ Übernehmen";
  $("#beleg-verwerfen").textContent = neu ? "Verwerfen" : "Löschen";
  $("#beleg-verwerfen").classList.toggle("hidden", !a);

  // Werte eintragen
  const w = a || { belegdatum: today(), kategorie: "sonstiges", privatanteil: 0 };
  for (const k of ["lieferant", "belegdatum", "bezahlt_am", "beschreibung", "kategorie", "notiz", "privatanteil"]) {
    if (f.elements[k]) f.elements[k].value = w[k] ?? "";
  }
  f.elements.betrag.value = w.betrag != null ? Number(w.betrag).toFixed(2).replace(".", ",") : "";
  f.elements.ust_satz.value = w.ust_satz ? String(Math.round(w.ust_satz)) : "";
  f.elements.rechnung_id.value = w.rechnung_id || "";
  const ohneBeleg = !a || !a.beleg_datei;
  f.elements.notiz.required = ohneBeleg;
  $("#notiz-hinweis").textContent = ohneBeleg ? "(Pflicht: warum gibt es keinen Beleg?)" : "(optional)";

  zeigeErkennung(a, neu);
  ocrImFormularVerfolgen();

  // Vorschau
  const v = $("#beleg-vorschau");
  if (!a || !a.beleg_datei) {
    v.innerHTML = `<div class="ohne-beleg"><b>Ohne Beleg</b><br>Für Ausgaben ohne Quittung (z. B. Parkautomat) bitte in der Notiz festhalten, warum es keinen Beleg gibt.</div>`;
    $("#beleg-original").textContent = "";
  } else {
    const url = `api/ausgaben/${a.id}/ansicht`;
    v.innerHTML = a.beleg_typ === "bild" ? `<img src="${url}" alt="Beleg" onerror="this.outerHTML='<div class=&quot;ohne-beleg&quot;>Für dieses Foto ist keine Vorschau möglich – bitte über „Original öffnen“ ansehen.</div>'">`
      : a.beleg_typ === "unbekannt" ? `<div class="ohne-beleg">Keine Vorschau für diesen Dateityp.</div>`
      : `<iframe src="${url}" title="Beleg" ${a.beleg_typ === "pdf" ? "" : 'sandbox=""'}></iframe>`;
    $("#beleg-original").innerHTML = `${a.beleg_typ === "mail" || a.beleg_typ === "msg" ? "Original-Mail" : "Original"} wird unverändert gespeichert · `
      + `<a href="#" id="beleg-original-link">Original öffnen</a>`;
  }
  showTab("beleg");
  window.scrollTo(0, 0);
  setTimeout(() => (f.elements.betrag.value ? f.querySelector("[type=submit]") : f.elements.betrag).focus(), 50);
}

document.addEventListener("click", e => {
  if (e.target.id !== "beleg-original-link") return;
  e.preventDefault();
  belegOriginal(fin.aktuell);
});

function naechsterOderListe() {
  const id = fin.warteschlange.shift();
  if (id != null) return oeffneBeleg(id);
  showTab("ausgaben");
}

$("#beleg-schliessen").addEventListener("click", () => { fin.warteschlange = []; showTab("ausgaben"); });

$("#beleg-form").addEventListener("submit", async e => {
  e.preventDefault();
  const f = e.target;
  const d = Object.fromEntries(["lieferant", "belegdatum", "bezahlt_am", "beschreibung", "kategorie", "notiz", "privatanteil",
    "betrag", "ust_satz", "rechnung_id"].map(k => [k, f.elements[k].value]));
  const a = fin.aktuell;
  try {
    if (!a) {
      await api("ausgaben", { method: "POST", body: d });
      toast(`Ausgabe ${d.lieferant} gespeichert`);
    } else {
      await api(`ausgaben/${a.id}`, { method: "PUT", body: { ...d, uebernehmen: a.status === "neu" } });
      toast(a.status === "neu" ? `${d.lieferant} übernommen` : `${d.lieferant} gespeichert`);
    }
    naechsterOderListe();
  } catch (err) { toast(err.message, true); }
});

$("#beleg-verwerfen").addEventListener("click", async () => {
  const a = fin.aktuell;
  if (!a) return;
  const frage = a.status === "neu" ? `Beleg „${a.beleg_name || a.lieferant}“ verwerfen?\n\nDie hochgeladene Datei wird gelöscht.`
    : `Ausgabe ${a.lieferant} (${euro2(a.betrag)}) löschen?\n\nDer Beleg wird mit gelöscht.`;
  if (!confirm(frage)) return;
  try {
    await api(`ausgaben/${a.id}`, { method: "DELETE" });
    toast(a.status === "neu" ? "Beleg verworfen" : "Ausgabe gelöscht");
    naechsterOderListe();
  } catch (err) { toast(err.message, true); }
});


// ======================= Fahrten =======================

const fahrt = { jahr: String(new Date().getFullYear()), daten: null, aktuell: null, nachladen: null };
const km = v => v == null ? "–" : String(v).replace(".", ",");

async function ladeFahrten() {
  clearTimeout(fahrt.nachladen);
  try { fahrt.daten = await api(`fahrten?jahr=${fahrt.jahr}`); }
  catch (e) { return toast("Laden fehlgeschlagen: " + e.message, true); }
  const jahre = [...new Set([String(new Date().getFullYear()), fahrt.jahr, ...fahrt.daten.fahrten.map(f => f.datum.slice(0, 4))])].sort().reverse();
  $("#fahrten-jahr").innerHTML = jahre.map(j => `<option${j === fahrt.jahr ? " selected" : ""}>${j}</option>`).join("");
  renderFahrten();
  // Läuft noch eine Berechnung im Hintergrund? Dann gleich noch einmal nachsehen.
  if (fahrt.daten.kartendienst && fahrt.daten.fahrten.some(f => f.km_einfach == null && !f.fehler)) {
    fahrt.nachladen = setTimeout(() => { if ($("#tab-fahrten").classList.contains("active")) ladeFahrten(); }, 2500);
  }
}

function renderFahrten() {
  const d = fahrt.daten, privat = d.fahrzeug !== "betrieb";
  $("#fahrten-info").innerHTML = `<span>Fahrzeug: <b>${privat ? "Privat" : "Betrieb"}</b>${privat ? ` (${euro2(d.km_satz)}/km)` : " – Fahrten als Nachweis"}</span>
    <span>Start: <b>${esc(d.start || "– bitte Absenderadresse eintragen –")}</b></span>
    <span>Berechnung: <b>${d.kartendienst ? "OpenStreetMap" : "von Hand"}</b></span>
    <a href="#" class="mehr zu-einstellungen">ändern →</a>`;
  const liste = d.fahrten;
  const summeKm = liste.reduce((s, f) => s + (f.km_gesamt || 0), 0);
  const summe = liste.reduce((s, f) => s + (f.betrag || 0), 0);
  const offen = liste.filter(f => f.km_einfach == null).length;
  $("#fahrten-kacheln").innerHTML = `
    <div class="card"><div class="kachel-titel">Fahrten ${fahrt.jahr}</div><div class="stat-gross">${liste.length}<small>${liste.filter(f => f.quelle === "hand").length} von Hand ergänzt${offen ? ` · ${offen} ohne Kilometer` : ""}</small></div></div>
    <div class="card"><div class="kachel-titel">Kilometer</div><div class="stat-gross">${Math.round(summeKm).toLocaleString("de-DE")} km<small>Hin- und Rückfahrten</small></div></div>
    <div class="card"><div class="kachel-titel">${privat ? "Als Ausgabe" : "Nachweis"}</div><div class="stat-gross">${privat ? euro2(summe) : "–"}<small>${privat ? `${Math.round(summeKm).toLocaleString("de-DE")} km × ${euro2(d.km_satz)}` : "Kosten über Belege (Kategorie Fahrzeug)"}</small></div></div>`;
  const quelle = f => f.km_einfach == null
    ? (f.fehler ? `<span class="chip q-offen" title="${esc(f.fehler)}">km fehlen</span>` : d.kartendienst ? `<span class="chip">wird berechnet …</span>` : `<span class="chip q-offen">km eintragen</span>`)
    : `<span class="chip q-${f.quelle}">${{ auto: "automatisch", korrigiert: "korrigiert", hand: "von Hand" }[f.quelle]}</span>`;
  $("#fahrten-body").innerHTML = liste.map(f => `<tr data-id="${f.id}">
      <td>${fmtDate(f.datum)}</td>
      <td>${esc(f.anlass)}${f.rechnung_id ? `<small>${esc(f.kunde)}${f.rechnung_text ? " · " + esc(f.rechnung_text) : ""}${f.rechnung_storniert ? " · <b>storniert</b>" : ""}</small>` : ""}</td>
      <td>${esc(f.ziel_name || f.ziel.split(", ").slice(-1)[0].replace(/^\d{4,5}\s+/, "") || f.ziel)}<small>${esc(f.ziel)}</small></td>
      <td class="num">${f.km_einfach == null ? "–" : (f.hin_zurueck ? `2 × ${km(f.km_einfach)} = ${km(f.km_gesamt)}` : km(f.km_gesamt))}</td>
      <td class="num">${privat && f.betrag != null ? euro2(f.betrag) : "–"}</td>
      <td>${quelle(f)}</td>
      <td class="btns"><button type="button" class="small secondary" data-act="bearbeiten" title="Kilometer oder Ziel ändern">✎</button><button type="button" class="icon del" data-act="loeschen" title="${f.rechnung_id && f.quelle !== "hand" ? "Fahrt entfernen – für diese Rechnung wird dann keine Fahrt mehr angelegt" : "Fahrt löschen"}">✕</button></td>
    </tr>`).join("")
    || `<tr><td colspan="7" class="hint">Noch keine Fahrten ${fahrt.jahr}. Sie entstehen automatisch mit jeder Rechnung – für ältere Rechnungen „Fahrten nachberechnen“.</td></tr>`;
  $("#fahrten-ohne").textContent = d.ohne_fahrt.length
    ? `Ohne Fahrt: ${d.ohne_fahrt.map(r => `Rechnung ${r.nummer} (${r.kunde})`).join(", ")} – „Fahrt erfassen“ ist bei ${d.ohne_fahrt.length === 1 ? "dieser Rechnung" : "diesen Rechnungen"} ausgeschaltet.` : "";
}

$("#fahrten-jahr").addEventListener("change", e => { fahrt.jahr = e.target.value; ladeFahrten(); });
$("#fahrten-nachberechnen").addEventListener("click", async () => {
  try {
    const r = await api("fahrten/nachberechnen", { method: "POST", body: { jahr: fahrt.jahr } });
    toast(`${r.angelegt} Fahrt${r.angelegt === 1 ? "" : "en"} angelegt` + (r.offen ? (r.kartendienst ? ` · ${r.offen} werden berechnet …` : ` · ${r.offen} ohne Kilometer – bitte eintragen oder die automatische Berechnung einschalten`) : ""));
    ladeFahrten();
  } catch (e) { toast(e.message, true); }
});

$("#fahrten-body").addEventListener("click", async e => {
  const b = e.target.closest("button[data-act]");
  if (!b) return;
  const f = fahrt.daten.fahrten.find(x => x.id === Number(b.closest("tr").dataset.id));
  if (b.dataset.act === "bearbeiten") return oeffneFahrt(f);
  const frage = f.rechnung_id && f.quelle !== "hand"
    ? `Fahrt zu ${f.anlass} entfernen?\n\nFür diese Rechnung wird dann keine Fahrt mehr angelegt („Fahrt erfassen“ wird ausgeschaltet).`
    : `Fahrt am ${fmtDate(f.datum)} löschen?`;
  if (!confirm(frage)) return;
  try { await api(`fahrten/${f.id}`, { method: "DELETE" }); toast("Fahrt entfernt"); ladeFahrten(); }
  catch (err) { toast(err.message, true); }
});

$("#fahrt-ergaenzen").addEventListener("click", () => oeffneFahrt(null));

async function oeffneFahrt(f) {
  fahrt.aktuell = f;
  const form = $("#fahrt-form");
  form.reset();
  if (!state.rechnungen.length) { try { state.rechnungen = await api("rechnungen"); } catch (_) { /* egal */ } }
  form.elements.rechnung_id.innerHTML = `<option value="">– keine –</option>` + state.rechnungen.filter(r => !r.storno_von).slice(0, 80)
    .map(r => `<option value="${r.id}">${esc(r.nummer)} – ${esc(r.kunde.name)}</option>`).join("");
  $("#fahrt-titel").textContent = f ? "Fahrt bearbeiten" : "Fahrt ergänzen";
  const w = f || { datum: today(), hin_zurueck: true };
  form.elements.datum.value = w.datum || "";
  form.elements.anlass.value = w.anlass || "";
  form.elements.ziel.value = w.ziel || "";
  form.elements.start.value = f ? (f.start || "") : "";
  form.elements.km_einfach.value = w.km_einfach != null ? km(w.km_einfach) : "";
  form.elements.hin_zurueck.checked = w.hin_zurueck !== false;
  form.elements.rechnung_id.value = w.rechnung_id || "";
  $("#fahrt-dialog-hinweis").textContent = f && f.quelle === "auto"
    ? "Automatisch berechnet. Änderst du die Kilometer (z. B. Umweg), bleibt dein Wert auch beim erneuten Speichern der Rechnung erhalten."
    : fahrt.daten && !fahrt.daten.kartendienst ? "Kilometer bitte eintragen – die automatische Berechnung ist ausgeschaltet." : "";
  $("#fahrt-dialog").showModal();
}
$("#fahrt-abbrechen").addEventListener("click", () => $("#fahrt-dialog").close());
$("#fahrt-form").addEventListener("submit", async e => {
  e.preventDefault();
  const f = e.target.elements;
  const d = { datum: f.datum.value, anlass: f.anlass.value, ziel: f.ziel.value, km_einfach: f.km_einfach.value,
              hin_zurueck: f.hin_zurueck.checked, rechnung_id: f.rechnung_id.value };
  if (f.start.value.trim()) d.start = f.start.value;
  try {
    if (fahrt.aktuell) await api(`fahrten/${fahrt.aktuell.id}`, { method: "PUT", body: d });
    else await api("fahrten", { method: "POST", body: d });
    $("#fahrt-dialog").close();
    toast("Fahrt gespeichert");
    ladeFahrten();
  } catch (err) { toast(err.message, true); }
});


// ======================= Anschaffungen =======================

const anl = { jahr: String(new Date().getFullYear()), liste: [], aktuell: null, modus: "kauf" };
const zahlText = v => v == null || v === "" ? "" : Number(v).toFixed(2).replace(".", ",");

async function ladeAnlagen() {
  try { anl.liste = await api(`anlagen?jahr=${anl.jahr}`); }
  catch (e) { return toast("Laden fehlgeschlagen: " + e.message, true); }
  const j = Number(new Date().getFullYear());
  $("#anlagen-jahr").innerHTML = [j + 1, j, j - 1, j - 2, j - 3].map(String)
    .map(x => `<option${x === anl.jahr ? " selected" : ""}>${x}</option>`).join("");
  $("#anlagen-kopf-afa").textContent = `Abschreibung ${anl.jahr}`;
  $("#anlagen-kopf-rest").textContent = `Restwert 31.12.${anl.jahr.slice(2)}`;
  $("#anlagen-body").innerHTML = anl.liste.map(a => {
    const kaufjahr = (a.anschaffung_am || "").slice(0, 4);
    const anteil = kaufjahr === anl.jahr && a.nutzungsdauer > 1 ? `<small>${13 - Number(a.anschaffung_am.slice(5, 7))} von 12 Monaten</small>` : "";
    return `<tr data-id="${a.id}">
      <td><b>${esc(a.bezeichnung)}</b><small>${a.ausgabe_id ? `aus Ausgabe ${esc(a.ausgabe_lieferant || "")}${a.ausgabe_mit_beleg ? " · 📎" : ""}` : a.restwert_start != null ? "aus Vorjahren übernommen" : "von Hand erfasst"}${a.abgang_am ? ` · Abgang ${fmtDate(a.abgang_am)}` : ""}</small></td>
      <td>${a.anschaffung_am ? fmtDate(a.anschaffung_am) : `vor ${a.start_jahr}`}</td>
      <td class="num">${a.kosten != null ? euro2(a.kosten) : `<small>Restwert 1.1.${String(a.start_jahr).slice(2)}</small>${euro2(a.restwert_start)}`}</td>
      <td>${a.restwert_start != null ? `noch ${a.rest_nutzungsdauer} J. ab ${a.start_jahr}` : a.nutzungsdauer === 1 ? "1 Jahr" : `${a.nutzungsdauer} Jahre`}</td>
      <td class="num">${euro2(a.afa)}${anteil}</td>
      <td class="num">${a.abgang_am && a.abgang_am.startsWith(anl.jahr) ? `<small>Abgang: Restwert ${euro2(a.abgang_restwert)} · Erlös ${euro2(a.abgang_erloes)}</small>` : euro2(a.restwert_ende)}</td>
      <td class="btns"><button type="button" class="small secondary" data-act="bearbeiten" title="Bearbeiten">✎</button></td>
    </tr>`;
  }).join("") || `<tr><td colspan="7" class="hint">Keine Anschaffungen über 800 € in ${anl.jahr}.</td></tr>`;
  const summe = anl.liste.reduce((s, a) => s + a.afa, 0);
  $("#anlagen-summe").innerHTML = anl.liste.length ? `Abschreibung ${anl.jahr} gesamt: <b>${euro2(summe)}</b>` : "";
}
$("#anlagen-jahr").addEventListener("change", e => { anl.jahr = e.target.value; ladeAnlagen(); });
$("#anlagen-body").addEventListener("click", e => {
  const b = e.target.closest("button[data-act=bearbeiten]");
  if (b) oeffneAnlage(anl.liste.find(a => a.id === Number(b.closest("tr").dataset.id)));
});
$("#anlage-uebernehmen").addEventListener("click", () => oeffneAnlage(null));

function anlageModus(m) {
  anl.modus = m;
  $$("#anlage-modus button").forEach(b => b.classList.toggle("an", b.dataset.modus === m));
  $("#anlage-kauf").classList.toggle("hidden", m !== "kauf");
  $("#anlage-rest").classList.toggle("hidden", m !== "rest");
}
$("#anlage-modus").addEventListener("click", e => { const b = e.target.closest("button[data-modus]"); if (b) anlageModus(b.dataset.modus); });

function oeffneAnlage(a) {
  anl.aktuell = a;
  const f = $("#anlage-form");
  f.reset();
  $("#anlage-titel").textContent = a ? a.bezeichnung : "Gerät aus Vorjahren übernehmen";
  const w = a || { nutzungsdauer: 7, start_jahr: Number(anl.jahr) };
  f.elements.bezeichnung.value = w.bezeichnung || "";
  f.elements.anschaffung_am.value = w.anschaffung_am || "";
  f.elements.kosten.value = zahlText(w.kosten);
  f.elements.nutzungsdauer.value = String(w.nutzungsdauer || 7);
  f.elements.start_jahr.value = w.start_jahr || "";
  f.elements.restwert_start.value = zahlText(w.restwert_start);
  f.elements.rest_nutzungsdauer.value = w.rest_nutzungsdauer || "";
  f.elements.abgang_am.value = w.abgang_am || "";
  f.elements.abgang_erloes.value = zahlText(w.abgang_erloes);
  f.elements.notiz.value = w.notiz || "";
  $(".abgang", f).open = !!(a && a.abgang_am);
  anlageModus(a && a.restwert_start != null ? "rest" : "kauf");
  $("#anlage-modus").classList.toggle("hidden", !!(a && a.ausgabe_id));
  // Kosten und Datum einer Anschaffung aus einer Ausgabe kommen aus der Ausgabe
  for (const k of ["anschaffung_am", "kosten"]) f.elements[k].disabled = !!(a && a.ausgabe_id);
  $("#anlage-kosten-hinweis").textContent = a && a.ausgabe_id ? "(aus der Ausgabe)" : state.absender && !state.absender.kleinunternehmer ? "(netto, €)" : "(brutto, €)";
  $("#anlage-loeschen").classList.toggle("hidden", !a || !!a.ausgabe_id);
  $("#anlage-plan").textContent = a && a.plan && a.plan.length
    ? "Plan: " + a.plan.map(([j, b]) => `${j}: ${euro2(b)}`).join(" · ") : "";
  $("#anlage-dialog").showModal();
}
$("#anlage-abbrechen").addEventListener("click", () => $("#anlage-dialog").close());
$("#anlage-form").addEventListener("submit", async e => {
  e.preventDefault();
  const f = e.target.elements;
  const d = { bezeichnung: f.bezeichnung.value, notiz: f.notiz.value, abgang_am: f.abgang_am.value, abgang_erloes: f.abgang_erloes.value };
  if (anl.modus === "kauf") {
    Object.assign(d, { nutzungsdauer: f.nutzungsdauer.value, restwert_start: "", start_jahr: "", rest_nutzungsdauer: "" });
    if (!f.kosten.disabled) Object.assign(d, { anschaffung_am: f.anschaffung_am.value, kosten: f.kosten.value });
  } else {
    Object.assign(d, { restwert_start: f.restwert_start.value, start_jahr: f.start_jahr.value, rest_nutzungsdauer: f.rest_nutzungsdauer.value,
                       anschaffung_am: "", kosten: "", nutzungsdauer: "" });
  }
  try {
    if (anl.aktuell) await api(`anlagen/${anl.aktuell.id}`, { method: "PUT", body: d });
    else await api("anlagen", { method: "POST", body: d });
    $("#anlage-dialog").close();
    toast("Gespeichert");
    ladeAnlagen();
  } catch (err) { toast(err.message, true); }
});
$("#anlage-loeschen").addEventListener("click", async () => {
  if (!anl.aktuell || !confirm(`${anl.aktuell.bezeichnung} aus dem Anlagenverzeichnis löschen?`)) return;
  try { await api(`anlagen/${anl.aktuell.id}`, { method: "DELETE" }); $("#anlage-dialog").close(); ladeAnlagen(); }
  catch (err) { toast(err.message, true); }
});

// Beim Prüfen: Hinweis zur 800-€-Grenze
function gwgHinweis() {
  const f = $("#beleg-form");
  const brutto = Number(String(f.elements.betrag.value).replace(/\./g, "").replace(",", ".")) || 0;
  const satz = Number(f.elements.ust_satz.value) || 0;
  const netto = brutto / (1 + satz / 100);
  const el = $("#erkannt-kategorie");
  if (f.elements.kategorie.value === "anschaffung") {
    el.innerHTML = netto && netto <= 800
      ? `<b>Unter 800 € netto</b> – das kann sofort als Ausgabe abgesetzt werden (Kategorie „Technik“).`
      : "Wird über die Nutzungsdauer abgeschrieben und erscheint unter Finanzen → Anschaffungen.";
  } else if (netto > 800 && f.elements.kategorie.value === "technik") {
    el.innerHTML = `<b>Über 800 € netto</b> – Geräte darüber werden abgeschrieben: Kategorie „Anschaffung über 800 €“ wählen.`;
  }
}
["kategorie", "betrag", "ust_satz"].forEach(k => $("#beleg-form").elements[k].addEventListener("input", gwgHinweis));
$("#beleg-form").elements.kategorie.addEventListener("change", gwgHinweis);


// ======================= Übersicht & EÜR =======================

const ue = { jahr: String(new Date().getFullYear()), daten: null };
const MON_KURZ = ["Jan", "Feb", "Mär", "Apr", "Mai", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"];

function jahresAuswahl(sel, jahr) {
  const j = new Date().getFullYear();
  sel.innerHTML = [j, j - 1, j - 2, j - 3].map(String).map(x => `<option${x === jahr ? " selected" : ""}>${x}</option>`).join("");
}

async function ladeUebersicht() {
  try { ue.daten = await api(`finanzen/euer?jahr=${ue.jahr}`); }
  catch (e) { return toast("Laden fehlgeschlagen: " + e.message, true); }
  jahresAuswahl($("#finanzen-jahr"), ue.jahr);
  const d = ue.daten;
  const heute = new Date();
  const stand = Number(ue.jahr) === heute.getFullYear() ? `bis ${fmtDate(today())}` : `Jahr ${ue.jahr}`;
  const fahrtAfa = [d.fahrtkosten && `Fahrten ${euro2(d.fahrtkosten)}`, d.afa && `Abschreibung ${euro2(d.afa)}`].filter(Boolean).join(" · ");
  $("#finanzen-kacheln").innerHTML = `
    <div class="card"><div class="kachel-titel">Einnahmen</div><div class="stat-gross">${euro2(d.einnahmen)}<small>${d.anzahl_rechnungen} bezahlte Rechnung${d.anzahl_rechnungen === 1 ? "" : "en"}</small></div></div>
    <div class="card"><div class="kachel-titel">Ausgaben</div><div class="stat-gross">${euro2(d.ausgaben)}<small>${fahrtAfa ? "inkl. " + fahrtAfa : "&nbsp;"}</small></div></div>
    <div class="card kachel-gewinn"><div class="kachel-titel">Gewinn</div><div class="stat-gross">${euro2(d.gewinn)}<small>${stand}</small></div></div>`;
  zeichneGrenzen(d.grenzen);
  $("#finanzen-hinweise").innerHTML = d.pruefliste.filter(p => p.stufe === "warn" && p.aktion !== "grenzen").map(p =>
    `<li class="gelb">${esc(p.text)}${p.aktion ? ` – <a href="#" data-pruef="${p.aktion}">${p.aktion === "bezahlt_am" ? "nachtragen" : "ansehen"}</a>` : ""}</li>`).join("");
  zeichneDiagramm(d.monate);
  const zeilen = d.ausgaben_zeilen.filter(z => z.betrag > 0);
  const max = Math.max(...zeilen.map(z => z.betrag), 1);
  $("#finanzen-kategorien").innerHTML = zeilen.map(z => `<div class="kat-zeile"><span>${esc(z.name)}</span><strong>${euro2(z.betrag)}</strong>
      <div class="kat-balken"><span style="width:${z.betrag / max * 100}%"></span></div></div>`).join("")
    || `<p class="hint">Noch keine Ausgaben in ${ue.jahr}.</p>`;
}
$("#finanzen-jahr").addEventListener("change", e => { ue.jahr = e.target.value; ladeUebersicht(); });

/* Gruppierte Säulen, eine Achse, Werte nur beim besten Einnahme- und beim höchsten Ausgabenmonat; Rest im Tooltip/Tabelle */
function zeichneDiagramm(monate) {
  const W = 640, H = 260, L = 46, R = 8, T = 22, B = 26;
  const maxWert = Math.max(1, ...monate.map(m => Math.max(m.einnahmen, m.ausgaben)));
  const schritt = [100, 250, 500, 1000, 2000, 2500, 5000, 10000, 20000, 25000, 50000].find(s => maxWert / s <= 4) || 100000;
  const max = Math.ceil(maxWert / schritt) * schritt;
  const bw = (W - L - R) / 12, bar = Math.min(14, (bw - 10) / 2);
  const y = v => T + (H - T - B) * (1 - Math.max(0, v) / max);
  const achse = v => v >= 1000 ? `${(v / 1000).toLocaleString("de-DE")} T€` : `${v} €`;
  let s = `<svg class="diagramm" viewBox="0 0 ${W} ${H}" role="img" aria-label="Einnahmen und Ausgaben je Monat ${ue.jahr}">`;
  for (let v = 0; v <= max; v += schritt) s += `<line class="gitter" x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}"/><text x="${L - 6}" y="${y(v) + 4}" text-anchor="end">${achse(v)}</text>`;
  const saeule = (x, v, farbe) => {
    if (v <= 0) return "";
    const h = y(0) - y(v), r = Math.min(4, h);
    return `<path d="M${x},${y(0)} V${y(v) + r} Q${x},${y(v)} ${x + r},${y(v)} H${x + bar - r} Q${x + bar},${y(v)} ${x + bar},${y(v) + r} V${y(0)} Z" fill="${farbe}"/>`;
  };
  monate.forEach((m, i) => {
    const x0 = L + i * bw;
    s += `<g class="monat" data-i="${i}"><rect class="hit" x="${x0}" y="${T}" width="${bw}" height="${H - T - B}" rx="6"/>`
      + saeule(x0 + bw / 2 - bar - 1, m.einnahmen, "var(--ein)") + saeule(x0 + bw / 2 + 1, m.ausgaben, "var(--aus)")
      + `<text x="${x0 + bw / 2}" y="${H - 8}" text-anchor="middle">${MON_KURZ[i]}</text></g>`;
  });
  const iE = monate.reduce((b, m, i) => m.einnahmen > monate[b].einnahmen ? i : b, 0);
  const iA = monate.reduce((b, m, i) => m.ausgaben > monate[b].ausgaben ? i : b, 0);
  if (monate[iE].einnahmen > 0) s += `<text class="wert" x="${L + iE * bw + bw / 2 - bar / 2 - 1}" y="${y(monate[iE].einnahmen) - 6}" text-anchor="middle">${euro2(monate[iE].einnahmen).replace(",00", "")}</text>`;
  if (monate[iA].ausgaben > 0 && iA !== iE) s += `<text class="wert" x="${L + iA * bw + bw / 2 + bar / 2 + 1}" y="${y(monate[iA].ausgaben) - 6}" text-anchor="middle">${euro2(monate[iA].ausgaben).replace(",00", "")}</text>`;
  $("#finanzen-diagramm").innerHTML = s + "</svg>";
  let tip = $(".diagramm-tip");
  if (!tip) { tip = document.createElement("div"); tip.className = "diagramm-tip"; document.body.appendChild(tip); }
  $$("#finanzen-diagramm g.monat").forEach(g => {
    g.addEventListener("mousemove", e => {
      const m = monate[Number(g.dataset.i)];
      tip.innerHTML = `<b>${MONATE[Number(g.dataset.i)]} ${ue.jahr}</b><div><span><i style="background:var(--ein)"></i>Einnahmen</span><span>${euro2(m.einnahmen)}</span></div>`
        + `<div><span><i style="background:var(--aus)"></i>Ausgaben</span><span>${euro2(m.ausgaben)}</span></div><div><span>Überschuss</span><b>${euro2(m.einnahmen - m.ausgaben)}</b></div>`
        + (Number(g.dataset.i) === 11 && ue.daten.afa ? `<div><small>inkl. Abschreibung des Jahres</small></div>` : "");
      tip.style.display = "block";
      tip.style.left = Math.min(e.clientX + 14, window.innerWidth - 220) + "px";
      tip.style.top = (e.clientY + 14) + "px";
    });
    g.addEventListener("mouseleave", () => { tip.style.display = "none"; });
  });
  $("#finanzen-tabelle").innerHTML = `<table class="mini"><thead><tr><th>Monat</th><th>Einnahmen</th><th>Ausgaben</th><th>Überschuss</th></tr></thead><tbody>`
    + monate.map((m, i) => `<tr><td>${MONATE[i]}</td><td>${euro2(m.einnahmen)}</td><td>${euro2(m.ausgaben)}</td><td>${euro2(m.einnahmen - m.ausgaben)}</td></tr>`).join("")
    + "</tbody></table>";
}
$("#diagramm-umschalten").addEventListener("click", e => {
  e.preventDefault();
  const tabelle = $("#finanzen-tabelle").hidden;
  $("#finanzen-tabelle").hidden = !tabelle;
  $("#finanzen-diagramm").hidden = tabelle;
  $("#diagramm-legende").hidden = tabelle;
  e.target.textContent = tabelle ? "Als Diagramm" : "Als Tabelle";
});

// Links aus Prüfliste/Hinweisen
document.addEventListener("click", e => {
  const a = e.target.closest("[data-pruef]");
  if (a) {
    e.preventDefault();
    if (a.dataset.pruef === "bezahlt_am") return oeffneBezahltAm();
    return showTab(a.dataset.pruef);
  }
  const g = e.target.closest("[data-goto-tab]");
  if (g) { e.preventDefault(); showTab(g.dataset.gotoTab); }
});

async function ladeEuer() {
  let d;
  try { d = await api(`finanzen/euer?jahr=${ue.jahr}`); }
  catch (e) { return toast("Laden fehlgeschlagen: " + e.message, true); }
  ue.daten = d;
  jahresAuswahl($("#euer-jahr"), ue.jahr);
  $("#euer-titel").innerHTML = `EÜR ${ue.jahr} <span class="h2-sub">${d.kleinunternehmer ? "Kleinunternehmer" : "umsatzsteuerpflichtig, netto"}${Number(ue.jahr) === new Date().getFullYear() ? ` · Stand ${fmtDate(today())}` : ""}</span>`;
  const zeile = z => `<tr class="eingerueckt"><td>${esc(z.name)}${z.euer ? `<small>${esc(z.euer)}</small>` : ""}</td><td class="num">${euro2(z.betrag)}</td></tr>`;
  $("#euer-body").innerHTML = `<tr class="zwischen"><td>Betriebseinnahmen</td><td class="num">${euro2(d.einnahmen)}</td></tr>`
    + d.einnahmen_zeilen.map(zeile).join("")
    + `<tr class="zwischen"><td>Betriebsausgaben</td><td class="num">${euro2(d.ausgaben)}</td></tr>`
    + (d.ausgaben_zeilen.map(zeile).join("") || `<tr class="eingerueckt"><td class="hint">keine</td><td></td></tr>`)
    + `<tr class="gewinn"><td>${d.gewinn >= 0 ? "Gewinn" : "Verlust"}</td><td class="num">${euro2(d.gewinn)}</td></tr>`;
  $("#euer-pruefliste").innerHTML = d.pruefliste.map(p => `<li class="${p.stufe}">${{ ok: "✓", warn: "⚠", info: "ℹ" }[p.stufe]} ${esc(p.text)}`
    + (p.aktion ? ` – <a href="#" data-pruef="${p.aktion}">${p.aktion === "bezahlt_am" ? "nachtragen" : "ansehen"}</a>` : "") + "</li>").join("");
  $("#euer-export-jahr").textContent = ue.jahr;
  $("#einnahmen-body").innerHTML = d.sonstige.map(x => `<tr data-id="${x.id}"><td>${fmtDate(x.datum)}</td><td>${esc(x.beschreibung)}</td>
      <td class="num">${euro2(x.betrag)}</td><td class="btns"><button type="button" class="icon del" title="Löschen">✕</button></td></tr>`).join("")
    || `<tr><td class="hint" colspan="4">Keine in ${ue.jahr}.</td></tr>`;
}
$("#euer-jahr").addEventListener("change", e => { ue.jahr = e.target.value; ladeEuer(); });
$("#euer-export").addEventListener("click", () => { ladeHerunter(`api/export?jahr=${ue.jahr}`); toast(`Export ${ue.jahr} wird erstellt …`); });

async function oeffneBezahltAm() {
  let liste;
  try { liste = await api("finanzen/ohne-bezahltdatum"); } catch (e) { return toast(e.message, true); }
  $("#bezahltam-body").innerHTML = liste.map(r => `<tr data-id="${r.id}"><td>Rechnung ${esc(r.nummer)}<br><small>${esc(r.kunde)} · ${fmtDate(r.datum)}</small></td>
      <td class="num">${euro2(r.gesamt)}</td><td><input type="date" value="" aria-label="Bezahlt am"></td></tr>`).join("")
    || `<tr><td class="hint">Alle bezahlten Rechnungen haben ein Bezahlt-Datum.</td></tr>`;
  $(".bezahltam-alle").hidden = !liste.length;
  $("#bezahltam-dialog").showModal();
}
$("#bezahltam-body").addEventListener("change", async e => {
  const tr = e.target.closest("tr[data-id]");
  if (!tr || !e.target.value) return;
  try { await api(`rechnungen/${tr.dataset.id}/bezahlt_am`, { method: "PUT", body: { bezahlt_am: e.target.value } }); tr.style.opacity = .5; toast("Bezahlt-Datum gespeichert"); }
  catch (err) { toast(err.message, true); }
});
function finanzenNeuLaden() {
  if ($("#tab-euer").classList.contains("active")) ladeEuer(); else if ($("#tab-finanzen").classList.contains("active")) ladeUebersicht();
  if (typeof renderStartFinanzen === "function") renderStartFinanzen();
}
$("#bezahltam-zu").addEventListener("click", () => { $("#bezahltam-dialog").close(); finanzenNeuLaden(); });
$("#bezahltam-rechnungsdatum").addEventListener("click", async () => {
  // Datumsfelder, die schon einzeln ausgefüllt wurden, sind bereits gespeichert – übrig bleiben nur die leeren
  try {
    const d = await api("finanzen/bezahlt-am-rechnungsdatum", { method: "POST" });
    $("#bezahltam-dialog").close();
    toast(`Rechnungsdatum bei ${d.anzahl} Rechnung${d.anzahl === 1 ? "" : "en"} als Bezahlt-Datum übernommen`);
    finanzenNeuLaden();
  } catch (e) { toast(e.message, true); }
});

$("#einnahme-neu").addEventListener("click", () => {
  const f = $("#einnahme-form"); f.reset(); f.elements.datum.value = today();
  $("#einnahme-dialog").showModal();
});
$("#einnahme-abbrechen").addEventListener("click", () => $("#einnahme-dialog").close());
$("#einnahme-form").addEventListener("submit", async e => {
  e.preventDefault();
  const f = e.target.elements;
  try {
    await api("einnahmen", { method: "POST", body: { datum: f.datum.value, betrag: f.betrag.value, beschreibung: f.beschreibung.value } });
    $("#einnahme-dialog").close(); toast("Einnahme gespeichert"); ladeEuer();
  } catch (err) { toast(err.message, true); }
});
$("#einnahmen-body").addEventListener("click", async e => {
  const tr = e.target.closest("tr[data-id]");
  if (!tr || !e.target.closest("button") || !confirm("Diese Einnahme löschen?")) return;
  try { await api(`einnahmen/${tr.dataset.id}`, { method: "DELETE" }); ladeEuer(); } catch (err) { toast(err.message, true); }
});

// Startseite: Kachel „Finanzen <Jahr>“
async function renderStartFinanzen() {
  const jahr = String(new Date().getFullYear());
  let d;
  try { d = await api(`finanzen/euer?jahr=${jahr}`); } catch (_) { return; }
  $("#start-finanzen-titel").textContent = `Finanzen ${jahr}`;
  const neu = d.pruefliste.find(p => p.aktion === "ausgaben" && p.stufe === "warn" && /Beleg/.test(p.text));
  const grenze = (d.grenzen?.hinweise || []).filter(h => h.stufe === "rot" || h.stufe === "gelb")[0];
  $("#start-finanzen-inhalt").innerHTML = `<div class="stat-gross">${euro2(d.gewinn)}<small>${d.gewinn >= 0 ? "Gewinn" : "Verlust"} bis heute · Einnahmen ${euro2(d.einnahmen)} · Ausgaben ${euro2(d.ausgaben)}</small></div>`
    + (neu || grenze ? `<ul class="hinweise">`
      + (grenze ? `<li class="${grenze.stufe}">${grenze.stufe === "rot" ? "⚠ " : ""}${esc(grenze.text)} – <a href="#" data-goto-tab="finanzen">Übersicht</a></li>` : "")
      + (neu ? `<li class="gelb">${esc(neu.text)} – <a href="#" data-pruef="ausgaben">jetzt prüfen</a></li>` : "") + `</ul>` : "");
}

// ---------- Paperless: Einstellungen und Abholen ----------

function plTagAuswahl(tags, gewaehlt, name) {
  const sel = $("#einstellungen").elements.paperless_tag;
  const opt = (id, text) => `<option value="${id}"${String(id) === String(gewaehlt) ? " selected" : ""}>${esc(text)}</option>`;
  if (tags) {
    sel.innerHTML = opt(0, "– Tag wählen –") + tags.map(t => opt(t.id, t.name + (t.anzahl != null ? ` (${t.anzahl} Dokument${t.anzahl === 1 ? "" : "e"})` : ""))).join("");
  } else {   // noch nicht verbunden: nur den gespeicherten Tag anzeigen
    sel.innerHTML = Number(gewaehlt) ? opt(gewaehlt, name || `Tag ${gewaehlt}`) : opt(0, "– erst Verbindung prüfen –");
  }
}

function plEinstellungen(werte) {
  const f = $("#einstellungen").elements;
  zeigePaperlessBelege();
  f.paperless_token.value = "";
  f.paperless_token.placeholder = werte.paperless_token_gesetzt ? "•••••••• gespeichert – nur zum Ändern neu eingeben" : "Token aus Paperless einfügen";
  $("#pl-token-status").textContent = werte.paperless_token_gesetzt ? "(gespeichert)" : "(wird nur lokal gespeichert)";
  plTagAuswahl(null, werte.paperless_tag, werte.paperless_tag_name);
  const verbunden = werte.paperless_token_gesetzt && werte.paperless_url;
  if (verbunden) $("#pl-api").open = true;
  $("#pl-verbunden").hidden = !verbunden;
  $("#pl-verbunden").textContent = verbunden ? `✓ Verbunden mit ${werte.paperless_url} – erneut anmelden nur bei Problemen.` : "";
  $("#pl-verbinden").textContent = verbunden ? "Tags neu laden" : "Mit Paperless verbinden";
}

$("#einstellungen").elements.paperless_tag.addEventListener("change", async e => {
  const o = e.target.selectedOptions[0], f = $("#einstellungen").elements;
  f.paperless_tag_name.value = Number(o.value) ? o.textContent.replace(/ \(\d+ Dokumente?\)$/, "") : "";
  try {   // Tag sofort speichern – kein extra Klick auf „Speichern“ nötig
    await api("einstellungen", { method: "PUT", body: { paperless_tag: o.value, paperless_tag_name: f.paperless_tag_name.value } });
    await ladeAbsender();
    if (Number(o.value)) toast(`Tag „${f.paperless_tag_name.value}“ gespeichert – unter Finanzen → Ausgaben „Aus Paperless abholen“`);
  } catch (err) { toast(err.message, true); }
});

$("#pl-verbinden").addEventListener("click", async e => {
  const f = $("#einstellungen").elements, btn = e.currentTarget, status = $("#pl-verbinden-status");
  btn.disabled = true;
  status.textContent = f.paperless_url.value.trim() ? "Verbinde …" : "Suche Paperless …";
  try {
    const r = await api("paperless/verbinden", { method: "POST", body: {
      url: f.paperless_url.value.trim(), token: f.paperless_token.value.trim(),
      benutzer: $("#pl-benutzer").value.trim(), passwort: $("#pl-passwort").value } });
    f.paperless_url.value = r.url;
    $("#pl-passwort").value = "";
    if (!r.tags) { status.textContent = r.hinweis; return; }
    if (r.token_gespeichert) plEinstellungen({ ...await api("einstellungen") });
    plTagAuswahl(r.tags, f.paperless_tag.value, f.paperless_tag_name.value);
    const gefunden = r.gefunden ? r.gefunden + " – " : "";
    if (!Number(f.paperless_tag.value)) {   // naheliegenden Tag vorschlagen (wird sofort gespeichert)
      const v = r.tags.find(t => /ausgabe|beleg|eür|euer|steuer|rechnung/i.test(t.name));
      if (v) { f.paperless_tag.value = v.id; f.paperless_tag.dispatchEvent(new Event("change")); }
    }
    status.textContent = Number(f.paperless_tag.value)
      ? `✓ ${gefunden}verbunden. Tag „${f.paperless_tag_name.value}“ ist eingestellt – unten änderbar.`
      : `✓ ${gefunden}verbunden. Jetzt unten den Tag deiner Ausgaben wählen.`;
  } catch (err) { status.textContent = ""; toast(err.message, true); }
  finally { btn.disabled = false; }
});

$("#paperless-abholen").addEventListener("click", async e => {
  const btn = e.currentTarget, text = btn.textContent;
  btn.disabled = true;
  let st;
  try {
    st = await api("paperless/abholen", { method: "POST" });
    while (st.laeuft) {
      btn.textContent = st.gesamt == null ? (st.meldung || "Paperless …") : `⇩ ${st.fertig} von ${st.gesamt} geholt …`;
      await new Promise(ok => setTimeout(ok, 800));
      st = await api("paperless/abholen");
    }
    const teile = [];
    if (st.neu) teile.push(`${st.neu} neu`);
    if (st.doppelt) teile.push(`${st.doppelt} schon von Hand hochgeladen`);
    if (st.fehler?.length) teile.push(`${st.fehler.length} nicht lesbar (${st.fehler.slice(0, 3).join(", ")})`);
    if (st.abbruch) toast(`${st.abbruch}${teile.length ? " · bis dahin: " + teile.join(" · ") : ""}`, true);
    else toast(teile.length ? `Paperless: ${teile.join(" · ")}` : `Paperless: keine neuen Belege (${st.vorhanden} schon übernommen)`);
    if (st.neu || st.doppelt) await ladeAusgaben();
  } catch (err) { toast(err.message, true); }
  finally { btn.disabled = false; btn.textContent = text; }
});

// ---------- Belege-Ordner ----------

const uhrzeit = iso => iso ? iso.slice(11, 16) : "";

function zeigeOrdnerStand(st) {
  const el = $("#ordner-stand");
  el.hidden = !st.ordner;
  if (!st.ordner) return;
  el.classList.toggle("warn", !!st.problem);
  el.innerHTML = st.problem ? `⚠ ${esc(st.problem)} – <a href="#" class="zu-einstellungen">Einstellungen</a>`
    : `↻ Belege-Ordner <b>${esc(st.ordner)}</b> wird automatisch eingelesen${st.laeuft ? " – gerade …" : st.geprueft ? ` · zuletzt ${uhrzeit(st.geprueft)} Uhr` : ""}`;
}

async function ordnerPruefen() {
  let st;
  try { st = await api("belege-ordner/einlesen", { method: "POST" }); } catch (_) { return; }
  const start = [st.start_neu, st.start_doppelt];
  zeigeOrdnerStand(st);
  for (let i = 0; st.laeuft && i < 600; i++) {
    await new Promise(ok => setTimeout(ok, 1000));
    try { st = await api("belege-ordner"); } catch (_) { return; }
    zeigeOrdnerStand(st);
  }
  const neu = st.neu - (start[0] ?? st.neu), doppelt = st.doppelt - (start[1] ?? st.doppelt);
  if (neu || doppelt) {
    toast(`Belege-Ordner: ${neu ? `${neu} neu` : ""}${neu && doppelt ? " · " : ""}${doppelt ? `${doppelt} schon vorhanden` : ""}`);
    await ladeAusgaben();
  }
}

// Paperless-Teil nur zeigen, wenn „Paperless-ngx ist installiert“ angehakt ist
function zeigePaperlessBelege() {
  $("#pl-belege").hidden = !$("#einstellungen").elements.paperless_installiert.checked;
}
$("#einstellungen").elements.paperless_installiert.addEventListener("change", zeigePaperlessBelege);

$("#pl-ordner-suchen").addEventListener("click", async e => {
  const btn = e.currentTarget, status = $("#pl-ordner-status"), f = $("#einstellungen").elements;
  btn.disabled = true;
  status.textContent = "Suche …";
  try {
    const r = await api("belege-ordner/suchen", { method: "POST", body: {} });
    // gefunden → sofort übernehmen: nur lesen (die Dateien gehören Paperless)
    await api("einstellungen", { method: "PUT", body: { belege_ordner: r.ordner, belege_ordner_verschieben: false } });
    f.belege_ordner.value = r.ordner;
    f.belege_ordner_verschieben.checked = false;
    status.textContent = `✓ Gefunden: ${r.ordner} (${r.anzahl} Beleg${r.anzahl === 1 ? "" : "e"}). Wird automatisch eingelesen – die Belege erscheinen unter Finanzen → Ausgaben.`;
    toast("Ausgaben-Ordner von Paperless eingestellt");
  } catch (err) { status.textContent = ""; toast(err.message, true); }
  finally { btn.disabled = false; }
});

// ---------- Kleinunternehmer-Grenzen (Übersicht) ----------

function grenzMeter(titel, wert, grenze, unterzeile) {
  const anteil = wert / grenze, breite = Math.min(100, Math.max(0, anteil * 100));
  const stufe = anteil > 1 ? "rot" : anteil >= 0.8 ? "gelb" : "ok";
  const status = anteil > 1 ? "⚠ überschritten" : anteil >= 0.8 ? "△ knapp" : "✓ im Rahmen";
  return `<div class="ku-kopf"><span>${titel}</span><span class="ku-status ${stufe}">${status}</span></div>
    <div class="ku-wert"><strong>${euro2(wert)}</strong> <span>von ${grenze.toLocaleString("de-DE")} €</span></div>
    <div class="ku-balken ${stufe}" role="meter" aria-valuemin="0" aria-valuemax="${grenze}" aria-valuenow="${wert}"
      aria-label="${esc(titel)}: ${euro2(wert)} von ${grenze.toLocaleString("de-DE")} €"><span style="width:${breite}%"></span></div>
    <small>${unterzeile}</small>`;
}

function zeichneGrenzen(g) {
  const karte = $("#ku-grenzen");
  karte.hidden = !g;
  if (!g) return;
  const j = g.jahr;
  $("#ku-titel").textContent = `Kleinunternehmer-Grenzen ${j}`;
  $("#ku-stand").textContent = g.laufend ? `Stand ${fmtDate(today())}` : "";
  const rest25 = g.grenze_vorjahr - g.umsatz;
  $("#ku-25").innerHTML = grenzMeter(`Umsatz ${j} – entscheidet über ${j + 1}`, g.umsatz, g.grenze_vorjahr,
    (rest25 > 0 ? `noch ${euro2(rest25)} bis 25.000 €` : `über 25.000 € → ${j + 1} keine Kleinunternehmerregelung`)
    + (g.laufend && g.offen ? ` · dazu offene Rechnungen ${euro2(g.offen)}` : "")
    + (g.hochrechnung ? ` · grobe Hochrechnung fürs Jahr ~${euro2(Math.round(g.hochrechnung / 100) * 100)}` : ""));
  $("#ku-100").innerHTML = grenzMeter(`Grenze im Jahr ${j}`, g.umsatz, g.grenze_jahr,
    g.gruendungsjahr ? `Umsatz ${j - 1}: keine Rechnungen in der App – alte Rechnungen ggf. importieren`
      : `Umsatz ${j - 1}: ${euro2(g.vorjahr)} ${g.vorjahr > g.grenze_vorjahr ? "– über 25.000 €" : "– unter 25.000 € ✓"}`);
  $("#ku-hinweise").innerHTML = g.hinweise.filter(h => h.stufe !== "ok").map(h =>
    `<li class="${h.stufe === "info" ? "" : h.stufe}">${h.stufe === "rot" ? "⚠ " : ""}${esc(h.text)}</li>`).join("");
}

// ---------- Texterkennung (Fotos, Scans) ----------

function ocrLaeuft(a) { return !!a && a.status === "neu" && (a.ocr === "wartet" || a.ocr === "laeuft"); }

function zeigeErkennung(a, neu) {
  const e = a?.erkannt || {}, laeuft = ocrLaeuft(a);
  $("#ocr-stand").hidden = !laeuft;
  $("#ocr-stand").textContent = a?.ocr === "wartet" ? "Text wird gleich gelesen – du kannst die Werte auch schon eintragen."
    : "Text wird gelesen … – du kannst die Werte auch schon eintragen.";
  $("#ocr-starten").hidden = laeuft || !neu || !a || a.betrag != null || !["bild", "pdf"].includes(a.beleg_typ);
  $("#beleg-hinweise").innerHTML = laeuft ? "" : (e.hinweise || []).map(h => `<li class="gelb">${esc(h)}</li>`).join("");
  // nur, solange das Feld noch den erkannten Wert hat – nicht unter selbst Getipptem
  $("#erkannt-lieferant").textContent = neu && a && e.lieferant && $("#beleg-form").elements.lieferant.value === e.lieferant ? (a.beleg_typ === "mail" || a.beleg_typ === "msg"
    ? "erkannt am Absender der Mail" : "aus dem Briefkopf übernommen – bitte prüfen") : "";
  $("#erkannt-betrag").innerHTML = neu && e.betrag != null ? `erkannt: <b>${esc(e.fundstellen?.betrag || "")}</b>`
    + (e.ust_betrag != null ? ` · Umsatzsteuer <b>${euro2(e.ust_betrag)}</b>` : "") + " – bitte kurz mit dem Beleg vergleichen" : "";
  $("#erkannt-kategorie").textContent = neu && a && a.lieferant ? (e.kategorie && e.kategorie === a.kategorie
    ? "aus dem Shop erkannt" : a.kategorie !== "sonstiges" ? `wie beim letzten Beleg von ${a.lieferant}` : "") : "";
}

const OCR_FELDER = {
  lieferant: a => a.lieferant || "", belegdatum: a => a.belegdatum || "", bezahlt_am: a => a.bezahlt_am || "",
  kategorie: a => a.kategorie || "", betrag: a => a.betrag != null ? Number(a.betrag).toFixed(2).replace(".", ",") : "",
  ust_satz: a => a.ust_satz ? String(Math.round(a.ust_satz)) : "",
};

// Beleg ist offen, während noch gelesen wird: Ergebnis nur in Felder, die noch unverändert sind
function ocrImFormularVerfolgen() {
  clearTimeout(fin.ocrFormular);
  const vorher = fin.aktuell;
  if (!ocrLaeuft(vorher)) return;
  fin.ocrFormular = setTimeout(async () => {
    if (!$("#tab-beleg").classList.contains("active")) return;
    let a;
    try { a = await api(`ausgaben/${vorher.id}`); } catch (_) { return ocrImFormularVerfolgen(); }
    if (fin.aktuell !== vorher) return;         // inzwischen ist ein anderer Beleg offen
    if (a.status === "neu") {
      const f = $("#beleg-form").elements;
      for (const [k, wert] of Object.entries(OCR_FELDER)) {
        if (f[k] !== document.activeElement && f[k].value === wert(vorher)) f[k].value = wert(a);
        else if (f[k] === document.activeElement && f[k].value === "" && !wert(vorher)) f[k].value = wert(a);   // leeres Feld mit Cursor
      }
      fin.aktuell = a;
      zeigeErkennung(a, true);
      ocrImFormularVerfolgen();
    }
  }, 1500);
}

$("#ocr-starten").addEventListener("click", async () => {
  const a = fin.aktuell;
  if (!a) return;
  try {
    const stand = await api(`ausgaben/${a.id}/texterkennung`, { method: "POST" });
    fin.aktuell = { ...a, ocr: stand.ocr };
    zeigeErkennung(fin.aktuell, true);
    ocrImFormularVerfolgen();
  } catch (err) { toast(err.message, true); }
});

function ocrListeNachladen() {
  clearTimeout(fin.ocrListe);
  if (!fin.ausgaben.some(ocrLaeuft)) return;
  fin.ocrListe = setTimeout(() => { if ($("#tab-ausgaben").classList.contains("active")) ladeAusgaben(); }, 2500);
}
