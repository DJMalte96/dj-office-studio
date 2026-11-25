/* DJ Office Studio – Frontend. Alle URLs relativ, damit es hinter dem HA-Ingress-Pfad funktioniert. */
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
  ausVertrag: null,   // Vertrag, aus dem die Rechnung im Editor erzeugt wird (seit 1.14)
  gueltigAuto: true,  // „Gültig bis“ folgt dem Angebotsdatum, bis es von Hand geändert wird
};

// ---------- Hilfsfunktionen ----------

// Kennzeichnet Anfragen der App selbst – ohne diesen Kopf lehnt der Server alles ab, was etwas ändert
const SCHUTZ = { "X-DJOS": "1" };

async function api(path, opts = {}) {
  const res = await fetch("api/" + path, {
    headers: opts.body ? { "Content-Type": "application/json", ...SCHUTZ } : SCHUTZ,
    ...opts,
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  if (!res.ok) {
    let msg = `Fehler ${res.status}`, daten = null;
    try { daten = await res.json(); msg = daten.error || msg; } catch (_) { /* kein JSON */ }
    throw Object.assign(new Error(msg), { daten });
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

/* Desktop-App im eigenen Fenster (pywebview): PDFs, Downloads und externe Links laufen über die
   Brücke zum Starter (window.pywebview.api), weil ein App-Fenster keine Tabs und keine Downloads kennt. */
const appFenster = () => !!(window.pywebview && window.pywebview.api);
window.addEventListener("pywebviewready", () => document.body.classList.add("app-fenster"));

function blobAlsBase64(blob) {
  return new Promise((ok, fehler) => {
    const r = new FileReader();
    r.onload = () => ok(String(r.result).split(",")[1]);
    r.onerror = () => fehler(r.error);
    r.readAsDataURL(blob);
  });
}

/* PDF der App anzeigen (url relativ, z. B. „api/rechnungen/3/pdf“) */
function zeigePdf(url) {
  if (appFenster()) {
    window.pywebview.api.pdf_oeffnen(url).catch(e => toast("PDF konnte nicht geöffnet werden: " + e.message, true));
    return;
  }
  window.open(url, "_blank");
}

/* Öffnet ein PDF in neuem Tab. Das Fenster wird sofort (synchron zum Klick) geöffnet,
   damit Popup-Blocker nicht eingreifen. Im App-Fenster: im PDF-Programm des Systems. */
async function openPdf(loader, name = "Dokument.pdf") {
  if (appFenster()) {
    try {
      const blob = await loader();
      await window.pywebview.api.pdf_daten_oeffnen(name, await blobAlsBase64(blob));
    } catch (e) { toast(e.message, true); }
    return;
  }
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

document.addEventListener("click", e => {
  const a = e.target.closest("a[target=_blank]");
  if (!a || !appFenster()) return;
  e.preventDefault();
  const href = a.getAttribute("href") || "";
  if (href.startsWith("api/")) zeigePdf(href);
  else if (href && href !== "#") window.pywebview.api.extern(a.href);
});

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
  if (typeof finanzenTab === "function") finanzenTab(name);   // finanzen.js
  if (typeof vertraegeTab === "function") vertraegeTab(name);  // vertraege.js
  const stamm = $(`#tab-${name}[data-stamm]`);
  if (stamm) renderStamm(stamm.dataset.stamm);
}
$$("nav [data-tab]").forEach(b => b.addEventListener("click", () => {
  const tab = b.dataset.tab;
  if (tab === "neu") neueRechnung();
  else if (tab === "angebot-neu") neuesAngebot();
  else if (tab === "vertrag-neu") { schliesseMenues(); neuerVertrag(); }
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
  pflichtfelder();
}

/* Rechnungen brauchen die vollständige Kundenanschrift und je Position ein Lieferdatum (bei Angeboten freiwillig). */
function pflichtfelder() {
  const rechnung = state.modus !== "angebot";
  ["#k-strasse", "#k-plz", "#k-ort"].forEach(s => { $(s).required = rechnung; });
  $$("#positionen .lieferdatum").forEach(f => { f.required = rechnung; });
}

const istAngebot = () => state.modus === "angebot";

function speichernText() {
  const art = istAngebot() ? "Angebot" : "Rechnung";
  $("#btn-senden").classList.toggle("hidden", !state.editId);
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
  // nur bei vollständigem Datum (die Texteingabe liefert bei ungültiger Eingabe den Rohtext)
  if (istAngebot() && state.gueltigAuto && /^\d{4}-\d{2}-\d{2}$/.test(e.target.value)) $("#a-gueltig").value = addDays(e.target.value, gueltigkeitTage());
});
$("#a-gueltig").addEventListener("input", () => { state.gueltigAuto = false; });
$("#logo").addEventListener("click", () => showTab("start"));

// ---------- Einstellungen ----------

$("#einstellungen-btn").addEventListener("click", () => showTab("einstellungen"));
document.addEventListener("click", e => {
  if (e.target.closest(".zu-einstellungen")) { e.preventDefault(); showTab("einstellungen"); }
});

// Alle Jahresmenüs: Jahre aus dem ganzen Bestand (api/finanzen/jahre), nie aus einer schon gefilterten Liste
function jahresAuswahl(sel, jahre, gewaehlt) {
  const html = [...new Set([...jahre.map(String), gewaehlt])].sort().reverse().map(j => `<option>${j}</option>`).join("");
  if (sel.dataset.jahre !== html) sel.innerHTML = sel.dataset.jahre = html;   // nur bei Änderung, sonst klappt ein offenes Menü zu
  sel.value = gewaehlt;
}

async function ladeEinstellungen() {
  const [werte, jahre] = await Promise.all([api("einstellungen"), api("finanzen/jahre")]);
  jahresAuswahl($("#export-jahr"), jahre, String(new Date().getFullYear()));
  const form = $("#einstellungen");
  for (const [k, v] of Object.entries(werte)) {
    const feld = form.elements[k];
    if (!feld) continue;
    if (feld.type === "checkbox") feld.checked = !!v; else feld.value = v ?? "";
  }
  zeigePasswortStatus(werte.smtp_passwort_gesetzt);
  if (typeof plEinstellungen === "function") plEinstellungen(werte);
  form.elements.km_satz.value = Number(werte.km_satz || 0.3).toFixed(2).replace(".", ",");
  zeigeUstFelder();
  waehleAnbieter(ANBIETER.find(a => a.server && a.server === werte.smtp_server)?.id
    || (werte.smtp_server ? "andere" : ""), false);
}

function zeigeUstFelder() {
  $("#ust-felder").classList.toggle("hidden", $("#einstellungen").elements.kleinunternehmer.checked);
}
$("#einstellungen").elements.kleinunternehmer.addEventListener("change", zeigeUstFelder);

/* ---- E-Mail-Versand: Anbieter-Vorlagen (nur Vorschläge – alle Felder bleiben frei änderbar) ---- */
const FREISCHALTEN = "Im Postfach muss der Zugriff über externe E-Mail-Programme (POP3/IMAP/SMTP) erlaubt sein:";
const ANBIETER = [
  { id: "webde", name: "WEB.DE", server: "smtp.web.de", port: 587, sicherheit: "starttls", domains: ["web.de"],
    hinweis: `${FREISCHALTEN} WEB.DE → Einstellungen → POP3/IMAP Abruf → „… über externe Programme“ aktivieren.` },
  { id: "gmx", name: "GMX", server: "mail.gmx.net", port: 587, sicherheit: "starttls",
    domains: ["gmx.de", "gmx.net", "gmx.at", "gmx.ch"],
    hinweis: `${FREISCHALTEN} GMX → Einstellungen → POP3/IMAP Abruf → „… über externe Programme“ aktivieren.` },
  { id: "gmail", name: "Gmail / Google Mail", server: "smtp.gmail.com", port: 587, sicherheit: "starttls",
    domains: ["gmail.com", "googlemail.com"],
    hinweis: "Das normale Google-Passwort funktioniert nicht: Bestätigung in zwei Schritten einschalten und unter Google-Konto → Sicherheit → App-Passwörter ein App-Passwort erzeugen und hier eintragen." },
  { id: "outlook", name: "Outlook.com / Hotmail", server: "smtp-mail.outlook.com", port: 587, sicherheit: "starttls",
    domains: ["outlook.com", "outlook.de", "hotmail.com", "hotmail.de", "live.com", "live.de", "msn.com"],
    hinweis: "Microsoft erlaubt die Anmeldung per Passwort bei privaten Konten teilweise nicht mehr – falls die Testmail scheitert, bitte ein anderes Postfach verwenden." },
  { id: "icloud", name: "iCloud Mail", server: "smtp.mail.me.com", port: 587, sicherheit: "starttls",
    domains: ["icloud.com", "me.com", "mac.com"],
    hinweis: "Benötigt ein app-spezifisches Passwort (Apple-Account → Anmeldung und Sicherheit → App-spezifische Passwörter). Benutzername = vollständige iCloud-Adresse." },
  { id: "tonline", name: "Telekom / T-Online", server: "securesmtp.t-online.de", port: 465, sicherheit: "ssl",
    domains: ["t-online.de", "magenta.de"],
    hinweis: "Benötigt das separate E-Mail-Passwort aus dem Telekom-Kundencenter (nicht das Login-Passwort)." },
  { id: "yahoo", name: "Yahoo Mail", server: "smtp.mail.yahoo.com", port: 465, sicherheit: "ssl",
    domains: ["yahoo.com", "yahoo.de"], hinweis: "Benötigt ein App-Passwort (Yahoo-Kontosicherheit → App-Passwort erstellen)." },
  { id: "freenet", name: "freenet Mail", server: "mail.freenet.de", port: 587, sicherheit: "starttls",
    domains: ["freenet.de"], hinweis: `${FREISCHALTEN} freenet → Einstellungen → POP3/IMAP/SMTP aktivieren.` },
  { id: "ionos", name: "IONOS (1&1)", server: "smtp.ionos.de", port: 587, sicherheit: "starttls", domains: [] },
  { id: "strato", name: "STRATO", server: "smtp.strato.de", port: 465, sicherheit: "ssl", domains: [] },
  { id: "posteo", name: "Posteo", server: "posteo.de", port: 587, sicherheit: "starttls", domains: ["posteo.de", "posteo.net"] },
  { id: "mailbox", name: "mailbox.org", server: "smtp.mailbox.org", port: 465, sicherheit: "ssl", domains: ["mailbox.org"] },
  { id: "andere", name: "Anderer Anbieter / eigene Domain / eigener Server",
    hinweis: "Die Daten für den Postausgangsserver (SMTP) findest du in der Hilfe deines Anbieters bzw. in der Verwaltung deines Webhosters – meist Server, Port 587 mit STARTTLS oder Port 465 mit SSL/TLS." },
];
$("#mail-anbieter").innerHTML = `<option value="">– bitte wählen –</option>`
  + ANBIETER.map(a => `<option value="${a.id}">${esc(a.name)}</option>`).join("");

function waehleAnbieter(id, ausfuellen = true) {
  const a = ANBIETER.find(x => x.id === id);
  $("#mail-anbieter").value = id || "";
  $("#mail-anbieter-hinweis").textContent = a?.hinweis || "";
  if (!ausfuellen || !a?.server) return;
  const f = $("#einstellungen").elements;
  f.smtp_server.value = a.server;
  f.smtp_port.value = a.port;
  f.smtp_sicherheit.value = a.sicherheit;
}
$("#mail-anbieter").addEventListener("change", e => waehleAnbieter(e.target.value));
// Server von Hand geändert → passende Vorlage oder „Anderer Anbieter“ anzeigen
$("#einstellungen").elements.smtp_server.addEventListener("input", e => {
  const server = e.target.value.trim();
  waehleAnbieter(ANBIETER.find(a => a.server && a.server === server)?.id || (server ? "andere" : ""), false);
});
// Anbieter anhand der E-Mail-Adresse vorschlagen, solange kein eigener Server eingetragen ist
$("#einstellungen").elements.absender_email.addEventListener("change", e => {
  const domain = e.target.value.trim().toLowerCase().split("@")[1];
  const a = ANBIETER.find(x => (x.domains || []).includes(domain));
  const server = $("#einstellungen").elements.smtp_server.value.trim();
  if (a && (!server || ANBIETER.some(x => x.server === server))) waehleAnbieter(a.id);
});

function zeigePasswortStatus(gesetzt) {
  const f = $("#einstellungen").elements.smtp_passwort;
  f.value = "";
  f.placeholder = gesetzt ? "•••••••• gespeichert – nur zum Ändern neu eingeben" : "Passwort bzw. App-Passwort";
  $("#passwort-status").innerHTML = gesetzt
    ? `(gespeichert · <a href="#" id="passwort-entfernen">entfernen</a>)` : "(wird nur lokal gespeichert)";
}
$("#passwort-status").addEventListener("click", async e => {
  if (e.target.id !== "passwort-entfernen") return;
  e.preventDefault();
  if (!confirm("Gespeichertes E-Mail-Passwort entfernen?")) return;
  try {
    await api("einstellungen", { method: "PUT", body: { smtp_passwort: null } });
    zeigePasswortStatus(false);
    await ladeAbsender();
    toast("Passwort entfernt");
  } catch (err) { toast(err.message, true); }
});

const MAIL_FELDER = ["absender_email", "smtp_server", "smtp_port", "smtp_sicherheit", "smtp_benutzer",
  "smtp_passwort", "mail_antwort_an", "name"];
$("#mail-test").addEventListener("click", async e => {
  const btn = e.currentTarget;
  const f = $("#einstellungen").elements;
  const daten = Object.fromEntries(MAIL_FELDER.map(k => [k, f[k].value.trim()]));
  if (!daten.absender_email || !daten.smtp_server) return toast("Bitte zuerst E-Mail-Adresse und Postausgangsserver eintragen.", true);
  const vorher = btn.innerHTML;
  btn.disabled = true;
  btn.textContent = "Sende Testmail …";
  try {
    const res = await api("versand/test", { method: "POST", body: daten });
    toast(`Testmail an ${res.an} gesendet – schau in dein Postfach. Einstellungen speichern nicht vergessen!`);
  } catch (err) { toast("Testmail fehlgeschlagen: " + err.message, true); }
  finally { btn.disabled = false; btn.innerHTML = vorher; }
});

/* Sicherung herunterladen; der Server merkt sich den Zeitpunkt → Startseite aktualisieren */
function sicherungHerunterladen() {
  ladeHerunter("api/backup");
  toast("Sicherung wird heruntergeladen … Am besten an einem anderen Ort ablegen (Cloud, USB-Stick).");
  setTimeout(async () => {
    await ladeAbsender();
    if ($("#tab-start").classList.contains("active")) renderStart();
  }, 1500);
}
$("#sicherung-btn").addEventListener("click", sicherungHerunterladen);
$("#export-btn").addEventListener("click", () => {
  ladeHerunter(`api/export?jahr=${$("#export-jahr").value}`);
  toast(`Export ${$("#export-jahr").value} wird heruntergeladen …`);
});
$("#wiederherstellen-btn").addEventListener("click", () => $("#sicherung-datei").click());
$("#sicherung-datei").addEventListener("change", async e => {
  const datei = e.target.files[0];
  e.target.value = "";
  if (!datei || !confirm(`Sicherung „${datei.name}“ einspielen?\n\nAlle aktuellen Daten (Kunden, Rechnungen, `
      + "Angebote, Einstellungen) werden durch die Sicherung ersetzt. Der aktuelle Stand wird vorher automatisch "
      + "gesichert.")) return;
  const fd = new FormData();
  fd.append("datei", datei);
  try {
    const res = await fetch("api/backup", { method: "POST", headers: SCHUTZ, body: fd });
    const daten = await res.json();
    if (!res.ok) throw new Error(daten.error || `Fehler ${res.status}`);
    const n = daten.anzahl;
    alert(`Sicherung eingespielt: ${n.rechnungen} Rechnungen, ${n.kunden} Kunden${n.angebote != null ? `, ${n.angebote} Angebote` : ""}`
      + `${n.ausgaben != null ? `, ${n.ausgaben} Ausgaben` : ""}${daten.belege ? `, ${daten.belege} Belege` : ""}.`
      + "\n\nDie App wird neu geladen.");
    location.reload();
  } catch (err) { toast("Einspielen fehlgeschlagen: " + err.message, true); }
});

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
    let res;
    try {
      res = await api("einstellungen", { method: "PUT", body: daten });
    } catch (err) {
      if (!err.daten?.offene_rechnungen) throw err;
      const verschickt = await frageVerschickt(err.daten.offene_rechnungen);
      if (!verschickt) return toast("Nicht gespeichert – der Absender bleibt, wie er war.", true);
      res = await api("einstellungen", { method: "PUT", body: { ...daten, schon_verschickt: verschickt } });
      if (verschickt.length) await loadListe();
    }
    zeigePasswortStatus(res.einstellungen.smtp_passwort_gesetzt);
    if (typeof plEinstellungen === "function") plEinstellungen(res.einstellungen);
    await ladeAbsender();
    pruefeUpdate();
    toast(res.hinweise.length ? `Gespeichert. Hinweis: ${res.hinweise.join(" ")}` : "Einstellungen gespeichert", !!res.hinweise.length);
    // Neue Startnummern sofort im Editor berücksichtigen
    if (!state.editId) $("#r-nummer").value = (await api(istAngebot() ? "angebote/naechste-nummer" : "rechnungen/naechste-nummer")).nummer;
  } catch (err) { toast(err.message, true); }
});

/* Absender geändert und es gibt nicht festgeschriebene Rechnungen: Welche sind schon verschickt?
   → Liste der IDs, oder null bei Abbrechen. */
function frageVerschickt(liste) {
  const dlg = $("#absender-dialog"), heute = today();
  $("#absender-liste").innerHTML = liste.map(r => `<label class="inline"><input type="checkbox" value="${r.id}"${r.datum < heute ? " checked" : ""}>
    <span><b>${esc(r.nummer)}</b> · ${fmtDate(r.datum)} · ${esc(r.kunde)} · ${fmtEuro(r.gesamt)}</span></label>`).join("");
  return new Promise(fertig => {
    dlg.returnValue = "";
    dlg.addEventListener("close", () => fertig(dlg.returnValue === "speichern"
      ? [...dlg.querySelectorAll("#absender-liste input:checked")].map(i => Number(i.value)) : null), { once: true });
    dlg.showModal();
  });
}
$("#absender-abbrechen").addEventListener("click", () => $("#absender-dialog").close(""));
$("#absender-speichern").addEventListener("click", () => $("#absender-dialog").close("speichern"));

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

/* Hinweis „Nutzung ohne Gewähr“: einmal pro Installation bestätigen, danach unter ⚙ Einstellungen nachlesbar. */
function zeigeHinweis(pflicht) {
  const d = $("#hinweis-dialog");
  d.dataset.pflicht = pflicht ? "1" : "";
  if (!d.open) d.showModal();
}
$("#hinweis-dialog").addEventListener("cancel", e => {   // Esc schließt nur, wenn schon bestätigt
  if (e.currentTarget.dataset.pflicht) e.preventDefault();
});
$("#hinweis-ok").addEventListener("click", async () => {
  const d = $("#hinweis-dialog");
  if (d.dataset.pflicht) {
    try { await api("hinweis", { method: "POST" }); state.absender.hinweis_bestaetigt = true; }
    catch (err) { return toast(err.message, true); }
  }
  d.close();
});
$("#daten-ordner-btn").addEventListener("click", () => appFenster() && window.pywebview.api.daten_ordner());
$("#hinweis-zeigen").addEventListener("click", e => { e.preventDefault(); zeigeHinweis(false); });

/* Absender-Infos laden und alles aktualisieren, was davon abhängt (Hinweis-Banner, Paperless-Buttons …). */
async function ladeAbsender() {
  const abs = await api("absender");
  state.absender = abs;
  $("#app-version").textContent = abs.version || "–";
  document.body.classList.toggle("desktop", !!abs.desktop);   // Desktop-Version: HA-spezifische Hinweise ausblenden
  $("#warnung").classList.toggle("hidden", abs.vollstaendig);
  $("#warnung-fehlt").textContent = (abs.fehlt || []).join(", ");
  document.body.classList.toggle("ust", !abs.kleinunternehmer);   // Preise netto, Umsatzsteuer ausweisen
  updateTotal();
  $$(".pl-button").forEach(b => b.classList.toggle("hidden", !abs.paperless));   // nur mit „Paperless installiert“
  $("#paperless-abholen")?.classList.toggle("hidden", !abs.paperless_belege);      // nur wenn Abholen eingerichtet
  if (!abs.hinweis_bestaetigt) zeigeHinweis(true);
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
  setTimeout(() => typeof fahrtVorschau === "function" && fahrtVorschau(), 0);
  state.kundeId = k.id || null;
  $("#k-name").value = k.name || "";
  $("#k-zusatz").value = k.zusatz || "";
  $("#k-strasse").value = k.strasse || "";
  $("#k-plz").value = k.plz || "";
  $("#k-ort").value = k.ort || "";
  setKundeHinweis();
  kundeGewaehlt();   // Spickzettel und ggf. Anzahlungen der Schlussrechnung zum neuen Kunden
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
  if (p.anzahlung_id) {             // Abzug einer Anzahlung (Schlussrechnung) – Betrag kommt aus der Anzahlungsrechnung
    pos.dataset.anzahlung = p.anzahlung_id;
    pos.classList.add("abzug");
    $(".preis", pos).readOnly = true;
    $(".preis", pos).title = "Betrag der Anzahlungsrechnung – zum Ändern unten bei „Schlussrechnung“ abwählen";
  }

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
  const spick = () => spickzettel(pos);
  $(".tb", pos).addEventListener("change", spick);
  for (const k of ["von", "bis", "preis", "beschreibung"]) $("." + k, pos).addEventListener("input", spick);
  pos.addEventListener("click", e => {
    const b = e.target.closest(".spick-preis");
    if (!b) return;
    $(".preis", pos).value = b.dataset.preis;
    $(".preis", pos).dispatchEvent(new Event("input"));
  });
  $(".del", pos).addEventListener("click", () => {
    pos.remove();
    if (!$$("#positionen .pos").length) addPosition();
    updateTotal();
  });

  $("#positionen").append(pos);
  updateTotal();
  spickzettel(pos);
  return pos;
}
$("#pos-add").addEventListener("click", () => addPosition());
new MutationObserver(pflichtfelder).observe($("#positionen"), { childList: true });   // neue Positionen

/* Summe im Editor – ohne Kleinunternehmerregelung mit Nettobetrag, Umsatzsteuer und Bruttobetrag */
function updateTotal() {
  const netto = $$("#positionen .preis").reduce((s, i) => s + (Number(i.value) || 0), 0);
  const ust = istUst() ? Math.round(netto * ustSatz()) / 100 : 0;
  $("#ust-zeilen").classList.toggle("hidden", !istUst());
  if (istUst()) {
    $("#ust-zeilen").innerHTML = `<div><span>Nettobetrag</span><span>${fmtEuro(netto)}</span></div>
      <div><span>zzgl. ${String(ustSatz()).replace(".", ",")} % Umsatzsteuer</span><span>${fmtEuro(ust)}</span></div>`;
  }
  $("#gesamt").textContent = fmtEuro(netto + ust);
}
const istUst = () => !!state.absender && !state.absender.kleinunternehmer;
const ustSatz = () => Number(state.absender?.ust_satz) || 19;

// ---------- Art der Rechnung: normal / Anzahlung / Schluss (seit 1.11) ----------

const ANZ_SPEICHER = "djos-anzahlung";   // zuletzt gewählte Anzahlung (Prozent oder fester Betrag)
const ra = { modus: "normal", vorher: null, haken: new Set(), fahrt: null, kunde: "",
  ...(() => { try { const v = JSON.parse(localStorage.getItem(ANZ_SPEICHER)); return { art: v.art === "betrag" ? "betrag" : "prozent", wert: Number(v.wert) > 0 ? Number(v.wert) : 30 }; }
    catch { return { art: "prozent", wert: 30 }; } })() };
const gueltigeRechnungen = () => (state.rechnungen || []).filter(r => !r.storno_von && !r.storniert_durch);
const istAbzugText = t => /^abzüglich Anzahlung\b/.test(t || "");
/* Schlussrechnung, in der eine Anzahlungsrechnung abgezogen ist (ohne die gerade bearbeitete) */
const verrechnetIn = (anz, ausser = null) => gueltigeRechnungen().find(r => r.id !== ausser && r.rechnungsart === "schluss"
  && r.positionen.some(p => p.anzahlung_id === anz.id));
const anzahlungenZu = a => gueltigeRechnungen().filter(r => r.rechnungsart === "anzahlung" && r.angebot_id === a.id);
const veranstaltungAm = b => (b.positionen || []).map(p => p.lieferdatum).filter(Boolean).sort().at(-1) || null;
const ohneUhrzeit = t => (t || "").replace(/\s*–\s*\d{1,2}:\d{2} Uhr bis \d{1,2}:\d{2} Uhr\s*$/, "");
const posDaten = () => $$("#positionen .pos").map(p => ({ beschreibung: $(".beschreibung", p).value, lieferdatum: $(".lieferdatum", p).value,
  preis: $(".preis", p).value, anzahlung_id: p.dataset.anzahlung ? Number(p.dataset.anzahlung) : undefined }));
const anzBetrag = summe => ra.art === "betrag" ? Math.min(summe, ra.wert) : Math.round(summe * ra.wert) / 100;

function positionenSetzen(liste) {
  $("#positionen").innerHTML = "";
  (liste.length ? liste : [{}]).forEach(p => addPosition(p));
  updateTotal();
}

/* Beim Leeren bzw. Laden eines Belegs: Art übernehmen, ohne Positionen anzufassen */
function raZuruecksetzen(modus = "normal") {
  ra.modus = ["anzahlung", "schluss"].includes(modus) ? modus : "normal";
  ra.vorher = null; ra.fahrt = null; ra.haken = new Set();
  ra.kunde = $("#k-name").value.trim().toLowerCase();
  raAnzeigen();
}

/* Art wechseln. Anzahlung: die eingetragenen Positionen (Leistung mit Gesamtpreis) werden zu einer Anzahlungszeile –
   „Normale Rechnung“ holt sie zurück. Schluss: Anzahlungsrechnungen des Kunden zum Abziehen anbieten. */
async function raSetzen(modus, haken) {
  if (ra.modus === "anzahlung" && ra.vorher) positionenSetzen(ra.vorher);
  if (ra.modus === "schluss") positionenSetzen(posDaten().filter(p => !p.anzahlung_id));
  if (ra.modus === "anzahlung" && ra.fahrt !== null) $("#r-fahrt").checked = ra.fahrt;
  ra.vorher = null; ra.fahrt = null; ra.haken = new Set();
  if (modus === "anzahlung") {
    const daten = posDaten().filter(p => p.beschreibung.trim());
    if (!(daten.reduce((s, p) => s + (Number(p.preis) || 0), 0) > 0)) {
      toast("Erst die Leistung mit dem vereinbarten Gesamtpreis eintragen (z. B. Hochzeit, 1.200 €) – dann „Anzahlungsrechnung“ wählen.", true);
      modus = "normal";
    } else {
      ra.vorher = daten;
      ra.fahrt = $("#r-fahrt").checked;
      $("#r-fahrt").checked = false;          // die Fahrt gehört zur Schlussrechnung
    }
  }
  if (modus === "schluss") {
    try { state.rechnungen = await api("rechnungen"); } catch { /* mit dem Stand von eben weiter */ }
    ra.haken = new Set(haken || anzahlungKandidaten().filter(r => !verrechnetIn(r, state.editId)).map(r => r.id));
  }
  ra.modus = modus;
  ra.kunde = $("#k-name").value.trim().toLowerCase();
  raAnwenden();
}

/* Anzahlungsrechnungen dieses Kunden, die noch nicht (anderswo) abgezogen sind – plus die schon angehakten */
function anzahlungKandidaten() {
  const name = $("#k-name").value.trim().toLowerCase();
  return gueltigeRechnungen().filter(r => r.rechnungsart === "anzahlung" && r.id !== state.editId
    && (ra.haken.has(r.id) || (name && r.kunde.name.trim().toLowerCase() === name && !verrechnetIn(r, state.editId))))
    .sort((a, b) => a.datum.localeCompare(b.datum));
}

function raAnwenden() {
  if (ra.modus === "anzahlung" && ra.vorher) {
    const summe = ra.vorher.reduce((s, p) => s + (Number(p.preis) || 0), 0);
    const am = ra.vorher.map(p => p.lieferdatum).filter(Boolean).sort().at(-1);
    const ang = state.ausAngebot && (state.angebote || []).find(a => a.id === state.ausAngebot);
    positionenSetzen([{ beschreibung: `Anzahlung${ra.art === "prozent" ? ` ${String(ra.wert).replace(".", ",")} %` : ""} für `
      + `${ohneUhrzeit(ra.vorher[0].beschreibung)}${am ? ` am ${fmtDate(am)}` : ""}${ang ? ` laut Angebot ${ang.nummer}` : ""} (Gesamtpreis ${euroCent(summe)})`,
      lieferdatum: am || "", preis: anzBetrag(summe) }]);
  }
  if (ra.modus === "schluss") {
    const k = anzahlungKandidaten();
    positionenSetzen([...posDaten().filter(p => !p.anzahlung_id), ...k.filter(r => ra.haken.has(r.id)).map(r => ({
      beschreibung: `abzüglich Anzahlung laut Rechnung ${r.nummer} vom ${fmtDate(r.datum)}${r.bezahlt ? ` (bezahlt am ${fmtDate(r.bezahlt_am || r.datum)})` : ""}`,
      lieferdatum: veranstaltungAm(r) || r.datum, anzahlung_id: r.id,
      preis: -Math.round(r.positionen.reduce((s, p) => s + (Number(p.preis) || 0), 0) * 100) / 100 }))]);
  }
  raAnzeigen();
}

function raAnzeigen() {
  const box = $("#rechnungsart-teil");
  $$("#rechnungsart-box [name=rechnungsart]").forEach(i => { i.checked = i.value === ra.modus; });
  if (ra.modus === "normal") { box.innerHTML = ""; return; }
  if (ra.modus === "anzahlung") {
    if (!ra.vorher) { box.innerHTML = `<p class="mini-hinweis">Anzahlungsrechnung – den Betrag direkt in der Position ändern.</p>`; return; }
    const summe = ra.vorher.reduce((s, p) => s + (Number(p.preis) || 0), 0);
    box.innerHTML = `<div class="ra-zeile">Vereinbarter Gesamtpreis <b>${euroCent(summe)}</b> · Anzahlung
        <input type="number" min="1" step="1" id="ra-wert" value="${ra.wert}" aria-label="Anzahlung">
        <select id="ra-art" aria-label="Prozent oder Euro"><option value="prozent"${ra.art === "prozent" ? " selected" : ""}>%</option>
          <option value="betrag"${ra.art === "betrag" ? " selected" : ""}>€</option></select>
        = <b id="ra-betrag">${euroCent(anzBetrag(summe))}</b></div>
      <p class="mini-hinweis">Die Rechnung enthält nur die Anzahlung. Den Rest schreibst du nach der Feier als Schlussrechnung – die Fahrt wird dort erfasst. „Normale Rechnung“ holt die Positionen zurück.</p>`;
    return;
  }
  const k = anzahlungKandidaten(), name = $("#k-name").value.trim();
  box.innerHTML = k.length ? `<div class="ra-liste">${k.map(r => `<label><input type="checkbox" data-ra-anzahlung="${r.id}"${ra.haken.has(r.id) ? " checked" : ""}>
      <span>Rechnung ${esc(r.nummer)} vom ${fmtDate(r.datum)} · <b>${euroCent(r.gesamt)}</b> · ${r.bezahlt ? `bezahlt am ${fmtDate(r.bezahlt_am || r.datum)}` : "noch nicht bezahlt"}</span></label>`).join("")}</div>
      <p class="mini-hinweis">Angehakte Anzahlungen stehen als eigene Zeile mit Minus auf der Rechnung, der Gesamtbetrag ist der Rest.</p>`
    : `<p class="mini-hinweis">${name ? `Für „${esc(name)}“ gibt es keine offene Anzahlungsrechnung.` : "Erst den Kunden eintragen – dann erscheinen hier seine Anzahlungsrechnungen."}</p>`;
}

$("#rechnungsart-box").addEventListener("change", e => {
  if (e.target.name === "rechnungsart") return raSetzen(e.target.value).catch(err => toast(err.message, true));
  if (e.target.id === "ra-art") { ra.art = e.target.value; raMerken(); return raAnwenden(); }
  const id = Number(e.target.dataset.raAnzahlung);
  if (id) { e.target.checked ? ra.haken.add(id) : ra.haken.delete(id); raAnwenden(); }
});
$("#rechnungsart-box").addEventListener("input", e => {
  if (e.target.id !== "ra-wert" || !ra.vorher) return;
  const wert = Number(e.target.value);
  if (!(wert > 0)) return;
  ra.wert = wert; raMerken();
  // nur Zeile und Betrag anpassen – das Eingabefeld bleibt, damit man weitertippen kann
  const summe = ra.vorher.reduce((s, p) => s + (Number(p.preis) || 0), 0);
  const pos = $("#positionen .pos");
  $(".beschreibung", pos).value = $(".beschreibung", pos).value.replace(/^Anzahlung( [\d,]+ %)?/, `Anzahlung${ra.art === "prozent" ? ` ${String(wert).replace(".", ",")} %` : ""}`);
  $(".preis", pos).value = anzBetrag(summe);
  $("#ra-betrag").textContent = euroCent(anzBetrag(summe));
  updateTotal();
});
const raMerken = () => localStorage.setItem(ANZ_SPEICHER, JSON.stringify({ art: ra.art, wert: ra.wert }));
// Kunde gewechselt: passende Anzahlungen neu anbieten
const raKundeNeu = () => {
  const name = $("#k-name").value.trim().toLowerCase();
  if (name === ra.kunde) return;          // gleicher Kunde (z. B. beim Öffnen einer Rechnung) – Haken bleiben, wie sie sind
  ra.kunde = name;
  if (ra.modus === "schluss") { ra.haken = new Set(anzahlungKandidaten().filter(r => !verrechnetIn(r, state.editId)).map(r => r.id)); raAnwenden(); }
};
$("#k-name").addEventListener("change", raKundeNeu);

// ---------- Preis-Spickzettel (seit 1.11) ----------

/* Was hast du für diesen Rechnungsposten bisher genommen? Aus allen gültigen Rechnungen, Anzahlungen und Abzüge zählen nicht. */
const tbMuster = tb => new RegExp("^" + tb.text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&").replace(/\\\{(von|bis)\\\}/g, "(\\d{1,2}:\\d{2})") + "$");
const tbPasst = (tb, t) => !/^(Anzahlung|abzüglich Anzahlung)\b/.test(t) && (tbMuster(tb).test(t) || t.toLowerCase().includes(tb.titel.toLowerCase()));
const stundenIm = t => { const m = (t || "").match(/(\d{1,2}:\d{2}) Uhr bis (\d{1,2}:\d{2}) Uhr/); return m ? hoursBetween(m[1].padStart(5, "0"), m[2].padStart(5, "0")) : null; };
const auf10 = v => Math.round(v / 10) * 10;

function anlassDerPosition(pos) {
  if (pos._tb) return pos._tb;
  const t = $(".beschreibung", pos).value.trim();
  if (!t || pos.dataset.anzahlung || /^Anzahlung\b/.test(t)) return null;
  return state.textbausteine.find(tb => tbMuster(tb).test(t)) || state.textbausteine.find(tb => tbPasst(tb, t)) || null;
}

function spickzettel(pos) {
  let box = $(".spick", pos);
  if (!box) { box = document.createElement("div"); box.className = "spick"; pos.append(box); }
  const tb = ra.modus === "normal" || ra.modus === "schluss" ? anlassDerPosition(pos) : null;
  if (!tb) { box.hidden = true; box.dataset.html = ""; return; }
  const ausser = istAngebot() ? null : state.editId;
  const bisher = gueltigeRechnungen().filter(r => r.id !== ausser && r.rechnungsart !== "anzahlung")
    .flatMap(r => r.positionen.filter(p => !p.anzahlung_id && Number(p.preis) > 0 && tbPasst(tb, p.beschreibung))
      .map(p => ({ preis: Number(p.preis), am: p.lieferdatum || r.datum, kunde: r.kunde.name, std: stundenIm(p.beschreibung) })))
    .sort((a, b) => b.am.localeCompare(a.am));
  const zeilen = [];
  const knopf = v => `<button type="button" class="spick-preis" data-preis="${v}" title="Als Preis übernehmen">${euroGanz(v)}</button>`;
  if (!bisher.length) zeilen.push(`<b>${esc(tb.titel)}</b> hast du noch nicht abgerechnet – der Spickzettel füllt sich mit jeder Rechnung.`);
  else {
    const preise = bisher.map(x => x.preis), schnitt = preise.reduce((s, p) => s + p, 0) / preise.length;
    const min = Math.min(...preise), max = Math.max(...preise);
    zeilen.push(`<b>${esc(tb.titel)} bisher:</b> ${bisher.length}× · zuletzt ${knopf(bisher[0].preis)} (${esc(bisher[0].kunde)}, ${fmtDate(bisher[0].am)})`
      + ` · Schnitt ${knopf(auf10(schnitt))}${min !== max ? ` · ${euroGanz(min)} bis ${euroGanz(max)}` : ""}`);
    const mitStd = bisher.filter(x => x.std);
    const jetzt = hoursBetween($(".von", pos).value, $(".bis", pos).value) || stundenIm($(".beschreibung", pos).value);
    if (mitStd.length) {
      const proStd = mitStd.reduce((s, x) => s + x.preis / x.std, 0) / mitStd.length;
      zeilen.push(`im Schnitt <b>${euroGanz(proStd)} pro Stunde</b>${jetzt ? ` → für ${String(jetzt).replace(".", ",")} Std. ${knopf(auf10(proStd * jetzt))}` : " – mit Uhrzeiten rechnet die App die Dauer mit"}`);
    }
    const preis = Number($(".preis", pos).value);
    if (preis > 0) {
      const abw = Math.round((preis - schnitt) / schnitt * 100);
      if (Math.abs(abw) >= 15) zeilen.push(`<span class="spick-abw">Dein Preis liegt ${Math.abs(abw)} % ${abw < 0 ? "unter" : "über"} deinem Schnitt.</span>`);
    }
  }
  const name = $("#k-name").value.trim().toLowerCase();
  const echt = r => r.positionen.find(p => !p.anzahlung_id && Number(p.preis) > 0);
  const zuletzt = name && gueltigeRechnungen().filter(r => r.id !== ausser && r.rechnungsart !== "anzahlung" && echt(r)
    && r.kunde.name.trim().toLowerCase() === name).sort((a, b) => b.datum.localeCompare(a.datum))[0];
  if (zuletzt) {
    const p = echt(zuletzt);
    zeilen.push(`<b>${esc(zuletzt.kunde.name)}</b> hat zuletzt ${euroGanz(p.preis)} gezahlt (${esc(ohneUhrzeit(p.beschreibung).replace(/^DJ – (Tätigkeit )?/, ""))}, ${fmtDate(p.lieferdatum || zuletzt.datum)})`);
  }
  const html = zeilen.map(z => `<div>${z}</div>`).join("");
  // nur bei echter Änderung neu aufbauen – sonst geht ein Klick ins Leere, wenn das Feld davor den Fokus verliert
  if (box.dataset.html !== html) { box.innerHTML = html; box.dataset.html = html; }
  box.hidden = false;
}
for (const ev of ["input", "change"]) $("#k-name").addEventListener(ev, () => $$("#positionen .pos").forEach(spickzettel));
function kundeGewaehlt() { setTimeout(() => { raKundeNeu(); $$("#positionen .pos").forEach(spickzettel); }, 0); }

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
    vertrag_id: !istAngebot() && state.ausVertrag ? state.ausVertrag : undefined,
    veranstaltungsort: $("#v-wie-kunde").checked ? null
      : { name: $("#v-name").value, strasse: $("#v-strasse").value, plz: $("#v-plz").value, ort: $("#v-ort").value },
    fahrt_erfassen: istAngebot() ? undefined : $("#r-fahrt").checked,
    kunde: {
      id: state.kundeId,
      name: $("#k-name").value, zusatz: $("#k-zusatz").value, strasse: $("#k-strasse").value,
      plz: $("#k-plz").value, ort: $("#k-ort").value,
    },
    rechnungsart: istAngebot() ? undefined : ra.modus,
    positionen: $$("#positionen .pos").map(pos => ({
      beschreibung: $(".beschreibung", pos).value,
      lieferdatum: $(".lieferdatum", pos).value,
      preis: $(".preis", pos).value,
      anzahlung_id: pos.dataset.anzahlung ? Number(pos.dataset.anzahlung) : undefined,
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
  raZuruecksetzen();
  addPosition();
  setVeranstaltung(null, state.absender ? state.absender.fahrt_standard : true);
  speichernText();
}

// ---------- Veranstaltungsort & Fahrt (seit 1.1) ----------

/* ort: {name, strasse, plz, ort} oder null (= wie Kundenadresse); fahrt: „Fahrt erfassen“ (nur Rechnungen) */
function setVeranstaltung(ort, fahrt) {
  $("#v-wie-kunde").checked = !ort;
  $("#v-felder").classList.toggle("hidden", !ort);
  for (const k of ["name", "strasse", "plz", "ort"]) $(`#v-${k}`).value = (ort && ort[k]) || "";
  if (fahrt !== undefined) $("#r-fahrt").checked = !!fahrt;
  fahrtVorschau();
}

let fahrtTimer;
function fahrtVorschau() {
  clearTimeout(fahrtTimer);
  fahrtTimer = setTimeout(async () => {
    const info = $("#fahrt-info");
    if (!$("#r-fahrt").checked) { info.textContent = "Für diese Rechnung wird keine Fahrt angelegt."; return; }
    const a = state.absender || {};
    const wieKunde = $("#v-wie-kunde").checked;
    const adr = wieKunde ? { strasse: $("#k-strasse").value, plz: $("#k-plz").value, ort: $("#k-ort").value }
      : { strasse: $("#v-strasse").value, plz: $("#v-plz").value, ort: $("#v-ort").value };
    const art = a.fahrzeug === "betrieb" ? "als Nachweis (Betriebsfahrzeug)"
      : `als Ausgabe (Privatfahrzeug, ${String(Number(a.km_satz || 0.3).toFixed(2)).replace(".", ",")} €/km)`;
    if (!a.kartendienst) {
      info.textContent = "Hin- und Rückfahrt wird unter Finanzen → Fahrten erfasst – Kilometer dort eintragen "
        + "(automatische Berechnung lässt sich unter ⚙ Einstellungen einschalten).";
      return;
    }
    if (!adr.ort && !adr.plz) { info.textContent = "Entfernung wird berechnet, sobald die Adresse eingetragen ist."; return; }
    info.textContent = "Entfernung wird berechnet …";
    try {
      const v = await api(`fahrten/vorschau?${new URLSearchParams(adr)}`);
      info.textContent = v.km_einfach != null
        ? `≈ ${String(v.km_einfach).replace(".", ",")} km einfach · hin und zurück ${String(v.km_gesamt).replace(".", ",")} km`
          + (a.fahrzeug === "betrieb" ? ` · ${art}` : ` · ${fmtEuro(v.betrag)} ${art}`)
        : `Entfernung konnte nicht berechnet werden (${v.fehler || "Adresse prüfen"}) – Kilometer später unter Finanzen → Fahrten eintragen.`;
    } catch (e) { info.textContent = "Entfernung konnte nicht berechnet werden."; }
  }, 600);
}
$("#v-wie-kunde").addEventListener("change", e => {
  $("#v-felder").classList.toggle("hidden", e.target.checked);
  if (!e.target.checked) $("#v-name").focus();
  fahrtVorschau();
});
$("#r-fahrt").addEventListener("change", fahrtVorschau);
["#v-strasse", "#v-plz", "#v-ort", "#k-strasse", "#k-plz", "#k-ort"].forEach(s => $(s).addEventListener("input", fahrtVorschau));

/* Hinweis im Editor, wenn eine Rechnung aus einem Angebot erzeugt wird. */
function setAusAngebot(a) {
  state.ausAngebot = a ? a.id : null;
  state.ausVertrag = null;
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
  if (inv.festgeschrieben) {
    zeigePdf(`api/rechnungen/${inv.id}/pdf`);
    toast(`${rechnungsName(inv)} ist festgeschrieben – Änderungen nur per Storno.`);
    return;
  }
  setModus("rechnung");
  setAusAngebot(null);
  state.editId = inv.id;
  fillKunde({ ...inv.kunde, id: inv.kunde_id });
  $("#r-nummer").value = inv.nummer;
  $("#r-datum").value = inv.datum;
  setZahlung(inv.zahlungsbedingung);
  $("#positionen").innerHTML = "";
  raZuruecksetzen(inv.rechnungsart);
  inv.positionen.forEach(p => addPosition(p));
  setVeranstaltung(inv.veranstaltungsort, inv.fahrt_erfassen !== false);
  ra.haken = new Set(inv.positionen.filter(p => p.anzahlung_id).map(p => p.anzahlung_id));
  raAnzeigen();
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
  setVeranstaltung(a.veranstaltungsort);
  speichernText();
  showTab("neu");
  window.scrollTo(0, 0);
}

/* Rechnung bzw. Angebot als neuen Beleg kopieren: Kunde, Texte, Preise und Zahlungsbedingung übernehmen,
   neue Nummer und heutiges Datum. Das Lieferdatum bleibt leer – es ist ja eine neue Veranstaltung. */
async function kopiere(art, beleg) {
  setModus(art);
  await resetForm();
  fillKunde({ ...beleg.kunde, id: beleg.kunde_id });
  if (beleg.zahlungsbedingung) setZahlung(beleg.zahlungsbedingung);
  if (art === "angebot") $("#a-hinweise").value = beleg.hinweise || "";
  $("#positionen").innerHTML = "";
  beleg.positionen.filter(p => !p.anzahlung_id).forEach(p => addPosition({ beschreibung: p.beschreibung, preis: p.preis }));
  setVeranstaltung(beleg.veranstaltungsort);
  updateTotal();
  showTab("neu");
  window.scrollTo(0, 0);
  toast(`Kopie von ${art === "angebot" ? "Angebot" : "Rechnung"} ${beleg.nummer} – bitte Datum der Veranstaltung eintragen und speichern.`);
}

/* Angebot → neue Rechnung: Kunde, Positionen und ggf. Zahlungsbedingung übernehmen. */
async function angebotZuRechnung(a) {
  setModus("rechnung");
  await resetForm();
  fillKunde({ ...a.kunde, id: a.kunde_id });
  if (a.zahlungsbedingung) setZahlung(a.zahlungsbedingung);
  $("#positionen").innerHTML = "";
  a.positionen.forEach(p => addPosition(p));
  setVeranstaltung(a.veranstaltungsort);
  setAusAngebot(a);
  // Gibt es zum Angebot schon eine Anzahlung, wird das hier die Schlussrechnung
  const anz = anzahlungenZu(a).filter(r => !verrechnetIn(r));
  if (anz.length) await raSetzen("schluss", anz.map(r => r.id));
  showTab("neu");
  window.scrollTo(0, 0);
}

$("#btn-neu").addEventListener("click", () => resetForm());
$("#btn-senden").addEventListener("click", async () => {
  try {
    const art = istAngebot() ? "angebot" : "rechnung";
    oeffneVersand(art, await api(`${art === "angebot" ? "angebote" : "rechnungen"}/${state.editId}`));
  } catch (err) { toast(err.message, true); }
});

$("#btn-vorschau").addEventListener("click", () => {
  const data = { ...readForm(), id: istAngebot() ? undefined : state.editId || undefined };
  openPdf(() => { checkPlaceholders(data); return api("vorschau", { method: "POST", body: data }); },
    `Vorschau_${istAngebot() ? "Angebot" : "Rechnung"}_${data.nummer || "neu"}.pdf`);
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
    if (data.angebot_id || data.vertrag_id) setAusAngebot(null);   // Angebot angenommen bzw. Rechnung am Vertrag
    speichernText();
    toast(`${art} ${data.nummer} gespeichert` + (res.datei ? ` → ${res.datei.split("/").pop()}` : ""));
    return api(`${pfad}/${res.id}/pdf`);
  }, `${art}_${data.nummer}.pdf`);
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

const ICON_MAIL = `<svg class="ico" viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="5" width="18" height="14" rx="2"/><path d="m3.5 6.5 8.5 6.5 8.5-6.5"/></svg>`;

const ICON_EDIT = `<svg class="ico" viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 20h4L19 9l-4-4L4 16v4z"/><path d="m13.5 6.5 4 4"/></svg>`;
const ICON_QR = `<svg class="ico" viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3.5" y="3.5" width="6" height="6" rx="1"/><rect x="14.5" y="3.5" width="6" height="6" rx="1"/><rect x="3.5" y="14.5" width="6" height="6" rx="1"/><path d="M14.5 14.5h2.5v2.5M20.5 14.5v.01M14.5 20.5h.01M17.5 20.5h3v-3"/></svg>`;
const ICON_KOPIE = `<svg class="ico" viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="8.5" y="8.5" width="12" height="12" rx="2"/><path d="M15.5 8.5V5.5a2 2 0 0 0-2-2h-8a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h3"/></svg>`;
const OHNE_UEBERWEISUNG = /\bbar\b|bereits|beglichen|erhalten/i;   // wie im Server: „Bar erhalten“, „Bereits bezahlt“
const aktionen = (...welche) => welche.map(a => ({
  pdf: `<button class="small secondary" data-act="pdf">PDF</button>`,
  edit: `<button class="small secondary" data-act="edit">Bearbeiten</button>`,
  del: `<button class="small danger" data-act="del">Löschen</button>`,
  storno: `<button class="small danger" data-act="storno" title="Stornorechnung erstellen">Stornieren</button>`,
  kopie: `<button class="small secondary" data-act="kopie" title="Als neue Rechnung kopieren (z. B. für Stammkunden)" aria-label="Kopieren">${ICON_KOPIE}</button>`,
  senden: `<button class="small secondary" data-act="senden" title="Per E-Mail senden, herunterladen oder teilen" aria-label="Senden">${ICON_MAIL}</button>`,
}[a] || "")).join("");

/* Offen = weder bezahlt noch storniert noch selbst eine Stornorechnung */
const istOffen = r => !r.bezahlt && !r.storno_von && !r.storniert_durch;
const NAECHSTE_MAHNUNG = ["Zahlungserinnerung", "1. Mahnung", "2. Mahnung"];
const MAHN_KURZ = { 1: "Erinnerung", 2: "1. Mahnung", 3: "2. Mahnung" };

const schloss = r => r.festgeschrieben
  ? ` <span class="schloss" title="${esc("Festgeschrieben – Änderungen nur per Storno" + absenderInfo(r.absender))}">🔒</span>` : "";
function absenderInfo(a) {
  if (!a) return "";
  const woher = { nachgetragen: " (nachträglich festgehalten – kann vom Original abweichen)",
    import: " (beim Import festgehalten – Original ist deine importierte PDF)" }[a.quelle] || "";
  return `\nAbsender: ${[a.name, a.strasse, a.plz_ort].filter(Boolean).join(", ")}${woher}`;
}

function stornoChip(r) {
  if (r.storno_von) return ` <span class="storno-chip">Storno zu ${esc(r.storno_zu?.nummer || "?")}</span>`;
  if (r.storniert_durch) return ` <span class="storno-chip">storniert → ${esc(r.storniert_durch_nummer || "?")}</span>`;
  return "";
}

const mahnVersand = (r, m) => (r.versand || []).filter(v => v.mahnung_id === m.id).pop();
const mahnChips = r => (r.mahnungen || []).map(m => {
  const v = mahnVersand(r, m);
  return ` <a class="mahn-chip" href="api/mahnungen/${m.id}/pdf" target="_blank" rel="noopener"
       title="${MAHN_KURZ[m.stufe]} vom ${fmtDate(m.datum)} – Frist bis ${fmtDate(m.frist)}${v ? ` – per E-Mail an ${esc(v.an)} am ${fmtDate(v.zeitpunkt.slice(0, 10))}` : ""}">${MAHN_KURZ[m.stufe]} ${fmtDate(m.datum)}${v ? " ✉" : ""}</a>`;
}).join("");

/* „✉ 17.11.26“ – zuletzt per E-Mail versendet (Rechnung bzw. Angebot selbst, ohne Mahnungen) */
function versandChip(b) {
  const v = (b.versand || []).filter(x => !x.mahnung_id);
  if (!v.length) return "";
  const letzte = v[v.length - 1];
  return ` <span class="versand-chip" title="${v.map(x => `per E-Mail an ${esc(x.an)} am ${fmtDate(x.zeitpunkt.slice(0, 10))} ${x.zeitpunkt.slice(11, 16)} Uhr`).join("\n")}">✉ ${fmtDate(letzte.zeitpunkt.slice(0, 10))}</span>`;
}

function renderOffen() {
  const offen = state.rechnungen.filter(istOffen).map(r => ({ ...r, ziel: zahlungsziel(r) }));
  // Überfällige zuerst, dann nach Fälligkeit, Rechnungen ohne Frist am Ende
  offen.sort((a, b) => (a.ziel ? a.ziel.faellig : Infinity) - (b.ziel ? b.ziel.faellig : Infinity)
    || a.datum.localeCompare(b.datum));

  const summe = offen.reduce((s, r) => s + r.gesamt, 0);
  const dringendste = offen[0];   // Liste ist nach Fälligkeit sortiert

  $("#offen").innerHTML = `
    <h2>Offene Rechnungen</h2>
    ${offen.length ? `<table class="list offen-liste">
      <thead><tr><th>Rechnung</th><th class="num">Betrag</th><th>Verbleibende Zeit</th><th class="haken-spalte">Bezahlt</th><th></th></tr></thead>
      <tbody>
      <tr class="summen-zeile">
        <td>${offen.length} offene Rechnung${offen.length === 1 ? "" : "en"}</td>
        <td class="num">${fmtEuro(summe)}</td>
        <td><span class="naechste">nächste Frist:</span> ${fristBadge(dringendste.ziel)}</td>
        <td></td><td></td>
      </tr>
      ${offen.map(r => `<tr data-id="${r.id}">
        <td><a href="#" class="rlink" title="${r.festgeschrieben ? "PDF öffnen (festgeschrieben)" : "Im Editor öffnen"}">${esc(rechnungsName(r))}</a>${artChip(r)}${schloss(r)}${versandChip(r)}${mahnChips(r)}</td>
        <td class="num">${fmtEuro(r.gesamt)}</td>
        <td title="${r.ziel ? `fällig am ${utcToDe(r.ziel.faellig)}` : ""}">${fristBadge(r.ziel)}</td>
        <td class="haken-spalte"><input type="checkbox" class="offen-haken" title="Als bezahlt markieren → ins Archiv"></td>
        <td class="btns offen-aktionen">
          ${r.mahnungen.length < 3 ? `<button type="button" class="small ${r.ziel && r.ziel.rest < 0 ? "" : "secondary"}" data-act="mahnung"
              title="${NAECHSTE_MAHNUNG[r.mahnungen.length]} als PDF erstellen">${NAECHSTE_MAHNUNG[r.mahnungen.length]}</button>` : ""}
          ${OHNE_UEBERWEISUNG.test(r.zahlungsbedingung || "") ? "" : `<button type="button" class="icon senden" data-act="qr" title="QR-Code zum Bezahlen anzeigen (z. B. direkt nach der Feier)" aria-label="QR-Code">${ICON_QR}</button>`}
          <button type="button" class="icon senden" data-act="senden" title="Per E-Mail senden, herunterladen oder teilen" aria-label="Senden">${ICON_MAIL}</button>
          <button type="button" class="icon senden" data-act="kopie" title="Als neue Rechnung kopieren (z. B. für Stammkunden)" aria-label="Kopieren">${ICON_KOPIE}</button>
          ${r.festgeschrieben ? "" : `<button type="button" class="icon" data-act="lock" title="Festschreiben (z. B. nach dem Versenden) – danach nur noch Storno">🔒</button>`}
          <button type="button" class="icon del" data-act="${r.festgeschrieben ? "storno" : "del"}"
            title="${r.festgeschrieben ? "Rechnung stornieren" : "Rechnung löschen"}">✕</button>
        </td>
      </tr>`).join("")}
      </tbody></table>`
    : `<p class="hint alles-bezahlt">Keine offenen Rechnungen – alles bezahlt.</p>`}`;
}

// ---------- Archiv (bezahlte Rechnungen) ----------

const plChip = r => ` <button type="button" class="pl-chip" data-act="pl-reset" title="An Paperless übertragen am ${
  fmtDate(r.paperless_am.slice(0, 10))} – klicken zum Zurücksetzen"><span class="pl-ok">Paperless ✓</span><span class="pl-x">Paperless ✕</span></button>`;

/* Link-Download (Server sendet Content-Disposition: attachment) */
function ladeHerunter(url) {
  if (appFenster()) {   // App-Fenster: „Speichern unter“-Dialog
    window.pywebview.api.speichern(url)
      .then(name => { if (name) toast(`Gespeichert: ${name}`); })
      .catch(e => toast("Speichern fehlgeschlagen: " + e.message, true));
    return;
  }
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
  const list = sortiere(state.rechnungen.filter(r => !istOffen(r) &&
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
      <td>${esc(r.nummer)}${artChip(r)}${schloss(r)}${stornoChip(r)}${versandChip(r)}${r.paperless_am
        ? plChip(r) : ""}${r.gesperrt ? ` <span class="lock" title="Einnahme in einem abgeschlossenen Jahr">🔒 ${(r.storno_von ? r.datum : r.bezahlt_am || "").slice(0, 4)}</span>` : ""}</td>
      <td>${fmtDate(r.datum)}</td>
      <td><button type="button" class="kunde-link" data-akte="${esc(r.kunde.name)}" title="Kundenakte öffnen">${esc(r.kunde.name)}</button><br><small>${esc(r.kunde.ort)}</small></td>
      <td class="num">${fmtEuro(r.gesamt)}</td>
      <td>${r.storno_von || r.storniert_durch ? `<span class="frist neutral">${r.storno_von ? "Storno" : "storniert"}</span>`
        : `<input type="checkbox" class="bezahlt" checked${r.gesperrt ? ` disabled title="Bezahlt in einem abgeschlossenen Jahr – zum Ändern das Jahr wieder öffnen"`
          : ` title="Haken entfernen = zurück zu den offenen Rechnungen"`}>`}</td>
      <td class="btns">${aktionen("pdf", "senden", ...(r.storno_von ? [] : ["kopie"]), ...(!r.festgeschrieben ? ["edit", "del"]
        : r.storno_von || r.storniert_durch ? [] : ["storno"]))}</td>
    </tr>`).join("") ||
    `<tr><td colspan="7" class="hint">${q ? "Keine Treffer im Archiv." : "Noch keine bezahlten oder stornierten Rechnungen im Archiv."}</td></tr>`;
  $("#liste-summe").textContent = list.length
    ? `${list.length} Rechnung${list.length === 1 ? "" : "en"} · Summe ${fmtEuro(list.reduce((s, r) => s + r.gesamt, 0))}` : "";
  renderAuswahl();
}

/* Auswahl-Leiste + „Alle“-Checkbox passend zur aktuellen Auswahl. */
function renderAuswahl() {
  // Nur Rechnungen behalten, die noch existieren und im Archiv sind
  const archivIds = new Set(state.rechnungen.filter(r => !istOffen(r)).map(r => r.id));
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
    if (btn.dataset.act === "pdf") zeigePdf(`api/rechnungen/${id}/pdf`);
    if (btn.dataset.act === "senden") oeffneVersand("rechnung", inv);
    if (btn.dataset.act === "qr") await oeffneQr(inv);
    if (btn.dataset.act === "kopie") await kopiere("rechnung", inv);
    if (btn.dataset.act === "edit") loadIntoForm(inv);
    if (btn.dataset.act === "pl-reset" && confirm(`Paperless-Markierung bei ${rechnungsName(inv)} zurücksetzen?\n\n`
        + "Die Rechnung gilt dann wieder als nicht übertragen und kann erneut an Paperless gesendet werden. "
        + "Die Datei in Paperless selbst bleibt davon unberührt.")) {
      await api(`rechnungen/${id}/paperless`, { method: "DELETE" });
      inv.paperless_am = null;
      renderListe();
      toast(`Paperless-Markierung bei ${rechnungsName(inv)} zurückgesetzt`);
    }
    if (btn.dataset.act === "del") {
      const hoechste = Math.max(...state.rechnungen.map(r => parseInt(r.nummer, 10) || 0));
      const luecke = (parseInt(inv.nummer, 10) || 0) < hoechste
        ? "\n\nAchtung: Es gibt schon spätere Rechnungsnummern – durch das Löschen entsteht eine Lücke im Nummernkreis. "
          + "Wurde die Rechnung schon verschickt, besser festschreiben und stornieren." : "";
      if (confirm(`${rechnungsName(inv)} wirklich löschen?${luecke}`)) {
        await api("rechnungen/" + id, { method: "DELETE" });
        if (state.editId === id) resetForm();
        await loadListe();
        toast(`${rechnungsName(inv)} gelöscht`);
      }
    }
    if (btn.dataset.act === "lock" && confirm(`${rechnungsName(inv)} festschreiben?\n\n`
        + "Danach lässt sich die Rechnung nicht mehr ändern oder löschen – Korrekturen nur noch per Storno. "
        + "Bezahlte, gemahnte oder an Paperless gesendete Rechnungen werden automatisch festgeschrieben.")) {
      await api(`rechnungen/${id}/festschreiben`, { method: "POST" });
      await loadListe();
      toast(`${rechnungsName(inv)} ist festgeschrieben`);
    }
    if (btn.dataset.act === "storno" && confirm(`${rechnungsName(inv)} stornieren?\n\n`
        + "Es wird eine Stornorechnung mit neuer Nummer und negativen Beträgen erstellt; beide Rechnungen landen "
        + "im Archiv. Das lässt sich nicht rückgängig machen.")) {
      openPdf(async () => {
        const res = await api(`rechnungen/${id}/stornieren`, { method: "POST" });
        await loadListe();
        toast(`Stornorechnung ${res.nummer} zu ${rechnungsName(inv)} erstellt`);
        return api(`rechnungen/${res.id}/pdf`);
      }, `Stornorechnung_zu_${inv.nummer}.pdf`);
    }
    if (btn.dataset.act === "mahnung") {
      const stufe = NAECHSTE_MAHNUNG[inv.mahnungen.length];
      if (confirm(`${stufe} zu ${rechnungsName(inv)} erstellen?\n\nDas PDF öffnet sich zum Versenden; `
          + "die Rechnung wird dabei festgeschrieben.")) {
        openPdf(async () => {
          const res = await api(`rechnungen/${id}/mahnung`, { method: "POST" });
          await loadListe();
          toast(`${res.bezeichnung} zu ${rechnungsName(inv)} erstellt` + (res.datei ? ` → ${res.datei.split("/").pop()}` : ""));
          return api(`mahnungen/${res.id}/pdf`);
        }, `${stufe.replace(". ", "-")}_${inv.nummer}.pdf`);
      }
    }
  } catch (err) { toast(err.message, true); }
});

// ---------- Angebote ----------

const STATUS_TEXT = { offen: "offen", angenommen: "angenommen", abgelehnt: "abgelehnt" };

/* Nachfassen (seit 1.11): gezählt ab dem letzten Versand per Mail, sonst ab dem Angebotsdatum; einmal pro Angebot */
const gesendetAm = a => { const v = (a.versand || []).at(-1); return v ? v.zeitpunkt.slice(0, 10) : a.datum; };
const nachfassenFaellig = a => {
  const tage = Number(state.absender?.nachfassen_tage ?? 7);
  return tage > 0 && a.status === "offen" && !a.nachgefragt_am && (!a.gueltig_bis || a.gueltig_bis >= isoLokal(new Date()))
    && tageSeit(gesendetAm(a)) >= tage;
};
const keineAntwort = a => { const n = tageSeit(gesendetAm(a)); return `keine Antwort seit ${n} ${n === 1 ? "Tag" : "Tagen"}`; };
const nachgefragtChip = a => a.nachgefragt_am
  ? ` <span class="versand-chip" title="${esc(a.nachgefragt_wie || "")}">nachgefragt ${fmtDate(a.nachgefragt_am).slice(0, 6)}</span>` : "";
/* Angenommenes Angebot mit Anzahlung, aber noch ohne Schlussrechnung */
const schlussOffen = a => a.status === "angenommen" && anzahlungenZu(a).some(r => !verrechnetIn(r));
const artChip = r => r.rechnungsart === "anzahlung" ? ` <span class="art-chip">Anzahlung</span>`
  : r.rechnungsart === "schluss" ? ` <span class="art-chip">Schlussrechnung</span>` : "";
const auswahlA = new Set();   // IDs der markierten Angebote
const angebotName = a => a.name || `Angebot_${a.nummer}`;

async function loadAngebote() {
  try {
    [state.angebote, state.rechnungen, ka.bar] = await Promise.all([api("angebote"), api("rechnungen"), api("barzahlungen")]);
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
        <td><a href="#" class="rlink" title="Im Editor öffnen">${esc(angebotName(a))}</a>${versandChip(a)}${nachgefragtChip(a)}<br><small>${esc(a.kunde.name)}</small></td>
        <td>${fmtDate(a.datum)}</td>
        <td class="num">${fmtEuro(a.gesamt)}</td>
        <td>${restBadge(a)}${nachfassenFaellig(a) ? `<span class="nf-hinweis">${keineAntwort(a)}</span>` : ""}</td>
        <td class="btns offen-aktionen">${nachfassenFaellig(a) ? `<button class="small secondary" data-act="nachfragen" title="Kurz nachfragen, ob das Angebot passt">Nachfragen</button>` : ""}<button class="small" data-act="rechnung" title="Rechnung aus diesem Angebot erstellen">→ Rechnung</button><button type="button" class="icon senden" data-act="senden" title="Per E-Mail senden, herunterladen oder teilen" aria-label="Senden">${ICON_MAIL}</button></td>
      </tr>`).join("")}
      </tbody></table>`
    : `<p class="hint alles-bezahlt">Keine offenen Angebote.</p>`}`;
}

$("#angebote-offen").addEventListener("click", async e => {
  const tr = e.target.closest("tr[data-id]");
  if (!tr) return;
  const a = state.angebote.find(x => x.id === Number(tr.dataset.id));
  if (e.target.closest("a.rlink")) { e.preventDefault(); loadAngebotIntoForm(a); }
  if (e.target.closest("button[data-act='senden']")) oeffneVersand("angebot", a);
  if (e.target.closest("button[data-act='nachfragen']")) oeffneNachfrage(a);
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
      <td>${esc(a.nummer)}${versandChip(a)}${a.paperless_am ? plChip(a) : ""}</td>
      <td>${fmtDate(a.datum)}</td>
      <td>${esc(a.kunde.name)}<br><small>${esc(a.kunde.ort)}</small></td>
      <td class="num">${fmtEuro(a.gesamt)}</td>
      <td>${gueltigBadge(a)}${(() => {
        const anz = anzahlungenZu(a);
        return anz.length ? `<br><small>Anzahlung ${euroGanz(anz.reduce((s, r) => s + r.gesamt, 0))} ${anz.every(r => r.bezahlt) ? "bezahlt" : "offen"}</small>` : "";
      })()}</td>
      <td><select class="status-select ${a.status}" title="Status des Angebots">${Object.entries(STATUS_TEXT)
        .map(([k, t]) => `<option value="${k}"${k === a.status ? " selected" : ""}>${t}</option>`).join("")}</select></td>
      <td class="btns">
        <button class="small secondary" data-act="pdf">PDF</button>
        <button class="small secondary" data-act="senden" title="Per E-Mail senden, herunterladen oder teilen" aria-label="Senden">${ICON_MAIL}</button>
        <button class="small secondary" data-act="kopie" title="Als neues Angebot kopieren" aria-label="Kopieren">${ICON_KOPIE}</button>
        <button class="small secondary" data-act="edit" title="Im Editor bearbeiten" aria-label="Bearbeiten">${ICON_EDIT}</button>
        ${schlussOffen(a) ? `<button class="small" data-act="rechnung" title="Schlussrechnung schreiben – die Anzahlung wird abgezogen">→ Schlussrechnung</button>`
          : a.rechnung_id ? "" : `<button class="small" data-act="rechnung" title="Rechnung aus diesem Angebot erstellen">→ Rechnung</button>`}
        <button type="button" class="icon del" data-act="del" title="Angebot löschen" aria-label="Löschen">✕</button>
      </td>
    </tr>`).join("") ||
    `<tr><td colspan="8" class="hint">${q ? "Keine Treffer." : "Noch keine Angebote – mit „＋ Neues Angebot“ das erste schreiben."}</td></tr>`;
  kaAngeboteErgaenzen();   // „Bar bezahlt“, Kundenakte (kundenakte.js)
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
    if (btn.dataset.act === "pdf") zeigePdf(`api/angebote/${id}/pdf`);
    if (btn.dataset.act === "senden") oeffneVersand("angebot", a);
    if (btn.dataset.act === "kopie") await kopiere("angebot", a);
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

// ---------- QR-Code zum Bezahlen (GiroCode) ----------

let qrRechnung = null;
async function oeffneQr(inv) {
  const info = await api(`rechnungen/${inv.id}/girocode?info=1`);   // wirft verständliche Fehler (z. B. IBAN fehlt)
  qrRechnung = inv;
  $("#qr-titel").textContent = `Rechnung ${inv.nummer} bezahlen`;
  $("#qr-bild").src = `api/rechnungen/${inv.id}/girocode?t=${Date.now()}`;
  $("#qr-empfaenger").textContent = info.empfaenger;
  $("#qr-iban").textContent = info.iban;
  $("#qr-betrag").textContent = fmtEuro(info.betrag);
  $("#qr-zweck").textContent = info.zweck;
  $("#qr-dialog").showModal();
}
$("#qr-zu").addEventListener("click", () => $("#qr-dialog").close());
$("#qr-dialog").addEventListener("click", e => { if (e.target.id === "qr-dialog") $("#qr-dialog").close(); });   // Klick daneben
$("#qr-bezahlt").addEventListener("click", async () => {
  try {
    await setBezahlt(qrRechnung.id, true);
    $("#qr-dialog").close();
  } catch (err) { toast(err.message, true); }
});

// ---------- Versand: E-Mail, Herunterladen, Teilen ----------

const versand = { art: null, beleg: null, entwurf: null, dateien: null };
const kannTeilen = () => !!(navigator.canShare && window.isSecureContext
  && navigator.canShare({ files: [new File(["x"], "x.pdf", { type: "application/pdf" })] }));

/* Aktuell gewähltes Dokument: { art: rechnung|angebot|mahnung, mahnung } */
function versandDokument() {
  const v = $("#versand-dokument").value;
  if (versand.art === "angebot") return { art: "angebot" };
  if (versand.art === "vertrag") return { art: "vertrag" };
  const m = v && versand.beleg.mahnungen.find(x => String(x.id) === v);
  return m ? { art: "mahnung", mahnung: m } : { art: "rechnung" };
}

/* PDF-Adressen des gewählten Dokuments (bei Mahnungen: Mahnung + Rechnung) */
function versandPdfs() {
  const d = versandDokument();
  if (versand.art === "vertrag") return [`api/vertraege/${versand.beleg.id}/pdf`];
  const beleg = versand.art === "angebot" ? `api/angebote/${versand.beleg.id}/pdf` : `api/rechnungen/${versand.beleg.id}/pdf`;
  return d.mahnung ? [`api/mahnungen/${d.mahnung.id}/pdf`, beleg] : [beleg];
}

async function oeffneVersand(art, beleg) {
  versand.art = art;
  versand.beleg = beleg;
  $("#versand-titel").textContent = art === "vertrag" ? `${beleg.name} senden`
    : `${art === "angebot" ? "Angebot" : beleg.storno_von ? "Stornorechnung" : "Rechnung"} ${beleg.nummer} senden`;
  const mahnungen = art === "rechnung" ? beleg.mahnungen || [] : [];
  $("#versand-dokument").innerHTML = `<option value="">${art === "angebot" ? "Angebot" : beleg.storno_von ? "Stornorechnung" : "Rechnung"}</option>`
    + mahnungen.map(m => `<option value="${m.id}">${MAHN_KURZ[m.stufe] === "Erinnerung" ? "Zahlungserinnerung" : MAHN_KURZ[m.stufe]} vom ${fmtDate(m.datum)} (mit Rechnung)</option>`).join("");
  // Offene Rechnung mit Mahnung: standardmäßig die letzte Mahnung schicken
  $("#versand-dokument").value = mahnungen.length && istOffen(beleg) ? String(mahnungen[mahnungen.length - 1].id) : "";
  $("#versand-dokument-label").classList.toggle("hidden", !mahnungen.length);
  $("#versand-teilen").classList.toggle("hidden", !kannTeilen());
  try { await ladeEntwurf(); } catch (err) { return toast(err.message, true); }
  $("#versand").showModal();
  if (!$("#versand-mail").classList.contains("hidden")) ($("#versand-an").value ? $("#versand-text") : $("#versand-an")).focus();
}

async function ladeEntwurf() {
  const d = versandDokument();
  const e = await api(`versand/entwurf?art=${d.art}&id=${versand.beleg.id}${d.mahnung ? `&mahnung_id=${d.mahnung.id}` : ""}`);
  versand.entwurf = e;
  $("#versand-nicht-eingerichtet").classList.toggle("hidden", e.konfiguriert);
  $("#versand-mail").classList.toggle("hidden", !e.konfiguriert);
  $("#versand-senden").classList.toggle("hidden", !e.konfiguriert);
  $("#versand-an").value = e.an;
  $("#versand-betreff").value = e.betreff;
  $("#versand-text").value = e.text;
  $("#versand-kopie").checked = e.kopie;
  $("#versand-eigene").textContent = e.absender_email;
  $("#versand-anhaenge").innerHTML = e.anhaenge.map((n, i) =>
    `<a href="${versandPdfs()[i]}" target="_blank" rel="noopener" class="anhang">📎 ${esc(n)}</a>`).join("");
  $("#versand-frueher").textContent = e.versand.length
    ? "Bereits gesendet: " + e.versand.map(v => `${fmtDate(v.zeitpunkt.slice(0, 10))} an ${v.an}`).join(" · ") : "";
  pruefeEmailSpeichern();
  // Für „Teilen“ die PDFs schon jetzt laden – manche Browser erlauben Teilen nur direkt nach dem Klick
  versand.dateien = kannTeilen() ? Promise.all(versandPdfs().map(async (url, i) =>
    new File([await (await fetch(url)).blob()], e.anhaenge[i], { type: "application/pdf" }))) : null;
}

function pruefeEmailSpeichern() {
  const an = $("#versand-an").value.trim();
  const zeigen = !!an && !an.includes(",") && an.toLowerCase() !== (versand.entwurf?.kunde_email || "").toLowerCase();
  $("#versand-speichern-label").classList.toggle("hidden", !zeigen);
}
$("#versand-an").addEventListener("input", pruefeEmailSpeichern);
$("#versand-dokument").addEventListener("change", () => ladeEntwurf().catch(err => toast(err.message, true)));
$("#versand-abbrechen").addEventListener("click", () => $("#versand").close());
$("#versand-zu-einstellungen").addEventListener("click", () => {
  $("#versand").close();
  setTimeout(() => $("#mail-karte").scrollIntoView({ behavior: "smooth" }), 50);
});

$("#versand-download").addEventListener("click", () => {
  versandPdfs().forEach((url, i) => setTimeout(() => ladeHerunter(url), i * 400));
  toast(versandPdfs().length > 1 ? "PDFs werden heruntergeladen …" : "PDF wird heruntergeladen …");
});

$("#versand-teilen").addEventListener("click", async () => {
  try {
    const files = await versand.dateien;
    await navigator.share({ files, title: $("#versand-betreff").value });
  } catch (err) {
    if (err.name !== "AbortError") toast("Teilen nicht möglich – bitte herunterladen. (" + err.message + ")", true);
  }
});

$("#versand-form").addEventListener("submit", async e => {
  e.preventDefault();
  const d = versandDokument();
  const btn = $("#versand-senden");
  const vorher = btn.innerHTML;
  btn.disabled = true;
  btn.textContent = "Sende …";
  try {
    const res = await api("versand", { method: "POST", body: {
      art: d.art, id: versand.beleg.id, mahnung_id: d.mahnung?.id,
      an: $("#versand-an").value, betreff: $("#versand-betreff").value, text: $("#versand-text").value,
      kopie: $("#versand-kopie").checked,
      email_speichern: !$("#versand-speichern-label").classList.contains("hidden") && $("#versand-speichern").checked,
    } });
    $("#versand").close();
    toast(`✉ ${res.anhaenge.join(" + ")} an ${res.an.join(", ")} gesendet`);
    // Versendete Rechnungen sind festgeschrieben – Editor nicht mit veralteten Daten offen lassen
    if (versand.art === "rechnung" && !istAngebot() && state.editId === versand.beleg.id) await resetForm();
    if (versand.art === "vertrag") await vertragVerschickt(versand.beleg.id);
    else if (versand.art === "angebot") await loadAngebote(); else await loadListe();
  } catch (err) { toast("Senden fehlgeschlagen: " + err.message, true); }
  finally { btn.disabled = false; btn.innerHTML = vorher; }
});

// ---------- Nachfrage zum Angebot (seit 1.11) ----------

let nachfrageAngebot = null;
async function oeffneNachfrage(a) {
  nachfrageAngebot = a;
  let e;
  try { e = await api(`versand/entwurf?art=nachfrage&id=${a.id}`); } catch (err) { return toast(err.message, true); }
  $("#nachfrage-titel").textContent = `Nachfrage zu Angebot ${a.nummer}`;
  $("#nachfrage-info").textContent = `${a.kunde.name} · ${euroCent(a.gesamt)} · ${(a.versand || []).length ? "per Mail geschickt" : "erstellt"} am `
    + `${fmtDate(gesendetAm(a))} (${tageText(tageSeit(gesendetAm(a)))})${a.gueltig_bis ? ` · gültig bis ${fmtDate(a.gueltig_bis)}` : ""}`;
  $("#nachfrage-nicht-eingerichtet").classList.toggle("hidden", e.konfiguriert);
  for (const id of ["#nachfrage-mail", "#nachfrage-anhang-label", "#nachfrage-kopie-label", "#nachfrage-senden"]) $(id).classList.toggle("hidden", !e.konfiguriert);
  $("#nachfrage-an").value = e.an;
  $("#nachfrage-betreff").value = e.betreff;
  $("#nachfrage-text").value = e.text;
  $("#nachfrage-datei").textContent = "📎 " + e.anhaenge[0];
  $("#nachfrage-anhang").checked = true;
  $("#nachfrage-kopie").checked = e.kopie;
  $("#nachfrage").showModal();
}
async function nachNachfrage(text) {
  $("#nachfrage").close();
  toast(text);
  if ($("#tab-start").classList.contains("active")) await renderStart();
  if ($("#tab-angebote").classList.contains("active")) await loadAngebote();
}
$("#nachfrage-form").addEventListener("submit", async e => {
  e.preventDefault();
  const a = nachfrageAngebot, btn = $("#nachfrage-senden");
  btn.disabled = true;
  try {
    const res = await api("versand", { method: "POST", body: { art: "nachfrage", id: a.id, an: $("#nachfrage-an").value,
      betreff: $("#nachfrage-betreff").value, text: $("#nachfrage-text").value, kopie: $("#nachfrage-kopie").checked,
      anhang: $("#nachfrage-anhang").checked } });
    await nachNachfrage(`✉ Nachfrage zu Angebot ${a.nummer} an ${res.an.join(", ")} gesendet`);
  } catch (err) { toast("Senden fehlgeschlagen: " + err.message, true); }
  finally { btn.disabled = false; }
});
$("#nachfrage").addEventListener("click", async e => {
  const b = e.target.closest("[data-nf]");
  if (!b) return;
  const a = nachfrageAngebot;
  try {
    switch (b.dataset.nf) {
      case "zu": return $("#nachfrage").close();
      case "kopieren":
        await navigator.clipboard.writeText($("#nachfrage-text").value);
        return toast("Text kopiert – z. B. für WhatsApp");
      case "erledigt":
        await api(`angebote/${a.id}/nachgefragt`, { method: "POST", body: { wie: "von Hand vermerkt" } });
        return nachNachfrage(`Angebot ${a.nummer}: als nachgefragt vermerkt`);
      case "angenommen":
        $("#nachfrage").close();
        return angebotZuRechnung(a);
      case "abgelehnt":
        await api(`angebote/${a.id}/status`, { method: "PATCH", body: { status: "abgelehnt" } });
        return nachNachfrage(`Angebot ${a.nummer} als abgelehnt markiert`);
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

  if (table === "kunden") await kaKundenListe(sec, items);   // Übersicht mit Kundenakte (kundenakte.js)
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
    const res = await fetch("api/import/analyse", { method: "POST", headers: SCHUTZ, body: fd });
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

const tageSeit = iso => Math.max(0, Math.round((heuteUtc() - isoToUtc(iso.slice(0, 10))) / TAG_MS));
const tageText = n => n === 0 ? "heute" : n === 1 ? "gestern" : `vor ${n} Tagen`;

/* Startseite (seit 1.10): dunkler Kopf mit „Heute wichtig“, „Demnächst“, Pinnwand, „Dein Jahr“, Statuszeile.
   Wirkt auch in ruhigen Zeiten nicht leer: leere Spalten fallen weg, „Dein Jahr“ ist immer gefüllt. */
const TAG_KURZ = ["So", "Mo", "Di", "Mi", "Do", "Fr", "Sa"];
const isoLokal = d => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const euroGanz = v => Math.round(Number(v) || 0).toLocaleString("de-DE") + " €";
const euroCent = v => (Number(v) || 0).toLocaleString("de-DE", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + " €";
let startTag = null;          // in der 14-Tage-Leiste angeklickter Tag

function sicherungStand() {
  const s = state.absender?.sicherung || {};
  const intervall = Number(s.erinnerung_tage) || 0;
  const tage = s.letzte ? tageSeit(s.letzte) : null;
  const hatDaten = state.rechnungen.length || state.angebote.length;
  const faellig = tage === null ? !!(hatDaten && intervall) : !!intervall && tage >= intervall;
  let faelligAm = null;
  if (s.letzte && intervall) { const d = new Date(s.letzte.slice(0, 10) + "T12:00"); d.setDate(d.getDate() + intervall); faelligAm = isoLokal(d); }
  return { tage, faellig, faelligAm, letzte: s.letzte };
}

async function renderStart() {
  const box = $("#start");
  let eu, faellig, abos, abschluss;
  try {
    [state.rechnungen, state.angebote, , eu, faellig, abos, abschluss] = await Promise.all([api("rechnungen"), api("angebote"), ladeAbsender(),
      api(`finanzen/euer?jahr=${new Date().getFullYear()}`).catch(() => null), api("abos/faellig").catch(() => []),
      api("abos").catch(() => ({ abos: [] })), api("abschluss").catch(() => ({}))]);
  } catch (e) { return toast("Laden fehlgeschlagen: " + e.message, true); }
  const jetzt = new Date(), jahr = jetzt.getFullYear(), heute = isoLokal(jetzt);
  const offen = state.rechnungen.filter(istOffen).map(r => ({ ...r, ziel: zahlungsziel(r) }))
    .sort((a, b) => (a.ziel ? a.ziel.faellig : Infinity) - (b.ziel ? b.ziel.faellig : Infinity));
  const angebote = offeneAngebote();
  const pl = eu?.pruefliste || [];
  const belegPunkt = pl.find(p => p.aktion === "ausgaben" && p.stufe === "warn" && /Beleg/.test(p.text));
  const ohneDatum = pl.find(p => p.aktion === "bezahlt_am");
  const sich = sicherungStand();
  const ueber = offen.filter(r => r.ziel && r.ziel.rest < 0);

  // ---------- Termine (für „Demnächst“ bzw. die 14-Tage-Leiste) ----------
  const termine = {};
  const dazu = (datum, art, kurz, lang) => { (termine[datum] ||= []).push({ art, kurz, lang }); };
  for (const r of offen.filter(r => r.ziel)) {
    const tag = new Date(r.ziel.faellig).toISOString().slice(0, 10);
    dazu(tag < heute ? heute : tag, tag < heute ? "rot" : "ein", `${euroGanz(r.gesamt)} ${r.kunde.name.split(" ")[0]}`,
      `Rechnung ${r.nummer} (${r.kunde.name}, ${euroCent(r.gesamt)}) ${tag < heute ? `seit ${fmtDate(tag)} überfällig` : "fällig"}`);
  }
  for (const a of abos.abos.filter(a => a.naechste)) dazu(a.naechste, "aus", `${euroGanz(a.betrag_aktuell)} ${a.lieferant.split(" ")[0]}`,
    `Abo ${a.lieferant}: Abbuchung ${euroCent(a.betrag_aktuell)}`);
  for (const a of angebote.filter(a => a.gueltig_bis && a.gueltig_bis >= heute)) dazu(a.gueltig_bis, "ang", `Angebot ${a.nummer}`,
    `Angebot ${a.nummer} (${a.kunde.name}, ${euroCent(a.gesamt)}) läuft ab`);
  if (sich.faelligAm && sich.faelligAm > heute) dazu(sich.faelligAm, "ang", "Sicherung", "Datensicherung fällig");
  const tage = [...Array(15)].map((_, i) => { const d = new Date(jetzt); d.setDate(d.getDate() + i); return d; });

  // ---------- Heute wichtig ----------
  const wichtig = [];
  if (state.absender && !state.absender.vollstaendig) wichtig.push(["rot", "⚙ Angaben für Rechnungen fehlen", `data-start="einstellungen"`]);
  if (ueber.length) wichtig.push(["rot", `€ ${ueber.length} Rechnung${ueber.length === 1 ? "" : "en"} überfällig`, `data-start="zu-karte" data-ziel=".start-karte.rot"`]);
  const heuteFaellig = offen.filter(r => r.ziel && r.ziel.rest === 0).length;
  if (heuteFaellig) wichtig.push(["gelb", `€ ${heuteFaellig} heute fällig`, `data-start="zu-karte" data-ziel=".start-karte.gelb"`]);
  if (faellig.length) wichtig.push(["gelb", `↻ ${faellig.length} Abo${faellig.length === 1 ? "" : "s"} fällig`, `data-start="ausgaben"`]);
  if (belegPunkt) wichtig.push(["gelb", `⇪ ${esc(belegPunkt.text.replace(" noch nicht geprüft", " zu prüfen"))}`, `data-start="belege"`]);
  if (ohneDatum) wichtig.push(["gelb", "📅 Bezahlt-Datum fehlt", `data-start="bezahlt-am"`]);
  const baldAb = angebote.filter(a => a.rest !== null && a.rest >= 0 && a.rest <= 3).length;
  if (baldAb) wichtig.push(["gelb", `✎ ${baldAb} Angebot${baldAb === 1 ? " läuft" : "e laufen"} bald ab`, `data-start="angebote"`]);
  [ka.vertraege, ka.bar, ka.ruhe] = await Promise.all([api("vertraege").catch(() => []), api("barzahlungen").catch(() => []),
    api("kunden/erinnerung").catch(() => ({}))]);
  const vtOffen = ka.vertraege.filter(v => v.status === "verschickt").length;
  if (vtOffen) wichtig.push(["gelb", `✍ ${vtOffen} ${vtOffen === 1 ? "Vertrag" : "Verträge"} nicht unterschrieben zurück`, `data-start="vertraege"`]);
  const nachfassen = angebote.filter(nachfassenFaellig).length;
  if (nachfassen) wichtig.push(["gelb", `✉ ${nachfassen} Angebot${nachfassen === 1 ? "" : "e"} nachfragen`, `data-start="zu-karte" data-ziel=".start-karte.nachfassen"`]);
  // Gibt es zum Angebot einen Vertrag, erinnert der Vertrag an die Rechnung (kaStartChips) – nicht doppelt
  for (const a of state.angebote.filter(a => schlussOffen(a) && veranstaltungAm(a) && veranstaltungAm(a) <= heute
    && !ka.vertraege.some(v => v.angebot_id === a.id)))
    wichtig.push(["gelb", `✎ Schlussrechnung ${esc(a.kunde.name.split(" ")[0])}`, `data-start="schluss" data-angebot="${a.id}" title="Feier am ${fmtDate(veranstaltungAm(a))} – Anzahlung wird abgezogen"`]);
  for (const g of (eu?.grenzen?.hinweise || []).filter(g => g.stufe === "rot")) wichtig.push(["rot", "! Kleinunternehmer-Grenze", `data-start="finanzen" title="${esc(g.text)}"`]);
  if (sich.faellig) wichtig.push(["rot", "⇩ Sicherung fällig", `data-start="sichern"`]);
  const kaChips = kaStartChips(heute);   // Vertrag → Rechnung, Stammkunden (kundenakte.js)
  const erster = Object.entries(termine).filter(([t]) => t > heute).sort(([a], [b]) => a < b ? -1 : 1)[0];

  // ---------- Demnächst: Tagesleiste nur, wenn genug los ist ----------
  let zeit;
  if (tage.filter(d => termine[isoLokal(d)]).length >= 4) {
    zeit = `<section class="start-zeit"><div class="start-titel"><h3>Die nächsten 14 Tage</h3><small>Rechnungen fällig · Abbuchungen · Angebote laufen ab</small></div>
      <div class="start-tage">${tage.map((d, i) => {
        const t = isoLokal(d), liste = termine[t] || [], we = d.getDay() === 0 || d.getDay() === 6;
        return `<button type="button" class="start-tag${i === 0 ? " heute" : we ? " we" : ""}${startTag === t ? " offen" : ""}" data-tag="${t}">
          <span class="d">${i === 0 ? "heute" : TAG_KURZ[d.getDay()]}</span><span class="n">${d.getDate()}.</span>
          ${liste.slice(0, 3).map(x => `<span class="start-punkt ${x.art}" title="${esc(x.lang)}">${esc(x.kurz)}</span>`).join("")}${liste.length > 3 ? `<span class="start-punkt">+${liste.length - 3}</span>` : ""}</button>`;
      }).join("")}</div>
      ${startTag && termine[startTag] ? `<div class="start-detail"><b>${new Date(startTag + "T12:00").toLocaleDateString("de-DE", { weekday: "long", day: "numeric", month: "long" })}</b>
        <ul>${termine[startTag].map(x => `<li>${esc(x.lang)}</li>`).join("")}</ul></div>` : ""}</section>`;
  } else {
    const grenze = isoLokal(new Date(jetzt.getTime() + 60 * 864e5));
    const kommend = Object.entries(termine).filter(([t]) => t > heute && t <= grenze).sort(([a], [b]) => a < b ? -1 : 1)
      .flatMap(([t, l]) => l.map(x => ({ t, ...x }))).slice(0, 5);
    const inTagen = t => { const n = Math.round((new Date(t + "T12:00") - new Date(heute + "T12:00")) / 864e5); return n === 1 ? "morgen" : `in ${n} Tagen`; };
    zeit = `<section class="start-zeit"><div class="start-titel"><h3>Demnächst</h3><small>ab morgen · bis ${fmtDate(grenze)}</small></div>
      ${kommend.length ? `<div class="start-agenda">${kommend.map(x => `<div class="start-ag ${x.art}"><span class="dat"><b>${TAG_KURZ[new Date(x.t + "T12:00").getDay()]} ${fmtDate(x.t).slice(0, 6)}</b><small>${inTagen(x.t)}</small></span>
        <span>${esc(x.lang)}</span></div>`).join("")}</div>` : `<div class="start-ruhig">🎧 In den nächsten Wochen wird nichts fällig.</div>`}</section>`;
  }

  // ---------- Pinnwand: nur Spalten mit Inhalt ----------
  const schonFaellig = new Set(faellig.map(f => f.abo_id));     // steht schon als fällige Abbuchung da – nicht doppelt zeigen
  const kommendeAbos = abos.abos.filter(a => a.naechste && !a.beendet && !schonFaellig.has(a.id))
    .sort((a, b) => a.naechste < b.naechste ? -1 : 1).slice(0, 3);
  const spalten = [], leer = [];
  if (offen.length) spalten.push(`<div class="start-spalte"><h3>Geld kommt rein <small>${euroGanz(offen.reduce((s, r) => s + r.gesamt, 0))}</small></h3>
    ${offen.slice(0, 5).map(r => {
      const st = !r.ziel ? "" : r.ziel.rest < 0 ? "rot" : r.ziel.rest <= 3 ? "gelb" : "gruen";
      const m = r.mahnungen || [];
      return `<div class="start-karte ${st}" data-rechnung="${r.id}"><div class="z1"><span>${esc(r.kunde.name)}</span><span>${euroCent(r.gesamt)}</span></div>
        <small>${artChip(r)}Rechnung ${esc(r.nummer)} · ${r.ziel ? (r.ziel.rest < 0 ? `<b>${-r.ziel.rest} ${-r.ziel.rest === 1 ? "Tag" : "Tage"} überfällig</b>` : r.ziel.rest === 0 ? "heute fällig" : `fällig in ${r.ziel.rest} ${r.ziel.rest === 1 ? "Tag" : "Tagen"}`) : "ohne Frist"}${m.length ? ` · ${MAHN_KURZ[m.at(-1).stufe]} ${fmtDate(m.at(-1).datum)}` : ""}</small>
        <div class="k">${r.ziel && r.ziel.rest < 0 && m.length < 3 ? `<button type="button" class="small" data-start="mahnen">${NAECHSTE_MAHNUNG[m.length]}</button>` : ""}
          ${OHNE_UEBERWEISUNG.test(r.zahlungsbedingung || "") ? "" : `<button type="button" class="small secondary" data-start="qr">QR</button>`}
          <button type="button" class="small secondary" data-start="bezahlt">✓ Bezahlt</button></div></div>`;
    }).join("")}${offen.length > 5 ? `<a href="#" class="mehr" data-start="liste">alle ${offen.length} →</a>` : ""}</div>`);
  else leer.push("alle Rechnungen bezahlt");
  if (faellig.length || belegPunkt || kommendeAbos.length) {
    spalten.push(`<div class="start-spalte"><h3>Geld geht raus <small>${euroGanz(eu?.monate?.[jetzt.getMonth()]?.ausgaben)} im ${MONATE[jetzt.getMonth()]}</small></h3>
      ${faellig.map(f => `<div class="start-karte gelb"><div class="z1"><span>${esc(f.lieferant)}</span><span>${euroCent(f.betrag)}</span></div>
        <small>Abo · fällig ${fmtDate(f.datum)}${f.beleg ? " · Beleg schon da" : ""}</small>
        <div class="k"><button type="button" class="small" data-start="ausgaben">Bestätigen</button></div></div>`).join("")}
      ${belegPunkt ? `<div class="start-karte gelb"><div class="z1"><span>${esc(belegPunkt.text)}</span><span></span></div><small>hochgeladen oder aus dem Belege-Ordner</small>
        <div class="k"><button type="button" class="small" data-start="belege">Prüfen</button></div></div>` : ""}
      ${kommendeAbos.map(a => `<div class="start-karte"><div class="z1"><span>${esc(a.lieferant)}</span><span>${euroCent(a.betrag_aktuell)}</span></div>
        <small>nächste Abbuchung ${fmtDate(a.naechste)} · ${esc(a.rhythmus_name)}</small></div>`).join("")}</div>`);
  }
  if (!faellig.length && !belegPunkt) leer.push("keine Belege zu prüfen");
  if (angebote.length) spalten.push(`<div class="start-spalte"><h3>Angebote <small>${euroGanz(angebote.filter(a => a.rest === null || a.rest >= 0).reduce((s, a) => s + a.gesamt, 0))} offen</small></h3>
    ${angebote.slice(0, 5).map(a => `<div class="start-karte ${nachfassenFaellig(a) ? "gelb nachfassen" : a.rest !== null && a.rest < 0 ? "" : a.rest !== null && a.rest <= 3 ? "gelb" : "gruen"}" data-angebot="${a.id}">
      <div class="z1"><span>${esc(a.kunde.name)}</span><span>${euroCent(a.gesamt)}</span></div>
      <small>Angebot ${esc(a.nummer)} · ${a.rest === null ? "ohne Frist" : a.rest < 0 ? `seit ${-a.rest} ${-a.rest === 1 ? "Tag" : "Tagen"} abgelaufen` : a.rest === 0 ? "läuft heute ab" : `noch ${a.rest} ${a.rest === 1 ? "Tag" : "Tage"} gültig`}${nachfassenFaellig(a) ? `<span class="nf-hinweis">${keineAntwort(a)}</span>` : nachgefragtChip(a)}</small>
      <div class="k">${nachfassenFaellig(a) ? `<button type="button" class="small" data-start="nachfragen">Nachfragen</button>` : ""}${a.rest !== null && a.rest < 0 ? `<button type="button" class="small secondary" data-start="abgelehnt">Abgelehnt</button>`
        : `<button type="button" class="small" data-start="zu-rechnung">→ Rechnung</button><button type="button" class="small secondary" data-ka-start="bar" title="Bar bezahlt – Quittung von Hand">Bar bezahlt</button>`}<button type="button" class="small secondary" data-start="angebot">Ansehen</button></div></div>`).join("")}
    ${angebote.length > 5 ? `<a href="#" class="mehr" data-start="angebote">alle ${angebote.length} →</a>` : ""}</div>`);
  else leer.push("keine offenen Angebote");

  // ---------- Dein Jahr (immer gefüllt) ----------
  const imJahr = state.rechnungen.filter(r => r.datum.startsWith(String(jahr)) && !r.storno_von && !r.storniert_durch);
  const monate = eu?.monate || [];
  const bester = monate.reduce((b, m, i) => m.einnahmen > (monate[b]?.einnahmen || 0) ? i : b, 0);
  const kunden = new Set(imJahr.map(r => (r.kunde.name || "").trim().toLowerCase())).size;
  const g = eu?.grenzen, anteil = g ? Math.min(100, g.umsatz / g.grenze_vorjahr * 100) : null;
  const gruss = jetzt.getHours() < 11 ? "Guten Morgen" : jetzt.getHours() < 18 ? "Hallo" : "Guten Abend";
  const vorname = (state.absender?.name || "").trim().split(/\s+/)[0];

  box.innerHTML = `
    <section class="start-kopf">
      <div>
        <h2>${gruss}${vorname ? `, ${esc(vorname)}` : ""}!</h2>
        <div class="datum">${jetzt.toLocaleDateString("de-DE", { weekday: "long", day: "numeric", month: "long", year: "numeric" })}</div>
        <div class="wichtig">${wichtig.length || kaChips.length ? `<span class="wt">Heute wichtig</span>${wichtig.map(([s, t, attr]) => `<button type="button" class="start-chip ${s}" ${attr}>${t}</button>`).join("")}${kaChips.join("")}`
          : `<span class="ruhig">✓ Alles erledigt${erster ? ` · als Nächstes: ${fmtDate(erster[0]).slice(0, 6)} ${esc(erster[1][0].lang)}` : ""}</span>`}</div>
      </div>
      <div class="knoepfe"><button type="button" data-start="neu">＋ Neue Rechnung</button><button type="button" data-start="angebot-neu">＋ Neues Angebot</button>
        <button type="button" data-start="beleg">⇪ Beleg hochladen</button></div>
    </section>
    ${zeit}
    ${spalten.length ? `<section class="start-pinnwand" style="--spalten:${spalten.length}">${spalten.join("")}</section>` : ""}
    ${leer.length ? `<div class="start-leer">${leer.map(t => `<span>✓ ${t}</span>`).join("")}</div>` : ""}
    <section class="start-jahr"><h3>Dein Jahr ${jahr}</h3><div class="start-jahr-zahlen">
      <div><b>${imJahr.length}</b><small>Rechnung${imJahr.length === 1 ? "" : "en"} geschrieben</small></div>
      <div><b>${imJahr.length ? euroGanz(imJahr.reduce((s, r) => s + r.gesamt, 0) / imJahr.length) : "–"}</b><small>im Schnitt je Rechnung</small></div>
      <div><b>${monate[bester]?.einnahmen ? MONATE[bester] : "–"}</b><small>stärkster Monat${monate[bester]?.einnahmen ? ` · ${euroGanz(monate[bester].einnahmen)}` : ""}</small></div>
      <div><b>${kunden}</b><small>Kund${kunden === 1 ? "e" : "en"}</small></div>
      <div><b>${euroGanz(eu?.gewinn)}</b><small>${(eu?.gewinn || 0) < 0 ? "Verlust" : "Gewinn"} bisher</small></div></div></section>
    <section class="start-status">
      <button type="button" class="start-plakette${sich.faellig ? " rot" : ""}" data-start="sichern">⇩ Sicherung ${sich.tage === null ? "noch nie" : tageText(sich.tage)} – jetzt sichern</button>
      ${anteil !== null ? `<button type="button" class="start-plakette${anteil >= 80 ? " gelb" : ""}" data-start="finanzen">Kleinunternehmer-Grenze ${Math.round(anteil)} % <span class="mini"><i style="width:${anteil}%"></i></span></button>` : ""}
      ${abschluss.hinweis ? `<span class="start-plakette"><button type="button" class="link" data-start="abschluss" data-jahr="${Number(abschluss.hinweis)}">🔒 ${Number(abschluss.hinweis)} abschließen</button>
        <button type="button" class="link aus" data-start="abschluss-aus" data-jahr="${Number(abschluss.hinweis)}" title="Hinweis ausblenden" aria-label="Hinweis ausblenden">✕</button></span>` : ""}
    </section>`;
}

$("#start").addEventListener("click", async e => {
  const tag = e.target.closest("[data-tag]");
  if (tag) { startTag = startTag === tag.dataset.tag ? null : tag.dataset.tag; return renderStart(); }
  const b = e.target.closest("[data-start]");
  if (!b) return;
  e.preventDefault();
  const was = b.dataset.start;
  const rid = Number(b.closest("[data-rechnung]")?.dataset.rechnung), aid = Number(b.closest("[data-angebot]")?.dataset.angebot);
  const r = state.rechnungen.find(x => x.id === rid), a = state.angebote.find(x => x.id === aid);
  try {
    switch (was) {
      case "neu": return neueRechnung();
      case "angebot-neu": return neuesAngebot();
      case "beleg": showTab("ausgaben"); return setTimeout(() => $("#beleg-dateien").click(), 300);
      case "liste": case "angebote": case "ausgaben": case "finanzen": case "vertraege": return showTab(was);
      case "belege": showTab("ausgaben"); return setTimeout(() => $("#alle-pruefen")?.click(), 700);
      case "bezahlt-am": return oeffneBezahltAm();
      case "einstellungen": return $("#einstellungen-btn").click();
      case "zu-karte": {
        const z = $(`#start ${b.dataset.ziel}`);
        z?.scrollIntoView({ behavior: "smooth", block: "center" });
        return z?.animate([{ boxShadow: "0 0 0 3px var(--neon)" }, { boxShadow: "none" }], 1200);
      }
      case "mahnen":
        b.disabled = true;
        await api(`rechnungen/${rid}/mahnung`, { method: "POST" });
        toast(`${b.textContent} zu Rechnung ${r.nummer} erstellt – unter Rechnungen per E-Mail senden oder herunterladen`);
        break;
      case "qr": return oeffneQr(r);
      case "bezahlt":
        b.disabled = true;
        await api(`rechnungen/${rid}/bezahlt`, { method: "PATCH", body: { bezahlt: true } });
        toast(`Rechnung ${r.nummer} als bezahlt markiert`);
        break;
      case "angebot": return loadAngebotIntoForm(a);
      case "nachfragen": return oeffneNachfrage(a);
      case "schluss": return angebotZuRechnung(a);
      case "zu-rechnung": return angebotZuRechnung(a);
      case "abgelehnt":
        await api(`angebote/${aid}/status`, { method: "PATCH", body: { status: "abgelehnt" } });
        toast(`Angebot ${a.nummer} als abgelehnt markiert`);
        break;
      case "sichern": return sicherungHerunterladen();
      case "abschluss": showTab("euer"); return setTimeout(() => abschlussStarten(Number(b.dataset.jahr)), 400);
      case "abschluss-aus":
        await api("abschluss/hinweis-aus", { method: "POST", body: { jahr: Number(b.dataset.jahr) } });
        toast("Hinweis ausgeblendet – unter Finanzen → EÜR & Export bleibt der Knopf");
        break;
    }
  } catch (err) { b.disabled = false; return toast(err.message, true); }
  renderStart();
});

// ---------- Start ----------

(async () => {
  try {
    await ladeAbsender();
    pruefeUpdate();   // läuft im Hintergrund
    await loadLookups();
    await resetForm();
    await renderStart();
    if (typeof rundgangAnbieten === "function") rundgangAnbieten();   // nur bei neuer Installation (rundgang.js)
  } catch (e) {
    toast("Laden fehlgeschlagen: " + e.message, true);
  }
})();
