"""Offline tests for scripts/extract.py using small pages shaped like the real listings.

Run:  python -m pytest tests  (or: python tests/test_extract.py)
"""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from extract import (extract_cards, extract_screenings, find_dates, find_times,  # noqa: E402
                     harvest_json, parse_schedule_page, pick_start_time)
from venues import VENUES  # noqa: E402

TODAY = date(2026, 10, 13)
V = {v["id"]: v for v in VENUES}


def by_title(events):
    return {e["title"]: e for e in events}


def test_dates_and_times():
    assert find_dates("Di 13.10.", TODAY)[0][1] == date(2026, 10, 13)
    assert find_dates("Do, 15. Oktober 2026", TODAY)[0][1] == date(2026, 10, 15)
    assert find_dates("Mi. 14 Okt", TODAY)[0][1] == date(2026, 10, 14)
    assert find_dates("So 13 Jun", TODAY)[0][1] == date(2027, 6, 13)
    assert find_dates("16.10.2026 19.00 Uhr", TODAY)[0][1] == date(2026, 10, 16)
    assert pick_start_time("19.30–22.50 Uhr")["end"].hour == 22
    assert pick_start_time("Einlass 18:30 Beginn 19:30")["time"].hour == 19
    assert not find_times("13.10. Schauspielhaus")
    assert pick_start_time("Di 13.10. 19:00")["time"].hour == 19


RESI = """
<main><section class="day"><h2>Di 13 Okt</h2>
 <article class="event">
  <img src="/media/_processed_/0/8/csm_Spielplan_Dreigroschenoper.jpg" alt="">
  <h3><a href="/stuecke/detail/die-dreigroschenoper">Die Dreigroschenoper <span class="sr">- 13 Okt</span></a></h3>
  <p>19.30–22.50 Uhr · Residenztheater</p><p>Ausverkauft · ggf. Restkarten an der Abendkasse</p>
  <p>29 bis 74 € · Preise J</p>
  <a href="/calendarics.ics?tx_sfculture_activitiescalendarics%5Baction%5D=calendarics&tx_sfculture_activitiescalendarics%5Bactivity%5D=9087&cHash=x">Termin speichern</a>
 </article>
 <article class="event">
  <img src="/resiworld/_processed_/2/2/csm_Hasters.jpeg">
  <h3><a href="/stuecke/detail/anti-opfer">Alice Hasters: Anti Opfer</a></h3>
  <p>Lesung &amp; Gespräch</p><p>20.00 Uhr · Marstall</p><p>20 €</p>
  <a href="https://tickets.staatstheater.bayern/rth.webshop/webticket/shop?event=43121">Tickets</a>
  <a href="/calendarics.ics?tx_sfculture_activitiescalendarics%5Bactivity%5D=9166&cHash=y">Termin speichern</a>
 </article>
</section>
<section class="day"><h2>Do 15 Okt</h2>
 <article class="event"><h3><a href="/stuecke/detail/cabaret">Cabaret</a></h3>
  <p>19.30–22.30 Uhr · Residenztheater</p><p>WITH ENGLISH SURTITLES</p>
  <a href="https://tickets.staatstheater.bayern/rth.webshop/webticket/shop?event=43099">Tickets</a>
  <a href="/calendarics.ics?tx_sfculture_activitiescalendarics%5Bactivity%5D=9079">Termin speichern</a></article>
 <article class="event"><h3><a href="/stuecke/detail/bernarda-albas-haus">Bernarda Albas Haus</a></h3>
  <p>19.30–20.50 Uhr · Cuvilliéstheater</p>
  <a href="/calendarics.ics?tx_sfculture_activitiescalendarics%5Bactivity%5D=9069">Termin speichern</a></article>
</section></main>"""


def test_residenztheater():
    evs, st = extract_cards(RESI, "https://www.residenztheater.de/spielplan", V["residenztheater"], TODAY)
    t = by_title(evs)
    assert len(evs) == 4, (st, [e["title"] for e in evs])
    d = t["Die Dreigroschenoper"]
    assert d["start"].startswith("2026-10-13T19:30")
    assert d["status"] == "sold_out" and d["duration_min"] == 200 and d["stage"] == "Residenztheater"
    assert d["price"] == "29–74 €" and d["image"].endswith("Dreigroschenoper.jpg")
    assert d["url"] == "https://www.residenztheater.de/stuecke/detail/die-dreigroschenoper"
    assert t["Alice Hasters: Anti Opfer"]["stage"] == "Marstall"
    assert "rth.webshop" in t["Alice Hasters: Anti Opfer"]["ticket_url"]
    assert t["Cabaret"]["start"].startswith("2026-10-15T19:30")
    assert "English surtitles" in t["Cabaret"]["tags"]
    assert t["Bernarda Albas Haus"]["stage"] == "Cuvilliéstheater"


BSO = """
<main><ul class="list">
<li><a class="activity" href="/stuecke/ariadne-auf-naxos/2026-10-16-1900-16111">
  <div class="date">16.10.2026</div><div class="time">19.00 Uhr</div><div class="loc">Nationaltheater</div>
  <h3 class="activity__title">ARIADNE AUF NAXOS</h3><p class="activity__subtitle">Richard Strauss</p><span>Oper</span></a>
  <a href="https://tickets.staatstheater.bayern/bso.webshop/webticket/shop?language=de&event=41777">Tickets</a>
  <a href="/stuecke/ariadne-auf-naxos/2026-10-16-1900-16111/calendar.ics">ics</a></li>
<li><a href="/stuecke/kinderfuehrung-durch-das-nationaltheater-abenteuer-oper/2026-10-17-1400-16647">
  <div>17.10.2026</div><div>14.00 Uhr</div><div>Freunde-Foyer</div><h3>Kinderführung „Abenteuer Oper“</h3><span>Extra</span>
  <span>ausverkauft</span></a></li>
<li><a href="/stuecke/common-ground/2026-10-17-1930-16112"><div>17.10.2026</div><div>19.30 Uhr</div>
  <div>Nationaltheater</div><h3>COMMON GROUND</h3><p>Ekman, Inger, Kylián</p><span>Ballett</span><span>Letzte Tickets</span></a></li>
</ul></main>"""


def test_staatsoper():
    evs, st = extract_cards(BSO, "https://www.staatsoper.de/spielplan", V["bayerische-staatsoper"], TODAY)
    t = by_title(evs)
    assert len(evs) == 3, (st, list(t))
    a = t["ARIADNE AUF NAXOS"]
    assert a["start"].startswith("2026-10-16T19:00") and a["genre"] == "Oper" and a["subtitle"] == "Richard Strauss"
    assert a["ticket_url"].endswith("event=41777") and a["stage"] == "Nationaltheater"
    assert t["Kinderführung „Abenteuer Oper“"]["status"] == "sold_out"
    assert t["COMMON GROUND"]["status"] == "few" and t["COMMON GROUND"]["genre"] == "Ballett"


VOLKS = """
<main><h2>Oktober</h2>
<div class="row"><div class="date">Di 13 Okt 2026</div><div class="time">20:00 Uhr</div><div>Bühne 2</div>
 <a href="/programm/schauspiel/i-wanna-contact-living-das-gespenstische-von-canterville">I WANNA CONTACT THE LIVING</a>
 <a href="https://tickets.muenchenticket.net/shop/215/link/event/450012">Karten</a></div>
<div class="row"><div class="date">Mi 14 Okt</div><div class="time">20:00 Uhr</div><div>Bühne 2</div>
 <a href="/programm/schauspiel/i-wanna-contact-living-das-gespenstische-von-canterville">I WANNA CONTACT THE LIVING</a>
 <a href="https://tickets.muenchenticket.net/shop/215/link/event/450013">Karten</a></div>
<div class="row"><div class="date">Fr 16 Okt</div><div class="time">19:30 Uhr</div><div>Bühne 1</div>
 <a href="/programm/schauspiel/die-geierwally">DIE GEIERWALLY</a><span>Ausverkauft</span></div>
<div class="row"><div class="date">Sa 17 Okt</div><div class="time">19:30 Uhr</div><div>Bühne 1</div>
 <a href="/programm/schauspiel/der-blinde-passagier">Der blinde Passagier</a><span>Ausfall</span> Entfällt krankheitsbedingt.</div>
<div class="row"><div class="date">Sa 17 Okt</div><div class="time">19:30 Uhr</div><div>Bühne 1</div>
 <a href="/programm/schauspiel/echtzeitalter">Echtzeitalter</a> ERSATZVORSTELLUNG
 <a href="https://tickets.muenchenticket.net/shop/215/link/event/450011">Karten</a></div>
</main>"""


def test_volkstheater():
    evs, st = extract_cards(VOLKS, "https://www.muenchner-volkstheater.de/programm/spielplan", V["volkstheater"], TODAY)
    assert len(evs) == 5, (st, [(e["title"], e["start"]) for e in evs])
    t = {(e["title"], e["start"][:10]): e for e in evs}
    assert t[("I WANNA CONTACT THE LIVING", "2026-10-14")]["ticket_url"].endswith("450013")
    assert t[("DIE GEIERWALLY", "2026-10-16")]["status"] == "sold_out"
    assert t[("Der blinde Passagier", "2026-10-17")]["status"] == "cancelled"
    assert t[("Echtzeitalter", "2026-10-17")]["status"] == "unknown"


GASTEIG = """
<main><h1>229 Veranstaltungen gefunden</h1><div class="grid">
<div class="card"><a href="/veranstaltungen/1-jugendkonzert/"><img data-src="/media/jugend.jpg" src="data:image/gif;base64,xx"></a>
 <span class="tag">Klassik</span><p>Do, 15. Oktober 2026</p><p>18:30</p><h3><a href="/veranstaltungen/1-jugendkonzert/">1. Jugendkonzert</a></h3>
 <p class="subline">Münchner Philharmoniker: Schostakowitsch / Zimmermann / Ravel</p></div>
<div class="card"><a href="/veranstaltungen/jeremias-ensemble/"><img src="/media/jeremias.jpg"></a>
 <span class="tag">Pop</span><p>Sa, 17. Oktober 2026</p><p>20:00</p><h3><a href="/veranstaltungen/jeremias-ensemble/">Jeremias &amp; Ensemble</a></h3><span>Ausverkauft</span></div>
</div><a href="/veranstaltungen/?categories=musik">Musik</a></main>"""


def test_gasteig():
    evs, st = extract_cards(GASTEIG, "https://www.gasteig.de/veranstaltungen/?room=isarphilharmonie", V["isarphilharmonie"], TODAY)
    t = by_title(evs)
    assert len(evs) == 2, st
    assert t["1. Jugendkonzert"]["image"] == "https://www.gasteig.de/media/jugend.jpg"
    assert t["1. Jugendkonzert"]["genre"] == "Klassik"
    assert t["Jeremias & Ensemble"]["status"] == "sold_out"


KAMMER = """
<main><div class="day"><h3>Mi 14.10.</h3>
<div class="item"><span>19:00</span><span>Therese-Giehse-Halle</span>
 <a href="/de/programm/51761-munchner-verkehr">Offene Probe „Münchner Verkehr“</a><span>Ausverkauft</span>
 <a href="/de/programm/51761-munchner-verkehr/52740.ics">Kalender</a></div>
<div class="item"><span>20:00</span><span>Schauspielhaus</span>
 <a href="/de/programm/52879-suchers-leidenschaften-odon-von-horvath?activity=52881">Suchers Leidenschaften: Ödön von Horváth</a>
 <a href="/de/programm/52879-suchers-leidenschaften-odon-von-horvath/52881.ics">Kalender</a></div>
</div><div class="day"><h3>Fr 16.10.</h3>
<div class="item"><span>20:00</span><span>Therese-Giehse-Halle</span><span>Premiere</span>
 <a href="/de/programm/51761-munchner-verkehr?activity=53278">(Münchner) Verkehr</a><span>Wenige Tickets</span>
 <a href="/de/programm/51761-munchner-verkehr/53278.ics">Kalender</a></div></div></main>"""


def test_kammerspiele():
    evs, st = extract_cards(KAMMER, "https://www.muenchner-kammerspiele.de/de/programm", V["kammerspiele"], TODAY)
    t = by_title(evs)
    assert len(evs) == 3, (st, list(t))
    assert t["Offene Probe „Münchner Verkehr“"]["start"].startswith("2026-10-14T19:00")
    assert t["Offene Probe „Münchner Verkehr“"]["genre"] == "Offene Probe"
    v = t["(Münchner) Verkehr"]
    assert v["start"].startswith("2026-10-16T20:00") and v["status"] == "few" and "Premiere" in v["tags"]
    assert v["url"].endswith("?activity=53278")


CITY = """
<main><div class="tabs"><button>Heute 13.10.</button><button>Mi 14.10.</button></div>
<div class="film"><a href="/filme/digger"><img src="https://images.ctfassets.net/x/Digger.jpeg"></a>
 <h3><a href="/filme/digger">Digger</a></h3><p>Drama, 120 Min.</p>
 <div class="times"><a href="https://booking.yorck.de/x/1"><span>14:45</span><span>DF</span></a>
 <a class="sold-out" href="https://booking.yorck.de/x/2"><span>17:15</span><span>OmU</span></a></div></div>
<div class="film"><h3><a href="/filme/the-social-reckoning">The Social Reckoning</a></h3>
 <div class="times"><button>20:15OmU</button></div></div></main>"""


def test_city_screenings():
    evs, st = extract_screenings(CITY, "https://www.city-kinos.de/filme", V["city-kino-atelier"], TODAY,
                                 context_date=date(2026, 10, 14))
    assert len(evs) == 3, (st, [(e["title"], e["start"]) for e in evs])
    d = [e for e in evs if e["title"] == "Digger"]
    assert d[0]["start"].startswith("2026-10-14T14:45") and d[0]["tags"] == ["DF"]
    assert d[1]["status"] == "sold_out" and d[1]["ticket_url"].endswith("/2")
    assert d[0]["image"].endswith("Digger.jpeg") and d[0]["duration_min"] == 120
    s = [e for e in evs if e["title"] == "The Social Reckoning"][0]
    assert s["start"].startswith("2026-10-14T20:15") and s["tags"] == ["OmU"]


MUSEUM = """
<main><h2>Dienstag, 13.10.</h2>
<div class="film"><img src="https://cineprog.de/images/Breite_400px_RGB/p_126254.jpg">
 <a href="/detail/126254/Verity%20%28OV%29"><h4>Verity (OV)</h4></a>
 <a href="/ticket?l=kinoheld&showId=3674086795">20:30</a></div>
<div class="film"><a href="/detail/125195/Forgotten%20Island%20%28OV%29"><h4>Forgotten Island (OV)</h4></a>
 <a href="/ticket?l=kinoheld&showId=1">14:00</a><a href="/ticket?l=kinoheld&showId=2">16:00</a>
 <span>Mi 14.10.</span><a href="/ticket?l=kinoheld&showId=3">16:00</a></div></main>"""


def test_museum_screenings():
    evs, st = extract_screenings(MUSEUM, "https://www.museum-lichtspiele.de/programm?filter=all",
                                 V["museum-lichtspiele"], TODAY)
    assert len(evs) == 4, (st, [(e["title"], e["start"]) for e in evs])
    f = sorted((e["start"][:16] for e in evs if e["title"] == "Forgotten Island (OV)"))
    assert f == ["2026-10-13T14:00", "2026-10-13T16:00", "2026-10-14T16:00"]


DT_SHOW = """
<html><head><meta property="og:title" content="Disney Der Glöckner von Notre Dame - Deutsches Theater München">
<meta property="og:image" content="https://www.deutsches-theater.de/wp-content/uploads/gloeckner.png"></head>
<body><main><h1>Disney Der Glöckner von Notre Dame</h1><p>07.10. bis 08.11.26</p>
<p>Preview: Mittwoch, 07.10.26</p><p>Premiere: Donnerstag, 08.10.26</p>
<p>Dienstag–Freitag: 19:30 Uhr</p><p>Samstag: 14:30 und 19:30 Uhr</p><p>Sonntag: 14:00 Uhr</p>
<p>Ort: Theatersaal</p><p>Tickets ab 39,90 €</p>
<a href="https://tickets.muenchenticket.net/shop/214/link/category/35886">Tickets</a></main></body></html>"""

DT_SINGLE = """
<html><head><meta property="og:title" content="KISS Forever Band"></head><body><main>
<h1>KISS Forever Band</h1><p>02.11.26</p><p>Vorstellungsbeginn: 19:30 Uhr</p>
<p>Einlass: eine Stunde vor Vorstellungsbeginn</p><p>Ort: Theatersaal</p><p>Dauer: 1 Stunde 50 Minuten ohne Pause</p>
<p>ab 29,00 €</p></main></body></html>"""


def test_deutsches_theater():
    evs, st = parse_schedule_page(DT_SHOW, "https://www.deutsches-theater.de/disney-der-gloeckner-von-notre-dame/",
                                  V["deutsches-theater"], TODAY)
    starts = [e["start"][:16] for e in evs]
    assert "2026-10-13T19:30" in starts and "2026-10-17T14:30" in starts and "2026-10-18T14:00" in starts
    assert not any(s.startswith("2026-10-19") for s in starts)  # Monday dark
    assert starts[-1].startswith("2026-11-08")
    assert evs[0]["title"] == "Disney Der Glöckner von Notre Dame" and evs[0]["stage"] == "Theatersaal"
    k, _ = parse_schedule_page(DT_SINGLE, "https://www.deutsches-theater.de/kiss-forever-band/", V["deutsches-theater"], TODAY)
    assert [e["start"][:16] for e in k] == ["2026-11-02T19:30"]
    assert k[0]["duration_min"] == 110 and k[0]["price"] == "ab 29 €"


def test_json_harvest():
    payload = {"props": {"pageProps": {"movies": [
        {"title": "Digger", "poster": {"url": "//images.ctfassets.net/p.jpg"},
         "sessions": [{"startTime": "2026-10-14T18:15:00+02:00", "auditorium": "Atelier", "soldOut": True},
                      {"startTime": "2026-10-14T20:30:00+02:00", "auditorium": "City 1"}]}]}}}
    evs = harvest_json(payload, V["city-kino-atelier"], "https://www.city-kinos.de/filme", TODAY, date(2027, 12, 1))
    assert len(evs) == 2 and evs[0]["status"] == "sold_out" and evs[0]["stage"] == "Atelier"
    assert evs[0]["image"] == "https://images.ctfassets.net/p.jpg"


if __name__ == "__main__":
    failures = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("ok  ", name)
            except AssertionError as exc:
                failures += 1
                print("FAIL", name, exc)
    sys.exit(1 if failures else 0)
