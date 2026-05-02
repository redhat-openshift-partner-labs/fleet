# Developer Guide

## Prerequisites

- Python 3.11+
- [Poetry](https://python-poetry.org/) for dependency management
- [tox](https://tox.wiki/) for running checks
- `oc` / `kubectl` and `kustomize` on `$PATH`
- Node.js (for `npx tekton-lint`)
- [pre-commit](https://pre-commit.com/)

## Setup

```bash
git clone <repo-url> && cd fleet
poetry install
pre-commit install --hook-type pre-push
```

## Development Cycle

Every change follows **Plan -> Test -> Code -> Commit**. See `CLAUDE.md` for
the full policy. In short: write a failing test first, then the implementation,
then commit.

## Running Checks

`tox` is the single entry point — run it before every commit:

```bash
tox          # all environments
tox -e test  # unit tests only (100% coverage enforced)
```

| Environment | What it checks |
|---|---|
| `test` | `pytest` — unit tests with 100% line coverage on `fleet/` |
| `yamllint` | All YAML files (180-char line limit) |
| `tekton-lint` | Tekton Task/Pipeline/Trigger YAML via `npx tekton-lint` |
| `validate-kustomize` | `kustomize build` on all overlay directories |
| `black` | Python formatting |
| `mypy` | Python type checking |
| `pylint` | Python linting (10.00/10 required) |
| `bandit` | Python security scanning |

`tekton-lint` and `validate-kustomize` are not in the default `envlist` — run
them explicitly with `tox -e tekton-lint` or `tox -e validate-kustomize`.

## Adding a New Tekton Task

Every Tekton task is a Python CLI tool with a thin bash wrapper. Follow these
steps:

### 1. Write the test (`tests/unit/test_<name>.py`)

Mock `subprocess.run` to isolate from real binaries. Cover success, failure,
and edge cases:

```python
from unittest import mock
import subprocess
import pytest
from fleet.tasks.<name> import main


def _ok(**kw):
    return subprocess.CompletedProcess([], 0, stdout="", stderr="", **kw)

def _fail(**kw):
    return subprocess.CompletedProcess([], 1, stdout="", stderr="err", **kw)


@mock.patch("fleet.tasks.<name>.subprocess.run")
def test_success(mock_run):
    mock_run.return_value = _ok()
    with mock.patch("sys.argv", ["prog", "--cluster-name", "c1"]):
        main()
    mock_run.assert_called_once()


@mock.patch("fleet.tasks.<name>.subprocess.run")
def test_failure(mock_run):
    mock_run.return_value = _fail()
    with mock.patch("sys.argv", ["prog", "--cluster-name", "c1"]):
        with pytest.raises(SystemExit, match="1"):
            main()
```

### 2. Write the CLI tool (`fleet/tasks/<name>.py`)

Follow the standard pattern — argparse, `_log`, subprocess, `sys.exit(1)` on
failure:

```python
"""One-line description of what this task does."""

import argparse
import subprocess
import sys

from fleet.tasks._log import configure, error, info


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cluster-name", required=True)
    args = parser.parse_args()

    configure("task-name")

    info("=== Task description ===")
    info(f"  cluster-name={args.cluster_name}")

    result = subprocess.run(
        ["oc", "do-something", args.cluster_name],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        error(f"Failed: {result.stderr}")
        sys.exit(1)

    info("Done")
```

Key conventions:

- Module docstring (required by pylint).
- `configure("task-name")` once at the top of `main()`.
- `info()` / `error()` for all output — never bare `print()`.
- `subprocess.run()` with `capture_output=True, text=True`.
- `sys.exit(1)` on fatal errors; `return` (exit 0) on success.
- Use `encoding="utf-8"` when calling `open()`.

### 3. Register the entry point (`pyproject.toml`)

Add a line under `[tool.poetry.scripts]`:

```toml
fleet-<name> = "fleet.tasks.<name>:main"
```

Then reinstall: `poetry install`.

### 4. Create the Tekton task YAML (`tekton/tasks/<name>.yaml`)

Thin bash stub that calls the CLI. The task should only pass params through:

```yaml
apiVersion: tekton.dev/v1
kind: Task
metadata:
  name: <name>
spec:
  params:
    - name: cluster-name
      type: string
    - name: pipeline-image
      type: string
  steps:
    - name: <step>
      image: $(params.pipeline-image)
      imagePullPolicy: Always
      script: |
        #!/usr/bin/env bash
        set -euo pipefail
        fleet-<name> --cluster-name "$(params.cluster-name)"
```

For optional params, use the `EXTRA_ARGS` bash array pattern:

```yaml
script: |
  #!/usr/bin/env bash
  set -euo pipefail
  EXTRA_ARGS=()
  if [[ -n "$(params.optional-thing)" ]]; then
    EXTRA_ARGS+=(--optional-thing "$(params.optional-thing)")
  fi
  fleet-<name> --cluster-name "$(params.cluster-name)" "${EXTRA_ARGS[@]}"
```

### 5. Verify

```bash
tox                    # all checks pass
tox -e tekton-lint     # Tekton YAML valid
```

## vCluster Test Infrastructure

The repo includes tooling for creating ephemeral vCluster instances to test the
post-provision pipeline without real cloud infrastructure. See
[vcluster.md](vcluster.md) for lifecycle diagrams, CLI reference, and how
vCluster integrates with the post-provision pipeline.

## Container Image

The pipeline image is a multi-stage build (`Dockerfile`):

- **Build stage** — UBI9 + Python 3.11, installs `fleet` package via Poetry
- **Runtime stage** — UBI9-minimal with `oc`, `kubectl`, `kustomize`,
  `vcluster`, and all `fleet-*` entry points

All Tekton tasks share this single image, referenced via the `pipeline-image`
param.

To rebuild locally:

```bash
podman build -t fleet-pipeline:dev .
```

## Commit Conventions

- [Conventional Commits](https://www.conventionalcommits.org/): `feat:`,
  `fix:`, `test:`, `refactor:`, `chore:`, `docs:`, `ci:`
- Scope encouraged: `feat(provision): add validate-inputs task`
- All commits signed (`-S`) with a `Signed-off-by` trailer (`-s`)
- No `Co-Authored-By` or AI attribution trailers
- One logical change per commit

## Branch Workflow

- Never commit directly to `main`
- Create feature branches: `feat/provision-pipeline`, `fix/cert-timeout`
- Use git worktrees for parallel work
- Never push to remote — the maintainer pushes when ready
