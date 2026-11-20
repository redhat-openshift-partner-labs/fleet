"""Checks that the hub setup documents match hub-config/, tekton/ and the Makefile."""

import re

import yaml

from tests.validation._markdown import ROOT, table_rows

HUB = ROOT / "hub-config"
HUB_README = HUB / "README.md"


def test_component_table_lists_every_directory_of_the_kustomization():
    kustomization = yaml.safe_load((HUB / "kustomization.yaml").read_text("utf-8"))
    directories = [r for r in kustomization["resources"] if r.endswith("/")]
    rows = table_rows(HUB_README, "## Components")

    missing = [d for d in directories if d not in rows]
    assert not missing, f"hub-config/README.md has no component row for {missing}"


def test_component_table_holds_the_channel_of_every_subscription():
    rows = table_rows(HUB_README, "## Components")
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


def test_scripts_named_for_the_hub_install_exist():
    sources = [ROOT / "Makefile", HUB_README, *sorted(HUB.glob("*.sh"))]
    for source in sources:
        named = set(re.findall(r"[a-z][a-z-]*\.sh", source.read_text("utf-8")))
        missing = sorted(name for name in named if not (HUB / name).is_file())
        assert not missing, f"{source.name} names {missing}"


def test_install_table_has_a_row_for_every_step_of_the_script():
    script = (HUB / "install-hub-config.sh").read_text(encoding="utf-8")
    steps = re.findall(r"^# Step (\d+):", script, flags=re.MULTILINE)
    assert steps == [str(number) for number in range(1, len(steps) + 1)]

    rows = table_rows(HUB_README, "## Install")
    assert [key for key in rows if key.isdigit()] == steps

    # The messages of the script carry the number of their step.
    echoed = re.findall(r'^echo ".*Step (\d+):', script, flags=re.MULTILINE)
    assert echoed == steps


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
    rows = table_rows(HUB_SETUP, "### 6. Set the pipeline configuration")
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
    rows = table_rows(HUB_SETUP, "## Secrets and accounts")
    missing = [name for name in REQUIRED_SECRETS if name not in rows]
    assert not missing, f"docs/hub-setup.md has no row for {missing}"

    # Each name is a name the repository uses.
    sources = list((ROOT / "tekton").rglob("*.yaml"))
    sources += list((ROOT / "fleet" / "tasks").glob("*.py"))
    sources += list((ROOT / "hub-config").rglob("*.yaml"))
    used = "\n".join(path.read_text(encoding="utf-8") for path in sources)
    unknown = [name for name in REQUIRED_SECRETS if name not in used]
    assert not unknown, unknown


def test_trigger_table_lists_the_triggers_of_the_eventlistener():
    path = ROOT / "tekton" / "triggers" / "eventlistener.yaml"
    listener = yaml.safe_load(path.read_text(encoding="utf-8"))
    triggers = {trigger["name"] for trigger in listener["spec"]["triggers"]}

    setup = ROOT / "docs" / "fleet-clusters-setup.md"
    rows = table_rows(setup, "## Triggers")
    assert {name for name in rows if name != "Trigger"} == triggers
