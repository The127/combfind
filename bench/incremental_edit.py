"""Canonical incremental edit applied to a *copy* of the fixture.

The edit is intentionally small and well-defined so the post-edit output
is reproducible. The bench applies it to a tmp copy of the fixture during
incremental-mode runs; the original bench/fixture/ tree is never modified
(the manifest verifies it).

Two files are touched, on purpose:

  1. App.java — adds two new methods. Exercises the diff path's
     "qualified_name not in existing" branch (pure insertion).
  2. Math.java — modifies the docstring of one overloaded `add` method.
     Exercises the diff path's "qualified_name in existing, hash differs"
     branch in the presence of overloads, so a regression in
     _diff_symbols's overload handling (the original bug) shows up as a
     parse_symbols.tsv mismatch.
"""

from __future__ import annotations

from pathlib import Path

APP_TARGET = "src/com/example/tasks/App.java"
MATH_TARGET = "src/com/example/tasks/util/Math.java"

# --- App.java: add two new methods before the closing brace ---

_APP_ANCHOR_OLD = """\
    public static void main(String[] args) {
        Queue<Task> q = new ConcurrentQueue<>();
        Store<Task> s = new MemoryStore<>();
        WorkerConfig cfg = new WorkerConfig(4, 1000);
        WorkerPool p = new WorkerPool(q, s, cfg);
        App app = new App(q, p, s);
        app.start();
    }
}
"""

_APP_ANCHOR_NEW = """\
    public static void main(String[] args) {
        Queue<Task> q = new ConcurrentQueue<>();
        Store<Task> s = new MemoryStore<>();
        WorkerConfig cfg = new WorkerConfig(4, 1000);
        WorkerPool p = new WorkerPool(q, s, cfg);
        App app = new App(q, p, s);
        app.start();
    }

    /** Pause workers without stopping the pool. Resume via start(). */
    public void pause() {
        pool.stop();
    }

    /** Resume a previously paused pool. */
    public void resume() {
        pool.start();
    }
}
"""

# --- Math.java: edit one overload's docstring ---
# Math.add has int/long/double/triadic-int variants. We modify only the
# (int, int) -> int overload's docstring. After reparse, all four add
# overloads must still be present; with the overload-on-reparse bug,
# _diff_symbols would mis-key the dict and silently drop one of the
# other three overloads, causing parse_symbols.tsv to mismatch.

_MATH_ANCHOR_OLD = """\
    /** Sum two ints. */
    public static int add(int a, int b) {
        return a + b;
    }
"""

_MATH_ANCHOR_NEW = """\
    /** Sum two ints. Returns the integer sum without overflow checks. */
    public static int add(int a, int b) {
        return a + b;
    }
"""


def _replace_once(target: Path, old: str, new: str) -> None:
    text = target.read_text()
    if old not in text:
        raise RuntimeError(
            f"canonical edit anchor not found in {target}; "
            "fixture may have drifted or been edited"
        )
    target.write_text(text.replace(old, new, 1))


def apply_canonical_edit(fixture_root: Path) -> None:
    """Apply both edits to the fixture copy at fixture_root."""
    _replace_once(fixture_root / APP_TARGET, _APP_ANCHOR_OLD, _APP_ANCHOR_NEW)
    _replace_once(fixture_root / MATH_TARGET, _MATH_ANCHOR_OLD, _MATH_ANCHOR_NEW)
