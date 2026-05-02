# combfind

Give an AI agent a codebase. combfind tells it where to look.

combfind builds a local index of a repository so an agent can find the right files and functions for a task with a plain-text query, without reading the entire codebase.

## Install

For local LLM inference:

```bash
pip3 install "combfind[llm]" \
  --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu
```

Download the default model (Qwen2.5-Coder-3B-Instruct Q6_K, ~2.5 GB):

```bash
combfind download-model
```

For a remote OpenAI-compatible API instead:

```bash
pip3 install "combfind[openai]"
```

For Apple Silicon (MLX):

```bash
pip3 install "combfind[mlx]"
```

## Usage

```bash
# Index a repository (local LLM, auto-detected model)
combfind init /path/to/repo --db repo.db

# Exclude test files (recommended for cleaner concepts)
combfind init /path/to/repo --db repo.db --exclude-regex '.*test.*'

# Index using a remote OpenAI-compatible API
COMBFIND_LLM_API_KEY=sk-... COMBFIND_LLM_MODEL=gpt-4o-mini \
  combfind init /path/to/repo --db repo.db --llm-mode openai

# Index using Apple Silicon MLX
combfind init /path/to/repo --db repo.db --llm-mode mlx \
  --llm-model mlx-community/Qwen2.5-7B-Instruct-4bit

# Query it
combfind query "how does authentication work" --db repo.db
combfind query "where are database migrations" --db repo.db --format json

# Inspect a symbol returned by a query
combfind inspect auth.service.AuthService --db repo.db
combfind inspect auth.service.AuthService --db repo.db --format json
```

### Query output (text)

```
[1] Token Refresh (implementation) — 0.87
    why: Handles session token validation and refresh logic.
    auth/service.py
      auth.service.AuthService.refresh  :42-67
      auth.service.AuthService.validate  :70-91
```

### Query output (JSON)

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

### Inspect output (text)

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

### Init options

| Flag | Default | Description |
|------|---------|-------------|
| `--db` | `<repo_path>/.combfind.db` | Output path |
| `--llm-model` | auto-detected | Path to a GGUF model file (local mode only) |
| `--llm-mode` | `local` | LLM backend: `local` (llama.cpp), `openai` (OpenAI-compatible API), or `mlx` (Apple Silicon) |
| `--exclude-paths` | - | Paths to skip relative to repo root (repeatable) |
| `--exclude-regex` | - | Regex matched against file paths to skip |
| `--llm-workers` | `1` | Parallel LLM calls (useful with `--llm-mode openai`) |
| `--docgen` | off | Generate LLM docstrings for undocumented symbols (slow) |
| `--force` | off | Re-run all stages, ignoring the cache |

### Query options

| Flag | Default | Description |
|------|---------|-------------|
| `--db` | `.combfind.db` | Database to query |
| `--top-k` | 5 | Number of results to return |
| `--format` | `text` | Output format: `text` or `json` |
| `--rerank` | off | Re-score results with LLM for better precision (requires `--llm-mode`) |
| `--agentic` | off | Run iterative query loop: LLM steers follow-up searches until satisfied (requires `--llm-mode`) |
| `--agentic-limit` | `3` | Max iterations for `--agentic` mode |
| `--llm-mode` | - | LLM backend for `--rerank` / `--agentic`: `local` or `openai` |

### Inspect options

| Flag | Default | Description |
|------|---------|-------------|
| `--db` | `.combfind.db` | Database to query |
| `--format` | `text` | Output format: `text` or `json` |

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `COMBFIND_LOG_LEVEL` | `info` | Log verbosity: `debug`, `info`, `warning`, `error` |
| `COMBFIND_MODEL` | (auto-detected) | GGUF path for `local` mode / HF repo for `mlx` mode; equivalent to `--llm-model` |
| `COMBFIND_LLM_BASE_URL` | - | Base URL for OpenAI-compatible API (e.g. `https://api.openai.com/v1`) |
| `COMBFIND_LLM_API_KEY` | - | API key for the remote LLM |
| `COMBFIND_LLM_MODEL` | `gpt-4o-mini` | Model name to use with `--llm-mode openai` |
| `HF_HUB_OFFLINE` | - | Set to `1` to skip HuggingFace network checks and use cached embedding models only |

## Using a remote LLM API

Pass `--llm-mode openai` to use any OpenAI-compatible API instead of a local model. Configure it with environment variables:

```bash
export COMBFIND_LLM_BASE_URL=https://api.openai.com/v1
export COMBFIND_LLM_API_KEY=sk-...
export COMBFIND_LLM_MODEL=gpt-4o-mini

combfind init /path/to/repo --db repo.db --llm-mode openai
```

Any API that speaks the OpenAI chat completions format works, including:

- **OpenAI** — set `COMBFIND_LLM_BASE_URL=https://api.openai.com/v1`
- **Ollama** — set `COMBFIND_LLM_BASE_URL=http://localhost:11434/v1` and `COMBFIND_LLM_API_KEY=ollama`
- **LM Studio** — set `COMBFIND_LLM_BASE_URL=http://localhost:1234/v1`
- **Any other OpenAI-compatible server** — point `COMBFIND_LLM_BASE_URL` at its `/v1` endpoint

`--llm-model` is ignored in openai mode; the model is selected via `COMBFIND_LLM_MODEL`.

## Clustering

combfind groups symbols by their package/directory, then sub-clusters large packages using KMeans (targeting ~20 symbols per concept). This produces stable, interpretable concepts aligned with the codebase structure.

For best results, exclude test files at index time:

```bash
combfind init . --exclude-regex '.*test.*'
```

## Supported languages

Python, Go. More languages can be added via tree-sitter grammars.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for dev setup, commit conventions, and how the release pipeline works.
