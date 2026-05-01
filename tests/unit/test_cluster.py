import numpy as np
import pytest

import combfind.pipeline.cluster as cluster_mod
from combfind.db import create_schema, get_connection

N = 10
DIM = 8


@pytest.fixture
def env(tmp_path):
    db_path = str(tmp_path / "test.db")
    conn = get_connection(db_path)
    create_schema(conn)

    conn.execute(
        "INSERT INTO files(path, language, content_hash, size_bytes) VALUES ('f.py','python','h',10)"
    )
    file_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    for i in range(N):
        conn.execute(
            "INSERT INTO symbols(file_id, name, kind, signature, start_line, end_line)"
            " VALUES (?,?,?,?,?,?)",
            (file_id, f"sym_{i}", "function", f"def sym_{i}()", i * 2 + 1, i * 2 + 2),
        )
        sym_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        emb = np.random.rand(DIM).astype(np.float32)
        conn.execute(
            "INSERT INTO symbol_embeddings(symbol_id, embedding) VALUES (?,?)",
            (sym_id, emb.tobytes()),
        )

    conn.commit()
    conn.close()
    return db_path


def _make_fake_hdbscan(label_fn):
    class FakeHDBSCAN:
        def __init__(self, **kwargs):
            pass

        def fit_predict(self, X):
            return np.array([label_fn(i, len(X)) for i in range(len(X))])

    class FakeMod:
        HDBSCAN = FakeHDBSCAN

    return FakeMod


@pytest.fixture
def two_clusters(monkeypatch):
    monkeypatch.setattr(
        cluster_mod, "_hdbscan_mod",
        _make_fake_hdbscan(lambda i, n: 0 if i < n // 2 else 1),
    )


@pytest.fixture
def with_noise(monkeypatch):
    # first n-2 in cluster 0, last 2 are noise (-1)
    monkeypatch.setattr(
        cluster_mod, "_hdbscan_mod",
        _make_fake_hdbscan(lambda i, n: 0 if i < n - 2 else -1),
    )


def test_two_concepts_created(env, two_clusters):
    cluster_mod.run(env, cluster_min_size=2)
    conn = get_connection(env)
    assert conn.execute("SELECT COUNT(*) FROM concepts").fetchone()[0] == 2


def test_all_symbols_in_members(env, two_clusters):
    cluster_mod.run(env, cluster_min_size=2)
    conn = get_connection(env)
    assert conn.execute("SELECT COUNT(*) FROM concept_members").fetchone()[0] == N


def test_member_counts_match(env, two_clusters):
    cluster_mod.run(env, cluster_min_size=2)
    conn = get_connection(env)
    counts = sorted(
        r[0] for r in conn.execute("SELECT member_count FROM concepts").fetchall()
    )
    assert counts == [N // 2, N - N // 2]


def test_centroids_stored(env, two_clusters):
    cluster_mod.run(env, cluster_min_size=2)
    conn = get_connection(env)
    blobs = [r[0] for r in conn.execute("SELECT centroid FROM concepts").fetchall()]
    assert all(len(b) == DIM * 4 for b in blobs)


def test_noise_singleton(env, with_noise):
    cluster_mod.run(env, cluster_min_size=2, noise="singleton")
    conn = get_connection(env)
    n_concepts = conn.execute("SELECT COUNT(*) FROM concepts").fetchone()[0]
    n_members = conn.execute("SELECT COUNT(*) FROM concept_members").fetchone()[0]
    assert n_concepts == 3  # 1 real + 2 singletons
    assert n_members == N


def test_noise_merge(env, with_noise):
    cluster_mod.run(env, cluster_min_size=2, noise="merge")
    conn = get_connection(env)
    names = [r[0] for r in conn.execute("SELECT name FROM concepts ORDER BY name").fetchall()]
    assert "uncategorized" in names
    assert conn.execute("SELECT COUNT(*) FROM concepts").fetchone()[0] == 2


def test_noise_drop(env, with_noise):
    cluster_mod.run(env, cluster_min_size=2, noise="drop")
    conn = get_connection(env)
    assert conn.execute("SELECT COUNT(*) FROM concept_members").fetchone()[0] == N - 2


def test_idempotent(env, two_clusters):
    cluster_mod.run(env, cluster_min_size=2)
    cluster_mod.run(env, cluster_min_size=2)
    conn = get_connection(env)
    assert conn.execute("SELECT COUNT(*) FROM concepts").fetchone()[0] == 2


def test_build_config_written(env, two_clusters):
    cluster_mod.run(env, cluster_min_size=3, noise="merge")
    conn = get_connection(env)
    import json
    cfg = {r["key"]: json.loads(r["value"]) for r in conn.execute("SELECT key, value FROM build_config").fetchall()}
    assert cfg["noise_strategy"] == "merge"
    assert cfg["cluster_min_size"] == 3
