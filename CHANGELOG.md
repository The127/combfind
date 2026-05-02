# CHANGELOG


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
