import re

from combfind import telemetry
from combfind.db import get_connection


def run(db_path: str, **_) -> None:
    conn = get_connection(db_path)

    if conn.execute("SELECT COUNT(*) FROM symbols").fetchone()[0] == 0:
        raise RuntimeError("index requires symbols — run parse first")

    conn.execute('DELETE FROM "references"')

    by_name: dict[str, list[int]] = {}
    by_qname: dict[str, int] = {}
    for row in conn.execute("SELECT id, name, qualified_name FROM symbols").fetchall():
        by_name.setdefault(row["name"], []).append(row["id"])
        if row["qualified_name"]:
            by_qname[row["qualified_name"]] = row["id"]

    inserted = 0
    for cls in conn.execute(
        "SELECT id, signature FROM symbols WHERE kind = 'class'"
    ).fetchall():
        src_id = cls["id"]
        for base_raw in _parse_bases(cls["signature"]):
            base_name = _clean_name(base_raw)
            if not base_name or base_name in ("object", "ABC", "Protocol"):
                continue
            dst_id = (
                by_qname.get(base_raw)
                or by_qname.get(base_name)
                or _sole(by_name.get(base_name, []), exclude=src_id)
            )
            if dst_id and dst_id != src_id:
                conn.execute(
                    'INSERT OR IGNORE INTO "references"'
                    "(src_symbol_id, dst_symbol_id, kind) VALUES (?,?,?)",
                    (src_id, dst_id, "inherit"),
                )
                inserted += 1

    conn.commit()
    conn.close()
    telemetry.info("index complete", references=inserted)


def _parse_bases(signature: str | None) -> list[str]:
    if not signature:
        return []
    m = re.match(r"class\s+\w+\s*\(([^)]*)\)", signature)
    if not m:
        return []
    return [b.strip() for b in m.group(1).split(",") if b.strip()]


def _clean_name(name: str) -> str:
    return re.split(r"[\[\(<]", name)[0].strip()


def _sole(candidates: list[int], *, exclude: int) -> int | None:
    filtered = [i for i in candidates if i != exclude]
    return filtered[0] if len(filtered) == 1 else None
