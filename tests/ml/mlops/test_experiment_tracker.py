from neuronews.ml.mlops.experiment import ExperimentTracker


def test_experiment_run_lifecycle():
    tracker = ExperimentTracker("exp1")
    with tracker.start_run("run-1") as r:
        tracker.log_param("run-1", "lr", "0.001")
        tracker.log_metric("run-1", "loss", 0.345)
        tracker.log_artifact("run-1", "/tmp/model.pt", "model_file")
        assert r.run_id == "run-1"
    ri = tracker.get_run("run-1")
    assert ri.end_time is not None
    assert ri.metrics["loss"] == 0.345
    assert ri.params["lr"] == "0.001"
    assert ri.artifacts["model_file"] == "/tmp/model.pt"
