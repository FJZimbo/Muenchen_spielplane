# München Spielplan

Theatre, opera, concerts and cinema in Munich on one page, refreshed every day.

| Category | Venues |
| --- | --- |
| Theatre | Residenztheater · Münchner Kammerspiele · Münchner Volkstheater · Deutsches Theater |
| Concert | Isarphilharmonie (calendar on gasteig.de) |
| Opera | Bayerische Staatsoper |
| Cinema | Museum Lichtspiele · City Kinos & Atelier (all screenings) |

## How it works

A GitHub Action opens each venue's programme in a headless Chrome browser every morning. It clicks
"Mehr laden", the "next month" buttons and the cinema day tabs, reads every performance and writes
`data/events.json`. The site (`index.html`, `app.js`, `style.css`) just displays that file.

- Sold out, few tickets and cancelled are read from each listing.
- Deutsches Theater lists runs ("07.10. bis 08.11.26") plus weekly times, not single dates. Its dates are
  derived from that and marked on the card. Its ticket shop blocks automated access, so availability is not shown.
- If a venue returns nothing on a given day, its previous dates are kept and the footer marks the source.
- The scraper respects each site's robots.txt and pauses between pages.

## Updating an existing repository (from version 1)

1. **Delete the old files** in the repository: `app.js`, `index.html`, `style.css`, `requirements.txt`,
   `scripts/scrape.py`, `data/events.json`, and the stray file named `Update` if it's still there.
2. **Upload the new files**: drag everything from the unzipped folder *except* `.github` onto the
   repository page (**Add file → Upload files**), then commit.
3. **Replace the workflow**: open `.github/workflows/update.yml` on GitHub, click the pencil icon, select all,
   paste the contents of the new `update.yml` (open it in TextEdit; press Cmd+Shift+. in Finder to see the
   hidden `.github` folder), and commit.
4. **Run it**: Actions → *Update programme* → **Run workflow** (leave "debug" ticked). A full run takes about
   10–20 minutes.
5. Open your site. The footer lists how many events each source returned.

## When a venue shows "keine Daten"

Websites change. Every manual run with "debug" ticked saves what the browser saw to the `debug/` folder.
Download the repository (**Code → Download ZIP**) and send the `debug` folder, together with the
"Scrape venues" log from the Actions run. The parser for that venue can then be fixed against the real page.
Venue URLs and link patterns live in `scripts/venues.py`.

## Running locally

```bash
pip install -r requirements.txt
python -m playwright install chromium
python tests/test_extract.py                 # offline parser tests
python scripts/scrape.py --debug             # all venues (or: --only kammerspiele)
python -m http.server 8000                   # open http://localhost:8000
```

## Files

| Path | Purpose |
| --- | --- |
| `index.html`, `style.css`, `app.js` | The site |
| `data/events.json` | All events (written by the scraper) |
| `data/status.json` | Per-venue result of the last run |
| `scripts/venues.py` | Venue list: URLs, link patterns, stages, genres |
| `scripts/extract.py` | Parsing (no network; tested by `tests/test_extract.py`) |
| `scripts/scrape.py` | Browser automation and output |
| `scripts/build_preview.py` | Builds a single-file preview with sample data |
| `.github/workflows/update.yml` | Daily run |
