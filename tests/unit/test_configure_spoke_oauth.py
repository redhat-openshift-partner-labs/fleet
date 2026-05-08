from unittest import mock

import subprocess

import pytest

from fleet.tasks.configure_spoke_oauth import main

BASE_ARGV = [
    "prog",
    "--cluster-name",
    "test-cluster",
    "--spoke-kubeconfig",
    "/workspace/kubeconfig",
    "--keycloak-issuer-url",
    "https://idp.example.com/realms/openshift",
    "--provider-name",
    "RedHat",
]


def _ok(stdout="done", stderr=""):
    return subprocess.CompletedProcess([], returncode=0, stdout=stdout, stderr=stderr)


def _fail(stderr="error"):
    return subprocess.CompletedProcess([], returncode=1, stdout="", stderr=stderr)


def _hub_reads_ok():
    """Two successful hub secret reads (base64 of 'my-client-id' and 'my-secret')."""
    return [
        _ok(stdout="bXktY2xpZW50LWlk"),  # base64("my-client-id")
        _ok(stdout="bXktc2VjcmV0"),  # base64("my-secret")
    ]


def _all_ok():
    """All 5 calls succeed: 2 hub reads + htpasswd + keycloak secret + OAuth CR."""
    return _hub_reads_ok() + [_ok(), _ok(), _ok()]


@mock.patch("fleet.tasks.configure_spoke_oauth.subprocess.run")
def test_configure_oauth_success(mock_run):
    mock_run.side_effect = _all_ok()
    with mock.patch("sys.argv", BASE_ARGV):
        main()
    assert mock_run.call_count == 5


@mock.patch("fleet.tasks.configure_spoke_oauth.subprocess.run")
def test_hub_reads_have_no_kubeconfig(mock_run):
    mock_run.side_effect = _all_ok()
    with mock.patch("sys.argv", BASE_ARGV):
        main()
    for call in mock_run.call_args_list[:2]:
        cmd = call.args[0]
        assert not any("--kubeconfig" in arg for arg in cmd)


@mock.patch("fleet.tasks.configure_spoke_oauth.subprocess.run")
def test_spoke_applies_use_kubeconfig(mock_run):
    mock_run.side_effect = _all_ok()
    with mock.patch("sys.argv", BASE_ARGV):
        main()
    for call in mock_run.call_args_list[2:]:
        cmd = call.args[0]
        assert "--kubeconfig=/workspace/kubeconfig" in cmd


@mock.patch("fleet.tasks.configure_spoke_oauth.subprocess.run")
def test_hub_secret_read_client_id_fails(mock_run):
    mock_run.side_effect = [_fail(stderr="not found")]
    with mock.patch("sys.argv", BASE_ARGV):
        with pytest.raises(SystemExit, match="1"):
            main()


@mock.patch("fleet.tasks.configure_spoke_oauth.subprocess.run")
def test_hub_secret_read_client_secret_fails(mock_run):
    mock_run.side_effect = [_ok(stdout="bXktY2xpZW50LWlk"), _fail(stderr="not found")]
    with mock.patch("sys.argv", BASE_ARGV):
        with pytest.raises(SystemExit, match="1"):
            main()


@mock.patch("fleet.tasks.configure_spoke_oauth.subprocess.run")
def test_keycloak_secret_pushed_to_spoke(mock_run):
    mock_run.side_effect = _all_ok()
    with mock.patch("sys.argv", BASE_ARGV):
        main()
    keycloak_apply = mock_run.call_args_list[3]
    secret_yaml = keycloak_apply.kwargs["input"]
    assert "namespace: openshift-config" in secret_yaml
    assert "name: test-cluster-keycloak-client" in secret_yaml
    assert "clientSecret: my-secret" in secret_yaml


@mock.patch("fleet.tasks.configure_spoke_oauth.subprocess.run")
def test_keycloak_secret_apply_to_spoke_fails(mock_run):
    mock_run.side_effect = _hub_reads_ok() + [_ok(), _fail(stderr="forbidden")]
    with mock.patch("sys.argv", BASE_ARGV):
        with pytest.raises(SystemExit, match="1"):
            main()


@mock.patch("fleet.tasks.configure_spoke_oauth.subprocess.run")
def test_configure_oauth_applies_htpasswd_secret(mock_run):
    mock_run.side_effect = _all_ok()
    with mock.patch("sys.argv", BASE_ARGV):
        main()
    htpasswd_apply = mock_run.call_args_list[2]
    htpasswd_yaml = htpasswd_apply.kwargs["input"]
    assert "name: htpasswd-secret" in htpasswd_yaml
    assert "namespace: openshift-config" in htpasswd_yaml


@mock.patch("fleet.tasks.configure_spoke_oauth.subprocess.run")
def test_configure_oauth_htpasswd_apply_fails(mock_run):
    mock_run.side_effect = _hub_reads_ok() + [_fail(stderr="forbidden")]
    with mock.patch("sys.argv", BASE_ARGV):
        with pytest.raises(SystemExit, match="1"):
            main()


@mock.patch("fleet.tasks.configure_spoke_oauth.subprocess.run")
def test_configure_oauth_uses_cluster_name_in_resources(mock_run):
    mock_run.side_effect = _all_ok()
    argv = [*BASE_ARGV]
    argv[2] = "my-cluster"
    with mock.patch("sys.argv", argv):
        main()
    all_stdin = [
        c.kwargs.get("input", "")
        for c in mock_run.call_args_list
        if c.kwargs.get("input")
    ]
    combined = "\n".join(all_stdin)
    assert "openshift-config" in combined


@mock.patch("fleet.tasks.configure_spoke_oauth.subprocess.run")
def test_configure_oauth_cr_apply_fails(mock_run):
    mock_run.side_effect = _hub_reads_ok() + [_ok(), _ok(), _fail(stderr="forbidden")]
    with mock.patch("sys.argv", BASE_ARGV):
        with pytest.raises(SystemExit, match="1"):
            main()


@mock.patch("fleet.tasks.configure_spoke_oauth.subprocess.run")
def test_issuer_url_parameterized(mock_run):
    mock_run.side_effect = _all_ok()
    argv = [
        "prog",
        "--cluster-name",
        "c1",
        "--spoke-kubeconfig",
        "/kc",
        "--keycloak-issuer-url",
        "https://sso.prod.com/realms/prod",
        "--provider-name",
        "RedHat",
    ]
    with mock.patch("sys.argv", argv):
        main()
    oauth_yaml = mock_run.call_args_list[4].kwargs["input"]
    assert "issuer: https://sso.prod.com/realms/prod" in oauth_yaml


@mock.patch("fleet.tasks.configure_spoke_oauth.subprocess.run")
def test_provider_name_in_oauth_yaml(mock_run):
    mock_run.side_effect = _all_ok()
    argv = [
        "prog",
        "--cluster-name",
        "c1",
        "--spoke-kubeconfig",
        "/kc",
        "--keycloak-issuer-url",
        "https://sso.example.com/realms/r",
        "--provider-name",
        "MyIDP",
    ]
    with mock.patch("sys.argv", argv):
        main()
    oauth_yaml = mock_run.call_args_list[4].kwargs["input"]
    assert "name: MyIDP" in oauth_yaml


@mock.patch("fleet.tasks.configure_spoke_oauth.subprocess.run")
def test_client_secret_name_matches_register_task(mock_run):
    mock_run.side_effect = _all_ok()
    with mock.patch("sys.argv", BASE_ARGV):
        main()
    oauth_yaml = mock_run.call_args_list[4].kwargs["input"]
    assert "name: test-cluster-keycloak-client" in oauth_yaml
