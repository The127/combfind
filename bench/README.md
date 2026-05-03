# `bench/` — Autoresearch harness for combfind init speed

A Karpathy-style autoresearch loop, gated by chess-engine-style SPRT,
for autonomously optimizing combfind's `init` speed. This directory is
the **frozen scoring side** of the loop: the agent edits
`combfind/pipeline/`, the harness here decides whether the change is
correct and (sufficiently) faster.

```
bench/
  fixture/                # 20-file synthetic Java tree (com.example.tasks)
  fixture.manifest        # sha256 per file; tampering rejected before scoring
  golden/
    parse_symbols.tsv               # cold-mode parse output, byte-equal gate
    parse_symbols.incremental.tsv   # post-canonical-edit parse output
    index_refs.tsv                  # cold-mode index output
    index_refs.incremental.tsv      # post-canonical-edit index output
  _manifest.py            # fixture integrity check
  capture.py              # rebaseline golden from current master
  incremental_edit.py     # canonical edit applied to a tmp copy
  score.py                # one run, gate + timing, JSON to stdout on pass
  runner.py               # paired SPRT, baseline ref vs patch ref
  program.md              # instructions for the autonomous agent
```

## Quick start

Score one run on the current working tree:
```
uv run python -m bench.score --mode=cold
uv run python -m bench.score --mode=incremental
```

Compare HEAD against HEAD~1 with paired SPRT trials:
```
uv run python -m bench.runner --mode=cold
uv run python -m bench.runner --mode=incremental
```

Defaults: α=β=0.05, Δ=5%, hard cap 50 pairs, 2 warmup pairs discarded.
Override per run with `--alpha --beta --delta --max-pairs --warmup-pairs`.

## What "passing" means

`score.py` exits 0 only if all four checks succeed:

1. `bench/fixture.manifest` matches the fixture tree (sha256 per file).
2. `parse_symbols.tsv` byte-equal to the appropriate golden.
3. `index_refs.tsv` byte-equal to the appropriate golden.
4. The pipeline didn't crash.

Different exit codes (2 = tampered, 3 = parse mismatch, 4 = index
mismatch, 5 = pipeline crash) let the runner distinguish "this patch
broke things" from "this patch ran but isn't faster."

`runner.py` runs the gate first; if either side fails the gate, no
timing is recorded and the runner exits 2. After the gate passes,
paired trials accumulate `t_baseline - t_patch`; Wald's SPRT decides
ACCEPT (≥ Δ faster), REJECT (not faster), or INDETERMINATE (hard cap).

## Scope

The bench measures **parse** and **index** stages only. The LLM-bound
stages (`embed`, `cluster`, `label`, `embed_concepts`) are
non-deterministic and not run here; rely on `pytest tests/unit` for
correctness on those.

For most Java/Python repos parse + index is the deterministic chunk
of init work. Pipeline-level optimizations that affect those stages
will show up here; LLM-stage optimizations won't.

## Rebaselining

The golden is captured from the *current* working tree by
`capture.py`. Re-run only when intentionally accepting a behavioral
change in parse or index output (a walker rule update, an indexer
fix, etc.). The capture script's idempotency check ensures two
consecutive captures produce byte-identical output before writing.

A rebaseline commit cannot be SPRT-tested via the runner: the runner
copies the *current* bench/ (with the new golden) into both
worktrees, but the baseline ref's pipeline code produces the *old*
output, which won't match. That's by design — rebaselines need human
review, not paired timing.

## What's been proven

`bench/autoresearch-harness` branch demonstrates the loop end-to-end:

- **ACCEPT case**: lazy stage imports in `_stage_fn` (commit 505604c),
  86% cold-init speedup on the bench fixture. SPRT verdict in 1
  counted pair.
- **REJECT case**: lazy parser construction in `parse.py:_build_parsers`,
  +0.3% within noise floor. SPRT verdict in 8 pairs (not in this
  branch — experiment was rejected and the commit dropped).
- **CORRECTNESS case** that surfaced a real bug: skipping scip-java
  when no build descriptor was present. The gate rejected — but with
  *more* refs than golden, exposing that the existing fallback never
  ran when scip-java failed at runtime. Fixed separately in the
  scip-java fallback PR.

## Known limitations

- Fixture is small (~700 lines). Wall-clock baseline is ~250ms cold,
  which means absolute noise is large relative to micro-optimizations.
  A bigger fixture would tighten the SPRT but slow each pair.
- LLM-stage perf is invisible to the bench. If you care about
  optimizing label or embed_concepts, the bench can't help.
- `tree_sitter_language_pack` isn't installed in the bench env, so
  the fixture is Java/Python/Go-only by default. Adding `.gleam` or
  `.erl` files to the fixture would make capture fail or warn.
