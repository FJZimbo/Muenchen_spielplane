"""Parsing helpers for the Munich programme scraper.

Nothing in this module touches the network, so every function can be tested
offline against saved HTML (see scripts/test_extract.py).

Three extraction strategies:
  * extract_cards()      - one card per performance (theatre, opera, concert)
  * extract_screenings() - one block per film with many times (cinemas)
  * harvest_json()       - schema.org JSON-LD, __NEXT_DATA__ and captured API JSON
plus parse_schedule_page() for show pages that only state a run and a weekly pattern.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime, time, timedelta
from urllib.parse import urljoin, urldefrag
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup, NavigableString, Tag

BERLIN = ZoneInfo("Europe/Berlin")

try:  # lxml is faster and more forgiving; fall back to the stdlib parser
    import lxml  # noqa: F401
    PARSER = "lxml"
except ImportError:  # pragma: no cover
    PARSER = "html.parser"

# --------------------------------------------------------------------------- text

MONTHS = {
    "januar": 1, "jan": 1, "january": 1,
    "februar": 2, "feb": 2, "february": 2,
    "märz": 3, "maerz": 3, "mär": 3, "mrz": 3, "march": 3, "mar": 3,
    "april": 4, "apr": 4,
    "mai": 5, "may": 5,
    "juni": 6, "jun": 6, "june": 6,
    "juli": 7, "jul": 7, "july": 7,
    "august": 8, "aug": 8,
    "september": 9, "sept": 9, "sep": 9,
    "oktober": 10, "okt": 10, "october": 10, "oct": 10,
    "november": 11, "nov": 11,
    "dezember": 12, "dez": 12, "december": 12, "dec": 12,
}
_MONTH_ALT = "|".join(sorted(map(re.escape, MONTHS), key=len, reverse=True))

WEEKDAYS = {
    "montag": 0, "mo": 0, "monday": 0, "mon": 0,
    "dienstag": 1, "di": 1, "tuesday": 1, "tue": 1,
    "mittwoch": 2, "mi": 2, "wednesday": 2, "wed": 2,
    "donnerstag": 3, "do": 3, "thursday": 3, "thu": 3,
    "freitag": 4, "fr": 4, "friday": 4, "fri": 4,
    "samstag": 5, "sa": 5, "sonnabend": 5, "saturday": 5, "sat": 5,
    "sonntag": 6, "so": 6, "sunday": 6, "sun": 6,
}
_WD_ALT = "|".join(sorted(map(re.escape, WEEKDAYS), key=len, reverse=True))

DATE_PATTERNS = [
    # (priority, regex, kind)
    (0, re.compile(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)"), "iso"),
    (1, re.compile(r"(?<![\d.])(\d{1,2})\.(\d{1,2})\.(\d{4}|\d{2})(?![\d])"), "dmy"),
    (2, re.compile(rf"(?<![\d.])(\d{{1,2}})\.?\s*({_MONTH_ALT})\.?(?![a-zäöü])(?:,?\s+(\d{{4}}))?", re.I), "dMy"),
    (3, re.compile(r"(?<![\d.])(\d{1,2})\.(\d{1,2})\.(?!\d)"), "dm"),
]

TIME_RE = re.compile(
    r"(?<![\d.:,])(\d{1,2})([:.])(\d{2})(?![\d])"
    r"(?:\s*(?:–|-|—|bis)\s*(\d{1,2})[:.](\d{2})(?!\d))?"
    r"(\s*(?:Uhr|h)\b)?",
    re.I,
)
_TIME_EXCLUDE_BEFORE = re.compile(
    r"(einlass|einführung|einfuehrung|kasse|abendkasse|öffnung|doors|foyer ab|treffpunkt|bar ab)\D{0,14}$", re.I
)
_TIME_PREFER_BEFORE = re.compile(r"(beginn|vorstellungsbeginn|start|anfang)\D{0,6}$", re.I)

STATUS_PATTERNS = [
    ("cancelled", re.compile(r"entfällt|entfaellt|abgesagt|fällt aus|\bausfall\b|cancel+ed|verschoben", re.I)),
    ("sold_out", re.compile(r"ausverkauft|ausgebucht|sold[\s-]?out", re.I)),
    ("few", re.compile(r"letzte (tickets|karten|plätze)|wenige (tickets|karten|plätze)|restkarten|few tickets|last tickets|nur noch \d+", re.I)),
]

TAG_PATTERNS = [
    ("Premiere", re.compile(r"\bpremiere\b", re.I)),
    ("Uraufführung", re.compile(r"uraufführung|urauffuehrung", re.I)),
    ("Wiederaufnahme", re.compile(r"wiederaufnahme", re.I)),
    ("Zum letzten Mal", re.compile(r"zum letzten mal|letzte vorstellung|dernière", re.I)),
    ("English surtitles", re.compile(r"english surtitles|englische übertitel|engl\. übertitel|with english", re.I)),
    ("Gastspiel", re.compile(r"\bgastspiel\b", re.I)),
    ("Publikumsgespräch", re.compile(r"publikumsgespräch|nachgespräch", re.I)),
    ("Familie", re.compile(r"kind&co|familienvorstellung|für kinder|familienkino|kinderkonzert", re.I)),
]

VERSION_RE = re.compile(r"^\s*[·\-–]?\s*(OmU|OmeU|OmdU|OmengU|OV|OF|DF|OmU\s*engl\.?|engl\.?\s*OV|3D|DF\s*3D|OV\s*3D)\b", re.I)

TICKET_HREF = re.compile(
    r"tickets?\.|webticket|muenchenticket|eventim|reservix|kinoheld|showId=|/ticket|/kartenanfrage|/booking|/buchen|/checkout|vivenu|ticketmaster",
    re.I,
)
BAD_TITLE = re.compile(
    r"^(tickets?|karten|mehr|more|mehr erfahren|info|infos|details?|kaufen|buy|termin speichern|trailer( ansehen)?|"
    r"ausverkauft|sold out|weiterlesen|read more|jetzt buchen|zum stück|zur veranstaltung|zum film|"
    r"merken|teilen|share|kalender|calendar|premiere|oper|ballett|konzert|extra|kind&co|bühne \d|ics)$",
    re.I,
)
BAD_IMAGE = re.compile(r"logo|icon|sprite|placeholder|blank|spacer|pixel|tracking|\.svg(\?|$)|data:image", re.I)

WS = re.compile(r"\s+")


def clean(text: str | None) -> str:
    return WS.sub(" ", text or "").strip()


# --------------------------------------------------------------------------- dates


def infer_year(month: int, day: int, today: date) -> int | None:
    """Pick the year that puts the date in the window [today - 60 days, today + ~10 months]."""
    for year in (today.year - 1, today.year, today.year + 1):
        try:
            candidate = date(year, month, day)
        except ValueError:
            continue
        if candidate >= today - timedelta(days=60):
            return year
    return None


def find_dates(text: str, today: date) -> list[tuple[int, date]]:
    """All dates in text as (position, date), in text order."""
    hits: dict[int, tuple[int, date]] = {}
    for prio, rx, kind in DATE_PATTERNS:
        for m in rx.finditer(text):
            try:
                if kind == "iso":
                    d = date(int(m[1]), int(m[2]), int(m[3]))
                elif kind == "dmy":
                    y = int(m[3])
                    y = y + 2000 if y < 100 else y
                    d = date(y, int(m[2]), int(m[1]))
                elif kind == "dMy":
                    mo = MONTHS[m[2].lower()]
                    y = int(m[3]) if m[3] else infer_year(mo, int(m[1]), today)
                    if y is None:
                        continue
                    d = date(y, mo, int(m[1]))
                else:  # dm
                    mo, dy = int(m[2]), int(m[1])
                    y = infer_year(mo, dy, today)
                    if y is None:
                        continue
                    d = date(y, mo, dy)
            except (ValueError, KeyError):
                continue
            pos = m.start()
            if pos not in hits or prio < hits[pos][0]:
                hits[pos] = (prio, d)
    # Drop matches that start inside a longer, higher-priority match (e.g. "13.10." inside "13.10.2026")
    return [(pos, d) for pos, (_, d) in sorted(hits.items())]


def first_date(text: str, today: date) -> date | None:
    found = find_dates(text, today)
    return found[0][1] if found else None


def find_times(text: str) -> list[dict]:
    """Start times in text. Each hit: {pos, time, end, preferred, excluded}."""
    out = []
    for m in TIME_RE.finditer(text):
        hh, sep, mm = int(m[1]), m[2], int(m[3])
        has_uhr = bool(m[6])
        has_range = m[4] is not None
        if hh > 23 or mm > 59:
            continue
        if sep == "." and not (has_uhr or has_range):
            continue  # "13.10." is a date, "19.30" without "Uhr" is too ambiguous
        after = text[m.end(): m.end() + 2]
        if not has_uhr and not has_range and re.match(r"\.\d", after):
            continue
        end = None
        if has_range:
            eh, em = int(m[4]), int(m[5])
            if eh <= 23 and em <= 59:
                end = time(eh, em)
        before = text[max(0, m.start() - 30): m.start()]
        out.append({
            "pos": m.start(),
            "end_pos": m.end(),
            "time": time(hh, mm),
            "end": end,
            "preferred": bool(_TIME_PREFER_BEFORE.search(before)),
            "excluded": bool(_TIME_EXCLUDE_BEFORE.search(before)),
        })
    return out


def pick_start_time(text: str) -> dict | None:
    hits = find_times(text)
    if not hits:
        return None
    for h in hits:
        if h["preferred"]:
            return h
    for h in hits:
        if not h["excluded"]:
            return h
    return hits[0]


def count_start_times(text: str) -> int:
    return len({(h["time"]) for h in find_times(text) if not h["excluded"]})


def parse_day_label(label: str, today: date) -> date | None:
    """'Heute 13.10.', 'Mi 14.10.', 'Morgen', 'Fr, 16. Okt' -> date"""
    lab = clean(label).lower()
    d = first_date(lab, today)
    if d:
        return d
    if lab.startswith(("heute", "today")):
        return today
    if lab.startswith(("morgen", "tomorrow")):
        return today + timedelta(days=1)
    return None


def to_iso(d: date, t: time | None) -> str:
    dt = datetime.combine(d, t or time(0, 0), tzinfo=BERLIN)
    return dt.isoformat()


def parse_iso_datetime(value: str) -> datetime | None:
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})(?::(\d{2}))?(?:\.\d+)?(Z|[+-]\d{2}:?\d{2})?$", value.strip())
    if not m:
        return None
    try:
        dt = datetime(int(m[1]), int(m[2]), int(m[3]), int(m[4]), int(m[5]))
    except ValueError:
        return None
    tz = m[7]
    if tz:
        try:
            aware = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
            return aware.astimezone(BERLIN)
        except ValueError:
            return dt.replace(tzinfo=BERLIN)
    return dt.replace(tzinfo=BERLIN)


# --------------------------------------------------------------------------- fields


def detect_status(text: str) -> str | None:
    for status, rx in STATUS_PATTERNS:
        if rx.search(text):
            return status
    return None


def detect_tags(text: str) -> list[str]:
    return [label for label, rx in TAG_PATTERNS if rx.search(text)]


_PRICE_RANGE = re.compile(r"(\d{1,3}(?:[,.]\d{2})?)\s*(?:€|EUR|Euro)?\s*(?:bis|–|-)\s*(\d{1,3}(?:[,.]\d{2})?)\s*(?:€|EUR|Euro)", re.I)
_PRICE_FROM = re.compile(r"(?:ab|from)\s*(\d{1,3}(?:[,.]\d{2})?)\s*(?:€|EUR|Euro)", re.I)
_PRICE_ONE = re.compile(r"(?<![\d,.])(\d{1,3}(?:[,.]\d{2})?)\s*(?:€|EUR|Euro)\b", re.I)
_FREE = re.compile(r"kostenfrei|eintritt frei|freier eintritt|free admission|free entry", re.I)


def _num(s: str) -> str:
    s = s.replace(".", ",")
    return s[:-3] if s.endswith(",00") else s


def detect_price(text: str) -> str | None:
    if m := _PRICE_RANGE.search(text):
        return f"{_num(m[1])}–{_num(m[2])} €"
    if m := _PRICE_FROM.search(text):
        return f"ab {_num(m[1])} €"
    if m := _PRICE_ONE.search(text):
        return f"{_num(m[1])} €"
    if _FREE.search(text):
        return "free"
    return None


_DUR_H = re.compile(r"(\d{1,2})\s*(?:Std\.?|Stunden?|h)\b\s*(?:(?:und\s*)?(\d{1,2})\s*(?:Min\.?|Minuten|min)\b)?", re.I)
_DUR_M = re.compile(r"(?<![\d:.])(\d{2,3})\s*(?:Min\.?|Minuten|min)\b", re.I)


def detect_duration(text: str) -> int | None:
    if m := _DUR_H.search(text):
        minutes = int(m[1]) * 60 + int(m[2] or 0)
        if 20 <= minutes <= 420:
            return minutes
    if m := _DUR_M.search(text):
        minutes = int(m[1])
        if 20 <= minutes <= 420:
            return minutes
    return None


def detect_from_list(text: str, options: list[str]) -> str | None:
    """First option found in text (options are matched case-insensitively as words)."""
    best = None
    for opt in options:
        m = re.search(rf"(?<![\wäöü]){re.escape(opt)}(?![\wäöü])", text, re.I)
        if m and (best is None or m.start() < best[0]):
            best = (m.start(), opt)
    return best[1] if best else None


def best_from_srcset(srcset: str) -> str | None:
    best, best_w = None, -1
    for part in srcset.split(","):
        bits = part.strip().split()
        if not bits:
            continue
        w = 0
        if len(bits) > 1:
            m = re.match(r"(\d+)", bits[1])
            w = int(m[1]) if m else 0
        if w >= best_w:
            best, best_w = bits[0], w
    return best


def pick_image(node: Tag, base: str) -> str | None:
    for img in node.find_all(["img", "source"]):
        for attr in ("data-src", "data-lazy-src", "data-original", "data-srcset", "srcset", "src"):
            val = img.get(attr)
            if not val:
                continue
            if "srcset" in attr:
                val = best_from_srcset(val)
            if not val or BAD_IMAGE.search(val):
                continue
            w = img.get("width")
            if w and str(w).isdigit() and int(w) < 60:
                continue
            return urljoin(base, val)
    for el in [node, *node.find_all(style=True)]:
        style = el.get("style") or ""
        m = re.search(r"url\(['\"]?([^'\")]+)['\"]?\)", style)
        if m and not BAD_IMAGE.search(m[1]):
            return urljoin(base, m[1])
    return None


def strip_date_time_noise(title: str, today: date) -> str:
    t = clean(title)
    # Remove trailing " - 13 Okt" / " – 13.10." and leading date/time chunks
    t = re.sub(rf"\s*[-–|·,]\s*(\d{{1,2}}\.?\s*({_MONTH_ALT})\.?|\d{{1,2}}\.\d{{1,2}}\.(\d{{2,4}})?)\s*$", "", t, flags=re.I)
    t = re.sub(rf"^(({_WD_ALT})\.?,?\s*)?(\d{{1,2}}\.\d{{1,2}}\.(\d{{2,4}})?|\d{{1,2}}\.?\s*({_MONTH_ALT})\.?)\s*[-–|·,]?\s*", "", t, flags=re.I)
    t = re.sub(r"^\d{1,2}[:.]\d{2}\s*(Uhr)?\s*[-–|·,]?\s*", "", t, flags=re.I)
    return t.strip(" -–|·,:")


def slug_title(url: str) -> str | None:
    m = re.search(r"/([a-z0-9][a-z0-9-]{2,})/?(?:[?#].*)?$", url or "")
    if not m:
        return None
    words = m[1].split("-")
    if words and re.fullmatch(r"[0-9a-f]{4,}|\d+", words[-1]):
        words = words[:-1]
    return " ".join(words).capitalize() if words else None


def _good_title(t: str) -> bool:
    return 2 <= len(t) <= 160 and not BAD_TITLE.match(t) and not re.fullmatch(r"[\d\s.:–\-/,]+(uhr)?", t, re.I)


def pick_title(card: Tag, page_url: str, title_re: re.Pattern | None, today: date) -> str | None:
    # 1. elements whose class says "title"
    for el in card.find_all(class_=re.compile(r"(^|[-_ ])(title|titel|headline|name)([-_ ]|$)", re.I)):
        if re.search(r"sub|over|pre|kicker|date|time|location|venue", " ".join(el.get("class", [])), re.I):
            continue
        t = strip_date_time_noise(el.get_text(" ", strip=True), today)
        if _good_title(t):
            return t
    # 2. headings
    for h in card.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]):
        t = strip_date_time_noise(h.get_text(" ", strip=True), today)
        if _good_title(t) and not find_dates(t, today):
            return t
    # 3. title links with short text
    if title_re:
        for a in card.find_all("a", href=True):
            if title_re.search(urljoin(page_url, a["href"])):
                t = strip_date_time_noise(a.get_text(" ", strip=True), today)
                if _good_title(t) and len(t) <= 120:
                    return t
    # 4. bold text
    for el in card.find_all(["strong", "b"]):
        t = strip_date_time_noise(el.get_text(" ", strip=True), today)
        if _good_title(t) and not find_dates(t, today):
            return t
    return None


def pick_subtitle(card: Tag, title: str | None) -> str | None:
    for el in card.find_all(class_=re.compile(r"sub|teaser|subline|author|composer|credits|byline|untertitel", re.I)):
        t = clean(el.get_text(" ", strip=True))
        if t and t != title and 2 < len(t) <= 220 and not (title and t in title):
            return t
    return None


def preceding_date(node: Tag, today: date, max_strings: int = 120) -> date | None:
    """Closest date that appears before node in document order (day headings etc.)."""
    buf = ""
    for i, s in enumerate(node.find_all_previous(string=True)):
        if i >= max_strings:
            break
        t = clean(str(s))
        if not t:
            continue
        buf = t + " " + buf
        found = find_dates(buf[:200], today)
        if found:
            return found[0][1]
    return None


def preceding_heading_text(node: Tag) -> str | None:
    h = node.find_previous(["h1", "h2", "h3", "h4"])
    return clean(h.get_text(" ", strip=True)) if h else None


def _strip_noise(soup: BeautifulSoup) -> None:
    for t in soup(["script", "style", "noscript", "svg", "template", "iframe"]):
        t.decompose()
    for t in soup.select("header nav, footer, [aria-hidden=true] nav"):
        t.decompose()


def make_soup(html: str, keep_scripts: bool = False) -> BeautifulSoup:
    soup = BeautifulSoup(html, PARSER)
    if not keep_scripts:
        _strip_noise(soup)
    return soup


# --------------------------------------------------------------------------- cards


def _occ_key(href: str, rx: re.Pattern) -> str | None:
    m = rx.search(href)
    if not m:
        return None
    return m.group(1) if m.groups() and m.group(1) else m.group(0)


def find_card(anchor: Tag, page_url: str, occ_rx: re.Pattern, own_key: str,
              time_guard: bool = True, max_len: int = 3000) -> Tag:
    """Largest ancestor that holds only this occurrence (and at most one start time)."""
    node = anchor
    while True:
        parent = node.parent
        if parent is None or not isinstance(parent, Tag) or parent.name in ("body", "html", "[document]", "main"):
            return node
        keys = set()
        for a in parent.find_all("a", href=True):
            k = _occ_key(urljoin(page_url, a["href"]), occ_rx)
            if k:
                keys.add(k)
        if len(keys - {own_key}) > 0:
            return node
        ptext = parent.get_text(" ", strip=True)
        if len(ptext) > max_len:
            return node
        if time_guard and count_start_times(ptext) > 1 and count_start_times(node.get_text(" ", strip=True)) >= 1:
            return node
        node = parent


def _time_attr(card: Tag) -> datetime | None:
    for t in card.find_all("time"):
        for attr in ("datetime", "content"):
            v = t.get(attr)
            if v:
                dt = parse_iso_datetime(v)
                if dt:
                    return dt
    for el in [card, *card.find_all(True)]:
        for k, v in el.attrs.items():
            if isinstance(v, str) and k.startswith(("data-", "content")) and re.match(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}", v):
                dt = parse_iso_datetime(v)
                if dt:
                    return dt
    return None


def extract_cards(html: str, page_url: str, venue: dict, today: date,
                  context_date: date | None = None) -> tuple[list[dict], dict]:
    """One event per occurrence anchor. Returns (events, stats)."""
    soup = make_soup(html)
    stats = {"anchors": 0, "cards": 0, "no_date": 0, "no_time": 0, "no_title": 0, "pattern": None}
    occ_patterns = venue["occ"] if isinstance(venue["occ"], list) else [venue["occ"]]
    title_rx = re.compile(venue["title_link"], re.I) if venue.get("title_link") else None
    url_dt_rx = re.compile(venue["date_from_url"]) if venue.get("date_from_url") else None

    anchors: list[tuple[Tag, str, str]] = []
    occ_rx = None
    for pat in occ_patterns:
        occ_rx = re.compile(pat, re.I)
        anchors = []
        for a in soup.find_all("a", href=True):
            href = urljoin(page_url, a["href"])
            k = _occ_key(href, occ_rx)
            if k:
                anchors.append((a, href, k))
        if anchors:
            stats["pattern"] = pat
            break
    stats["anchors"] = len(anchors)

    events = []
    seen_cards: set[int] = set()
    for a, href, key in anchors:
        card = find_card(a, page_url, occ_rx, key, time_guard=venue.get("time_guard", True))
        if id(card) in seen_cards:
            continue
        seen_cards.add(id(card))
        stats["cards"] += 1
        text = clean(card.get_text(" ", strip=True))

        d, t, end = None, None, None
        if url_dt_rx and (m := url_dt_rx.search(href)):
            g = [int(x) for x in m.groups()]
            try:
                d = date(g[0], g[1], g[2])
                if len(g) >= 5:
                    t = time(g[3], g[4])
            except ValueError:
                d = None
        if d is None and (dt := _time_attr(card)):
            d, t = dt.date(), dt.time()
        if d is None:
            d = first_date(text, today) or context_date or preceding_date(card, today)
        if t is None:
            hit = pick_start_time(text)
            if hit:
                t, end = hit["time"], hit["end"]
        if d is None:
            stats["no_date"] += 1
            continue
        if t is None and venue.get("require_time", True):
            stats["no_time"] += 1
            continue

        title = pick_title(card, page_url, title_rx, today)
        if not title and title_rx is None:
            title = strip_date_time_noise(a.get_text(" ", strip=True), today) or None
            if title and (len(title) > 120 or not _good_title(title)):
                title = None
        info_url = None
        if title_rx:
            for la in card.find_all("a", href=True):
                h = urljoin(page_url, la["href"])
                if title_rx.search(h):
                    info_url = urldefrag(h)[0]
                    break
        if not info_url and not TICKET_HREF.search(href) and not href.endswith(".ics") and "calendar" not in href:
            info_url = urldefrag(href)[0]
        if not title:
            title = slug_title(info_url or href)
        if not title:
            stats["no_title"] += 1
            continue

        ticket_url = None
        for la in card.find_all("a", href=True):
            h = urljoin(page_url, la["href"])
            if TICKET_HREF.search(h) and not h.endswith(".ics"):
                ticket_url = h
                break

        duration = None
        if t and end:
            mins = (datetime.combine(d, end) - datetime.combine(d, t)).seconds // 60
            duration = mins if 15 <= mins <= 420 else None
        duration = duration or detect_duration(text)

        events.append(make_event(
            venue=venue, title=title, d=d, t=t, page_url=page_url,
            subtitle=pick_subtitle(card, title),
            stage=detect_from_list(text, venue.get("stages", [])),
            genre=detect_from_list(text, venue.get("genres", [])) or venue.get("default_genre"),
            tags=detect_tags(text),
            status=detect_status(text),
            price=detect_price(text),
            duration=duration,
            image=pick_image(card, page_url),
            url=info_url or page_url,
            ticket_url=ticket_url,
            source="page",
        ))
    return events, stats


# --------------------------------------------------------------------------- cinemas


def _enclosing_link(node, stop: Tag) -> Tag | None:
    el = node.parent if isinstance(node, NavigableString) else node
    for _ in range(4):
        if el is None or el is stop:
            return None
        if el.name == "a" and el.get("href"):
            return el
        if el.name == "button" and (el.get("data-href") or el.get("data-url")):
            return el
        el = el.parent
    return None


def _screening_status(node, stop: Tag) -> str | None:
    el = node.parent if isinstance(node, NavigableString) else node
    for _ in range(4):
        if el is None or el is stop:
            break
        blob = " ".join([*el.get("class", []), el.get("title") or "", el.get("aria-label") or ""])
        st = detect_status(blob)
        if st:
            return st
        if re.search(r"soldout|sold-out|is-sold|ausverkauft", blob, re.I):
            return "sold_out"
        el = el.parent
    return None


def extract_screenings(html: str, page_url: str, venue: dict, today: date,
                       context_date: date | None = None) -> tuple[list[dict], dict]:
    """Cinema listings: one block per film, many times (optionally under date labels)."""
    soup = make_soup(html)
    title_rx = re.compile(venue["title_link"], re.I)
    stats = {"film_links": 0, "blocks": 0, "screenings": 0, "undated_times": 0}
    events = []
    seen_blocks: set[int] = set()
    for a in soup.find_all("a", href=True):
        href = urljoin(page_url, a["href"])
        key = _occ_key(href, title_rx)
        if not key:
            continue
        stats["film_links"] += 1
        block = find_card(a, page_url, title_rx, key, time_guard=False, max_len=6000)
        if id(block) in seen_blocks:
            continue
        seen_blocks.add(id(block))
        stats["blocks"] += 1

        title = pick_title(block, page_url, title_rx, today) or slug_title(href)
        if not title:
            continue
        image = pick_image(block, page_url)
        btext = clean(block.get_text(" ", strip=True))
        duration = detect_duration(btext)
        cur = context_date or preceding_date(block, today)

        strings = [s for s in block.find_all(string=True) if clean(str(s))]
        for i, s in enumerate(strings):
            txt = clean(str(s))
            if len(txt) > 40:
                continue
            ds = find_dates(txt, today)
            if ds and not find_times(txt):
                cur = ds[0][1]
                continue
            if ds:
                cur = ds[0][1]
            for hit in find_times(txt):
                if hit["excluded"]:
                    continue
                if cur is None:
                    stats["undated_times"] += 1
                    continue
                rest = txt[hit["end_pos"]:]
                nxt = clean(str(strings[i + 1])) if i + 1 < len(strings) else ""
                vm = VERSION_RE.match(rest) or VERSION_RE.match(nxt)
                version = vm[1].strip() if vm else None
                link = _enclosing_link(s, block)
                ticket = None
                if link is not None:
                    ticket = urljoin(page_url, link.get("href") or link.get("data-href") or link.get("data-url"))
                    if ticket.endswith("#") or ticket == page_url:
                        ticket = None
                status = _screening_status(s, block)
                events.append(make_event(
                    venue=venue, title=title, d=cur, t=hit["time"], page_url=page_url,
                    subtitle=None, stage=None, genre=venue.get("default_genre"),
                    tags=[version] if version else [], status=status, price=None,
                    duration=duration, image=image, url=urldefrag(href)[0],
                    ticket_url=ticket, source="page",
                ))
                stats["screenings"] += 1
    return events, stats


# --------------------------------------------------------------------------- JSON

_DT_KEY = re.compile(r"(start|begin|showtime|show_time|session|performance|datetime|date_time|eventdate|playtime)|^(date|time|when)$", re.I)
_DT_EXCL = re.compile(r"updat|creat|modif|publish|release|end|expir|valid|birth|sale|deadline|archiv", re.I)
_TITLE_KEYS = ("title", "name", "filmTitle", "movieTitle", "eventTitle", "eventName", "headline",
               "productionTitle", "showTitle", "originalTitle")
_URL_KEYS = ("url", "link", "href", "permalink", "detailUrl", "slug")
_TICKET_KEYS = ("bookingUrl", "ticketUrl", "ticketLink", "shopUrl", "checkoutUrl", "bookingLink", "deeplink")
_IMG_KEYS = ("image", "poster", "posterUrl", "imageUrl", "thumbnail", "picture", "cover", "heroImage", "still")


def _str_of(v) -> str | None:
    if isinstance(v, str):
        return v
    if isinstance(v, dict):
        for k in ("de", "de-DE", "value", "text", "name", "title", "url", "src"):
            if isinstance(v.get(k), str):
                return v[k]
        for k in ("fields", "file", "asset", "sys"):
            if isinstance(v.get(k), dict):
                s = _str_of(v[k])
                if s:
                    return s
    if isinstance(v, list) and v:
        return _str_of(v[0])
    return None


def _json_sold_out(d: dict) -> str | None:
    for k, v in d.items():
        kl = k.lower()
        if ("soldout" in kl or "sold_out" in kl or "ausverkauft" in kl) and v is True:
            return "sold_out"
        if kl in ("availability", "status", "state", "bookingstatus", "ticketstatus") and isinstance(v, str):
            st = detect_status(v) or ("sold_out" if re.search(r"soldout|sold_out", v, re.I) else None)
            if st:
                return st
        if kl in ("availableseats", "freeseats", "seatsavailable", "available") and v == 0:
            return "sold_out"
        if kl == "offers":
            for o in v if isinstance(v, list) else [v]:
                if isinstance(o, dict):
                    st = _json_sold_out(o)
                    if st:
                        return st
    return None


def harvest_json(payload, venue: dict, page_url: str, today: date, horizon: date) -> list[dict]:
    """Find objects that look like a dated performance/screening anywhere in a JSON tree."""
    out = []

    def lookup(chain: list[dict], keys) -> str | None:
        for d in reversed(chain):
            for k in keys:
                if k in d:
                    s = _str_of(d[k])
                    if s and s.strip():
                        return s.strip()
        return None

    def walk(node, chain: list[dict], depth: int):
        if depth > 40:
            return
        if isinstance(node, list):
            for item in node:
                walk(item, chain, depth + 1)
            return
        if not isinstance(node, dict):
            return
        new_chain = chain + [node]
        dt = None
        for k, v in node.items():
            if isinstance(v, str) and _DT_KEY.search(k) and not _DT_EXCL.search(k):
                dt = parse_iso_datetime(v)
                if dt:
                    break
        if dt and today - timedelta(days=1) <= dt.date() <= horizon and (dt.hour or dt.minute):
            wp = node.get("workPresented")
            title = _str_of(wp.get("name")) if isinstance(wp, dict) else None
            title = title or lookup(new_chain, _TITLE_KEYS)
            if title and 1 < len(title) < 200:
                url = lookup(new_chain, _URL_KEYS)
                if url and not url.startswith(("http", "/")):
                    url = None
                ticket = lookup([node], _TICKET_KEYS)
                image = lookup(new_chain, _IMG_KEYS)
                if image and image.startswith("//"):
                    image = "https:" + image
                status = None
                for d in reversed(new_chain[-2:]):
                    status = status or _json_sold_out(d)
                loc = node.get("location")
                stage = _str_of(loc.get("name")) if isinstance(loc, dict) else _str_of(node.get("auditorium") or node.get("screen") or node.get("room"))
                out.append(make_event(
                    venue=venue, title=clean(title), d=dt.date(), t=dt.time(), page_url=page_url,
                    subtitle=None, stage=clean(stage) if stage else None,
                    genre=venue.get("default_genre"), tags=[], status=status, price=None,
                    duration=None,
                    image=urljoin(page_url, image) if image and not BAD_IMAGE.search(image) else None,
                    url=urljoin(page_url, url) if url else page_url,
                    ticket_url=urljoin(page_url, ticket) if ticket else None,
                    source="json",
                ))
        for v in node.values():
            if isinstance(v, (dict, list)):
                walk(v, new_chain, depth + 1)

    walk(payload, [], 0)
    return out


def embedded_json(html: str) -> list:
    """JSON-LD blocks and Next.js __NEXT_DATA__ from raw HTML."""
    soup = BeautifulSoup(html, PARSER)
    out = []
    for s in soup.find_all("script"):
        typ = (s.get("type") or "").lower()
        if typ == "application/ld+json" or s.get("id") == "__NEXT_DATA__" or typ == "application/json":
            try:
                out.append(json.loads(s.string or s.get_text() or ""))
            except (json.JSONDecodeError, TypeError):
                continue
    return out


# --------------------------------------------------------------------------- schedule pages

_RANGE_RE = re.compile(
    r"(?<![\d.])(\d{1,2})\.(\d{1,2})\.(\d{2,4})?\s*(?:–|-|—|bis)\s*(\d{1,2})\.(\d{1,2})\.(\d{2,4})(?!\d)")
_WEEKLY_RE = re.compile(
    rf"\b({_WD_ALT})\.?(?:\s*(?:–|-|—|bis)\s*({_WD_ALT})\.?)?\s*:\s*((?:\d{{1,2}}[:.]\d{{2}}(?:\s*Uhr)?\s*(?:,|und|&|/)?\s*)+)",
    re.I)


def _year(y: str | None, fallback: int) -> int:
    if not y:
        return fallback
    y = int(y)
    return y + 2000 if y < 100 else y


def parse_schedule_page(html: str, page_url: str, venue: dict, today: date) -> tuple[list[dict], dict]:
    """Show pages that state 'DD.MM. bis DD.MM.YY' plus weekly times, or single dates + 'Beginn'."""
    soup = make_soup(html, keep_scripts=True)
    meta = {m.get("property") or m.get("name"): m.get("content") for m in soup.find_all("meta")}
    _strip_noise(soup)
    body = soup.find("main") or soup.find("article") or soup.body or soup
    lines = [clean(x) for x in body.get_text("\n").split("\n")]
    lines = [x for x in lines if x]
    text = "\n".join(lines)
    stats = {"mode": None, "dates": 0}

    title = meta.get("og:title") or (soup.find("h1").get_text(" ", strip=True) if soup.find("h1") else None)
    if title:
        title = re.split(r"\s+[|–-]\s+(Deutsches Theater|DT München)", title)[0].strip()
    if not title:
        return [], stats
    image = meta.get("og:image")
    if not image:
        image = pick_image(body, page_url)
    desc = meta.get("og:description") or meta.get("description")
    stage = None
    if m := re.search(r"\bOrt:\s*([^\n]+)", text):
        stage = m[1].strip()
    stage = stage or detect_from_list(text, venue.get("stages", []))
    duration = None
    if m := re.search(r"(Dauer|Spieldauer)[^\n]*\n?[^\n]*", text, re.I):
        duration = detect_duration(m[0])
    price = None
    if m := re.search(r"[^\n]*(ab\s*\d{1,3}(?:[,.]\d{2})?\s*€)[^\n]*", text, re.I):
        price = detect_price(m[0])
    ticket = None
    for a in body.find_all("a", href=True):
        if TICKET_HREF.search(a["href"]):
            ticket = urljoin(page_url, a["href"])
            break
    genre = detect_from_list(text, venue.get("genres", [])) or venue.get("default_genre")
    global_time = None
    if m := re.search(r"(Vorstellungsbeginn|Beginn|Showbeginn|Konzertbeginn)\s*:?\s*(\d{1,2})[:.](\d{2})", text, re.I):
        global_time = time(int(m[2]), int(m[3]))

    occurrences: dict[date, set[time]] = {}

    rng = _RANGE_RE.search(text)
    weekly: dict[int, list[time]] = {}
    for m in _WEEKLY_RE.finditer(text):
        a = WEEKDAYS[m[1].lower()]
        b = WEEKDAYS[m[2].lower()] if m[2] else a
        days = list(range(a, b + 1)) if a <= b else list(range(a, 7)) + list(range(0, b + 1))
        times = [time(int(h), int(mi)) for h, mi in re.findall(r"(\d{1,2})[:.](\d{2})", m[3])]
        for wd in days:
            weekly.setdefault(wd, [])
            weekly[wd].extend(t for t in times if t not in weekly[wd])

    if rng and weekly:
        end_y = _year(rng[6], today.year)
        end = date(end_y, int(rng[5]), int(rng[4]))
        start_y = _year(rng[3], end_y if int(rng[2]) <= int(rng[5]) else end_y - 1)
        start = date(start_y, int(rng[2]), int(rng[1]))
        if (end - start).days <= 200:
            stats["mode"] = "range+weekly"
            d = start
            while d <= end:
                for t in weekly.get(d.weekday(), []):
                    occurrences.setdefault(d, set()).add(t)
                d += timedelta(days=1)
    else:
        # explicit dates, each with a time on the same line or the global start time
        for line in lines:
            if _RANGE_RE.search(line):
                continue
            for _, d in find_dates(line, today):
                hit = pick_start_time(line)
                t = hit["time"] if hit else global_time
                if t:
                    occurrences.setdefault(d, set()).add(t)
        stats["mode"] = "dates" if occurrences else "none"

    # Premiere / preview markers on specific dates
    special: dict[date, str] = {}
    for line in lines:
        lm = re.match(r"(Premiere|Preview|Voraufführung|Dernière|Derniere)\b", line, re.I)
        if lm:
            d = first_date(line, today)
            if d:
                special[d] = "Premiere" if lm[1].lower() == "premiere" else lm[1].capitalize()

    events = []
    for d, times in sorted(occurrences.items()):
        if d < today:
            continue
        for t in sorted(times):
            tags = [special[d]] if d in special else []
            ev = make_event(
                venue=venue, title=clean(title), d=d, t=t, page_url=page_url,
                subtitle=None, stage=stage, genre=genre, tags=tags, status=None,
                price=price, duration=duration, image=urljoin(page_url, image) if image else None,
                url=urldefrag(page_url)[0], ticket_url=ticket, source="schedule",
            )
            ev["description"] = clean(desc)[:400] if desc else None
            ev["note"] = "derived"
            events.append(ev)
    stats["dates"] = len(events)
    return events, stats


# --------------------------------------------------------------------------- record


def make_event(*, venue: dict, title: str, d: date, t: time | None, page_url: str, subtitle, stage, genre,
               tags, status, price, duration, image, url, ticket_url, source) -> dict:
    start = to_iso(d, t)
    ident = hashlib.md5(f"{venue['id']}|{start}|{title.lower()}".encode()).hexdigest()[:12]
    return {
        "id": ident,
        "venue_id": venue["id"],
        "title": title,
        "subtitle": subtitle,
        "start": start,
        "time_tbd": t is None,
        "stage": stage,
        "genre": genre,
        "tags": [x for x in (tags or []) if x],
        "status": status or "unknown",
        "price": price,
        "duration_min": duration,
        "image": image,
        "url": url or page_url,
        "ticket_url": ticket_url,
        "description": None,
        "source": source,
    }


def norm_title(title: str) -> str:
    t = title.lower()
    t = re.sub(r"\((omu|ov|omeu|df|engl\.? ?ov)\)", "", t)
    return re.sub(r"[^a-z0-9äöüß]+", "", t)


def merge_events(events: list[dict]) -> list[dict]:
    """De-duplicate on (venue, start, normalised title), keeping the richest record."""
    best: dict[tuple, dict] = {}
    for e in events:
        key = (e["venue_id"], e["start"][:16], norm_title(e["title"]))
        cur = best.get(key)
        if cur is None:
            best[key] = dict(e)
            continue
        for k, v in e.items():
            if cur.get(k) in (None, "", [], "unknown") and v not in (None, "", [], "unknown"):
                cur[k] = v
        cur["tags"] = sorted(set(cur.get("tags") or []) | set(e.get("tags") or []))
    return sorted(best.values(), key=lambda x: (x["start"], x["venue_id"], x["title"]))
