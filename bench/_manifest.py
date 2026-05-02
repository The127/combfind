"""Fixture integrity manifest. Used by capture/score/runner to detect tampering."""

from __future__ import annotations

import hashlib
from pathlib import Path

FIXTURE_DIR = Path(__file__).parent / "fixture"
MANIFEST_PATH = Path(__file__).parent / "fixture.manifest"


def compute_manifest(root: Path = FIXTURE_DIR) -> str:
    """Return TAB-separated <relpath>\\t<sha256> per file, sorted by relpath."""
    lines = []
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(root).as_posix()
        h = hashlib.sha256(p.read_bytes()).hexdigest()
        lines.append(f"{rel}\t{h}")
    return "\n".join(lines) + "\n"


def write_manifest() -> None:
    MANIFEST_PATH.write_text(compute_manifest())


def verify() -> None:
    """Raise SystemExit(2) if the fixture has been modified."""
    expected = MANIFEST_PATH.read_text()
    actual = compute_manifest()
    if expected != actual:
        diff_summary = _summarize_diff(expected, actual)
        raise SystemExit(
            f"FIXTURE TAMPERED — bench/fixture/ does not match fixture.manifest\n"
            f"{diff_summary}"
        )


def _summarize_diff(expected: str, actual: str) -> str:
    exp_map = dict(line.split("\t") for line in expected.strip().splitlines())
    act_map = dict(line.split("\t") for line in actual.strip().splitlines())
    added = set(act_map) - set(exp_map)
    removed = set(exp_map) - set(act_map)
    changed = {k for k in exp_map.keys() & act_map.keys() if exp_map[k] != act_map[k]}
    parts = []
    if added:
        parts.append(f"  added: {sorted(added)}")
    if removed:
        parts.append(f"  removed: {sorted(removed)}")
    if changed:
        parts.append(f"  changed: {sorted(changed)}")
    return "\n".join(parts) if parts else "  (no specific diff)"


if __name__ == "__main__":
    write_manifest()
    print(f"wrote {MANIFEST_PATH}")
