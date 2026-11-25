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
  faellig: [],               // fällige, noch nicht bestätigte Abo-Abbuchungen (seit 1.9)
};

const euro2 = v => (Number(v) || 0).toLocaleString("de-DE", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + " €";
const katName = id => (fin.kategorien.find(k => k.id === id) || {}).name || id;
const TYP_KURZ = { pdf: "PDF", xml: "XML", mail: "MAIL", msg: "MAIL", bild: "FOTO", unbekannt: "DATEI" };

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
  if (name === "papierkorb") ladePapierkorb();
  if (name === "fahrten") ladeFahrten();
  if (name === "anschaffungen") ladeAnlagen();
  if (name === "finanzen") ladeUebersicht();
  if (name === "euer") ladeEuer();
}

async function ladeAusgaben() {
  const jahr = fin.jahr;
  try {
    await ladeKategorien();
    const [liste, jahre, faellig] = await Promise.all([api(`ausgaben?jahr=${jahr}`), api("finanzen/jahre"), api("abos/faellig")]);
    if (jahr !== fin.jahr) return;      // inzwischen ein anderes Jahr gewählt
    fin.ausgaben = liste;
    fin.faellig = faellig;
    jahresAuswahl($("#ausgaben-jahr"), jahre, jahr);
  } catch (e) { return toast("Laden fehlgeschlagen: " + e.message, true); }
  renderAusgaben();
  ladePapierkorbAnzahl();
  ocrListeNachladen();
}

function renderAusgaben() {
  const neu = fin.ausgaben.filter(a => a.status === "neu");
  const abos = fin.faellig;
  const zumAbo = new Map(abos.filter(f => f.beleg).map(f => [f.beleg.id, f]));
  $("#ausgaben-neu-karte").classList.toggle("hidden", !neu.length && !abos.length);
  $("#ausgaben-neu-anzahl").textContent = [abos.length && `${abos.length} Abo${abos.length === 1 ? "" : "s"}`,
    neu.length && `${neu.length} Beleg${neu.length === 1 ? "" : "e"}`].filter(Boolean).join(" · ");
  $("#alle-pruefen").classList.toggle("hidden", !neu.length);
  $("#ausgaben-neu").innerHTML = abos.map(aboZeile).join("") + neu.map(a => {
    const e = a.erkannt || {};
    const erkannt = [e.erechnung && (e.erechnung.gutschrift ? "E-Rechnung (Gutschrift)" : "E-Rechnung"), e.betrag != null && "Gesamt", e.ust_betrag != null && "MwSt.", e.kategorie && "Kategorie"].filter(Boolean);
    const info = ocrLaeuft(a) ? "Text wird gelesen …"
      : erkannt.length ? `erkannt: ${erkannt.join(", ")}` : "nichts erkannt – bitte Werte eintragen";
    const zuAbo = zumAbo.get(a.id);
    return `<div class="neu-beleg${zuAbo ? " gehoert" : ""}" data-id="${a.id}">
      <div class="datei-icon">${TYP_KURZ[a.beleg_typ] || "DATEI"}</div>
      <div class="was"><strong>${esc(a.lieferant || a.beleg_name)}</strong>
        <small>${esc(a.beschreibung || a.beleg_name)} · ${fmtDate(a.belegdatum)} · ${info}${zuAbo ? ` · <b>gehört zum Abo ${esc(zuAbo.lieferant)} (oben)</b>` : ""}</small></div>
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
      <td>${fmtDate(a.bezahlt_am || a.belegdatum)}${a.gesperrt ? schlossChip(a.jahr) : ""}${a.abo_id ? ` <span class="chip-abo" title="aus einem Abo${a.beleg_datei ? "" : " – Beleg fehlt"}">ABO${a.beleg_datei ? "" : " · ohne Beleg"}</span>` : ""}${a.jahr !== (a.bezahlt_am || a.belegdatum || "").slice(0, 4)
        ? ` <span class="lock" title="Nach der 10-Tage-Regel dem Jahr ${a.jahr} zugeordnet">→ ${a.jahr}</span>` : ""}</td><td>${esc(a.lieferant)}</td>
      <td>${esc(a.beschreibung)}${a.privatanteil ? ` <small class="muted">(${a.privatanteil} % privat)</small>` : ""}</td>
      <td><span class="chip k-${a.kategorie}">${esc(a.kategorie_name)}</span></td>
      <td class="num">${euro2(a.betrag)}</td>
      <td>${a.beleg_datei ? `<a href="#" class="beleg-link" data-act="beleg" title="Beleg öffnen">📎</a>`
        : `<span class="muted" title="${esc(a.notiz || "ohne Beleg")}">—</span>`}</td>
      <td class="btns"><button type="button" class="small secondary" data-act="bearbeiten" title="${a.gesperrt ? "Ansehen" : "Bearbeiten"}">${a.gesperrt ? "Ansehen" : "✎"}</button></td>
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
  gesperrtZeile($("#ausgaben-body").closest("table"), fin.jahr);
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
  const res = await fetch("api/ausgaben/belege", { method: "POST", headers: SCHUTZ, body: fd });
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
  const gesamt = { neu: 0, doppelt: [], papierkorb: [], fehler: [] };
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
        gesamt.papierkorb.push(...(d.papierkorb || []));
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
    if (gesamt.papierkorb.length) {
      teile.push(`${gesamt.papierkorb.length} im Papierkorb gefunden`);
      papierkorbAnbieten(gesamt.papierkorb.map(x => x.id));
    }
    if (gesamt.fehler.length) {
      const namen = gesamt.fehler.length <= 3 ? ` (${gesamt.fehler.map(x => x.fehler ? `${x.datei}: ${x.fehler}` : x.datei).join(", ")})` : "";
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
const BELEG_ENDUNG = /\.(pdf|xml|eml|msg|mbox|jpe?g|png|heic|heif|webp)$/i;
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
  if (a && a.status === "papierkorb") {        // in einem anderen Fenster gelöscht
    toast("Dieser Beleg liegt im Papierkorb.", true);
    return naechsterOderListe();
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
  lesemodus($("#tab-beleg"), a && a.gesperrt ? Number(a.jahr) : null);      // abgeschlossenes Jahr: nur ansehen
  if (a && a.gesperrt) $("#beleg-titel").textContent = "Ausgabe ansehen";
  $("#notiz-hinweis").textContent = ohneBeleg ? "(Pflicht: warum gibt es keinen Beleg?)" : "(optional)";

  zeigeErkennung(a, neu);
  ocrImFormularVerfolgen();

  // Vorschau
  const v = $("#beleg-vorschau");
  if (!a || !a.beleg_datei) {
    v.innerHTML = `<div class="ohne-beleg"><b>Ohne Beleg</b><br>Für Ausgaben ohne Quittung (z. B. Parkautomat) bitte in der Notiz festhalten, warum es keinen Beleg gibt.</div>`;
    $("#beleg-original").textContent = "";
  } else {
    v.innerHTML = belegVorschauHtml(a);
    $("#beleg-original").innerHTML = `${a.beleg_typ === "mail" || a.beleg_typ === "msg" ? "Original-Mail" : a.beleg_typ === "xml" ? "Original-XML" : "Original"} wird unverändert gespeichert · `
      + `<a href="#" id="beleg-original-link">${a.beleg_typ === "xml" ? "Original herunterladen" : "Original öffnen"}</a>`
      + (a.beleg_typ === "pdf" && a.erkannt?.erechnung ? ` · <a href="#" id="beleg-daten-link">Rechnungsdaten anzeigen</a>` : "");
  }
  showTab("beleg");
  window.scrollTo(0, 0);
  const speichern = f.querySelector("[type=submit]");
  const feld = !f.elements.betrag.value ? f.elements.betrag : !f.elements.lieferant.value ? f.elements.lieferant : speichern;
  // Gibt es eine Warnung, nicht an ihr vorbei zum Knopf scrollen
  setTimeout(() => feld.focus({ preventScroll: feld === speichern && !!$("#beleg-hinweise").children.length }), 50);
}

function belegVorschauHtml(a) {
  const url = `api/ausgaben/${a.id}/ansicht`;
  return a.beleg_typ === "bild" ? `<img src="${url}" alt="Beleg" class="beleg-foto">`
    : a.beleg_typ === "unbekannt" ? `<div class="ohne-beleg">Keine Vorschau für diesen Dateityp.</div>`
    : `<iframe src="${url}" title="Beleg" ${a.beleg_typ === "pdf" ? "" : 'sandbox=""'}></iframe>`;
}

// Foto ohne Vorschau (z. B. HEIC ohne Umwandlung): Hinweis statt kaputtem Bild – als Listener, die CSP verbietet Inline-Handler
document.addEventListener("error", e => {
  if (!e.target.matches?.("img.beleg-foto")) return;
  const hinweis = document.createElement("div");
  hinweis.className = "ohne-beleg";
  hinweis.textContent = "Für dieses Foto ist keine Vorschau möglich – bitte über „Original öffnen“ ansehen.";
  e.target.replaceWith(hinweis);
}, true);

document.addEventListener("click", e => {
  if (e.target.id !== "beleg-original-link") return;
  e.preventDefault();
  belegOriginal(fin.aktuell);
});

// PDF mit eingebetteter E-Rechnung: zwischen sichtbarem PDF und Rechnungsdaten umschalten
document.addEventListener("click", e => {
  if (e.target.id !== "beleg-daten-link") return;
  e.preventDefault();
  const daten = e.target.dataset.an !== "1", a = fin.aktuell;
  e.target.dataset.an = daten ? "1" : "";
  e.target.textContent = daten ? "PDF anzeigen" : "Rechnungsdaten anzeigen";
  $("#beleg-vorschau").innerHTML = daten
    ? `<iframe src="api/ausgaben/${a.id}/ansicht?daten=1" title="Rechnungsdaten" sandbox=""></iframe>` : belegVorschauHtml(a);
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
  if (a?.status === "neu" && a.doppelt_verdacht && !confirm(`${doppeltText(a.doppelt_verdacht)}\n\nTrotzdem übernehmen?`)) return;
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
  const frage = a.status === "neu" ? `Beleg „${a.beleg_name || a.lieferant}“ verwerfen?\n\nEr kommt in den Papierkorb und lässt sich dort wiederherstellen.`
    : `Ausgabe ${a.lieferant} (${euro2(a.betrag)}) löschen?\n\nSie kommt mit Beleg in den Papierkorb, zählt nicht mehr mit und lässt sich dort wiederherstellen.`;
  if (!confirm(frage)) return;
  try {
    await api(`ausgaben/${a.id}`, { method: "DELETE" });
    toast(a.status === "neu" ? "Beleg in den Papierkorb gelegt" : "Ausgabe in den Papierkorb gelegt");
    naechsterOderListe();
  } catch (err) { toast(err.message, true); }
});


// ======================= Fahrten =======================

const fahrt = { jahr: String(new Date().getFullYear()), daten: null, aktuell: null, nachladen: null };
const km = v => v == null ? "–" : String(v).replace(".", ",");

async function ladeFahrten() {
  clearTimeout(fahrt.nachladen);
  const jahr = fahrt.jahr;
  try {
    const [daten, jahre] = await Promise.all([api(`fahrten?jahr=${jahr}`), api("finanzen/jahre")]);
    if (jahr !== fahrt.jahr) return;
    fahrt.daten = daten;
    jahresAuswahl($("#fahrten-jahr"), jahre, jahr);
  } catch (e) { return toast("Laden fehlgeschlagen: " + e.message, true); }
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
      <td>${fmtDate(f.datum)}${f.gesperrt ? schlossChip(f.datum.slice(0, 4)) : ""}</td>
      <td>${esc(f.anlass)}${f.rechnung_id ? `<small>${esc(f.kunde)}${f.rechnung_text ? " · " + esc(f.rechnung_text) : ""}${f.rechnung_storniert ? " · <b>storniert</b>" : ""}</small>` : ""}</td>
      <td>${esc(f.ziel_name || f.ziel.split(", ").slice(-1)[0].replace(/^\d{4,5}\s+/, "") || f.ziel)}<small>${esc(f.ziel)}</small></td>
      <td class="num">${f.km_einfach == null ? "–" : (f.hin_zurueck ? `2 × ${km(f.km_einfach)} = ${km(f.km_gesamt)}` : km(f.km_gesamt))}</td>
      <td class="num">${privat && f.betrag != null ? euro2(f.betrag) : "–"}</td>
      <td>${quelle(f)}</td>
      <td class="btns">${f.gesperrt ? `<button type="button" class="small secondary" data-act="bearbeiten" title="Ansehen">Ansehen</button>`
        : `<button type="button" class="small secondary" data-act="bearbeiten" title="Kilometer oder Ziel ändern">✎</button><button type="button" class="icon del" data-act="loeschen" title="${f.rechnung_id && f.quelle !== "hand" ? "Fahrt entfernen – für diese Rechnung wird dann keine Fahrt mehr angelegt" : "Fahrt löschen"}">✕</button>`}</td>
    </tr>`).join("")
    || `<tr><td colspan="7" class="hint">Noch keine Fahrten ${fahrt.jahr}. Sie entstehen automatisch mit jeder Rechnung – für ältere Rechnungen „Fahrten nachberechnen“.</td></tr>`;
  gesperrtZeile($("#fahrten-body").closest("table"), fahrt.jahr);
  $("#fahrten-nachberechnen").disabled = istZu(fahrt.jahr);
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
  $("#fahrt-titel").textContent = f ? (f.gesperrt ? "Fahrt ansehen" : "Fahrt bearbeiten") : "Fahrt ergänzen";
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
  lesemodus($("#fahrt-dialog"), f && f.gesperrt ? Number(f.datum.slice(0, 4)) : null);
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
  const jahr = anl.jahr;
  try {
    const [liste, jahre] = await Promise.all([api(`anlagen?jahr=${jahr}`), api("finanzen/jahre")]);
    if (jahr !== anl.jahr) return;
    anl.liste = liste;
    jahresAuswahl($("#anlagen-jahr"), [new Date().getFullYear() + 1, ...jahre], jahr);   // Abschreibung auch fürs nächste Jahr
  } catch (e) { return toast("Laden fehlgeschlagen: " + e.message, true); }
  $("#anlagen-kopf-afa").textContent = `Abschreibung ${anl.jahr}`;
  $("#anlagen-kopf-rest").textContent = `Restwert 31.12.${anl.jahr.slice(2)}`;
  $("#anlagen-body").innerHTML = anl.liste.map(a => {
    const kaufjahr = (a.anschaffung_am || "").slice(0, 4);
    const anteil = kaufjahr === anl.jahr && a.nutzungsdauer > 1 ? `<small>${13 - Number(a.anschaffung_am.slice(5, 7))} von 12 Monaten</small>` : "";
    return `<tr data-id="${a.id}">
      <td><b>${esc(a.bezeichnung)}</b>${a.gesperrt ? ` <span class="lock" title="Ein abgeschlossenes Jahr liegt ab dem Kauf – Kauf und Abschreibung stehen fest">🔒</span>` : ""}<small>${a.ausgabe_id ? `aus Ausgabe ${esc(a.ausgabe_lieferant || "")}${a.ausgabe_mit_beleg ? " · 📎" : ""}` : a.restwert_start != null ? "aus Vorjahren übernommen" : "von Hand erfasst"}${a.abgang_am ? ` · Abgang ${fmtDate(a.abgang_am)}` : ""}</small></td>
      <td>${a.anschaffung_am ? fmtDate(a.anschaffung_am) : `vor ${a.start_jahr}`}</td>
      <td class="num">${a.kosten != null ? euro2(a.kosten) : `<small>Restwert 1.1.${String(a.start_jahr).slice(2)}</small>${euro2(a.restwert_start)}`}</td>
      <td>${a.restwert_start != null ? `noch ${a.rest_nutzungsdauer} J. ab ${a.start_jahr}` : a.nutzungsdauer === 1 ? "1 Jahr" : `${a.nutzungsdauer} Jahre`}</td>
      <td class="num">${euro2(a.afa)}${anteil}</td>
      <td class="num">${a.abgang_am && a.abgang_am.startsWith(anl.jahr) ? `<small>Abgang: Restwert ${euro2(a.abgang_restwert)} · Erlös ${euro2(a.abgang_erloes)}</small>` : euro2(a.restwert_ende)}</td>
      <td class="btns"><button type="button" class="small secondary" data-act="bearbeiten" title="Bearbeiten">✎</button></td>
    </tr>`;
  }).join("") || `<tr><td colspan="7" class="hint">Keine Anschaffungen über 800 € in ${anl.jahr}.</td></tr>`;
  const summe = anl.liste.reduce((s, a) => s + a.afa, 0);
  gesperrtZeile($("#anlagen-body").closest("table"), anl.jahr);
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
  // Abgeschlossenes Jahr ab dem Kauf: Kauf und Abschreibung fest; Verkauf/Verschrottung später geht noch
  const box = $("#anlage-dialog");
  if (a && a.gesperrt) {
    const start = a.start_jahr || Number((a.anschaffung_am || "0").slice(0, 4));
    const jahr = Math.max(...[...abs.zu].filter(j => j >= start), start);
    const abgang = a.abgang_am ? Number(a.abgang_am.slice(0, 4)) : null;
    const zuAbgang = abgang ? Math.max(...[...abs.zu].filter(j => j >= abgang), abgang) : jahr;
    lesemodus(box, a.abgang_gesperrt ? zuAbgang : jahr, a.abgang_gesperrt ? {} : {
      felder: ["anschaffung_am", "kosten", "nutzungsdauer", "start_jahr", "restwert_start", "rest_nutzungsdauer"], knoepfe: false,
      text: `${jahr} ist abgeschlossen – Kauf und Abschreibung stehen fest. Einen Verkauf oder die Verschrottung kannst du noch eintragen.` });
    $("#anlage-modus").classList.add("hidden");
    $("#anlage-loeschen").classList.add("hidden");
  } else lesemodus(box, null);
  box.showModal();
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

async function ladeUebersicht() {
  const jahr = ue.jahr;
  try {
    const [daten, jahre] = await Promise.all([api(`finanzen/euer?jahr=${jahr}`), api("finanzen/jahre")]);
    if (jahr !== ue.jahr) return;
    ue.daten = daten;
    jahresAuswahl($("#finanzen-jahr"), jahre, jahr);
  } catch (e) { return toast("Laden fehlgeschlagen: " + e.message, true); }
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
  const jahr = ue.jahr;
  try {
    const [daten, jahre] = await Promise.all([api(`finanzen/euer?jahr=${jahr}`), api("finanzen/jahre")]);
    if (jahr !== ue.jahr) return;
    ue.daten = d = daten;
    jahresAuswahl($("#euer-jahr"), jahre, jahr);
  } catch (e) { return toast("Laden fehlgeschlagen: " + e.message, true); }
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
  if (d.abschluss) {
    if (d.abschluss.status === "zu") abs.zu.add(Number(ue.jahr)); else abs.zu.delete(Number(ue.jahr));
  }
  renderAbschlussBand(d.abschluss);
  $("#einnahme-neu").disabled = istZu(ue.jahr);
  $("#einnahmen-body").innerHTML = d.sonstige.map(x => `<tr data-id="${x.id}"><td>${fmtDate(x.datum)}</td><td>${esc(x.beschreibung)}</td>
      <td class="num">${euro2(x.betrag)}</td><td class="btns">${istZu(ue.jahr) ? "" : `<button type="button" class="icon del" title="Löschen">✕</button>`}</td></tr>`).join("")
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

// Startseite (seit 1.10 in app.js): nach Änderungen an Finanzen, Abos oder Abschluss neu zeichnen, falls sichtbar
function renderStartFinanzen() {
  if ($("#tab-start").classList.contains("active")) renderStart();
}

// ---------- Paperless: Einstellungen und Abholen ----------

function plTagAuswahl(tags, gewaehlt, name) {
  const sel = $("#einstellungen").elements.paperless_tag;
  const opt = (id, text) => `<option value="${esc(String(id))}"${String(id) === String(gewaehlt) ? " selected" : ""}>${esc(text)}</option>`;
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
    if (st.verworfen) teile.push(`${st.verworfen} verworfen, bleiben draußen`);
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
  zeigeUebergangen(st);
  const el = $("#ordner-stand");
  el.hidden = !st.ordner;
  if (!st.ordner) return;
  el.classList.toggle("warn", !!st.problem);
  el.innerHTML = st.problem ? `⚠ ${esc(st.problem)} – <a href="#" class="zu-einstellungen">Einstellungen</a>`
    : `↻ Belege-Ordner <b>${esc(st.ordner)}</b> wird automatisch eingelesen${st.laeuft ? " – gerade …" : st.geprueft ? ` · zuletzt ${uhrzeit(st.geprueft)} Uhr` : ""}`;
}

function zeigeUebergangen(st) {
  const el = $("#ordner-uebergangen"), liste = st.uebergangen || [], n = st.uebergangen_anzahl || 0;
  el.hidden = !st.ordner || !n;
  el.querySelector("summary").textContent = `⚠ ${n} Datei${n === 1 ? "" : "en"} im Belege-Ordner nicht eingelesen`;
  const html = liste.map(x => `<li><b>${esc(x.datei)}</b> – ${esc(x.grund)}</li>`).join("")
    + (n > liste.length ? `<li>… und ${n - liste.length} weitere</li>` : "");
  const ul = el.querySelector("ul");
  if (ul.dataset.html !== html) ul.innerHTML = ul.dataset.html = html;
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
  if (st.papierkorb?.length) papierkorbAnbieten(st.papierkorb);
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

function doppeltText(d) {
  const was = `${d.lieferant}${d.datum ? `, ${fmtDate(d.datum)}` : ""}${d.betrag != null ? `, ${euro2(d.betrag)}` : ""}${d.status === "neu" ? ", noch ungeprüft" : ""}`;
  return d.sicher ? `Diese Rechnung gibt es schon (${was}). Übernommen würde sie doppelt zählen – bitte eine von beiden verwerfen.`
    : `Vermutlich gibt es diese Rechnung schon in anderer Form (${was}). Dann bitte eine von beiden verwerfen – die E-Rechnung ist das Original.`;
}

function ocrLaeuft(a) { return !!a && a.status === "neu" && (a.ocr === "wartet" || a.ocr === "laeuft"); }

function zeigeErkennung(a, neu) {
  const e = a?.erkannt || {}, laeuft = ocrLaeuft(a);
  $("#ocr-stand").hidden = !laeuft;
  $("#ocr-stand").textContent = a?.ocr === "wartet" ? "Text wird gleich gelesen – du kannst die Werte auch schon eintragen."
    : "Text wird gelesen … – du kannst die Werte auch schon eintragen.";
  $("#ocr-starten").hidden = laeuft || !neu || !a || a.betrag != null || !!e.erechnung || !["bild", "pdf"].includes(a.beleg_typ);
  $("#beleg-hinweise").innerHTML = laeuft ? "" : [...(neu && a?.doppelt_verdacht ? [doppeltText(a.doppelt_verdacht)] : []), ...(e.hinweise || [])].map(h => `<li class="gelb">${esc(h)}</li>`).join("");
  // nur, solange das Feld noch den erkannten Wert hat – nicht unter selbst Getipptem
  $("#erkannt-lieferant").textContent = neu && a && e.lieferant && $("#beleg-form").elements.lieferant.value === e.lieferant ? (e.erechnung && e.lieferant === e.erechnung.verkaeufer ? "Verkäufer laut E-Rechnung"
    : a.beleg_typ === "mail" || a.beleg_typ === "msg" ? "erkannt am Absender der Mail" : "aus dem Briefkopf übernommen – bitte prüfen") : "";
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

// ---------- Papierkorb ----------

const papierkorb = { liste: [], angebot: new Set(), abgelehnt: new Set(), vorschau: null };

async function ladePapierkorbAnzahl() {
  try {
    const { anzahl } = await api("papierkorb/anzahl");
    $("#papierkorb-anzahl").textContent = anzahl ? ` (${anzahl})` : "";
  } catch (_) { /* nur die Zahl am Knopf */ }
}

async function ladePapierkorb() {
  try { papierkorb.liste = await api("papierkorb"); }
  catch (e) { return toast("Laden fehlgeschlagen: " + e.message, true); }
  $("#papierkorb-leeren").classList.toggle("hidden", !papierkorb.liste.length);
  $("#papierkorb-liste").innerHTML = papierkorb.liste.map(a => {
    const wann = a.geloescht_am ? `gelöscht am ${fmtDate(a.geloescht_am.slice(0, 10))}` : "aus der Zeit vor 1.6 im Belege-Ordner gefunden";
    const war = a.status_vorher === "ok" ? `war übernommen (${esc(a.jahr)})` : "ungeprüft";
    return `<div class="neu-beleg papierkorb-zeile" data-id="${a.id}">
      <div class="datei-icon">${a.beleg_datei ? TYP_KURZ[a.beleg_typ] || "DATEI" : "OHNE"}</div>
      <div class="was"><strong>${esc(a.lieferant || a.beleg_name || "Ausgabe")}</strong>
        <small>${esc(a.beschreibung || a.beleg_name || a.notiz || "")}${a.belegdatum ? ` · ${fmtDate(a.belegdatum)}` : ""}</small>
        <small>${war} · ${wann}</small></div>
      <div class="betrag">${a.betrag != null ? euro2(a.betrag) : "– €"}</div>
      <div class="papierkorb-knoepfe">
        ${a.beleg_datei ? `<button type="button" class="small secondary" data-act="vorschau">Vorschau</button>` : ""}
        <button type="button" class="small" data-act="holen">Wiederherstellen</button>
        <button type="button" class="small secondary danger-text" data-act="endgueltig">Endgültig löschen</button>
      </div>
    </div>`;
  }).join("") || `<p class="hint">Der Papierkorb ist leer.</p>`;
}

async function papierkorbHolen(a) {
  if (a.aehnlich && !confirm(`Es gibt schon eine Ausgabe mit gleichem Betrag und Datum (${a.aehnlich}).\n\n`
    + "Ist das derselbe Beleg, würde er doppelt zählen. Trotzdem wiederherstellen?")) return null;
  return api(`papierkorb/${a.id}/wiederherstellen`, { method: "POST" });
}

async function papierkorbEinenHolen(a) {
  try {
    const neu = await papierkorbHolen(a);
    if (!neu) return;
    toast(neu.status === "ok" ? `Wiederhergestellt – zählt wieder in der EÜR ${neu.jahr}` : "Wiederhergestellt unter „Neu – bitte prüfen“");
    $("#papierkorb-dialog").close();
    await ladePapierkorb();
    ladePapierkorbAnzahl();
  } catch (e) { toast(e.message, true); }
}

$("#papierkorb-oeffnen").addEventListener("click", () => showTab("papierkorb"));
$("#papierkorb-zurueck").addEventListener("click", () => showTab("ausgaben"));
$("#papierkorb-liste").addEventListener("click", async e => {
  const act = e.target.closest("[data-act]")?.dataset.act;
  const id = Number(e.target.closest("[data-id]")?.dataset.id);
  const a = papierkorb.liste.find(x => x.id === id);
  if (!act || !a) return;
  if (act === "holen") return papierkorbEinenHolen(a);
  if (act === "vorschau") {
    papierkorb.vorschau = a;
    $("#papierkorb-dialog-titel").textContent = a.lieferant || a.beleg_name || "Beleg";
    $("#papierkorb-vorschau").innerHTML = belegVorschauHtml(a);
    return $("#papierkorb-dialog").showModal();
  }
  if (act === "endgueltig") {
    if (!confirm(`„${a.lieferant || a.beleg_name || "Ausgabe"}“ endgültig löschen?\n\nDie Belegdatei in der App wird gelöscht. Das lässt sich nicht rückgängig machen.`
      + (a.status_vorher === "ok" ? "\n\nDiese Ausgabe war schon übernommen: Buchungsbelege muss man in der Regel 8 Jahre aufbewahren." : ""))) return;
    try {
      await api(`papierkorb/${a.id}`, { method: "DELETE" });
      toast("Endgültig gelöscht");
      await ladePapierkorb();
    } catch (err) { toast(err.message, true); }
  }
});
$("#papierkorb-dialog-zu").addEventListener("click", () => $("#papierkorb-dialog").close());
$("#papierkorb-dialog-holen").addEventListener("click", () => papierkorb.vorschau && papierkorbEinenHolen(papierkorb.vorschau));
$("#papierkorb-dialog").addEventListener("close", () => { $("#papierkorb-vorschau").innerHTML = ""; papierkorb.vorschau = null; });

$("#papierkorb-leeren").addEventListener("click", async () => {
  const liste = papierkorb.liste, gebucht = liste.filter(a => a.status_vorher === "ok").length;
  if (!confirm(`${liste.length === 1 ? "1 Eintrag" : `${liste.length} Einträge`} endgültig löschen?\n\nDie Belegdateien in der App werden gelöscht. Das lässt sich nicht rückgängig machen.`
    + (gebucht ? `\n\n${gebucht} davon ${gebucht === 1 ? "war" : "waren"} schon übernommen: Buchungsbelege muss man in der Regel 8 Jahre aufbewahren.` : ""))) return;
  try {
    const { anzahl } = await api("papierkorb/leeren", { method: "POST", body: { ids: liste.map(a => a.id) } });
    toast(`${anzahl} endgültig gelöscht`);
    await ladePapierkorb();
  } catch (e) { toast(e.message, true); }
});

// Derselbe Beleg noch einmal hochgeladen bzw. in den Belege-Ordner gelegt
function papierkorbAnbieten(ids) {
  ids.forEach(id => { if (!papierkorb.abgelehnt.has(id)) papierkorb.angebot.add(id); });
  zeigePapierkorbAngebot();
}

function zeigePapierkorbAngebot() {
  const n = papierkorb.angebot.size;
  $("#papierkorb-angebot").classList.toggle("hidden", !n);
  $("#papierkorb-angebot-text").textContent = n === 1 ? "Dieser Beleg liegt schon im Papierkorb."
    : `${n} dieser Belege liegen schon im Papierkorb.`;
}

$("#papierkorb-angebot-holen").addEventListener("click", async () => {
  let n = 0;
  try {
    const liste = await api("papierkorb");
    for (const id of [...papierkorb.angebot]) {
      const a = liste.find(x => x.id === id);
      if (a) {
        if (await papierkorbHolen(a)) n++;
        else papierkorb.abgelehnt.add(id);
      }
      papierkorb.angebot.delete(id);
    }
  } catch (e) { toast(e.message, true); }
  zeigePapierkorbAngebot();
  if (n) toast(`${n} wiederhergestellt`);
  ladeAusgaben();
});
$("#papierkorb-angebot-ansehen").addEventListener("click", () => {
  papierkorb.angebot.clear();
  zeigePapierkorbAngebot();
  showTab("papierkorb");
});
$("#papierkorb-angebot-zu").addEventListener("click", () => {
  papierkorb.angebot.forEach(id => papierkorb.abgelehnt.add(id));
  papierkorb.angebot.clear();
  zeigePapierkorbAngebot();
});


// ======================= Jahresabschluss (seit 1.8) =======================
// Ein Jahr wird nie von selbst gesperrt – nur über „Jahr abschließen“. Die Sperre selbst sitzt im Server.

const abs = { zu: new Set(), jahr: null, schritt: 1, daten: null, zurueck: null };

async function ladeAbschlussZu() {
  try { abs.zu = new Set(await api("abschluss/zu")); } catch (_) { /* ohne Kennzeichnung weiter */ }
  return abs.zu;
}
const istZu = j => abs.zu.has(Number(j));

function gesperrtZeile(vor, jahr) {
  const da = vor.previousElementSibling?.classList.contains("gesperrt-zeile") ? vor.previousElementSibling : null;
  if (!istZu(jahr)) { da?.remove(); return; }
  const z = da || document.createElement("div");
  z.className = "gesperrt-zeile";
  z.innerHTML = `<span>🔒 <b>${jahr} ist abgeschlossen</b> – Einträge lassen sich ansehen, aber nicht ändern.</span>
    <a href="#" data-abschluss-oeffnen="${jahr}">${jahr} wieder öffnen</a>`;
  if (!da) vor.before(z);
}
const schlossChip = j => ` <span class="lock" title="${j} ist abgeschlossen">🔒 ${j}</span>`;

/* Editor nur zum Ansehen: Felder gestrichelt, Speichern/Löschen weg, Hinweis mit „wieder öffnen“.
   felder: nur diese sperren (sonst alle); jahr = null hebt den Lesemodus auf. */
function lesemodus(box, jahr, { felder = null, knoepfe = true, text = null } = {}) {
  box.querySelector(".gesperrt-zeile.lesen")?.remove();
  box.querySelectorAll(".nur-lesen").forEach(x => x.classList.remove("nur-lesen"));
  box.querySelectorAll("[data-ja-aus]").forEach(x => { x.hidden = false; delete x.dataset.jaAus; });
  box.querySelectorAll("[data-ja-readonly]").forEach(x => { x.readOnly = false; x.tabIndex = 0; delete x.dataset.jaReadonly; });
  if (!jahr) return;
  const ziele = felder ? felder.map(n => box.querySelector(`[name="${n}"]`)).filter(Boolean) : [...box.querySelectorAll("input, select, textarea")];
  for (const f of ziele) {
    f.classList.add("nur-lesen");
    if ("readOnly" in f && f.tagName !== "SELECT") { f.readOnly = true; f.dataset.jaReadonly = "1"; }
  }
  if (!felder) box.querySelector("form")?.classList.add("nur-lesen");
  if (knoepfe) {
    box.querySelectorAll("button[type=submit], .ja-weg").forEach(b => { if (!b.hidden) { b.hidden = true; b.dataset.jaAus = "1"; } });
  }
  const ziel = box.querySelector(".actions") || box.querySelector("form") || box;
  ziel.insertAdjacentHTML("beforebegin", `<div class="gesperrt-zeile lesen"><span>🔒 ${text || `${jahr} ist abgeschlossen – nur ansehen.`}</span>
    <a href="#" data-abschluss-oeffnen="${jahr}">${jahr} wieder öffnen</a></div>`);
}

// ---------- EÜR: Band oben ----------
function renderAbschlussBand(st) {
  const b = $("#abschluss-band");
  if (!st) { b.classList.add("hidden"); return; }
  const j = st.jahr, a = st.aktuell;
  b.classList.remove("hidden");
  b.classList.toggle("zu", st.status === "zu");
  b.classList.toggle("abweichung", !!st.abweichung);
  $("#euer-pruefliste-karte").classList.toggle("hidden", st.status === "zu");
  if (st.status === "zu") {
    const summe = a.pruefsumme;
    b.innerHTML = `<div><b>🔒 ${j} abgeschlossen</b> am ${fmtDate(a.abgeschlossen_am.slice(0, 10))} · Gewinn ${euro2(a.gewinn)}
        <p class="hint">Fassung ${a.fassung} · Prüfsumme ${summe.slice(0, 4)}…${summe.slice(-4)}${st.abweichung ? " · <b>⚠ Die EÜR weicht heute vom Abschluss ab</b> (z. B. durch eine geänderte Berechnung in einer neuen Version) – bitte prüfen" : ""}</p></div>
      <div class="knoepfe"><button type="button" class="secondary" data-abschluss="paket">⇩ Paket</button>
        <button type="button" class="secondary" data-abschluss="blatt">Abschlussblatt</button>
        <a href="#" data-abschluss-oeffnen="${j}">${j} wieder öffnen</a></div>`;
  } else if (st.status === "offen") {
    const wieder = st.fassungen.length ? ` Zuletzt wieder geöffnet am ${fmtDate(st.fassungen.at(-1).geoeffnet_am.slice(0, 10))}: „${esc(st.fassungen.at(-1).grund)}“.` : "";
    b.innerHTML = `<div><b>${j} ist noch offen</b><p class="hint">Wenn alles drin ist, kannst du das Jahr abschließen. Bis dahin lässt sich alles ändern – ein Jahr wird nie von selbst gesperrt.${wieder}</p></div>
      <div class="knoepfe"><button type="button" data-abschluss="start">🔒 ${j} abschließen …</button></div>`;
  } else {
    b.innerHTML = `<div><b>${j} läuft noch</b><p class="hint">Abschließen geht ab dem ${fmtDate(st.abschliessbar_ab)} – nach den 10 Tagen um den Jahreswechsel.</p></div>`;
  }
  b.dataset.jahr = j;
}

// ---------- Assistent ----------
function schrittAnzeigen(n) {
  abs.schritt = n;
  $$("#abschluss-schritte li").forEach(li => {
    const s = Number(li.dataset.schritt);
    li.classList.toggle("an", s === n);
    li.classList.toggle("fertig", s < n);
    li.querySelector("b").textContent = s < n ? "✓" : s;
  });
}

async function abschlussStarten(jahr) {
  abs.jahr = Number(jahr);
  $("#abschluss-titel").textContent = `${jahr} abschließen`;
  zurueckKnopf(null);
  await abschlussSchritt1();
  if (!$("#abschluss-dialog").open) $("#abschluss-dialog").showModal();
}

async function abschlussLaden() {
  abs.daten = await api(`abschluss/${abs.jahr}/pruefung`);
  return abs.daten;
}

async function abschlussSchritt1() {
  let p;
  try { p = await abschlussLaden(); } catch (e) { return toast(e.message, true); }
  schrittAnzeigen(1);
  const zeichen = { rot: "✕", gelb: "?", ok: "✓", info: "ℹ" };
  const aktion = x => {
    if (x.aktion) return `<a href="#" data-abschluss-ansehen="${x.aktion}">${x.aktion === "bezahlt_am" ? "nachtragen" : "ansehen"}</a>`;
    if (x.art === "offen") return `<div class="wahl" data-rechnung="${x.id}"><button type="button" class="small secondary an" data-wahl="offen">noch offen</button>
      <button type="button" class="small secondary" data-wahl="bezahlt">bezahlt am …</button></div>`;
    if (x.art === "zehn_tage") return `<div class="wahl" data-ausgabe="${x.id}">${x.jahre.map(j =>
      `<button type="button" class="small secondary${j === x.gewaehlt ? " an" : ""}" data-jahr="${j}">${j}</button>`).join("")}</div>`;
    if (x.art === "einstellungen") return `<a href="#" data-abschluss-ansehen="einstellungen">ändern</a>`;
    return "<span></span>";
  };
  $("#abschluss-inhalt").innerHTML = `<ul class="ja-liste">${p.punkte.map(x => `<li class="${x.stufe}"><span class="z">${zeichen[x.stufe]}</span>
      <div>${esc(x.text)}${x.klein ? `<small>${esc(x.klein)}</small>` : ""}</div>${aktion(x)}</li>`).join("")}</ul>
    <p class="hint">${p.offen ? `Noch ${p.offen} rot markierte${p.offen === 1 ? "r Punkt" : " Punkte"}: „ansehen“ öffnet die Stelle, unten rechts geht es zurück zum Abschluss.`
      : "Alles erledigt. Die gelben Punkte bitte kurz ansehen – ein Klick ändert die Antwort sofort."}</p>`;
  $("#abschluss-aktionen").innerHTML = `<button type="button" class="secondary" data-abschluss="schliessen">Später</button>
    <button type="button" data-abschluss="weiter2"${p.offen ? " disabled" : ""}>Weiter →</button>`;
}

function abschlussSchritt2() {
  const p = abs.daten, z = p.zahlen, v = p.vorjahr, j = abs.jahr;
  schrittAnzeigen(2);
  const pz = (a, b) => (b ? `${a >= b ? "+" : "−"} ${Math.abs(Math.round((a - b) / Math.abs(b) * 100))} %` : "");
  const g = p.grenzen[0];
  $("#abschluss-inhalt").innerHTML = `<div class="ja-kacheln"><div><b>${z.anzahl_rechnungen}</b>Zahlungseingänge</div><div><b>${z.ausgaben_anzahl}</b>Ausgaben</div>
      <div><b>${z.fahrten_anzahl}</b>Fahrten</div><div><b>${z.anlagen_anzahl}</b>Anschaffung${z.anlagen_anzahl === 1 ? "" : "en"}</div></div>
    <table class="ja-zahlen"><thead><tr><th></th><th>${j}</th><th>${j - 1}</th><th>Änderung</th></tr></thead><tbody>
      <tr><td>Einnahmen</td><td>${euro2(z.einnahmen)}</td><td>${euro2(v.einnahmen)}</td><td class="pl">${pz(z.einnahmen, v.einnahmen)}</td></tr>
      <tr><td>Ausgaben</td><td>${euro2(z.ausgaben)}</td><td>${euro2(v.ausgaben)}</td><td class="pl">${pz(z.ausgaben, v.ausgaben)}</td></tr>
      ${z.afa || v.afa ? `<tr><td>&nbsp;&nbsp;davon Abschreibungen</td><td>${euro2(z.afa)}</td><td>${euro2(v.afa)}</td><td class="pl"></td></tr>` : ""}
      ${z.fahrtkosten || v.fahrtkosten ? `<tr><td>&nbsp;&nbsp;davon Fahrten (${z.km.toLocaleString("de-DE")} km)</td><td>${euro2(z.fahrtkosten)}</td><td>${euro2(v.fahrtkosten)}</td><td class="pl"></td></tr>` : ""}
      <tr class="gewinn"><td>${z.gewinn >= 0 ? "Gewinn" : "Verlust"}</td><td>${euro2(z.gewinn)}</td><td>${euro2(v.gewinn)}</td>
        <td class="pl">${z.gewinn >= v.gewinn ? "+" : "−"} ${euro2(Math.abs(z.gewinn - v.gewinn))}</td></tr></tbody></table>
    ${g ? `<ul class="ja-liste"><li class="${g.stufe === "ok" ? "ok" : "gelb"}"><span class="z">${g.stufe === "ok" ? "✓" : "!"}</span><div>${esc(g.text)}</div><span></span></li></ul>` : ""}
    <p class="hint">Sieht etwas komisch aus? „Später“, den Eintrag korrigieren und neu starten – noch ist nichts gesperrt.</p>`;
  $("#abschluss-aktionen").innerHTML = `<button type="button" class="secondary" data-abschluss="zurueck1">← Zurück</button>
    <button type="button" data-abschluss="weiter3">Stimmt so →</button>`;
}

function abschlussSchritt3() {
  const j = abs.jahr;
  schrittAnzeigen(3);
  $("#abschluss-inhalt").innerHTML = `<p>Die App legt ein Paket an und sperrt ${j} gegen Änderungen.</p>
    <div class="paket"><b>📦 Jahresabschluss_${j}_Fassung_${(abs.daten.status.fassungen.at(-1)?.fassung || 0) + 1}.zip</b><ul>
      <li>Abschlussblatt (PDF) mit allen Zahlen und Prüfsumme</li>
      <li>EÜR, Rechnungen, Einnahmen, Ausgaben, Fahrten, Anlagenverzeichnis (Tabellen)</li>
      <li>alle Rechnungen und Belege von ${j} im Original</li></ul></div>
    <ul class="ja-liste">
      <li><span class="z">✓</span><div>Ansehen, herunterladen und Rechnungen erneut schicken geht weiter</div><span></span></li>
      <li><span class="z">✓</span><div>Offene Rechnungen von ${j} kannst du später als bezahlt markieren – das ändert ${j} nicht</div><span></span></li>
      <li><span class="z">🔒</span><div>Ändern, löschen und neue Einträge mit Datum ${j} gehen erst nach „${j} wieder öffnen“</div><span></span></li></ul>
    <label class="ja-bestaetigen"><input type="checkbox" id="abschluss-geprueft"> Ich habe die Zahlen geprüft.</label>`;
  $("#abschluss-aktionen").innerHTML = `<button type="button" class="secondary" data-abschluss="zurueck2">← Zurück</button>
    <button type="button" data-abschluss="abschliessen" disabled>🔒 ${j} abschließen</button>`;
  $("#abschluss-geprueft").addEventListener("change", e => { $("[data-abschluss=abschliessen]").disabled = !e.target.checked; });
}

async function abschlussAusfuehren(btn) {
  btn.disabled = true;
  btn.textContent = "Paket wird erstellt …";
  try {
    await api(`abschluss/${abs.jahr}`, { method: "POST", body: { bestaetigt: true } });
  } catch (e) {
    btn.disabled = false;
    btn.textContent = `🔒 ${abs.jahr} abschließen`;
    return toast(e.message, true);
  }
  $("#abschluss-dialog").close();
  await ladeAbschlussZu();
  toast(`🔒 ${abs.jahr} abgeschlossen – Paket und Abschlussblatt liegen unter EÜR & Export.`);
  ue.jahr = String(abs.jahr);
  ladeEuer();
  renderStartFinanzen();
}

function zurueckKnopf(jahr) {
  $(".ja-zurueck")?.remove();
  abs.zurueck = jahr;
  if (jahr) document.body.insertAdjacentHTML("beforeend",
    `<button type="button" class="ja-zurueck" data-abschluss="zurueck-assistent">← Zurück zum Abschluss ${jahr}</button>`);
}

function jahrWaehlen(sel, jahr) {
  const s = $(sel);
  if (s && [...s.options].some(o => o.value === String(jahr)) && s.value !== String(jahr)) {
    s.value = String(jahr);
    s.dispatchEvent(new Event("change"));
  }
}

$("#abschluss-dialog").addEventListener("click", async e => {
  const w = e.target.closest(".wahl button");
  if (w) {
    const box = w.closest(".wahl");
    try {
      if (box.dataset.ausgabe) {
        await api(`ausgaben/${box.dataset.ausgabe}/euer-jahr`, { method: "PUT", body: { jahr: Number(w.dataset.jahr) } });
        toast(`Zählt jetzt zu ${w.dataset.jahr}`);
        return abschlussSchritt1();
      }
      if (w.dataset.wahl === "offen") { box.querySelectorAll("button").forEach(b => b.classList.toggle("an", b === w)); box.querySelector("input")?.remove(); return; }
      if (w.dataset.wahl === "bezahlt" && !box.querySelector("input")) {
        box.insertAdjacentHTML("beforeend", `<input type="date" aria-label="Bezahlt am" max="${today()}"><button type="button" class="small" data-wahl="speichern">✓</button>`);
        box.querySelectorAll("button").forEach(b => b.classList.toggle("an", b === w));
        return box.querySelector("input").focus();
      }
      if (w.dataset.wahl === "speichern") {
        const datum = box.querySelector("input").value;
        if (!datum) return toast("Bitte das Datum des Zahlungseingangs eintragen.", true);
        await api(`rechnungen/${box.dataset.rechnung}/bezahlt`, { method: "PATCH", body: { bezahlt: true } });
        await api(`rechnungen/${box.dataset.rechnung}/bezahlt_am`, { method: "PUT", body: { bezahlt_am: datum } });
        toast("Als bezahlt eingetragen");
        state.rechnungen = [];
        return abschlussSchritt1();
      }
    } catch (err) { return toast(err.message, true); }
  }
  const ansehen = e.target.closest("[data-abschluss-ansehen]");
  if (ansehen) {
    e.preventDefault();
    const ziel = ansehen.dataset.abschlussAnsehen;
    $("#abschluss-dialog").close();
    zurueckKnopf(abs.jahr);
    if (ziel === "bezahlt_am") return oeffneBezahltAm();
    if (ziel === "einstellungen") {
      $("#einstellungen-btn").click();
      setTimeout(() => { $("#jahre-einstellungen").open = true; $("#jahre-einstellungen").scrollIntoView({ block: "center" }); }, 500);
      return;
    }
    showTab(ziel);
    setTimeout(() => jahrWaehlen(`#${ziel}-jahr`, abs.jahr), 200);
  }
});

document.addEventListener("click", e => {
  const b = e.target.closest("[data-abschluss]");
  const auf = e.target.closest("[data-abschluss-oeffnen]");
  if (auf) { e.preventDefault(); return wiederOeffnen(Number(auf.dataset.abschlussOeffnen)); }
  if (!b) return;
  e.preventDefault();
  const jahr = Number($("#abschluss-band").dataset.jahr);
  switch (b.dataset.abschluss) {
    case "start": return abschlussStarten(jahr);
    case "schliessen": return $("#abschluss-dialog").close();
    case "weiter2": return abschlussSchritt2();
    case "zurueck1": return abschlussSchritt1();
    case "weiter3": return abschlussSchritt3();
    case "zurueck2": return abschlussSchritt2();
    case "abschliessen": return abschlussAusfuehren(b);
    case "paket": return ladeHerunter(`api/abschluss/${jahr}/paket`);
    case "blatt": return zeigePdf(`api/abschluss/${jahr}/blatt`);
    case "zurueck-assistent": {
      const j = abs.zurueck;
      zurueckKnopf(null);
      document.querySelectorAll("dialog[open]").forEach(d => d.close());
      showTab("euer");
      ue.jahr = String(j);
      ladeEuer();
      return abschlussStarten(j);
    }
    case "hinweis": {
      showTab("euer");
      ue.jahr = b.dataset.jahr;
      ladeEuer();
      return abschlussStarten(Number(b.dataset.jahr));
    }
    case "hinweis-aus":
      api("abschluss/hinweis-aus", { method: "POST", body: { jahr: Number(b.dataset.jahr) } }).catch(() => {});
      b.closest("li")?.remove();
      return toast("Hinweis ausgeblendet – unter Finanzen → EÜR & Export bleibt der Knopf.");
  }
});

// ---------- Wieder öffnen ----------
async function wiederOeffnen(jahr) {
  let u;
  try { u = await api("abschluss"); } catch (e) { return toast(e.message, true); }
  const st = u.jahre.find(x => x.jahr === jahr);
  const d = $("#oeffnen-dialog");
  d.dataset.jahr = jahr;
  $("#oeffnen-titel").textContent = `${jahr} wieder öffnen`;
  $("#oeffnen-text").textContent = `Danach lässt sich ${jahr} wieder ändern. Das Paket von Fassung ${st?.aktuell?.fassung || 1} bleibt erhalten; `
    + "beim nächsten Abschluss zeigt das Abschlussblatt, warum geöffnet wurde und was sich geändert hat.";
  $("#oeffnen-vorschlaege").innerHTML = u.vorschlaege.map(t => `<button type="button" class="secondary">${esc(t)}</button>`).join("")
    + u.gruende.map(t => `<button type="button" class="secondary eigen" title="selbst eingegeben">${esc(t)}</button>`).join("");
  $("#oeffnen-grund").value = "";
  $("#oeffnen-ok").textContent = `${jahr} wieder öffnen`;
  grundPruefen();
  document.querySelectorAll("dialog[open]").forEach(x => x.close());
  d.showModal();
  $("#oeffnen-grund").focus();
}
const grundTeile = () => $("#oeffnen-grund").value.split(" · ").map(s => s.trim()).filter(Boolean);
function grundPruefen() {
  $("#oeffnen-ok").disabled = !$("#oeffnen-grund").value.trim();
  const teile = grundTeile();
  $$("#oeffnen-vorschlaege button").forEach(b => b.classList.toggle("an", teile.includes(b.textContent)));
}
$("#oeffnen-vorschlaege").addEventListener("click", e => {
  const b = e.target.closest("button");
  if (!b) return;
  const teile = grundTeile();
  const i = teile.indexOf(b.textContent);
  if (i >= 0) teile.splice(i, 1); else teile.push(b.textContent);
  $("#oeffnen-grund").value = teile.join(" · ");
  grundPruefen();
  $("#oeffnen-grund").focus();
});
$("#oeffnen-grund").addEventListener("input", grundPruefen);
$("#oeffnen-abbrechen").addEventListener("click", () => $("#oeffnen-dialog").close());
$("#oeffnen-ok").addEventListener("click", async () => {
  const jahr = Number($("#oeffnen-dialog").dataset.jahr);
  try { await api(`abschluss/${jahr}/oeffnen`, { method: "POST", body: { grund: $("#oeffnen-grund").value } }); }
  catch (e) { return toast(e.message, true); }
  $("#oeffnen-dialog").close();
  await ladeAbschlussZu();
  toast(`${jahr} ist wieder offen – ändern und danach erneut abschließen.`);
  const aktiv = document.querySelector("section.tab.active")?.id?.replace("tab-", "");
  if (aktiv === "euer") ladeEuer();
  else if (aktiv === "ausgaben") ladeAusgaben();
  else if (aktiv === "fahrten") ladeFahrten();
  else if (aktiv === "anschaffungen") ladeAnlagen();
  else if (aktiv === "liste") loadListe();
});

// ---------- Einstellungen: Kleinunternehmer und Fahrzeug je Jahr ----------
async function ladeJahreEinstellungen() {
  let u;
  try { u = await api("abschluss"); } catch (_) { return; }
  const aktuell = new Date().getFullYear();
  const jahre = u.jahre.filter(x => x.jahr < aktuell).reverse();
  $("#jahre-einstellungen").hidden = !jahre.length;
  const fz = v => v === "betrieb" ? "Betriebsfahrzeug" : "Privatfahrzeug";
  $("#jahre-tabelle").innerHTML = `<table class="jahre"><thead><tr><th>Jahr</th><th>Kleinunternehmer</th><th>Fahrzeug</th><th></th></tr></thead><tbody>${jahre.map(x =>
    x.status === "zu"
      ? `<tr><td>${x.jahr}</td><td>${x.kleinunternehmer ? "✓ ja" : "nein"}</td><td>${fz(x.fahrzeug)}</td><td><span class="lock">🔒 abgeschlossen</span></td></tr>`
      : `<tr data-jahr="${x.jahr}"><td>${x.jahr}</td><td><label class="inline" style="margin:0"><input type="checkbox" data-k="kleinunternehmer"${x.kleinunternehmer ? " checked" : ""}> ja</label></td>
         <td><select data-k="fahrzeug"><option value="privat"${x.fahrzeug !== "betrieb" ? " selected" : ""}>Privatfahrzeug</option>
           <option value="betrieb"${x.fahrzeug === "betrieb" ? " selected" : ""}>Betriebsfahrzeug</option></select></td><td><span class="hint">offen</span></td></tr>`).join("")}</tbody></table>`;
}
$("#jahre-tabelle").addEventListener("change", async e => {
  const tr = e.target.closest("tr[data-jahr]");
  if (!tr) return;
  const body = { kleinunternehmer: tr.querySelector("[data-k=kleinunternehmer]").checked, fahrzeug: tr.querySelector("[data-k=fahrzeug]").value };
  try {
    await api(`abschluss/${tr.dataset.jahr}/einstellungen`, { method: "PUT", body });
    toast(`${tr.dataset.jahr}: ${body.kleinunternehmer ? "Kleinunternehmer" : "umsatzsteuerpflichtig"} · ${body.fahrzeug === "betrieb" ? "Betriebsfahrzeug" : "Privatfahrzeug"} gespeichert`);
  } catch (err) { toast(err.message, true); ladeJahreEinstellungen(); }
});
$("#einstellungen-btn").addEventListener("click", () => ladeJahreEinstellungen());

// Gesperrter Editor: Enter in einem Feld schickt nichts ab
document.addEventListener("submit", e => {
  if (e.target.classList.contains("nur-lesen")) { e.preventDefault(); e.stopImmediatePropagation(); }
}, true);

ladeAbschlussZu();


// ======================= Abos – wiederkehrende Ausgaben (seit 1.9) =======================
// Fällige Abbuchungen stehen unter „Neu – bitte prüfen“; erst nach dem Bestätigen gibt es eine Ausgabe.

const abo = { daten: null, aktuell: null };

function aboZeile(f) {
  const gesperrt = f.gesperrt;
  const alt = f.datum.slice(0, 4) < String(new Date().getFullYear());
  const treffer = f.beleg || f.vorhanden;
  const ok = f.beleg ? "✓ Mit Beleg bestätigen" : f.vorhanden ? "✓ Damit verknüpfen" : "✓ Bestätigen";
  return `<div class="neu-beleg abo" data-abo="${f.abo_id}" data-datum="${f.datum}">
    <div class="datei-icon">ABO</div>
    <div class="was"><strong>${esc(f.lieferant)}</strong>
      <small>${esc(f.beschreibung || f.rhythmus_name)} · fällig ${fmtDate(f.datum)}${alt ? " · <b>noch nicht bestätigt</b>" : ""}${f.zehn_tage ? ` · zählt nach der 10-Tage-Regel zu ${f.zehn_tage}` : ""}</small>
      ${f.beleg ? `<small class="treffer">Beleg gefunden: ${esc(f.beleg.name || f.beleg.lieferant)} vom ${fmtDate(f.beleg.datum)} – ${euro2(f.beleg.betrag)}</small>` : ""}
      ${f.vorhanden ? `<small class="treffer">Schon erfasst: Ausgabe ${esc(f.vorhanden.lieferant)} vom ${fmtDate(f.vorhanden.datum)} – ${euro2(f.vorhanden.betrag)}</small>` : ""}
      ${gesperrt ? `<small><b>${f.datum.slice(0, 4)} ist abgeschlossen</b> – zum Nachtragen das Jahr wieder öffnen.</small>` : ""}</div>
    <div class="betrag">${euro2(f.betrag)}</div>
    <div class="knoepfe">${gesperrt ? "" : `<button type="button" class="small" data-abo-act="ok"${f.beleg ? ` data-beleg="${f.beleg.id}"` : ""}${f.vorhanden ? ` data-ausgabe="${f.vorhanden.id}"` : ""}>${ok}</button>
      ${treffer ? "" : `<button type="button" class="small secondary" data-abo-act="betrag">Betrag ändern</button>`}`}
      <button type="button" class="small secondary" data-abo-act="aus" title="z. B. Pause oder nicht abgebucht">${
        gesperrt ? "Nicht nachtragen" : f.rhythmus === "monatlich" ? "Diesen Monat nicht" : f.rhythmus === "woechentlich" ? "Diese Woche nicht" : "Diesmal nicht"}</button></div>
  </div>`;
}

$("#ausgaben-neu").addEventListener("click", async e => {
  const b = e.target.closest("[data-abo-act]");
  if (!b) return;
  const zeile = b.closest(".neu-beleg.abo"), url = `abos/${zeile.dataset.abo}/termine/${zeile.dataset.datum}`;
  const f = fin.faellig.find(x => String(x.abo_id) === zeile.dataset.abo && x.datum === zeile.dataset.datum);
  if (b.dataset.aboAct === "betrag") {
    const box = zeile.querySelector(".betrag");
    if (box.querySelector("input")) return;
    box.innerHTML = `<input inputmode="decimal" value="${Number(f.betrag).toFixed(2).replace(".", ",")}" aria-label="Betrag">`;
    box.querySelector("input").select();
    b.remove();
    zeile.querySelector(".was").insertAdjacentHTML("beforeend",
      `<small><label class="inline ab-jetzt-label"><input type="checkbox" class="ab-jetzt"> ab jetzt immer (Preis geändert)</label></small>`);
    return;
  }
  b.disabled = true;
  try {
    if (b.dataset.aboAct === "aus") {
      await api(url, { method: "POST", body: { aktion: "aus" } });
      toast(`${f.lieferant} ${fmtDate(f.datum)}: nicht gebucht`);
    } else {
      const input = zeile.querySelector(".betrag input");
      const body = { aktion: "ok" };
      if (input) Object.assign(body, { betrag: input.value, ab_jetzt: zeile.querySelector(".ab-jetzt").checked });
      if (b.dataset.beleg) body.beleg_id = Number(b.dataset.beleg);
      if (b.dataset.ausgabe) body.ausgabe_id = Number(b.dataset.ausgabe);
      await api(url, { method: "POST", body });
      toast(`${f.lieferant} ${fmtDate(f.datum)} bestätigt${b.dataset.beleg ? " – mit Beleg" : b.dataset.ausgabe ? " – mit der erfassten Ausgabe verknüpft" : " – Beleg kann später angehängt werden"}`);
    }
  } catch (err) { b.disabled = false; return toast(err.message, true); }
  ladeAusgaben();
  renderStartFinanzen();
});

// ---------- Abos verwalten ----------
async function ladeAbos() {
  try { abo.daten = await api("abos"); } catch (e) { toast(e.message, true); return null; }
  return abo.daten;
}

function aboWann(a) {
  if (a.wochenweise) {
    const t = new Date(a.beginn + "T12:00").toLocaleDateString("de-DE", { weekday: "long" }).toLowerCase();
    return `${t}s, ab ${fmtDate(a.beginn)}`;
  }
  const monate = { monatlich: 1, zweimonatlich: 2, vierteljaehrlich: 3, halbjaehrlich: 6, jaehrlich: 12, zweijaehrlich: 24 }[a.rhythmus]
    ?? (a.einheit === "jahre" ? 12 * a.anzahl : a.anzahl);
  const monat = new Date(a.beginn + "T12:00").toLocaleDateString("de-DE", { month: "long" });
  if (monate === 1) return `am ${a.tag}.`;
  if (monate % 12 === 0) return `am ${a.tag}. ${monat}`;
  return `am ${a.tag}., ab ${new Date(a.beginn + "T12:00").toLocaleDateString("de-DE", { month: "long", year: "numeric" })}`;
}

async function zeigeAbos() {
  const d = await ladeAbos();
  if (!d) return;
  const aktiv = d.abos.filter(a => !a.beendet);
  $("#abos-inhalt").innerHTML = `<div class="abo-summe"><span><b>${aktiv.length}</b> aktiv</span><span>≈ <b>${euro2(d.pro_monat)}</b> im Monat</span>
      <span>≈ <b>${euro2(d.pro_monat * 12)}</b> im Jahr</span></div>
    <table class="abo-liste"><thead><tr><th>Abo</th><th>Rhythmus</th><th class="num">Betrag</th><th>nächste Abbuchung</th><th></th></tr></thead><tbody>
    ${d.abos.map(a => {
      const p = a.preise.filter(x => x.ab <= today()).at(-1);
      return `<tr data-id="${a.id}"${a.beendet ? ' class="beendet"' : ""}>
        <td><b>${esc(a.lieferant)}</b><small>${esc(a.beschreibung || "")}${a.beschreibung ? " · " : ""}${esc(katName(a.kategorie))}${a.privatanteil ? ` · ${String(a.privatanteil).replace(".", ",")} % privat` : ""}</small></td>
        <td>${esc(a.rhythmus_name)}<small>${aboWann(a)}</small></td>
        <td class="num">${euro2(a.betrag_aktuell)}${p ? `<small>seit ${fmtDate(p.ab)}</small>` : ""}</td>
        <td>${a.beendet ? `beendet am ${fmtDate(a.ende)}` : a.naechste ? fmtDate(a.naechste) : "–"}${a.offen ? `<small><b>${a.offen} fällig</b> – unter „Neu“</small>` : ""}${a.ende && !a.beendet ? `<small>endet ${fmtDate(a.ende)}</small>` : ""}</td>
        <td class="btns"><button type="button" class="small secondary" data-abos="bearbeiten" title="Bearbeiten, Preis ändern, kündigen">✎</button></td></tr>`;
    }).join("") || `<tr><td colspan="5" class="hint">Noch keine Abos – z. B. Musikpool oder DJ-Software einmal anlegen.</td></tr>`}</tbody></table>
    <p class="hint">Am Tag der Abbuchung erscheint das Abo unter „Neu – bitte prüfen“. Erst nach dem Bestätigen zählt es in der EÜR. Kommt die Rechnung als Mail oder PDF, hängt die App sie an.</p>`;
  $("#abos-aktionen").innerHTML = `<button type="button" data-abos="schliessen">Schließen</button>`;
  $("#abos-titel-knopf").hidden = false;
  $("#abos-titel").textContent = "Abos";
  if (!$("#abos-dialog").open) $("#abos-dialog").showModal();
}

function zeigeAboForm(a) {
  const d = abo.daten;
  abo.aktuell = a;
  const w = a || { lieferant: "", beschreibung: "", kategorie: "musik", betrag_aktuell: "", rhythmus: "monatlich", anzahl: 6, einheit: "wochen",
                   tag: new Date().getDate(), beginn: today(), ende: "", privatanteil: 0 };
  $("#abos-titel").textContent = a ? a.lieferant : "Abo anlegen";
  $("#abos-titel-knopf").hidden = true;
  const kat = fin.kategorien.filter(k => k.id !== "anschaffung");
  $("#abos-inhalt").innerHTML = `${a ? "" : `<div class="vorschlag-chips">${d.vorschlaege.map((v, i) => `<button type="button" class="secondary" data-vorschlag="${i}">${esc(v.lieferant)}</button>`).join("")}</div>`}
    <form id="abo-form" class="abo-form" autocomplete="off"><div class="grid">
      <label>Lieferant<input name="lieferant" required value="${esc(w.lieferant)}" placeholder="z. B. Musikpool Beispiel"></label>
      <label>Beschreibung<input name="beschreibung" value="${esc(w.beschreibung || "")}" placeholder="z. B. DJ-Musikpool (Monatsabo)"></label>
      <label>Kategorie<select name="kategorie">${kat.map(k => `<option value="${k.id}"${k.id === w.kategorie ? " selected" : ""}>${esc(k.name)}</option>`).join("")}</select></label>
      <label>Betrag ${a ? `<span class="opt">(brutto, €)</span>` : `<span class="opt">(brutto, €)</span>`}<input name="betrag" required inputmode="decimal" value="${w.betrag_aktuell === "" ? "" : Number(w.betrag_aktuell).toFixed(2).replace(".", ",")}"></label>
      <label>Rhythmus<select name="rhythmus">${d.rhythmen.map(r => `<option value="${r.id}"${r.id === w.rhythmus ? " selected" : ""}>${esc(r.id === "eigen" ? "eigener Rhythmus …" : r.name)}</option>`).join("")}</select></label>
      <div class="eigen-rhythmus"><label>alle<input name="anzahl" type="number" min="1" max="99" value="${w.anzahl || 6}"></label>
        <label>&nbsp;<select name="einheit" aria-label="Einheit">${d.einheiten.map(e => `<option value="${e.id}"${e.id === w.einheit ? " selected" : ""}>${esc(e.name)}</option>`).join("")}</select></label></div>
      <label class="tag-feld">Abbuchung am <span class="opt">(Tag im Monat)</span><input name="tag" type="number" min="1" max="31" value="${w.tag || 1}"></label>
      <label>Beginn<input name="beginn" type="date" required value="${w.beginn}"></label>
      <label>Ende <span class="opt">(bei Kündigung)</span><input name="ende" type="date" value="${w.ende || ""}"></label>
      <label>Privatanteil <span class="opt">(%)</span><input name="privatanteil" type="number" min="0" max="100" step="1" value="${w.privatanteil || 0}"></label>
    </div>
    ${a ? `<p class="hint abo-preis-hinweis">Ein neuer Betrag gilt ab heute – frühere Buchungen bleiben, wie sie waren.</p>`
      : `<label class="inline"><input type="checkbox" name="nachtragen"> Frühere Abbuchungen seit dem Beginn nachtragen <span class="opt">(sonst ab heute – meist sind sie schon erfasst)</span></label>`}
    <div class="abo-hinweis">Abbuchungen ab dem 22.12. für den nächsten Zeitraum ordnet die App nach der 10-Tage-Regel automatisch dem neuen Jahr zu (nicht bei wöchentlichen Abos).</div>
    </form>`;
  $("#abos-aktionen").innerHTML = `${a ? `<button type="button" class="secondary danger-text" data-abos="loeschen">Löschen</button>` : ""}
    <button type="button" class="secondary" data-abos="liste">Abbrechen</button><button type="submit" form="abo-form">Speichern</button>`;
  const f = $("#abo-form");
  const felder = () => {
    const r = f.elements.rhythmus.value;
    const woche = ["woechentlich", "vierwochen"].includes(r) || (r === "eigen" && f.elements.einheit.value === "wochen");
    f.querySelector(".eigen-rhythmus").hidden = r !== "eigen";
    f.querySelector(".tag-feld").hidden = woche;
  };
  f.addEventListener("change", felder);
  felder();
  f.addEventListener("submit", async ev => {
    ev.preventDefault();
    const x = Object.fromEntries([...f.elements].filter(e => e.name).map(e => [e.name, e.type === "checkbox" ? e.checked : e.value]));
    try {
      if (a) await api(`abos/${a.id}`, { method: "PUT", body: x });
      else await api("abos", { method: "POST", body: x });
    } catch (err) { return toast(err.message, true); }
    toast(a ? `${x.lieferant} gespeichert${x.ende ? ` – endet am ${fmtDate(x.ende)}` : ""}` : `Abo ${x.lieferant} angelegt`);
    zeigeAbos();
    ladeAusgaben();
  });
  f.elements.lieferant.focus();
}

$("#abos-oeffnen").addEventListener("click", () => zeigeAbos());
$("#abos-dialog").addEventListener("click", async e => {
  const v = e.target.closest("[data-vorschlag]");
  if (v) {
    const x = abo.daten.vorschlaege[v.dataset.vorschlag], f = $("#abo-form");
    for (const k of ["lieferant", "beschreibung", "kategorie", "rhythmus"]) f.elements[k].value = x[k];
    f.dispatchEvent(new Event("change"));
    return f.elements.betrag.focus();
  }
  const b = e.target.closest("[data-abos]");
  if (!b) return;
  switch (b.dataset.abos) {
    case "neu": return zeigeAboForm(null);
    case "liste": return zeigeAbos();
    case "schliessen": return $("#abos-dialog").close();
    case "bearbeiten": return zeigeAboForm(abo.daten.abos.find(a => a.id === Number(b.closest("tr").dataset.id)));
    case "loeschen":
      if (!confirm(`Abo ${abo.aktuell.lieferant} löschen?\n\nSchon gebuchte Ausgaben bleiben erhalten. Zum Kündigen besser ein Ende eintragen.`)) return;
      try { await api(`abos/${abo.aktuell.id}`, { method: "DELETE" }); } catch (err) { return toast(err.message, true); }
      toast("Abo gelöscht");
      zeigeAbos();
      ladeAusgaben();
  }
});
