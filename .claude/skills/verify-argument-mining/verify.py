"""
verify-argument-mining: smoke-test the ClaimDetector and StanceClassifier
inference wrappers across all six Noesis content types.

Runs entirely offline — no API server, no trained model required.  When a
fine-tuned checkpoint is present in models/claim_detector/ or
models/stance_classifier/ it is used; otherwise the heuristic fallback runs.

Usage:
    python3 .claude/skills/verify-argument-mining/verify.py [--topic TOPIC]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

# ---------------------------------------------------------------------------
# Sample documents — one representative sentence per source type.
# Each tuple: (source_type, content, stance_topic)
# ---------------------------------------------------------------------------
_SAMPLES = [
    (
        "news",
        (
            "The unemployment rate fell to 3.8% in March, the lowest level in two decades. "
            "The central bank raised interest rates by 25 basis points to 5.25%. "
            "Critics argue the government has not done enough to address the cost-of-living crisis."
        ),
        "economic policy",
    ),
    (
        "blog",
        (
            "After tracking this metric daily for 18 months I can confirm engagement dropped 37% "
            "after the platform update. "
            "In my opinion, this is the most reckless change the company has made in years. "
            "The library added async support in version 3.2, released on 4 April 2024."
        ),
        "platform changes",
    ),
    (
        "paper",
        (
            "Our analysis reveals a statistically significant correlation between sleep duration "
            "and cognitive performance (r = 0.74, p < 0.001). "
            "It is possible that unmeasured confounders may have influenced the observed association. "
            "The cohort comprised 3,247 participants aged 18–65 recruited across six clinical sites."
        ),
        "public health",
    ),
    (
        "transcript",
        (
            "What we reported to the board was a 30% reduction in operating costs across all four divisions. "
            "I think what we are seeing is a fundamental shift in how communities engage with these institutions. "
            "The committee chair confirmed the vote passed by nine votes to three."
        ),
        "corporate performance",
    ),
    (
        "book",
        (
            "By 1943 the city had lost more than a third of its pre-war population to evacuation. "
            "One might argue the turning point came not with the armistice but with the collapse of civilian morale. "
            "The treaty signed on 11 June 1919 transferred sovereignty over the territory to the new republic."
        ),
        "historical events",
    ),
    (
        "note",
        (
            "Board approved budget of $2.4M on 14 June; finance confirmed transfer completed same day. "
            "Need to follow up with legal on the contract terms before signing. "
            "Security audit completed 10 June — 3 critical findings, all remediated by 12 June."
        ),
        "project status",
    ),
]

_SEP = "─" * 72


def _banner(text: str) -> None:
    print(f"\n{_SEP}")
    print(f"  {text}")
    print(_SEP)


def _truncate(s: str, width: int = 55) -> str:
    return s if len(s) <= width else s[: width - 1] + "…"


def main(topic_override: str | None = None) -> int:
    import time

    from services.ingest.common.document_model import Document
    from src.argument_mining.models import ClaimDetector, StanceClassifier

    claim_model_dir = REPO_ROOT / "models" / "claim_detector"
    stance_model_dir = REPO_ROOT / "models" / "stance_classifier"

    cd = ClaimDetector()
    sc = StanceClassifier()

    claim_mode = "trained model" if (claim_model_dir / "config.json").exists() else "heuristic fallback"
    stance_mode = "trained model" if (stance_model_dir / "config.json").exists() else "heuristic fallback"

    _banner(f"Argument Mining — inference smoke-test")
    print(f"  ClaimDetector:    {claim_mode}")
    print(f"  StanceClassifier: {stance_mode}")
    print(f"  Repo root:        {REPO_ROOT}")

    errors: list[str] = []

    for source_type, content, default_topic in _SAMPLES:
        topic = topic_override or default_topic
        doc = Document(
            document_id=f"smoke-{source_type}",
            source_type=source_type,
            language="en",
            ingested_at=int(time.time() * 1000),
            content=content,
        )

        try:
            claim_preds = cd.predict(doc)
            stance_preds = sc.predict(doc, topic)
        except Exception as exc:
            errors.append(f"{source_type}: {exc}")
            print(f"\n  [{source_type}]  ERROR: {exc}")
            continue

        print(f"\n  [{source_type}]  topic={topic!r}  ({len(claim_preds)} sentences)")
        print(f"  {'Sentence':<56} {'Claim':<8} {'Conf':>5}  {'Stance':<10} {'Conf':>5}")
        print(f"  {'─'*56} {'─'*8} {'─'*5}  {'─'*10} {'─'*5}")

        for cp, sp in zip(claim_preds, stance_preds):
            label = "CLAIM" if cp.is_claim else "—"
            print(
                f"  {_truncate(cp.text):<56} {label:<8} {cp.confidence:>5.2f}"
                f"  {sp.stance:<10} {sp.confidence:>5.2f}"
            )

    print(f"\n{_SEP}")
    if errors:
        print(f"  RESULT: FAIL — {len(errors)} error(s)")
        for e in errors:
            print(f"    • {e}")
        print(_SEP)
        return 1

    all_types = {s[0] for s in _SAMPLES}
    print(f"  RESULT: PASS — all {len(all_types)} source types produced predictions")
    if claim_mode == "heuristic fallback":
        print()
        print("  NOTE: heuristic mode — run training scripts once #109 data lands")
        print("  to get F1-scored models:")
        print("    python -m src.argument_mining.train_claim --data data/argument_mining")
        print("    python -m src.argument_mining.train_stance --data data/argument_mining")
    print(_SEP)
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Smoke-test argument mining inference wrappers")
    parser.add_argument(
        "--topic",
        default=None,
        help="Override the stance topic for all samples (default: per-sample topic)",
    )
    args = parser.parse_args()
    sys.exit(main(topic_override=args.topic))
