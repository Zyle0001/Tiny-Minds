from __future__ import annotations

import math
from collections import defaultdict
from typing import Iterable


def recall_at_k(expected: set[str], ranked: list[str], k: int) -> float:
    return len(expected & set(ranked[:k])) / max(1, len(expected))


def precision(expected: set[str], predicted: Iterable[str]) -> float:
    values = list(predicted)
    return sum(item in expected for item in values) / max(1, len(values))


def ndcg_at_k(relevance: dict[str, float], ranked: list[str], k: int) -> float:
    def dcg(items: list[str]) -> float:
        return sum((2 ** relevance.get(item, 0.0) - 1) / math.log2(index + 2) for index, item in enumerate(items[:k]))
    ideal = sorted(relevance, key=relevance.get, reverse=True)
    denominator = dcg(ideal)
    return dcg(ranked) / denominator if denominator else 0.0


def macro_f1(expected: list[str], predicted: list[str]) -> float:
    if len(expected) != len(predicted):
        raise ValueError("expected and predicted labels must have equal length")
    labels = sorted(set(expected) | set(predicted))
    values = []
    for label in labels:
        true_positive = sum(a == label and b == label for a, b in zip(expected, predicted))
        false_positive = sum(a != label and b == label for a, b in zip(expected, predicted))
        false_negative = sum(a == label and b != label for a, b in zip(expected, predicted))
        p = true_positive / max(1, true_positive + false_positive)
        r = true_positive / max(1, true_positive + false_negative)
        values.append(2 * p * r / (p + r) if p + r else 0.0)
    return sum(values) / max(1, len(values))


def top_k_accuracy(expected: list[str], ranked: list[list[str]], k: int) -> float:
    if len(expected) != len(ranked):
        raise ValueError("expected and ranked outputs must have equal length")
    return sum(label in choices[:k] for label, choices in zip(expected, ranked)) / max(1, len(expected))
