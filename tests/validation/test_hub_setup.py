"""Checks that the hub setup documents match hub-config/, tekton/ and the Makefile."""

import re

import yaml

from tests.validation._markdown import ROOT

HUB = ROOT / "hub-config"
HUB_README = HUB / "README.md"


def rows_by_first_cell(path, heading: str) -> dict[str, list[str]]:
    """Rows of the tables in one section of a document, keyed by their first cell.

    The key is the first cell without backticks. A section runs from its
    heading to the next heading of the same level.
    """
    text = path.read_text(encoding="utf-8")
    level = heading.split(" ", 1)[0]
    section = text.split(f"\n{heading}\n", 1)[1].split(f"\n{level} ", 1)[0]
    rows = {}
    for line in section.splitlines():
        if line.startswith("|") and not line.startswith("|---"):
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            rows[cells[0].strip("`")] = cells
    return rows


def test_component_table_lists_every_directory_of_the_kustomization():
    kustomization = yaml.safe_load((HUB / "kustomization.yaml").read_text("utf-8"))
    directories = [r for r in kustomization["resources"] if r.endswith("/")]
    rows = rows_by_first_cell(HUB_README, "## Components")

    missing = [d for d in directories if d not in rows]
    assert not missing, f"hub-config/README.md has no component row for {missing}"


def test_component_table_holds_the_channel_of_every_subscription():
    rows = rows_by_first_cell(HUB_README, "## Components")
    subscriptions = sorted(HUB.glob("*/subscription.yaml"))
    assert subscriptions

    for path in subscriptions:
        documents = yaml.safe_load_all(path.read_text(encoding="utf-8"))
        channels = [
            document["spec"]["channel"]
            for document in documents
            if document and document.get("kind") == "Subscription"
        ]
        row = " ".join(rows[f"{path.parent.name}/"])
        for channel in channels:
            assert f"`{channel}`" in row, f"{path.parent.name}: channel {channel}"


def test_make_targets_named_in_the_readme_exist():
    named = set(re.findall(r"make (hub-[a-z]+)", HUB_README.read_text("utf-8")))
    assert named
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    targets = set(re.findall(r"^(hub-[a-z]+):", makefile, flags=re.MULTILINE))
    assert named <= targets, f"not in the Makefile: {sorted(named - targets)}"


HUB_SETUP = ROOT / "docs" / "hub-setup.md"

# Secrets the code reads by a fixed name.
REQUIRED_SECRETS = [
    "aws-credentials",
    "fleet-pipeline-pull-secret",
    "fleet-webhook-secret",
    "fleet-github-app-key",
    "keycloak-admin",
    "fleet-iam-read-only",
]


def test_configuration_table_names_only_keys_of_the_configmap():
    rows = rows_by_first_cell(HUB_SETUP, "### 6. Set the pipeline configuration")
    keys = [key for key in rows if key != "Key"]
    assert keys

    path = ROOT / "tekton" / "configmap-defaults.yaml"
    defaults = yaml.safe_load(path.read_text(encoding="utf-8"))["data"]
    unknown = [key for key in keys if key not in defaults]
    assert not unknown, f"not in fleet-pipeline-config: {unknown}"

    # The Default column repeats the value in git.
    for key in keys:
        assert f"`{defaults[key]}`" in rows[key][1] or (
            defaults[key] == "" and rows[key][1] == "Empty"
        ), f"default of {key}"


def test_secrets_table_lists_every_secret_the_code_reads_by_name():
    rows = rows_by_first_cell(HUB_SETUP, "## Secrets and accounts")
    missing = [name for name in REQUIRED_SECRETS if name not in rows]
    assert not missing, f"docs/hub-setup.md has no row for {missing}"

    # Each name is a name the repository uses.
    sources = list((ROOT / "tekton").rglob("*.yaml"))
    sources += list((ROOT / "fleet" / "tasks").glob("*.py"))
    sources += list((ROOT / "hub-config").rglob("*.yaml"))
    used = "\n".join(path.read_text(encoding="utf-8") for path in sources)
    unknown = [name for name in REQUIRED_SECRETS if name not in used]
    assert not unknown, unknown
