---
name: report-preview
description: Generate a Noesis topic report in JSON, CSV, and PDF formats and rasterise the PDF to PNG for visual inspection. Use when iterating on report layout, verifying that a topic returns data, or spot-checking output formats. Calls src/reports/generate_report.py directly — no API server required.
---

# report-preview skill

Generates a report for a given topic + period in all three formats (JSON, CSV,
PDF) and optionally rasterises the PDF to a PNG for quick visual inspection.
Runs entirely offline — calls `src/reports/generate_report.py` directly with
no API server, no extra services.

**All paths are relative to the repo root** (`/home/Ikey/NeuroNews`).

## Usage

```bash
bash .claude/skills/report-preview/preview.sh --topic "Iran" [--period last_7_days] [--format all|json|csv|pdf]
```

Default period: `last_7_days`. Default format: `all`.

Valid periods: `last_24_hours`, `last_7_days`, `last_30_days`, `last_90_days`.

## Output

All files land in `.claude/skills/report-preview/screenshots/`:

```
screenshots/
  iran_last_7_days.json   ← headline stats + article list
  iran_last_7_days.csv    ← raw article rows
  iran_last_7_days.pdf    ← formatted PDF
  iran_last_7_days.png    ← PDF page 1 raster at 150 dpi (if pdftoppm/convert available)
```

The PNG is produced by `pdftoppm` (from `poppler-utils`) if present, falling
back to ImageMagick `convert`. If neither is installed the PNG step is skipped
with a note — the PDF is still written.

## Examples

```bash
# Preview a 30-day report on "AI" — all formats
bash .claude/skills/report-preview/preview.sh --topic "AI" --period last_30_days

# Just PDF for a quick layout check
bash .claude/skills/report-preview/preview.sh --topic "Trump" --format pdf

# Check what data exists for a topic (JSON only, fastest)
bash .claude/skills/report-preview/preview.sh --topic "SpaceX" --format json
```

## Reading output as an agent

After running, **open the PNG** (or read the JSON) to verify:
- The report has articles (non-zero `total_articles` in stats).
- The PDF layout is readable — title block, summary stats, article listing.
- No encoding errors (curly quotes, em-dashes in headlines are sanitized to
  Latin-1 automatically).

If `total_articles` is 0, the topic keyword returned no matches in the DuckDB
warehouse for the chosen period. Try a broader keyword or a longer period.

## Requirements

- `fpdf2` — PDF generation (`pip install fpdf2`; already installed).
- `pdftoppm` (poppler-utils) OR ImageMagick `convert` — optional, for PNG raster.
- No API server, no network, no API keys needed.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `total_articles: 0` | Topic keyword has no matches in the DB for that period. Try `last_30_days` or a shorter keyword (e.g. `"AI"` instead of `"Artificial Intelligence"`). |
| PDF raster skipped | Install `poppler-utils` (`sudo dnf install poppler-utils`) for `pdftoppm`, or ImageMagick (`sudo dnf install ImageMagick`) for `convert`. |
| `RuntimeError: fpdf2 is required` | `pip install fpdf2` in the repo's Python environment. |
| PNG is blank / wrong page | The PDF may be multi-page; the raster shows page 1 only. Open the PDF directly to see all pages. |
