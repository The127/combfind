import os
from pathlib import Path

import click

from combfind.db import create_schema, get_connection

_MODELS_DIR = Path.home() / ".cache" / "combfind" / "models"
_DEFAULT_REPO = "Qwen/Qwen2.5-3B-Instruct-GGUF"
_DEFAULT_FILE = "qwen2.5-3b-instruct-q4_k_m.gguf"


def _default_llm_model() -> str | None:
    if not _MODELS_DIR.exists():
        return None
    ggufs = sorted(_MODELS_DIR.glob("*.gguf"))
    return str(ggufs[0]) if ggufs else None


@click.group()
def cli():
    """combfind — queryable concept map of a codebase."""


@cli.command("init")
@click.argument("repo_path", default=".", required=False)
@click.option("--db", default=None, help="Database path (default: <repo_path>/.combfind.db)")
@click.option("--llm-model", default=None, help="Path to GGUF model file (auto-detected if omitted)")
@click.option("--llm-mode", default="local", show_default=True,
              type=click.Choice(["local", "openai"]),
              help="LLM backend: local (llama.cpp) or openai (OpenAI-compatible API via env vars)")
@click.option("--exclude-paths", multiple=True, metavar="PATH",
              help="Paths to exclude relative to repo root (repeatable)")
@click.option("--exclude-regex", default=None, metavar="PATTERN",
              help="Regex matched against file paths to exclude")
def init_cmd(repo_path, db, llm_model, llm_mode, exclude_paths, exclude_regex):
    """Index a repository."""
    from combfind.pipeline import run as pipeline_run
    from combfind.llm import create_backend

    db_path = db or os.path.join(repo_path, ".combfind.db")
    conn = get_connection(db_path)
    create_schema(conn)
    conn.close()

    resolved_llm = llm_model or _default_llm_model()

    if llm_mode == "local" and resolved_llm is None:
        raise click.ClickException("no model found; run combfind download-model or pass --llm-model")

    backend = create_backend(llm_mode, llm_model=resolved_llm)

    pipeline_run.run(
        db_path,
        backend=backend,
        repo_path=repo_path,
        llm_model=resolved_llm,
        exclude_paths=list(exclude_paths) or None,
        exclude_regex=exclude_regex,
    )


@cli.command("query")
@click.argument("text")
@click.option("--db", default=".combfind.db", show_default=True)
@click.option("--top-k", default=5, show_default=True)
@click.option("--format", "fmt", default="text", show_default=True,
              type=click.Choice(["text", "json"]))
def query_cmd(text, db, top_k, fmt):
    """Query the index with free text."""
    from combfind import query as query_mod
    results = query_mod.query(text, db_path=db, top_k=top_k)
    query_mod.print_results(results, fmt=fmt)


@cli.command("download-model")
@click.option("--repo", default=_DEFAULT_REPO, show_default=True)
@click.option("--file", "filename", default=_DEFAULT_FILE, show_default=True)
@click.option("--dest", default=None, help="Destination directory (default: ~/.cache/combfind/models)")
def download_model(repo, filename, dest):
    """Download a GGUF model to the local cache."""
    try:
        from huggingface_hub import hf_hub_download
    except ImportError:
        raise click.ClickException('huggingface_hub is required: pip install "combfind[llm]"')

    dest_dir = Path(dest) if dest else _MODELS_DIR
    dest_dir.mkdir(parents=True, exist_ok=True)

    click.echo(f"Downloading {filename} from {repo} ...")
    path = hf_hub_download(repo_id=repo, filename=filename, local_dir=str(dest_dir))
    click.echo(f"Saved to: {path}")
    click.echo(f"Run combfind init to build an index - model will be auto-detected.")
