#!/usr/bin/env python3
"""
Smoke-test for the entity corrections pipeline (Issue #44).
Run from repo root: PYTHONPATH=. python3 .claude/skills/verify-entity-corrections/smoke.py
"""
from __future__ import annotations

import sys
import traceback

# Reset singletons so this script is re-runnable in the same process
import src.knowledge_graph.entity_corrections as _ec_mod
import src.knowledge_graph.kg_updater as _ku_mod
_ec_mod._correction_store = None
_ku_mod._store = None
_ku_mod._resolver = None
_ku_mod._events.clear()

from src.knowledge_graph.foundation import Node, EntityType
from src.knowledge_graph.kg_updater import _shared_store
from src.knowledge_graph.entity_corrections import (
    CorrectionType, CorrectionStatus, get_correction_store,
)

PASS = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"
results: list[tuple[str, bool, str]] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    results.append((label, condition, detail))
    status = PASS if condition else FAIL
    suffix = f"  — {detail}" if detail else ""
    print(f"  {status}  {label}{suffix}")


def run() -> None:
    store = _shared_store()
    cs = get_correction_store()

    # ---- seed entities ---------------------------------------------------- #
    target = Node(type=EntityType.PERSON, name="Tim Cook")
    source = Node(type=EntityType.PERSON, name="Timothy Cook")
    org    = Node(type=EntityType.ORGANIZATION, name="Apple")
    for n in [target, source, org]:
        store.add_node(n)

    print("\n── Submission ──────────────────────────────────────────────────")

    c_rename = cs.submit(target.node_id, CorrectionType.RENAME,
                         {"new_name": "Tim D. Cook"}, "full middle name", "user-1")
    check("rename submitted as pending", c_rename.status == CorrectionStatus.PENDING)

    c_alias = cs.submit(target.node_id, CorrectionType.ADD_ALIAS,
                        {"alias": "Timothy Donald Cook"}, "formal name", "user-1")
    check("add_alias submitted as pending", c_alias.status == CorrectionStatus.PENDING)

    c_rem_alias = cs.submit(target.node_id, CorrectionType.REMOVE_ALIAS,
                            {"alias": "Timothy Donald Cook"}, "undo alias", "user-1")
    check("remove_alias submitted as pending", c_rem_alias.status == CorrectionStatus.PENDING)

    c_add_prop = cs.submit(target.node_id, CorrectionType.ADD_PROPERTY,
                           {"key": "title", "value": "CEO"}, "add title", "user-1")
    check("add_property submitted as pending", c_add_prop.status == CorrectionStatus.PENDING)

    c_rem_prop = cs.submit(target.node_id, CorrectionType.REMOVE_PROPERTY,
                           {"key": "title"}, "remove title", "user-1")
    check("remove_property submitted as pending", c_rem_prop.status == CorrectionStatus.PENDING)

    c_merge = cs.submit(target.node_id, CorrectionType.MERGE,
                        {"merge_from": source.node_id}, "deduplicate", "user-1")
    check("merge submitted as pending", c_merge.status == CorrectionStatus.PENDING)

    c_reject = cs.submit(org.node_id, CorrectionType.RENAME,
                         {"new_name": "Wrong Name"}, "bad correction", "user-99")
    check("reject-candidate submitted", c_reject.status == CorrectionStatus.PENDING)

    check("versions are monotonic per entity",
          [c.version for c in [c_rename, c_alias, c_rem_alias, c_add_prop, c_rem_prop, c_merge]]
          == list(range(1, 7)))

    print("\n── Approval (checked immediately after each) ───────────────────")

    cs.approve(c_rename.correction_id, reviewed_by="admin-1", review_note="ok")
    check("rename applied",
          store.get_node(target.node_id).name == "Tim D. Cook",
          store.get_node(target.node_id).name)

    cs.approve(c_alias.correction_id, reviewed_by="admin-1")
    node = store.get_node(target.node_id)
    check("add_alias applied",
          "Timothy Donald Cook" in node.aliases,
          str(node.aliases))

    cs.approve(c_rem_alias.correction_id, reviewed_by="admin-1")
    node = store.get_node(target.node_id)
    check("remove_alias applied",
          "Timothy Donald Cook" not in node.aliases,
          str(node.aliases))

    cs.approve(c_add_prop.correction_id, reviewed_by="admin-1")
    node = store.get_node(target.node_id)
    check("add_property applied",
          node.properties.get("title") == "CEO",
          str(node.properties))

    cs.approve(c_rem_prop.correction_id, reviewed_by="admin-1")
    node = store.get_node(target.node_id)
    check("remove_property applied",
          "title" not in node.properties,
          str(node.properties))

    cs.approve(c_merge.correction_id, reviewed_by="admin-1")
    check("merge: source node removed",
          store.get_node(source.node_id) is None)

    check("merge: source name in target aliases",
          "Timothy Cook" in store.get_node(target.node_id).aliases,
          str(store.get_node(target.node_id).aliases))

    print("\n── Rejection ───────────────────────────────────────────────────")

    cs.reject(c_reject.correction_id, reviewed_by="admin-1", review_note="incorrect data")
    check("rejection recorded",
          c_reject.status == CorrectionStatus.REJECTED)
    check("rejected correction note preserved",
          c_reject.review_note == "incorrect data")
    check("org name unchanged after rejection",
          store.get_node(org.node_id).name == "Apple")

    print("\n── Double-review guard ─────────────────────────────────────────")

    try:
        cs.approve(c_rename.correction_id, reviewed_by="admin-2")
        check("double-approve prevented", False, "no exception raised")
    except ValueError:
        check("double-approve prevented", True)

    try:
        cs.reject(c_reject.correction_id, reviewed_by="admin-2")
        check("double-reject prevented", False, "no exception raised")
    except ValueError:
        check("double-reject prevented", True)

    print("\n── Query helpers ───────────────────────────────────────────────")

    pending = cs.list_corrections(status=CorrectionStatus.PENDING)
    check("no pending corrections remain", len(pending) == 0, f"found {len(pending)}")

    approved_list = cs.list_corrections(status=CorrectionStatus.APPROVED)
    check("6 approved corrections", len(approved_list) == 6, f"found {len(approved_list)}")

    by_entity = cs.list_corrections(entity_id=target.node_id)
    check("list_corrections filters by entity", all(c.entity_id == target.node_id for c in by_entity))

    fetched = cs.get(c_rename.correction_id)
    check("get() returns correct correction", fetched is not None and fetched.correction_id == c_rename.correction_id)


def main() -> None:
    print("verify-entity-corrections smoke test")
    print("=" * 50)
    try:
        run()
    except Exception:
        traceback.print_exc()
        print(f"\n{FAIL}  Unhandled exception — see traceback above")
        sys.exit(1)

    passed = sum(1 for _, ok, _ in results if ok)
    failed = sum(1 for _, ok, _ in results if not ok)
    print(f"\n{'=' * 50}")
    print(f"Results: {passed} passed, {failed} failed")
    if failed:
        sys.exit(1)
    print("All checks passed.")


if __name__ == "__main__":
    main()
