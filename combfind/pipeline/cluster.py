import json
from collections import defaultdict

import numpy as np

try:
    import hdbscan as _hdbscan_mod
except ImportError:
    _hdbscan_mod = None  # type: ignore[assignment]

from combfind.db import get_connection


def run(db_path: str, *, cluster_min_size: int | None = None, noise: str = "singleton", **_) -> None:
    if _hdbscan_mod is None:
        raise ImportError("hdbscan is required for the cluster stage")

    conn = get_connection(db_path)

    rows = conn.execute("SELECT symbol_id, embedding FROM symbol_embeddings").fetchall()
    if not rows:
        raise RuntimeError("cluster requires symbol_embeddings — run embed first")

    symbol_ids = [r["symbol_id"] for r in rows]
    embeddings = np.array(
        [np.frombuffer(r["embedding"], dtype=np.float32) for r in rows]
    )

    n = len(symbol_ids)
    min_size = cluster_min_size if cluster_min_size is not None else max(5, n // 100)

    clusterer = _hdbscan_mod.HDBSCAN(min_cluster_size=min_size, metric="euclidean")
    labels = clusterer.fit_predict(embeddings)

    conn.execute("DELETE FROM concepts")
    conn.execute("DELETE FROM concept_members")

    clusters: dict[int, list[int]] = defaultdict(list)
    for idx, label in enumerate(labels.tolist()):
        clusters[label].append(idx)

    for label in sorted(k for k in clusters if k >= 0):
        _insert_concept(conn, symbol_ids, embeddings, clusters[label])

    noise_indices = clusters.get(-1, [])
    if noise_indices:
        if noise == "singleton":
            for idx in noise_indices:
                _insert_concept(conn, symbol_ids, embeddings, [idx])
        elif noise == "merge":
            _insert_concept(conn, symbol_ids, embeddings, noise_indices, name="uncategorized")
        # "drop": do nothing

    for key, val in (("noise_strategy", noise), ("cluster_min_size", min_size)):
        conn.execute(
            "INSERT OR REPLACE INTO build_config(key, value) VALUES (?,?)",
            (key, json.dumps(val)),
        )

    conn.commit()
    conn.close()

    n_real = sum(1 for k in clusters if k >= 0)
    print(f"[combfind] cluster: {n_real} clusters, {len(noise_indices)} noise ({noise})")


def _insert_concept(conn, symbol_ids: list, embeddings: np.ndarray, indices: list, *, name: str | None = None) -> None:
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
            "INSERT INTO concept_members(concept_id, symbol_id, distance_to_centroid) VALUES (?,?,?)",
            (concept_id, symbol_ids[idx], dist),
        )
