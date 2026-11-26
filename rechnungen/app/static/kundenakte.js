/* DJ Office Studio – seit 1.14: Vertrag → Feier → Rechnung, „Bar bezahlt“ (Quittung von Hand), Kundenakte unter
   Stammdaten → Kunden und die Jahres-Erinnerung für Stammkunden. Wird nach app.js und vertraege.js geladen. */
"use strict";

const ka = { vertraege: [], bar: [], kunden: [], ruhe: {}, akte: null, wahl: null, barQuelle: null };
const kaNorm = n => (n || "").trim().replace(/\s+/g, " ").toLowerCase();
const kaHeute = () => isoLokal(new Date());
const kaGueltig = r => !r.storno_von && !r.storniert_durch;
const feierVon = b => (b.positionen || []).map(p => p.lieferdatum).filter(Boolean).sort().at(-1) || b.datum;
const anlassVon = b => ((b.positionen?.[0]?.beschreibung) || "").replace(/^DJ – (Tätigkeit )?/, "")
  .replace(/\s*–\s*\d{1,2}:\d{2} Uhr bis.*$/, "").replace(/^Anzahlung.*$/, "Anzahlung");
const vorname = name => esc((name || "").trim().split(/\s+/)[0]);
const KA_FIRMA = /(gmbh|\bag\b|e\.\s?v\.?|\bkg\b|\bohg\b|\bug\b|gbr|verein|schule|gemeinde|firma)/i;

/* Alles, was Kundenakte, Startseite und Listen brauchen – Rechnungen und Angebote landen in state. */
async function kaLaden({ kunden = false } = {}) {
  const [rechnungen, angebote, vertraege, bar, ruhe, stamm] = await Promise.all([api("rechnungen"), api("angebote"), api("vertraege"),
    api("barzahlungen"), api("kunden/erinnerung"), kunden ? api("kunden") : Promise.resolve(null)]);
  Object.assign(state, { rechnungen, angebote });
  Object.assign(ka, { vertraege, bar, ruhe }, stamm ? { kunden: stamm } : {});
}

// ---------- Vertrag → Rechnung ----------

const vertragAnzahlungen = v => (state.rechnungen || []).filter(r => kaGueltig(r) && r.rechnungsart === "anzahlung"
  && (r.vertrag_id === v.id || (v.angebot_id && r.angebot_id === v.angebot_id)));
const vertragRechnung = v => (state.rechnungen || []).find(r => kaGueltig(r) && r.rechnungsart !== "anzahlung"
  && (r.vertrag_id === v.id || (v.angebot_id && r.angebot_id === v.angebot_id)));
const vertragBar = v => ka.bar.find(b => b.vertrag_id === v.id || (v.angebot_id && b.angebot_id === v.angebot_id));
const angebotBar = a => ka.bar.find(b => b.angebot_id === a.id);
/* Angenommenes Angebot ohne Vertrag: nach der Feier (bis 60 Tage danach) an Rechnung bzw. „Bar bezahlt“ erinnern,
   solange es dazu weder eine Rechnung (außer Anzahlung) noch eine Barzahlung gibt. Ältere Angebote bleiben still –
   sonst meldeten sich längst erledigte oder importierte Angebote. */
const ANGEBOT_ERINNERN_TAGE = 60;
function angebotBraucht(a, heute = kaHeute()) {
  const feier = veranstaltungAm(a);
  if (a.status !== "angenommen" || !feier || feier > heute) return false;
  const grenze = new Date(heute + "T12:00");
  grenze.setDate(grenze.getDate() - ANGEBOT_ERINNERN_TAGE);
  if (feier < isoLokal(grenze)) return false;
  if (ka.vertraege.some(v => v.angebot_id === a.id) || angebotBar(a)) return false;
  return !(state.rechnungen || []).some(r => kaGueltig(r) && r.rechnungsart !== "anzahlung" && (r.angebot_id === a.id || r.id === a.rechnung_id));
}
const mitAnzahlung = v => v.felder.zahlung !== "ganz" && Number(v.felder.anzahlung) > 0;

/* Was steht beim Vertrag an? „rechnung“ nach der Feier, „anzahlung“ vorher (falls vereinbart und unterschrieben), sonst null. */
function vertragBraucht(v, heute = kaHeute()) {
  if (v.status === "entwurf" || vertragRechnung(v) || vertragBar(v)) return null;
  if (v.datum && v.datum <= heute) return "rechnung";
  // Anzahlung erst anmahnen, wenn der Vertrag unterschrieben zurück ist (Knopf in der Liste gibt es schon ab „verschickt“)
  if (v.status === "unterschrieben" && mitAnzahlung(v) && !vertragAnzahlungen(v).length) return "anzahlung";
  return null;
}

/* Rechnung aus dem Vertrag vorbereiten: Kunde, Termin, Ort und Gage; mit Anzahlung wird es die Schlussrechnung. */
async function rechnungAusVertrag(v, art = "rechnung") {
  try { await kaLaden(); } catch (e) { return toast(e.message, true); }
  setModus("rechnung");
  await resetForm();
  fillKunde({ ...v.kunde, id: v.kunde_id });
  $("#positionen").innerHTML = "";
  addPosition({ beschreibung: `DJ – Tätigkeit ${v.anlass || "Veranstaltung"}${v.von && v.bis ? ` – ${shortTime(v.von)} Uhr bis ${shortTime(v.bis)} Uhr` : ""}`,
                lieferdatum: v.datum, preis: v.gage });
  setVeranstaltung(v.ort, state.absender ? state.absender.fahrt_standard : true);
  showTab("neu");
  const anz = vertragAnzahlungen(v).filter(r => !verrechnetIn(r));
  if (art === "anzahlung") { ra.art = "prozent"; ra.wert = Number(v.felder.anzahlung) || 30; await raSetzen("anzahlung"); }
  else if (anz.length) await raSetzen("schluss", anz.map(r => r.id));
  setAusVertrag(v, art === "anzahlung" ? "Anzahlungsrechnung" : anz.length ? "Schlussrechnung" : "Rechnung");
  window.scrollTo(0, 0);
}

/* Hinweis im Editor; beim Speichern wird die Rechnung mit dem Vertrag verknüpft. */
function setAusVertrag(v, was) {
  state.ausVertrag = v.id;
  ka.feierAm = v.datum || "";
  const box = $("#aus-angebot");
  box.classList.remove("hidden");
  box.textContent = `${was} aus ${v.name} – Kunde, Termin, Ort und Gage übernommen.`;
  if (was === "Anzahlungsrechnung") return;
  box.insertAdjacentHTML("beforeend", `<span class="rv-leiste">Länger gespielt oder etwas dazugekommen?
    <button type="button" class="small secondary" data-rv-pos="verlaengerung">＋ Verlängerung</button>
    <button type="button" class="small secondary" data-rv-pos="position">＋ weitere Position</button></span>`);
}
$("#aus-angebot").addEventListener("click", e => {
  const b = e.target.closest("[data-rv-pos]");
  if (!b) return;
  const pos = b.dataset.rvPos === "verlaengerung" ? rvPosition({ beschreibung: "Verlängerung – 1 Stunde", preis: "" }) : rvPosition({});
  $(b.dataset.rvPos === "verlaengerung" ? ".preis" : ".beschreibung", pos).focus();
});
/* Weitere Leistung am Tag der Feier – vor dem Abzug der Anzahlung, damit die Rechnung in der üblichen Reihenfolge steht. */
function rvPosition(p) {
  const pos = addPosition({ ...p, lieferdatum: ka.feierAm || undefined });
  $("#positionen .pos.abzug")?.before(pos);
  return pos;
}

// ---------- Wie wurde bezahlt? → Rechnung oder bar ----------

function zahlwegFragen(quelle) {
  ka.wahl = quelle;
  const v = quelle.vertrag, a = quelle.angebot, name = (v || a).kunde.name;
  $("#rv-wahl-titel").textContent = `Wie hat ${(name || "der Kunde").trim().split(/\s+/)[0]} bezahlt?`;
  $("#rv-wahl-info").textContent = v ? `${v.name} · Feier ${v.datum ? fmtDate(v.datum) : "–"} · ${euroCent(v.gage)}`
    : `Angebot ${a.nummer} · ${euroCent(a.gesamt)}`;
  $("#rv-wahl").showModal();
}
$("#rv-wahl").addEventListener("click", e => {
  const b = e.target.closest("[data-zahlweg]");
  if (!b) return;
  $("#rv-wahl").close();
  const q = ka.wahl;
  if (b.dataset.zahlweg === "rechnung") return q.vertrag ? rechnungAusVertrag(q.vertrag) : angebotZuRechnung(q.angebot);
  if (b.dataset.zahlweg === "bar") oeffneBar(q);
});

function oeffneBar(quelle) {
  const v = quelle.vertrag, a = quelle.angebot, kunde = (v || a).kunde;
  const anz = v ? vertragAnzahlungen(v) : anzahlungenZu(a);
  const gesamt = v ? v.gage : a.gesamt, schon = anz.filter(r => r.bezahlt).reduce((s, r) => s + r.gesamt, 0);
  const feier = v ? v.datum : veranstaltungAm(a);
  ka.barQuelle = { vertrag: v, angebot: a };
  $("#bar-titel").textContent = `Bar bezahlt: ${kunde.name || "Kunde"}`;
  $("#bar-info").textContent = `${v ? v.name : `Angebot ${a.nummer}`} · ${v ? "Gage" : "Betrag"} ${euroCent(gesamt)}`
    + (schon ? ` · Anzahlung ${anz.filter(r => r.bezahlt).map(r => r.nummer).join(", ")} (${euroCent(schon)}) schon bezahlt – vorausgefüllt ist der Rest` : "");
  $("#bar-betrag").value = Math.max(0, Math.round((gesamt - schon) * 100) / 100) || "";
  $("#bar-am").value = feier && feier <= kaHeute() ? feier : kaHeute();
  $("#bar-nr").value = "";
  $("#bar-foto").value = "";
  $("#bar-firma").textContent = KA_FIRMA.test(kunde.name || "")
    ? "Hinweis: Firmen und Vereine brauchen für ihre Buchhaltung meist eine richtige Rechnung – dann lieber „Rechnung schreiben“." : "";
  $("#bar-dialog").showModal();
}

$("#bar-dialog").addEventListener("click", async e => {
  const b = e.target.closest("[data-bar]");
  if (!b) return;
  if (b.dataset.bar === "zu") return $("#bar-dialog").close();
  const q = ka.barQuelle, fd = new FormData();
  fd.append("betrag", $("#bar-betrag").value);
  fd.append("datum", $("#bar-am").value);
  fd.append("quittung_nr", $("#bar-nr").value.trim());
  if (q.vertrag) fd.append("vertrag_id", q.vertrag.id);
  else fd.append("angebot_id", q.angebot.id);
  if ($("#bar-foto").files[0]) fd.append("beleg", $("#bar-foto").files[0]);
  b.disabled = true;
  try {
    const res = await fetch("api/barzahlungen", { method: "POST", headers: SCHUTZ, body: fd });
    const d = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(d.error || `Fehler ${res.status}`);
    $("#bar-dialog").close();
    toast(`${euroCent(d.betrag)} bar bezahlt vermerkt${d.quittung_nr ? ` (Quittung ${d.quittung_nr})` : ""}`);
    kaNeuZeichnen();
  } catch (err) { toast(err.message, true); }
  b.disabled = false;
});

const barText = b => `bar bezahlt ${fmtDate(b.datum).slice(0, 6)}${b.quittung_nr ? ` · Quittung ${b.quittung_nr}` : ""}`;

/* Nach einer Änderung die gerade sichtbare Ansicht neu zeichnen. */
function kaNeuZeichnen() {
  const aktiv = $(".tab.active")?.id;
  if (aktiv === "tab-start") renderStart();
  if (aktiv === "tab-vertraege") ladeVertraege();
  if (aktiv === "tab-angebote") loadAngebote();
  if (aktiv === "tab-kunden") renderStamm("kunden");
  if ($("#kundenakte").open && ka.akte) oeffneAkte(ka.akte.name);
}

// ---------- Kennzahlen je Kunde ----------

function belegeVon(name) {
  const n = kaNorm(name);
  return {
    rechnungen: (state.rechnungen || []).filter(r => kaNorm(r.kunde.name) === n),
    angebote: (state.angebote || []).filter(a => kaNorm(a.kunde.name) === n),
    vertraege: ka.vertraege.filter(v => kaNorm(v.kunde.name) === n),
    bar: ka.bar.filter(b => kaNorm(b.kunde.name) === n),
  };
}

/* Preis einer Feier: bei einer Schlussrechnung samt der abgezogenen Anzahlungen. */
function feierPreis(r) {
  if (r.rechnungsart !== "schluss") return r.gesamt;
  const ids = new Set(r.positionen.map(p => p.anzahlung_id).filter(Boolean));
  return r.gesamt + (state.rechnungen || []).filter(x => ids.has(x.id)).reduce((s, x) => s + x.gesamt, 0);
}

function kennzahlen(name, heute = kaHeute()) {
  const b = belegeVon(name);
  const feiern = [
    ...b.rechnungen.filter(r => kaGueltig(r) && r.rechnungsart !== "anzahlung").map(r => ({ am: feierVon(r), preis: feierPreis(r), beleg: r })),
    ...b.bar.map(x => ({ am: x.feier_datum || x.datum, preis: x.betrag, bar: x })),
  ];
  const jahre = {};
  const plus = (tag, betrag) => { const j = (tag || "").slice(0, 4); if (j) jahre[j] = (jahre[j] || 0) + betrag; };
  b.rechnungen.filter(r => kaGueltig(r) && r.bezahlt).forEach(r => plus(r.bezahlt_am || r.datum, r.gesamt));
  b.bar.forEach(x => plus(x.datum, x.betrag));
  const daten = feiern.map(f => f.am).filter(Boolean).sort();
  const naechste = [...b.vertraege.map(v => v.datum), ...b.angebote.filter(a => a.status !== "abgelehnt").map(feierVon), ...daten]
    .filter(x => x && x > heute).sort()[0] || null;
  return {
    b, feiern, jahre, naechste,
    umsatz: Object.values(jahre).reduce((s, x) => s + x, 0),
    letzte: daten.filter(x => x <= heute).at(-1) || null,
    schnitt: feiern.length ? feiern.reduce((s, f) => s + f.preis, 0) / feiern.length : 0,
    stamm: new Set(daten.map(x => x.slice(0, 4))).size >= 2,
  };
}

// ---------- Jahres-Erinnerung: Stammkunde, Feier vor knapp einem Jahr, noch nichts Neues ----------

function erinnerungen(heute = kaHeute()) {
  const namen = new Map();
  for (const x of [...(state.rechnungen || []), ...ka.bar]) if (x.kunde.name) namen.set(kaNorm(x.kunde.name), x.kunde.name);
  const aus = [];
  for (const [n, name] of namen) {
    const ruhe = ka.ruhe[n];
    if (ruhe === "nie") continue;
    const k = kennzahlen(name, heute);
    if (!k.stamm) continue;
    const letzte = k.feiern.filter(f => f.am <= heute).sort((a, b) => a.am.localeCompare(b.am)).at(-1);
    if (!letzte) continue;
    const tag = new Date(letzte.am + "T12:00");
    tag.setFullYear(tag.getFullYear() + 1);
    const am = isoLokal(tag), bis = Math.round((tag - new Date(heute + "T12:00")) / 864e5);
    const schonNeu = [...k.b.angebote.map(a => a.datum), ...k.b.vertraege.map(v => (v.erstellt || "").slice(0, 10)),
      ...k.b.rechnungen.map(r => r.datum), ...k.b.bar.map(x => x.datum)].some(x => x > letzte.am);
    if (bis >= 0 && bis <= 42 && !schonNeu && !(ruhe && ruhe >= am)) aus.push({ name, letzte, am });
  }
  return aus;
}

async function erinnerungRuhe(name, ruhe) {
  await api("kunden/erinnerung", { method: "PUT", body: { name, ruhe } });
  if (ruhe === null) delete ka.ruhe[kaNorm(name)]; else ka.ruhe[kaNorm(name)] = ruhe;
}

// ---------- Startseite ----------

/* Chips für „Heute wichtig“ (HTML) – wird von renderStart aufgerufen, nachdem die Daten geladen sind. */
function kaStartChips(heute) {
  const chips = [];
  for (const v of ka.vertraege) {
    const b = vertragBraucht(v, heute), wer = vorname(v.kunde.name);
    if (b === "rechnung") chips.push(`<button type="button" class="start-chip gelb" data-ka-start="rechnung" data-vertrag="${v.id}">✎ Rechnung schreiben: Feier ${wer} war am ${fmtDate(v.datum).slice(0, 6)}</button>`);
    if (b === "anzahlung") chips.push(`<button type="button" class="start-chip gelb" data-ka-start="anzahlung" data-vertrag="${v.id}">€ Anzahlung anfordern: ${wer}</button>`);
  }
  for (const a of (state.angebote || []).filter(a => angebotBraucht(a, heute)))
    chips.push(`<button type="button" class="start-chip gelb" data-ka-start="angebot-rechnung" data-aid="${a.id}" title="Angebot ${esc(a.nummer)}">✎ Rechnung schreiben: Feier ${vorname(a.kunde.name)} war am ${fmtDate(veranstaltungAm(a)).slice(0, 6)}</button>`);
  for (const e of erinnerungen(heute))
    chips.push(`<span class="start-chip stamm-chip"><button type="button" class="link" data-akte="${esc(e.name)}" title="Kundenakte öffnen">↻ Stammkunde ${vorname(e.name)}: letztes Jahr am ${fmtDate(e.letzte.am).slice(0, 6)} – Angebot schicken?</button>
      <button type="button" class="link aus" data-ka-start="ruhe" data-name="${esc(e.name)}" data-am="${e.am}" title="Diesmal nicht – kommt nächstes Jahr wieder" aria-label="Diesmal nicht">✕</button></span>`);
  return chips;
}

$("#start").addEventListener("click", async e => {
  const b = e.target.closest("[data-ka-start]");
  if (!b) return;
  e.stopPropagation();
  const v = ka.vertraege.find(x => x.id === Number(b.dataset.vertrag));
  const a = state.angebote.find(x => x.id === Number(b.closest("[data-angebot]")?.dataset.angebot));
  try {
    switch (b.dataset.kaStart) {
      case "rechnung": return zahlwegFragen({ vertrag: v });
      case "angebot-rechnung": return zahlwegFragen({ angebot: state.angebote.find(x => x.id === Number(b.dataset.aid)) });
      case "anzahlung": return rechnungAusVertrag(v, "anzahlung");
      case "bar": return oeffneBar({ angebot: a });
      case "ruhe":
        await erinnerungRuhe(b.dataset.name, b.dataset.am);
        toast("Ausgeblendet – nächstes Jahr kommt die Erinnerung wieder");
        return renderStart();
    }
  } catch (err) { toast(err.message, true); }
}, true);

// ---------- Verträge-Liste: Stand der Rechnungen und Knöpfe ----------

/* Zusätze je Zeile der Verträge-Liste (wird von ladeVertraege aufgerufen). */
async function kaVertraegeErgaenzen() {
  try { await kaLaden(); } catch (e) { return; }
  for (const tr of $$("#vt-body tr[data-id]")) {
    const v = ka.vertraege.find(x => x.id === Number(tr.dataset.id));
    if (!v) continue;
    const anz = vertragAnzahlungen(v), re = vertragRechnung(v), bar = vertragBar(v), braucht = vertragBraucht(v);
    const stand = [...anz.map(r => `Anzahlung ${esc(r.nummer)} ${r.bezahlt ? "✓ bezahlt" : "offen"}`),
      re ? `Rechnung ${esc(re.nummer)} ${re.bezahlt ? "✓ bezahlt" : "offen"}` : "", bar ? `✓ ${esc(barText(bar))}` : ""].filter(Boolean);
    if (stand.length) tr.children[3].insertAdjacentHTML("beforeend", `<div class="vt-rechnung">${stand.join(" · ")}</div>`);
    const btns = tr.querySelector(".btns");
    if (v.status !== "entwurf" && !re && !bar) {
      btns.insertAdjacentHTML("afterbegin", `<button type="button" class="small secondary" data-ka-vt="bar" title="Bar bezahlt – Quittung von Hand auf dem Quittungsblock">Bar bezahlt</button>`);
      if (mitAnzahlung(v) && !anz.length && !(v.datum && v.datum <= kaHeute()))
        btns.insertAdjacentHTML("afterbegin", `<button type="button" class="small${braucht === "anzahlung" ? "" : " secondary"}" data-ka-vt="anzahlung">→ Anzahlungsrechnung</button>`);
      btns.insertAdjacentHTML("afterbegin", `<button type="button" class="small${braucht === "rechnung" ? "" : " secondary"}" data-ka-vt="rechnung">→ ${anz.length ? "Schlussrechnung" : "Rechnung"}</button>`);
    }
    const name = tr.querySelector("td small");
    if (name && v.kunde.name) {
      const knopf = kundeLink(v.kunde.name);
      name.firstChild.replaceWith(knopf, name.firstChild.textContent.slice(v.kunde.name.length));
    }
  }
}
$("#vt-body").addEventListener("click", e => {
  const b = e.target.closest("[data-ka-vt]");
  if (!b) return;
  e.stopPropagation();
  const v = ka.vertraege.find(x => x.id === Number(b.closest("tr").dataset.id));
  if (b.dataset.kaVt === "bar") oeffneBar({ vertrag: v });
  else rechnungAusVertrag(v, b.dataset.kaVt);
}, true);

/* Vertragsfenster: „→ Rechnung“ in der Kopfzeile (nicht bei Entwürfen). */
function kaVertragKopf(v) {
  $("#vt-zur-rechnung").classList.toggle("hidden", v.status === "entwurf");
}
$("#vt-zur-rechnung").addEventListener("click", async () => {
  try { await kaLaden(); } catch (e) { return toast(e.message, true); }
  const v = ka.vertraege.find(x => x.id === vtState.aktuell.id);
  $("#vertrag").close();
  if (vertragRechnung(v)) return loadIntoForm(vertragRechnung(v));
  rechnungAusVertrag(v, vertragBraucht(v) === "anzahlung" ? "anzahlung" : "rechnung");
});

// ---------- Angebote: „Bar bezahlt“ neben „→ Rechnung“ ----------

function kaAngeboteErgaenzen() {
  for (const tr of $$("#angebote-offen tr[data-id], #angebote-body tr[data-id]")) {
    const a = state.angebote.find(x => x.id === Number(tr.dataset.id));
    if (!a) continue;
    const bar = angebotBar(a), re = tr.querySelector("[data-act=rechnung]");
    if (bar && tr.closest("#angebote-body")) {
      tr.children[5].insertAdjacentHTML("beforeend", `<br><small>${esc(barText(bar))}</small>`);
      re?.remove();
    } else if (re && !bar) {
      re.insertAdjacentHTML("afterend", `<button type="button" class="small secondary" data-ka-bar="${a.id}" title="Bar bezahlt – Quittung von Hand auf dem Quittungsblock">Bar bezahlt</button>`);
    }
    const kunde = tr.querySelector("td small");
    if (kunde && a.kunde.name && kunde.textContent === a.kunde.name) kunde.replaceChildren(kundeLink(a.kunde.name));
  }
}
for (const sel of ["#angebote-offen", "#angebote-body"]) $(sel).addEventListener("click", e => {
  const b = e.target.closest("[data-ka-bar]");
  if (!b) return;
  e.stopPropagation();
  oeffneBar({ angebot: state.angebote.find(a => a.id === Number(b.dataset.kaBar)) });
}, true);

// ---------- Kundenakte ----------

function kundeLink(name, fett = false) {
  const b = document.createElement("button");
  b.type = "button";
  b.className = "kunde-link";
  b.dataset.akte = name;
  b.title = "Kundenakte öffnen";
  if (fett) b.append(Object.assign(document.createElement("b"), { textContent: name }));
  else b.textContent = name;
  return b;
}
document.addEventListener("click", e => {
  const b = e.target.closest("[data-akte]");
  if (!b) return;
  e.preventDefault();
  e.stopPropagation();
  if ($("#suche")?.open) $("#suche").close();
  oeffneAkte(b.dataset.akte);
}, true);

async function oeffneAkte(name) {
  try { await kaLaden({ kunden: true }); } catch (e) { return toast(e.message, true); }
  const k = kennzahlen(name), n = kaNorm(name);
  const stamm = ka.kunden.find(x => kaNorm(x.name) === n) || k.b.rechnungen[0]?.kunde || k.b.angebote[0]?.kunde || { name };
  const eintraege = [
    ...k.b.rechnungen.map(r => ({ art: r.rechnungsart === "anzahlung" ? "Anzahlung" : r.storno_von ? "Storno" : "Rechnung", nr: r.nummer,
      datum: feierVon(r), text: anlassVon(r), betrag: r.gesamt,
      status: r.storno_von || r.storniert_durch ? "storniert" : r.bezahlt ? "bezahlt" : "offen", oeffne: () => loadIntoForm(r) })),
    ...k.b.angebote.map(a => ({ art: "Angebot", nr: a.nummer, datum: feierVon(a), text: anlassVon(a), betrag: a.gesamt,
      status: STATUS_TEXT[a.status] || a.status, oeffne: () => loadAngebotIntoForm(a) })),
    ...k.b.vertraege.map(v => ({ art: "Vertrag", nr: v.nummer, datum: v.datum, text: v.anlass, betrag: v.gage,
      status: VT_STATUS[v.status], oeffne: () => oeffneVertrag(v.id) })),
    ...k.b.bar.map(x => ({ art: "Bar", nr: x.quittung_nr ? `Quittung ${x.quittung_nr}` : "", datum: x.feier_datum || x.datum,
      text: [x.anlass, `bezahlt am ${fmtDate(x.datum)}`].filter(Boolean).join(" · "), betrag: x.betrag, status: "bar bezahlt",
      foto: x.hat_beleg ? x.id : null, bar: x })),
  ].sort((a, b) => (b.datum || "").localeCompare(a.datum || ""));
  const erinnerung = erinnerungen().find(e => kaNorm(e.name) === n);
  const letzteR = erinnerung?.letzte.beleg;
  const adresse = [stamm.zusatz, stamm.strasse, [stamm.plz, stamm.ort].filter(Boolean).join(" ")].filter(Boolean).join(", ");
  $("#ka-inhalt").innerHTML = `<div class="ka-kopf"><div><h2>${esc(stamm.name)}${k.stamm ? `<span class="ku-stamm">Stammkunde</span>` : ""}</h2>
      <div class="hint">${esc(adresse)}${stamm.email ? `${adresse ? " · " : ""}${esc(stamm.email)}` : ""}</div></div>
      <div class="row"><button type="button" class="small" data-ka="angebot">＋ Angebot</button>
        <button type="button" class="small secondary" data-ka="vertrag">＋ Vertrag</button>
        <button type="button" class="small secondary" data-ka="rechnung">＋ Rechnung</button></div></div>
    ${stamm.id ? `<div class="ka-notiz"><label>Notiz <span class="opt">(nur für dich – steht nie auf Angebot oder Rechnung)</span>
      <textarea id="ka-notiz" maxlength="5000" placeholder="z. B. mag keinen Schlager · Parken hinterm Haus · Ansprechpartnerin Frau Beispiel">${esc(stamm.notiz || "")}</textarea></label>
      <div class="row"><button type="button" class="small secondary" data-ka="notiz">Notiz speichern</button><span class="mini-hinweis" id="ka-notiz-stand"></span></div></div>` : ""}
    ${erinnerung ? `<div class="ka-hinweis">↻ Letztes Jahr am ${fmtDate(erinnerung.letzte.am)}${letzteR ? `: ${esc(anlassVon(letzteR))}` : ""} für ${euroCent(erinnerung.letzte.preis)} – Angebot schicken?
      <div class="ka-knoepfe">${letzteR ? `<button type="button" class="small" data-ka="wieder">Angebot wie letztes Jahr</button>` : `<button type="button" class="small" data-ka="angebot">＋ Angebot</button>`}
      <button type="button" class="small secondary" data-ka="diesmal" title="Kommt nächstes Jahr wieder">Diesmal nicht</button>
      <button type="button" class="small secondary" data-ka="nie" title="Für diesen Kunden keine Jahres-Erinnerung mehr">Nicht mehr erinnern</button></div></div>`
      : ka.ruhe[n] === "nie" ? `<div class="ka-hinweis ka-aus">Jahres-Erinnerung für diesen Kunden ist aus.
      <button type="button" class="small secondary" data-ka="wieder-an">Wieder einschalten</button></div>` : ""}
    <div class="ka-kacheln"><div><b>${euroGanz(k.umsatz)}</b><small>Umsatz (bezahlt)</small></div>
      <div><b>${k.feiern.length}</b><small>Feier${k.feiern.length === 1 ? "" : "n"}</small></div>
      <div><b>${k.schnitt ? euroGanz(k.schnitt) : "–"}</b><small>üblicher Preis</small></div>
      <div><b>${k.naechste ? fmtDate(k.naechste) : k.letzte ? fmtDate(k.letzte) : "–"}</b><small>${k.naechste ? "nächste Feier" : "letzte Feier"}</small></div></div>
    ${Object.keys(k.jahre).length ? `<div class="ka-jahre">${Object.entries(k.jahre).sort().map(([j, s]) => `<span>${j}: ${euroGanz(s)}</span>`).join("")}</div>` : ""}
    <table class="ka-liste">${eintraege.map((x, i) => `<tr data-i="${i}"><td><span class="ka-art">${x.art}</span> ${esc(x.nr || "")}</td>
      <td>${x.datum ? fmtDate(x.datum) : "–"}<br><small>${esc(x.text || "")}</small></td><td class="num">${euroCent(x.betrag || 0)}</td>
      <td>${esc(x.status || "")}${x.foto ? ` · <a href="api/barzahlungen/${x.foto}/beleg" class="ka-foto">📎 Foto</a>` : ""}</td></tr>`).join("")
      || `<tr><td class="hint">Noch nichts für diesen Kunden.</td></tr>`}</table>`;
  ka.akte = { name, stamm, eintraege, erinnerung };
  if (!$("#kundenakte").open) $("#kundenakte").showModal();
}

$("#kundenakte").addEventListener("click", async e => {
  if (e.target.closest("a.ka-foto")) return;            // Foto herunterladen
  const zeile = e.target.closest("tr[data-i]"), b = e.target.closest("[data-ka]");
  const akte = ka.akte;
  if (zeile) {
    const x = akte.eintraege[Number(zeile.dataset.i)];
    if (x.bar) {
      if (!confirm(`Barzahlung über ${euroCent(x.betrag)} vom ${fmtDate(x.bar.datum)} löschen?\n\n`
        + "Nur nötig, wenn sie versehentlich vermerkt wurde – die Quittung auf dem Block bleibt davon unberührt.")) return;
      try { await api(`barzahlungen/${x.bar.id}`, { method: "DELETE" }); toast("Barzahlung gelöscht"); } catch (err) { return toast(err.message, true); }
      return oeffneAkte(akte.name);
    }
    $("#kundenakte").close();
    return x.oeffne();
  }
  if (!b) return;
  const was = b.dataset.ka, k = akte.stamm;
  try {
    if (["diesmal", "nie", "wieder-an"].includes(was)) {
      await erinnerungRuhe(akte.name, was === "wieder-an" ? null : was === "nie" ? "nie" : akte.erinnerung.am);
      toast(was === "nie" ? "Für diesen Kunden keine Jahres-Erinnerung mehr – in der Kundenakte wieder einschaltbar"
        : was === "diesmal" ? "Erinnerung für dieses Jahr ausgeblendet – nächstes Jahr kommt sie wieder" : "Jahres-Erinnerung wieder an");
      if ($("#tab-start").classList.contains("active")) renderStart();
      return oeffneAkte(akte.name);
    }
    if (was === "zu") return $("#kundenakte").close();
    if (was === "notiz") {
      const d = await api(`kunden/${k.id}/notiz`, { method: "PUT", body: { notiz: $("#ka-notiz").value } });
      k.notiz = d.notiz;
      $("#ka-notiz-stand").textContent = "✓ gespeichert";
      if (state.kundeId === k.id) kundenNotizZeigen(k);
      return;
    }
    $("#kundenakte").close();
    if (was === "angebot") { await neuesAngebot(); fillKunde({ ...k, id: k.id || null }); }
    if (was === "rechnung") { await neueRechnung(); fillKunde({ ...k, id: k.id || null }); }
    if (was === "vertrag") neuerVertrag();
    if (was === "wieder") await kopiere("angebot", akte.erinnerung.letzte.beleg);
  } catch (err) { toast(err.message, true); }
});

// ---------- Stammdaten → Kunden: Übersicht mit Umsatz, Feiern, Stammkunde ----------

async function kaKundenListe(sec, kunden) {
  try { await kaLaden(); } catch (e) { return; }
  const karte = $$(".card", sec)[1], tbody = $("tbody", karte);
  if (!kunden.length) return;
  $("h2", karte).insertAdjacentHTML("afterend", `<p class="hint">Ein Klick auf den Namen öffnet die Kundenakte mit allen Angeboten, Verträgen, Rechnungen und Barzahlungen.</p>`);
  tbody.insertAdjacentHTML("beforebegin", `<thead><tr><th>Kunde</th><th>Feiern</th><th class="num">Umsatz</th><th>Letzte / nächste Feier</th><th></th></tr></thead>`);
  const zeilen = $$("tr[data-id]", tbody).map(tr => {
    const ku = kunden.find(x => x.id === Number(tr.dataset.id)), k = kennzahlen(ku.name);
    const td = tr.children[0];
    td.replaceChildren(kundeLink(ku.name, true));
    if (k.stamm) td.insertAdjacentHTML("beforeend", `<span class="ku-stamm">Stammkunde</span>`);
    td.insertAdjacentHTML("beforeend", `<br><small>${esc([ku.strasse, [ku.plz, ku.ort].filter(Boolean).join(" ")].filter(Boolean).join(", "))}</small>`);
    tr.children[1].textContent = k.feiern.length;
    tr.children[1].insertAdjacentHTML("afterend", `<td class="num">${euroGanz(k.umsatz)}</td>
      <td>${k.naechste ? `nächste ${fmtDate(k.naechste)}` : k.letzte ? `zuletzt ${fmtDate(k.letzte)}` : "–"}</td>`);
    return { tr, umsatz: k.umsatz };
  });
  zeilen.sort((a, b) => b.umsatz - a.umsatz).forEach(z => tbody.append(z.tr));
}
