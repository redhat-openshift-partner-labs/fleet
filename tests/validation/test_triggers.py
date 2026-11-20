"""Checks the triggers of the EventListener in tekton/triggers/."""

import yaml

from tests.validation._markdown import ROOT

TRIGGERS = ROOT / "tekton" / "triggers"


def _load(name: str) -> dict:
    return yaml.safe_load((TRIGGERS / name).read_text(encoding="utf-8"))


def _triggers() -> list[dict]:
    return _load("eventlistener.yaml")["spec"]["triggers"]


def test_every_trigger_checks_the_signature_of_the_webhook():
    # A trigger without the github interceptor starts a run for every client
    # that reaches the Route of the EventListener.
    for trigger in _triggers():
        github = [
            interceptor
            for interceptor in trigger.get("interceptors", [])
            if interceptor["ref"]["name"] == "github"
        ]
        assert github, f"trigger {trigger['name']} has no github interceptor"
        params = {param["name"]: param["value"] for param in github[0]["params"]}
        assert params["secretRef"] == {
            "secretName": "fleet-webhook-secret",
            "secretKey": "WebHookSecretKey",
        }, trigger["name"]


def test_kustomization_lists_every_trigger_file():
    listed = set(_load("kustomization.yaml")["resources"])
    files = {path.name for path in TRIGGERS.glob("*.yaml")} - {"kustomization.yaml"}
    assert listed == files


def test_every_binding_and_template_belongs_to_a_trigger():
    bindings = {
        binding["ref"] for trigger in _triggers() for binding in trigger["bindings"]
    }
    templates = {trigger["template"]["ref"] for trigger in _triggers()}

    defined: dict[str, set[str]] = {"TriggerBinding": set(), "TriggerTemplate": set()}
    for path in TRIGGERS.glob("trigger*.yaml"):
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        defined[document["kind"]].add(document["metadata"]["name"])

    assert defined["TriggerBinding"] == bindings
    assert defined["TriggerTemplate"] == templates
