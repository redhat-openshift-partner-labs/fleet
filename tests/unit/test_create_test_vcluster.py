from unittest import mock

import subprocess

import pytest

from fleet.tasks.create_test_vcluster import main


@mock.patch("builtins.open", mock.mock_open())
@mock.patch("fleet.tasks.create_test_vcluster.subprocess.run")
def test_create_and_connect_success(mock_run):
    mock_run.side_effect = [
        subprocess.CompletedProcess([], returncode=0, stdout="", stderr=""),
        subprocess.CompletedProcess(
            [], returncode=0, stdout="kubeconfig-data", stderr=""
        ),
    ]
    with mock.patch(
        "sys.argv",
        [
            "prog",
            "--cluster-name",
            "test-vc",
            "--namespace",
            "test-ns",
            "--output-dir",
            "/out",
            "--values-file",
            "/vals.yaml",
        ],
    ):
        main()
    assert mock_run.call_count == 2
    create_call = mock_run.call_args_list[0].args[0]
    assert "vcluster" == create_call[0]
    assert "create" == create_call[1]
    assert "-f" in create_call
    assert "/vals.yaml" in create_call


@mock.patch("fleet.tasks.create_test_vcluster.subprocess.run")
def test_create_fails(mock_run):
    mock_run.side_effect = [
        subprocess.CompletedProcess([], returncode=1, stdout="", stderr="error"),
    ]
    with mock.patch(
        "sys.argv",
        [
            "prog",
            "--cluster-name",
            "test-vc",
            "--namespace",
            "test-ns",
            "--output-dir",
            "/out",
        ],
    ):
        with pytest.raises(SystemExit, match="1"):
            main()
    assert mock_run.call_count == 1


@mock.patch("fleet.tasks.create_test_vcluster.subprocess.run")
def test_connect_fails(mock_run):
    mock_run.side_effect = [
        subprocess.CompletedProcess([], returncode=0, stdout="", stderr=""),
        subprocess.CompletedProcess([], returncode=1, stdout="", stderr="error"),
    ]
    with mock.patch(
        "sys.argv",
        [
            "prog",
            "--cluster-name",
            "test-vc",
            "--namespace",
            "test-ns",
            "--output-dir",
            "/out",
        ],
    ):
        with pytest.raises(SystemExit, match="1"):
            main()


@mock.patch("builtins.open", mock.mock_open())
@mock.patch("fleet.tasks.create_test_vcluster.subprocess.run")
def test_no_values_file(mock_run):
    mock_run.side_effect = [
        subprocess.CompletedProcess([], returncode=0, stdout="", stderr=""),
        subprocess.CompletedProcess(
            [], returncode=0, stdout="kubeconfig-data", stderr=""
        ),
    ]
    with mock.patch(
        "sys.argv",
        [
            "prog",
            "--cluster-name",
            "test-vc",
            "--namespace",
            "test-ns",
            "--output-dir",
            "/out",
        ],
    ):
        main()
    create_call = mock_run.call_args_list[0].args[0]
    assert "-f" not in create_call
