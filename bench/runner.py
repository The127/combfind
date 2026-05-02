"""Paired SPRT runner for combfind autoresearch.

Compares wall-clock init time between two git refs (baseline vs patch),
running paired trials in alternating order until a Wald-style SPRT
decides. The correctness gate (bench/score.py) is run once per side
before any timing — if either side fails the gate, the runner aborts
with no timing reported.

Usage:
    uv run python -m bench.runner [--baseline=REF] [--patch=REF]
                                  [--mode=cold|incremental]
                                  [--alpha=0.05] [--beta=0.05]
                                  [--delta=0.05] [--max-pairs=50]

Defaults:
    baseline = HEAD~1
    patch    = HEAD
    mode     = cold

The runner builds two detached git worktrees in a tmp dir, but always
overrides bench/ with the *current* repo's bench/ — so the pipeline
code under measurement comes from each ref, while the harness is held
constant.

SPRT math (Wald, normal-mean, assumed variance):
    H0: mean(t_baseline - t_patch) = 0       (patch is no faster)
    H1: mean(t_baseline - t_patch) >= delta * baseline_mean

    Variance assumption: sigma_prior = 0.10 * baseline_mean for first
    few pairs; switch to running sample stdev (floored at 0.05 *
    baseline_mean) once n >= 5.

    Decision bounds: upper = log((1-beta)/alpha),
                     lower = log(beta/(1-alpha)).

    Hard cap stops with verdict INDETERMINATE — treat as REJECT in the
    outer loop (preserve the baseline).

Verdicts (also reflected in exit code):
    0  ACCEPT          — patch is at least delta faster
    1  REJECT          — patch is no faster, or hit the hard cap
    2  CORRECTNESS     — gate failed on baseline or patch (no timing)
    3  USAGE / INTERNAL
"""

from __future__ import annotations

import argparse
import json
import math
import random
import shutil
import statistics
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BENCH_DIR = REPO_ROOT / "bench"


@dataclass
class TrialResult:
    pair_index: int
    order: str  # "BP" or "PB"
    t_baseline: float
    t_patch: float

    @property
    def diff(self) -> float:
        return self.t_baseline - self.t_patch


def _resolve(ref: str) -> str:
    out = subprocess.run(
        ["git", "rev-parse", ref],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return out.stdout.strip()


def _setup_worktree(ref: str, work_root: Path, label: str) -> Path:
    """Add a detached worktree at ref, override bench/ from the current repo."""
    target = work_root / f"work_{label}"
    subprocess.run(
        ["git", "worktree", "add", "--detach", str(target), ref],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
    )
    # Keep the bench harness constant: replace whatever bench/ shipped at ref
    # with the current repo's bench/.
    target_bench = target / "bench"
    if target_bench.exists():
        shutil.rmtree(target_bench)
    shutil.copytree(BENCH_DIR, target_bench)
    return target


def _teardown_worktree(target: Path) -> None:
    subprocess.run(
        ["git", "worktree", "remove", "--force", str(target)],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
    )


def _run_score(workdir: Path, mode: str) -> tuple[int, str, str]:
    """Run bench.score in workdir. Returns (returncode, stdout, stderr)."""
    proc = subprocess.run(
        ["uv", "run", "python", "-m", "bench.score", f"--mode={mode}"],
        cwd=workdir,
        capture_output=True,
        text=True,
    )
    return proc.returncode, proc.stdout, proc.stderr


def _gate_check(workdir: Path, mode: str, label: str) -> float:
    """Run scorer once. Returns elapsed_seconds. Exits non-zero on failure."""
    rc, out, err = _run_score(workdir, mode)
    if rc != 0:
        print(
            f"CORRECTNESS gate failed on {label} (exit {rc}):\n{err}",
            file=sys.stderr,
        )
        sys.exit(2)
    try:
        data = json.loads(out.strip().splitlines()[-1])
    except (ValueError, IndexError) as exc:
        print(
            f"INTERNAL: could not parse score output for {label}: {exc}\n{out}",
            file=sys.stderr,
        )
        sys.exit(3)
    return float(data["elapsed_seconds"])


def _timed_run(workdir: Path, mode: str, label: str) -> float:
    """Run scorer expecting it to pass; returns elapsed_seconds."""
    rc, out, err = _run_score(workdir, mode)
    if rc != 0:
        # Timing-loop correctness drift: a side that passed the gate should
        # never fail it later for the same code. Treat as a real regression.
        print(
            f"CORRECTNESS regression mid-trial on {label} (exit {rc}):\n{err}",
            file=sys.stderr,
        )
        sys.exit(2)
    data = json.loads(out.strip().splitlines()[-1])
    return float(data["elapsed_seconds"])


def _sprt(
    diffs: list[float],
    baseline_mean: float,
    alpha: float,
    beta: float,
    delta: float,
) -> tuple[str, float, float]:
    """Wald SPRT log-likelihood. Returns (verdict, lr, sigma_used)."""
    n = len(diffs)
    if n < 1:
        return "continue", 0.0, 0.0

    mu_0 = 0.0
    mu_1 = delta * baseline_mean

    if n >= 5:
        sigma = max(statistics.stdev(diffs), 0.05 * baseline_mean)
    else:
        sigma = 0.10 * baseline_mean

    if sigma <= 0:
        return "continue", 0.0, sigma

    s_n = sum(diffs)
    lr = ((mu_1 - mu_0) / (sigma**2)) * (s_n - n * (mu_0 + mu_1) / 2.0)

    upper = math.log((1 - beta) / alpha)
    lower = math.log(beta / (1 - alpha))

    if lr >= upper:
        return "accept", lr, sigma
    if lr <= lower:
        return "reject", lr, sigma
    return "continue", lr, sigma


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Paired SPRT runner.")
    parser.add_argument("--baseline", default="HEAD~1", help="baseline git ref")
    parser.add_argument("--patch", default="HEAD", help="patch git ref")
    parser.add_argument("--mode", choices=["cold", "incremental"], default="cold")
    parser.add_argument("--alpha", type=float, default=0.05)
    parser.add_argument("--beta", type=float, default=0.05)
    parser.add_argument(
        "--delta",
        type=float,
        default=0.05,
        help="minimum-meaningful improvement as fraction of baseline mean",
    )
    parser.add_argument("--max-pairs", type=int, default=50)
    parser.add_argument("--seed", type=int, default=None, help="seed for pair ordering")
    parser.add_argument(
        "--warmup-pairs",
        type=int,
        default=2,
        help="discard pairs before SPRT begins (mitigates JIT/cache warmup)",
    )
    args = parser.parse_args(argv)

    rng = random.Random(args.seed)

    base_sha = _resolve(args.baseline)
    patch_sha = _resolve(args.patch)
    if base_sha == patch_sha:
        print(
            f"baseline ({args.baseline}) and patch ({args.patch}) resolve to the "
            f"same SHA {base_sha}; nothing to compare.",
            file=sys.stderr,
        )
        return 3

    print(f"baseline = {args.baseline} ({base_sha[:8]})")
    print(f"patch    = {args.patch} ({patch_sha[:8]})")
    print(f"mode     = {args.mode}")
    print(
        f"alpha={args.alpha} beta={args.beta} delta={args.delta} "
        f"max_pairs={args.max_pairs}"
    )

    with tempfile.TemporaryDirectory(prefix="combfind-bench-") as tmp:
        tmp_root = Path(tmp)
        baseline_dir = _setup_worktree(base_sha, tmp_root, "baseline")
        patch_dir = _setup_worktree(patch_sha, tmp_root, "patch")
        try:
            print("\n--- correctness gate ---")
            t_b0 = _gate_check(baseline_dir, args.mode, "baseline")
            t_p0 = _gate_check(patch_dir, args.mode, "patch")
            print(f"baseline initial: {t_b0:.4f}s")
            print(f"patch    initial: {t_p0:.4f}s")

            print("\n--- paired trials ---")
            diffs: list[float] = []
            baseline_times = [t_b0]
            patch_times = [t_p0]
            trials: list[TrialResult] = []

            for i in range(1, args.max_pairs + 1):
                order = rng.choice(["BP", "PB"])
                if order == "BP":
                    t_b = _timed_run(baseline_dir, args.mode, "baseline")
                    t_p = _timed_run(patch_dir, args.mode, "patch")
                else:
                    t_p = _timed_run(patch_dir, args.mode, "patch")
                    t_b = _timed_run(baseline_dir, args.mode, "baseline")

                tr = TrialResult(i, order, t_b, t_p)
                trials.append(tr)
                baseline_times.append(t_b)
                patch_times.append(t_p)

                # Discard warmup pairs: they tend to be inflated by cold caches.
                if i <= args.warmup_pairs:
                    print(
                        f"pair {i:3d} [{order}] t_b={t_b:.4f} t_p={t_p:.4f} "
                        f"diff={tr.diff:+.4f} (warmup; not counted)"
                    )
                    continue

                diffs.append(tr.diff)
                baseline_mean = statistics.mean(baseline_times[args.warmup_pairs + 1 :])
                verdict, lr, sigma = _sprt(
                    diffs, baseline_mean, args.alpha, args.beta, args.delta
                )
                mean_diff = statistics.mean(diffs)
                print(
                    f"pair {i:3d} [{order}] t_b={t_b:.4f} t_p={t_p:.4f} "
                    f"diff={tr.diff:+.4f} | n={len(diffs)} "
                    f"mean_d={mean_diff:+.4f} sigma={sigma:.4f} lr={lr:+.3f} "
                    f"-> {verdict}"
                )

                if verdict == "accept":
                    return _print_verdict(
                        "ACCEPT", baseline_times, patch_times, diffs, args
                    )
                if verdict == "reject":
                    return _print_verdict(
                        "REJECT", baseline_times, patch_times, diffs, args
                    )

            return _print_verdict(
                "INDETERMINATE", baseline_times, patch_times, diffs, args
            )
        finally:
            _teardown_worktree(baseline_dir)
            _teardown_worktree(patch_dir)


def _print_verdict(
    verdict: str,
    baseline_times: list[float],
    patch_times: list[float],
    diffs: list[float],
    args,
) -> int:
    print()
    print(f"=== VERDICT: {verdict} ===")
    if diffs:
        n = len(diffs)
        mean_b = statistics.mean(baseline_times[args.warmup_pairs + 1 :])
        mean_p = statistics.mean(patch_times[args.warmup_pairs + 1 :])
        mean_d = statistics.mean(diffs)
        pct = 100.0 * mean_d / mean_b if mean_b > 0 else 0.0
        if n >= 2:
            sigma = statistics.stdev(diffs)
            ci_half = 1.96 * sigma / math.sqrt(n)
            ci_str = f"{ci_half:.4f}s"
        else:
            ci_str = "n/a (single pair)"
        print(
            f"pairs={n}  baseline_mean={mean_b:.4f}s  patch_mean={mean_p:.4f}s  "
            f"mean_diff={mean_d:+.4f}s ({pct:+.1f}%)  95% CI half-width={ci_str}"
        )
    else:
        print("(no trials)")

    return {"ACCEPT": 0, "REJECT": 1, "INDETERMINATE": 1}[verdict]


if __name__ == "__main__":
    raise SystemExit(main())
