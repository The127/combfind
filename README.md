# combfind

A queryable, concept-aware map of a codebase — built locally, no paid APIs.

combfind indexes a repository into a SQLite file that an LLM coding agent can query with free text to find the right work area for a task, without reading thousands of files.

## Why

When an AI agent gets a ticket like "users get logged out randomly on mobile," it has two failure modes:

1. It reads too many files hunting for relevant code, burning tokens and time.
2. It patches *a* file locally, missing that the bug is in shared code, an interface contract, or affects sibling implementations.

combfind addresses both: fast retrieval of the right area, and explicit awareness of structural relationships (interfaces, implementations, orchestrators) so agents know when a fix is local vs. shared vs. contractual.

## Install

```bash
pip install combfind
```

LLM labeling (stage 5) requires `llama-cpp-python`. Install the pre-built CPU wheel to avoid compiler hassle:

```bash
pip install "combfind[llm]" \
  --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu
```

Then download a model (Qwen2.5-3B, ~2 GB, one-time):

```bash
combfind download-model
```

## Usage

```bash
# Build the map (LLM model auto-detected from cache after download-model)
combfind build /path/to/repo --db repo.db

# Query
combfind query "how does authentication work" --db repo.db
combfind query "where are database migrations" --db repo.db --format json

# Inspect pipeline state
combfind info repo.db

# Re-run a single stage
combfind stage parse repo.db
combfind stage label repo.db llm_model=/path/to/model.gguf
```

### Build options

| Flag | Default | Description |
|------|---------|-------------|
| `--db` | `<repo>/.combfind.db` | Output database path |
| `--stages` | all | Comma-separated stage names to run |
| `--force` | off | Clear cache and re-run all stages |
| `--embed-model` | `all-MiniLM-L6-v2` | sentence-transformers model name |
| `--llm-model` | auto | Path to GGUF file (required for labeling) |
| `--exclude-paths` | — | Paths to exclude relative to repo root (repeatable) |
| `--exclude-regex` | — | Regex matched against relative file paths to exclude |
| `--noise` | `singleton` | How to handle unclustered symbols: `singleton`, `merge`, `drop` |

### Query output (JSON)

```json
[
  {
    "rank": 1,
    "concept": "Token Refresh",
    "role": "implementation",
    "score": 0.87,
    "files": [{"path": "auth/service.py", "start_line": 42, "end_line": 91}],
    "symbols": ["AuthService.refresh", "AuthService.validate"],
    "why_relevant": "Handles session token validation and refresh logic.",
    "sibling_implementations": ["MobileAuthService", "OAuthService"]
  }
]
```

## How it works

The pipeline has six stages, each writing to SQLite:

```
parse   → symbols (tree-sitter: signatures, line ranges, docstrings)
index   → references (inherit relationships between symbols)
embed   → symbol vectors (sentence-transformers)
cluster → concept groups (HDBSCAN over symbol embeddings)
label   → concept names, descriptions, structural roles (local LLM)
embed_concepts → concept vectors (sentence-transformers)
```

Stages 2 and 3 run concurrently. Each stage is independently re-runnable. File-hash caching means re-runs over an unchanged repo are fast.

Query path: embed the input text → cosine search over concept vectors → expand top-k concepts to member symbols and 1-hop callers/callees → return ranked work areas.

## Eval

```bash
combfind eval --db repo.db --tickets eval_data/fixtures/ --k 3,5
```

Fixtures are directories containing `input.txt` (query text) and `expected.json` (expected files and symbols). Metric: recall@k for files and symbols.

## Supported languages

Python (built-in). Additional languages via tree-sitter grammars — add a `LanguageDef` in `combfind/languages/__init__.py`.
