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
  if (name === "ausgaben") ladeAusgaben();
}

async function ladeAusgaben() {
  try {
    await ladeKategorien();
    fin.ausgaben = await api(`ausgaben?jahr=${fin.jahr}`);
  } catch (e) { return toast("Laden fehlgeschlagen: " + e.message, true); }
  const jahre = [...new Set([String(new Date().getFullYear()), fin.jahr, ...fin.ausgaben.map(a => a.jahr).filter(Boolean)])].sort().reverse();
  $("#ausgaben-jahr").innerHTML = jahre.map(j => `<option${j === fin.jahr ? " selected" : ""}>${j}</option>`).join("");
  renderAusgaben();
}

function renderAusgaben() {
  const neu = fin.ausgaben.filter(a => a.status === "neu");
  $("#ausgaben-neu-karte").classList.toggle("hidden", !neu.length);
  $("#ausgaben-neu-anzahl").textContent = `${neu.length} Beleg${neu.length === 1 ? "" : "e"}`;
  $("#ausgaben-neu").innerHTML = neu.map(a => {
    const e = a.erkannt || {};
    const erkannt = [e.betrag != null && "Gesamt", e.ust_betrag != null && "MwSt.", e.kategorie && "Kategorie"].filter(Boolean);
    const info = e.typ === "bild" ? "Foto – keine automatische Erkennung, Betrag bitte eintragen"
      : erkannt.length ? `erkannt: ${erkannt.join(", ")}` : "nichts erkannt – bitte Werte eintragen";
    return `<div class="neu-beleg" data-id="${a.id}">
      <div class="datei-icon">${TYP_KURZ[a.beleg_typ] || "DATEI"}</div>
      <div class="was"><strong>${esc(a.lieferant || a.beleg_name)}</strong>
        <small>${esc(a.beschreibung || a.beleg_name)} · ${fmtDate(a.belegdatum)} · ${info}</small></div>
      <div class="betrag">${a.betrag != null ? euro2(a.betrag) : "– €"}</div>
      <button type="button" class="small${a === neu[0] ? "" : " secondary"}" data-act="pruefen">${a.betrag != null ? "Prüfen" : "Eintragen"}</button>
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

async function belegeHochladen(dateien) {
  if (!dateien.length) return;
  const fd = new FormData();
  [...dateien].forEach(f => fd.append("dateien", f));
  $("#beleg-status").textContent = `${dateien.length} Beleg${dateien.length === 1 ? " wird" : "e werden"} gelesen …`;
  try {
    const res = await fetch("api/ausgaben/belege", { method: "POST", body: fd });
    const d = await res.json();
    if (!res.ok) throw new Error(d.error || `Fehler ${res.status}`);
    const teile = [];
    if (d.neu.length) teile.push(`${d.neu.length} neu`);
    if (d.doppelt.length) teile.push(`${d.doppelt.length} schon vorhanden (${d.doppelt.map(x => x.datei).join(", ")})`);
    if (d.fehler.length) teile.push(`${d.fehler.length} nicht lesbar`);
    toast(teile.join(" · ") || "Nichts hochgeladen", !!(d.fehler.length && !d.neu.length));
    await ladeAusgaben();
  } catch (e) { toast("Hochladen fehlgeschlagen: " + e.message, true); }
  finally { $("#beleg-status").textContent = "oder klicken zum Auswählen"; }
}

const drop = $("#beleg-drop");
drop.addEventListener("dragover", e => { e.preventDefault(); drop.classList.add("over"); });
drop.addEventListener("dragleave", () => drop.classList.remove("over"));
drop.addEventListener("drop", e => {
  e.preventDefault();
  drop.classList.remove("over");
  belegeHochladen(e.dataTransfer.files);
});
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

  // Hinweise und Fundstellen der Erkennung
  const e = (a && a.erkannt) || {};
  $("#beleg-hinweise").innerHTML = (e.hinweise || []).map(h => `<li class="gelb">${esc(h)}</li>`).join("");
  $("#erkannt-lieferant").innerHTML = neu && a && e.lieferant ? (a.beleg_typ === "mail" || a.beleg_typ === "msg"
    ? "erkannt am Absender der Mail" : "aus dem Briefkopf übernommen – bitte prüfen") : "";
  $("#erkannt-betrag").innerHTML = neu && e.betrag != null ? `erkannt: <b>${esc(e.fundstellen?.betrag || "")}</b>`
    + (e.ust_betrag != null ? ` · Umsatzsteuer <b>${euro2(e.ust_betrag)}</b>` : "") + " – bitte kurz mit dem Beleg vergleichen" : "";
  $("#erkannt-kategorie").textContent = neu && a && a.lieferant ? (e.kategorie && e.kategorie === a.kategorie
    ? "aus dem Shop erkannt" : a.kategorie !== "sonstiges" ? `wie beim letzten Beleg von ${a.lieferant}` : "") : "";

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
