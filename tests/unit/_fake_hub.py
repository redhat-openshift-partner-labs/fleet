"""Fake of subprocess.run for the tests of the test-vcluster tools."""

import json
import subprocess


class FakeHub:
    """Answers a command with the first rule that matches it.

    A rule is (command, returncode, stdout, stderr). A list matches every
    command that starts with it, a tuple only the same command. A command that
    matches no rule exits 0 with no output. Every command is recorded in `calls`.
    """

    def __init__(self, *rules):
        self.rules = list(rules)
        self.calls = []

    def __call__(self, cmd, **_kwargs):
        self.calls.append(list(cmd))
        for rule, code, stdout, stderr in self.rules:
            compared = cmd if isinstance(rule, tuple) else cmd[: len(rule)]
            if list(compared) == list(rule):
                return subprocess.CompletedProcess(cmd, code, stdout, stderr)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    def changes(self):
        """The commands that change the hub: every command that is not an oc get."""
        return [call for call in self.calls if call[:2] != ["oc", "get"]]


def found(kind, name, namespace=None, labels=None):
    """Rule: `oc get KIND NAME -o json` of the guard finds the object."""
    document = json.dumps({"metadata": {"name": name, "labels": labels or {}}})
    return (_read(kind, name, namespace), 0, document, "")


def unreadable(kind, name, namespace=None):
    """Rule: `oc get KIND NAME` of the guard fails."""
    return (_read(kind, name, namespace), 1, "", "forbidden")


def _read(kind, name, namespace):
    prefix = ["oc", "get", kind, name, "--ignore-not-found=true"]
    return prefix + (["-n", namespace] if namespace else [])
