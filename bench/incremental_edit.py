"""Canonical incremental edit applied to a *copy* of the fixture.

The edit is intentionally small and well-defined so the post-edit output
is reproducible. The bench applies it to a tmp copy of the fixture during
incremental-mode runs; the original bench/fixture/ tree is never modified
(the manifest verifies it).
"""

from __future__ import annotations

from pathlib import Path

EDIT_TARGET = "src/com/example/tasks/App.java"

# Insertion point: just before the final '}' of the App class.
# Anchor on '    public static void main(String[] args) {' which is the
# last method, then insert after its closing brace.
_NEW_METHOD = """\

    /** Pause workers without stopping the pool. Resume via start(). */
    public void pause() {
        pool.stop();
    }

    /** Resume a previously paused pool. */
    public void resume() {
        pool.start();
    }
"""

_ANCHOR_OLD = """\
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

_ANCHOR_NEW = (
    "    public static void main(String[] args) {\n"
    "        Queue<Task> q = new ConcurrentQueue<>();\n"
    "        Store<Task> s = new MemoryStore<>();\n"
    "        WorkerConfig cfg = new WorkerConfig(4, 1000);\n"
    "        WorkerPool p = new WorkerPool(q, s, cfg);\n"
    "        App app = new App(q, p, s);\n"
    "        app.start();\n"
    "    }\n" + _NEW_METHOD + "}\n"
)


def apply_canonical_edit(fixture_root: Path) -> None:
    """Mutate the fixture copy at fixture_root by adding pause/resume to App."""
    target = fixture_root / EDIT_TARGET
    text = target.read_text()
    if _ANCHOR_OLD not in text:
        raise RuntimeError(
            f"canonical edit anchor not found in {target}; "
            "fixture may have drifted or been edited"
        )
    new_text = text.replace(_ANCHOR_OLD, _ANCHOR_NEW, 1)
    target.write_text(new_text)
