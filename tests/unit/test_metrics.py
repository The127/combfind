from combfind.eval.metrics import recall_at_k


def test_perfect_recall():
    assert recall_at_k(["a", "b"], ["a", "b", "c"], k=3) == 1.0


def test_partial_recall():
    assert recall_at_k(["a", "b"], ["a", "c", "d"], k=3) == 0.5


def test_zero_recall():
    assert recall_at_k(["a", "b"], ["c", "d"], k=2) == 0.0


def test_empty_expected_is_perfect():
    assert recall_at_k([], ["a", "b"], k=2) == 1.0


def test_k_caps_retrieved():
    # "b" is in retrieved but beyond k=1, so not counted
    assert recall_at_k(["b"], ["a", "b"], k=1) == 0.0


def test_k_includes_first_item():
    assert recall_at_k(["a"], ["a", "b"], k=1) == 1.0


def test_duplicates_in_retrieved_do_not_inflate():
    assert recall_at_k(["a"], ["a", "a", "a"], k=3) == 1.0


def test_order_in_expected_irrelevant():
    assert recall_at_k(["b", "a"], ["a", "b"], k=2) == 1.0
