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
  `vcluster`, `privatebin`, `qemu-img`, `ca-certificates`, and all `fleet-*`
  entry points

All Tekton tasks share this single image, referenced via the `pipeline-image`
param.

To rebuild locally:

```bash
podman build -t fleet-pipeline:dev .
```

### Maintenance: CentOS signing key

The runtime stage installs `qemu-img` from CentOS Stream 9 AppStream with
`gpgcheck=1`. The `Dockerfile` downloads the CentOS Official signing key file from
`CENTOS_KEY_URL`, compares the file's SHA-256 with `CENTOS_KEY_SHA256`, and imports
the key. `CENTOS_KEY_SHA256` pins the bytes of the key file; the fingerprint
identifies the key.

| Item | State on 2026-11-13 |
|------|---------------------|
| Key fingerprint | `99DB 70FA E1D7 CE22 7FB6 4882 05B5 55B3 8483 C65D` |
| Key creation date | 2019-05-03 |
| Key expiry date | none |
| Key file | `https://www.centos.org/keys/RPM-GPG-KEY-CentOS-Official-SHA256` |

The key has no expiry date, so no date announces a rotation. The image is built by
`.github/workflows/build-image.yml` on a `v*` tag push and by a local
`podman build`; `ci.yml` does not build it. A change of the key or of the key file
appears as a failed image build at the next tag push. Published images are
unaffected.

| Build output | Cause |
|--------------|-------|
| `/etc/pki/rpm-gpg/RPM-GPG-KEY-centosofficial: FAILED` and `sha256sum: WARNING: 1 computed checksum did NOT match` | The file at `CENTOS_KEY_URL` changed: a new key, an added key, or the same key in a re-exported file. |
| `curl: (22) The requested URL returned error: 404` | The key file moved. The current URL is listed at <https://www.centos.org/keys/>. |
| `microdnf install -y qemu-img` fails on the package signature | CentOS signs the package with a key that the pinned file does not contain. |

Update the pin:

1. Download the key file. When the file moved, set `CENTOS_KEY_URL` in the
   `Dockerfile` to the new URL first.

   ```bash
   curl -fsSL https://www.centos.org/keys/RPM-GPG-KEY-CentOS-Official-SHA256 -o /tmp/centos-key.asc
   ```

2. List the fingerprints of the keys in the file.

   ```bash
   gpg --show-keys --with-fingerprint /tmp/centos-key.asc
   ```

3. Compare every fingerprint with two sources: the list at
   <https://www.centos.org/keys/> and the file `RPM-GPG-KEY-centosofficial` in
   branch `c9s` of
   <https://gitlab.com/redhat/centos-stream/rpms/centos-stream-release>. The
   GitLab file holds the same key in different bytes, so its SHA-256 differs
   from `CENTOS_KEY_SHA256`; compare fingerprints only. Stop when a fingerprint
   is absent from either source.

4. Compute the SHA-256 of the key file and set `CENTOS_KEY_SHA256` in the
   `Dockerfile` to it. `Containerfile` is a symlink to `Dockerfile`.

   ```bash
   sha256sum /tmp/centos-key.asc
   ```

5. Build the image for both platforms of `build-image.yml` and run `qemu-img`.

   ```bash
   podman build --platform linux/amd64 -t fleet-pipeline:dev-amd64 .
   podman build --platform linux/arm64 -t fleet-pipeline:dev-arm64 .
   podman run --rm fleet-pipeline:dev-amd64 qemu-img --version
   podman run --rm fleet-pipeline:dev-arm64 qemu-img --version
   ```

6. Update the table in this section. `.gitleaks.toml` allowlists the line
   pattern `CENTOS_KEY_SHA256=<64 hex digits>` and needs no change.

7. Commit the change with the type `build(image)` and push a `v*` tag after the
   merge; `build-image.yml` publishes the image.

### Maintenance: CentOS Stream 9 end of life

| Item | State on 2026-11-13 |
|------|---------------------|
| CentOS Stream 9 end of life | 2027-05-31, listed at <https://www.centos.org/download/> |
| Repository in the `Dockerfile` | `https://mirror.stream.centos.org/9-stream/AppStream/$basearch/os/` |
| Precedent | CentOS Stream 8 ended on 2024-05-31. `https://mirror.stream.centos.org/8-stream/` returns 404; the content is at `https://vault.centos.org/8-stream/`. |
| Replacement | `qemu-img` from RHEL 9 AppStream, installed with a Red Hat subscription at build time |

CentOS publishes no `qemu-img` update for Stream 9 after 2027-05-31. When CentOS
removes `9-stream` from the mirror, `microdnf install -y qemu-img` fails at the
next image build. Published images are unaffected. Complete the switch to RHEL
before 2027-05-31.

The image uses CentOS Stream today because the RHEL 9 AppStream repository
requires a subscription during the build, and the GitHub runner of
`build-image.yml` and a local `podman build` have none. The UBI 9 repositories
require no subscription and do not contain `qemu-img`.

Requirements of the switch:

- An activation key and the organization ID of a Red Hat account whose terms
  permit use in GitHub Actions.
- Two GitHub Actions secrets that hold them, for example `RHSM_ORG` and
  `RHSM_ACTIVATION_KEY`.
- A private image repository. The UBI terms cover redistribution of UBI content;
  a RHEL package in the image is outside them. The pull secret of the image is
  described in [image-pull-secret-setup.md](image-pull-secret-setup.md).
- The same two values in local files for every local build.

Switch the image to RHEL:

1. Create the activation key in the Red Hat Hybrid Cloud Console and store the
   organization ID and the key as the two repository secrets.

2. Add a stage to the `Dockerfile` that registers, downloads the package and
   unregisters in one `RUN`. `ubi9` contains `subscription-manager`;
   `ubi9-minimal` does not. A build secret is mounted at `/run/secrets/<id>`
   during the `RUN` and is stored in no image layer.

   ```dockerfile
   FROM registry.access.redhat.com/ubi9:latest AS qemu
   RUN --mount=type=secret,id=rhsm_org --mount=type=secret,id=rhsm_activationkey \
       subscription-manager register \
         --org "$(cat /run/secrets/rhsm_org)" \
         --activationkey "$(cat /run/secrets/rhsm_activationkey)" && \
       { dnf install -y --downloadonly --downloaddir=/rpms qemu-img; rc=$?; \
         subscription-manager unregister; exit "$rc"; }
   ```

3. In the final stage, replace the CentOS block (`CENTOS_KEY_URL`,
   `CENTOS_KEY_SHA256` and the `RUN` that writes
   `centos-stream-appstream.repo`) with a copy of the package and its install.
   `libaio`, `liburing` and `numactl-libs` are the dependencies of the CentOS
   package that UBI provides; `rpm -qpR` on the downloaded file lists the
   dependencies of the RHEL package. `rpm -K` checks the package signature
   against the Red Hat keys in the RPM database of `ubi9-minimal` and exits 1
   for a package signed with another key.

   ```dockerfile
   COPY --from=qemu /rpms/qemu-img-*.rpm /tmp/
   RUN microdnf install -y libaio liburing numactl-libs && \
       rpm -K /tmp/qemu-img-*.rpm && rpm -i /tmp/qemu-img-*.rpm && \
       rm -f /tmp/qemu-img-*.rpm && microdnf clean all
   ```

4. Pass the secrets to the build step of `.github/workflows/build-image.yml`
   (`docker/build-push-action`):

   ```yaml
   secrets: |
     rhsm_org=${{ secrets.RHSM_ORG }}
     rhsm_activationkey=${{ secrets.RHSM_ACTIVATION_KEY }}
   ```

5. Build the image for both platforms and run `qemu-img`. `org.txt` holds the
   organization ID and `key.txt` the activation key; keep both files outside
   the repository checkout or delete them after the build.

   ```bash
   podman build --platform linux/amd64 --secret id=rhsm_org,src=org.txt --secret id=rhsm_activationkey,src=key.txt -t fleet-pipeline:dev-amd64 .
   podman build --platform linux/arm64 --secret id=rhsm_org,src=org.txt --secret id=rhsm_activationkey,src=key.txt -t fleet-pipeline:dev-arm64 .
   podman run --rm fleet-pipeline:dev-amd64 qemu-img --version
   podman run --rm fleet-pipeline:dev-arm64 qemu-img --version
   ```

6. Remove what the CentOS source needed: the section "Maintenance: CentOS
   signing key" and this section, the `CENTOS_KEY_SHA256` pattern in
   `.gitleaks.toml`, and the CentOS statements in `CLAUDE.md` and
   [coco-tier.md](coco-tier.md).

7. Commit the change with the type `build(image)` and push a `v*` tag after the
   merge.

Checked on 2026-11-13 on a host without a subscription:

- The stage of step 2, built with placeholder secrets, mounts both secrets and
  stops at `subscription-manager register` with HTTP 401 for the unknown
  organization ID.
- `ubi9` contains `subscription-manager` 1.29.55 and `dnf install --downloadonly`.
- The UBI repositories contain `libaio`, `liburing` and `numactl-libs` and no
  `qemu-img`.
- In `ubi9-minimal`, `rpm -i` installs the CentOS `qemu-img` package after the
  `microdnf install` of step 3, and `rpm -K` exits 1 for that package.

Not run: a registration with a valid key, the package download from RHEL 9
AppStream, and `rpm -K` and `rpm -i` on the RHEL package.

Each build registers one system in the Red Hat account and unregisters it. A
build that is cancelled between the two commands leaves the system registered.

When the switch is not complete on 2027-05-31, a `baseurl` at
`https://vault.centos.org/9-stream/AppStream/$basearch/os/` is the fallback
that the Stream 8 precedent indicates. That path does not exist on 2026-11-13,
and an archived repository receives no updates.

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
