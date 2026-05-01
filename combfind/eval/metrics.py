def recall_at_k(expected: list[str], retrieved: list[str], k: int) -> float:
    if not expected:
        return 1.0
    hits = sum(1 for e in expected if e in retrieved[:k])
    return hits / len(expected)
