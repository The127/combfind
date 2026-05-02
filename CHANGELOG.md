# CHANGELOG


## v1.5.1 (2026-05-02)

### Bug Fixes

- Bypass cache check for parse stage so disk changes are detected
  ([`b868657`](https://github.com/The127/combfind/commit/b8686578efcdcc1564d645e8f7bfe28fb0e8c4e8))

the parse stage's cache key was derived from files.content_hash in the db, but parse is the only
  stage that updates that column. once the db had any rows, parse would always see "no change" and
  skip, so new and modified files on disk were never picked up without --force. parse now always
  runs; its per-file hash check keeps the no-op case cheap, and downstream stages still cascade
  correctly via the post-parse hash recompute.

### Documentation

- Add concept roles section, tighten performance copy and eval caveat
  ([`c5b6811`](https://github.com/The127/combfind/commit/c5b68116240eec1f09ecb7bd0a45f440cd4d6a44))

- Remove external paper citation from performance section
  ([`2c95365`](https://github.com/The127/combfind/commit/2c95365169c7e914479da4588044820ed5f75875))


## v1.5.0 (2026-05-02)

### Bug Fixes

- Pin tree-sitter-language-pack to 1.6.2 to avoid broken cp312 wheel in 1.6.3
  ([`047bd14`](https://github.com/The127/combfind/commit/047bd14b63b005872fb05b9cd0bc2bc21d931781))

### Continuous Integration

- Install gleam extra in test step
  ([`de7336e`](https://github.com/The127/combfind/commit/de7336e60d05474e6f3f1a0eac3415597a3089bb))

### Documentation

- Add gleam to supported languages and install section
  ([`7438acf`](https://github.com/The127/combfind/commit/7438acf97701704c3c364bcd0a3e38f012a82c27))

- Clarify crash recovery is batch-level, not just stage-level
  ([`05aaa3c`](https://github.com/The127/combfind/commit/05aaa3cad15b5a49b89607612ab0c4398363728e))

- Highlight token reduction, incremental reindex timing, and crash safety
  ([`03b5d10`](https://github.com/The127/combfind/commit/03b5d10eb7904c5a2047d80344e87e6b42e12a24))

- Rewrite readme with sharper value prop, benchmarks, and query guidance
  ([`db338f5`](https://github.com/The127/combfind/commit/db338f5d49358f69d0c6219cd3f6d2baaa8eb0ba))

- Sharpen intro copy, hedge benchmark, fix paid APIs claim
  ([`e265754`](https://github.com/The127/combfind/commit/e26575405381cc013760867a9c3ef4ddff694964))

- Simplify supported languages section
  ([`70d8439`](https://github.com/The127/combfind/commit/70d84391ee7ee696e29bb034b7c3cdeaaa268dce))

### Features

- Add erlang language support
  ([`8de7b4c`](https://github.com/The127/combfind/commit/8de7b4ce5dda3d6064ab0db124af78d5b4c0aa8a))

- Add gleam language support
  ([`7946950`](https://github.com/The127/combfind/commit/79469506c7ebe104a86241783cbe36c50f1bc798))

Parses .gleam files via tree-sitter-language-pack (no standalone PyPI package for tree-sitter-gleam
  exists). Extracts functions, custom types, type aliases, and constants; picks up /// doc comments
  from the preceding statement_comment sibling.

- LanguageDef gains pack_name field; _build_parsers falls back to tree-sitter-language-pack when
  grammar is empty - adds 'constant' to the symbols.kind CHECK constraint - install with: pip
  install "combfind[gleam]"


## v1.4.0 (2026-05-02)

### Features

- Inspect accepts multiple qualified names
  ([`47d3d0d`](https://github.com/The127/combfind/commit/47d3d0d82b828892112187d4e438efe78204498d))

combfind inspect sym.A sym.B now inspects all given symbols in one call. JSON output is always a
  list; text output separates results with a blank line.


## v1.3.0 (2026-05-02)

### Features

- Java language support
  ([`8a115eb`](https://github.com/The127/combfind/commit/8a115ebeb5ec5c211fd323779445fe40a9694974))

Add JavaIndexer with inheritance and import reference extraction, register it in get_indexer(), add
  tests, and document scip-java in the optional dependencies table.

tree_sitter_java was already a declared dependency and JavaWalker already existed; this completes
  the index stage for Java.


## v1.2.0 (2026-05-02)

### Bug Fixes

- Handle NULL content_hash in _member_hash
  ([`315087d`](https://github.com/The127/combfind/commit/315087d10bb584ce7356de0509c2801aabae9f7d))

COALESCE ensures symbols inserted before the embed stage (or in tests without content_hash) don't
  crash the cluster stage.

- Prefer documented default GGUF over alphabetical fallback
  ([`0a9fa0f`](https://github.com/The127/combfind/commit/0a9fa0f021587f5499188315e758a23b37a65dae))

When ~/.cache/combfind/models/ contains multiple GGUF files, the previous _default_llm_model()
  returned the first one alphabetically. Capital letters sort before lowercase, so a model like
  'Llama-3.2-3B-Instruct-Q6_K.gguf' would shadow the documented default
  'qwen2.5-coder-3b-instruct-q6_k.gguf' (lowercase q).

Now check for the documented default file first; only fall back to alphabetical when it's absent.

### Features

- Per-concept member hash to skip re-labeling unchanged concepts
  ([`01a7d4c`](https://github.com/The127/combfind/commit/01a7d4c32927ec9d06181155ebbb4412fe06f85e))

Each concept now stores a SHA-256 of its members' sorted content hashes. On re-runs, cluster carries
  forward name/description/role for any concept whose membership hasn't changed, so the label stage
  only calls the LLM for genuinely changed concepts.

One docstring change: 13 LLM calls → 1.

- Warm-start KMeans from previous centroids for stable clusters
  ([`e4574eb`](https://github.com/The127/combfind/commit/e4574ebe0eb9ae422075cea5da21f6bfec112205))

On incremental re-runs, initialize KMeans from the previous run's centroids so changed symbols get
  absorbed into existing clusters rather than reshuffling all assignments. Falls back to k-means++
  when no prior centroids exist or k has changed.

- **java**: Add Java support via tree-sitter-java
  ([`a7e405a`](https://github.com/The127/combfind/commit/a7e405ae74bf9d12c0703a32826e82e01f1cdef3))

Adds a JavaWalker that extracts classes, interfaces, enums, records, methods, constructors, enum
  constants, and nested types. Javadoc comments preceding declarations are captured as docstrings.
  Package qualified names are derived from the package_declaration when present (matching how
  GoWalker uses the package clause).

Extends the symbols.kind CHECK constraint to include 'record' and 'enum_constant' kinds for
  first-class Java symbol types.


## v1.1.0 (2026-05-02)

### Features

- Scip reference indexing for Go and Python
  ([`9edf034`](https://github.com/The127/combfind/commit/9edf034a4db76881c5cfeda3b25fdcf1c66299a5))

- Add scip-go and scip-python integration to extract type-resolved call/import edges into the
  references table - Refactor index stage into indexers/ with BaseIndexer ABC and factory - Each
  indexer falls back to tree-sitter heuristics when SCIP binary is not installed - Vendor
  scip_pb2.py (generated from scip.proto) - Add Go imports.scm tree-sitter query for fallback -
  Update README with optional SCIP dependencies

- Symbol-level content hash for incremental re-embedding
  ([`dc672fc`](https://github.com/The127/combfind/commit/dc672fcd2a102c2be9c4024a4b089158b0c5ef00))

Add content_hash to symbols table, computed from the text fed to the embedding model (qualified_name
  + signature + docstring). Parse now diffs symbols on file change instead of deleting and
  reinserting all of them: unchanged symbols keep their embedding rows, changed symbols drop theirs
  via FK cascade so embed only processes what actually changed.


## v1.0.3 (2026-05-02)

### Bug Fixes

- Pin llama-cpp-python<0.3.20
  ([`d5825ad`](https://github.com/The127/combfind/commit/d5825adfba852852bd9c688890b6499f02a4d292))

Versions 0.3.20 and 0.3.21 ship corrupt universal wheels: the Metal index URL returns HTTP 404, and
  the GitHub release asset itself is either an invalid ZIP (0.3.20) or has a bad CRC on libllama
  dylib (0.3.21). Until upstream republishes, constrain to the last known-good 0.3.19.

### Chores

- Publish github releases as non-draft
  ([`59841df`](https://github.com/The127/combfind/commit/59841dfc6d2ec0dbaaed8e20c6acdf176402f251))


## v1.0.2 (2026-05-02)

### Bug Fixes

- Remove hardcoded max_tokens; add parse docstring preservation tests
  ([`22e5a53`](https://github.com/The127/combfind/commit/22e5a536c27fcbf3af4b9a62ee40d10fb3343c91))

- **ci**: Correct commitlint action name
  ([`30367c1`](https://github.com/The127/combfind/commit/30367c1603e246ff343bdebd02873cb923b03d32))

### Chores

- Add MIT license
  ([`fb193fe`](https://github.com/The127/combfind/commit/fb193fe7696c01955cc128fe12d995a870d167e5))

- Add ruff pre-commit hook and Claude Code auto-format
  ([#1](https://github.com/The127/combfind/pull/1),
  [`932031a`](https://github.com/The127/combfind/commit/932031aec4b2d2e82ab9cbb2df6b9de42fdc64dc))

- .pre-commit-config.yaml: ruff-format + ruff-check --fix - .claude/settings.json: PostToolUse hook
  so agents using Claude Code auto-format Python files on Edit/Write/MultiEdit (avoids the
  pre-commit hook bouncing commits back during agent loops) - pyproject.toml: add pre-commit>=3.7 to
  dev extras; also resolves leftover merge conflict markers in this file - .gitignore: ignore
  personal .claude/settings.local.json - uv.lock: lockfile for the dev environment

- Enable Sigstore attestations on PyPI releases
  ([`d73b1b8`](https://github.com/The127/combfind/commit/d73b1b83c1da3249258ee91038ff57a0bb6aa2ff))

- Reset version to 1.0.2 to realign with pre-semantic-release history
  ([`b688345`](https://github.com/The127/combfind/commit/b688345c10d6a3533ac4c828a4f204a9c322214a))

### Code Style

- Apply ruff format and lint across codebase ([#2](https://github.com/The127/combfind/pull/2),
  [`be90ab0`](https://github.com/The127/combfind/commit/be90ab0d39f9819b3a6c1ebe003390d4cf2307d8))

- Run `ruff format` on all Python files - Run `ruff check --fix` to apply auto-fixable lint rules
  (imports ordering, unused names, etc.) - Manually break the remaining E501 (line-too-long)
  violations using implicit Python string concatenation; SQL/prompt content is preserved verbatim
  (only intra-string whitespace changes, which is irrelevant for SQLite and language-model prompts)
  - Rename the inner loop variable `l` (E741: ambiguous, looks like 1) in cluster.py to a meaningful
  name

No behavioral changes.

### Continuous Integration

- Fold conventional commit lint into release.yml, add commit-msg hook
  ([`93cce0a`](https://github.com/The127/combfind/commit/93cce0a5942cfeb4956c80f886af70fca6e69e48))

- Replace inline version bump with python-semantic-release, add conventional commit enforcement
  ([`38d1fd2`](https://github.com/The127/combfind/commit/38d1fd25cd172cc8e99cd007fad372a3df8471dc))

- python-semantic-release reads conventional commits to determine bump type (feat→minor, fix→patch,
  BREAKING CHANGE→major) and only releases when there is something releasable — chore/docs/style
  pushes are no-ops - Removes the hacky commit-message if-condition on the test job;
  semantic-release commits with [skip ci] to break the loop cleanly - Adds fetch-depth: 0 so
  semantic-release can walk the full tag history - Adds concurrency: release to prevent overlapping
  release runs - PyPI publish and Sigstore attestations still go through pypa/gh-action-pypi-publish
  (semantic-release handles tag + GitHub release only) - New conventional-commits.yml validates PR
  titles via amannn/action-semantic-pull-request so squash-merge commit messages stay well-formed

- Retrigger release
  ([`c40f392`](https://github.com/The127/combfind/commit/c40f392afca0a7c107a655745125c060f3e19f2a))

### Documentation

- Add CONTRIBUTING.md with dev setup, commit conventions, and release pipeline
  ([`fe2fdb1`](https://github.com/The127/combfind/commit/fe2fdb1594af4709cfdba77ea25e3273c89e47e2))

- Document HF_HUB_OFFLINE env var
  ([`af8e5a2`](https://github.com/The127/combfind/commit/af8e5a2e798230dd535998db9060707f4bfc5b6b))

- Update README for package-aware clustering, MLX, exclude-regex tip
  ([`655b68d`](https://github.com/The127/combfind/commit/655b68d112d255519b106223429fc52d74ea205d))

### Features

- Add --llm-workers parallelism for docgen and label stages
  ([`caba5d5`](https://github.com/The127/combfind/commit/caba5d5dbd65e252bf8eccf30140614a187da4b3))

- Add debug logging per package in cluster stage
  ([`d467436`](https://github.com/The127/combfind/commit/d467436fd852527e688acb9e804f83318f047c27))

- Add debug logging to query path (candidates, rerank scores)
  ([`5ab0ec4`](https://github.com/The127/combfind/commit/5ab0ec4e578c2bddc4a504ecff040b63b2ab4713))

- Add inspect command with callers, callees, concept siblings
  ([`e8f2f9d`](https://github.com/The127/combfind/commit/e8f2f9d87934d8819524bb39690cc5acb63459da))

- Add MLX backend for Apple Silicon via --llm-mode mlx
  ([`3e5b749`](https://github.com/The127/combfind/commit/3e5b7493f4c66d61f06cd2fe0fb0bc6dcc1f06c5))

- Agentic query loop with --agentic-limit, tuned steering prompt, cached embed model
  ([`2d7ef26`](https://github.com/The127/combfind/commit/2d7ef26842e4097f687a886aab8842816e897379))

- Bump default model and add COMBFIND_MODEL env var
  ([#4](https://github.com/The127/combfind/pull/4),
  [`604b45e`](https://github.com/The127/combfind/commit/604b45e51179a3f9c53cb370267fc36f71492498))

- Default model: Qwen2.5-3B-Instruct (Q4_K_M) → Qwen2.5-Coder-3B-Instruct (Q6_K). The Coder variant
  is purpose-built for code, and Q6_K is a less lossy quantization (~2.5 GB vs ~2 GB) -
  `--llm-model` on `init` now also reads `COMBFIND_MODEL` from the env - `query` gains `--llm-model`
  (also reading `COMBFIND_MODEL`) so reranking and agentic queries can pick a specific model without
  falling back to whatever auto-detection finds first

Flag name `--llm-model` is unchanged.

- Enable reranker via --rerank --llm-mode on query command
  ([`ed68334`](https://github.com/The127/combfind/commit/ed68334406458dd5667a591758eb5d4800ca3711))

- Make docgen opt-in via --docgen flag (off by default)
  ([`c9ece19`](https://github.com/The127/combfind/commit/c9ece198e6b01b90d2f50bebdff4a287f5998c5c))

- Replace HDBSCAN with package-aware clustering
  ([`29865f6`](https://github.com/The127/combfind/commit/29865f624469afe79db51a70b50522c552f87c37))

Groups symbols by directory (package), sub-clusters large packages with KMeans at ~20
  symbols/concept. Deterministic, stable, and produces ~10x fewer concepts on real repos.
