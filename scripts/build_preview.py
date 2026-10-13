#!/usr/bin/env python3
"""Build a single self-contained preview page (CSS, JS and data inlined).

    python scripts/build_preview.py data/sample.json preview.html
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main(data_path: str, out_path: str) -> None:
    index = (ROOT / "index.html").read_text(encoding="utf-8")
    body = index.split("<!-- BODY:START -->")[1].split("<!-- BODY:END -->")[0]
    css = (ROOT / "style.css").read_text(encoding="utf-8")
    js = (ROOT / "app.js").read_text(encoding="utf-8")
    data = json.loads(Path(data_path).read_text(encoding="utf-8"))
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    note = '<div class="preview-note" id="preview-note"><div class="wrap"></div></div>'
    page = f"""<title>Münchner Spielplan</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wdth,wght@62..125,400..900&family=Instrument+Sans:wght@400..700&display=swap">
<style>
{css}
</style>
{note}
{body}
<script type="application/json" id="embedded-data">{payload}</script>
<script>
{js}
</script>
"""
    Path(out_path).write_text(page, encoding="utf-8")
    print(f"wrote {out_path} ({len(page) // 1024} KB)")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
