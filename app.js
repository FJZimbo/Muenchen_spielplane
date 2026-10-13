(() => {
  "use strict";

  const TZ = "Europe/Berlin";

  const STRINGS = {
    de: {
      today: "Heute",
      todayOn: "Heute ✓",
      allVenues: "Alle Orte",
      allCategories: "Alle Kategorien",
      jumpTo: "Zu Datum springen",
      noData: "Noch keine Termine geladen. Der Spielplan wird täglich automatisch aktualisiert.",
      noMatch: "Keine Termine für diese Auswahl.",
      soldOut: "Ausgebucht",
      tickets: "Tickets / Info",
      price: "Preis",
      duration: "Dauer",
      updated: "Stand",
      footer: "Daten werden von den Websites der Häuser übernommen. Titel werden nicht übersetzt. Angaben ohne Gewähr. Bitte vor dem Besuch beim Haus prüfen.",
      lang: "EN",
      locale: "de-DE",
      categories: { theatre: "Theater", opera: "Oper", concert: "Konzert", cinema: "Kino" },
      minutes: "Min.",
    },
    en: {
      today: "Today",
      todayOn: "Today ✓",
      allVenues: "All venues",
      allCategories: "All categories",
      jumpTo: "Jump to date",
      noData: "No events loaded yet. The programme is refreshed automatically every day.",
      noMatch: "No events for this selection.",
      soldOut: "Sold out",
      tickets: "Tickets / info",
      price: "Price",
      duration: "Duration",
      updated: "Updated",
      footer: "Data is taken from the venues' websites. Titles are not translated. No guarantee of completeness; please check with the venue before you go.",
      lang: "DE",
      locale: "en-GB",
      categories: { theatre: "Theatre", opera: "Opera", concert: "Concert", cinema: "Cinema" },
      minutes: "min",
    },
  };

  const CATEGORY_ICON = { theatre: "🎭", opera: "🎶", concert: "🎻", cinema: "🎬" };

  const state = {
    lang: localStorage.getItem("lang") || (navigator.language.startsWith("de") ? "de" : "en"),
    data: null,
    venues: new Set(),       // empty = all
    categories: new Set(),   // empty = all
    todayOnly: false,
  };

  const $ = (sel) => document.querySelector(sel);
  const t = () => STRINGS[state.lang];

  // Event dates are grouped by their Berlin calendar day, not the viewer's local day.
  const berlinDateKey = (date) =>
    new Intl.DateTimeFormat("en-CA", { timeZone: TZ, year: "numeric", month: "2-digit", day: "2-digit" })
      .format(date);
  const todayKey = () => berlinDateKey(new Date());

  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[c]);

  const fmtTime = (d) =>
    new Intl.DateTimeFormat(t().locale, { timeZone: TZ, hour: "2-digit", minute: "2-digit" }).format(d);
  const fmtMonth = (d) =>
    new Intl.DateTimeFormat(t().locale, { timeZone: TZ, month: "long", year: "numeric" }).format(d);
  const fmtDay = (d) =>
    new Intl.DateTimeFormat(t().locale, { timeZone: TZ, weekday: "long", day: "numeric", month: "long" }).format(d);
  const fmtShortWd = (d) =>
    new Intl.DateTimeFormat(t().locale, { timeZone: TZ, weekday: "short" }).format(d);
  const fmtDayNum = (d) =>
    new Intl.DateTimeFormat(t().locale, { timeZone: TZ, day: "numeric", month: "short" }).format(d);

  function venueById(id) {
    return state.data.venues.find((v) => v.id === id) || { id, name: id, color: "#888", category: "" };
  }

  function filtered() {
    return state.data.events.filter((e) => {
      if (state.venues.size && !state.venues.has(e.venue_id)) return false;
      const cat = venueById(e.venue_id).category;
      if (state.categories.size && !state.categories.has(cat)) return false;
      if (state.todayOnly && berlinDateKey(new Date(e.start)) !== todayKey()) return false;
      return true;
    });
  }

  function groupByDay(events) {
    const days = new Map();
    for (const e of events) {
      const key = berlinDateKey(new Date(e.start));
      if (!days.has(key)) days.set(key, []);
      days.get(key).push(e);
    }
    return days;
  }

  function cardHTML(e) {
    const v = venueById(e.venue_id);
    const cat = v.category;
    const start = new Date(e.start);
    const imgStyle = e.image
      ? `background-image:url('${esc(e.image)}')`
      : "";
    const meta = [];
    if (e.duration_min) meta.push(`${e.duration_min} ${t().minutes}`);
    if (e.price) meta.push(`${t().price}: ${esc(e.price)}`);
    return `
      <article class="card">
        <div class="card-img ${e.image ? "" : "placeholder"}" style="${imgStyle}" role="img"
             aria-label="${esc(e.title)}">
          <span class="cat-badge">${CATEGORY_ICON[cat] || ""} ${esc(t().categories[cat] || cat)}</span>
        </div>
        <div class="card-body">
          <div class="card-meta">
            <span class="time">${fmtTime(start)}</span>
            <span>·</span>
            <span class="venue-chip"><span class="dot" style="background:${esc(v.color)}"></span>${esc(v.name)}</span>
          </div>
          <h3>${esc(e.title)}</h3>
          ${e.subtitle ? `<p class="desc" style="-webkit-line-clamp:1">${esc(e.subtitle)}</p>` : ""}
          ${e.description ? `<p class="desc">${esc(e.description)}</p>` : ""}
          ${meta.length ? `<div class="small muted">${meta.join(" · ")}</div>` : ""}
          <div class="card-foot">
            ${e.sold_out ? `<span class="sold">${t().soldOut}</span>` : "<span></span>"}
            <a class="tickets" href="${esc(e.url)}" target="_blank" rel="noopener">${t().tickets} →</a>
          </div>
        </div>
      </article>`;
  }

  function renderBubbles() {
    const vBox = $("#venue-bubbles");
    vBox.innerHTML = state.data.venues.map((v) => {
      const on = state.venues.has(v.id);
      return `<button class="bubble ${on ? "active" : ""}" type="button" aria-pressed="${on}"
                data-venue="${esc(v.id)}">
                <span class="dot" style="background:${esc(v.color)}">${esc(v.name.charAt(0))}</span>
                ${esc(v.name)}</button>`;
    }).join("");

    const cBox = $("#category-bubbles");
    const cats = [...new Set(state.data.venues.map((v) => v.category))];
    cBox.innerHTML = cats.map((c) => {
      const on = state.categories.has(c);
      return `<button class="bubble ${on ? "active" : ""}" type="button" aria-pressed="${on}"
                data-category="${esc(c)}">
                <span class="dot" style="background:#333">${CATEGORY_ICON[c] || "•"}</span>
                ${esc(t().categories[c] || c)}</button>`;
    }).join("");
  }

  function renderSelects() {
    const vSel = $("#venue");
    vSel.innerHTML = `<option value="">${t().allVenues}</option>` +
      state.data.venues.map((v) => `<option value="${esc(v.id)}">${esc(v.name)}</option>`).join("");
    vSel.value = state.venues.size === 1 ? [...state.venues][0] : "";

    const cSel = $("#category");
    const cats = [...new Set(state.data.venues.map((v) => v.category))];
    cSel.innerHTML = `<option value="">${t().allCategories}</option>` +
      cats.map((c) => `<option value="${esc(c)}">${esc(t().categories[c] || c)}</option>`).join("");
    cSel.value = state.categories.size === 1 ? [...state.categories][0] : "";
  }

  function renderStaticText() {
    document.documentElement.lang = state.lang;
    $("#lang").textContent = t().lang;
    $("#today").textContent = state.todayOnly ? t().todayOn : t().today;
    $("#today").classList.toggle("pill-strong", state.todayOnly);
    $("#today").classList.toggle("pill", !state.todayOnly);
    $("#date").setAttribute("aria-label", t().jumpTo);
    $("#footer-note").textContent = t().footer;
    const gen = state.data.generated_at ? new Date(state.data.generated_at) : null;
    $("#updated").textContent = gen ? `${t().updated}: ${fmtDayNum(gen)} ${fmtTime(gen)}` : "";
  }

  function renderDayStrip(days) {
    const strip = $("#day-strip");
    const allDays = [...groupByDay(state.data.events).keys()].sort();
    const dates = allDays.slice(0, 60);
    strip.innerHTML = dates.map((key) => {
      const count = (days.get(key) || []).length;
      const d = new Date(`${key}T12:00:00+02:00`);
      return `<a href="#day-${key}" class="${count ? "" : "empty"}">
                <span class="wd">${esc(fmtShortWd(d))}</span>
                <span class="dn">${esc(new Intl.DateTimeFormat(t().locale, { timeZone: TZ, day: "numeric" }).format(d))}</span>
                <span class="ct">${count}</span></a>`;
    }).join("");
  }

  function render() {
    renderStaticText();
    renderBubbles();
    renderSelects();

    const status = $("#status");
    const program = $("#program");

    if (!state.data.events.length) {
      status.textContent = t().noData;
      program.innerHTML = "";
      $("#day-strip").innerHTML = "";
      return;
    }

    const events = filtered();
    const days = groupByDay(events);
    renderDayStrip(groupByDay(filtered()));
    status.textContent = events.length ? "" : t().noMatch;

    let html = "";
    let lastMonth = "";
    const today = todayKey();
    for (const key of [...days.keys()].sort()) {
      const d = new Date(`${key}T12:00:00+02:00`);
      const month = fmtMonth(d);
      if (month !== lastMonth) {
        html += `<h2 class="month">${esc(month)}</h2>`;
        lastMonth = month;
      }
      const isToday = key === today;
      html += `<section class="day" id="day-${key}">
                 <h3 class="day-head">${esc(fmtDay(d))}
                   ${isToday ? `<span class="today-tag">${t().today}</span>` : ""}
                 </h3>
                 <div class="cards">${days.get(key).map(cardHTML).join("")}</div>
               </section>`;
    }
    program.innerHTML = html;
  }

  function toggle(set, value) {
    if (set.has(value)) set.delete(value); else set.add(value);
  }

  function jumpToDate(value) {
    if (!value) return;
    const days = [...groupByDay(filtered()).keys()].sort();
    const target = days.find((k) => k >= value);
    const el = document.getElementById(`day-${target || value}`);
    if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function bind() {
    $("#lang").addEventListener("click", () => {
      state.lang = state.lang === "de" ? "en" : "de";
      localStorage.setItem("lang", state.lang);
      render();
    });

    $("#today").addEventListener("click", () => {
      state.todayOnly = !state.todayOnly;
      render();
      if (state.todayOnly) document.getElementById("top").scrollIntoView({ behavior: "smooth" });
    });

    $("#venue-bubbles").addEventListener("click", (ev) => {
      const b = ev.target.closest("[data-venue]");
      if (!b) return;
      toggle(state.venues, b.dataset.venue);
      render();
    });

    $("#category-bubbles").addEventListener("click", (ev) => {
      const b = ev.target.closest("[data-category]");
      if (!b) return;
      toggle(state.categories, b.dataset.category);
      render();
    });

    $("#venue").addEventListener("change", (ev) => {
      state.venues = new Set(ev.target.value ? [ev.target.value] : []);
      render();
    });

    $("#category").addEventListener("change", (ev) => {
      state.categories = new Set(ev.target.value ? [ev.target.value] : []);
      render();
    });

    $("#date").addEventListener("change", (ev) => jumpToDate(ev.target.value));
  }

  async function init() {
    try {
      const res = await fetch("data/events.json", { cache: "no-cache" });
      if (!res.ok) throw new Error(res.status);
      state.data = await res.json();
    } catch (err) {
      state.data = { generated_at: null, venues: [], events: [] };
      console.error("Could not load events:", err);
    }
    bind();
    render();
  }

  init();
})();
