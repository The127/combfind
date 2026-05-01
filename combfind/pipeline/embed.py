import json

try:
    from sentence_transformers import SentenceTransformer
except ImportError:  # pragma: no cover
    SentenceTransformer = None  # type: ignore[assignment,misc]

from combfind.db import get_connection


def run(db_path: str, *, embed_model: str = "all-MiniLM-L6-v2", **_) -> None:
    if SentenceTransformer is None:
        raise ImportError("sentence-transformers is required for the embed stage")

    import numpy as np

    conn = get_connection(db_path)

    rows = conn.execute(
        """SELECT s.id, s.name, s.signature, s.docstring
           FROM symbols s
           LEFT JOIN symbol_embeddings se ON se.symbol_id = s.id
           WHERE se.symbol_id IS NULL"""
    ).fetchall()

    if not rows:
        print("[combfind] embed: all symbols already embedded, skipping")
        conn.close()
        return

    model = SentenceTransformer(embed_model)

    texts = []
    ids = []
    for row in rows:
        parts = [row["name"]]
        if row["signature"] and row["signature"] != row["name"]:
            parts.append(row["signature"])
        if row["docstring"]:
            parts.append(row["docstring"])
        texts.append(" ".join(parts))
        ids.append(row["id"])

    embeddings = model.encode(texts, batch_size=256, show_progress_bar=False, convert_to_numpy=True)
    embeddings = np.array(embeddings, dtype=np.float32)
    dim = embeddings.shape[1]

    for sym_id, emb in zip(ids, embeddings):
        conn.execute(
            "INSERT OR REPLACE INTO symbol_embeddings(symbol_id, embedding) VALUES (?,?)",
            (sym_id, emb.tobytes()),
        )

    for key, value in (("embed_model", embed_model), ("embed_dim", dim)):
        conn.execute(
            "INSERT OR REPLACE INTO build_config(key, value) VALUES (?,?)",
            (key, json.dumps(value)),
        )

    conn.commit()
    conn.close()
    print(f"[combfind] embed: {len(ids)} symbols embedded ({embed_model}, dim={dim})")
