/* Datumsfelder: Eingabe als Text im deutschen Format (TT.MM.JJJJ) statt des Datumsfelds des Browsers.
 *
 * Grund: In Safari bzw. der Desktop-App am Mac (WebKit) lässt sich das Jahr im Datumsfeld nicht zuverlässig
 * eintippen („2019“ wird zu „0019“ o. Ä.). Jedes <input type="date"> wird deshalb zu einem Textfeld mit
 * Kalender-Knopf. Für den übrigen Code ändert sich nichts: .value liest und schreibt weiterhin JJJJ-MM-TT.
 *
 * Erlaubte Eingaben: 7.10.2019 · 07.10.19 · 07102019 · 071019 · 7.10. (aktuelles Jahr) · 2019-10-07
 */
(function () {
  const nativ = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value");
  const zwei = n => String(n).padStart(2, "0");

  function gueltig(j, m, t) {
    const d = new Date(j, m - 1, t);
    return j >= 1900 && j <= 2199 && d.getFullYear() === j && d.getMonth() === m - 1 && d.getDate() === t;
  }

  function jahr4(j) {   // zweistellig → 19xx/20xx (bis zum nächsten Jahr 20xx)
    if (j >= 100) return j;
    const grenze = (new Date().getFullYear() % 100) + 1;
    return j <= grenze ? 2000 + j : 1900 + j;
  }

  // Text → „JJJJ-MM-TT“, "" (leer) oder null (nicht lesbar)
  function zuIso(text) {
    const t = (text || "").trim();
    if (!t) return "";
    let m = t.match(/^(\d{4})-(\d{1,2})-(\d{1,2})$/);
    let j, mo, ta;
    if (m) [j, mo, ta] = [+m[1], +m[2], +m[3]];
    else if ((m = t.match(/^(\d{1,2})\D+(\d{1,2})(?:\D+(\d{2}|\d{4}))?\D*$/))) {
      [ta, mo] = [+m[1], +m[2]];
      j = m[3] ? jahr4(+m[3]) : new Date().getFullYear();
    } else if ((m = t.match(/^(\d{2})(\d{2})(\d{2}|\d{4})$/))) {
      [ta, mo, j] = [+m[1], +m[2], jahr4(+m[3])];
    } else return null;
    return gueltig(j, mo, ta) ? `${j}-${zwei(mo)}-${zwei(ta)}` : null;
  }

  function zuText(iso) {
    const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso || "");
    return m ? `${m[3]}.${m[2]}.${m[1]}` : (iso || "");
  }

  function pruefen(el) {
    const roh = nativ.get.call(el);
    el.setCustomValidity(zuIso(roh) === null ? "Bitte ein gültiges Datum eingeben, z. B. 07.10.2019" : "");
  }

  function melden(el) {
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
  }

  function umbauen(el) {
    if (el.dataset.datum) return;
    el.dataset.datum = "1";
    const iso = nativ.get.call(el);               // vorhandenen Wert (JJJJ-MM-TT) mitnehmen
    el.type = "text";
    el.inputMode = "numeric";
    el.autocomplete = "off";
    if (!el.placeholder) el.placeholder = "TT.MM.JJJJ";
    el.classList.add("datum");
    Object.defineProperty(el, "value", {
      configurable: true,
      get() {
        const roh = nativ.get.call(this);
        const w = zuIso(roh);
        return w === null ? roh.trim() : w;        // Unlesbares unverändert weitergeben – der Server meldet den Fehler
      },
      set(v) {
        nativ.set.call(this, zuText(v == null ? "" : String(v)));
        pruefen(this);
      },
    });
    nativ.set.call(el, zuText(iso));
    el.defaultValue = zuText(el.defaultValue);
    el.addEventListener("input", () => pruefen(el));
    el.addEventListener("blur", () => {           // beim Verlassen schön formatieren
      const w = zuIso(nativ.get.call(el));
      if (w) nativ.set.call(el, zuText(w));
      pruefen(el);
    });

    // Kalender-Knopf: öffnet den Kalender des Browsers über ein unsichtbares Datumsfeld
    const huelle = document.createElement("span");
    huelle.className = "datum-feld";
    el.replaceWith(huelle);
    huelle.append(el);
    const knopf = document.createElement("button");
    knopf.type = "button";
    knopf.className = "datum-kalender";
    knopf.tabIndex = -1;
    knopf.title = "Kalender";
    knopf.setAttribute("aria-label", "Kalender öffnen");
    knopf.innerHTML = '<svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true"><rect x="3.5" y="5" width="17" height="15" rx="2.5" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M3.5 10h17M8 3v4M16 3v4" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>';
    const versteckt = document.createElement("input");
    versteckt.type = "date";
    versteckt.tabIndex = -1;
    versteckt.className = "datum-versteckt";
    versteckt.setAttribute("aria-hidden", "true");
    huelle.append(knopf, versteckt);
    knopf.addEventListener("click", () => {
      if (el.disabled || el.readOnly) return;
      nativ.set.call(versteckt, el.value && /^\d{4}-/.test(el.value) ? el.value : "");
      try { versteckt.showPicker(); } catch (_) { versteckt.focus(); versteckt.click(); }
    });
    versteckt.addEventListener("change", () => {
      if (!versteckt.value) return;
      el.value = versteckt.value;
      melden(el);
    });
  }

  function alleUmbauen(wurzel) {
    if (wurzel.matches && wurzel.matches('input[type="date"]:not(.datum-versteckt)')) umbauen(wurzel);
    wurzel.querySelectorAll && wurzel.querySelectorAll('input[type="date"]:not(.datum-versteckt)').forEach(umbauen);
  }

  window.datumZuIso = zuIso;   // für Tests
  function start() {
    alleUmbauen(document);
    new MutationObserver(liste => liste.forEach(m => m.addedNodes.forEach(n => n.nodeType === 1 && alleUmbauen(n))))
      .observe(document.body, { childList: true, subtree: true });
  }
  // wird vor app.js geladen (Ende von <body>) → sofort umbauen, damit alle Zugriffe schon über .value laufen
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start); else start();
})();
