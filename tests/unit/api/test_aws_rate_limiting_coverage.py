"""Coverage-focused tests for src/api/aws_rate_limiting.py.

Targets the uncovered branches of the local (no-AWS) rate limiting module:
- state load/save success + error paths
- usage-plan / API-key / tier assignment error branches
- usage-statistics aggregation windows
- monitor_throttling_events, metrics recorder, alarms, setup helper failures

Every dependency (filesystem) is redirected to a tmp dir via NEURONEWS_LOG_DIR.
boto3 is never imported; the module is stdlib-only, so no cloud mocking is
needed -- but we still assert boto3 is absent to prove the local backend.
"""

import asyncio
import importlib
import json
import os
import sys

import pytest

MODULE_PATH = "src.api.aws_rate_limiting"


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture()
def mod(tmp_path, monkeypatch):
    """Import the module fresh with state/metrics pointed at a temp dir."""
    monkeypatch.setenv("NEURONEWS_LOG_DIR", str(tmp_path))
    monkeypatch.delenv("API_GATEWAY_ID", raising=False)
    monkeypatch.delenv("API_GATEWAY_STAGE", raising=False)
    sys.modules.pop(MODULE_PATH, None)
    m = importlib.import_module(MODULE_PATH)
    importlib.reload(m)
    return m, str(tmp_path)


# ---------------------------------------------------------------------------
# boto3 absence (proves purely-local backend, no cloud client needed)
# ---------------------------------------------------------------------------
def test_module_does_not_import_boto3(mod):
    m, _ = mod
    src = open(m.__file__).read()
    # The module must not *import* boto3/botocore -- it is a purely local,
    # stdlib-only backend. ("boto3" may legitimately appear in the docstring,
    # so we only forbid actual import statements.) We deliberately do NOT assert
    # on the global sys.modules: unrelated libraries loaded by other tests in
    # the same process may pull boto3 in transitively, which says nothing about
    # this module.
    assert "import boto3" not in src
    assert "import botocore" not in src
    assert "from boto3" not in src
    assert "from botocore" not in src


# ---------------------------------------------------------------------------
# _load_state: success reading an existing file, and error fallback
# ---------------------------------------------------------------------------
def test_load_state_reads_existing_file_and_merges_defaults(mod, tmp_path):
    m, log_dir = mod
    state_file = os.path.join(log_dir, "rate_limit_usage_plans.json")
    # Partial state on disk: only 'usage_plans' present; defaults must be merged.
    with open(state_file, "w") as f:
        json.dump({"usage_plans": {"free_tier": "free-tier-plan"}}, f)

    mgr = m.LocalUsagePlanManager()
    # Existing key preserved (line 119-123 success path executed on __init__)
    assert mgr._state["usage_plans"] == {"free_tier": "free-tier-plan"}
    # Missing defaults filled in
    assert mgr._state["plans"] == {}
    assert mgr._state["api_keys"] == {}
    assert mgr._state["plan_keys"] == {}


def test_load_state_falls_back_to_defaults_on_corrupt_json(mod, tmp_path):
    m, log_dir = mod
    state_file = os.path.join(log_dir, "rate_limit_usage_plans.json")
    with open(state_file, "w") as f:
        f.write("{not valid json")

    mgr = m.LocalUsagePlanManager()
    assert mgr._state == mgr._default_state()


# ---------------------------------------------------------------------------
# _save_state OSError branch (line 131-132)
# ---------------------------------------------------------------------------
def test_save_state_logs_on_oserror(mod, monkeypatch):
    m, _ = mod
    mgr = m.LocalUsagePlanManager()

    def boom(*a, **k):
        raise OSError("disk full")

    monkeypatch.setattr(m, "open", boom, raising=False)
    # Should swallow OSError (logged) and not raise.
    mgr._save_state()
    # State object itself untouched.
    assert "usage_plans" in mgr._state


# ---------------------------------------------------------------------------
# create_usage_plans: API-gateway association branch (line 164)
# ---------------------------------------------------------------------------
def test_create_usage_plans_associates_api_gateway_id(mod, monkeypatch):
    m, _ = mod
    monkeypatch.setenv("API_GATEWAY_ID", "api-xyz")
    mgr = m.LocalUsagePlanManager()
    assert mgr.api_id == "api-xyz"

    plans = _run(mgr.create_usage_plans())
    assert set(plans) == {"free_tier", "premium_tier", "enterprise_tier"}
    # The api gateway id must be attached to every plan's key list (line 164).
    for plan_id in plans.values():
        assert "api-xyz" in mgr._state["plan_keys"][plan_id]

    # Re-running must NOT duplicate the api id (the `not in` guard on line 163).
    _run(mgr.create_usage_plans())
    for plan_id in plans.values():
        assert mgr._state["plan_keys"][plan_id].count("api-xyz") == 1


# ---------------------------------------------------------------------------
# create_usage_plans: per-plan exception branch (lines 170-171)
# ---------------------------------------------------------------------------
def test_create_usage_plans_records_error_but_continues(mod, monkeypatch):
    m, _ = mod
    mgr = m.LocalUsagePlanManager()

    real_plans = mgr._state["plans"]

    class ExplodingPlans(dict):
        def __setitem__(self, key, value):
            # Fail only for the very first plan (free tier).
            if key == "free-tier-plan":
                raise RuntimeError("boom")
            return real_plans.__setitem__(key, value)

    mgr._state["plans"] = ExplodingPlans()
    result = _run(mgr.create_usage_plans())
    # Free tier failed inside the loop (170-171) so it is absent, others created.
    assert "free_tier" not in result
    assert "premium_tier" in result
    assert "enterprise_tier" in result


# ---------------------------------------------------------------------------
# get_usage_plans: exception branch (lines 182-184)
# ---------------------------------------------------------------------------
def test_get_usage_plans_returns_empty_on_error(mod, monkeypatch):
    m, _ = mod
    mgr = m.LocalUsagePlanManager()
    # Force dict() over the value to raise.
    mgr._state["usage_plans"] = 12345  # dict(int) -> TypeError
    assert _run(mgr.get_usage_plans()) == {}


# ---------------------------------------------------------------------------
# create_api_key_for_user: exception branch (lines 211-215)
# ---------------------------------------------------------------------------
def test_create_api_key_for_user_returns_none_on_error(mod, monkeypatch):
    m, _ = mod
    mgr = m.LocalUsagePlanManager()
    # Make the api_keys store raise on assignment.

    class Boom(dict):
        def __setitem__(self, *a, **k):
            raise RuntimeError("cannot store")

    mgr._state["api_keys"] = Boom()
    assert _run(mgr.create_api_key_for_user("u1", "k1")) is None


def test_create_api_key_for_user_success(mod):
    m, _ = mod
    mgr = m.LocalUsagePlanManager()
    key_id = _run(mgr.create_api_key_for_user("u1", "secret"))
    assert key_id == "key-u1"
    assert mgr._state["api_keys"]["key-u1"]["value"] == "secret"
    assert mgr._state["api_keys"]["key-u1"]["tags"]["user_id"] == "u1"


# ---------------------------------------------------------------------------
# assign_user_to_plan: unknown tier / plan-missing / key-fail branches
# ---------------------------------------------------------------------------
def test_assign_user_unknown_tier(mod):
    m, _ = mod
    mgr = m.LocalUsagePlanManager()
    assert _run(mgr.assign_user_to_plan("u1", "platinum", "k")) is False


def test_assign_user_plan_not_found(mod):
    m, _ = mod
    mgr = m.LocalUsagePlanManager()
    # No plans created, so lookup returns None -> line 235-236.
    assert _run(mgr.assign_user_to_plan("u1", "free", "k")) is False


def test_assign_user_key_creation_fails(mod, monkeypatch):
    m, _ = mod
    mgr = m.LocalUsagePlanManager()
    _run(mgr.create_usage_plans())

    async def fail_key(user_id, api_key_value):
        return None

    monkeypatch.setattr(mgr, "create_api_key_for_user", fail_key)
    # plan exists but key creation returns None -> line 240.
    assert _run(mgr.assign_user_to_plan("u1", "free", "k")) is False


def test_assign_user_outer_exception(mod, monkeypatch):
    m, _ = mod
    mgr = m.LocalUsagePlanManager()
    _run(mgr.create_usage_plans())

    async def boom():
        raise RuntimeError("lookup exploded")

    monkeypatch.setattr(mgr, "get_usage_plans", boom)
    # Exception inside try -> lines 255-259.
    assert _run(mgr.assign_user_to_plan("u1", "free", "k")) is False


def test_assign_user_success(mod):
    m, _ = mod
    mgr = m.LocalUsagePlanManager()
    _run(mgr.create_usage_plans())
    assert _run(mgr.assign_user_to_plan("u1", "premium", "apikey")) is True
    plan_id = mgr._state["usage_plans"]["premium_tier"]
    assert "key-u1" in mgr._state["plan_keys"][plan_id]


# ---------------------------------------------------------------------------
# update_user_tier: no user key / remove-old-plan exception / outer exception
# ---------------------------------------------------------------------------
def test_update_user_tier_no_existing_key(mod):
    m, _ = mod
    mgr = m.LocalUsagePlanManager()
    _run(mgr.create_usage_plans())
    # No API key stored for this user -> lines 273-274.
    assert _run(mgr.update_user_tier("ghost", "free", "premium")) is False


def test_update_user_tier_remove_from_old_plan_exception(mod, monkeypatch):
    m, _ = mod
    mgr = m.LocalUsagePlanManager()
    _run(mgr.create_usage_plans())
    _run(mgr.assign_user_to_plan("u1", "free", "apikey"))

    free_plan_id = mgr._state["usage_plans"]["free_tier"]

    class BadList(list):
        def remove(self, *a, **k):
            raise RuntimeError("cannot remove")

        def __contains__(self, item):
            return True  # force the remove() call path

    mgr._state["plan_keys"][free_plan_id] = BadList(["key-u1"])
    # remove() raises -> warning branch 286-287, then still tries to add to new plan.
    result = _run(mgr.update_user_tier("u1", "free", "premium"))
    assert result is True
    prem_plan_id = mgr._state["usage_plans"]["premium_tier"]
    assert "key-u1" in mgr._state["plan_keys"][prem_plan_id]


def test_update_user_tier_removes_from_old_plan_and_saves(mod):
    m, _ = mod
    mgr = m.LocalUsagePlanManager()
    _run(mgr.create_usage_plans())
    _run(mgr.assign_user_to_plan("u1", "free", "apikey"))

    free_plan_id = mgr._state["usage_plans"]["free_tier"]
    # Ensure the key is present in the old plan so remove() runs and _save_state
    # (line 285) is reached on the success path.
    assert "key-u1" in mgr._state["plan_keys"][free_plan_id]

    result = _run(mgr.update_user_tier("u1", "free", "premium"))
    assert result is True
    # Removed from old plan...
    assert "key-u1" not in mgr._state["plan_keys"][free_plan_id]
    # ...and added to the new plan.
    prem_plan_id = mgr._state["usage_plans"]["premium_tier"]
    assert "key-u1" in mgr._state["plan_keys"][prem_plan_id]


def test_update_user_tier_outer_exception(mod, monkeypatch):
    m, _ = mod
    mgr = m.LocalUsagePlanManager()
    _run(mgr.create_usage_plans())
    _run(mgr.assign_user_to_plan("u1", "free", "apikey"))

    # Make iteration over api_keys.values() raise -> lines 294-296.
    class BadDict(dict):
        def values(self):
            raise RuntimeError("iteration exploded")

    mgr._state["api_keys"] = BadDict(mgr._state["api_keys"])
    assert _run(mgr.update_user_tier("u1", "free", "premium")) is False


# ---------------------------------------------------------------------------
# get_usage_statistics: key-not-found / aggregation window / exception
# ---------------------------------------------------------------------------
def test_get_usage_statistics_key_not_found(mod):
    m, _ = mod
    mgr = m.LocalUsagePlanManager()
    # No matching api key -> lines 319-320.
    assert _run(mgr.get_usage_statistics("missing-key", "2026-01-01", "2026-12-31")) == {}


def test_get_usage_statistics_aggregates_window(mod):
    m, log_dir = mod
    mgr = m.LocalUsagePlanManager()
    metrics = m.LocalMetricsRecorder()
    _run(mgr.create_usage_plans())
    _run(mgr.assign_user_to_plan("uZ", "free", "apikey-z"))

    # Two in-window RequestCount records for uZ, plus out-of-window + other user.
    recs = [
        {"metric_name": "RequestCount", "user_id": "uZ", "value": 10,
         "timestamp": "2026-03-01T00:00:00"},
        {"metric_name": "RequestCount", "user_id": "uZ", "value": 5,
         "timestamp": "2026-03-02T00:00:00"},
        {"metric_name": "RequestCount", "user_id": "uZ", "value": 999,
         "timestamp": "2026-01-01T00:00:00"},  # before start -> excluded
        {"metric_name": "RequestCount", "user_id": "uZ", "value": 777,
         "timestamp": "2026-12-31T00:00:00"},  # after end -> excluded
        {"metric_name": "RequestCount", "user_id": "other", "value": 42,
         "timestamp": "2026-03-01T00:00:00"},  # other user -> excluded
        {"metric_name": "RateLimitViolations", "user_id": "uZ", "value": 3,
         "timestamp": "2026-03-01T00:00:00"},  # wrong metric -> excluded
    ]
    with open(metrics.metrics_file, "a") as f:
        for r in recs:
            f.write(json.dumps(r) + "\n")

    stats = _run(mgr.get_usage_statistics("apikey-z", "2026-02-01", "2026-06-01"))
    assert stats["total_requests"] == 15
    assert stats["daily_breakdown"] == {"2026-03-01": 10, "2026-03-02": 5}
    assert stats["period"] == "2026-02-01 to 2026-06-01"
    assert stats["start_date"] == "2026-02-01"
    assert stats["end_date"] == "2026-06-01"


def test_get_usage_statistics_exception(mod, monkeypatch):
    m, _ = mod
    mgr = m.LocalUsagePlanManager()

    class BadDict(dict):
        def values(self):
            raise RuntimeError("iteration exploded")

    mgr._state["api_keys"] = BadDict()
    # Exception inside try -> lines 336-338.
    assert _run(mgr.get_usage_statistics("k", "2026-01-01", "2026-12-31")) == {}


# ---------------------------------------------------------------------------
# monitor_throttling_events (lines 342-356)
# ---------------------------------------------------------------------------
def test_monitor_throttling_events(mod, monkeypatch):
    m, _ = mod
    monkeypatch.setenv("API_GATEWAY_ID", "api-mon")
    monkeypatch.setenv("API_GATEWAY_STAGE", "staging")
    mgr = m.LocalUsagePlanManager()
    events = _run(mgr.monitor_throttling_events())
    assert isinstance(events, list) and len(events) == 1
    ev = events[0]
    assert ev["api_id"] == "api-mon"
    assert ev["stage"] == "staging"
    assert ev["throttled_requests"] == 0
    assert ev["total_requests"] == 0
    assert ev["throttle_rate"] == 0.0
    assert "timestamp" in ev


def test_monitor_throttling_events_exception(mod, monkeypatch):
    m, _ = mod
    mgr = m.LocalUsagePlanManager()

    class BoomDateTime:
        @staticmethod
        def now(*a, **k):
            raise RuntimeError("clock exploded")

    # Force the try body to raise -> exception handler (lines 354-356) -> [].
    monkeypatch.setattr(m, "datetime", BoomDateTime)
    assert _run(mgr.monitor_throttling_events()) == []


# ---------------------------------------------------------------------------
# _aggregate_request_counts: skip-blank / bad-json / metric filter branches
# ---------------------------------------------------------------------------
def test_aggregate_request_counts_branches(mod):
    m, log_dir = mod
    metrics = m.LocalMetricsRecorder()
    lines = [
        "",  # blank -> skipped (line 375)
        "   ",  # whitespace -> skipped
        "{not json}",  # bad json -> skipped (378-379)
        json.dumps({"metric_name": "Other", "user_id": "u", "value": 1,
                    "timestamp": "2026-05-01T00:00:00"}),  # wrong metric -> 383
        json.dumps({"metric_name": "RequestCount", "user_id": "u", "value": 2,
                    "timestamp": "2026-05-01T00:00:00"}),  # counted
        json.dumps({"metric_name": "RequestCount", "user_id": "other", "value": 8,
                    "timestamp": "2026-05-01T00:00:00"}),  # other user -> 387
        json.dumps({"metric_name": "RequestCount", "user_id": "u", "value": 100,
                    "timestamp": "2026-01-01T00:00:00"}),  # before start -> 389
        json.dumps({"metric_name": "RequestCount", "user_id": "u", "value": 200,
                    "timestamp": "2026-12-31T00:00:00"}),  # after end -> 391-392
    ]
    with open(metrics.metrics_file, "w") as f:
        f.write("\n".join(lines) + "\n")

    result = m._aggregate_request_counts("u", "2026-03-01", "2026-06-01")
    assert result == {"2026-05-01": 2}


def test_aggregate_request_counts_missing_file(mod, monkeypatch):
    m, _ = mod
    # Point the metrics path at a nonexistent file -> FileNotFoundError branch.
    monkeypatch.setattr(m, "_metrics_file", lambda: "/nonexistent/does/not/exist.jsonl")
    assert m._aggregate_request_counts("u", "2026-01-01", "2026-12-31") == {}


def test_aggregate_request_counts_no_user_filter(mod):
    m, _ = mod
    metrics = m.LocalMetricsRecorder()
    with open(metrics.metrics_file, "w") as f:
        f.write(json.dumps({"metric_name": "RequestCount", "user_id": "a",
                            "value": 3, "timestamp": "2026-05-01T00:00:00"}) + "\n")
        f.write(json.dumps({"metric_name": "RequestCount", "user_id": "b",
                            "value": 4, "timestamp": "2026-05-01T00:00:00"}) + "\n")
    # user_id=None -> both users aggregated together.
    result = m._aggregate_request_counts(None, "2026-01-01", "2026-12-31")
    assert result == {"2026-05-01": 7}


# ---------------------------------------------------------------------------
# LocalMetricsRecorder.put_rate_limit_metrics: success + exception (452-453)
# ---------------------------------------------------------------------------
def test_put_rate_limit_metrics_writes_two_records(mod):
    m, _ = mod
    metrics = m.LocalMetricsRecorder()
    _run(metrics.put_rate_limit_metrics("u9", "premium", 50, 4))
    recs = [json.loads(l) for l in open(metrics.metrics_file) if l.strip()]
    by_name = {r["metric_name"]: r for r in recs}
    assert by_name["RequestCount"]["value"] == 50
    assert by_name["RateLimitViolations"]["value"] == 4
    assert by_name["RequestCount"]["tier"] == "premium"


def test_put_rate_limit_metrics_exception(mod, monkeypatch):
    m, _ = mod
    metrics = m.LocalMetricsRecorder()

    def boom(record):
        raise OSError("write failed")

    monkeypatch.setattr(metrics, "_append_metric", boom)
    # Must swallow the error (lines 452-453) and not raise.
    _run(metrics.put_rate_limit_metrics("u", "free", 1, 0))


# ---------------------------------------------------------------------------
# create_rate_limit_alarms: success + exception (478-479)
# ---------------------------------------------------------------------------
def test_create_rate_limit_alarms_success(mod):
    m, log_dir = mod
    metrics = m.LocalMetricsRecorder()
    _run(metrics.create_rate_limit_alarms())
    with open(metrics.alarms_file) as f:
        data = json.load(f)
    assert data["alarms"][0]["MetricName"] == "RateLimitViolations"
    assert data["alarms"][0]["Threshold"] == 100.0


def test_create_rate_limit_alarms_exception(mod, monkeypatch):
    m, _ = mod
    metrics = m.LocalMetricsRecorder()

    def boom(*a, **k):
        raise OSError("cannot open alarms file")

    monkeypatch.setattr(m, "open", boom, raising=False)
    # Must swallow the error (478-479) and not raise.
    _run(metrics.create_rate_limit_alarms())


# ---------------------------------------------------------------------------
# setup_aws_rate_limiting: success + failure branch (510-512)
# ---------------------------------------------------------------------------
def test_setup_success(mod):
    m, _ = mod
    assert _run(m.setup_aws_rate_limiting()) is True


def test_setup_failure_returns_false(mod, monkeypatch):
    m, _ = mod

    def boom():
        raise RuntimeError("factory exploded")

    monkeypatch.setattr(m, "get_api_gateway_manager", boom)
    # Exception -> lines 510-512, returns False.
    assert _run(m.setup_aws_rate_limiting()) is False


# ---------------------------------------------------------------------------
# factory helpers
# ---------------------------------------------------------------------------
def test_factories_return_local_instances(mod):
    m, _ = mod
    assert isinstance(m.get_api_gateway_manager(), m.LocalUsagePlanManager)
    assert isinstance(m.get_cloudwatch_metrics(), m.LocalMetricsRecorder)
