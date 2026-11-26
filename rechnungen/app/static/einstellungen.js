/* DJ Office Studio – seit 1.16: Einstellungen nach Themen (links), Belege aus dem Postfach, Handbuch in der App. */
"use strict";

// ======================= Einstellungen: Themen links =======================

const EINST_SVG = d => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${d}</svg>`;
const EINST_THEMEN = [
  ["absender", "Absender & Bank", `<circle cx="12" cy="8" r="3.5"/><path d="M5 20c1.2-3.6 4-5.5 7-5.5s5.8 1.9 7 5.5"/>`],
  ["belege-re", "Rechnungen & Angebote", `<path d="M6 3h9l4 4v14H6z"/><path d="M14 3v5h5M9 13h7M9 17h5"/>`],
  ["mail", "E-Mail", `<rect x="3" y="5" width="18" height="14" rx="2"/><path d="m3.5 6.5 8.5 6.5 8.5-6.5"/>`],
  ["belege", "Belege & Ablage", `<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>`],
  ["fahrten", "Fahrten", `<path d="M5 16h14l-1.5-5.5A2 2 0 0 0 15.6 9H8.4a2 2 0 0 0-1.9 1.5z"/><circle cx="8" cy="17.5" r="1.5"/><circle cx="16" cy="17.5" r="1.5"/>`],
  ["sicherung", "Datensicherung", `<path d="M12 3 5 6v5c0 4.5 3 8 7 10 4-2 7-5.5 7-10V6z"/><path d="m9 12 2 2 4-4"/>`],
  ["app", "Über die App", `<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/>`],
];
(() => {
  const form = $("#einstellungen"), nav = $(".eins-nav", form), inhalt = $(".eins-inhalt", form);
  nav.innerHTML = EINST_THEMEN.map(([id, name, d]) => `<button type="button" data-thema="${id}"><span class="sym">${EINST_SVG(d)}</span>${name}</button>`).join("");
  for (const [id, name] of EINST_THEMEN) {
    const g = document.createElement("div");
    g.className = "eins-gruppe";
    g.dataset.gruppe = id;
    g.innerHTML = `<h2 class="eins-titel">${name}</h2>`;
    g.append(...$$(`[data-thema="${id}"]`, form).filter(x => !x.closest(".eins-nav")));
    inhalt.append(g);
  }
  $$(":scope > .grid2", form).forEach(g => { if (!g.children.length) g.remove(); });   // leere Hüllen der alten Anordnung
  $(":scope > .actions", form).classList.add("eins-aktionen");
  nav.addEventListener("click", e => {
    const b = e.target.closest("[data-thema]");
    if (b) { einstellungenThema(b.dataset.thema); window.scrollTo(0, 0); }
  });
  einstellungenThema(sessionStorage.getItem("djos-einst-thema") || "absender");
})();

function einstellungenThema(id) {
  if (!EINST_THEMEN.some(t => t[0] === id)) id = "absender";
  $$(".eins-nav button").forEach(b => b.classList.toggle("aktiv", b.dataset.thema === id));
  $$(".eins-gruppe").forEach(g => g.classList.toggle("aktiv", g.dataset.gruppe === id));
  sessionStorage.setItem("djos-einst-thema", id);
}

/* Fehlende Angaben: roter Punkt am Thema; Aufruf nach dem Laden der Einstellungen. */
function einstellungenMarkieren() {
  const b = $(".eins-nav [data-thema=absender]");
  b?.querySelector(".punkt")?.remove();
  if (state.absender && !state.absender.vollstaendig) b?.insertAdjacentHTML("beforeend", `<span class="punkt" title="Angaben für Rechnungen fehlen"></span>`);
}

// ======================= Belege aus dem Postfach =======================

const pf = { regeln: [], treffer: null };

async function postfachLaden() {
  let d;
  try { d = await api("postfach"); } catch (e) { return; }
  pf.regeln = d.regeln.length ? d.regeln : [];
  pf.treffer = null;
  $("#pf-server").textContent = d.server || "– (erst den E-Mail-Versand einrichten)";
  $("#pf-holen").classList.toggle("hidden", !d.an);
  postfachZeigen();
  postfachStand(d.stand);
}

function postfachStand(st) {
  $("#pf-status").textContent = !st ? "Noch nicht abgeholt."
    : `Zuletzt abgefragt am ${fmtDate(st.am.slice(0, 10))} um ${st.am.slice(11, 16)} Uhr – ${st.neu} neu${st.doppelt ? `, ${st.doppelt} schon vorhanden` : ""}`
      + (st.fehler?.length ? ` · ⚠ ${st.fehler.join(" · ")}` : "");
}

function postfachZeigen() {
  $("#pf-teil").classList.toggle("hidden", !$("#pf-an").checked);
  $("#pf-regeln-feld").value = JSON.stringify(pf.regeln);
  $("#pf-regeln").innerHTML = (pf.regeln.length ? `<div class="pf-kopf"><span></span><span>Ordner</span><span>Absender enthält <span class="opt">(optional)</span></span>
    <span>Betreff enthält <span class="opt">(optional)</span></span><span></span></div>` : `<p class="hint">Noch keine Regel – mit „＋ Regel“ den ersten Ordner eintragen.</p>`)
    + pf.regeln.map((r, i) => {
      const t = pf.treffer?.[i];
      return `<div class="pf-regel${r.an ? "" : " aus"}" data-i="${i}">
      <input type="checkbox" data-f="an"${r.an ? " checked" : ""} title="Regel an/aus" aria-label="Regel an">
      <input data-f="ordner" list="pf-ordnerliste" value="${esc(r.ordner)}" placeholder="z. B. Geschäftlich/Belege" aria-label="Ordner" maxlength="200">
      <input data-f="von" value="${esc(r.von)}" placeholder="z. B. beatport.com" aria-label="Absender enthält" maxlength="200">
      <input data-f="betreff" value="${esc(r.betreff)}" placeholder="z. B. Rechnung" aria-label="Betreff enthält" maxlength="200">
      <button type="button" class="icon" data-weg="${i}" title="Regel löschen" aria-label="Regel löschen">✕</button>
      ${t ? `<p class="treffer${t.gefunden ? "" : " fehlt"}">${t.gefunden ? `✓ Ordner gefunden · ${t.passend} passende Mail${t.passend === 1 ? "" : "s"} seit ${fmtDate($("#pf-ab").value) || "30 Tagen"}`
        : "⚠ Diesen Ordner gibt es im Postfach nicht – Schreibweise prüfen"}</p>` : ""}</div>`;
    }).join("");
}

$("#pf-karte").addEventListener("change", e => {
  if (e.target.id === "pf-an") return postfachZeigen();
  const z = e.target.closest(".pf-regel");
  if (z && e.target.dataset.f === "an") { pf.regeln[+z.dataset.i].an = e.target.checked; postfachZeigen(); }
});
$("#pf-karte").addEventListener("input", e => {
  const z = e.target.closest(".pf-regel");
  if (z && e.target.dataset.f && e.target.dataset.f !== "an") {
    pf.regeln[+z.dataset.i][e.target.dataset.f] = e.target.value;
    pf.treffer = null;
    $("#pf-regeln-feld").value = JSON.stringify(pf.regeln);
  }
});
$("#pf-karte").addEventListener("click", async e => {
  const b = e.target.closest("button");
  if (!b) return;
  if (b.id === "pf-neu") {
    pf.regeln.push({ an: true, ordner: "", von: "", betreff: "" });
    pf.treffer = null; postfachZeigen();
    return $$("#pf-regeln [data-f=ordner]").at(-1).focus();
  }
  if (b.dataset.weg !== undefined) { pf.regeln.splice(+b.dataset.weg, 1); pf.treffer = null; return postfachZeigen(); }
  if (!["pf-laden", "pf-pruefen", "pf-jetzt"].includes(b.id)) return;
  b.disabled = true;
  try {
    if (b.id === "pf-laden") {
      const d = await api("postfach/ordner", { method: "POST" });
      $("#pf-ordnerliste").innerHTML = d.ordner.map(o => `<option value="${esc(o)}">`).join("");
      toast(`${d.ordner.length} Ordner geladen – beim Eintippen werden sie vorgeschlagen`);
    } else {
      await einstellungenSpeichernStill();
      if (b.id === "pf-pruefen") {
        pf.treffer = (await api("postfach/pruefen", { method: "POST" })).regeln;
        postfachZeigen();
      } else await postfachAbholen();
    }
  } catch (err) { toast(err.message, true); }
  b.disabled = false;
});

/* Regeln vor „Prüfen“/„Abholen“ speichern, damit der Server dieselben Regeln nutzt wie angezeigt. */
async function einstellungenSpeichernStill() {
  await api("einstellungen", { method: "PUT", body: { postfach_an: $("#pf-an").checked, postfach_regeln: JSON.stringify(pf.regeln),
    postfach_ab: $("#pf-ab").value, imap_server: $("#pf-imap").value, imap_port: $("#einstellungen [name=imap_port]").value || 993 } });
}

async function postfachAbholen() {
  toast("Postfach wird abgefragt …");
  const st = await api("postfach/abholen", { method: "POST" });
  postfachStand(st);
  toast(st.fehler.length && !st.neu ? `Postfach: ${st.fehler[0]}`
    : st.neu ? `${st.neu} neue${st.neu === 1 ? "r" : ""} Beleg${st.neu === 1 ? "" : "e"} aus dem Postfach – bitte prüfen` : "Keine neuen Rechnungsmails", !!st.fehler.length && !st.neu);
  if ($("#tab-ausgaben").classList.contains("active") && typeof ladeAusgaben === "function") ladeAusgaben();
}
$("#pf-holen").addEventListener("click", async e => {
  e.target.disabled = true;
  try { await postfachAbholen(); } catch (err) { toast(err.message, true); }
  e.target.disabled = false;
});

// ======================= Handbuch =======================

let hbGeladen = false;
async function handbuch(ziel) {
  $("#handbuch").showModal();
  if (!hbGeladen) {
    try {
      const d = await api("handbuch");
      $("#hb-text").innerHTML = d.html;   // eigene README der App, von der App selbst erzeugt
    } catch (e) { $("#hb-text").textContent = e.message; return; }
    $$("#hb-text a[href^='http']").forEach(a => { a.target = "_blank"; a.rel = "noopener"; });
    $("#hb-nav").innerHTML = $$("#hb-text h2[id], #hb-text h3[id]")
      .map(h => `<a href="#${esc(h.id)}" class="${h.tagName.toLowerCase()}">${esc(h.textContent)}</a>`).join("");
    hbGeladen = true;
  }
  if (ziel) hbSpringe(ziel);
}
function hbSpringe(id) {
  const el = $("#hb-text").querySelector(`#${CSS.escape(id)}`);
  if (el) $("#hb-text").scrollTo({ top: el.offsetTop - 8 });
  $$("#hb-nav a").forEach(a => a.classList.toggle("aktiv", a.getAttribute("href") === `#${id}`));
}
$("#handbuch-oeffnen").addEventListener("click", () => handbuch());
$("#handbuch").addEventListener("click", e => {
  if (e.target.closest("[data-hb=zu]")) return $("#handbuch").close();
  const a = e.target.closest("a[href^='#']");
  if (a) { e.preventDefault(); hbSpringe(decodeURIComponent(a.getAttribute("href").slice(1))); }
});
$("#hb-text").addEventListener("scroll", () => {
  const top = $("#hb-text").scrollTop + 20;
  const akt = $$("#hb-text h2[id], #hb-text h3[id]").filter(h => h.offsetTop <= top).at(-1);
  if (akt) $$("#hb-nav a").forEach(a => a.classList.toggle("aktiv", a.getAttribute("href") === `#${akt.id}`));
});
function hbMarkierungenWeg() {
  for (const m of $$("#hb-text mark")) m.replaceWith(document.createTextNode(m.textContent));
  $("#hb-text").normalize();
}
let hbTimer;
$("#hb-suche").addEventListener("input", e => {
  clearTimeout(hbTimer);
  hbTimer = setTimeout(() => {
    const q = e.target.value.trim().toLowerCase();
    hbMarkierungenWeg();
    if (q.length < 3) { $$("#hb-nav a").forEach(a => a.classList.remove("weg")); return; }
    const abschnitte = $$("#hb-text h2[id], #hb-text h3[id]"), treffer = new Set();
    abschnitte.forEach(h => {
      let el = h.nextElementSibling, text = h.textContent;
      while (el && !abschnitte.includes(el)) { text += " " + el.textContent; el = el.nextElementSibling; }
      if (text.toLowerCase().includes(q)) treffer.add(h.id);
    });
    $$("#hb-nav a").forEach(a => a.classList.toggle("weg", !treffer.has(decodeURIComponent(a.getAttribute("href").slice(1)))));
    const knoten = [], lauf = document.createTreeWalker($("#hb-text"), NodeFilter.SHOW_TEXT);
    let n;
    while ((n = lauf.nextNode()) && knoten.length < 200) if (n.textContent.toLowerCase().includes(q)) knoten.push(n);
    let erst = null;
    for (const k of knoten) {
      const i = k.textContent.toLowerCase().indexOf(q), r = document.createRange();
      r.setStart(k, i); r.setEnd(k, i + q.length);
      const m = document.createElement("mark");
      r.surroundContents(m);
      erst = erst || m;
    }
    if (erst) $("#hb-text").scrollTo({ top: erst.offsetTop - 80 });
  }, 250);
});

postfachLaden();   // Knopf „Aus dem Postfach“ bei den Ausgaben gleich richtig zeigen
