from unittest import mock

import subprocess

import pytest
import yaml

from fleet.tasks.request_ssl_cert import main


@mock.patch("fleet.tasks.request_ssl_cert.subprocess.run")
def test_request_cert_success(mock_run):
    mock_run.return_value = subprocess.CompletedProcess(
        [],
        returncode=0,
        stdout="certificate.cert-manager.io/test-cluster-tls created",
        stderr="",
    )
    with mock.patch(
        "sys.argv",
        [
            "prog",
            "--cluster-name",
            "test-cluster",
            "--dns-zones",
            "apps.test.example.com",
        ],
    ):
        main()
    mock_run.assert_called_once()
    call_args = mock_run.call_args
    cmd = call_args.args[0]
    assert cmd[0] == "oc"
    assert "apply" in cmd
    assert "-f" in cmd


@mock.patch("fleet.tasks.request_ssl_cert.subprocess.run")
def test_request_cert_multiple_dns_zones(mock_run):
    mock_run.return_value = subprocess.CompletedProcess(
        [], returncode=0, stdout="created", stderr=""
    )
    with mock.patch(
        "sys.argv",
        [
            "prog",
            "--cluster-name",
            "test-cluster",
            "--dns-zones",
            "*.apps.test.example.com,api.test.example.com",
        ],
    ):
        main()
    mock_run.assert_called_once()
    call_args = mock_run.call_args
    stdin_yaml = call_args.kwargs.get("input", "")
    assert "*.apps.test.example.com" in stdin_yaml
    assert "api.test.example.com" in stdin_yaml
    parsed = yaml.safe_load(stdin_yaml)
    assert parsed["spec"]["dnsNames"] == [
        "*.apps.test.example.com",
        "api.test.example.com",
    ]


@mock.patch("fleet.tasks.request_ssl_cert.subprocess.run")
def test_request_cert_uses_cluster_name_in_cert(mock_run):
    mock_run.return_value = subprocess.CompletedProcess(
        [], returncode=0, stdout="created", stderr=""
    )
    with mock.patch(
        "sys.argv",
        ["prog", "--cluster-name", "my-cluster", "--dns-zones", "apps.my.example.com"],
    ):
        main()
    call_args = mock_run.call_args
    stdin_yaml = call_args.kwargs.get("input", "")
    assert "my-cluster-wildcard-certificate" in stdin_yaml
    assert "letsencrypt-my-cluster" in stdin_yaml


@mock.patch("fleet.tasks.request_ssl_cert.subprocess.run")
def test_request_cert_fails(mock_run):
    mock_run.return_value = subprocess.CompletedProcess(
        [], returncode=1, stdout="", stderr="forbidden"
    )
    with mock.patch(
        "sys.argv",
        [
            "prog",
            "--cluster-name",
            "test-cluster",
            "--dns-zones",
            "apps.test.example.com",
        ],
    ):
        with pytest.raises(SystemExit, match="1"):
            main()
