"""Checks that docs/developer-guide.md matches tox.ini, the CI workflow and the Dockerfile."""

import re

import yaml

from tests.validation._markdown import ROOT, table_rows

GUIDE = ROOT / "docs" / "developer-guide.md"


def test_environment_table_lists_the_environments_of_tox():
    tox_ini = (ROOT / "tox.ini").read_text(encoding="utf-8")
    environments = set(
        re.findall(r"^\[testenv:([\w-]+)\]", tox_ini, flags=re.MULTILINE)
    )

    rows = table_rows(GUIDE, "### Environments")
    assert {key for key in rows if key != "Environment"} == environments


def test_ci_table_lists_the_jobs_and_tox_commands_of_the_workflow():
    path = ROOT / ".github" / "workflows" / "ci.yml"
    workflow = yaml.safe_load(path.read_text(encoding="utf-8"))
    jobs = workflow["jobs"]

    rows = table_rows(GUIDE, "### CI")
    assert {key for key in rows if key != "Job"} == {
        job["name"] for job in jobs.values()
    }

    section = " ".join(" ".join(cells) for cells in rows.values())
    for job in jobs.values():
        for step in job["steps"]:
            command = step.get("run", "").strip()
            if "tox" in command:
                assert f"`{command}`" in section, f"CI command {command}"


def test_image_section_lists_the_packages_of_the_runtime_stage():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    install = re.search(r"microdnf install -y ([\w\s.-]+?) &&", dockerfile)
    packages = install[1].split()
    assert packages

    text = GUIDE.read_text(encoding="utf-8")
    section = text.split("\n## Container Image\n", 1)[1].split("\n## ", 1)[0]
    missing = [package for package in packages if f"`{package}`" not in section]
    assert not missing, f"docs/developer-guide.md does not list {missing}"
