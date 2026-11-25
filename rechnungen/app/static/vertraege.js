/* Dokumente → Booking-Verträge (seit 1.13): Liste, Vertrag (zu einem Angebot oder ohne), Vorlage, eigener Vertrag, Anlagen.
   Der Vertragstext entsteht auf dem Server (Vorschau = PDF); hier wird nur angezeigt und gespeichert. */

const VT_STATUS = { entwurf: "Entwurf", verschickt: "verschickt", unterschrieben: "unterschrieben" };
const VT_WEG = { datei: "unterschrieben zurück", mail: "per Mail bestätigt", vorort: "vor Ort unterschrieben" };
const vtState = { liste: [], aktuell: null, weitereOffen: false, vorlage: [], kunden: [], hochgeladen: null, speichern: null };

function vertraegeTab(name) {
  if (name === "vertraege") ladeVertraege();
  if (name === "vertragsvorlage") ladeVorlage();
  // „Dokumente“ im Menü markieren, solange eine seiner Seiten offen ist
  $("#menu-dokumente .menu-kopf").classList.toggle("active", name === "vertraege" || name === "vertragsvorlage");
}

// ---------- Liste ----------

async function ladeVertraege() {
  try { vtState.liste = await api("vertraege"); } catch (e) { return toast(e.message, true); }
  const vt = vtState.liste;
  $("#vt-body").innerHTML = vt.map(v => `<tr data-id="${v.id}">
      <td><a href="#" class="rlink" data-vt-act="oeffnen">${esc(v.name)}</a><br><small>${esc(v.kunde.name || "– Kunde fehlt –")}${v.angebot_id ? "" : " · ohne Angebot"}</small></td>
      <td>${v.datum ? fmtDate(v.datum) : "–"}<br><small>${esc(v.anlass || "")}</small></td>
      <td class="num">${euroCent(v.gage)}</td>
      <td><span class="vt-status ${v.status}">${VT_STATUS[v.status]}</span>${v.status === "verschickt" && v.verschickt_am ? `<br><small>am ${fmtDate(v.verschickt_am)}</small>`
        : v.status === "unterschrieben" && v.unterschrieben ? `<br><small>${VT_WEG[v.unterschrieben.weg]} · ${fmtDate(v.unterschrieben.am)}${v.hat_unterschrift_datei
          ? ` · <a href="api/vertraege/${v.id}/unterschrift">📎 ${esc(v.unterschrieben.dateiname || "Datei")}</a>` : ""}</small>` : ""}</td>
      <td class="btns">${v.status === "entwurf" ? `<button type="button" class="small secondary" data-vt-act="verschickt" title="z. B. per WhatsApp oder ausgedruckt übergeben">Als verschickt vermerken</button>` : ""}
        ${v.status !== "unterschrieben" ? `<button type="button" class="small" data-vt-act="unterschrieben">✓ Unterschrieben</button>` : ""}
        <button type="button" class="small secondary" data-vt-act="oeffnen">Ansehen</button>
        ${v.status !== "unterschrieben" ? `<button type="button" class="icon del" data-vt-act="loeschen" title="Vertrag löschen" aria-label="Vertrag löschen">✕</button>` : ""}</td>
    </tr>`).join("") || `<tr><td colspan="5" class="hint">Noch keine Verträge – mit „＋ Neuer Vertrag“ den ersten anlegen.</td></tr>`;
  await kaVertraegeErgaenzen();   // Stand der Rechnungen, → Rechnung, Bar bezahlt, Kundenakte (kundenakte.js)
}

$("#vt-neu-knopf").addEventListener("click", () => neuerVertrag());
$("#vt-body").addEventListener("click", async e => {
  const b = e.target.closest("[data-vt-act]");
  if (!b) return;
  e.preventDefault();
  const v = vtState.liste.find(x => x.id === Number(b.closest("tr").dataset.id));
  try {
    switch (b.dataset.vtAct) {
      case "oeffnen": return oeffneVertrag(v.id);
      case "unterschrieben": return oeffneUnterschrift(v);
      case "verschickt":
        await api(`vertraege/${v.id}/status`, { method: "POST", body: { status: "verschickt" } });
        toast(`${v.name}: als verschickt vermerkt`);
        return ladeVertraege();
      case "loeschen":
        if (!confirm(`${v.name} wirklich löschen?`)) return;
        await api(`vertraege/${v.id}`, { method: "DELETE" });
        return ladeVertraege();
    }
  } catch (err) { toast(err.message, true); }
});

// ---------- Neuer Vertrag: Angebot wählen oder ohne Angebot ----------

async function neuerVertrag() {
  try { [state.angebote, vtState.liste] = await Promise.all([api("angebote"), api("vertraege")]); } catch (e) { return toast(e.message, true); }
  $("#vt-wahl-suche").value = "";
  zeigeWahl();
  $("#vt-wahl").showModal();
  $("#vt-wahl-suche").focus();
}
function zeigeWahl() {
  const q = $("#vt-wahl-suche").value.trim().toLowerCase();
  const mitVertrag = new Set(vtState.liste.map(v => v.angebot_id).filter(Boolean));
  const veranstaltung = a => a.positionen.map(p => p.lieferdatum).filter(Boolean).sort().at(-1) || "";
  const anlass = a => (a.positionen[0]?.beschreibung || "").replace(/^DJ – (Tätigkeit )?/, "").replace(/\s*–\s*\d{1,2}:\d{2} Uhr bis.*$/, "");
  const liste = state.angebote.filter(a => a.status !== "abgelehnt" && !mitVertrag.has(a.id))
    .filter(a => !q || [a.nummer, a.kunde.name, anlass(a)].join(" ").toLowerCase().includes(q))
    .sort((x, y) => veranstaltung(x).localeCompare(veranstaltung(y)));
  $("#vt-wahl-liste").innerHTML = liste.map(a => `<button type="button" data-wahl-id="${a.id}"><span><b>${esc(a.kunde.name)}</b>
      <small>Angebot ${esc(a.nummer)} · ${esc(anlass(a))} · ${veranstaltung(a) ? fmtDate(veranstaltung(a)) : "ohne Termin"} · ${esc(a.status)}</small></span>
      <span>${euroCent(a.gesamt)}</span></button>`).join("")
    || `<p class="hint">Kein Angebot ohne Vertrag${q ? " passt zur Suche" : ""}.</p>`;
}
$("#vt-wahl-suche").addEventListener("input", zeigeWahl);
$("#vt-wahl").addEventListener("click", async e => {
  if (e.target.closest("[data-wahl=zu]")) return $("#vt-wahl").close();
  const frei = e.target.closest("[data-wahl=frei]"), b = e.target.closest("[data-wahl-id]");
  if (!frei && !b) return;
  $("#vt-wahl").close();
  try {
    const j = await api("vertraege", { method: "POST", body: frei ? {} : { angebot_id: Number(b.dataset.wahlId) } });
    await zeigeVertragDialog(j);
    if (frei) $("#vf-name").focus();
  } catch (err) { toast(err.message, true); }
});

// ---------- Vertrag ----------

async function oeffneVertrag(id) {
  try { await zeigeVertragDialog(await api(`vertraege/${id}`)); } catch (e) { toast(e.message, true); }
}

async function zeigeVertragDialog({ vertrag, inhalt }) {
  vtState.aktuell = vertrag;
  vtState.weitereOffen = false;
  const [vorlage, kunden] = await Promise.all([api("vertragsvorlage"), api("kunden").catch(() => [])]);
  vtState.vorlage = vorlage.abschnitte;
  vtState.kunden = kunden;
  $("#vf-kunden").innerHTML = kunden.map(k => `<option value="${esc(k.name)}">`).join("");
  $("#vf-anlaesse").innerHTML = (state.textbausteine || []).map(t => `<option value="${esc(t.titel)}">`).join("");
  felderFuellen();
  $("#vt-termin").open = !vertrag.angebot_id;
  vorschau(inhalt);
  if (!$("#vertrag").open) $("#vertrag").showModal();
  $("#vt-einst").scrollTop = 0;
}

function felderFuellen() {
  const v = vtState.aktuell, f = v.felder, gesperrt = v.status !== "entwurf";
  kaVertragKopf(v);
  $("#vt-titel").innerHTML = `${esc(v.name)}${v.kunde.name ? ` · ${esc(v.kunde.name)}` : ""} <span class="vt-status ${v.status}">${VT_STATUS[v.status]}</span>`;
  $("#vt-termin-hinweis").textContent = v.angebot_id ? `aus Angebot ${v.angebot_nummer}` : "";
  for (const [id, wert] of [["vf-name", v.kunde.name], ["vf-strasse", v.kunde.strasse], ["vf-plz", v.kunde.plz], ["vf-ort", v.kunde.ort],
    ["vf-anlass", v.anlass], ["vf-datum", v.datum], ["vf-von", v.von], ["vf-bis", v.bis], ["vf-gage", v.gage || ""],
    ["vt-aufbau", f.aufbau], ["vt-kontakt", f.kontakt], ["vt-zahlung", f.zahlung], ["vt-anz", f.anzahlung]]) {
    if (document.activeElement?.id !== id) $("#" + id).value = wert ?? "";
  }
  $("#vt-anz-label").classList.toggle("hidden", f.zahlung === "ganz");
  const an = new Set(v.abschnitte);
  const extra = x => x.id === "verpflegung" ? `<input id="vt-verpflegung" class="vt-extra" maxlength="200" placeholder="z. B. für 2 Personen" aria-label="Verpflegung – Zusatz">`
    : x.id === "gema" ? `<select id="vt-gema" class="vt-extra" aria-label="GEMA-Anmeldung"><option value="veranstalter">meldet der Veranstalter an</option>
        <option value="dj">meldet der DJ an (in der Gage)</option></select>` : "";
  const zeile = x => `<label class="vt-ab-zeile"><input type="checkbox" data-abschnitt="${esc(x.id)}"${an.has(x.id) ? " checked" : ""}> ${esc(x.titel)}</label>`;
  const ein = vtState.vorlage.filter(x => an.has(x.id)), aus = vtState.vorlage.filter(x => !an.has(x.id));
  $("#vt-schalter").innerHTML = (ein.length ? ein.map(x => `<div class="vt-ab">${zeile(x)}${extra(x)}</div>`).join("") : `<p class="hint">Keine – unten Bausteine zuschalten.</p>`)
    + (aus.length ? `<details class="vt-weitere"${vtState.weitereOffen ? " open" : ""}><summary>Weitere Bausteine (${aus.length})</summary>
        ${aus.map(x => `<div class="vt-ab">${zeile(x)}</div>`).join("")}</details>` : "");
  if ($("#vt-verpflegung")) $("#vt-verpflegung").value = f.verpflegung || "";
  if ($("#vt-gema")) $("#vt-gema").value = f.gema || "veranstalter";
  $$("#vt-einst input, #vt-einst select").forEach(el => { el.disabled = gesperrt; });
  $("#vt-gesperrt").classList.toggle("hidden", !gesperrt);
  $("#vt-gesperrt").innerHTML = v.status === "verschickt"
    ? `Verschickt am ${fmtDate(v.verschickt_am)} – der Text steht fest. <button type="button" class="small secondary" data-vt="bearbeiten">Wieder bearbeiten</button>`
    : v.status === "unterschrieben" ? `Unterschrieben am ${fmtDate(v.unterschrieben?.am)} (${{ datei: "als Datei zurückgekommen", mail: "per Mail bestätigt", vorort: "vor Ort" }[v.unterschrieben?.weg] || ""})${v.hat_unterschrift_datei
      ? ` · <a href="api/vertraege/${v.id}/unterschrift">📎 ${esc(v.unterschrieben.dateiname || "Datei")}</a>` : ""} – nur noch zum Ansehen.` : "";
  $("#vertrag [data-vt=senden]").disabled = v.status === "unterschrieben";
}

/* Vertragstext aus der Server-Struktur – nur **fett** im Abschnitt „Gage und Zahlung“, alles andere als reiner Text */
function vorschau(inhalt) {
  const absatz = (t, fett) => t.split("\n\n").map(p => `<p>${fett ? esc(p).replace(/\*\*(.+?)\*\*/g, "<b>$1</b>") : esc(p)}</p>`).join("");
  $("#vt-papier").innerHTML = `<div class="vt-kopf"><div>${esc(inhalt.kopf_links)}</div><div>${esc(inhalt.kopf_rechts)}</div></div>
    <h1>${esc(inhalt.titel)}</h1>
    ${inhalt.abschnitte.map(a => `<h2>${esc(a.titel)}</h2>${a.text ? absatz(a.text, a.fett) : ""}${a.tabelle ? `<table>${a.tabelle.map(([l, r]) =>
      `<tr><td>${esc(l)}</td><td>${esc(r).replace(/\n/g, "<br>")}</td></tr>`).join("")}</table>` : ""}`).join("")}
    ${inhalt.anlagen.length ? `<p class="vt-fuss">Anlage${inhalt.anlagen.length === 1 ? "" : "n"}: ${inhalt.anlagen.map(esc).join(", ")} (Bestandteil dieses Vertrags)</p>` : ""}
    <div class="vt-unterschrift"><div>${esc(inhalt.unterschrift_links)}</div><div>${esc(inhalt.unterschrift_rechts)}</div></div>
    <div class="vt-fuss">${esc(inhalt.fuss)}</div>`;
}

/* Änderungen sammeln und kurz danach speichern – die Vorschau kommt mit der Antwort */
function vtAendern(teil) {
  const v = vtState.aktuell;
  if (!v || v.status !== "entwurf") return;
  vtState.offen = { ...(vtState.offen || {}), ...teil, felder: { ...(vtState.offen?.felder || {}), ...(teil.felder || {}) } };
  clearTimeout(vtState.speichern);
  vtState.speichern = setTimeout(vtSpeichern, 300);
}
async function vtSpeichern() {
  const daten = vtState.offen;
  vtState.offen = null;
  if (!daten) return;
  try {
    const j = await api(`vertraege/${vtState.aktuell.id}`, { method: "PUT", body: daten });
    vtState.aktuell = j.vertrag;
    felderFuellen();
    vorschau(j.inhalt);
  } catch (e) { toast(e.message, true); }
}
const kundeFeld = { "vf-name": "name", "vf-strasse": "strasse", "vf-plz": "plz", "vf-ort": "ort" };
$("#vertrag").addEventListener("input", e => {
  const id = e.target.id, v = vtState.aktuell;
  if (kundeFeld[id]) {
    const kunde = { ...v.kunde, [kundeFeld[id]]: e.target.value };
    const k = id === "vf-name" && vtState.kunden.find(x => x.name.trim().toLowerCase() === e.target.value.trim().toLowerCase());
    if (k) for (const x of ["strasse", "plz", "ort"]) { kunde[x] = k[x] || ""; $("#vf-" + x).value = k[x] || ""; }   // bekannter Kunde
    v.kunde = kunde;
    return vtAendern({ kunde });
  }
  const einfach = { "vf-anlass": "anlass", "vf-von": "von", "vf-bis": "bis", "vf-gage": "gage" }[id];
  if (einfach) return vtAendern({ [einfach]: e.target.value });
  const feld = { "vt-aufbau": "aufbau", "vt-kontakt": "kontakt", "vt-anz": "anzahlung", "vt-verpflegung": "verpflegung" }[id];
  if (feld) vtAendern({ felder: { [feld]: e.target.value } });
});
$("#vertrag").addEventListener("change", e => {
  const id = e.target.id;
  if (id === "vt-zahlung") { $("#vt-anz-label").classList.toggle("hidden", e.target.value === "ganz"); return vtAendern({ felder: { zahlung: e.target.value } }); }
  if (id === "vt-gema") return vtAendern({ felder: { gema: e.target.value } });
  if (id === "vf-datum") return vtAendern({ datum: e.target.value });          // Datumsfeld meldet erst beim Verlassen
  const ab = e.target.dataset.abschnitt;
  if (ab) {
    const an = new Set(vtState.aktuell.abschnitte);
    e.target.checked ? an.add(ab) : an.delete(ab);
    vtState.aktuell.abschnitte = vtState.vorlage.map(x => x.id).filter(x => an.has(x));
    felderFuellen();                                                            // eingeschaltete rutschen nach oben
    vtAendern({ abschnitte: vtState.aktuell.abschnitte });
  }
});
$("#vertrag").addEventListener("toggle", e => { if (e.target.matches?.(".vt-weitere")) vtState.weitereOffen = e.target.open; }, true);
$("#vertrag").addEventListener("click", async e => {
  const b = e.target.closest("[data-vt]");
  if (!b) return;
  const v = vtState.aktuell;
  try {
    if (vtState.offen) { clearTimeout(vtState.speichern); await vtSpeichern(); }
    switch (b.dataset.vt) {
      case "zu":
        $("#vertrag").close();
        if (!v.angebot_id && !v.kunde.name && !v.datum && !v.gage && v.status === "entwurf") {   // leer angelegt → nicht stehen lassen
          await api(`vertraege/${v.id}`, { method: "DELETE" }).catch(() => {});
        }
        if ($("#tab-vertraege").classList.contains("active")) ladeVertraege();
        return;
      case "pdf": return zeigePdf(`api/vertraege/${v.id}/pdf`);
      case "senden": return oeffneVersand("vertrag", vtState.aktuell);
      case "bearbeiten": {
        const j = await api(`vertraege/${v.id}/status`, { method: "POST", body: { status: "entwurf" } });
        return zeigeVertragDialog(j);
      }
    }
  } catch (err) { toast(err.message, true); }
});

/* nach dem Versand (app.js): Status neu laden */
async function vertragVerschickt(id) {
  if ($("#vertrag").open) await oeffneVertrag(id);
  if ($("#tab-vertraege").classList.contains("active")) await ladeVertraege();
}

// ---------- Unterschrift vermerken ----------

function oeffneUnterschrift(v) {
  vtState.unterschrift = v;
  $("#vtu-titel").textContent = `${v.name} unterschrieben`;
  $("#vtu-am").value = isoLokal(new Date());
  $("#vtu-notiz").value = "";
  $("#vtu-datei").value = "";
  $("#vt-unterschrift [value=datei]").checked = true;
  const angebot = v.angebot_id && (state.angebote || []).find(a => a.id === v.angebot_id);
  $("#vtu-annehmen-label").classList.toggle("hidden", !v.angebot_id || angebot?.status === "angenommen");
  $("#vtu-annehmen").checked = !!v.angebot_id;
  $("#vt-unterschrift").showModal();
}
$("#vt-unterschrift").addEventListener("click", e => { if (e.target.closest("[data-vtu=zu]")) $("#vt-unterschrift").close(); });
$("#vtu-form").addEventListener("submit", async e => {
  e.preventDefault();
  const v = vtState.unterschrift, weg = $("#vt-unterschrift [name=vtu-weg]:checked").value, datei = $("#vtu-datei").files[0];
  if (weg === "datei" && !datei) return toast("Bitte die unterschriebene Datei auswählen – oder einen anderen Weg wählen", true);
  const fd = new FormData();
  fd.append("weg", weg);
  fd.append("am", $("#vtu-am").value);
  fd.append("notiz", $("#vtu-notiz").value);
  if (!$("#vtu-annehmen-label").classList.contains("hidden") && $("#vtu-annehmen").checked) fd.append("angebot_annehmen", "1");
  if (weg === "datei") fd.append("datei", datei);
  try {
    const r = await fetch(`api/vertraege/${v.id}/unterschrieben`, { method: "POST", body: fd, headers: SCHUTZ });
    const j = await r.json();
    if (!r.ok) throw new Error(j.error || `Fehler ${r.status}`);
    $("#vt-unterschrift").close();
    toast(`${v.name} ist als unterschrieben vermerkt`);
    ladeVertraege();
    if ($("#tab-start").classList.contains("active")) renderStart();
  } catch (err) { toast(err.message, true); }
});

// ---------- Vorlage ----------

async function ladeVorlage() {
  try {
    const j = await api("vertragsvorlage");
    vtState.vorlage = j.abschnitte;
    vtState.anlagen = j.anlagen;
  } catch (e) { return toast(e.message, true); }
  zeigeVorlage();
}
function zeigeVorlage(offen) {
  const vl = vtState.vorlage;
  $("#vt-vorlage").innerHTML = vl.map((a, i) => `<details class="vt-vorlage-zeile"${offen === i ? " open" : ""}><summary><input type="checkbox" data-v-an="${i}"${a.an ? " checked" : ""}
      aria-label="${esc(a.titel)} standardmäßig im Vertrag">${esc(a.titel)}${a.herkunft === "eigen" ? ` <span class="art-chip">eigener Abschnitt</span>`
      : a.herkunft !== "standard" ? ` <span class="art-chip">aus ${esc(a.herkunft)}</span>` : ""}</summary>
      <input class="vt-v-titel" data-v-titel="${i}" value="${esc(a.titel)}" maxlength="120" aria-label="Überschrift">
      <textarea rows="4" data-v-text="${i}" maxlength="6000" aria-label="Text">${esc(a.text)}</textarea>
      <div class="vt-zeile-knoepfe"><button type="button" class="small secondary" data-v-hoch="${i}" title="nach oben"${i ? "" : " disabled"}>↑</button>
        <button type="button" class="small secondary" data-v-runter="${i}" title="nach unten"${i < vl.length - 1 ? "" : " disabled"}>↓</button>
        ${a.herkunft !== "standard" ? `<button type="button" class="small secondary" data-v-weg="${i}">Abschnitt entfernen</button>` : ""}</div></details>`).join("");
  $("#vt-anlagen").innerHTML = (vtState.anlagen || []).length ? `<h3 class="vt-anlagen-titel">Anlagen zu jedem Vertrag</h3>${vtState.anlagen.map(a =>
    `<div class="vt-anlage"><a href="api/vertragsvorlage/anlagen/${a.id}" target="_blank" rel="noopener">📎 ${esc(a.name)}</a>
      <button type="button" class="icon del" data-anlage-weg="${a.id}" title="Anlage entfernen" aria-label="Anlage entfernen">✕</button></div>`).join("")}` : "";
}
async function vorlageSpeichern(offen) {
  try {
    const j = await api("vertragsvorlage/abschnitte", { method: "PUT", body: { abschnitte: vtState.vorlage } });
    vtState.vorlage = j.abschnitte;
    if (offen !== undefined) zeigeVorlage(offen);
  } catch (e) { toast(e.message, true); ladeVorlage(); }
}
let vorlageTimer;
$("#vt-vorlage").addEventListener("input", e => {
  const i = e.target.dataset.vText ?? e.target.dataset.vTitel;
  if (i === undefined) return;
  vtState.vorlage[+i][e.target.dataset.vText !== undefined ? "text" : "titel"] = e.target.value;
  clearTimeout(vorlageTimer);
  vorlageTimer = setTimeout(() => vorlageSpeichern(), 600);
});
$("#vt-vorlage").addEventListener("change", e => {
  if (e.target.dataset.vAn === undefined) return;
  vtState.vorlage[+e.target.dataset.vAn].an = e.target.checked;
  vorlageSpeichern();
});
$("#vt-vorlage").addEventListener("click", e => {
  if (e.target.matches("summary input")) return e.stopPropagation();
  const hoch = e.target.closest("[data-v-hoch]"), runter = e.target.closest("[data-v-runter]"), weg = e.target.closest("[data-v-weg]");
  const vl = vtState.vorlage;
  if (hoch || runter) {
    const i = +(hoch || runter).dataset[hoch ? "vHoch" : "vRunter"], j = hoch ? i - 1 : i + 1;
    [vl[i], vl[j]] = [vl[j], vl[i]];
    zeigeVorlage(j);
    return vorlageSpeichern(j);
  }
  if (weg && confirm(`Abschnitt „${vl[+weg.dataset.vWeg].titel}“ aus der Vorlage entfernen?`)) {
    vl.splice(+weg.dataset.vWeg, 1);
    zeigeVorlage();
    vorlageSpeichern();
  }
});
$("#vt-eigen-neu").addEventListener("click", () => {
  $("#vt-eigen-form").classList.remove("hidden");
  $("#vt-eigen-neu").classList.add("hidden");
  $("#vt-ea-titel").focus();
});
$("#vt-eigen-form").addEventListener("click", async e => {
  const b = e.target.closest("[data-ea]");
  if (!b) return;
  if (b.dataset.ea === "speichern") {
    const titel = $("#vt-ea-titel").value.trim(), text = $("#vt-ea-text").value.trim();
    if (!titel || !text) return toast("Bitte Überschrift und Text eintragen", true);
    vtState.vorlage.push({ titel, text, an: $("#vt-ea-an").checked });
    await vorlageSpeichern(vtState.vorlage.length - 1);
    toast(`Abschnitt „${titel}“ angelegt`);
  }
  $("#vt-ea-titel").value = "";
  $("#vt-ea-text").value = "";
  $("#vt-ea-an").checked = true;
  $("#vt-eigen-form").classList.add("hidden");
  $("#vt-eigen-neu").classList.remove("hidden");
});

// ---------- Eigenen Vertrag hochladen / Anlage ----------

async function hochladen(pfad, datei) {
  const fd = new FormData();
  fd.append("datei", datei);
  const r = await fetch(pfad, { method: "POST", body: fd, headers: SCHUTZ });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.error || `Fehler ${r.status}`);
  return j;
}
async function eigenenVertragLesen(datei) {
  $("#vt-eigen-ergebnis").innerHTML = `<p class="hint">Lese ${esc(datei.name)} …</p>`;
  let j;
  try { j = await hochladen("api/vertragsvorlage/lesen", datei); } catch (e) { $("#vt-eigen-ergebnis").innerHTML = ""; return toast(e.message, true); }
  vtState.hochgeladen = { ...j, datei, pdf: datei.name.toLowerCase().endsWith(".pdf") };
  const t = j.abschnitte;
  $("#vt-eigen-ergebnis").innerHTML = `<div class="vt-eigen-box"><b>${esc(j.name)}</b> – ${t.length} Abschnitt${t.length === 1 ? "" : "e"} erkannt. Welche sollen in deine Vorlage?
    ${t.map((a, i) => `<label class="vt-eigen-teil"><input type="checkbox" data-teil="${i}"${a.fest ? "" : " checked"}>
      <span><b>${esc(a.titel)}</b>${a.fest ? ` <span class="art-chip">füllt die App selbst aus</span>` : ""}<small>${esc(a.text.slice(0, 160))}${a.text.length > 160 ? " …" : ""}</small></span></label>`).join("")}
    <div class="vt-eigen-wahl"><label><input type="radio" name="vt-eigen-modus" value="dazu" checked> zu meinen Abschnitten hinzufügen</label>
      <label><input type="radio" name="vt-eigen-modus" value="ersetzen"> meine bisherigen Abschnitte ausschalten</label></div>
    ${vtState.hochgeladen.pdf ? `<label class="inline"><input type="checkbox" id="vt-eigen-anlage"> PDF zusätzlich unverändert an jeden Vertrag anhängen</label>` : ""}
    <div class="actions"><button type="button" class="secondary" data-eigen="abbrechen">Abbrechen</button><button type="button" data-eigen="uebernehmen">Übernehmen</button></div></div>`;
}
$("#vt-eigen-datei").addEventListener("change", e => { if (e.target.files[0]) eigenenVertragLesen(e.target.files[0]); e.target.value = ""; });
$("#vt-eigen-drop").addEventListener("dragover", e => e.preventDefault());
$("#vt-eigen-drop").addEventListener("drop", e => { e.preventDefault(); if (e.dataTransfer.files[0]) eigenenVertragLesen(e.dataTransfer.files[0]); });
$("#vt-eigen-karte").addEventListener("click", async e => {
  const weg = e.target.closest("[data-anlage-weg]");
  if (weg) {
    try { await api(`vertragsvorlage/anlagen/${weg.dataset.anlageWeg}`, { method: "DELETE" }); } catch (err) { return toast(err.message, true); }
    return ladeVorlage();
  }
  const b = e.target.closest("[data-eigen]");
  if (!b) return;
  const h = vtState.hochgeladen;
  if (b.dataset.eigen === "abbrechen") { vtState.hochgeladen = null; $("#vt-eigen-ergebnis").innerHTML = ""; return; }
  const gewaehlt = $$("#vt-eigen-ergebnis [data-teil]:checked").map(x => h.abschnitte[+x.dataset.teil]);
  const anhang = !!$("#vt-eigen-anlage")?.checked;
  if (!gewaehlt.length && !anhang) return toast("Bitte Abschnitte auswählen oder „unverändert anhängen“ ankreuzen", true);
  try {
    if (gewaehlt.length) {
      if ($("#vt-eigen-ergebnis [name=vt-eigen-modus]:checked").value === "ersetzen") vtState.vorlage.forEach(a => { a.an = false; });
      vtState.vorlage.push(...gewaehlt.map(a => ({ titel: a.titel, text: a.text, an: true, herkunft: h.name })));
      await vorlageSpeichern();
    }
    if (anhang) await hochladen("api/vertragsvorlage/anlagen", h.datei);
  } catch (err) { return toast(err.message, true); }
  toast([gewaehlt.length ? `${gewaehlt.length} Abschnitt${gewaehlt.length === 1 ? "" : "e"} übernommen` : "", anhang ? `${h.name} geht als Anlage mit` : ""].filter(Boolean).join(" · "));
  vtState.hochgeladen = null;
  $("#vt-eigen-ergebnis").innerHTML = "";
  ladeVorlage();
});
