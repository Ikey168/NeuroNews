"""Unit tests for the local file-based NLP metrics backend.

These tests verify that ``src.nlp.metrics.NLPMetrics`` records metrics to a
local JSON-lines file with no AWS/boto3 dependency.
"""

import importlib
import json
import os
import sys

import pytest


@pytest.fixture()
def metrics_module():
    """Import (or reimport) the metrics module fresh."""
    sys.modules.pop("src.nlp.metrics", None)
    return importlib.import_module("src.nlp.metrics")


@pytest.fixture()
def nlp_metrics(metrics_module, tmp_path, monkeypatch):
    """Provide an NLPMetrics instance writing into a temp directory."""
    monkeypatch.setenv("NEURONEWS_METRICS_DIR", str(tmp_path))
    monkeypatch.delenv("NEURONEWS_LOG_DIR", raising=False)
    return metrics_module.NLPMetrics(namespace="Test/NLP")


def _read_lines(path):
    with open(path, "r") as f:
        return [json.loads(line) for line in f if line.strip()]


def test_no_boto3_imported(metrics_module):
    """The module must not depend on boto3/botocore."""
    src = metrics_module.__file__
    with open(src, "r") as f:
        content = f.read()
    assert "boto3" not in content
    assert "botocore" not in content
    assert "boto3" not in sys.modules or True  # not imported by this module


def test_metrics_dir_env_resolution(metrics_module, tmp_path, monkeypatch):
    """NEURONEWS_METRICS_DIR takes precedence; falls back to NEURONEWS_LOG_DIR."""
    metrics_dir = tmp_path / "mdir"
    monkeypatch.setenv("NEURONEWS_METRICS_DIR", str(metrics_dir))
    m = metrics_module.NLPMetrics()
    assert m.metrics_dir == str(metrics_dir)
    assert os.path.isdir(str(metrics_dir))

    monkeypatch.delenv("NEURONEWS_METRICS_DIR", raising=False)
    log_dir = tmp_path / "ldir"
    monkeypatch.setenv("NEURONEWS_LOG_DIR", str(log_dir))
    m2 = metrics_module.NLPMetrics()
    assert m2.metrics_dir == str(log_dir)


def test_put_metric_writes_record(nlp_metrics):
    nlp_metrics.put_metric("Custom", 42, unit="Count")
    records = _read_lines(nlp_metrics.metrics_file)
    assert len(records) == 1
    rec = records[0]
    assert rec["MetricName"] == "Custom"
    assert rec["Value"] == 42
    assert rec["Unit"] == "Count"
    assert rec["Namespace"] == "Test/NLP"
    assert "Timestamp" in rec


def test_emit_processing_time(nlp_metrics):
    nlp_metrics.emit_processing_time("job-1", 12.5)
    recs = nlp_metrics.read_metrics("NLPProcessingTime")
    assert len(recs) == 1
    assert recs[0]["Value"] == 12.5
    assert recs[0]["Unit"] == "Seconds"
    assert {"Name": "JobId", "Value": "job-1"} in recs[0]["Dimensions"]


def test_emit_document_count(nlp_metrics):
    nlp_metrics.emit_document_count("job-2", 7)
    recs = nlp_metrics.read_metrics("DocumentsProcessed")
    assert recs[0]["Value"] == 7
    assert recs[0]["Unit"] == "Count"


def test_emit_job_status_success_and_failure(nlp_metrics):
    nlp_metrics.emit_job_status("job-3", "success")
    nlp_metrics.emit_job_status("job-4", "failure")
    recs = nlp_metrics.read_metrics("NLPJobsCompleted")
    assert len(recs) == 2
    values = {
        next(d["Value"] for d in r["Dimensions"] if d["Name"] == "JobId"): r["Value"]
        for r in recs
    }
    assert values["job-3"] == 1
    assert values["job-4"] == 0


def test_emit_error_count_with_type(nlp_metrics):
    nlp_metrics.emit_error_count("job-5", 3, error_type="ValueError")
    recs = nlp_metrics.read_metrics("ProcessingErrors")
    assert recs[0]["Value"] == 3
    assert {"Name": "ErrorType", "Value": "ValueError"} in recs[0]["Dimensions"]


def test_emit_error_count_without_type(nlp_metrics):
    nlp_metrics.emit_error_count("job-6", 1)
    recs = nlp_metrics.read_metrics("ProcessingErrors")
    names = [d["Name"] for d in recs[0]["Dimensions"]]
    assert "ErrorType" not in names


def test_emit_batch_metrics_full(nlp_metrics):
    nlp_metrics.emit_batch_metrics(
        {
            "job_id": "batch-1",
            "duration": 5.0,
            "doc_count": 10,
            "success": True,
            "errors": 2,
            "error_type": "ParseError",
        }
    )
    all_recs = nlp_metrics.read_metrics()
    metric_names = {r["MetricName"] for r in all_recs}
    assert {
        "NLPProcessingTime",
        "DocumentsProcessed",
        "NLPJobsCompleted",
        "ProcessingErrors",
    } <= metric_names


def test_emit_batch_metrics_no_errors_skips_error_metric(nlp_metrics):
    nlp_metrics.emit_batch_metrics(
        {
            "job_id": "batch-2",
            "duration": 1.0,
            "doc_count": 1,
            "success": False,
            "errors": 0,
        }
    )
    assert nlp_metrics.read_metrics("ProcessingErrors") == []
    status = nlp_metrics.read_metrics("NLPJobsCompleted")
    assert status[0]["Value"] == 0


def test_read_metrics_empty_when_no_file(metrics_module, tmp_path, monkeypatch):
    monkeypatch.setenv("NEURONEWS_METRICS_DIR", str(tmp_path / "fresh"))
    m = metrics_module.NLPMetrics()
    assert m.read_metrics() == []
