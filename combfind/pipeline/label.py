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


def run(db_path: str, *, backend=None, llm_model: str | None = None, llm_ctx: int | None = None, **_) -> None:
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

    telemetry.info("label running", concepts=len(unlabeled))
    total = len(unlabeled)

    for i, row in enumerate(unlabeled, 1):
        concept_id = row["id"]

        members = conn.execute(
            """SELECT s.qualified_name, s.name, s.kind, s.signature, s.docstring
               FROM concept_members cm
               JOIN symbols s ON s.id = cm.symbol_id
               WHERE cm.concept_id = ?
               ORDER BY cm.distance_to_centroid
               LIMIT ?""",
            (concept_id, _MAX_MEMBERS),
        ).fetchall()

        telemetry.debug("label concept", progress=f"{i}/{total}", concept_id=concept_id)
        messages = _build_messages(members)
        text = backend.chat(messages, max_tokens=256, schema=_SCHEMA)

        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            telemetry.warning("label parse error", concept_id=concept_id, progress=f"{i}/{total}")
            continue

        name = str(parsed.get("name", ""))[:120]
        description = str(parsed.get("description", ""))[:500]
        role = parsed.get("role") if parsed.get("role") in _ROLES else None

        telemetry.debug("concept labeled", progress=f"{i}/{total}", name=name, role=role)

        conn.execute(
            "UPDATE concepts SET name=?, description=?, role=? WHERE id=?",
            (name, description, role, concept_id),
        )

        if i % _COMMIT_EVERY == 0:
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
