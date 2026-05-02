import json
from collections import defaultdict
from pathlib import Path

import numpy as np

from combfind import telemetry
from combfind.db import get_connection

_TARGET_CONCEPT_SIZE = 20  # aim for ~this many symbols per concept


def run(db_path: str, *, noise: str = "singleton", **_) -> None:
    conn = get_connection(db_path)

    rows = conn.execute(
        """SELECT se.symbol_id, se.embedding, f.path
           FROM symbol_embeddings se
           JOIN symbols s ON s.id = se.symbol_id
           JOIN files f ON f.id = s.file_id"""
    ).fetchall()

    if not rows:
        raise RuntimeError("cluster requires symbol_embeddings — run embed first")

    # group by package (parent directory of file)
    packages: dict[str, list] = defaultdict(list)
    for row in rows:
        pkg = str(Path(row["path"]).parent)
        packages[pkg].append(row)

    conn.execute("DELETE FROM concepts")
    conn.execute("DELETE FROM concept_members")

    total_concepts = 0
    for pkg, pkg_rows in sorted(packages.items()):
        symbol_ids = [r["symbol_id"] for r in pkg_rows]
        embeddings = np.array(
            [np.frombuffer(r["embedding"], dtype=np.float32) for r in pkg_rows]
        )

        k = max(1, round(len(pkg_rows) / _TARGET_CONCEPT_SIZE))
        telemetry.debug("cluster package", package=pkg, symbols=len(pkg_rows), k=k)
        if k == 1:
            _insert_concept(conn, symbol_ids, embeddings, list(range(len(pkg_rows))))
            total_concepts += 1
        else:
            labels = _kmeans(embeddings, k)
            for cluster_id in range(k):
                indices = [i for i, label in enumerate(labels) if label == cluster_id]
                if indices:
                    _insert_concept(conn, symbol_ids, embeddings, indices)
                    total_concepts += 1

    for key, val in (
        ("noise_strategy", noise),
        ("cluster_min_size", _TARGET_CONCEPT_SIZE),
    ):
        conn.execute(
            "INSERT OR REPLACE INTO build_config(key, value) VALUES (?,?)",
            (key, json.dumps(val)),
        )

    conn.commit()
    conn.close()
    telemetry.info("cluster complete", concepts=total_concepts, packages=len(packages))


def _kmeans(embeddings: np.ndarray, k: int) -> np.ndarray:
    try:
        from sklearn.cluster import KMeans

        km = KMeans(n_clusters=k, n_init=3, random_state=42)
        return km.fit_predict(embeddings)
    except ImportError:
        # fallback: assign round-robin if sklearn unavailable (shouldn't happen)
        return np.array([i % k for i in range(len(embeddings))])


def _insert_concept(
    conn,
    symbol_ids: list,
    embeddings: np.ndarray,
    indices: list,
    *,
    name: str | None = None,
) -> None:
    member_embs = embeddings[indices]
    centroid = member_embs.mean(axis=0).astype(np.float32)

    conn.execute(
        "INSERT INTO concepts(name, member_count, centroid) VALUES (?,?,?)",
        (name, len(indices), centroid.tobytes()),
    )
    concept_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    for idx in indices:
        dist = float(np.linalg.norm(embeddings[idx] - centroid))
        conn.execute(
            "INSERT INTO concept_members(concept_id, symbol_id, distance_to_centroid) "
            "VALUES (?,?,?)",
            (concept_id, symbol_ids[idx], dist),
        )
