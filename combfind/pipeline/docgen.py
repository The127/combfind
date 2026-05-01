import json
from pathlib import Path

from combfind import telemetry
from combfind.db import get_connection

_COMMIT_EVERY = 10


def run(db_path: str, *, backend=None, llm_model: str | None = None, llm_ctx: int | None = None, **_) -> None:
    if backend is None:
        if llm_model is None:
            telemetry.debug("docgen skipped, no llm backend configured")
            return
        from combfind.llm import LocalBackend
        backend = LocalBackend(model_path=llm_model, n_ctx=llm_ctx or 2048)

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

    telemetry.info("docgen running", symbols=len(rows))
    total = len(rows)

    for i, row in enumerate(rows, 1):
        skeleton = _read_skeleton(row, repo_path)
        if not skeleton:
            continue

        symbol = row["qualified_name"] or row["name"]
        telemetry.debug("docgen symbol", progress=f"{i}/{total}", symbol=symbol)
        messages = _build_messages(row, skeleton)
        doc = backend.chat(messages)

        if doc:
            conn.execute(
                "UPDATE symbols SET docstring = ? WHERE id = ?",
                (doc[:500], row["id"]),
            )

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


_EXAMPLES = """\
function: postgres.mapUser
func mapUser(u User) postgresUser { ... }
Converts a domain User struct to a PostgreSQL-mapped postgresUser for database persistence.

method: password.minimumSpecialPolicy.Validate
func (p minimumSpecialPolicy) Validate(password string) error { ... }
Validates that a password contains at least N special characters, returning an error if the requirement is not met.

struct: queries.GetResourceServer
type GetResourceServer struct { VirtualServerName string; ProjectSlug string; ResourceServerID uuid.UUID }
Query object for retrieving a resource server by ID within a specific project and virtual server."""


def _build_messages(row, skeleton: str) -> list[dict]:
    return [
        {
            "role": "system",
            "content": (
                "Write a doc comment for a code symbol. "
                "1-3 sentences. Name specific types, patterns, or domain concepts. "
                "Do not start with the symbol name. Output only the comment text, nothing else.\n\n"
                f"Examples:\n{_EXAMPLES}"
            ),
        },
        {
            "role": "user",
            "content": f"{row['kind']}: {row['qualified_name'] or row['name']}\n\n{skeleton}",
        },
    ]
