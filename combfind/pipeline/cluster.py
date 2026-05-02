import hashlib
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

    prev_centroids = _load_prev_centroids(conn)
    prev_labels = _load_prev_labels(conn)

    conn.execute("DELETE FROM concepts")
    conn.execute("DELETE FROM concept_members")

    total_concepts = 0
    reused = 0
    for pkg, pkg_rows in sorted(packages.items()):
        symbol_ids = [r["symbol_id"] for r in pkg_rows]
        embeddings = np.array(
            [np.frombuffer(r["embedding"], dtype=np.float32) for r in pkg_rows]
        )

        k = max(1, round(len(pkg_rows) / _TARGET_CONCEPT_SIZE))
        telemetry.debug("cluster package", package=pkg, symbols=len(pkg_rows), k=k)
        if k == 1:
            mh = _member_hash(conn, symbol_ids)
            label = prev_labels.get(mh)
            _insert_concept(conn, symbol_ids, embeddings, list(range(len(pkg_rows))), member_hash=mh, label=label)
            total_concepts += 1
            if label:
                reused += 1
        else:
            labels = _kmeans(embeddings, k, init_centroids=prev_centroids.get(pkg))
            for cluster_id in range(k):
                indices = [i for i, label in enumerate(labels) if label == cluster_id]
                if indices:
                    member_ids = [symbol_ids[i] for i in indices]
                    mh = _member_hash(conn, member_ids)
                    label = prev_labels.get(mh)
                    _insert_concept(conn, symbol_ids, embeddings, indices, member_hash=mh, label=label)
                    total_concepts += 1
                    if label:
                        reused += 1

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
    telemetry.info("cluster complete", concepts=total_concepts, reused_labels=reused, packages=len(packages))


def _member_hash(conn, symbol_ids: list) -> str:
    placeholders = ",".join("?" * len(symbol_ids))
    rows = conn.execute(
        f"SELECT COALESCE(content_hash, '') FROM symbols WHERE id IN ({placeholders}) ORDER BY content_hash",
        symbol_ids,
    ).fetchall()
    return hashlib.sha256("".join(r[0] for r in rows).encode()).hexdigest()


def _load_prev_labels(conn) -> dict[str, tuple]:
    rows = conn.execute(
        "SELECT member_hash, name, description, role FROM concepts "
        "WHERE member_hash IS NOT NULL AND name IS NOT NULL"
    ).fetchall()
    return {r["member_hash"]: (r["name"], r["description"], r["role"]) for r in rows}


def _load_prev_centroids(conn) -> dict[str, np.ndarray]:
    """Return previous centroids keyed by package, for warm-starting KMeans."""
    rows = conn.execute(
        """SELECT c.id, c.centroid, f.path
           FROM concepts c
           JOIN concept_members cm ON cm.concept_id = c.id
           JOIN symbols s ON s.id = cm.symbol_id
           JOIN files f ON f.id = s.file_id
           GROUP BY c.id"""
    ).fetchall()
    by_pkg: dict[str, list] = defaultdict(list)
    for row in rows:
        pkg = str(Path(row["path"]).parent)
        by_pkg[pkg].append(np.frombuffer(row["centroid"], dtype=np.float32))
    return {pkg: np.array(cs) for pkg, cs in by_pkg.items()}


def _kmeans(embeddings: np.ndarray, k: int, init_centroids: np.ndarray | None = None) -> np.ndarray:
    try:
        from sklearn.cluster import KMeans

        if init_centroids is not None and init_centroids.shape == (k, embeddings.shape[1]):
            init: str | np.ndarray = init_centroids
            n_init = 1
        else:
            init = "k-means++"
            n_init = 3

        km = KMeans(n_clusters=k, init=init, n_init=n_init, random_state=42)  # type: ignore[arg-type]
        return km.fit_predict(embeddings)
    except ImportError:
        return np.array([i % k for i in range(len(embeddings))])


def _insert_concept(
    conn,
    symbol_ids: list,
    embeddings: np.ndarray,
    indices: list,
    *,
    member_hash: str | None = None,
    label: tuple | None = None,
) -> None:
    member_embs = embeddings[indices]
    centroid = member_embs.mean(axis=0).astype(np.float32)
    name, description, role = label if label else (None, None, None)

    conn.execute(
        "INSERT INTO concepts(name, description, role, member_count, centroid, member_hash) VALUES (?,?,?,?,?,?)",
        (name, description, role, len(indices), centroid.tobytes(), member_hash),
    )
    concept_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    for idx in indices:
        dist = float(np.linalg.norm(embeddings[idx] - centroid))
        conn.execute(
            "INSERT INTO concept_members(concept_id, symbol_id, distance_to_centroid) "
            "VALUES (?,?,?)",
            (concept_id, symbol_ids[idx], dist),
        )
