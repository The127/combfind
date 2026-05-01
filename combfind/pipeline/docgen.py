import json
from pathlib import Path

from combfind import telemetry
from combfind.db import get_connection

try:
    from llama_cpp import Llama
except ImportError:
    Llama = None  # type: ignore[assignment,misc]

_COMMIT_EVERY = 10


def run(db_path: str, *, llm_model: str | None = None, llm_ctx: int | None = None, **_) -> None:
    if Llama is None:
        raise ImportError("llama-cpp-python is required for the docgen stage")
    if llm_model is None:
        telemetry.debug("docgen skipped, no llm_model configured")
        return

    conn = get_connection(db_path)
    repo_path = _repo_path(conn)

    rows = conn.execute(
        """SELECT s.id, s.qualified_name, s.name, s.kind,
                  s.start_line, s.end_line, f.path, f.language
           FROM symbols s
           JOIN files f ON f.id = s.file_id
           WHERE s.docstring IS NULL"""
    ).fetchall()

    if not rows:
        telemetry.debug("docgen skipped, all symbols have docstrings")
        conn.close()
        return

    telemetry.info("docgen loading model", model=llm_model, symbols=len(rows))
    llm = Llama(model_path=llm_model, n_ctx=llm_ctx or 2048, verbose=False)
    total = len(rows)

    for i, row in enumerate(rows, 1):
        skeleton = _read_skeleton(row, repo_path)
        if not skeleton:
            continue

        messages = _build_messages(row, skeleton)
        result = llm.create_chat_completion(messages, max_tokens=128)
        doc = result["choices"][0]["message"]["content"].strip()

        if doc:
            conn.execute(
                "UPDATE symbols SET docstring = ? WHERE id = ?",
                (doc[:500], row["id"]),
            )
            telemetry.debug("docgen symbol", progress=f"{i}/{total}",
                            symbol=row["qualified_name"] or row["name"])

        if i % _COMMIT_EVERY == 0:
            conn.commit()

    conn.commit()
    conn.close()
    telemetry.info("docgen complete", symbols=len(rows))


def _repo_path(conn) -> str | None:
    row = conn.execute(
        "SELECT params FROM pipeline_runs WHERE stage = 'parse'"
    ).fetchone()
    if row and row["params"]:
        return json.loads(row["params"]).get("repo_path")
    return None


def _read_skeleton(row, repo_path: str | None) -> str | None:
    if not repo_path:
        return None
    try:
        from combfind.pipeline.walkers import get_walker
        source = (Path(repo_path) / row["path"]).read_text(errors="replace")
        lines = source.splitlines()
        slice_text = "\n".join(lines[row["start_line"] - 1 : row["end_line"]])
        return get_walker(row["language"]).extract_skeleton(slice_text, row["kind"])
    except Exception:
        return None


def _build_messages(row, skeleton: str) -> list[dict]:
    return [
        {
            "role": "system",
            "content": (
                "You are writing documentation for code symbols used by AI coding agents. "
                "Given source code, write a single sentence that explains what this code does "
                "and when a developer would search for it. "
                "Be specific: name the technologies, patterns, data types, or domain concepts involved. "
                "Output only the sentence, nothing else."
            ),
        },
        {
            "role": "user",
            "content": f"{row['kind']}: {row['qualified_name'] or row['name']}\n\n{skeleton}",
        },
    ]
