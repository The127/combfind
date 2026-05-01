import json
from pathlib import Path

from combfind.eval.metrics import recall_at_k
from combfind.query import query


def run(*, db_path: str, fixtures_dir: str, ks: list[int]) -> dict[int, dict[str, float]]:
    """Run all fixtures and return aggregate recall@k scores.

    Returns {k: {"file_recall": float, "symbol_recall": float}}.
    """
    fixtures = _load_fixtures(Path(fixtures_dir))
    if not fixtures:
        print(f"[combfind eval] no fixtures found in {fixtures_dir}")
        return {}

    max_k = max(ks)
    per_fixture: list[dict] = []

    for name, input_text, expected in fixtures:
        results = query(input_text, db_path=db_path, top_k=max_k)

        row: dict = {"name": name}
        for k in ks:
            top_k = results[:k]
            retrieved_files = [f["path"] for r in top_k for f in r["files"]]
            retrieved_symbols = [s for r in top_k for s in r["symbols"]]

            row[k] = {
                "file_recall": recall_at_k(expected["files"], retrieved_files, k=len(retrieved_files)),
                "symbol_recall": recall_at_k(expected["symbols"], retrieved_symbols, k=len(retrieved_symbols)),
            }

        per_fixture.append(row)

    # Print per-fixture results
    print(f"\nEval: {len(fixtures)} fixture(s)  k={ks}\n")
    for row in per_fixture:
        print(f"  {row['name']}:")
        for k in ks:
            s = row[k]
            print(f"    @{k}: files={s['file_recall']:.2f}  symbols={s['symbol_recall']:.2f}")

    # Aggregate
    aggregate: dict[int, dict[str, float]] = {}
    print("\nAggregate:")
    for k in ks:
        avg_file = sum(r[k]["file_recall"] for r in per_fixture) / len(per_fixture)
        avg_sym = sum(r[k]["symbol_recall"] for r in per_fixture) / len(per_fixture)
        aggregate[k] = {"file_recall": avg_file, "symbol_recall": avg_sym}
        print(f"  @{k}: file_recall={avg_file:.3f}  symbol_recall={avg_sym:.3f}")

    print()
    return aggregate


def _load_fixtures(root: Path) -> list[tuple[str, str, dict]]:
    """Return list of (name, input_text, expected_dict) for each valid fixture dir."""
    fixtures = []
    if not root.is_dir():
        return fixtures

    for d in sorted(root.iterdir()):
        if not d.is_dir():
            continue
        input_file = d / "input.txt"
        expected_file = d / "expected.json"
        if not input_file.exists() or not expected_file.exists():
            print(f"[combfind eval] skipping {d.name}: missing input.txt or expected.json")
            continue
        try:
            input_text = input_file.read_text().strip()
            expected = json.loads(expected_file.read_text())
            expected.setdefault("files", [])
            expected.setdefault("symbols", [])
        except (OSError, json.JSONDecodeError) as e:
            print(f"[combfind eval] skipping {d.name}: {e}")
            continue
        fixtures.append((d.name, input_text, expected))

    return fixtures
