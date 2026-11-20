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


BUILD_WORKFLOW = ROOT / ".github" / "workflows" / "build-image.yml"


def build_steps() -> list[dict]:
    workflow = yaml.safe_load(BUILD_WORKFLOW.read_text(encoding="utf-8"))
    return workflow["jobs"]["build-push"]["steps"]


def test_documents_name_the_platforms_of_the_image_build():
    platforms = {
        platform
        for step in build_steps()
        for platform in step.get("with", {}).get("platforms", "").split(",")
        if platform
    }
    assert platforms

    for path in (GUIDE, ROOT / "README.md"):
        named = set(re.findall(r"linux/[a-z0-9]+", path.read_text("utf-8")))
        assert named == platforms, f"{path.name} names {sorted(named)}"
