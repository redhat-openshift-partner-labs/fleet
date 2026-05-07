import subprocess
from unittest import mock

import pytest

from fleet.tasks.scaffold_cluster import main


@mock.patch("fleet.tasks.scaffold_cluster.subprocess.run")
def test_scaffold_writes_and_validates(mock_run, tmp_path):
    mock_run.return_value = subprocess.CompletedProcess(
        [], returncode=0, stdout="", stderr=""
    )
    with mock.patch(
        "sys.argv",
        [
            "prog",
            "--name",
            "test-01",
            "--region",
            "us-east-1",
            "--tier",
            "base",
            "--base-path",
            str(tmp_path),
        ],
    ):
        main()
    assert (tmp_path / "test-01" / "kustomization.yaml").exists()
    assert (tmp_path / "test-01" / "hive" / "kustomization.yaml").exists()
    assert (tmp_path / "test-01" / "crossplane" / "kustomization.yaml").exists()
    assert mock_run.call_count == 2


@mock.patch("fleet.tasks.scaffold_cluster.subprocess.run")
def test_scaffold_fails_on_invalid_kustomize(mock_run, tmp_path):
    mock_run.return_value = subprocess.CompletedProcess(
        [], returncode=1, stdout="", stderr="error"
    )
    with mock.patch(
        "sys.argv",
        [
            "prog",
            "--name",
            "bad-cluster",
            "--region",
            "us-east-1",
            "--tier",
            "base",
            "--base-path",
            str(tmp_path),
        ],
    ):
        with pytest.raises(SystemExit, match="1"):
            main()


@mock.patch("fleet.tasks.scaffold_cluster.subprocess.run")
def test_scaffold_with_custom_zones(mock_run, tmp_path):
    mock_run.return_value = subprocess.CompletedProcess(
        [], returncode=0, stdout="", stderr=""
    )
    with mock.patch(
        "sys.argv",
        [
            "prog",
            "--name",
            "zoned",
            "--region",
            "eu-west-1",
            "--tier",
            "ai",
            "--zones",
            "eu-west-1a,eu-west-1c",
            "--base-path",
            str(tmp_path),
        ],
    ):
        main()
    assert (tmp_path / "zoned" / "kustomization.yaml").exists()
