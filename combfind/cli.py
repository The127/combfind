import click

from combfind.db import create_schema, get_connection


@click.group()
def cli():
    """combfind — queryable concept map of a codebase."""


@cli.command()
@click.argument("repo_path")
@click.option("--db", default=None, help="Output db path (default: <repo_path>/.combfind.db)")
@click.option("--stages", default=None, help="Comma-separated stage names")
@click.option("--force", is_flag=True, help="Clear pipeline_runs and re-run all stages")
@click.option("--embed-model", default="all-MiniLM-L6-v2", show_default=True)
@click.option("--llm-model", default=None, help="Path to GGUF file (required for stage 5 and --rerank)")
@click.option("--llm-ctx", default=None, type=int)
@click.option("--cluster-min-size", default=None, type=int)
@click.option("--noise", default="singleton", show_default=True,
              type=click.Choice(["singleton", "merge", "drop"]))
@click.option("--exclude-paths", multiple=True, metavar="PATH",
              help="Paths to exclude relative to repo root (repeatable, e.g. --exclude-paths tests)")
@click.option("--exclude-regex", default=None, metavar="PATTERN",
              help="Regex matched against relative file paths to exclude (e.g. '.*_generated\\.py')")
def build(repo_path, db, stages, force, embed_model, llm_model, llm_ctx, cluster_min_size,
          noise, exclude_paths, exclude_regex):
    """Build a combfind map for a repository."""
    import os
    from combfind.pipeline import run as pipeline_run

    db_path = db or os.path.join(repo_path, ".combfind.db")
    conn = get_connection(db_path)
    create_schema(conn)
    conn.close()

    stage_list = stages.split(",") if stages else None
    pipeline_run.run(
        db_path,
        repo_path=repo_path,
        stages=stage_list,
        force=force,
        embed_model=embed_model,
        llm_model=llm_model,
        llm_ctx=llm_ctx,
        cluster_min_size=cluster_min_size,
        noise=noise,
        exclude_paths=list(exclude_paths) or None,
        exclude_regex=exclude_regex,
    )


@cli.command("query")
@click.argument("text")
@click.option("--db", required=True)
@click.option("--top-k", default=5, show_default=True)
@click.option("--rerank", is_flag=True)
@click.option("--llm-model", default=None)
@click.option("--format", "fmt", default="text", show_default=True,
              type=click.Choice(["text", "json"]))
def query_cmd(text, db, top_k, rerank, llm_model, fmt):
    """Query a combfind map with free text."""
    from combfind import query as query_mod
    results = query_mod.query(text, db_path=db, top_k=top_k, rerank=rerank, llm_model=llm_model)
    query_mod.print_results(results, fmt=fmt)


@cli.command("stage")
@click.argument("stage_name")
@click.argument("db_path")
@click.argument("extra", nargs=-1, metavar="KEY=VALUE")
def stage_cmd(stage_name, db_path, extra):
    """Run a single pipeline stage against an existing db."""
    from combfind.pipeline import run as pipeline_run

    params = {}
    for kv in extra:
        k, _, v = kv.partition("=")
        params[k.replace("-", "_")] = v

    pipeline_run.run_stage(stage_name, db_path, **params)


@cli.command("eval")
@click.option("--db", required=True)
@click.option("--tickets", required=True, help="Directory of fixture subdirs")
@click.option("--k", "k_values", default="3,5", show_default=True)
def eval_cmd(db, tickets, k_values):
    """Run eval fixtures and report recall@k."""
    from combfind.eval import harness

    ks = [int(k) for k in k_values.split(",")]
    harness.run(db_path=db, fixtures_dir=tickets, ks=ks)


@cli.command("info")
@click.argument("db_path")
def info(db_path):
    """Print pipeline stage statuses, counts, and build config."""
    import os

    conn = get_connection(db_path)

    click.echo(f"db: {db_path}  ({os.path.getsize(db_path) // 1024} KB)")
    click.echo("")

    rows = conn.execute(
        "SELECT stage, status, completed_at FROM pipeline_runs ORDER BY stage"
    ).fetchall()
    if rows:
        click.echo("Pipeline stages:")
        for r in rows:
            click.echo(f"  {r['stage']:<20} {r['status']}")
        click.echo("")

    for table in ("files", "symbols", "concepts"):
        n = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        click.echo(f"  {table}: {n}")

    cfg = conn.execute("SELECT key, value FROM build_config").fetchall()
    if cfg:
        click.echo("")
        click.echo("Build config:")
        for row in cfg:
            click.echo(f"  {row['key']}: {row['value']}")

    conn.close()
