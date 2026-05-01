import json

import numpy as np

try:
    from sentence_transformers import SentenceTransformer
except ImportError:
    SentenceTransformer = None  # type: ignore[assignment,misc]

from combfind.db import get_connection


def run(db_path: str, *, embed_model: str = "all-MiniLM-L6-v2", **_) -> None:
    if SentenceTransformer is None:
        raise ImportError("sentence-transformers is required for the embed_concepts stage")

    conn = get_connection(db_path)

    # Prefer the model that was used for symbol embeddings
    cfg_row = conn.execute(
        "SELECT value FROM build_config WHERE key = 'embed_model'"
    ).fetchone()
    if cfg_row:
        embed_model = json.loads(cfg_row[0])

    rows = conn.execute(
        """SELECT c.id, c.description
           FROM concepts c
           LEFT JOIN concept_embeddings ce ON ce.concept_id = c.id
           WHERE c.description IS NOT NULL AND ce.concept_id IS NULL"""
    ).fetchall()

    if not rows:
        print("[combfind] embed_concepts: all concepts already embedded, skipping")
        conn.close()
        return

    model = SentenceTransformer(embed_model)

    concept_ids = [r["id"] for r in rows]
    texts = [r["description"] for r in rows]

    embeddings = model.encode(texts, batch_size=128, show_progress_bar=False, convert_to_numpy=True)
    embeddings = np.array(embeddings, dtype=np.float32)

    for concept_id, emb in zip(concept_ids, embeddings):
        conn.execute(
            "INSERT OR REPLACE INTO concept_embeddings(concept_id, embedding) VALUES (?,?)",
            (concept_id, emb.tobytes()),
        )

    conn.commit()
    conn.close()
    print(f"[combfind] embed_concepts: {len(concept_ids)} concepts embedded ({embed_model})")
