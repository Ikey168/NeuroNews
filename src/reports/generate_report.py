"""
Automated report generation — PDF & CSV.

Queries the local DuckDB analytics warehouse for a given topic and time
window, then serialises the results as both a CSV (raw rows) and a PDF
(formatted summary with headline stats and per-article listing).

Usage (standalone):
    python -m src.reports.generate_report --topic "Nvidia" --period last_7_days
"""

from __future__ import annotations

import csv
import io
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import List

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Period helpers
# ---------------------------------------------------------------------------

_PERIOD_DAYS: dict[str, int] = {
    "last_7_days": 7,
    "last_30_days": 30,
    "last_90_days": 90,
    "last_24_hours": 1,
}


def _period_to_cutoff(period: str) -> datetime:
    days = _PERIOD_DAYS.get(period)
    if days is None:
        raise ValueError(
            f"Unknown period '{period}'. Supported: {list(_PERIOD_DAYS)}"
        )
    return datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class ArticleRow:
    article_id: str
    title: str
    source: str
    category: str
    publish_date: str
    sentiment_label: str
    sentiment_score: float
    url: str


@dataclass
class ReportData:
    topic: str
    period: str
    generated_at: str
    total_articles: int
    avg_sentiment: float
    positive_pct: float
    negative_pct: float
    neutral_pct: float
    top_sources: List[str]
    articles: List[ArticleRow] = field(default_factory=list)


# ---------------------------------------------------------------------------
# DuckDB query
# ---------------------------------------------------------------------------

def _fetch_report_data(topic: str, period: str) -> ReportData:
    from src.database.local_analytics_connector import get_shared_connection, _LOCK

    cutoff = _period_to_cutoff(period)
    conn = get_shared_connection()

    query = """
        SELECT
            id,
            title,
            COALESCE(url, '') AS url,
            COALESCE(source, 'Unknown') AS source,
            COALESCE(category, 'General') AS category,
            STRFTIME(publish_date, '%Y-%m-%d %H:%M') AS publish_date,
            COALESCE(sentiment_label, 'neutral') AS sentiment_label,
            COALESCE(sentiment_score, 0.0) AS sentiment_score
        FROM news_articles
        WHERE
            (title ILIKE ? OR category ILIKE ?)
            AND publish_date >= ?
        ORDER BY publish_date DESC
        LIMIT 200
    """
    pattern = f"%{topic}%"

    with _LOCK:
        rows = conn.execute(query, [pattern, pattern, cutoff]).fetchall()

    articles = [
        ArticleRow(
            article_id=r[0],
            title=r[1],
            url=r[2],
            source=r[3],
            category=r[4],
            publish_date=r[5],
            sentiment_label=r[6],
            sentiment_score=float(r[7]),
        )
        for r in rows
    ]

    total = len(articles)
    avg_sent = sum(a.sentiment_score for a in articles) / total if total else 0.0
    pos = sum(1 for a in articles if a.sentiment_label == "positive")
    neg = sum(1 for a in articles if a.sentiment_label == "negative")
    neu = total - pos - neg
    pct = lambda n: round(n / total * 100, 1) if total else 0.0

    # Top sources by article count
    source_counts: dict[str, int] = {}
    for a in articles:
        source_counts[a.source] = source_counts.get(a.source, 0) + 1
    top_sources = [s for s, _ in sorted(source_counts.items(), key=lambda x: -x[1])[:5]]

    return ReportData(
        topic=topic,
        period=period,
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        total_articles=total,
        avg_sentiment=round(avg_sent, 4),
        positive_pct=pct(pos),
        negative_pct=pct(neg),
        neutral_pct=pct(neu),
        top_sources=top_sources,
        articles=articles,
    )


# ---------------------------------------------------------------------------
# CSV serialiser
# ---------------------------------------------------------------------------

def generate_csv(topic: str, period: str) -> bytes:
    """Return UTF-8 encoded CSV bytes for the report."""
    data = _fetch_report_data(topic, period)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "article_id", "title", "source", "category",
        "publish_date", "sentiment_label", "sentiment_score", "url",
    ])
    for a in data.articles:
        writer.writerow([
            a.article_id, a.title, a.source, a.category,
            a.publish_date, a.sentiment_label, a.sentiment_score, a.url,
        ])
    return buf.getvalue().encode("utf-8")


# ---------------------------------------------------------------------------
# PDF serialiser (fpdf2)
# ---------------------------------------------------------------------------

def _latin1(text: str) -> str:
    """Sanitize text to the Latin-1 range that fpdf2's core fonts support."""
    _SUBS = str.maketrans({
        "‘": "'", "’": "'",
        "“": '"', "”": '"',
        "—": "-", "–": "-",
        "…": "...",
    })
    return text.translate(_SUBS).encode("latin-1", errors="replace").decode("latin-1")


def generate_pdf(topic: str, period: str) -> bytes:
    """Return PDF bytes for the report. Requires fpdf2."""
    try:
        from fpdf import FPDF
    except ImportError as exc:
        raise RuntimeError("fpdf2 is required: pip install fpdf2") from exc

    data = _fetch_report_data(topic, period)

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=14)
    pdf.add_page()

    # Title block
    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(0, 10, _latin1(f"Noesis Report: {data.topic}"), ln=True)
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(120, 120, 120)
    pdf.cell(0, 6, _latin1(f"Period: {data.period}  |  Generated: {data.generated_at}"), ln=True)
    pdf.ln(4)
    pdf.set_draw_color(50, 120, 220)
    pdf.set_line_width(0.5)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(5)

    # Summary stats
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, "Summary", ln=True)
    pdf.set_font("Helvetica", "", 10)

    stats = [
        ("Total articles", str(data.total_articles)),
        ("Avg sentiment score", f"{data.avg_sentiment:+.4f}"),
        ("Positive", f"{data.positive_pct}%"),
        ("Negative", f"{data.negative_pct}%"),
        ("Neutral", f"{data.neutral_pct}%"),
        ("Top sources", ", ".join(data.top_sources) or "-"),
    ]
    for label, value in stats:
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(48, 7, _latin1(label + ":"), ln=False)
        pdf.set_font("Helvetica", "", 10)
        pdf.cell(0, 7, _latin1(value), ln=True)

    pdf.ln(4)
    pdf.set_draw_color(220, 220, 220)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(5)

    # Article listing
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, f"Articles ({data.total_articles})", ln=True)
    pdf.ln(2)

    SENT_COLOR = {
        "positive": (40, 167, 69),
        "negative": (220, 53, 69),
        "neutral": (108, 117, 125),
    }

    for i, a in enumerate(data.articles):
        if pdf.get_y() > 265:
            pdf.add_page()

        r, g, b = SENT_COLOR.get(a.sentiment_label, (108, 117, 125))
        pdf.set_text_color(r, g, b)
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(20, 6, a.sentiment_label.upper(), ln=False)

        pdf.set_text_color(0, 0, 0)
        pdf.set_font("Helvetica", "", 9)
        title = a.title if len(a.title) <= 90 else a.title[:87] + "..."
        pdf.cell(0, 6, _latin1(title), ln=True)

        pdf.set_text_color(140, 140, 140)
        pdf.set_font("Helvetica", "", 8)
        pdf.cell(20, 5, "", ln=False)
        meta = f"{a.source}  *  {a.publish_date}  *  score {a.sentiment_score:+.3f}"
        pdf.cell(0, 5, _latin1(meta), ln=True)
        pdf.set_text_color(0, 0, 0)

        if i < len(data.articles) - 1:
            pdf.set_draw_color(240, 240, 240)
            pdf.line(10, pdf.get_y(), 200, pdf.get_y())

    return bytes(pdf.output())


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _cli():
    import argparse, pathlib

    parser = argparse.ArgumentParser(description="Generate a Noesis topic report")
    parser.add_argument("--topic", required=True, help="Topic keyword to filter by")
    parser.add_argument(
        "--period",
        default="last_7_days",
        choices=list(_PERIOD_DAYS),
        help="Time window",
    )
    parser.add_argument(
        "--out",
        default=".",
        help="Output directory (default: current dir)",
    )
    parser.add_argument(
        "--format",
        choices=["pdf", "csv", "both"],
        default="both",
    )
    args = parser.parse_args()

    out_dir = pathlib.Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    slug = args.topic.lower().replace(" ", "_")

    if args.format in ("csv", "both"):
        csv_path = out_dir / f"report_{slug}_{args.period}.csv"
        csv_path.write_bytes(generate_csv(args.topic, args.period))
        print(f"CSV → {csv_path}")

    if args.format in ("pdf", "both"):
        pdf_path = out_dir / f"report_{slug}_{args.period}.pdf"
        pdf_path.write_bytes(generate_pdf(args.topic, args.period))
        print(f"PDF → {pdf_path}")


if __name__ == "__main__":
    _cli()
