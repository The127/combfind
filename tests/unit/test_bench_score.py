"""Tests for bench/score.py exit-code contract.

The autoresearch runner relies on score.py's exit codes to distinguish
correctness regressions from perf no-ops, so these need to stay stable.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
GOLDEN_DIR = REPO_ROOT / "bench" / "golden"
MANIFEST = REPO_ROOT / "bench" / "fixture.manifest"
FIXTURE_DIR = REPO_ROOT / "bench" / "fixture"


def _run_score(mode: str = "cold") -> tuple[int, str, str]:
    proc = subprocess.run(
        [sys.executable, "-m", "bench.score", f"--mode={mode}"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    return proc.returncode, proc.stdout, proc.stderr


def test_clean_state_exits_zero_with_json_on_stdout():
    rc, out, _ = _run_score("cold")
    assert rc == 0, f"expected pass on clean state; stderr={_}"
    payload = json.loads(out.strip().splitlines()[-1])
    assert payload["status"] == "OK"
    assert payload["mode"] == "cold"
    assert payload["parse_rows"] > 0
    assert payload["elapsed_seconds"] > 0


def test_incremental_mode_passes_with_more_rows():
    rc, out, _ = _run_score("incremental")
    assert rc == 0
    payload = json.loads(out.strip().splitlines()[-1])
    # canonical edit adds two methods (App.pause, App.resume)
    assert payload["mode"] == "incremental"
    assert payload["parse_rows"] >= 128


def test_tampered_fixture_exits_two(tmp_path):
    """Touching the fixture tree must reject before any timing is recorded."""
    target = FIXTURE_DIR / "src" / "com" / "example" / "tasks" / "App.java"
    backup = tmp_path / "App.java.bak"
    shutil.copy(target, backup)
    try:
        target.write_text(target.read_text() + "// tampered\n")
        rc, out, err = _run_score("cold")
        assert rc == 2, f"expected exit 2 (tampered); got {rc}, stderr={err}"
        assert "TAMPERED" in err
        assert out.strip() == ""  # no JSON on tamper
    finally:
        shutil.copy(backup, target)


def test_parse_mismatch_exits_three(tmp_path):
    """Stale golden vs current pipeline output must exit 3."""
    backup = tmp_path / "parse_symbols.tsv.bak"
    target = GOLDEN_DIR / "parse_symbols.tsv"
    shutil.copy(target, backup)
    try:
        # Drop a row from the golden — current pipeline output won't match.
        lines = target.read_text().splitlines()
        target.write_text("\n".join(lines[:-1]) + "\n")
        rc, out, err = _run_score("cold")
        assert rc == 3, f"expected exit 3 (parse mismatch); got {rc}, stderr={err}"
        assert "parse_symbols mismatch" in err
        assert out.strip() == ""
    finally:
        shutil.copy(backup, target)


def test_index_mismatch_exits_four(tmp_path):
    backup = tmp_path / "index_refs.tsv.bak"
    target = GOLDEN_DIR / "index_refs.tsv"
    shutil.copy(target, backup)
    try:
        lines = target.read_text().splitlines()
        target.write_text("\n".join(lines[:-1]) + "\n")
        rc, out, err = _run_score("cold")
        assert rc == 4, f"expected exit 4 (index mismatch); got {rc}, stderr={err}"
        assert "index_refs mismatch" in err
    finally:
        shutil.copy(backup, target)


def test_invalid_mode_rejected_by_argparse():
    proc = subprocess.run(
        [sys.executable, "-m", "bench.score", "--mode=garbage"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert proc.returncode != 0
    # argparse default exit code is 2; we don't pin a specific code here.
