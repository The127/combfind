import json

from combfind.db import get_connection


def inspect_symbol(qualified_name: str, *, db_path: str) -> dict | None:
    conn = get_connection(db_path)

    row = conn.execute(
        """SELECT s.id, s.name, s.qualified_name, s.kind, s.signature,
                  s.start_line, s.end_line, s.docstring, f.path
           FROM symbols s JOIN files f ON f.id = s.file_id
           WHERE s.qualified_name = ?""",
        (qualified_name,),
    ).fetchone()

    if row is None:
        conn.close()
        return None

    sym_id = row["id"]

    concept_row = conn.execute(
        """SELECT c.name, c.role FROM concepts c
           JOIN concept_members cm ON cm.concept_id = c.id
           WHERE cm.symbol_id = ?""",
        (sym_id,),
    ).fetchone()

    callers = conn.execute(
        """SELECT s.qualified_name, s.name, s.start_line, f.path
           FROM "references" r
           JOIN symbols s ON s.id = r.src_symbol_id
           JOIN files f ON f.id = s.file_id
           WHERE r.dst_symbol_id = ?
           ORDER BY f.path, s.start_line
           LIMIT 20""",
        (sym_id,),
    ).fetchall()

    callees = conn.execute(
        """SELECT s.qualified_name, s.name, s.start_line, f.path
           FROM "references" r
           JOIN symbols s ON s.id = r.dst_symbol_id
           JOIN files f ON f.id = s.file_id
           WHERE r.src_symbol_id = ?
           ORDER BY f.path, s.start_line
           LIMIT 20""",
        (sym_id,),
    ).fetchall()

    siblings: list[dict] = []
    if concept_row:
        sibling_rows = conn.execute(
            """SELECT s.qualified_name, s.name, s.kind, f.path
               FROM concept_members cm
               JOIN symbols s ON s.id = cm.symbol_id
               JOIN files f ON f.id = s.file_id
               JOIN concepts c ON c.id = cm.concept_id
               WHERE c.name = ? AND cm.symbol_id != ?
               ORDER BY f.path, s.name""",
            (concept_row["name"], sym_id),
        ).fetchall()
        siblings = [
            {
                "qualified_name": r["qualified_name"],
                "kind": r["kind"],
                "file": r["path"],
            }
            for r in sibling_rows
        ]

    conn.close()

    return {
        "symbol": row["qualified_name"],
        "kind": row["kind"],
        "file": row["path"],
        "lines": f"{row['start_line']}-{row['end_line']}",
        "signature": row["signature"] or "",
        "docstring": row["docstring"] or "",
        "concept": concept_row["name"] if concept_row else None,
        "role": concept_row["role"] if concept_row else None,
        "callers": [
            {
                "symbol": r["qualified_name"] or r["name"],
                "file": r["path"],
                "line": r["start_line"],
            }
            for r in callers
        ],
        "callees": [
            {
                "symbol": r["qualified_name"] or r["name"],
                "file": r["path"],
                "line": r["start_line"],
            }
            for r in callees
        ],
        "concept_siblings": siblings,
    }


def find_candidates(name: str, *, db_path: str) -> list[str]:
    conn = get_connection(db_path)
    rows = conn.execute(
        """SELECT qualified_name FROM symbols
           WHERE qualified_name LIKE ?
           ORDER BY qualified_name
           LIMIT 20""",
        (f"%{name}%",),
    ).fetchall()
    conn.close()
    return [r["qualified_name"] for r in rows if r["qualified_name"]]


def print_inspect(result: dict, *, fmt: str = "text") -> None:
    if fmt == "json":
        print(json.dumps(result, indent=2))
        return

    print(f"{result['symbol']}  ({result['kind']}, {result['file']}:{result['lines']})")
    if result["concept"]:
        print(f"concept:  {result['concept']}  [{result['role']}]")
    if result["signature"]:
        print(f"sig:      {result['signature']}")
    if result["docstring"]:
        print(f"doc:      {result['docstring']}")

    print()

    if result["callers"]:
        print(f"callers ({len(result['callers'])}):")
        for c in result["callers"]:
            print(f"  {c['symbol']}  {c['file']}:{c['line']}")

    if result["callees"]:
        print(f"callees ({len(result['callees'])}):")
        for c in result["callees"]:
            print(f"  {c['symbol']}  {c['file']}:{c['line']}")

    if result["concept_siblings"]:
        print(f"concept siblings ({len(result['concept_siblings'])}):")
        for s in result["concept_siblings"]:
            print(f"  {s['qualified_name']}  [{s['kind']}]  {s['file']}")
