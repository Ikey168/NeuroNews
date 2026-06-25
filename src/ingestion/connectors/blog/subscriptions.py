"""JSON-backed subscription store for blog/RSS/Atom feeds."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import List, Optional

from src.ingestion.connectors.blog.models import FeedSubscription

_DEFAULT_PATH = Path(__file__).parents[4] / "config" / "blog_subscriptions.json"


class SubscriptionStore:
    """Persist and query RSS/Atom feed subscriptions in a JSON file."""

    def __init__(self, path: Optional[Path] = None) -> None:
        self._path = Path(path) if path is not None else _DEFAULT_PATH

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def subscribe(self, url: str, name: str = "", tags: Optional[List[str]] = None) -> FeedSubscription:
        """Add or update a subscription. Existing entries are updated in-place."""
        subs = self._load()
        existing = next((s for s in subs if s.url == url), None)
        if existing is not None:
            subs.remove(existing)
        sub = FeedSubscription(
            url=url,
            name=name or url,
            tags=list(tags or []),
            added_at=int(time.time() * 1000),
        )
        subs.append(sub)
        self._save(subs)
        return sub

    def unsubscribe(self, url: str) -> bool:
        """Remove a subscription by URL. Returns True if it was present."""
        subs = self._load()
        before = len(subs)
        subs = [s for s in subs if s.url != url]
        if len(subs) < before:
            self._save(subs)
            return True
        return False

    def list(self) -> List[FeedSubscription]:
        return self._load()

    def get(self, url: str) -> Optional[FeedSubscription]:
        return next((s for s in self._load() if s.url == url), None)

    # ------------------------------------------------------------------ #
    # Persistence
    # ------------------------------------------------------------------ #

    def _load(self) -> List[FeedSubscription]:
        if not self._path.exists():
            return []
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            return [
                FeedSubscription(
                    url=r["url"],
                    name=r.get("name", r["url"]),
                    tags=list(r.get("tags", [])),
                    added_at=int(r.get("added_at", 0)),
                )
                for r in raw.get("subscriptions", [])
                if r.get("url")
            ]
        except Exception:
            return []

    def _save(self, subs: List[FeedSubscription]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "subscriptions": [
                {"url": s.url, "name": s.name, "tags": s.tags, "added_at": s.added_at}
                for s in subs
            ]
        }
        self._path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
