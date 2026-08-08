from tiny_minds.evaluation import macro_f1, ndcg_at_k, precision, recall_at_k, top_k_accuracy


def test_calibration_metrics_are_deterministic() -> None:
    assert recall_at_k({"a", "b"}, ["a", "x", "b"], 2) == 0.5
    assert precision({"a"}, ["a", "x"]) == 0.5
    assert ndcg_at_k({"a": 3, "b": 1}, ["a", "b"], 2) == 1.0
    assert macro_f1(["a", "b"], ["a", "b"]) == 1.0
    assert top_k_accuracy(["a", "b"], [["a"], ["x", "b"]], 2) == 1.0
