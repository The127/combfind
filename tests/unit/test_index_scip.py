import pytest

from combfind.pipeline.indexers import containing_symbol
from combfind.pipeline.indexers.go import _scip_symbol_to_qname as go_qname
from combfind.pipeline.indexers.python import _scip_symbol_to_qname as py_qname


# ---------------------------------------------------------------------------
# Go SCIP symbol → qualified_name
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "symbol, expected",
    [
        ("scip-go go github.com/x/y v1.0 internal/auth/Validate().", "auth.Validate"),
        ("scip-go go github.com/x/y v1.0 internal/auth/Service#Validate().", "auth.Service.Validate"),
        ("scip-go go github.com/x/y v1.0 internal/auth/Service#", "auth.Service"),
        ("scip-go go github.com/x/y v1.0 query/Run().", "query.Run"),
        ("local 42", None),
        ("scip-go go github.com/x/y", None),
        ("scip-go go github.com/x/y v1.0 internal/auth/", None),
    ],
)
def test_go_scip_symbol_to_qname(symbol, expected):
    assert go_qname(symbol) == expected


# ---------------------------------------------------------------------------
# Python SCIP symbol → qualified_name
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "symbol, expected",
    [
        (
            "scip-python python combfind 1.0.2 `combfind.pipeline.index`/run().",
            "combfind.pipeline.index.run",
        ),
        (
            "scip-python python combfind 1.0.2 `combfind.pipeline.indexers`/BaseIndexer#run().",
            "combfind.pipeline.indexers.BaseIndexer.run",
        ),
        (
            "scip-python python combfind 1.0.2 `combfind.pipeline.indexers`/BaseIndexer#",
            "combfind.pipeline.indexers.BaseIndexer",
        ),
        # module-level meta → None
        (
            "scip-python python combfind 1.0.2 `combfind.pipeline.index`/__init__:",
            None,
        ),
        # parameter → None
        (
            "scip-python python combfind 1.0.2 `combfind.pipeline.index`/run().(db_path)",
            None,
        ),
        ("local 42", None),
        ("scip-python python combfind 1.0.2", None),
    ],
)
def test_py_scip_symbol_to_qname(symbol, expected):
    assert py_qname(symbol) == expected


# ---------------------------------------------------------------------------
# containing_symbol
# ---------------------------------------------------------------------------


def _make(triples):
    syms = sorted(triples)
    starts = [s[0] for s in syms]
    return syms, starts


def test_containing_symbol_exact_start():
    syms, starts = _make([(1, 10, 101), (12, 20, 102)])
    assert containing_symbol(syms, starts, 1) == 101


def test_containing_symbol_mid_range():
    syms, starts = _make([(1, 10, 101), (12, 20, 102)])
    assert containing_symbol(syms, starts, 5) == 101


def test_containing_symbol_exact_end():
    syms, starts = _make([(1, 10, 101), (12, 20, 102)])
    assert containing_symbol(syms, starts, 10) == 101


def test_containing_symbol_between_ranges():
    syms, starts = _make([(1, 10, 101), (12, 20, 102)])
    assert containing_symbol(syms, starts, 11) is None


def test_containing_symbol_picks_innermost():
    syms, starts = _make([(1, 100, 101), (5, 20, 102)])
    assert containing_symbol(syms, starts, 10) == 102


def test_containing_symbol_before_all():
    syms, starts = _make([(5, 10, 101)])
    assert containing_symbol(syms, starts, 2) is None


def test_containing_symbol_after_all():
    syms, starts = _make([(1, 10, 101)])
    assert containing_symbol(syms, starts, 15) is None
