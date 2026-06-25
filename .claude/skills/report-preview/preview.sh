#!/usr/bin/env bash
# preview.sh — generate a report in all three formats and screenshot the PDF.
#
# Usage:
#   bash .claude/skills/report-preview/preview.sh --topic "Iran" [--period last_7_days] [--format all|json|csv|pdf]
#
# Outputs:
#   .claude/skills/report-preview/screenshots/<slug>_<period>.{pdf,csv,json}
#   .claude/skills/report-preview/screenshots/<slug>_<period>.png   (PDF page 1 raster)
#
# Requirements:
#   - PYTHONPATH set to repo root (done automatically)
#   - fpdf2  (pip install fpdf2)
#   - pdftoppm OR ImageMagick convert  (for PNG raster; optional)
#
# All paths are relative to the repo root.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
SHOT_DIR="$REPO_ROOT/.claude/skills/report-preview/screenshots"
mkdir -p "$SHOT_DIR"

TOPIC=""
PERIOD="last_7_days"
FORMAT="all"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --topic)   TOPIC="$2";  shift 2 ;;
    --period)  PERIOD="$2"; shift 2 ;;
    --format)  FORMAT="$2"; shift 2 ;;
    *) echo "Unknown arg: $1" >&2; exit 1 ;;
  esac
done

if [[ -z "$TOPIC" ]]; then
  echo "Usage: $0 --topic <keyword> [--period last_7_days|last_30_days|last_90_days|last_24_hours] [--format all|json|csv|pdf]" >&2
  exit 1
fi

SLUG="${TOPIC,,}"         # lowercase
SLUG="${SLUG// /_}"       # spaces → underscores
BASE="$SHOT_DIR/${SLUG}_${PERIOD}"

export PYTHONPATH="$REPO_ROOT"

echo "==> Generating report: topic='$TOPIC' period='$PERIOD'"

# JSON
if [[ "$FORMAT" == "all" || "$FORMAT" == "json" ]]; then
  python3 - <<PY
import json, sys
sys.path.insert(0, "$REPO_ROOT")
from src.reports.generate_report import _fetch_report_data
d = _fetch_report_data("$TOPIC", "$PERIOD")
out = {
    "topic": d.topic, "period": d.period, "generated_at": d.generated_at,
    "stats": {
        "total_articles": d.total_articles, "avg_sentiment": d.avg_sentiment,
        "positive_pct": d.positive_pct, "negative_pct": d.negative_pct,
        "neutral_pct": d.neutral_pct, "top_sources": d.top_sources,
    },
    "articles": [
        {"title": a.title, "source": a.source, "publish_date": a.publish_date,
         "sentiment_label": a.sentiment_label, "sentiment_score": a.sentiment_score}
        for a in d.articles
    ],
}
with open("${BASE}.json", "w") as f:
    json.dump(out, f, indent=2)
print(f"  JSON  -> ${BASE}.json  ({d.total_articles} articles)")
PY
fi

# CSV
if [[ "$FORMAT" == "all" || "$FORMAT" == "csv" ]]; then
  python3 - <<PY
import sys
sys.path.insert(0, "$REPO_ROOT")
from src.reports.generate_report import generate_csv
data = generate_csv("$TOPIC", "$PERIOD")
with open("${BASE}.csv", "wb") as f:
    f.write(data)
lines = data.decode().count('\n')
print(f"  CSV   -> ${BASE}.csv  ({lines} rows incl. header)")
PY
fi

# PDF
if [[ "$FORMAT" == "all" || "$FORMAT" == "pdf" ]]; then
  python3 - <<PY
import sys
sys.path.insert(0, "$REPO_ROOT")
from src.reports.generate_report import generate_pdf
data = generate_pdf("$TOPIC", "$PERIOD")
with open("${BASE}.pdf", "wb") as f:
    f.write(data)
print(f"  PDF   -> ${BASE}.pdf  ({len(data)} bytes)")
PY

  # Rasterise page 1 of the PDF to PNG for quick visual check
  PNG_OUT="${BASE}.png"
  RASTERISED=false

  if command -v pdftoppm &>/dev/null; then
    pdftoppm -r 150 -png -singlefile "${BASE}.pdf" "${BASE}" && mv "${BASE}.ppm" "$PNG_OUT" 2>/dev/null || true
    # pdftoppm outputs <base>-1.png by default when -singlefile is not available on old builds
    if [[ -f "${BASE}-1.png" ]]; then mv "${BASE}-1.png" "$PNG_OUT"; fi
    [[ -f "$PNG_OUT" ]] && RASTERISED=true
  fi

  if [[ "$RASTERISED" == "false" ]] && command -v convert &>/dev/null; then
    convert -density 150 "${BASE}.pdf[0]" "$PNG_OUT" && RASTERISED=true
  fi

  if [[ "$RASTERISED" == "true" ]]; then
    echo "  PNG   -> $PNG_OUT"
  else
    echo "  PNG   skipped (install pdftoppm or ImageMagick for raster preview)"
  fi
fi

echo ""
echo "Done. Files in: $SHOT_DIR"
ls -lh "$SHOT_DIR/${SLUG}_${PERIOD}".* 2>/dev/null || true
