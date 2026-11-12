from unittest import mock

import subprocess

import pytest

from fleet.tasks.read_cluster_tier import main


@mock.patch("fleet.tasks.read_cluster_tier.subprocess.run")
def test_read_tier_success(mock_run, capsys):
    mock_run.return_value = subprocess.CompletedProcess(
        [], returncode=0, stdout="base", stderr=""
    )
    with mock.patch("sys.argv", ["prog", "--cluster-name", "test-cluster"]):
        main()
    mock_run.assert_called_once_with(
        [
            "oc",
            "get",
            "managedcluster",
            "test-cluster",
            "-o",
            "jsonpath={.metadata.labels.tier}",
        ],
        capture_output=True,
        text=True,
    )
    captured = capsys.readouterr()
    assert captured.out.strip() == "base"
    assert "[info]" in captured.err
    assert "[read-cluster-tier" in captured.err
    assert "tier value:" in captured.err


@mock.patch("fleet.tasks.read_cluster_tier.subprocess.run")
def test_read_virt_tier_success(mock_run, capsys):
    mock_run.return_value = subprocess.CompletedProcess(
        [], returncode=0, stdout="virt", stderr=""
    )
    with mock.patch("sys.argv", ["prog", "--cluster-name", "test-cluster"]):
        main()
    captured = capsys.readouterr()
    assert captured.out.strip() == "virt"


@mock.patch("fleet.tasks.read_cluster_tier.subprocess.run")
def test_read_tier_fails(mock_run):
    mock_run.return_value = subprocess.CompletedProcess(
        [], returncode=1, stdout="", stderr="not found"
    )
    with mock.patch("sys.argv", ["prog", "--cluster-name", "test-cluster"]):
        with pytest.raises(SystemExit, match="1"):
            main()


@mock.patch("fleet.tasks.read_cluster_tier.subprocess.run")
def test_read_tier_empty(mock_run):
    mock_run.return_value = subprocess.CompletedProcess(
        [], returncode=0, stdout="", stderr=""
    )
    with mock.patch("sys.argv", ["prog", "--cluster-name", "test-cluster"]):
        with pytest.raises(SystemExit, match="1"):
            main()


@pytest.mark.parametrize("tier", ["base", "virt", "ai", "coco"])
@mock.patch("fleet.tasks.read_cluster_tier.subprocess.run")
def test_supported_tier_is_printed(mock_run, capsys, tier):
    mock_run.return_value = subprocess.CompletedProcess(
        [], returncode=0, stdout=f"{tier}\n", stderr=""
    )
    with mock.patch("sys.argv", ["prog", "--cluster-name", "test-cluster"]):
        main()
    assert capsys.readouterr().out == f"{tier}\n"


@pytest.mark.parametrize("tier", ["gold", "Coco", "coco-2"])
@mock.patch("fleet.tasks.read_cluster_tier.error")
@mock.patch("fleet.tasks.read_cluster_tier.subprocess.run")
def test_unsupported_tier_exits(mock_run, mock_error, capsys, tier):
    """A tier this image does not list would skip every tier task without an error."""
    mock_run.return_value = subprocess.CompletedProcess(
        [], returncode=0, stdout=tier, stderr=""
    )
    with mock.patch("sys.argv", ["prog", "--cluster-name", "test-cluster"]):
        with pytest.raises(SystemExit, match="1"):
            main()
    assert [str(c.args[0]) for c in mock_error.call_args_list] == [
        f"Tier '{tier}' is not supported by this pipeline image; "
        "supported tiers: base, virt, ai, coco"
    ]
    assert capsys.readouterr().out == ""
