import json

from combfind import telemetry
from combfind.db import get_connection

_ROLES = [
    "interface", "implementation", "orchestrator",
    "entry_point", "domain_model", "infrastructure", "cross_cutting",
]

_SCHEMA = json.dumps({
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "description": {"type": "string"},
        "role": {"type": "string", "enum": _ROLES},
    },
    "required": ["name", "description", "role"],
})

_MAX_MEMBERS = 20
_COMMIT_EVERY = 10


def run(db_path: str, *, backend=None, llm_model: str | None = None, llm_ctx: int | None = None, llm_workers: int = 1, **_) -> None:
    if backend is None:
        if llm_model is None:
            raise ValueError("llm backend or --llm-model is required for the label stage")
        from combfind.llm import LocalBackend
        backend = LocalBackend(model_path=llm_model, n_ctx=llm_ctx or 2048)

    conn = get_connection(db_path)

    unlabeled = conn.execute(
        "SELECT id FROM concepts WHERE name IS NULL"
    ).fetchall()

    if not unlabeled:
        telemetry.debug("label skipped, no unlabeled concepts")
        conn.close()
        return

    telemetry.info("label running", concepts=len(unlabeled), workers=llm_workers)
    total = len(unlabeled)

    concept_members = {}
    for row in unlabeled:
        concept_members[row["id"]] = conn.execute(
            """SELECT s.qualified_name, s.name, s.kind, s.signature, s.docstring
               FROM concept_members cm
               JOIN symbols s ON s.id = cm.symbol_id
               WHERE cm.concept_id = ?
               ORDER BY cm.distance_to_centroid
               LIMIT ?""",
            (row["id"], _MAX_MEMBERS),
        ).fetchall()

    def _label(concept_id):
        messages = _build_messages(concept_members[concept_id])
        text = backend.chat(messages, schema=_SCHEMA)
        return concept_id, text

    from concurrent.futures import ThreadPoolExecutor, as_completed
    completed = 0
    with ThreadPoolExecutor(max_workers=llm_workers) as ex:
        futures = {ex.submit(_label, row["id"]): row["id"] for row in unlabeled}
        for future in as_completed(futures):
            completed += 1
            concept_id, text = future.result()
            telemetry.debug("label concept", progress=f"{completed}/{total}", concept_id=concept_id)

            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                telemetry.warning("label parse error", concept_id=concept_id, progress=f"{completed}/{total}")
                continue

            name = str(parsed.get("name", ""))[:120]
            description = str(parsed.get("description", ""))[:500]
            role = parsed.get("role") if parsed.get("role") in _ROLES else None

            telemetry.debug("concept labeled", progress=f"{completed}/{total}", name=name, role=role)
            conn.execute(
                "UPDATE concepts SET name=?, description=?, role=? WHERE id=?",
                (name, description, role, concept_id),
            )

            if completed % _COMMIT_EVERY == 0:
                conn.commit()

    conn.commit()
    conn.close()
    telemetry.info("label complete", concepts=len(unlabeled))


def _build_messages(members) -> list[dict]:
    lines = []
    for m in members:
        line = f"- {m['qualified_name'] or m['name']} ({m['kind']}): {m['signature'] or m['name']}"
        if m["docstring"]:
            doc = m["docstring"][:120].replace("\n", " ")
            line += f" — {doc}"
        lines.append(line)

    member_block = "\n".join(lines)
    return [
        {
            "role": "system",
            "content": (
                "You are a code analysis assistant. Given a cluster of related code symbols, "
                "output a JSON object with exactly these fields:\n"
                '  "name": a short concept name (2-5 words) — must be specific, never generic terms like "function", "class", "code", or "interface"\n'
                '  "description": one sentence a developer would search for to find this code — '
                "mention specific technologies, patterns, file types, or use cases; "
                "write it so queries like 'how do I add Go support?' or 'where is auth handled?' would match\n"
                '  "role": one of: interface, implementation, orchestrator, '
                "entry_point, domain_model, infrastructure, cross_cutting\n"
                "Output only valid JSON, nothing else."
            ),
        },
        {
            "role": "user",
            "content": f"Symbols in this cluster:\n{member_block}\n\nClassify this concept as JSON:",
        },
    ]
