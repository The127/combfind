import numpy as np

import combfind.pipeline.cluster as cluster_mod
from combfind.db import create_schema, get_connection

DIM = 8


def _make_db(tmp_path, file_symbol_map: dict[str, int]) -> str:
    """file_symbol_map: {file_path: n_symbols}"""
    db_path = str(tmp_path / "test.db")
    conn = get_connection(db_path)
    create_schema(conn)

    for path, n in file_symbol_map.items():
        conn.execute(
            "INSERT INTO files(path, language, content_hash, size_bytes) "
            "VALUES (?,?,?,?)",
            (path, "python", path, 10),
        )
        file_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        for i in range(n):
            conn.execute(
                "INSERT INTO symbols(file_id, name, kind, start_line, end_line) "
                "VALUES (?,?,?,?,?)",
                (file_id, f"sym_{path}_{i}", "function", i + 1, i + 1),
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


def test_single_package_one_concept(tmp_path):
    db = _make_db(tmp_path, {"pkg/a.py": 5, "pkg/b.py": 5})
    cluster_mod.run(db)
    conn = get_connection(db)
    assert conn.execute("SELECT COUNT(*) FROM concepts").fetchone()[0] == 1
    conn.close()


def test_two_packages_two_concepts(tmp_path):
    db = _make_db(tmp_path, {"pkg_a/a.py": 5, "pkg_b/b.py": 5})
    cluster_mod.run(db)
    conn = get_connection(db)
    assert conn.execute("SELECT COUNT(*) FROM concepts").fetchone()[0] == 2
    conn.close()


def test_all_symbols_in_members(tmp_path):
    db = _make_db(tmp_path, {"pkg_a/a.py": 6, "pkg_b/b.py": 4})
    cluster_mod.run(db)
    conn = get_connection(db)
    assert conn.execute("SELECT COUNT(*) FROM concept_members").fetchone()[0] == 10
    conn.close()


def test_centroids_stored(tmp_path):
    db = _make_db(tmp_path, {"pkg/a.py": 5})
    cluster_mod.run(db)
    conn = get_connection(db)
    blobs = [r[0] for r in conn.execute("SELECT centroid FROM concepts").fetchall()]
    assert all(len(b) == DIM * 4 for b in blobs)
    conn.close()


def test_large_package_sub_clustered(tmp_path, monkeypatch):
    monkeypatch.setattr(cluster_mod, "_TARGET_CONCEPT_SIZE", 10)
    db = _make_db(tmp_path, {"pkg/a.py": 25})
    cluster_mod.run(db)
    conn = get_connection(db)
    n = conn.execute("SELECT COUNT(*) FROM concepts").fetchone()[0]
    conn.close()
    assert n >= 2


def test_idempotent(tmp_path):
    db = _make_db(tmp_path, {"pkg_a/a.py": 5, "pkg_b/b.py": 5})
    cluster_mod.run(db)
    cluster_mod.run(db)
    conn = get_connection(db)
    assert conn.execute("SELECT COUNT(*) FROM concepts").fetchone()[0] == 2
    conn.close()


def test_build_config_written(tmp_path):
    import json

    db = _make_db(tmp_path, {"pkg/a.py": 5})
    cluster_mod.run(db)
    conn = get_connection(db)
    cfg = {
        r["key"]: json.loads(r["value"])
        for r in conn.execute("SELECT key, value FROM build_config").fetchall()
    }
    conn.close()
    assert "noise_strategy" in cfg
    assert "cluster_min_size" in cfg
