#!/usr/bin/env python3
"""Collect Munich theatre, concert, opera and cinema programmes into data/events.json.

Per venue, the scraper:
  1. fetches the listing page(s) listed in VENUES,
  2. reads schema.org "Event" JSON-LD (most ticketing sites embed it),
  3. falls back to CSS selectors in the venue's "selectors" entry, if one is given.

A failing venue is logged and skipped; the others are still written.
Run locally:  python scripts/scrape.py
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

BERLIN = ZoneInfo("Europe/Berlin")
ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "events.json"
HEADERS = {
    "User-Agent": "muenchen-spielplan/1.0 (personal programme overview; contact: site owner)",
    "Accept-Language": "de-DE,de;q=0.9,en;q=0.5",
}
HORIZON_DAYS = 365  # keep events up to one year ahead

# NOTE: all URLs below are unverified starting points. Check each one in a
# browser before the first run and fix it if the site has moved.
VENUES = [
    {"id": "residenztheater", "name": "Residenztheater", "category": "theatre",
     "color": "#7a1f2b", "urls": ["https://www.residenztheater.de/spielplan"]},
    {"id": "kammerspiele", "name": "Münchner Kammerspiele", "category": "theatre",
     "color": "#2b4c7e", "urls": ["https://www.muenchner-kammerspiele.de/spielplan"]},
    {"id": "volkstheater", "name": "Münchner Volkstheater", "category": "theatre",
     "color": "#b5651d", "urls": ["https://www.muenchner-volkstheater.de/spielplan"]},
    {"id": "deutsches-theater", "name": "Deutsches Theater", "category": "theatre",
     "color": "#8b2c5c", "urls": ["https://www.deutschestheater.de/spielplan"]},
    {"id": "isarphilharmonie", "name": "Isarphilharmonie", "category": "concert",
     "color": "#1e6b5c", "urls": ["https://www.isarphilharmonie.de/"]},
    {"id": "bayerische-staatsoper", "name": "Bayerische Staatsoper", "category": "opera",
     "color": "#6b4a1e", "urls": ["https://www.staatsoper.de/spielplan"]},
    {"id": "museum-lichtspiele", "name": "Museum Lichtspiele", "category": "cinema",
     "color": "#4a3f8a", "urls": ["https://www.museum-lichtspiele.de/programm"]},
    {"id": "city-kino-atelier", "name": "City Kino Atelier", "category": "cinema",
     "color": "#2e7d32", "urls": ["https://www.citykinoatelier.de/programm"]},
]
# Optional CSS fallback, used only when a page has no JSON-LD events.
# Example: {"item": ".event", "title": "h3", "start": "time[datetime]", "link": "a[href]"}
SELECTORS: dict[str, dict] = {}


def fetch(url: str) -> BeautifulSoup | None:
    try:
        r = requests.get(url, headers=HEADERS, timeout=30)
        r.raise_for_status()
        return BeautifulSoup(r.text, "html.parser")
    except requests.RequestException as exc:
        print(f"  ! {url}: {exc}", file=sys.stderr)
        return None


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=BERLIN)
    return dt.astimezone(BERLIN)


def walk_jsonld(node):
    """Yield every dict in a JSON-LD structure."""
    if isinstance(node, dict):
        yield node
        for v in node.values():
            yield from walk_jsonld(v)
    elif isinstance(node, list):
        for v in node:
            yield from walk_jsonld(v)


def is_sold_out(event: dict) -> bool:
    offers = event.get("offers") or []
    if isinstance(offers, dict):
        offers = [offers]
    return any("SoldOut" in str(o.get("availability", "")) for o in offers if isinstance(o, dict))


def price_from(event: dict) -> str | None:
    offers = event.get("offers") or []
    if isinstance(offers, dict):
        offers = [offers]
    prices = []
    for o in offers:
        if isinstance(o, dict) and o.get("price") not in (None, ""):
            try:
                prices.append(float(str(o["price"]).replace(",", ".")))
            except ValueError:
                pass
    return f"ab {min(prices):.0f} €" if prices else None


def events_from_jsonld(soup: BeautifulSoup, page_url: str, venue: dict) -> list[dict]:
    found = []
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except json.JSONDecodeError:
            continue
        for node in walk_jsonld(data):
            types = node.get("@type", [])
            types = [types] if isinstance(types, str) else types
            if "Event" not in types and "ScreeningEvent" not in types and "TheaterEvent" not in types:
                continue
            start = parse_dt(node.get("startDate"))
            if not start or not node.get("name"):
                continue
            image = node.get("image")
            if isinstance(image, list):
                image = image[0] if image else None
            if isinstance(image, dict):
                image = image.get("url")
            url = node.get("url") or page_url
            found.append({
                "venue_id": venue["id"],
                "title": str(node["name"]).strip(),
                "start": start.isoformat(),
                "category": venue["category"],
                "description": re.sub(r"\s+", " ", str(node.get("description") or "")).strip()[:400],
                "image": urljoin(page_url, image) if image else None,
                "url": urljoin(page_url, url),
                "sold_out": is_sold_out(node),
                "price": price_from(node),
            })
    return found


def events_from_selectors(soup: BeautifulSoup, page_url: str, venue: dict) -> list[dict]:
    sel = SELECTORS.get(venue["id"])
    if not sel:
        return []
    found = []
    for item in soup.select(sel["item"]):
        title_el = item.select_one(sel["title"])
        time_el = item.select_one(sel["start"])
        link_el = item.select_one(sel.get("link", "a[href]"))
        if not (title_el and time_el):
            continue
        raw = time_el.get("datetime") or time_el.get_text(strip=True)
        start = parse_dt(raw)
        if not start:
            continue
        found.append({
            "venue_id": venue["id"],
            "title": title_el.get_text(" ", strip=True),
            "start": start.isoformat(),
            "category": venue["category"],
            "description": "",
            "image": None,
            "url": urljoin(page_url, link_el["href"]) if link_el else page_url,
            "sold_out": "ausverkauft" in item.get_text(" ", strip=True).lower(),
            "price": None,
        })
    return found


def scrape_venue(venue: dict) -> list[dict]:
    events: list[dict] = []
    for url in venue["urls"]:
        soup = fetch(url)
        if soup is None:
            continue
        page_events = events_from_jsonld(soup, url, venue) or events_from_selectors(soup, url, venue)
        print(f"  {venue['name']}: {len(page_events)} events from {url}")
        events.extend(page_events)
    return events


def main() -> int:
    now = datetime.now(BERLIN)
    horizon = now + timedelta(days=HORIZON_DAYS)
    collected: list[dict] = []
    for venue in VENUES:
        print(f"Scraping {venue['name']}")
        collected.extend(scrape_venue(venue))

    # Keep future events within the horizon and drop duplicates.
    seen = set()
    events = []
    for e in sorted(collected, key=lambda x: x["start"]):
        start = datetime.fromisoformat(e["start"])
        if start < now - timedelta(hours=3) or start > horizon:
            continue
        key = (e["venue_id"], e["start"], e["title"])
        if key in seen:
            continue
        seen.add(key)
        digest = hashlib.md5(e["title"].encode("utf-8")).hexdigest()[:6]
        e["id"] = f"{e['venue_id']}-{start:%Y%m%d%H%M}-{digest}"
        events.append(e)

    # Safety net: never overwrite good data with an empty run.
    if not events and OUT.exists():
        try:
            if json.loads(OUT.read_text(encoding="utf-8")).get("events"):
                print("No events scraped; keeping existing data/events.json", file=sys.stderr)
                return 1
        except json.JSONDecodeError:
            pass

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "venues": [{k: v for k, v in venue.items() if k != "urls"} for venue in VENUES],
        "events": events,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {len(events)} events to {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
