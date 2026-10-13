(() => {
  "use strict";

  const TZ = "Europe/Berlin";
  const DAYS_PER_CHUNK = 7;

  // ------------------------------------------------------------------ text
  const T = {
    de: {
      locale: "de-DE",
      sub: "Theater · Oper · Konzert · Kino in München",
      search: "Titel, Haus, Bühne suchen",
      today: "Heute", available: "Nur mit Karten", filters: "Filter", clear: "Zurücksetzen",
      jump: "Zu Datum springen",
      cat: { theatre: "Theater", opera: "Oper", concert: "Konzert", cinema: "Kino" },
      stageEvents: "Bühne & Konzert", films: "Kino",
      events: (n) => `${n} ${n === 1 ? "Termin" : "Termine"}`,
      soldOut: "Ausverkauft", few: "Wenige Karten", cancelled: "Entfällt",
      info: "Info", tickets: "Tickets", free: "Eintritt frei", min: "Min.",
      derived: "Termin laut Spielzeitangabe. Verfügbarkeit im Ticketshop prüfen.",
      updated: "Stand", stale: "Daten älter als 2 Tage",
      loading: "Spielplan wird geladen …",
      noData: "Noch keine Termine. Der Spielplan wird täglich automatisch eingelesen. Nach dem ersten Lauf erscheinen hier alle Termine.",
      noMatch: "Keine Termine für diese Auswahl.",
      sources: "Quellen", fine: "Alle Angaben werden automatisch von den Websites der Häuser übernommen und täglich aktualisiert. Ohne Gewähr. Bitte vor dem Besuch beim Haus prüfen. Titel stehen immer im Original.",
      ok: (n) => `${n} Termine`, none: "keine Daten", kept: (n) => `${n} (alter Stand)`,
      preview: "Vorschau mit Beispieldaten vom 13.10.2026. Die gehostete Seite zeigt den vollständigen, täglich aktualisierten Spielplan.",
      wd: ["So", "Mo", "Di", "Mi", "Do", "Fr", "Sa"],
    },
    en: {
      locale: "en-GB",
      sub: "Theatre · Opera · Concerts · Cinema in Munich",
      search: "Search title, venue, stage",
      today: "Today", available: "Tickets available", filters: "Filters", clear: "Reset",
      jump: "Jump to date",
      cat: { theatre: "Theatre", opera: "Opera", concert: "Concert", cinema: "Cinema" },
      stageEvents: "Stage & concerts", films: "Cinema",
      events: (n) => `${n} ${n === 1 ? "event" : "events"}`,
      soldOut: "Sold out", few: "Few tickets", cancelled: "Cancelled",
      info: "Info", tickets: "Tickets", free: "Free admission", min: "min",
      derived: "Date from the venue's run schedule. Check availability in the ticket shop.",
      updated: "Updated", stale: "Data older than 2 days",
      loading: "Loading programme …",
      noData: "No events yet. The programme is read automatically every day; all events appear here after the first run.",
      noMatch: "No events for this selection.",
      sources: "Sources", fine: "All information is taken automatically from the venues' websites and refreshed daily. No guarantee; please check with the venue before you go. Titles are always shown in the original.",
      ok: (n) => `${n} events`, none: "no data", kept: (n) => `${n} (older data)`,
      preview: "Preview with sample data from 13 Oct 2026. The hosted site shows the full programme, refreshed daily.",
      wd: ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"],
    },
  };
  // Labels that come from the venues' sites but are not titles
  const EN_WORDS = {
    "Oper": "Opera", "Ballett": "Ballet", "Konzert": "Concert", "Schauspiel": "Drama", "Lesung": "Reading",
    "Gespräch": "Talk", "Offene Probe": "Open rehearsal", "Liederabend": "Song recital", "Kind&Co": "Kids",
    "Klassik": "Classical", "Tanz": "Dance", "Tanztheater": "Dance theatre", "Buchpräsentation": "Book launch",
    "Kinder": "Children", "Familie": "Family", "Chor": "Choir", "Filmmusik": "Film music", "Weltmusik": "World music",
    "Kabarett": "Cabaret", "Festspiele": "Festival", "Premiere": "Premiere", "Uraufführung": "World premiere",
    "Wiederaufnahme": "Revival", "Zum letzten Mal": "Final performance", "Gastspiel": "Guest performance",
    "Publikumsgespräch": "Post-show talk", "Party": "Party",
  };

  const ICONS = {
    theatre: '<path d="M5 4.5c4 1.6 10 1.6 14 0V11a7 7 0 0 1-14 0z"/><path d="M9 10h.01M15 10h.01"/><path d="M9.5 14.5c1.4 1 3.6 1 5 0"/>',
    opera: '<path d="M3 4h18M3 20h18"/><path d="M4 4v16M20 4v16"/><path d="M4 4c0 6 3 9 6.5 10M20 4c0 6-3 9-6.5 10"/>',
    concert: '<path d="M9 18V5l11-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="17" cy="16" r="3"/>',
    cinema: '<rect x="3" y="5" width="18" height="14" rx="1.5"/><path d="M7 5v14M17 5v14M3 9h4M3 15h4M17 9h4M17 15h4"/>',
    search: '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
  };
  const icon = (k, cls = "ico") => `<svg class="${cls}" viewBox="0 0 24 24" aria-hidden="true">${ICONS[k] || ""}</svg>`;

  // ------------------------------------------------------------------ state
  const store = {
    get(k, d) { try { const v = localStorage.getItem("msp:" + k); return v === null ? d : JSON.parse(v); } catch { return d; } },
    set(k, v) { try { localStorage.setItem("msp:" + k, JSON.stringify(v)); } catch { /* storage unavailable */ } },
  };
  const state = {
    lang: store.get("lang", (navigator.language || "de").toLowerCase().startsWith("de") ? "de" : "en"),
    q: "",
    venues: new Set(store.get("venues", [])),
    cats: new Set(store.get("cats", [])),
    todayOnly: false,
    availableOnly: store.get("available", false),
    data: null,
    status: null,
    days: [],        // [{key, items}]
    rendered: 0,
  };
  const t = () => T[state.lang];
  const word = (w) => (state.lang === "en" && EN_WORDS[w]) || w;

  const $ = (s, root = document) => root.querySelector(s);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

  // ------------------------------------------------------------------ dates (always Munich time)
  const fmt = (opts) => new Intl.DateTimeFormat(t().locale, { timeZone: TZ, ...opts });
  const dayKey = (d) => new Intl.DateTimeFormat("en-CA", { timeZone: TZ, year: "numeric", month: "2-digit", day: "2-digit" }).format(d);
  const todayKey = () => dayKey(new Date());
  const keyToDate = (k) => new Date(`${k}T12:00:00Z`);
  const hhmm = (iso) => iso.slice(11, 16);

  // ------------------------------------------------------------------ data
  const venueMap = () => Object.fromEntries(state.data.venues.map((v) => [v.id, v]));

  function matches(e, V) {
    const v = V[e.venue_id];
    if (!v) return false;
    if (state.venues.size && !state.venues.has(e.venue_id)) return false;
    if (state.cats.size && !state.cats.has(v.category)) return false;
    if (state.availableOnly && (e.status === "sold_out" || e.status === "cancelled")) return false;
    if (state.q) {
      const hay = `${e.title} ${e.subtitle || ""} ${v.name} ${e.stage || ""} ${e.genre || ""} ${(e.tags || []).join(" ")}`.toLowerCase();
      if (!state.q.split(/\s+/).every((w) => hay.includes(w))) return false;
    }
    return true;
  }

  function buildDays() {
    const V = venueMap();
    const today = todayKey();
    const byDay = new Map();
    for (const e of state.data.events) {
      const k = e.start.slice(0, 10);
      if (k < today) continue;
      if (state.todayOnly && k !== today) continue;
      if (!matches(e, V)) continue;
      if (!byDay.has(k)) byDay.set(k, []);
      byDay.get(k).push(e);
    }
    state.days = [...byDay.keys()].sort().map((key) => ({ key, items: byDay.get(key).sort((a, b) => a.start.localeCompare(b.start)) }));
  }

  // ------------------------------------------------------------------ rendering pieces
  function placeholder(v, cls = "") {
    const short = v.short || v.name.slice(0, 3);
    return `<div class="ph ${cls}" style="background:${esc(v.color)}"><span class="ph-short">${esc(short)}</span>${icon(v.category, "ico ph-ico")}</div>`;
  }
  function imageOr(e, v) {
    const ph = placeholder(v);
    if (!e.image) return ph;
    return `${ph}<img src="${esc(e.image)}" alt="" loading="lazy" decoding="async" referrerpolicy="no-referrer" onerror="this.remove()">`;
  }
  function stateBadge(s) {
    if (s === "sold_out") return `<span class="state sold_out">${t().soldOut}</span>`;
    if (s === "few") return `<span class="state few">${t().few}</span>`;
    if (s === "cancelled") return `<span class="state cancelled">${t().cancelled}</span>`;
    return "";
  }
  function durationText(min) {
    if (!min) return "";
    const h = Math.floor(min / 60), m = min % 60;
    return state.lang === "de" ? (h ? `${h} Std.${m ? ` ${m} Min.` : ""}` : `${m} Min.`) : (h ? `${h} h${m ? ` ${m} min` : ""}` : `${m} min`);
  }

  function eventCard(e, v) {
    const meta = [e.stage, word(e.genre), durationText(e.duration_min), e.price === "free" ? t().free : e.price]
      .filter(Boolean).map((x) => `<span>${esc(x)}</span>`).join("");
    const tags = (e.tags || []).map((x) => `<span class="tag">${esc(word(x))}</span>`).join("") + stateBadge(e.status);
    const info = e.url ? `<a class="btn" href="${esc(e.url)}" target="_blank" rel="noopener">${t().info}</a>` : "";
    const tix = e.ticket_url && e.status !== "cancelled" && e.status !== "sold_out"
      ? `<a class="btn primary" href="${esc(e.ticket_url)}" target="_blank" rel="noopener">${t().tickets} →</a>` : "";
    return `<article class="ev is-${esc(e.status)}">
      <a class="media" href="${esc(e.url || v.home)}" target="_blank" rel="noopener" tabindex="-1" aria-hidden="true">
        ${imageOr(e, v)}<span class="cat-badge">${icon(v.category)}${esc(t().cat[v.category])}</span></a>
      <div class="ev-body">
        <div class="ev-top"><span class="time">${e.time_tbd ? "–" : hhmm(e.start)}</span>
          <span class="venue"><i style="background:${esc(v.color)}"></i><b>${esc(v.name)}</b></span></div>
        <h3 class="ev-title"><a href="${esc(e.url || v.home)}" target="_blank" rel="noopener">${esc(e.title)}</a></h3>
        ${e.subtitle ? `<p class="ev-sub">${esc(e.subtitle)}</p>` : e.description ? `<p class="ev-sub">${esc(e.description)}</p>` : ""}
        ${meta ? `<p class="meta">${meta}</p>` : ""}
        ${tags ? `<div class="tags">${tags}</div>` : ""}
        ${e.note === "derived" ? `<span class="note">${t().derived}</span>` : ""}
        ${info || tix ? `<div class="actions">${info}${tix}</div>` : ""}
      </div></article>`;
  }

  function filmCard(group, v) {
    const first = group[0];
    const now = new Date();
    const times = group.map((e) => {
      const ver = (e.tags || [])[0];
      const past = new Date(e.start) < now;
      const cls = `t ${e.status === "sold_out" ? "sold_out" : ""} ${past ? "past" : ""}`;
      const inner = `${hhmm(e.start)}${ver ? `<small>${esc(ver)}</small>` : ""}`;
      const href = e.ticket_url || e.url;
      const label = e.status === "sold_out" ? ` title="${t().soldOut}"` : "";
      return href && e.status !== "sold_out" && !past
        ? `<a class="${cls}" href="${esc(href)}" target="_blank" rel="noopener">${inner}</a>`
        : `<span class="${cls}"${label}>${inner}</span>`;
    }).join("");
    const img = group.find((e) => e.image)?.image;
    const dur = group.find((e) => e.duration_min)?.duration_min;
    return `<article class="film">
      <a class="poster" href="${esc(first.url || v.home)}" target="_blank" rel="noopener" tabindex="-1" aria-hidden="true">
        ${placeholder(v)}${img ? `<img src="${esc(img)}" alt="" loading="lazy" referrerpolicy="no-referrer" onerror="this.remove()">` : ""}</a>
      <div class="film-body">
        <span class="venue"><i style="background:${esc(v.color)}"></i><b>${esc(v.name)}</b></span>
        <h3 class="ev-title"><a href="${esc(first.url || v.home)}" target="_blank" rel="noopener">${esc(first.title)}</a></h3>
        ${dur ? `<p class="meta"><span>${esc(durationText(dur))}</span></p>` : ""}
        <div class="times">${times}</div>
      </div></article>`;
  }

  function dayHTML(day, V) {
    const d = keyToDate(day.key);
    const stage = [], films = new Map();
    for (const e of day.items) {
      const v = V[e.venue_id];
      if (v.category === "cinema") {
        const k = `${e.venue_id}|${e.title.toLowerCase()}`;
        if (!films.has(k)) films.set(k, []);
        films.get(k).push(e);
      } else stage.push(e);
    }
    const isToday = day.key === todayKey();
    const wd = fmt({ weekday: "long" }).format(d);
    let body = "";
    if (stage.length) {
      body += films.size ? `<h4 class="sub-h">${t().stageEvents}</h4>` : "";
      body += `<div class="cards">${stage.map((e) => eventCard(e, V[e.venue_id])).join("")}</div>`;
    }
    if (films.size) {
      body += `<h4 class="sub-h">${t().films}</h4>`;
      body += `<div class="films">${[...films.values()].map((g) => filmCard(g, V[g[0].venue_id])).join("")}</div>`;
    }
    return `<section class="day" id="day-${day.key}" data-key="${day.key}">
      <header class="day-head"><span class="day-num">${fmt({ day: "numeric" }).format(d)}</span>
        <span class="day-wd">${esc(wd)}</span><span class="day-ct">${t().events(day.items.length)}</span>
        ${isToday ? `<span class="today-badge">${t().today}</span>` : ""}</header>
      <div class="day-body">${body}</div></section>`;
  }

  function monthHTML(key) {
    const d = keyToDate(key);
    const month = fmt({ month: "long" }).format(d);
    return `<h2 class="month" id="month-${key.slice(0, 7)}">${esc(month)}<small>${key.slice(0, 4)}</small></h2>`;
  }

  // ------------------------------------------------------------------ programme (rendered in chunks)
  let observer;
  function renderProgramme() {
    const box = $("#programme");
    const msg = $("#status-msg");
    state.rendered = 0;
    box.innerHTML = "";
    if (!state.data.events.length) { msg.textContent = t().noData; msg.hidden = false; return; }
    if (!state.days.length) { msg.textContent = t().noMatch; msg.hidden = false; return; }
    msg.hidden = true;
    renderMore(DAYS_PER_CHUNK);
  }

  function renderMore(n) {
    const box = $("#programme");
    const V = venueMap();
    const end = Math.min(state.days.length, state.rendered + n);
    let html = "";
    for (let i = state.rendered; i < end; i++) {
      const key = state.days[i].key;
      const prev = i > 0 ? state.days[i - 1].key : null;
      if (!prev || prev.slice(0, 7) !== key.slice(0, 7)) html += monthHTML(key);
      html += dayHTML(state.days[i], V);
    }
    $(".more-sentinel", box)?.remove();
    box.insertAdjacentHTML("beforeend", html + (end < state.days.length ? '<div class="more-sentinel"></div>' : ""));
    state.rendered = end;
    const s = $(".more-sentinel", box);
    if (s) {
      observer?.disconnect();
      observer = new IntersectionObserver((ents) => { if (ents.some((x) => x.isIntersecting)) renderMore(DAYS_PER_CHUNK); }, { rootMargin: "1200px" });
      observer.observe(s);
    }
  }

  function jumpTo(key) {
    const idx = state.days.findIndex((d) => d.key >= key);
    if (idx < 0) return;
    if (idx >= state.rendered) renderMore(idx - state.rendered + 3);
    const el = document.getElementById(`day-${state.days[idx].key}`);
    if (!el) return;
    const barH = $(".bar").getBoundingClientRect().height;
    window.scrollTo({ top: el.getBoundingClientRect().top + window.scrollY - barH - 6, behavior: "smooth" });
  }

  // ------------------------------------------------------------------ chrome (filters, strip, footer)
  function renderStrip() {
    const strip = $("#strip");
    const today = todayKey();
    let html = "", lastMonth = "";
    for (const day of state.days.slice(0, 120)) {
      const d = keyToDate(day.key);
      const m = day.key.slice(0, 7);
      if (m !== lastMonth) { html += `<span class="m">${esc(fmt({ month: "short" }).format(d))}</span>`; lastMonth = m; }
      html += `<a href="#day-${day.key}" data-key="${day.key}" class="${day.key === today ? "today" : ""}">
        <span class="wd">${t().wd[d.getUTCDay()]}</span><span class="dn">${d.getUTCDate()}</span><span class="ct">${day.items.length}</span></a>`;
    }
    strip.innerHTML = html;
  }

  function renderChips() {
    const V = state.data.venues;
    const today = todayKey();
    const counts = {};
    for (const e of state.data.events) if (e.start.slice(0, 10) >= today) counts[e.venue_id] = (counts[e.venue_id] || 0) + 1;
    const cats = ["theatre", "opera", "concert", "cinema"].filter((c) => V.some((v) => v.category === c));
    $("#cats").innerHTML = cats.map((c) => `<button class="chip" type="button" data-cat="${c}" aria-pressed="${state.cats.has(c)}">
      ${icon(c)}${esc(t().cat[c])}</button>`).join("");
    $("#venues").innerHTML = V.map((v) => `<button class="chip" type="button" data-venue="${esc(v.id)}" aria-pressed="${state.venues.has(v.id)}">
      <span class="bub" style="background:${esc(v.color)}">${esc((v.short || "").slice(0, 4))}</span>${esc(v.name)}
      <span class="n">${counts[v.id] || 0}</span></button>`).join("");
  }

  function renderChrome() {
    document.documentElement.lang = state.lang;
    $("#brand-sub").textContent = t().sub;
    $("#q").placeholder = t().search;
    $("#q").setAttribute("aria-label", t().search);
    $("#today").textContent = t().today;
    $("#today").setAttribute("aria-pressed", state.todayOnly);
    $("#available").textContent = t().available;
    $("#available").setAttribute("aria-pressed", state.availableOnly);
    $("#filter-toggle").textContent = t().filters;
    $("#clear").textContent = t().clear;
    $("#date").setAttribute("aria-label", t().jump);
    $("#date").title = t().jump;
    $("#sources-h").textContent = t().sources;
    $("#fine").textContent = t().fine;
    document.querySelectorAll(".lang button").forEach((b) => b.setAttribute("aria-pressed", b.dataset.lang === state.lang));
    const pv = $("#preview-note");
    if (pv) pv.querySelector(".wrap").textContent = t().preview;

    const gen = state.data.generated_at ? new Date(state.data.generated_at) : null;
    const up = $("#updated");
    if (gen) {
      const stale = Date.now() - gen.getTime() > 48 * 3600e3;
      up.textContent = `${t().updated}: ${fmt({ day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }).format(gen)}${stale ? ` · ${t().stale}` : ""}`;
      up.classList.toggle("stale", stale);
    } else up.textContent = "";

    // sources
    const today = todayKey();
    const counts = {};
    for (const e of state.data.events) if (e.start.slice(0, 10) >= today) counts[e.venue_id] = (counts[e.venue_id] || 0) + 1;
    const st = state.status?.venues || {};
    $("#sources").innerHTML = state.data.venues.map((v) => {
      const s = st[v.id];
      const n = counts[v.id] || 0;
      let label = n ? t().ok(n) : t().none;
      if (s && s.ok === false && s.kept_previous) label = t().kept(n);
      const bad = !n || (s && s.ok === false);
      return `<div class="src"><i style="background:${esc(v.color)}"></i><a href="${esc(v.home)}" target="_blank" rel="noopener">${esc(v.name)}</a>
        <span class="n ${bad ? "bad" : ""}">${esc(label)}</span></div>`;
    }).join("");
    const dates = state.data.events.map((e) => e.start.slice(0, 10)).filter((k) => k >= today).sort();
    const dateEl = $("#date");
    if (dates.length) { dateEl.min = dates[0]; dateEl.max = dates[dates.length - 1]; }
  }

  function refresh({ keepScroll = false } = {}) {
    buildDays();
    renderChips();
    renderChrome();
    renderStrip();
    renderProgramme();
    if (!keepScroll) window.scrollTo({ top: 0 });
    setBarHeight();
  }

  function setBarHeight() {
    const h = $(".bar").getBoundingClientRect().height;
    document.documentElement.style.setProperty("--bar-h", `${Math.round(h) + 12}px`);
  }

  function syncStripToScroll() {
    const barH = $(".bar").getBoundingClientRect().height;
    let current = null;
    for (const sec of document.querySelectorAll(".day")) {
      if (sec.getBoundingClientRect().top - barH - 20 <= 0) current = sec.dataset.key; else break;
    }
    document.querySelectorAll("#strip a").forEach((a) => a.classList.toggle("current", a.dataset.key === current));
    const active = $(`#strip a[data-key="${current}"]`);
    if (active) {
      const strip = $("#strip");
      const r = active.getBoundingClientRect(), s = strip.getBoundingClientRect();
      if (r.left < s.left || r.right > s.right) strip.scrollLeft += r.left - s.left - s.width / 3;
    }
  }

  // ------------------------------------------------------------------ events
  function bind() {
    document.querySelectorAll(".lang button").forEach((b) => b.addEventListener("click", () => {
      state.lang = b.dataset.lang; store.set("lang", state.lang); refresh({ keepScroll: true });
    }));
    let qTimer;
    $("#q").addEventListener("input", (ev) => {
      clearTimeout(qTimer);
      qTimer = setTimeout(() => { state.q = ev.target.value.trim().toLowerCase(); refresh({ keepScroll: true }); }, 180);
    });
    $("#today").addEventListener("click", () => { state.todayOnly = !state.todayOnly; refresh(); });
    $("#available").addEventListener("click", () => { state.availableOnly = !state.availableOnly; store.set("available", state.availableOnly); refresh({ keepScroll: true }); });
    $("#cats").addEventListener("click", (ev) => {
      const b = ev.target.closest("[data-cat]"); if (!b) return;
      const c = b.dataset.cat; state.cats.has(c) ? state.cats.delete(c) : state.cats.add(c);
      store.set("cats", [...state.cats]); refresh();
    });
    $("#venues").addEventListener("click", (ev) => {
      const b = ev.target.closest("[data-venue]"); if (!b) return;
      const v = b.dataset.venue; state.venues.has(v) ? state.venues.delete(v) : state.venues.add(v);
      store.set("venues", [...state.venues]); refresh();
    });
    $("#clear").addEventListener("click", () => {
      state.venues.clear(); state.cats.clear(); state.q = ""; state.todayOnly = false; state.availableOnly = false;
      $("#q").value = ""; store.set("venues", []); store.set("cats", []); store.set("available", false); refresh();
    });
    $("#filter-toggle").addEventListener("click", (ev) => {
      const open = $("#more-filters").classList.toggle("open");
      ev.currentTarget.setAttribute("aria-expanded", open); setBarHeight();
    });
    $("#date").addEventListener("change", (ev) => { if (ev.target.value) jumpTo(ev.target.value); });
    $("#strip").addEventListener("click", (ev) => {
      const a = ev.target.closest("a[data-key]"); if (!a) return;
      ev.preventDefault(); jumpTo(a.dataset.key);
    });
    let ticking = false;
    window.addEventListener("scroll", () => {
      if (ticking) return; ticking = true;
      requestAnimationFrame(() => { syncStripToScroll(); ticking = false; });
    }, { passive: true });
    window.addEventListener("resize", setBarHeight);
  }

  // ------------------------------------------------------------------ boot
  async function load() {
    const embedded = document.getElementById("embedded-data");
    if (embedded && embedded.textContent.trim()) {
      const all = JSON.parse(embedded.textContent);
      return { data: all.events ? all : all.data, status: all.status || null };
    }
    const res = await fetch("data/events.json", { cache: "no-cache" });
    if (!res.ok) throw new Error(`events.json: HTTP ${res.status}`);
    const data = await res.json();
    let status = null;
    try { const r = await fetch("data/status.json", { cache: "no-cache" }); if (r.ok) status = await r.json(); } catch { /* optional */ }
    return { data, status };
  }

  async function init() {
    $("#status-msg").textContent = T[state.lang].loading;
    try {
      const { data, status } = await load();
      state.data = data; state.status = status;
    } catch (err) {
      console.error(err);
      state.data = { generated_at: null, venues: [], events: [] };
    }
    if (!state.data.venues?.length) state.data.venues = [];
    // forget saved filters for venues that no longer exist
    const ids = new Set(state.data.venues.map((v) => v.id));
    state.venues = new Set([...state.venues].filter((v) => ids.has(v)));
    if (location.hash === "#heute" || location.hash === "#today") state.todayOnly = true;
    bind();
    refresh();
    const m = location.hash.match(/^#day-(\d{4}-\d{2}-\d{2})$/);
    if (m) setTimeout(() => jumpTo(m[1]), 50);
  }

  init();
})();
