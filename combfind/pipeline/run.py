import concurrent.futures
import hashlib
import json
import time

from combfind.db import get_connection
from combfind import telemetry

# stages 2+3 are independent of each other; run them concurrently
_PLAN: list[list[str]] = [
    ["parse"],
    ["index", "embed"],
    ["cluster"],
    ["label"],
    ["embed_concepts"],
]

_ALL_STAGES = [s for group in _PLAN for s in group]


def _stage_fn(name: str):
    from combfind.pipeline import cluster, embed, embed_concepts, index, label, parse

    return {
        "parse": parse.run,
        "index": index.run,
        "embed": embed.run,
        "cluster": cluster.run,
        "label": label.run,
        "embed_concepts": embed_concepts.run,
    }[name]


def _input_hash(conn, params: dict) -> str:
    hashes = [r[0] for r in conn.execute("SELECT content_hash FROM files ORDER BY path")]
    payload = json.dumps({"hashes": sorted(hashes), "params": params}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


def _is_cached(conn, stage: str, input_hash: str) -> bool:
    row = conn.execute(
        "SELECT status, input_hash FROM pipeline_runs WHERE stage = ?", (stage,)
    ).fetchone()
    return row is not None and row["status"] == "done" and row["input_hash"] == input_hash


def _mark(conn, stage: str, status: str, input_hash: str | None = None, params: dict | None = None):
    conn.execute(
        """INSERT INTO pipeline_runs(stage, status, completed_at, input_hash, params)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(stage) DO UPDATE SET
               status=excluded.status,
               completed_at=excluded.completed_at,
               input_hash=excluded.input_hash,
               params=excluded.params""",
        (stage, status, int(time.time()) if status in ("done", "failed") else None,
         input_hash, json.dumps(params) if params else None),
    )
    conn.commit()


def _run_one(stage: str, db_path: str, input_hash: str, params: dict) -> None:
    conn = get_connection(db_path)
    if _is_cached(conn, stage, input_hash):
        telemetry.debug("stage cached, skipping", stage=stage)
        conn.close()
        return
    telemetry.info("stage running", stage=stage)
    _mark(conn, stage, "running")
    conn.close()
    try:
        _stage_fn(stage)(db_path, **params)
        conn = get_connection(db_path)
        _mark(conn, stage, "done", input_hash, params)
        conn.close()
    except ImportError as exc:
        conn = get_connection(db_path)
        _mark(conn, stage, "skipped")
        conn.close()
        telemetry.warning("stage skipped", stage=stage, reason=str(exc))
    except Exception as exc:
        conn = get_connection(db_path)
        _mark(conn, stage, "failed")
        conn.close()
        telemetry.error("stage failed", stage=stage, reason=str(exc))
        raise


def run(db_path: str, stages: list[str] | None = None, force: bool = False, **params) -> None:
    conn = get_connection(db_path)
    if force:
        conn.execute("DELETE FROM pipeline_runs")
        conn.commit()

    requested = set(stages) if stages else set(_ALL_STAGES)

    for group in _PLAN:
        to_run = [s for s in group if s in requested]
        if not to_run:
            continue

        # recompute hash after each group (files table grows after parse)
        ih = _input_hash(conn, params)
        conn.close()

        if len(to_run) == 1:
            _run_one(to_run[0], db_path, ih, params)
        else:
            with concurrent.futures.ThreadPoolExecutor(max_workers=len(to_run)) as ex:
                futures = {ex.submit(_run_one, s, db_path, ih, params): s for s in to_run}
                for f in concurrent.futures.as_completed(futures):
                    f.result()  # re-raises on failure

        conn = get_connection(db_path)

    conn.close()


def run_stage(stage: str, db_path: str, **params) -> None:
    if stage not in _ALL_STAGES:
        raise ValueError(f"Unknown stage {stage!r}. Valid: {_ALL_STAGES}")
    conn = get_connection(db_path)
    ih = _input_hash(conn, params)
    conn.close()
    _run_one(stage, db_path, ih, params)
