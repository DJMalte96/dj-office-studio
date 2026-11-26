/* DJ Office Studio – seit 1.15: Sicherungs-Passwort, verschlüsselte Sicherungen, Tageskopie in einen Cloud-Ordner.
   Das Passwort geht nur per POST an den Server und steht nie in einer Adresse. */
"use strict";

const sp = { st: null, einspielen: null };

async function sicherungStatusLaden() {
  try { sp.st = await api("sicherung"); } catch (e) { return; }
  const st = sp.st, box = $("#sp-box");
  box.classList.toggle("an", st.gesetzt);
  box.innerHTML = st.gesetzt
    ? `<div class="sp-kopf"><b>🔒 Sicherungen sind verschlüsselt</b><button type="button" class="small secondary" data-sp-box>Passwort ändern</button></div>
       <small>Passwort festgelegt am ${fmtDate(st.seit)}. Beim Herunterladen und Einspielen fragt die App jedes Mal danach.</small>
       ${st.desktop ? `<small>Automatische Tagessicherung: ebenfalls verschlüsselt – ganz ohne Eingabe.</small>` : ""}`
    : `<div class="sp-kopf"><b>Sicherungs-Passwort</b><button type="button" class="small" data-sp-box>Passwort festlegen</button></div>
       <small>Noch nicht festgelegt – Sicherungen sind unverschlüsselt. Wer die Datei bekommt (Cloud, USB-Stick, Mail), sieht Kunden, Bankdaten und Belege.</small>`;
  const k = $("#kopie-status");
  if (k) k.textContent = !st.kopie_ordner ? "Aus – Ordner eintragen und Einstellungen speichern."
    : !st.gesetzt ? "Für die Kopie bitte zuerst ein Sicherungs-Passwort festlegen."
    : st.kopie_fehler ? `Letzter Versuch fehlgeschlagen: ${st.kopie_fehler}`
    : st.kopie_am ? `Zuletzt kopiert am ${fmtDate(st.kopie_am.slice(0, 10))} um ${st.kopie_am.slice(11, 16)} Uhr – die letzten 7 Tage bleiben im Ordner.`
    : "Kopiert wird einmal am Tag beim Start der App.";
}

// ---------- Passwort festlegen / ändern ----------

function staerke(p) {
  const n = (p.length >= 10) + (p.length >= 14) + (/[A-ZÄÖÜ]/.test(p) && /[a-zäöüß]/.test(p)) + /\d/.test(p) + /[^A-Za-z0-9ÄÖÜäöüß]/.test(p);
  return p.length < 10 ? [Math.min(25, p.length * 2.5), "var(--danger)", "zu kurz – mindestens 10 Zeichen"]
    : n <= 2 ? [50, "var(--gelb)", "geht – länger oder gemischter wäre besser"]
    : n === 3 ? [75, "var(--primary)", "gut"] : [100, "var(--primary-d)", "sehr gut"];
}
$("#sp-neu").addEventListener("input", e => {
  const [breite, farbe, text] = staerke(e.target.value);
  $("#sp-balken").style.width = breite + "%";
  $("#sp-balken").style.background = farbe;
  $("#sp-staerke").textContent = text;
});

function passwortDialog() {
  const aendern = !!sp.st?.gesetzt;
  $("#sp-titel").textContent = aendern ? "Sicherungs-Passwort ändern" : "Sicherungs-Passwort festlegen";
  $("#sp-alt-label").classList.toggle("hidden", !aendern);
  $("#sp-alt-hinweis").classList.toggle("hidden", !aendern);
  for (const id of ["sp-alt", "sp-neu", "sp-neu2"]) $("#" + id).value = "";
  $("#sp-notiert").checked = false;
  $("#sp-neu").dispatchEvent(new Event("input"));
  $("#sp-dialog").showModal();
  (aendern ? $("#sp-alt") : $("#sp-neu")).focus();
}
$("#sp-box").addEventListener("click", e => { if (e.target.closest("[data-sp-box]")) passwortDialog(); });
$("#sp-dialog").addEventListener("click", async e => {
  const b = e.target.closest("[data-sp]");
  if (!b) return;
  if (b.dataset.sp === "zu") return $("#sp-dialog").close();
  const neu = $("#sp-neu").value;
  if (neu.length < (sp.st?.min_laenge || 10)) return toast("Bitte mindestens 10 Zeichen", true);
  if (neu !== $("#sp-neu2").value) return toast("Die beiden Eingaben sind verschieden", true);
  if (!$("#sp-notiert").checked) return toast("Bitte bestätigen, dass du das Passwort notiert hast", true);
  const erstes = !sp.st?.gesetzt;
  b.disabled = true;
  try {
    await api("sicherung/passwort", { method: "POST", body: { neu, alt: $("#sp-alt").value } });
    $("#sp-dialog").close();
    toast(erstes ? "Sicherungs-Passwort festgelegt – ab jetzt sind alle Sicherungen verschlüsselt"
      : "Passwort geändert – neue Sicherungen nutzen das neue Passwort");
    await sicherungStatusLaden();
  } catch (err) { toast(err.message, true); }
  b.disabled = false;
});

// ---------- Herunterladen ----------

/* Ersetzt das direkte Herunterladen: mit Passwort verschlüsselt, ohne Passwort mit Warnung. */
async function sicherungLaden() {
  await sicherungStatusLaden();
  const st = sp.st || {};
  sp.einspielen = null;
  $("#sp-laden-titel").textContent = "Sicherung herunterladen";
  if (st.gesetzt) {
    $("#sp-laden-inhalt").innerHTML = `<p class="hint">Die Sicherung wird mit deinem Sicherungs-Passwort verschlüsselt (Datei …<b>.djos</b>).</p>
      <label>Sicherungs-Passwort<input id="sp-eingabe" type="password" autocomplete="current-password"></label>`;
    $("#sp-laden-knoepfe").innerHTML = `<button type="button" class="secondary" data-l="zu">Abbrechen</button><button type="button" data-l="laden">⇩ Verschlüsselt herunterladen</button>`;
  } else {
    $("#sp-laden-inhalt").innerHTML = `<div class="sp-warn">Noch kein Sicherungs-Passwort – die Datei ist unverschlüsselt. Wer sie bekommt, sieht Kunden, Bankdaten und Belege.</div>`;
    $("#sp-laden-knoepfe").innerHTML = `<button type="button" class="secondary" data-l="ohne">Ohne Passwort herunterladen</button><button type="button" data-l="festlegen">Passwort festlegen</button>`;
  }
  $("#sp-laden").showModal();
  $("#sp-eingabe")?.focus();
}

function nachDerSicherung() {
  setTimeout(async () => {
    await ladeAbsender();
    if ($("#tab-start").classList.contains("active")) renderStart();
  }, 1500);
}

// ---------- Einspielen ----------

/* Datei einspielen; bei einer verschlüsselten Sicherung nach dem Passwort fragen. */
async function sicherungEinspielen(datei, passwort) {
  const fd = new FormData();
  fd.append("datei", datei);
  if (passwort) fd.append("passwort", passwort);
  const res = await fetch("api/backup", { method: "POST", headers: SCHUTZ, body: fd });
  const daten = await res.json().catch(() => ({}));
  if (!res.ok && daten.passwort) {
    if (passwort) toast(daten.error, true);
    sp.einspielen = datei;
    $("#sp-laden-titel").textContent = "Sicherung einspielen";
    $("#sp-laden-inhalt").innerHTML = `<p class="hint">Die Datei <span class="sp-datei">${esc(datei.name)}</span> ist verschlüsselt.</p>
      <label>Sicherungs-Passwort<input id="sp-eingabe" type="password" autocomplete="current-password"></label>
      <p class="mini-hinweis">Der bisherige Stand wird vorher automatisch gesichert.</p>`;
    $("#sp-laden-knoepfe").innerHTML = `<button type="button" class="secondary" data-l="zu">Abbrechen</button><button type="button" data-l="einspielen">⇪ Entschlüsseln und einspielen</button>`;
    if (!$("#sp-laden").open) $("#sp-laden").showModal();
    $("#sp-eingabe").focus();
    return null;
  }
  if (!res.ok) throw new Error(daten.error || `Fehler ${res.status}`);
  return daten;
}

function eingespielt(daten) {
  const n = daten.anzahl;
  alert(`Sicherung eingespielt: ${n.rechnungen} Rechnungen, ${n.kunden} Kunden${n.angebote != null ? `, ${n.angebote} Angebote` : ""}`
    + `${n.ausgaben != null ? `, ${n.ausgaben} Ausgaben` : ""}${daten.belege ? `, ${daten.belege} Belege` : ""}.`
    + "\n\nDie App wird neu geladen.");
  location.reload();
}

$("#sp-laden").addEventListener("click", async e => {
  const b = e.target.closest("[data-l]");
  if (!b) return;
  const l = b.dataset.l;
  if (l === "zu") return $("#sp-laden").close();
  if (l === "festlegen") { $("#sp-laden").close(); return passwortDialog(); }
  if (l === "ohne") {
    $("#sp-laden").close();
    ladeHerunter("api/backup");
    toast("Sicherung wird heruntergeladen … Am besten an einem anderen Ort ablegen (Cloud, USB-Stick).");
    return nachDerSicherung();
  }
  const pw = $("#sp-eingabe").value;
  if (!pw) return toast("Bitte das Sicherungs-Passwort eingeben", true);
  b.disabled = true;
  try {
    if (l === "laden") {
      b.textContent = "Wird verschlüsselt …";
      const d = await api("sicherung/vorbereiten", { method: "POST", body: { passwort: pw } });
      $("#sp-laden").close();
      ladeHerunter(d.url);
      toast(`${d.name} wird heruntergeladen … Am besten an einem anderen Ort ablegen (Cloud, USB-Stick).`);
      nachDerSicherung();
    } else if (l === "einspielen") {
      b.textContent = "Wird eingespielt …";
      const d = await sicherungEinspielen(sp.einspielen, pw);
      if (d) { $("#sp-laden").close(); eingespielt(d); }
    }
  } catch (err) { toast(err.message, true); }
  b.disabled = false;
  if (l === "laden") b.textContent = "⇩ Verschlüsselt herunterladen";
  if (l === "einspielen") b.textContent = "⇪ Entschlüsseln und einspielen";
});
$("#sp-laden").addEventListener("keydown", e => {
  if (e.key === "Enter" && e.target.id === "sp-eingabe") { e.preventDefault(); $("#sp-laden [data-l=laden], #sp-laden [data-l=einspielen]")?.click(); }
});

// ---------- Tageskopie in einen Ordner (Desktop) ----------

$("#kopie-waehlen").addEventListener("click", async () => {
  if (!appFenster() || !window.pywebview.api.ordner_waehlen) return toast("Bitte den Pfad zum Ordner eintragen", true);
  const pfad = await window.pywebview.api.ordner_waehlen($("#kopie-ordner").value);
  if (pfad) { $("#kopie-ordner").value = pfad; toast("Ordner gewählt – bitte Einstellungen speichern"); }
});
$("#kopie-jetzt").addEventListener("click", async e => {
  e.target.disabled = true;
  try {
    const d = await api("sicherung/kopie", { method: "POST" });
    toast(`Kopiert: ${d.datei}`);
  } catch (err) { toast(err.message, true); }
  e.target.disabled = false;
  sicherungStatusLaden();
});
