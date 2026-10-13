"""Venue definitions. Edit this file to fix a URL or a link pattern.

Keys
  id, name, short, category, color   - shown on the site
  mode        "cards" (one card per performance), "screenings" (cinema: film blocks with
              many times) or "schedule" (show pages with a run + weekly pattern)
  start       listing pages to open
  occ         regex(es) on link hrefs that identify ONE performance (first group = unique key).
              A list is tried in order; the first pattern that matches anything is used.
  title_link  regex for links to the production / film page (used for title and info link)
  date_from_url  regex with (year, month, day, hour, minute) groups, if the URL carries the date
  actions     what the browser does on each start page:
              {"load_more": N}        click "Mehr laden" up to N times
              {"next": regex, "max": N}  click a "next month" control and snapshot each month
              {"follow": regex, "max": N} follow pagination links matching regex
              {"day_tabs": N}         click day tabs ("Heute 13.10.", "Mi 14.10.") and snapshot each
  show_links  (schedule mode) regex for show pages linked from the start pages
  json        also harvest JSON (API responses, JSON-LD, __NEXT_DATA__)
  stages / genres  words to look for in a card
"""

VENUES = [
    {
        "id": "residenztheater",
        "name": "Residenztheater",
        "short": "Resi",
        "category": "theatre",
        "color": "#b0182e",
        "mode": "cards",
        "start": ["https://www.residenztheater.de/spielplan"],
        "occ": [
            r"calendarics\.ics\?.*?activity(?:%5D|\])?=(\d+)",
            r"rth\.webshop/webticket/shop\?.*?event=(\d+)",
        ],
        "title_link": r"residenztheater\.de/stuecke/detail/[a-z0-9-]+",
        "actions": [{"follow": r"residenztheater\.de/spielplan\?.*month=\d{4}-\d{2}", "max": 13}],
        "stages": ["Cuvilliéstheater", "Marstall", "Residenztheater", "Zwischendeck", "Plateau", "Gastspiel"],
        "genres": ["Lesung", "Gespräch", "Konzert", "Liederabend", "Tanz", "Performance"],
        "default_genre": "Schauspiel",
    },
    {
        "id": "kammerspiele",
        "name": "Münchner Kammerspiele",
        "short": "MK",
        "category": "theatre",
        "color": "#1f4fa3",
        "mode": "cards",
        "start": ["https://www.muenchner-kammerspiele.de/de/programm"],
        "occ": [
            r"/programm/\d+-[^/?#]+/(\d+)\.ics",
            r"/programm/\d+-[^/?#.]+\?activity=(\d+)",
        ],
        "title_link": r"muenchner-kammerspiele\.de/de/programm/\d+-[^/?#.]+(\?activity=\d+)?$",
        "actions": [{"load_more": 30}],
        "stages": ["Schauspielhaus", "Therese-Giehse-Halle", "Werkraum", "Kammer 1", "Kammer 2", "Kammer 3",
                   "Habibi Kiosk", "Neues Haus", "Foyer"],
        "genres": ["Offene Probe", "Lesung", "Konzert", "Party", "Gespräch", "Performance", "Tanz"],
        "default_genre": "Schauspiel",
    },
    {
        "id": "volkstheater",
        "name": "Münchner Volkstheater",
        "short": "VT",
        "category": "theatre",
        "color": "#e0601b",
        "mode": "cards",
        "start": ["https://www.muenchner-volkstheater.de/programm/spielplan"],
        "occ": [r"muenchner-volkstheater\.de/programm/(?!spielplan)([a-z0-9-]+/[a-z0-9-]+)/?$"],
        "title_link": r"muenchner-volkstheater\.de/programm/(?!spielplan)[a-z0-9-]+/[a-z0-9-]+/?$",
        "actions": [{"load_more": 20}],
        "stages": ["Bühne 1", "Bühne 2", "Bühne 3", "Foyer", "Gastspiel"],
        "genres": ["Comedy", "Lesung", "Konzert", "Buchpräsentation", "Kabarett", "Extra"],
        "default_genre": "Schauspiel",
    },
    {
        "id": "deutsches-theater",
        "name": "Deutsches Theater",
        "short": "DT",
        "category": "theatre",
        "color": "#7a2d8c",
        "mode": "schedule",
        "start": ["https://www.deutsches-theater.de/programm/", "https://www.deutsches-theater.de/"],
        "show_links": r"^https://www\.deutsches-theater\.de/(?!programm|kontakt|impressum|datenschutz|agb|presse|"
                      r"ueber-uns|jobs|newsletter|gutschein|anfahrt|barrierefrei|faq|vermietung|gastro|wp-|tag/|"
                      r"category/|en/|kartenkauf|service|theater|haus|location)[a-z0-9-]+/?$",
        "actions": [{"load_more": 15}],
        "stages": ["Theatersaal", "Silbersaal", "Ballsaal"],
        "genres": ["Musical", "Konzert", "Tanztheater", "Show", "Ballett", "Comedy", "Kabarett", "Oper"],
        "default_genre": "Musical",
    },
    {
        "id": "isarphilharmonie",
        "name": "Isarphilharmonie",
        "short": "IP",
        "category": "concert",
        "color": "#0f7b6c",
        "mode": "cards",
        "start": ["https://www.gasteig.de/veranstaltungen/?room=isarphilharmonie"],
        "occ": [r"gasteig\.de/veranstaltungen/([a-z0-9][a-z0-9-]*)/?$"],
        "title_link": r"gasteig\.de/veranstaltungen/[a-z0-9][a-z0-9-]*/?$",
        "actions": [{"load_more": 40}],
        "stages": ["Isarphilharmonie"],
        "genres": ["Klassik", "Jazz", "Pop", "Rock", "Weltmusik", "Lesung", "Podcast", "Comedy", "Kabarett",
                   "Filmmusik", "Chor", "Kinder", "Familie"],
        "default_genre": "Konzert",
    },
    {
        "id": "bayerische-staatsoper",
        "name": "Bayerische Staatsoper",
        "short": "BSO",
        "category": "opera",
        "color": "#8a6d1d",
        "mode": "cards",
        "start": ["https://www.staatsoper.de/spielplan"],
        "occ": [r"staatsoper\.de/stuecke/[^/]+/(\d{4}-\d{2}-\d{2}-\d{4}-\d+)"],
        "date_from_url": r"/(\d{4})-(\d{2})-(\d{2})-(\d{2})(\d{2})-\d+",
        "title_link": None,
        "time_guard": False,
        "actions": [{"next": r"nächsten Monat|naechsten Monat|next month", "max": 11}],
        "stages": ["Nationaltheater", "Prinzregententheater", "Cuvilliés-Theater", "Cuvilliéstheater",
                   "Allerheiligen Hofkirche", "Große Probebühne", "Capriccio-Saal", "Königssaal", "Foyer",
                   "Freunde-Foyer", "Parkettgarderobe"],
        "genres": ["Oper", "Ballett", "Konzert", "Liederabend", "Kind&Co", "Extra", "Festspiele"],
        "default_genre": "Oper",
    },
    {
        "id": "museum-lichtspiele",
        "name": "Museum Lichtspiele",
        "short": "ML",
        "category": "cinema",
        "color": "#3b3f8f",
        "mode": "screenings",
        "start": ["https://www.museum-lichtspiele.de/programm?filter=all",
                  "https://www.museum-lichtspiele.de/home"],
        "title_link": r"museum-lichtspiele\.de/(?:barrierefrei/film)?detail/(\d+)/",
        "actions": [{"day_tabs": 40}],
        "json": True,
        "default_genre": "Film",
    },
    {
        "id": "city-kino-atelier",
        "name": "City Kinos & Atelier",
        "short": "City",
        "category": "cinema",
        "color": "#2f7d32",
        "mode": "screenings",
        "start": ["https://www.city-kinos.de/filme"],
        "title_link": r"city-kinos\.de/filme/([a-z0-9-]+)/?$",
        "actions": [{"day_tabs": 40}],
        "json": True,
        "default_genre": "Film",
    },
]
