# Bench loop instructions

You are an autoresearch agent optimizing combfind's `init` performance.
Your goal: produce git commits on the current branch that are
**demonstrably faster** under SPRT, **without regressing correctness**.

Read this file in full before making any changes.

## The loop

For each round:

1. **Pick one hypothesis** about a code change that might make `init`
   faster. State it explicitly (one or two sentences), naming the
   specific files you intend to edit. Limit each round to one
   independent change — small commits are easier to review and roll
   back if a future false-accept is discovered.

2. **Edit only files inside the editable scope** (see below). Make the
   change.

3. **Decide which mode the hypothesis targets**:
   - `cold`: a change that affects parse-from-scratch speed (e.g.,
     parser tweaks, walker pruning, file-walk reordering).
   - `incremental`: a change that affects re-init when only a handful
     of files changed (e.g., per-file dedup, the file-content-hash skip
     in parse.py:90, smarter symbol diff).
   A change can be tested in either mode; pick the one your hypothesis
   actually targets. If you're not sure, default to `cold`.

4. **Commit the change** on the current branch with a conventional
   subject describing the change (`perf:`, `refactor:`, etc.). This
   makes the new HEAD the patch and HEAD~1 the baseline.

5. **Run the SPRT runner**:
   ```
   uv run python -m bench.runner --mode=<cold|incremental>
   ```
   Default args compare HEAD vs HEAD~1 with α=β=0.05, Δ=5%, hard cap
   50 pairs.

6. **Read the verdict**:
   - `ACCEPT` (exit 0): the change passes the gate AND is at least Δ
     faster. **Keep the commit.**
   - `REJECT` (exit 1): the change passes the gate but is not Δ
     faster (or the runner hit the hard cap inconclusive). **Run
     `git reset --hard HEAD~1`** to drop the commit, then pick a
     different hypothesis.
   - Exit 2 (CORRECTNESS): the change *failed* the byte-equal gate.
     Read the diagnostic on stderr — it tells you which TSV mismatched
     and shows up to 5 missing/extra rows. **Run `git reset --hard
     HEAD~1`**. Do not try to "fix the test"; the gate is correct, your
     change broke parse or index output.
   - Exit 3 (USAGE / INTERNAL): something is wrong with the runner's
     environment. Read the message; it's not a verdict on your patch.

7. **Repeat.** No clever stacking — start each round from a clean
   working tree.

## Editable scope

You may edit any file under:
- `combfind/pipeline/` — parse, index, embed, cluster, label, docgen,
  embed_concepts, run, walkers, indexers
- `combfind/db.py` — schema and connection setup. Schema changes are
  in scope but expensive to review; prefer pipeline-level changes when
  the same speedup is reachable both ways.

## Forbidden scope

You may **not** edit:
- `bench/` — the harness, fixture, and golden are held constant. If you
  edit these to make the gate happier, your patch will fail review even
  if SPRT accepts.
- `tests/` — these are the unit-test safety net. Don't relax them.
- The fixture's content_hashes are verified against
  `bench/fixture.manifest` before every score run; tampering exits 2.

## What "correctness" means here

The gate is byte-equal comparison of:
- `bench/golden/parse_symbols.tsv` (cold) or
  `bench/golden/parse_symbols.incremental.tsv` (incremental)
- `bench/golden/index_refs.tsv` / `.incremental.tsv`

These dump every `(file, qualified_name, signature, kind, content_hash)`
and `(src_qname, dst_qname, ref_kind)` row, sorted. Any change that
adds, drops, or modifies a symbol or reference shows up immediately.

The bench measures only `parse` and `index` stages. The LLM-bound
stages (`embed`, `cluster`, `label`, `embed_concepts`) are not run by
the bench; if you optimize them, the bench cannot validate them — rely
on `pytest tests/unit` separately for those.

## Known suspects

Pulled from `plans/incremental-reindex-investigation.md`. These are
hypotheses, not confirmed wins.

1. **`pipeline/run.py:_input_hash`** treats `params` as part of the
   hash, which includes `repo_path` and `llm_workers`. Changing
   parallelism or moving the DB invalidates every stage's cache even
   when the data is identical. Could `params` be filtered down to
   semantically-meaningful keys only?

2. **`pipeline/run.py` stage caching is all-or-nothing** keyed on a
   single corpus-wide hash. If one file changes content, every stage's
   `_is_cached` returns False. Each stage then re-derives per-row
   incrementality internally. Could the stage cache be per-file rather
   than per-corpus, so unchanged files skip the stage entirely?

3. **`pipeline/parse.py` re-parses on file content_hash mismatch but
   doesn't include the parser/walker version**. A combfind upgrade
   that changes a walker rule will silently keep stale symbols whose
   file content didn't change. (Out of scope for speed, but flagged.)

4. **`pipeline/cluster.py` wipes all concepts and re-clusters every
   run**, even when only one package's symbols changed. Could
   re-clustering be limited to the packages whose membership changed?

5. **`pipeline/index.py` wipes the entire references table** every
   run. Same per-package question.

6. **`pipeline/parse.py:_build_parsers()` runs at the start of every
   parse stage**, importing tree-sitter language modules even for
   languages with zero files in the repo. Could it be lazy?

7. **`pipeline/parse.py` walks the entire tree** with `os.walk`, then
   skips directories via `_SKIP_DIRS` and the exclude rules. The walk
   itself is unconditional. Could the SKIP_DIRS prune happen earlier
   via `os.scandir`?

You are also welcome to find your own. Read the pipeline code, look
for redundant work, and test your hypothesis.

## Diagnostics

`bench/score.py` prints per-stage telemetry by setting
`COMBFIND_LOG_LEVEL=info` (silent by default in the bench). To inspect
what a stage is doing during a slow trial:

```
COMBFIND_LOG_LEVEL=info uv run python -m bench.score --mode=cold
```

The runner's per-pair log shows wall-clock for each side and the
running LR. A run that converges to ACCEPT in 6 pairs is more confident
than one that converges in 30; both are valid.

## Hard rules

- **Never edit anything in `bench/`** to make the gate pass.
- **Never edit anything in `tests/`** to make tests pass.
- **Never bypass the runner** — don't time things by hand and commit;
  the SPRT verdict is the contract.
- **Never push to remote**; the branch is reviewed before merge.
- **Never run `git push --force`**.
- If the runner exits 3 (USAGE / INTERNAL) repeatedly, stop and write
  a note for the human reviewer instead of guessing.
