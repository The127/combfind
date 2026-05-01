def recall_at_k(expected: list[str], retrieved: list[str], k: int) -> float:
    """Fraction of expected items that appear in retrieved[:k]."""
    if not expected:
        return 1.0
    retrieved_set = set(retrieved[:k])
    hits = sum(1 for e in expected if e in retrieved_set)
    return hits / len(expected)
