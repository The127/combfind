from combfind import telemetry
from combfind.db import get_connection
from combfind.pipeline.indexers import get_indexer


def run(db_path: str, *, repo_path: str | None = None, **_) -> None:
    conn = get_connection(db_path)

    if conn.execute("SELECT COUNT(*) FROM symbols").fetchone()[0] == 0:
        raise RuntimeError("index requires symbols — run parse first")

    conn.execute('DELETE FROM "references"')

    languages = [
        r[0]
        for r in conn.execute("SELECT DISTINCT language FROM files").fetchall()
        if r[0]
    ]

    inserted = 0
    for lang in languages:
        indexer = get_indexer(lang)
        if indexer:
            inserted += indexer.run(conn, repo_path=repo_path)

    conn.commit()
    conn.close()
    telemetry.info("index complete", references=inserted)
