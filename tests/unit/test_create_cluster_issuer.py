from unittest import mock

import subprocess

import pytest

from fleet.tasks.create_cluster_issuer import main


@mock.patch("fleet.tasks.create_cluster_issuer.subprocess.run")
def test_create_cluster_issuer_success(mock_run):
    mock_run.side_effect = [
        subprocess.CompletedProcess(
            [], returncode=0, stdout="QUFBQUFBQUFBQUFBQUFBQUFBQUE=", stderr=""
        ),
        subprocess.CompletedProcess(
            [], returncode=0, stdout="U1VQRVJzZWNyZXRLRVk=", stderr=""
        ),
        subprocess.CompletedProcess([], returncode=0, stdout="yaml-output", stderr=""),
        subprocess.CompletedProcess([], returncode=0, stdout="", stderr=""),
        subprocess.CompletedProcess([], returncode=0, stdout="", stderr=""),
    ]
    with mock.patch(
        "sys.argv",
        [
            "prog",
            "--cluster-name",
            "test-cluster",
            "--acme-email",
            "admin@example.com",
        ],
    ):
        main()

    calls = mock_run.call_args_list
    assert calls[0] == mock.call(
        [
            "oc",
            "get",
            "secret",
            "aws-credentials",
            "-n",
            "test-cluster",
            "-o",
            "jsonpath={.data.aws_access_key_id}",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert calls[1] == mock.call(
        [
            "oc",
            "get",
            "secret",
            "aws-credentials",
            "-n",
            "test-cluster",
            "-o",
            "jsonpath={.data.aws_secret_access_key}",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert calls[2] == mock.call(
        [
            "oc",
            "create",
            "secret",
            "generic",
            "test-cluster-cert-manager-aws",
            "-n",
            "cert-manager",
            "--from-literal=secret_access_key=SUPERsecretKEY",
            "--dry-run=client",
            "-o",
            "yaml",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert calls[3] == mock.call(
        ["oc", "apply", "-f", "-"],
        input="yaml-output",
        capture_output=True,
        text=True,
        check=True,
    )
    issuer_yaml = calls[4].kwargs["input"]
    assert "name: letsencrypt-test-cluster" in issuer_yaml
    assert "email: admin@example.com" in issuer_yaml
    assert "accessKeyID: AAAAAAAAAAAAAAAAAA" in issuer_yaml
    assert "name: test-cluster-cert-manager-aws" in issuer_yaml
    assert "key: secret_access_key" in issuer_yaml
    assert "region: us-east-1" in issuer_yaml
    assert "letsencrypt.org/directory" in issuer_yaml
    assert calls[4] == mock.call(
        ["oc", "apply", "-f", "-"],
        input=issuer_yaml,
        capture_output=True,
        text=True,
        check=True,
    )


@mock.patch("fleet.tasks.create_cluster_issuer.subprocess.run")
def test_aws_creds_read_failure(mock_run):
    mock_run.side_effect = subprocess.CalledProcessError(1, "oc", stderr="not found")
    with mock.patch(
        "sys.argv",
        [
            "prog",
            "--cluster-name",
            "test-cluster",
            "--acme-email",
            "admin@example.com",
        ],
    ):
        with pytest.raises(SystemExit, match="1"):
            main()


@mock.patch("fleet.tasks.create_cluster_issuer.subprocess.run")
def test_secret_create_failure(mock_run):
    mock_run.side_effect = [
        subprocess.CompletedProcess(
            [], returncode=0, stdout="QUFBQUFBQUFBQUFBQUFBQUFBQUE=", stderr=""
        ),
        subprocess.CompletedProcess(
            [], returncode=0, stdout="U1VQRVJzZWNyZXRLRVk=", stderr=""
        ),
        subprocess.CalledProcessError(1, "oc", stderr="create failed"),
    ]
    with mock.patch(
        "sys.argv",
        [
            "prog",
            "--cluster-name",
            "test-cluster",
            "--acme-email",
            "admin@example.com",
        ],
    ):
        with pytest.raises(SystemExit, match="1"):
            main()


@mock.patch("fleet.tasks.create_cluster_issuer.subprocess.run")
def test_cluster_issuer_create_failure(mock_run):
    mock_run.side_effect = [
        subprocess.CompletedProcess(
            [], returncode=0, stdout="QUFBQUFBQUFBQUFBQUFBQUFBQUE=", stderr=""
        ),
        subprocess.CompletedProcess(
            [], returncode=0, stdout="U1VQRVJzZWNyZXRLRVk=", stderr=""
        ),
        subprocess.CompletedProcess([], returncode=0, stdout="yaml-output", stderr=""),
        subprocess.CompletedProcess([], returncode=0, stdout="", stderr=""),
        subprocess.CalledProcessError(1, "oc", stderr="apply failed"),
    ]
    with mock.patch(
        "sys.argv",
        [
            "prog",
            "--cluster-name",
            "test-cluster",
            "--acme-email",
            "admin@example.com",
        ],
    ):
        with pytest.raises(SystemExit, match="1"):
            main()
