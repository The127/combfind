import os
from pathlib import Path

import click

from combfind.db import create_schema, get_connection

_MODELS_DIR = Path.home() / ".cache" / "combfind" / "models"
_DEFAULT_REPO = "Qwen/Qwen2.5-Coder-3B-Instruct-GGUF"
_DEFAULT_FILE = "qwen2.5-coder-3b-instruct-q6_k.gguf"


def _default_llm_model() -> str | None:
    if not _MODELS_DIR.exists():
        return None
    preferred = _MODELS_DIR / _DEFAULT_FILE
    if preferred.exists():
        return str(preferred)
    ggufs = sorted(_MODELS_DIR.glob("*.gguf"))
    return str(ggufs[0]) if ggufs else None


@click.group()
def cli():
    """combfind — queryable concept map of a codebase."""


@cli.command("version")
def version_cmd():
    """Show the installed version."""
    from importlib.metadata import version

    click.echo(version("combfind"))


@cli.command("init")
@click.argument("repo_path", default=".", required=False)
@click.option(
    "--db", default=None, help="Database path (default: <repo_path>/.combfind.db)"
)
@click.option(
    "--llm-model",
    default=None,
    envvar="COMBFIND_MODEL",
    show_envvar=True,
    help="Path to GGUF model file (auto-detected if omitted)",
)
@click.option(
    "--llm-mode",
    default="local",
    show_default=True,
    type=click.Choice(["local", "openai", "mlx"]),
    help=(
        "LLM backend: local (llama.cpp), openai (OpenAI-compatible API), "
        "or mlx (Apple Silicon)"
    ),
)
@click.option(
    "--exclude-paths",
    multiple=True,
    metavar="PATH",
    help="Paths to exclude relative to repo root (repeatable)",
)
@click.option(
    "--exclude-regex",
    default=None,
    metavar="PATTERN",
    help="Regex matched against file paths to exclude",
)
@click.option(
    "--force", is_flag=True, default=False, help="Re-run all stages, ignoring cache"
)
@click.option(
    "--llm-workers",
    default=1,
    show_default=True,
    type=int,
    help="Number of parallel LLM calls (useful for remote APIs)",
)
@click.option(
    "--docgen",
    is_flag=True,
    default=False,
    help="Generate LLM docstrings for undocumented symbols (slow; off by default)",
)
def init_cmd(
    repo_path,
    db,
    llm_model,
    llm_mode,
    exclude_paths,
    exclude_regex,
    force,
    llm_workers,
    docgen,
):
    """Index a repository."""
    from combfind.llm import create_backend
    from combfind.pipeline import run as pipeline_run

    db_path = db or os.path.join(repo_path, ".combfind.db")
    conn = get_connection(db_path)
    create_schema(conn)
    conn.close()

    resolved_llm = llm_model or _default_llm_model()

    if llm_mode == "local" and resolved_llm is None:
        raise click.ClickException(
            "no model found; run combfind download-model or pass --llm-model"
        )
    if llm_mode == "mlx" and resolved_llm is None:
        raise click.ClickException(
            "--llm-model is required for mlx mode (HuggingFace repo ID or local path)"
        )

    backend = create_backend(llm_mode, llm_model=resolved_llm)

    pipeline_run.run(
        db_path,
        backend=backend,
        repo_path=repo_path,
        llm_model=resolved_llm,
        force=force,
        docgen=docgen,
        llm_workers=llm_workers,
        exclude_paths=list(exclude_paths) or None,
        exclude_regex=exclude_regex,
    )


@cli.command("query")
@click.argument("text")
@click.option("--db", default=".combfind.db", show_default=True)
@click.option("--top-k", default=5, show_default=True)
@click.option(
    "--format",
    "fmt",
    default="text",
    show_default=True,
    type=click.Choice(["text", "json"]),
)
@click.option(
    "--rerank",
    is_flag=True,
    default=False,
    help="Rerank results with LLM (requires --llm-mode)",
)
@click.option(
    "--agentic",
    is_flag=True,
    default=False,
    help="Run iterative agentic query loop (requires --llm-mode)",
)
@click.option(
    "--agentic-limit",
    default=3,
    show_default=True,
    type=int,
    help="Max iterations for --agentic mode",
)
@click.option(
    "--llm-mode",
    default=None,
    type=click.Choice(["local", "openai", "mlx"]),
    help="LLM backend for reranking or agentic mode",
)
@click.option(
    "--llm-model",
    default=None,
    envvar="COMBFIND_MODEL",
    show_envvar=True,
    help="Path to GGUF model file (auto-detected if omitted)",
)
def query_cmd(
    text, db, top_k, fmt, rerank, agentic, agentic_limit, llm_mode, llm_model
):
    """Query the index with free text."""
    from combfind import query as query_mod

    backend = None
    if rerank or agentic:
        if llm_mode is None:
            raise click.ClickException("--rerank and --agentic require --llm-mode")
        from combfind.llm import create_backend

        backend = create_backend(llm_mode, llm_model=llm_model or _default_llm_model())

    if agentic:
        results = query_mod.agentic_query(
            text, db_path=db, top_k=top_k, backend=backend, max_iterations=agentic_limit
        )
    else:
        results = query_mod.query(
            text, db_path=db, top_k=top_k, rerank=rerank, backend=backend
        )
    query_mod.print_results(results, fmt=fmt)


@cli.command("inspect")
@click.argument("qualified_names", nargs=-1, required=True)
@click.option("--db", default=".combfind.db", show_default=True)
@click.option(
    "--format",
    "fmt",
    default="text",
    show_default=True,
    type=click.Choice(["text", "json"]),
)
def inspect_cmd(qualified_names, db, fmt):
    """Inspect one or more symbols: callers, callees, concept, siblings."""
    import json as _json

    from combfind.inspect import find_candidates, inspect_symbol, print_inspect

    results = []
    for name in qualified_names:
        result = inspect_symbol(name, db_path=db)
        if result is None:
            candidates = find_candidates(name, db_path=db)
            if candidates:
                raise click.ClickException(
                    f"no exact match for {name!r}; did you mean:\n"
                    + "\n".join(f"  {c}" for c in candidates)
                )
            raise click.ClickException(f"symbol not found: {name!r}")
        results.append(result)

    if fmt == "json":
        print(_json.dumps(results, indent=2))
    else:
        for i, result in enumerate(results):
            if i > 0:
                print()
            print_inspect(result, fmt="text")


@cli.command("download-model")
@click.option("--repo", default=_DEFAULT_REPO, show_default=True)
@click.option("--file", "filename", default=_DEFAULT_FILE, show_default=True)
@click.option(
    "--dest",
    default=None,
    help="Destination directory (default: ~/.cache/combfind/models)",
)
def download_model(repo, filename, dest):
    """Download a GGUF model to the local cache."""
    try:
        from huggingface_hub import hf_hub_download
    except ImportError:
        raise click.ClickException(
            'huggingface_hub is required: pip install "combfind[llm]"'
        )

    dest_dir = Path(dest) if dest else _MODELS_DIR
    dest_dir.mkdir(parents=True, exist_ok=True)

    click.echo(f"Downloading {filename} from {repo} ...")
    path = hf_hub_download(repo_id=repo, filename=filename, local_dir=str(dest_dir))
    click.echo(f"Saved to: {path}")
    click.echo("Run combfind init to build an index - model will be auto-detected.")
