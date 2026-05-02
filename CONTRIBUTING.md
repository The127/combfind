# Contributing

## Development setup

```bash
pip install -e ".[dev]" tree-sitter-go
pre-commit install --hook-type commit-msg
```

The second command installs the commit-msg hook that validates your commit messages locally before they push.

## Commit messages

This project uses [Conventional Commits](https://www.conventionalcommits.org/). Every commit on `master` must follow the format:

```
<type>(<optional scope>): <description>
```

Common types:

| Type | Triggers a release? | Version bump |
|------|---------------------|--------------|
| `feat` | yes | minor |
| `fix` | yes | patch |
| `perf` | yes | patch |
| `feat!` / `BREAKING CHANGE` | yes | major |
| `chore`, `docs`, `style`, `ci`, `test`, `refactor` | no | — |

The commit-msg hook enforces this locally. CI enforces it on every push to `master`.

## Release pipeline

Releases are fully automated. On every push to `master`:

1. Commit messages are linted.
2. Tests run.
3. [python-semantic-release](https://python-semantic-release.readthedocs.io/) inspects commits since the last tag. If there are releasable commits it:
   - bumps the version in `pyproject.toml`
   - commits the bump with `[skip ci]`
   - creates a git tag and a GitHub release with a changelog
4. The new version is built and published to PyPI with Sigstore attestations.

Pushes that contain only non-releasable types (`chore`, `docs`, etc.) run tests but do not produce a release.
