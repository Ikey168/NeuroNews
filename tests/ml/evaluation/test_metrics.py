from neuronews.ml.evaluation.metrics import compute_accuracy, compute_precision


def test_metrics_accuracy_precision():
    y_true = [0,1,1,0]
    y_pred = [0,1,0,0]
    acc = compute_accuracy(y_true, y_pred)
    prec = compute_precision(y_true, y_pred)
    assert 0 <= acc <= 1
    assert 0 <= prec <= 1

def test_metrics_empty():
    assert compute_accuracy([], []) == 0.0
    assert compute_precision([0], [0]) == 0.0
