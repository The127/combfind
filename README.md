# combfind

When an AI coding agent gets a ticket like "users get logged out randomly on mobile," it has two failure modes: it reads too many files burning tokens and time, or it finds *a* relevant file and patches it locally, missing that the bug lives in shared code, an interface, or a sibling implementation.

combfind fixes this. It builds a concept map of a codebase so an agent can query "session token refresh" and get back ranked symbols with files and line ranges. The key is what it tells you about structure: is this an interface, an implementation, or one of several siblings that all need to change together? That context is what prevents a local patch to the wrong layer. In practice it cuts orientation-phase token cost by **50-66%** (measured on one dev loop; your mileage will vary): the agent reads 3-5 targeted files instead of scanning dozens.

Runs entirely locally. Doesn't require paid APIs.

## Install

```bash
# Local LLM (llama.cpp)
pip install "combfind[llm]" \
  --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu

# Apple Silicon (MLX)
pip install "combfind[mlx]"

# Remote OpenAI-compatible API
pip install "combfind[openai]"

# Gleam support
pip install "combfind[gleam]"
```

Download the default local model (~2.5 GB):

```bash
combfind download-model
```

## Quick start

```bash
# Build the index
combfind init /path/to/repo --db repo.db

# Query it
combfind query "how does authentication work" --db repo.db

# Inspect a symbol from the results
combfind inspect auth.service.AuthService --db repo.db
```

## Usage

### init: build the index

```bash
# Basic
combfind init /path/to/repo --db repo.db

# Exclude test files (recommended for cleaner concepts)
combfind init /path/to/repo --db repo.db --exclude-regex '.*test.*'

# OpenAI-compatible API
COMBFIND_LLM_API_KEY=sk-... COMBFIND_LLM_MODEL=gpt-4o-mini \
  combfind init /path/to/repo --db repo.db --llm-mode openai

# Apple Silicon MLX
combfind init /path/to/repo --db repo.db --llm-mode mlx \
  --llm-model mlx-community/Qwen2.5-7B-Instruct-4bit
```

| Flag | Default | Description |
|------|---------|-------------|
| `--db` | `<repo_path>/.combfind.db` | Output database path |
| `--llm-mode` | `local` | LLM backend: `local`, `openai`, or `mlx` |
| `--llm-model` | auto-detected | GGUF path (local) or HF repo ID (mlx) |
| `--exclude-paths` | | Paths to skip, relative to repo root (repeatable) |
| `--exclude-regex` | | Regex matched against file paths to skip |
| `--llm-workers` | `1` | Parallel LLM calls (useful with `--llm-mode openai`) |
| `--docgen` | off | Generate docstrings for undocumented symbols (slow) |
| `--force` | off | Re-run all stages, ignoring the cache |

### query: search the index

```bash
combfind query "users get logged out randomly" --db repo.db
combfind query "where are database migrations" --db repo.db --format json
```

**Text output:**
```
[1] Token Refresh (implementation) - 0.87
    why: Handles session token validation and refresh logic.
    auth/service.py
      auth.service.AuthService.refresh  :42-67
      auth.service.AuthService.validate  :70-91
```

**JSON output:**
```json
[
  {
    "rank": 1,
    "concept": "Token Refresh",
    "role": "implementation",
    "score": 0.87,
    "files": [
      {
        "path": "auth/service.py",
        "symbols": [
          {"name": "refresh", "qualified_name": "auth.service.AuthService.refresh", "start_line": 42, "end_line": 67},
          {"name": "validate", "qualified_name": "auth.service.AuthService.validate", "start_line": 70, "end_line": 91}
        ]
      }
    ],
    "why_relevant": "Handles session token validation and refresh logic.",
    "sibling_implementations": []
  }
]
```

| Flag | Default | Description |
|------|---------|-------------|
| `--db` | `.combfind.db` | Database to query |
| `--top-k` | `5` | Number of results |
| `--format` | `text` | `text` or `json` |
| `--rerank` | off | Re-score results with LLM (requires `--llm-mode`) |
| `--agentic` | off | Iterative query loop: LLM steers follow-up searches until satisfied (requires `--llm-mode`) |
| `--agentic-limit` | `3` | Max iterations for `--agentic` |
| `--llm-mode` | | LLM backend for `--rerank` / `--agentic`: `local`, `openai`, or `mlx` |

### inspect: look up a symbol

```bash
combfind inspect auth.service.AuthService --db repo.db
combfind inspect auth.service.AuthService auth.service.TokenService --db repo.db --format json
```

**Output:**
```
auth.service.AuthService  (class, auth/service.py:10-80)
concept:  Token Refresh  [implementation]
sig:      class AuthService

callers (1):
  auth.mock.MockAuthService  auth/mock.py:5

callees (1):
  auth.service.AuthService.validate  auth/service.py:20

concept siblings (1):
  auth.service.AuthService.validate  [method]  auth/service.py
```

| Flag | Default | Description |
|------|---------|-------------|
| `--db` | `.combfind.db` | Database to query |
| `--format` | `text` | `text` or `json` |

## How it works

The `init` pipeline runs six stages, each reading and writing to a SQLite file:

1. **parse**: tree-sitter extracts files, symbols (signatures, line ranges, docstrings, imports)
2. **index**: SCIP or tree-sitter heuristics populate a `references` table of calls, imports, and inheritance edges
3. **embed**: sentence-transformers produces a vector per symbol
4. **cluster**: symbols are grouped by package/directory, then sub-clustered with KMeans (~20 symbols per concept)
5. **label**: a local LLM names and describes each cluster and assigns a structural role (see [Concept roles](#concept-roles) below)
6. **embed concepts**: sentence-transformers produces a vector per concept description

At query time: embed the query, cosine search over concept embeddings, optionally rerank with LLM, expand top concepts to member symbols and 1-hop callers/callees, return ranked symbols and code regions.

Stages are cached by a content hash of their inputs. When you re-run `init`, only stages affected by changed files are re-executed; the rest are skipped. Pass `--force` to rebuild from scratch.

## Performance

All numbers below are from my own ~50k LOC Go codebase using Qwen2.5:7b via Ollama. Treat them as directional, not a cross-repo benchmark.

Initial index builds in ~5 minutes. Query time is around 7 seconds, most of which is loading the local model on the first call. In `--agentic` mode the model is loaded once and kept warm across all iterations, so a 3-iteration run is roughly 7s + 2x steer time, not 3x7s.

**Incremental reindexing is fast.** When a handful of files change, re-running `init` takes around 30 seconds; only the stages affected by changed files are re-executed. The index is also crash-safe: progress is committed to SQLite in batches within each stage, so if a run is interrupted it picks up close to where it left off rather than starting over.

The goal is not to replace careful code reading. It is to give an agent a cheap orientation pass so it knows which 3-5 files to read rather than all 500. On that goal, combfind achieves file_recall@3 of **0.75** on structural queries with `--rerank`, evaluated against 10 hand-picked bug fixes from that codebase (n=10, single repo). No API costs, no multi-step LLM pipelines, runs fully local.

## How to query well

combfind matches against concept descriptions, so structural queries outperform symptom descriptions.

"Where are user creation request DTOs and their field definitions?" finds the right code immediately. "EmailVerified boolean gets rejected by the validator" does not, because the symptom vocabulary has no overlap with the code structure.

When an agent receives a bug ticket, the right move is to translate the symptom into a structural question before querying: not *what went wrong*, but *where does this kind of code live*.

## Concept roles

Every concept cluster is tagged with one of seven roles. An agent that finds `TokenRefresh` tagged `interface` knows to also look at all `implementation` siblings before touching anything. Not because it's smart, but because combfind surfaced them.

| Role | Meaning |
|------|---------|
| `interface` | Contract or protocol definition; changes here propagate to all implementations |
| `implementation` | Concrete implementation of an interface; there may be siblings that also need updating |
| `orchestrator` | Coordinates other components; high fan-out, changes ripple broadly |
| `entry_point` | Top-level handlers (HTTP routes, CLI commands, queue consumers) |
| `domain_model` | Core data structures and business entities |
| `infrastructure` | I/O, persistence, external service clients |
| `cross_cutting` | Utilities, logging, auth middleware used throughout |

## Supported languages

Python, Go, Java, Kotlin, Gleam, Erlang.

## Optional SCIP tools

These are not required but produce more accurate call and import edges than the tree-sitter fallback:

| Tool | Language | Install |
|------|----------|---------|
| `scip-go` | Go | `go install github.com/scip-code/scip-go/cmd/scip-go@latest` |
| `scip-python` | Python | `npm install -g @sourcegraph/scip-python` |
| `scip-java` | Java | [scip-java releases](https://github.com/sourcegraph/scip-java/releases) |

## Using a remote LLM

Pass `--llm-mode openai` to use any OpenAI-compatible API:

```bash
export COMBFIND_LLM_BASE_URL=https://api.openai.com/v1
export COMBFIND_LLM_API_KEY=sk-...
export COMBFIND_LLM_MODEL=gpt-4o-mini

combfind init /path/to/repo --db repo.db --llm-mode openai
```

Works with OpenAI, Ollama (`http://localhost:11434/v1`), LM Studio (`http://localhost:1234/v1`), and any other OpenAI-compatible server.

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `COMBFIND_LOG_LEVEL` | `info` | Log verbosity: `debug`, `info`, `warning`, `error` |
| `COMBFIND_MODEL` | auto-detected | GGUF path (local) or HF repo ID (mlx); equivalent to `--llm-model` |
| `COMBFIND_LLM_BASE_URL` | | Base URL for OpenAI-compatible API |
| `COMBFIND_LLM_API_KEY` | | API key for remote LLM |
| `COMBFIND_LLM_MODEL` | `gpt-4o-mini` | Model name for `--llm-mode openai` |
| `HF_HUB_OFFLINE` | | Set to `1` to use cached embedding models without network access |

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for dev setup, commit conventions, and the release pipeline.
