# combfind

Give an AI agent a codebase. combfind tells it where to look.

combfind builds a local index of a repository so an agent can find the right files and functions for a task with a plain-text query, without reading the entire codebase.

## Install

```bash
pip install "combfind[llm]" \
  --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu
```

Download a model (one-time, ~2 GB):

```bash
combfind download-model
```

## Usage

```bash
# Index a repository
combfind build /path/to/repo --db repo.db

# Query it
combfind query "how does authentication work" --db repo.db
combfind query "where are database migrations" --db repo.db --format json
```

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

### Build options

| Flag | Default | Description |
|------|---------|-------------|
| `--db` | `<repo>/.combfind.db` | Output path |
| `--force` | off | Ignore cache, re-index from scratch |
| `--llm-model` | auto | Path to a GGUF model file |
| `--exclude-paths` | - | Paths to skip, relative to repo root (repeatable) |
| `--exclude-regex` | - | Regex matched against file paths to skip |

## Supported languages

Python, Go. More languages can be added via tree-sitter grammars.
