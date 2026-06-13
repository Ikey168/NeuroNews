"""Simple in-memory model registry for tests."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Any
import time


@dataclass
class RegisteredModel:
    name: str
    version: int
    obj: Any
    registered_at: float
    stage: str = "None"


class ModelRegistry:
    def __init__(self):
        self._store: Dict[str, Dict[int, RegisteredModel]] = {}

    def register(self, name: str, model_obj: Any) -> RegisteredModel:
        versions = self._store.setdefault(name, {})
        next_version = max(versions.keys(), default=0) + 1
        rm = RegisteredModel(name=name, version=next_version, obj=model_obj, registered_at=time.time())
        versions[next_version] = rm
        return rm

    def get(self, name: str, version: int) -> RegisteredModel:
        return self._store[name][version]

    def latest(self, name: str) -> RegisteredModel:
        versions = self._store.get(name, {})
        if not versions:
            raise KeyError(f"No versions for model {name}")
        v = max(versions.keys())
        return versions[v]

    def transition_stage(self, name: str, version: int, stage: str) -> RegisteredModel:
        rm = self.get(name, version)
        rm.stage = stage
        return rm
