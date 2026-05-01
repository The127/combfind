import json

import pytest

import combfind.eval.harness as harness_mod


def _fake_query(results):
    def _q(text, *, db_path, top_k, **kwargs):
        return results[:top_k]
    return _q


def _fixture_dir(tmp_path, cases: dict[str, tuple[str, dict]]) -> str:
    """Build a fixtures directory from {name: (input_text, expected_dict)}."""
    root = tmp_path / "fixtures"
    root.mkdir()
    for name, (text, expected) in cases.items():
        d = root / name
        d.mkdir()
        (d / "input.txt").write_text(text)
        (d / "expected.json").write_text(json.dumps(expected))
    return str(root)


RESULT_HIT = {
    "rank": 1, "concept": "Auth", "role": "implementation", "score": 0.9,
    "files": [{"path": "auth/service.py", "start_line": 1, "end_line": 50}],
    "symbols": ["AuthService.validate", "AuthService.refresh"],
    "why_relevant": "auth", "sibling_implementations": [],
}

RESULT_MISS = {
    "rank": 1, "concept": "DB", "role": "infrastructure", "score": 0.7,
    "files": [{"path": "db/pool.py", "start_line": 1, "end_line": 30}],
    "symbols": ["Pool.connect"],
    "why_relevant": "db", "sibling_implementations": [],
}


@pytest.fixture
def mock_query_hit(monkeypatch):
    monkeypatch.setattr(harness_mod, "query", _fake_query([RESULT_HIT]))


@pytest.fixture
def mock_query_miss(monkeypatch):
    monkeypatch.setattr(harness_mod, "query", _fake_query([RESULT_MISS]))


def test_perfect_file_recall(tmp_path, mock_query_hit):
    fixtures = _fixture_dir(tmp_path, {
        "case1": ("find auth code", {"files": ["auth/service.py"], "symbols": []})
    })
    agg = harness_mod.run(db_path="fake.db", fixtures_dir=fixtures, ks=[1])
    assert agg[1]["file_recall"] == 1.0


def test_perfect_symbol_recall(tmp_path, mock_query_hit):
    fixtures = _fixture_dir(tmp_path, {
        "case1": ("find auth code", {"files": [], "symbols": ["AuthService.validate"]})
    })
    agg = harness_mod.run(db_path="fake.db", fixtures_dir=fixtures, ks=[1])
    assert agg[1]["symbol_recall"] == 1.0


def test_zero_recall_on_miss(tmp_path, mock_query_miss):
    fixtures = _fixture_dir(tmp_path, {
        "case1": ("find auth code", {"files": ["auth/service.py"], "symbols": ["AuthService.validate"]})
    })
    agg = harness_mod.run(db_path="fake.db", fixtures_dir=fixtures, ks=[1])
    assert agg[1]["file_recall"] == 0.0
    assert agg[1]["symbol_recall"] == 0.0


def test_multiple_ks(tmp_path, monkeypatch):
    monkeypatch.setattr(harness_mod, "query", _fake_query([RESULT_HIT, RESULT_MISS]))
    fixtures = _fixture_dir(tmp_path, {
        "case1": ("find auth code", {"files": ["auth/service.py"], "symbols": []})
    })
    agg = harness_mod.run(db_path="fake.db", fixtures_dir=fixtures, ks=[1, 3])
    assert set(agg.keys()) == {1, 3}


def test_aggregate_over_multiple_fixtures(tmp_path, monkeypatch):
    monkeypatch.setattr(harness_mod, "query", _fake_query([RESULT_HIT]))
    # One fixture expects a hit, one expects something not in results
    fixtures = _fixture_dir(tmp_path, {
        "hit": ("find auth", {"files": ["auth/service.py"], "symbols": []}),
        "miss": ("find db", {"files": ["missing/file.py"], "symbols": []}),
    })
    agg = harness_mod.run(db_path="fake.db", fixtures_dir=fixtures, ks=[1])
    assert agg[1]["file_recall"] == pytest.approx(0.5)


def test_empty_fixtures_dir(tmp_path):
    (tmp_path / "fixtures").mkdir()
    agg = harness_mod.run(db_path="fake.db", fixtures_dir=str(tmp_path / "fixtures"), ks=[3])
    assert agg == {}


def test_skips_incomplete_fixture(tmp_path, mock_query_hit):
    root = tmp_path / "fixtures"
    root.mkdir()
    # Only input.txt, no expected.json
    incomplete = root / "bad"
    incomplete.mkdir()
    (incomplete / "input.txt").write_text("text")
    # Valid fixture
    valid = root / "good"
    valid.mkdir()
    (valid / "input.txt").write_text("find auth code")
    (valid / "expected.json").write_text(json.dumps({"files": ["auth/service.py"], "symbols": []}))

    agg = harness_mod.run(db_path="fake.db", fixtures_dir=str(root), ks=[1])
    assert agg[1]["file_recall"] == 1.0  # only the valid fixture counted


def test_returns_aggregate_dict(tmp_path, mock_query_hit):
    fixtures = _fixture_dir(tmp_path, {
        "case1": ("text", {"files": ["auth/service.py"], "symbols": ["AuthService.validate"]})
    })
    result = harness_mod.run(db_path="fake.db", fixtures_dir=fixtures, ks=[1, 3])
    for k in [1, 3]:
        assert "file_recall" in result[k]
        assert "symbol_recall" in result[k]
        assert 0.0 <= result[k]["file_recall"] <= 1.0
