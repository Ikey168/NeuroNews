from src.ml.training.trainer import SimpleTrainer
from src.ml.mlops.experiment import ExperimentTracker
from src.ml.registry.registry import ModelRegistry


def test_simple_trainer_registers_and_logs():
    tracker = ExperimentTracker("exp-ml")
    registry = ModelRegistry()
    trainer = SimpleTrainer(tracker, registry)
    reg_model, acc = trainer.train("run-42", data=[{"x":1}], epochs=3)
    assert acc > 0.6
    assert reg_model.version == 1
    run = tracker.get_run("run-42")
    assert "acc_epoch_3" in run.metrics
