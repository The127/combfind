import json


def query(
    text: str,
    *,
    db_path: str,
    top_k: int = 5,
    rerank: bool = False,
    llm_model: str | None = None,
) -> list[dict]:
    raise NotImplementedError


def print_results(results: list[dict], *, fmt: str = "text") -> None:
    if fmt == "json":
        print(json.dumps(results, indent=2))
        return
    for i, r in enumerate(results, 1):
        score = r.get("score", 0)
        role = r.get("role", "")
        concept = r.get("concept", "")
        print(f"[{i}] {concept} ({role}) — {score:.2f}")
        for f in r.get("files", []):
            print(f"    {f['path']}:{f['start_line']}-{f['end_line']}")
        if r.get("why_relevant"):
            print(f"    why: {r['why_relevant']}")
        for sib in r.get("sibling_implementations", []):
            print(f"    sibling: {sib['name']} ({sib['file']})")
