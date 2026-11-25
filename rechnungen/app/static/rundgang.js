/* Rundgang durch die App (seit 1.12) und Schnellsuche (Strg/⌘ + K). Läuft nach app.js und finanzen.js. */
(() => {
  // =====================================================================
  // Rundgang
  // =====================================================================
  const istHandy = () => matchMedia("(max-width: 700px)").matches;
  const SCHRITTE = [
    { titel: "Willkommen bei DJ Office Studio 👋",
      text: "In zwei Minuten zeige ich dir, wo alles ist: Rechnungen und Angebote schreiben, Belege sammeln und am Jahresende alles für den Steuerberater. Du kannst jederzeit abbrechen – der Rundgang lässt sich unter ⚙ Einstellungen wiederholen." },
    { ziel: "nav", tab: "start", titel: "Das Menü",
      text: "Hier oben erreichst du alles: Start, Rechnungen, Angebote, Finanzen und die Stammdaten (Kunden, Rechnungsposten, Zahlungsbedingungen)." },
    { ziel: "#einstellungen-btn", tab: "start", titel: "Zuerst: deine Angaben",
      text: "Unter ⚙ Einstellungen trägst du Name, Anschrift, Bankverbindung und Steuernummer ein und ob du Kleinunternehmer bist. Daraus entstehen Absender und Fußzeile jeder Rechnung. Dort richtest du auch den Mailversand und den Belege-Ordner ein." },
    { ziel: ".start-kopf", tab: "start", titel: "Die Startseite",
      text: "„Heute wichtig“ zeigt, was ansteht – überfällige Rechnungen, Angebote ohne Antwort, Belege zum Prüfen. Ein Klick führt direkt hin. Darunter die nächsten Termine, die Pinnwand und dein Jahr." },
    { ziel: "#k-name", karte: true, tab: "neu", titel: "Rechnung schreiben: Kunde",
      text: "Namen eintippen und einen Vorschlag übernehmen – oder einen neuen Kunden eingeben, er wird beim Speichern angelegt." },
    { ziel: "#positionen .pos", tab: "neu", titel: "Positionen und Preis",
      text: "Rechnungsposten wählen (z. B. Hochzeit), Uhrzeiten und Preis eintragen – der Text entsteht von selbst. Der Spickzettel darunter zeigt, was du bisher dafür genommen hast. Unter „Art der Rechnung“ geht's bei Bedarf zur Anzahlung." },
    { ziel: "#offen", tab: "liste", titel: "Rechnungen",
      text: "Oben die offenen Rechnungen mit Restzeit. Ist bezahlt, Haken setzen – dann wandert sie ins Archiv. Überfällig? Ein Klick erstellt Zahlungserinnerung oder Mahnung. Briefumschlag = per Mail senden, QR = GiroCode zum Bezahlen." },
    { ziel: "#angebote-offen", tab: "angebote", titel: "Angebote",
      text: "Angebote schreibst du im selben Editor. Sagt der Kunde zu, macht „→ Rechnung“ daraus die Rechnung. Kommt keine Antwort, erinnert die Startseite ans Nachfragen." },
    { ziel: "#menu-dokumente", tab: "angebote", titel: "Dokumente: Verträge",
      text: "Unter Dokumente schreibst du Booking-Verträge – zu einem Angebot oder ohne. Die Vorlage mit deinen Bedingungen (Verpflegung, GEMA, Ersatz-DJ …) stellst du unter „Vertragsvorlage“ ein; ein eigener Vertrag lässt sich hochladen." },
    { ziel: "#beleg-drop", tab: "ausgaben", titel: "Ausgaben und Belege",
      text: "Rechnungen, Fotos von Kassenbons oder Kauf-Mails einfach hierher ziehen – die App liest Lieferant, Datum und Betrag aus, du prüfst nur noch. Abos (Musikpool, Software) laufen über ↻ Abos." },
    { ziel: "#euer-body", karte: true, tab: "euer", titel: "EÜR und Steuerberater",
      text: "Hier entsteht die Einnahmen-Überschuss-Rechnung. Die Prüfliste zeigt, was noch fehlt; der Export packt alles für den Steuerberater in ein ZIP. Nach Jahresende kannst du das Jahr abschließen." },
    { ziel: "#suche-knopf", tab: "start", titel: "Schnell finden",
      text: "Die Lupe – oder Strg + K (am Mac ⌘ + K) – sucht in Rechnungen, Angeboten, Kunden und Belegen und springt direkt hin." },
    { ziel: "#sicherung-btn", karte: true, tab: "einstellungen", titel: "Datensicherung – und fertig!",
      text: "Lade ab und zu eine Sicherung herunter; die Startseite erinnert dich daran. Den Rundgang findest du jederzeit wieder hier in den Einstellungen unter „Rundgang starten“. Viel Spaß!" },
  ];
  let schritt = -1;
  const licht = Object.assign(document.createElement("div"), { className: "tour-licht" });
  const sperre = Object.assign(document.createElement("div"), { className: "tour-sperre" });
  const karte = Object.assign(document.createElement("div"), { className: "tour-karte", role: "dialog" });
  karte.setAttribute("aria-live", "polite");

  async function zeige(i) {
    schritt = i;
    const s = SCHRITTE[i];
    if (s.tab) {
      if (s.tab === "neu") { if (istAngebot()) await neueRechnung(); else showTab("neu"); }
      else showTab(s.tab);
      await new Promise(r => setTimeout(r, 350));
    }
    let el = s.ziel ? $(s.ziel) : null;
    if (el && s.karte) el = el.closest(".card") || el;
    if (el) {
      // unter die (feste) Kopfzeile scrollen; kleine Bereiche mittig, große oben
      const kopf = $("header")?.getBoundingClientRect().bottom || 0, r = el.getBoundingClientRect();
      const frei = innerHeight - kopf - (istHandy() ? 260 : 0);
      const ziel = r.height < frei * .5 ? kopf + (frei - r.height) / 2 : kopf + 16;
      window.scrollTo({ top: Math.max(0, scrollY + r.top - ziel), behavior: "instant" });
      await new Promise(r => setTimeout(r, 60));
    }
    karte.innerHTML = `<div class="tour-punkte">${SCHRITTE.map((_, k) => `<i class="${k <= i ? "an" : ""}"></i>`).join("")}</div>
      <h3>${esc(s.titel)}</h3><p>${esc(s.text)}</p>
      <div class="tour-fuss"><span class="tour-schritt">${i + 1} von ${SCHRITTE.length}</span>
        ${i ? `<button type="button" class="small secondary" data-tour="zurueck">Zurück</button>` : `<button type="button" class="link" data-tour="ende">Überspringen</button>`}
        <button type="button" class="small" data-tour="weiter">${i === SCHRITTE.length - 1 ? "Fertig" : "Weiter"}</button></div>
      ${i && i < SCHRITTE.length - 1 ? `<div class="tour-ende"><button type="button" class="link" data-tour="ende">Rundgang beenden</button></div>` : ""}`;
    platzieren();
    karte.querySelector("[data-tour=weiter]").focus();
  }
  function platzieren() {
    const s = SCHRITTE[schritt];
    let el = s.ziel ? $(s.ziel) : null;
    if (el && s.karte) el = el.closest(".card") || el;
    const r = el?.getBoundingClientRect();
    if (!r || !r.width) {
      licht.classList.add("ohne");
      Object.assign(karte.style, { left: `${(innerWidth - karte.offsetWidth) / 2}px`, top: `${Math.max(60, innerHeight * .3)}px` });
      return;
    }
    licht.classList.remove("ohne");
    const rand = 6, oben = Math.max(r.top - rand, 4), hoehe = Math.min(r.height + 2 * rand, innerHeight - oben - 4);
    Object.assign(licht.style, { left: `${r.left - rand}px`, top: `${oben}px`, width: `${r.width + 2 * rand}px`, height: `${hoehe}px` });
    if (istHandy()) return;
    const kw = karte.offsetWidth, kh = karte.offsetHeight;
    let top = oben + hoehe + 12, left = Math.min(Math.max(12, r.left), innerWidth - kw - 12);
    if (top + kh > innerHeight - 12) top = oben - kh - 12;                                   // passt nicht drunter → drüber
    if (top < 12) {
      if (r.right + 16 + kw < innerWidth) { left = r.right + 16; top = Math.max(12, Math.min(innerHeight - kh - 12, r.top)); }
      else if (r.left - kw - 16 > 0) { left = r.left - kw - 16; top = Math.max(12, Math.min(innerHeight - kh - 12, r.top)); }
      else { left = innerWidth - kw - 16; top = innerHeight - kh - 16; }        // kein Platz daneben: unten rechts in die Ecke
    }
    Object.assign(karte.style, { left: `${left}px`, top: `${top}px` });
  }
  function startTour() {
    schliesseMenues?.();
    document.body.append(sperre, licht, karte);
    zeige(0);
  }
  function endeTour(fertig) {
    sperre.remove(); licht.remove(); karte.remove();
    schritt = -1;
    showTab("start");
    toast(fertig ? "Rundgang beendet – unter ⚙ Einstellungen → „Rundgang starten“ kannst du ihn wiederholen."
      : "Rundgang übersprungen – du findest ihn unter ⚙ Einstellungen → „Rundgang starten“.");
  }
  karte.addEventListener("click", e => {
    const b = e.target.closest("[data-tour]"); if (!b) return;
    if (b.dataset.tour === "weiter") return schritt === SCHRITTE.length - 1 ? endeTour(true) : zeige(schritt + 1);
    if (b.dataset.tour === "zurueck") return zeige(schritt - 1);
    endeTour(false);
  });
  document.addEventListener("keydown", e => {
    if (schritt < 0) return;
    if (e.key === "Escape") { e.preventDefault(); endeTour(false); }
    if (e.key === "ArrowRight") karte.querySelector("[data-tour=weiter]").click();
    if (e.key === "ArrowLeft" && schritt > 0) zeige(schritt - 1);
  }, true);
  addEventListener("resize", () => schritt >= 0 && platzieren());
  addEventListener("scroll", () => schritt >= 0 && platzieren(), { passive: true });

  // Frage beim ersten Öffnen – nur bei einer neuen Installation, einmal (Server merkt sich die Antwort)
  const frageBeantwortet = () => {
    if (state.absender) state.absender.rundgang_anbieten = false;
    api("rundgang", { method: "POST" }).catch(() => {});
  };
  window.rundgangAnbieten = () => {
    if (state.absender?.rundgang_anbieten && !$("#hinweis-dialog").open && !$("#tour-frage").open) $("#tour-frage").showModal();
  };
  $("#hinweis-dialog").addEventListener("close", () => setTimeout(window.rundgangAnbieten, 200));
  $("#tour-frage").addEventListener("click", e => {
    const b = e.target.closest("[data-frage]"); if (!b) return;
    $("#tour-frage").close();
    frageBeantwortet();
    if (b.dataset.frage === "los") startTour();
    else toast("Alles klar – den Rundgang findest du unter ⚙ Einstellungen → „Rundgang starten“.");
  });
  $("#tour-frage").addEventListener("cancel", frageBeantwortet);   // Esc = später

  // Einstellungen: Knopf zum Wiederholen
  $("#rundgang-starten").addEventListener("click", () => { window.scrollTo(0, 0); startTour(); });

  // =====================================================================
  // Schnellsuche
  // =====================================================================
  const mac = /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent);
  $("#suche-knopf").title = `Suchen (${mac ? "⌘" : "Strg"} + K)`;

  const SEITEN = [
    ["Neue Rechnung", "neu", "＋"], ["Neues Angebot", "angebot-neu", "✎"], ["Rechnungen", "liste", "☰"], ["Angebote", "angebote", "❐"],
    ["Finanzen – Übersicht", "finanzen", "◔"], ["Ausgaben", "ausgaben", "↧"], ["Fahrten", "fahrten", "➜"], ["Anschaffungen", "anschaffungen", "▣"],
    ["EÜR & Export", "euer", "§"], ["Kunden", "kunden", "◉"], ["Rechnungsposten", "textbausteine", "♪"], ["Zahlungsbedingungen", "zahlungsbedingungen", "€"],
    ["Neuer Vertrag", "vertrag-neu", "✍"], ["Verträge", "vertraege", "✍"], ["Vertragsvorlage", "vertragsvorlage", "§"],
    ["Einstellungen", "einstellungen", "⚙"], ["Datensicherung herunterladen", "sichern", "⇩"], ["Rundgang starten", "rundgang", "?"],
  ];
  let daten = null, treffer = [], aktiv = 0;
  const norm = t => String(t ?? "").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");
  const betragTexte = v => [String(v), String(v).replace(".", ","), Math.round(v).toString(),
    Number(v).toLocaleString("de-DE", { minimumFractionDigits: 2 })];
  function markiere(text, q) {
    const t = String(text ?? ""); if (!q) return esc(t);
    const i = norm(t).indexOf(norm(q.split(/\s+/)[0]));
    return i < 0 ? esc(t) : esc(t.slice(0, i)) + "<mark>" + esc(t.slice(i, i + q.split(/\s+/)[0].length)) + "</mark>" + esc(t.slice(i + q.split(/\s+/)[0].length));
  }
  async function laden() {
    const [rechnungen, angebote, kunden, ausgaben, vertraege] = await Promise.all([api("rechnungen"), api("angebote"), api("kunden").catch(() => []),
      api("ausgaben").catch(() => []), api("vertraege").catch(() => [])]);
    daten = { rechnungen, angebote, kunden, ausgaben, vertraege };
  }
  function suchen(q) {
    const w = norm(q).split(/\s+/).filter(Boolean);
    const passt = felder => { const t = norm(felder.join(" ")); return w.every(x => t.includes(x)); };
    const g = [];
    if (!w.length) {
      g.push(["Zuletzt", daten.rechnungen.slice(0, 4).map(r => ({ art: "rechnung", r })), "rechnung"]);
      g.push(["Seiten", SEITEN.slice(0, 6).map(s => ({ art: "seite", s }))]);
      return g;
    }
    const rs = daten.rechnungen.filter(r => passt([r.nummer, r.name, r.kunde.name, r.kunde.ort, r.datum, fmtDate(r.datum), ...betragTexte(r.gesamt), ...r.positionen.map(p => p.beschreibung),
      r.rechnungsart === "anzahlung" ? "anzahlung" : r.rechnungsart === "schluss" ? "schlussrechnung" : "", r.storno_von ? "storno" : "", istOffen(r) ? "offen" : "bezahlt"])).slice(0, 6);
    const as = daten.angebote.filter(a => passt([a.nummer, a.name, a.kunde.name, a.kunde.ort, a.datum, fmtDate(a.datum), ...betragTexte(a.gesamt), ...a.positionen.map(p => p.beschreibung), a.status, "angebot"])).slice(0, 5);
    const ks = daten.kunden.filter(k => passt([k.name, k.zusatz, k.strasse, k.plz, k.ort, k.email])).slice(0, 4);
    const bs = daten.ausgaben.filter(b => b.status !== "papierkorb" && passt([b.lieferant, b.beschreibung, b.notiz, b.belegdatum, fmtDate(b.belegdatum), ...betragTexte(b.betrag || 0), b.kategorie_name || b.kategorie])).slice(0, 5);
    const vs = daten.vertraege.filter(v => passt([v.name, v.nummer, v.kunde.name, v.kunde.ort, v.anlass, v.datum, fmtDate(v.datum),
      ...betragTexte(v.gage), "vertrag", v.status])).slice(0, 4);
    const ss = SEITEN.filter(s => passt([s[0]])).slice(0, 4);
    const seiteZuerst = ss.some(x => norm(x[0]).split(/[\s–&-]+/).some(wort => wort.startsWith(w[0])));
    if (seiteZuerst) g.push(["Seiten", ss.map(s => ({ art: "seite", s }))]);
    if (rs.length) g.push(["Rechnungen", rs.map(r => ({ art: "rechnung", r }))]);
    if (as.length) g.push(["Angebote", as.map(a => ({ art: "angebot", a }))]);
    if (vs.length) g.push(["Verträge", vs.map(v => ({ art: "vertrag", v }))]);
    if (ks.length) g.push(["Kunden", ks.map(k => ({ art: "kunde", k }))]);
    if (bs.length) g.push(["Belege & Ausgaben", bs.map(b => ({ art: "beleg", b }))]);
    if (ss.length && !seiteZuerst) g.push(["Seiten", ss.map(s => ({ art: "seite", s }))]);
    return g;
  }
  function zeile(t, q) {
    if (t.art === "rechnung") { const r = t.r;
      return `<span class="sym">€</span><span class="txt"><b>${markiere(`Rechnung ${r.nummer} · ${r.kunde.name}`, q)}</b>
        <small>${fmtDate(r.datum)} · ${esc(r.positionen[0]?.beschreibung || "")}</small></span>
        <span class="rechts">${fmtEuro(r.gesamt)} · ${r.storno_von ? "Storno" : r.storniert_durch ? "storniert" : istOffen(r) ? "offen" : "bezahlt"}</span>`; }
    if (t.art === "angebot") { const a = t.a;
      return `<span class="sym">✎</span><span class="txt"><b>${markiere(`Angebot ${a.nummer} · ${a.kunde.name}`, q)}</b>
        <small>${fmtDate(a.datum)} · ${esc(a.positionen[0]?.beschreibung || "")}</small></span><span class="rechts">${fmtEuro(a.gesamt)} · ${esc(a.status)}</span>`; }
    if (t.art === "kunde") { const k = t.k; const n = daten.rechnungen.filter(r => r.kunde.name === k.name).length;
      return `<span class="sym">◉</span><span class="txt"><b>${markiere(k.name, q)}</b><small>${esc([k.strasse, [k.plz, k.ort].filter(Boolean).join(" ")].filter(Boolean).join(", "))}</small></span>
        <span class="rechts">${n} Rechnung${n === 1 ? "" : "en"}</span>`; }
    if (t.art === "vertrag") { const v = t.v;
      return `<span class="sym">✍</span><span class="txt"><b>${markiere(`${v.name} · ${v.kunde.name || "ohne Kunde"}`, q)}</b>
        <small>${v.datum ? fmtDate(v.datum) : "ohne Termin"} · ${esc(v.anlass || "")}</small></span><span class="rechts">${fmtEuro(v.gage)} · ${esc(v.status)}</span>`; }
    if (t.art === "beleg") { const b = t.b;
      return `<span class="sym">↧</span><span class="txt"><b>${markiere(b.lieferant || "Beleg", q)}</b><small>${fmtDate(b.belegdatum)} · ${esc(b.beschreibung || b.kategorie_name || "")}</small></span>
        <span class="rechts">${fmtEuro(b.betrag || 0)}${b.status === "neu" ? " · zu prüfen" : ""}</span>`; }
    return `<span class="sym">${t.s[2]}</span><span class="txt"><b>${markiere(t.s[0], q)}</b><small>Seite öffnen</small></span>`;
  }
  function zeigen() {
    const q = $("#suche-eingabe").value.trim();
    const gruppen = suchen(q);
    treffer = gruppen.flatMap(g => g[1]);
    aktiv = Math.min(aktiv, Math.max(0, treffer.length - 1));
    let n = 0;
    $("#suche-liste").innerHTML = treffer.length ? gruppen.map(([titel, liste]) => `<div class="suche-gruppe">${titel}</div>`
      + liste.map(t => `<button type="button" class="suche-treffer${n === aktiv ? " aktiv" : ""}" role="option" data-n="${n++}">${zeile(t, q)}</button>`).join("")).join("")
      : `<div class="suche-leer">Nichts gefunden für „${esc(q)}“.</div>`;
  }
  async function oeffneSuche() {
    if (schritt >= 0) return;
    $("#suche-eingabe").value = ""; aktiv = 0;
    $("#suche-liste").innerHTML = `<div class="suche-leer">Lade …</div>`;
    $("#suche").showModal(); $("#suche-eingabe").focus();
    try { await laden(); } catch (e) { return toast(e.message, true); }
    zeigen();
  }
  async function waehle(t) {
    $("#suche").close();
    if (t.art === "rechnung") return loadIntoForm(t.r);
    if (t.art === "angebot") return loadAngebotIntoForm(t.a);
    if (t.art === "kunde") return oeffneAkte(t.k.name);   // seit 1.14: Kundenakte
    if (t.art === "beleg") { showTab("ausgaben"); return setTimeout(() => oeffneBeleg(t.b.id), 300); }
    if (t.art === "vertrag") return oeffneVertrag(t.v.id);
    const ziel = t.s[1];
    if (ziel === "neu") return neueRechnung();
    if (ziel === "vertrag-neu") return neuerVertrag();
    if (ziel === "angebot-neu") return neuesAngebot();
    if (ziel === "sichern") return sicherungHerunterladen();
    if (ziel === "rundgang") return startTour();
    if (ziel === "einstellungen") return $("#einstellungen-btn").click();
    showTab(ziel);
  }
  $("#suche-knopf").addEventListener("click", oeffneSuche);
  $("#suche-eingabe").addEventListener("input", () => { aktiv = 0; zeigen(); });
  $("#suche-eingabe").addEventListener("keydown", e => {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      aktiv = (aktiv + (e.key === "ArrowDown" ? 1 : -1) + treffer.length) % Math.max(1, treffer.length);
      zeigen(); $("#suche-liste .aktiv")?.scrollIntoView({ block: "nearest" });
    }
    if (e.key === "Enter" && treffer[aktiv]) { e.preventDefault(); waehle(treffer[aktiv]); }
  });
  $("#suche-liste").addEventListener("click", e => { const b = e.target.closest("[data-n]"); if (b) waehle(treffer[Number(b.dataset.n)]); });
  $("#suche").addEventListener("click", e => { if (e.target === e.currentTarget) $("#suche").close(); });   // Klick daneben
  document.addEventListener("keydown", e => {
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); $("#suche").open ? $("#suche").close() : oeffneSuche(); }
  });
})();
