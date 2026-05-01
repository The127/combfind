import json
import textwrap

try:
    from llama_cpp import Llama, LlamaGrammar
except ImportError:
    Llama = None  # type: ignore[assignment,misc]
    LlamaGrammar = None  # type: ignore[assignment,misc]

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


def run(db_path: str, *, llm_model: str | None = None, llm_ctx: int | None = None, **_) -> None:
    if llm_model is None:
        raise ValueError("--llm-model is required for the label stage")
    if Llama is None:
        raise ImportError("llama-cpp-python is required for the label stage")

    conn = get_connection(db_path)

    unlabeled = conn.execute(
        "SELECT id FROM concepts WHERE name IS NULL"
    ).fetchall()

    if not unlabeled:
        print("[combfind] label: no unlabeled concepts, skipping")
        conn.close()
        return

    llm = Llama(model_path=llm_model, n_ctx=llm_ctx or 2048, verbose=False)
    grammar = LlamaGrammar.from_json_schema(_SCHEMA)

    for row in unlabeled:
        concept_id = row["id"]

        members = conn.execute(
            """SELECT s.name, s.kind, s.signature, s.docstring
               FROM concept_members cm
               JOIN symbols s ON s.id = cm.symbol_id
               WHERE cm.concept_id = ?
               ORDER BY cm.distance_to_centroid
               LIMIT ?""",
            (concept_id, _MAX_MEMBERS),
        ).fetchall()

        prompt = _build_prompt(members)
        result = llm(prompt, max_tokens=256, grammar=grammar, echo=False)
        text = result["choices"][0]["text"].strip()

        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            continue

        name = str(parsed.get("name", ""))[:120]
        description = str(parsed.get("description", ""))[:500]
        role = parsed.get("role") if parsed.get("role") in _ROLES else None

        conn.execute(
            "UPDATE concepts SET name=?, description=?, role=? WHERE id=?",
            (name, description, role, concept_id),
        )

    conn.commit()
    conn.close()
    print(f"[combfind] label: {len(unlabeled)} concepts labeled")


def _build_prompt(members) -> str:
    lines = []
    for m in members:
        line = f"- {m['name']} ({m['kind']}): {m['signature'] or m['name']}"
        if m["docstring"]:
            doc = m["docstring"][:80].replace("\n", " ")
            line += f" — {doc}"
        lines.append(line)

    return textwrap.dedent(f"""
        You are analyzing a cluster of code symbols to identify the concept they represent.

        Symbols in this cluster:
        {chr(10).join(lines)}

        Respond with a JSON object:
        - "name": a short concept name (2-5 words, e.g. "User Authentication", "Database Connection Pool")
        - "description": one sentence describing what these symbols do together
        - "role": one of: interface, implementation, orchestrator, entry_point, domain_model, infrastructure, cross_cutting

        JSON:
    """).strip()
