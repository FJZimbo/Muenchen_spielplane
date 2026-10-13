#!/usr/bin/env python3
"""Collect the Munich programme into data/events.json using a headless browser.

    python scripts/scrape.py                 # all venues
    python scripts/scrape.py --only kammerspiele --debug

--debug saves the rendered HTML of each page to debug/ so parsers can be fixed offline.
A venue that yields nothing keeps its previous (future) events and is flagged in data/status.json.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time as systime
import traceback
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

from playwright.sync_api import TimeoutError as PWTimeout
from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from extract import (BERLIN, embedded_json, extract_cards, extract_screenings, harvest_json,  # noqa: E402
                     make_soup, merge_events, parse_day_label, parse_schedule_page, find_dates)
from venues import VENUES  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DEBUG = ROOT / "debug"
EVENTS_FILE = DATA / "events.json"
STATUS_FILE = DATA / "status.json"
META_CACHE = DATA / "meta_cache.json"
HORIZON_DAYS = 400
USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/124.0 Safari/537.36 muenchen-spielplan/2.0")
ROBOTS_UA = "muenchen-spielplan"
PAUSE = 0.8  # seconds between page loads, to be polite

CONSENT_JS = r"""
() => {
  const rx = /^(alle akzeptieren|alle cookies akzeptieren|akzeptieren|accept all|accept|zustimmen|alle zulassen|einverstanden|ok|verstanden|allow all|annehmen|alle annehmen)$/i;
  for (const el of document.querySelectorAll('button, a, [role=button], input[type=button], input[type=submit]')) {
    const t = (el.innerText || el.value || '').trim();
    if (rx.test(t) && el.offsetParent !== null) { el.click(); return t; }
  }
  return null;
}
"""

CLICK_TEXT_JS = r"""
(pattern) => {
  const rx = new RegExp(pattern, 'i');
  const els = [...document.querySelectorAll('button, a, [role=button], [role=link], span, div')]
    .filter(el => el.offsetParent !== null && !el.disabled && el.getAttribute('aria-disabled') !== 'true');
  const parts = el => [el.getAttribute('aria-label'), el.getAttribute('title'), el.innerText]
    .filter(Boolean).map(p => p.replace(/\s+/g, ' ').trim());
  const hit = el => parts(el).some(p => rx.test(p));
  for (const el of els) {
    if (!hit(el)) continue;
    // prefer the innermost clickable element
    if ([...el.querySelectorAll('button, a, [role=button]')].some(hit)) continue;
    if ((el.innerText || '').length > 60) continue;
    el.scrollIntoView({block: 'center'});
    el.click();
    return parts(el).join(' | ').slice(0, 80) || 'clicked';
  }
  return null;
}
"""

MARK_TABS_JS = r"""
() => {
  const rx = /^(heute|morgen|today|tomorrow|mo|di|mi|do|fr|sa|so|mon|tue|wed|thu|fri|sat|sun)\.?,?\s*(\d{1,2}\.\s*\d{1,2}\.?|\d{1,2}\.?\s*[a-zä]{3,9}\.?)?$/i;
  const out = [];
  const cands = [...document.querySelectorAll('button, a, [role=tab], li, label, div, span')];
  for (const el of cands) {
    const t = (el.innerText || '').replace(/\s+/g, ' ').trim();
    if (!t || t.length > 24 || !rx.test(t)) continue;
    if (!/\d/.test(t) && !/^(heute|morgen|today|tomorrow)$/i.test(t)) continue;
    // innermost match only
    if ([...el.children].some(c => rx.test((c.innerText || '').replace(/\s+/g, ' ').trim()))) continue;
    out.push(el);
  }
  // keep only one element per label (the first)
  const seen = new Set();
  const uniq = out.filter(el => { const t = el.innerText.replace(/\s+/g,' ').trim(); if (seen.has(t)) return false; seen.add(t); return true; });
  uniq.forEach((el, i) => el.setAttribute('data-msp-tab', String(i)));
  return uniq.map(el => el.innerText.replace(/\s+/g, ' ').trim());
}
"""


# --------------------------------------------------------------------------- helpers


class Robots:
    def __init__(self, request):
        self.request = request
        self.cache: dict[str, RobotFileParser | None] = {}

    def allowed(self, url: str) -> bool:
        host = urlparse(url)
        base = f"{host.scheme}://{host.netloc}"
        if base not in self.cache:
            rp = RobotFileParser()
            try:
                r = self.request.get(base + "/robots.txt", timeout=15000)
                if r.ok:
                    rp.parse(r.text().splitlines())
                    self.cache[base] = rp
                else:
                    self.cache[base] = None  # no robots.txt -> allowed
            except Exception:
                self.cache[base] = None
        rp = self.cache[base]
        return True if rp is None else rp.can_fetch(ROBOTS_UA, url)


def settle(page, ms: int = 1500):
    try:
        page.wait_for_load_state("networkidle", timeout=ms + 6000)
    except PWTimeout:
        pass
    page.wait_for_timeout(ms // 3)


def scroll_through(page, steps: int = 12):
    last = 0
    for _ in range(steps):
        h = page.evaluate("() => { window.scrollBy(0, window.innerHeight * 1.5); return document.body.scrollHeight; }")
        page.wait_for_timeout(250)
        at_bottom = page.evaluate("() => window.innerHeight + window.scrollY >= document.body.scrollHeight - 5")
        if at_bottom and h == last:
            break
        last = h
    page.evaluate("() => window.scrollTo(0, 0)")


def accept_consent(page):
    try:
        if page.evaluate(CONSENT_JS):
            page.wait_for_timeout(600)
    except Exception:
        pass


class Session:
    """One browser page with JSON-response capture."""

    def __init__(self, context):
        self.page = context.new_page()
        self.responses = []
        self.page.on("response", self._on_response)

    def _on_response(self, resp):
        ct = (resp.headers.get("content-type") or "").lower()
        if "json" in ct and not re.search(r"google|analytics|facebook|hotjar|matomo|cookie|consent|sentry|gtm", resp.url):
            self.responses.append(resp)

    def drain_json(self) -> list[tuple[str, object]]:
        out = []
        for r in self.responses:
            try:
                body = r.text()
                if len(body) > 8_000_000:
                    continue
                out.append((r.url, json.loads(body)))
            except Exception:
                continue
        self.responses = []
        return out

    def goto(self, url: str):
        resp = self.page.goto(url, wait_until="domcontentloaded", timeout=45000)
        settle(self.page)
        accept_consent(self.page)
        return resp.status if resp else None

    def html(self) -> str:
        return self.page.content()


def save_debug(name: str, html: str):
    DEBUG.mkdir(exist_ok=True)
    # Drop bulky script/style bodies but keep JSON-LD / __NEXT_DATA__
    html = re.sub(r"<script(?![^>]*(ld\+json|__NEXT_DATA__|application/json))[^>]*>.*?</script>", "<script></script>",
                  html, flags=re.S | re.I)
    html = re.sub(r"<style[^>]*>.*?</style>", "<style></style>", html, flags=re.S | re.I)
    (DEBUG / f"{name}.html").write_text(html[:3_000_000], encoding="utf-8")


# --------------------------------------------------------------------------- page collection


def collect_snapshots(sess: Session, venue: dict, url: str, report: dict, debug: bool, idx: int):
    """Open url, run the venue's actions, return [(html, page_url, context_date)] and captured JSON."""
    today = datetime.now(BERLIN).date()
    snaps: list[tuple[str, str, date | None]] = []
    status = sess.goto(url)
    page_info = {"url": url, "http": status, "snapshots": 0, "actions": []}
    report["pages"].append(page_info)
    if status and status >= 400:
        report["errors"].append(f"HTTP {status} for {url}")
        return snaps, sess.drain_json()

    actions = venue.get("actions", [])
    scroll_through(sess.page)
    snaps.append((sess.html(), sess.page.url, None))

    for act in actions:
        if "load_more" in act:
            clicks = 0
            for _ in range(act["load_more"]):
                before = len(sess.html())
                label = sess.page.evaluate(CLICK_TEXT_JS, r"^(mehr laden|mehr anzeigen|weitere laden|weitere anzeigen|weitere termine|alle termine|load more|show more)$")
                if not label:
                    break
                settle(sess.page, 1200)
                clicks += 1
                if len(sess.html()) <= before:
                    break
            if clicks:
                scroll_through(sess.page, 6)
                snaps[-1] = (sess.html(), sess.page.url, None)
            page_info["actions"].append(f"load_more x{clicks}")

        if "next" in act:
            done = 0
            for _ in range(act["max"]):
                before = sess.html()
                label = sess.page.evaluate(CLICK_TEXT_JS, act["next"])
                if not label:
                    break
                settle(sess.page, 1500)
                after = sess.html()
                if after == before:
                    break
                scroll_through(sess.page, 4)
                snaps.append((sess.html(), sess.page.url, None))
                done += 1
            page_info["actions"].append(f"next x{done}")

        if "follow" in act:
            rx = re.compile(act["follow"], re.I)
            seen = {sess.page.url}
            queue = []
            followed = 0

            def enqueue(html, base):
                for h in re.findall(r'href="([^"]+)"', html):
                    full = urljoin(base, h.replace("&amp;", "&")).split("#")[0]
                    m = re.search(r"month=(\d{4}-\d{2})", full)
                    keyed = m[1] if m else full
                    if rx.search(full) and keyed not in seen:
                        seen.add(keyed)
                        queue.append(full)

            enqueue(snaps[0][0], sess.page.url)
            while queue and followed < act["max"]:
                nxt = queue.pop(0)
                systime.sleep(PAUSE)
                st = sess.goto(nxt)
                if st and st >= 400:
                    report["errors"].append(f"HTTP {st} for {nxt}")
                    continue
                scroll_through(sess.page, 4)
                html = sess.html()
                snaps.append((html, sess.page.url, None))
                enqueue(html, sess.page.url)
                followed += 1
            page_info["actions"].append(f"follow x{followed}")

        if "day_tabs" in act:
            labels = sess.page.evaluate(MARK_TABS_JS) or []
            used = 0
            for i, label in enumerate(labels[: act["day_tabs"]]):
                ctx = parse_day_label(label, today)
                if ctx is None:
                    continue
                try:
                    sess.page.evaluate(MARK_TABS_JS)  # re-mark after re-renders
                    loc = sess.page.locator(f'[data-msp-tab="{i}"]').first
                    loc.scroll_into_view_if_needed(timeout=3000)
                    loc.click(timeout=4000)
                except Exception:
                    continue
                settle(sess.page, 1200)
                snaps.append((sess.html(), sess.page.url, ctx))
                used += 1
            if used:
                # The initial view has no reliable date (tab labels would be mistaken for dates)
                snaps = [s for s in snaps if s[2] is not None]
            page_info["actions"].append(f"day_tabs {used}/{len(labels)}")

    page_info["snapshots"] = len(snaps)
    if debug:
        for n, (html, _, ctx) in enumerate(snaps[:3]):
            save_debug(f"{venue['id']}-{idx}-{n}", html)
    return snaps, sess.drain_json()


# --------------------------------------------------------------------------- venues


def scrape_venue(context, robots: Robots, venue: dict, debug: bool) -> tuple[list[dict], dict]:
    today = datetime.now(BERLIN).date()
    horizon = today + timedelta(days=HORIZON_DAYS)
    report = {"name": venue["name"], "pages": [], "errors": [], "stats": [], "count": 0}
    events: list[dict] = []
    sess = Session(context)
    try:
        json_payloads = []
        for idx, url in enumerate(venue["start"]):
            if not robots.allowed(url):
                report["errors"].append(f"robots.txt disallows {url}")
                continue
            systime.sleep(PAUSE)
            try:
                snaps, js = collect_snapshots(sess, venue, url, report, debug, idx)
            except Exception as exc:
                report["errors"].append(f"{url}: {type(exc).__name__}: {str(exc)[:200]}")
                continue
            json_payloads.extend(js)
            for html, page_url, ctx in snaps:
                json_payloads.extend((page_url, j) for j in embedded_json(html))
                if venue["mode"] == "cards":
                    evs, st = extract_cards(html, page_url, venue, today, ctx)
                elif venue["mode"] == "screenings":
                    evs, st = extract_screenings(html, page_url, venue, today, ctx)
                else:
                    evs, st = [], {}
                report["stats"].append({"url": page_url, "context": str(ctx) if ctx else None, **st, "events": len(evs)})
                events.extend(evs)

            if venue["mode"] == "schedule":
                show_rx = re.compile(venue["show_links"], re.I)
                links = []
                for html, page_url, _ in snaps:
                    soup = make_soup(html)
                    for a in soup.find_all("a", href=True):
                        full = urljoin(page_url, a["href"]).split("#")[0].split("?")[0]
                        if show_rx.search(full) and full not in links:
                            links.append(full)
                report["stats"].append({"url": url, "show_links": len(links)})
                for link in links[:80]:
                    if not robots.allowed(link):
                        continue
                    systime.sleep(PAUSE)
                    try:
                        sess.goto(link)
                        html = sess.html()
                    except Exception as exc:
                        report["errors"].append(f"{link}: {type(exc).__name__}")
                        continue
                    evs, st = parse_schedule_page(html, link, venue, today)
                    if st.get("dates"):
                        report["stats"].append({"url": link, **st})
                    events.extend(evs)
                    json_payloads.extend((link, j) for j in embedded_json(html))

        # JSON: always for json venues, otherwise only as a fallback
        if venue.get("json") or not events:
            jevents = []
            for src, payload in json_payloads:
                jevents.extend(harvest_json(payload, venue, src, today, horizon))
            report["stats"].append({"json_payloads": len(json_payloads), "json_events": len(jevents)})
            events.extend(jevents)
            if debug and json_payloads:
                DEBUG.mkdir(exist_ok=True)
                biggest = sorted(json_payloads, key=lambda p: -len(json.dumps(p[1])))[:3]
                for n, (src, payload) in enumerate(biggest):
                    (DEBUG / f"{venue['id']}-json-{n}.json").write_text(
                        json.dumps({"source": src, "data": payload}, ensure_ascii=False)[:2_000_000], encoding="utf-8")
    except Exception as exc:
        report["errors"].append(f"{type(exc).__name__}: {exc}")
        traceback.print_exc()
    finally:
        sess.page.close()

    events = [e for e in merge_events(events) if today <= date.fromisoformat(e["start"][:10]) <= horizon]
    report["count"] = len(events)
    return events, report


def enrich(context, robots: Robots, events: list[dict], report: dict):
    """Fill missing images/descriptions from each production page's og: tags (cached)."""
    cache = {}
    if META_CACHE.exists():
        try:
            cache = json.loads(META_CACHE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            cache = {}
    need = sorted({e["url"] for e in events if (not e.get("image") or not e.get("description")) and e.get("url")})
    fetched = 0
    for url in need:
        if url in cache or fetched >= 250:
            continue
        if not robots.allowed(url):
            cache[url] = {}
            continue
        try:
            r = context.request.get(url, timeout=20000)
            meta = {}
            if r.ok:
                soup = make_soup(r.text(), keep_scripts=True)
                for m in soup.find_all("meta"):
                    k = m.get("property") or m.get("name")
                    if k in ("og:image", "og:description", "description", "twitter:image"):
                        meta.setdefault(k, m.get("content"))
            cache[url] = {
                "image": urljoin(url, meta.get("og:image") or meta.get("twitter:image") or "") or None,
                "description": (meta.get("og:description") or meta.get("description") or "").strip()[:400] or None,
            }
            fetched += 1
            systime.sleep(0.3)
        except Exception:
            cache[url] = {}
    generic = re.compile(r"sharing|default|og-image|open_graph|logo|fallback|spielzeit", re.I)
    for e in events:
        c = cache.get(e.get("url") or "", {})
        if not e.get("image") and c.get("image") and not generic.search(c["image"]):
            e["image"] = c["image"]
        if not e.get("description") and c.get("description"):
            e["description"] = c["description"]
    META_CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=0), encoding="utf-8")
    report["enriched_pages"] = fetched


# --------------------------------------------------------------------------- main


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", help="venue ids to scrape")
    ap.add_argument("--debug", action="store_true", help="save rendered HTML to debug/")
    ap.add_argument("--no-enrich", action="store_true")
    args = ap.parse_args()

    now = datetime.now(BERLIN)
    previous = {"events": [], "venues": []}
    if EVENTS_FILE.exists():
        try:
            previous = json.loads(EVENTS_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    prev_status = {}
    if STATUS_FILE.exists():
        try:
            prev_status = json.loads(STATUS_FILE.read_text(encoding="utf-8")).get("venues", {})
        except json.JSONDecodeError:
            pass

    selected = [v for v in VENUES if not args.only or v["id"] in args.only]
    all_events: list[dict] = []
    status: dict[str, dict] = {}

    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--disable-blink-features=AutomationControlled"])
        context = browser.new_context(
            locale="de-DE", timezone_id="Europe/Berlin", user_agent=USER_AGENT,
            viewport={"width": 1366, "height": 900},
        )
        robots = Robots(context.request)
        for venue in selected:
            print(f"== {venue['name']}", flush=True)
            t0 = systime.time()
            events, report = scrape_venue(context, robots, venue, args.debug)
            report["seconds"] = round(systime.time() - t0, 1)
            if events:
                report["ok"] = True
                report["last_success"] = now.isoformat(timespec="minutes")
                report["first"] = events[0]["start"][:10]
                report["last"] = events[-1]["start"][:10]
                report["sold_out"] = sum(1 for e in events if e["status"] == "sold_out")
                report["with_image"] = sum(1 for e in events if e.get("image"))
            else:
                report["ok"] = False
                report["last_success"] = prev_status.get(venue["id"], {}).get("last_success")
                kept = [e for e in previous.get("events", []) if e["venue_id"] == venue["id"]
                        and e["start"][:10] >= now.date().isoformat()]
                report["kept_previous"] = len(kept)
                events = kept
            print(f"   {len(events)} events  ({report['seconds']}s)  errors: {report['errors'][:3]}", flush=True)
            for st in report["stats"][:6]:
                print(f"   {st}", flush=True)
            all_events.extend(events)
            status[venue["id"]] = report

        # keep venues that were not part of this run
        if args.only:
            for e in previous.get("events", []):
                if e["venue_id"] not in args.only and e["start"][:10] >= now.date().isoformat():
                    all_events.append(e)
            for vid, st in prev_status.items():
                status.setdefault(vid, st)

        if not args.no_enrich:
            enrich_report = {}
            try:
                enrich(context, robots, all_events, enrich_report)
            except Exception as exc:
                print("enrich failed:", exc)
            print("enriched pages:", enrich_report.get("enriched_pages"))
        browser.close()

    all_events = merge_events(all_events)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "venues": [{k: v[k] for k in ("id", "name", "short", "category", "color")} | {"home": v["start"][0]}
                   for v in VENUES],
        "events": all_events,
    }
    DATA.mkdir(exist_ok=True)
    EVENTS_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    STATUS_FILE.write_text(json.dumps({"generated_at": payload["generated_at"], "venues": status},
                                      ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nWrote {len(all_events)} events.")
    for vid, st in status.items():
        print(f"  {vid:24} {'OK ' if st.get('ok') else 'NO DATA'} {st.get('count', 0):5}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
