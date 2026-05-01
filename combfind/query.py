import json

import numpy as np

try:
    from sentence_transformers import SentenceTransformer
except ImportError:
    SentenceTransformer = None  # type: ignore[assignment,misc]

from combfind.db import get_connection


def query(
    text: str,
    *,
    db_path: str,
    top_k: int = 5,
    rerank: bool = False,
    backend=None,
) -> list[dict]:
    if SentenceTransformer is None:
        raise ImportError("sentence-transformers is required for querying")

    conn = get_connection(db_path)

    cfg_row = conn.execute(
        "SELECT value FROM build_config WHERE key = 'embed_model'"
    ).fetchone()
    embed_model = json.loads(cfg_row[0]) if cfg_row else "all-MiniLM-L6-v2"

    rows = conn.execute(
        """SELECT ce.concept_id, ce.embedding, c.name, c.description, c.role
           FROM concept_embeddings ce
           JOIN concepts c ON c.id = ce.concept_id"""
    ).fetchall()

    if not rows:
        conn.close()
        return []

    concept_ids = [r["concept_id"] for r in rows]
    concept_meta = {r["concept_id"]: dict(r) for r in rows}
    embs = np.array([np.frombuffer(r["embedding"], dtype=np.float32) for r in rows])

    model = SentenceTransformer(embed_model)
    query_emb = model.encode([text], convert_to_numpy=True)[0].astype(np.float32)

    q_norm = float(np.linalg.norm(query_emb))
    e_norms = np.linalg.norm(embs, axis=1)
    scores = np.dot(embs, query_emb) / np.maximum(e_norms * q_norm, 1e-10)

    fetch_k = min(top_k * 3 if rerank else top_k, len(concept_ids))
    top_idx = np.argsort(scores)[::-1][:fetch_k]
    candidates = [(concept_ids[i], float(scores[i])) for i in top_idx]

    if rerank and backend is not None:
        candidates = _rerank(candidates, concept_meta, text, backend)

    results = [
        _expand(conn, concept_id, score, concept_meta[concept_id], rank)
        for rank, (concept_id, score) in enumerate(candidates[:top_k], 1)
    ]

    conn.close()
    return results


def print_results(results: list[dict], *, fmt: str = "text") -> None:
    if fmt == "json":
        print(json.dumps(results, indent=2))
        return

    for r in results:
        role = r.get("role") or ""
        concept = r.get("concept") or ""
        score = r.get("score", 0.0)
        print(f"[{r['rank']}] {concept} ({role}) — {score:.2f}")

        if r.get("why_relevant"):
            print(f"    why: {r['why_relevant']}")

        for f in r.get("files", []):
            print(f"    {f['path']}")
            for sym in f.get("symbols", []):
                name = sym["qualified_name"] or sym["name"]
                print(f"      {name}  :{sym['start_line']}-{sym['end_line']}")

        for sib in r.get("sibling_implementations", []):
            print(f"    sibling: {sib['name']} ({sib['file']})")

        print()


# ---------------------------------------------------------------------------
# internals
# ---------------------------------------------------------------------------

def _expand(conn, concept_id: int, score: float, meta: dict, rank: int) -> dict:
    members = conn.execute(
        """SELECT s.id, s.qualified_name, s.start_line, s.end_line, f.path
           FROM concept_members cm
           JOIN symbols s ON s.id = cm.symbol_id
           JOIN files f ON f.id = s.file_id
           WHERE cm.concept_id = ?
           ORDER BY f.path, s.start_line""",
        (concept_id,),
    ).fetchall()

    files_by_path: dict[str, dict] = {}
    for m in members:
        p = m["path"]
        if p not in files_by_path:
            files_by_path[p] = {"path": p, "symbols": []}
        files_by_path[p]["symbols"].append({
            "name": m["qualified_name"].split(".")[-1] if m["qualified_name"] else "",
            "qualified_name": m["qualified_name"] or "",
            "start_line": m["start_line"],
            "end_line": m["end_line"],
        })

    symbol_ids = [m["id"] for m in members]
    siblings: list[dict] = []

    if symbol_ids:
        ph = ",".join("?" * len(symbol_ids))
        # Siblings: classes that inherit FROM any member of this concept
        sibling_rows = conn.execute(
            f'SELECT DISTINCT s.name, f.path '
            f'FROM "references" r '
            f'JOIN symbols s ON s.id = r.src_symbol_id '
            f'JOIN files f ON f.id = s.file_id '
            f'WHERE r.dst_symbol_id IN ({ph}) '
            f'  AND r.kind = "inherit" '
            f'  AND r.src_symbol_id NOT IN ({ph})',
            symbol_ids * 2,
        ).fetchall()
        siblings = [{"name": r["name"], "file": r["path"]} for r in sibling_rows]

    return {
        "rank": rank,
        "concept": meta["name"] or f"concept_{concept_id}",
        "role": meta["role"],
        "score": round(score, 4),
        "files": list(files_by_path.values()),
        "why_relevant": meta["description"] or "",
        "sibling_implementations": siblings,
    }


def _rerank(
    candidates: list[tuple[int, float]],
    concept_meta: dict,
    query_text: str,
    backend,
) -> list[tuple[int, float]]:
    scored = []
    for concept_id, orig_score in candidates:
        meta = concept_meta[concept_id]
        messages = [
            {
                "role": "system",
                "content": (
                    "Rate the relevance of a code concept to a developer query. "
                    "Reply with a single decimal number between 0.0 and 1.0. Nothing else."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Query: {query_text}\n"
                    f"Concept: {meta['name']}: {meta['description']}\n"
                    f"Relevance (0.0–1.0):"
                ),
            },
        ]
        try:
            text = backend.chat(messages, max_tokens=8)
            score = float(text.strip().split()[0])
        except (ValueError, IndexError, Exception):
            score = orig_score
        scored.append((concept_id, score))

    return sorted(scored, key=lambda x: x[1], reverse=True)
