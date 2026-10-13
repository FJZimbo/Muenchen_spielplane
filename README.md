# München Spielplan

A static page listing theatre, opera, concert and cinema programmes for Munich in one place.
It reads `data/events.json`, which a scraper refreshes every day.

## What's included

- **Theatre:** Residenztheater, Münchner Kammerspiele, Münchner Volkstheater, Deutsches Theater
- **Concert:** Isarphilharmonie
- **Opera:** Bayerische Staatsoper
- **Cinema:** Museum Lichtspiele, City Kino Atelier (all screenings)

## Hosting (free, GitHub Pages)

1. Create a new GitHub repository and push this folder to it.
2. In the repository, go to **Settings → Pages**, choose *Deploy from a branch*, select `main` and `/ (root)`.
3. Go to **Actions**, open *Update programme* and click **Run workflow** once to fill the data.
4. The site is then live at `https://<your-user>.github.io/<repo>/` and refreshes daily at about 06:15 Berlin time.

## Before the first run: check the scraper

The venue URLs and the parsing logic in `scripts/scrape.py` are a starting point and have **not yet been
verified against the live websites**. Please:

1. Open each URL in `VENUES` and confirm it shows the programme. Correct any that have moved.
2. Run `python scripts/scrape.py` locally. It prints how many events it found per venue.
3. For any venue that returns 0 events, look at the page source. If the page has no schema.org `Event`
   data, add CSS selectors to `SELECTORS` in the script.
4. Check each venue's terms of use. Some sites restrict automated access. If one does, drop it from
   `VENUES` or ask the venue for a feed or a list you can paste in.

The scraper keeps the previous data if a run finds nothing, so a broken site won't empty the page.

## Running locally

```bash
pip install -r requirements.txt
python scripts/scrape.py
python -m http.server 8000     # then open http://localhost:8000
```

Opening `index.html` directly from disk won't load the data, because browsers block `fetch` for local files.
Use the local server above.

## Features

- Cards per event with image, time, venue, category, duration, price and a "sold out" badge
- Venue and category bubbles, plus dropdowns
- "Heute / Today" toggle and a day strip to jump to any date
- Month headings, as on the Berlin site
- German / English interface. Event titles are never translated.

## Files

| Path | Purpose |
| --- | --- |
| `index.html`, `style.css`, `app.js` | The site |
| `data/events.json` | Programme data (written by the scraper) |
| `scripts/scrape.py` | Scraper and venue list |
| `.github/workflows/update.yml` | Daily automatic update |
