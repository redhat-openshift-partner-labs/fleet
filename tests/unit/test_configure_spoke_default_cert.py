from unittest import mock

import subprocess

import pytest

from fleet.tasks.configure_spoke_default_cert import main


@mock.patch("fleet.tasks.configure_spoke_default_cert.subprocess.run")
def test_success(mock_run):
    mock_run.side_effect = [
        subprocess.CompletedProcess(
            [],
            returncode=0,
            stdout='{"tls.crt":"Y2VydA==","tls.key":"a2V5"}',
            stderr="",
        ),
        subprocess.CompletedProcess(
            [],
            returncode=0,
            stdout="secret/test-cluster-leaf-cert configured",
            stderr="",
        ),
        subprocess.CompletedProcess(
            [],
            returncode=0,
            stdout="ingresscontroller.operator.openshift.io/default patched",
            stderr="",
        ),
    ]
    with mock.patch(
        "sys.argv",
        ["prog", "--cluster-name", "test-cluster", "--spoke-kubeconfig", "/tmp/kc"],
    ):
        main()
    assert mock_run.call_count == 3


@mock.patch("fleet.tasks.configure_spoke_default_cert.subprocess.run")
def test_hub_read_has_no_kubeconfig(mock_run):
    mock_run.side_effect = [
        subprocess.CompletedProcess(
            [],
            returncode=0,
            stdout='{"tls.crt":"Y2VydA==","tls.key":"a2V5"}',
            stderr="",
        ),
        subprocess.CompletedProcess([], returncode=0, stdout="ok", stderr=""),
        subprocess.CompletedProcess([], returncode=0, stdout="ok", stderr=""),
    ]
    with mock.patch(
        "sys.argv",
        ["prog", "--cluster-name", "test-cluster", "--spoke-kubeconfig", "/tmp/kc"],
    ):
        main()
    hub_cmd = " ".join(mock_run.call_args_list[0].args[0])
    assert "--kubeconfig" not in hub_cmd


@mock.patch("fleet.tasks.configure_spoke_default_cert.subprocess.run")
def test_spoke_operations_use_kubeconfig(mock_run):
    mock_run.side_effect = [
        subprocess.CompletedProcess(
            [],
            returncode=0,
            stdout='{"tls.crt":"Y2VydA==","tls.key":"a2V5"}',
            stderr="",
        ),
        subprocess.CompletedProcess([], returncode=0, stdout="ok", stderr=""),
        subprocess.CompletedProcess([], returncode=0, stdout="ok", stderr=""),
    ]
    with mock.patch(
        "sys.argv",
        ["prog", "--cluster-name", "test-cluster", "--spoke-kubeconfig", "/tmp/kc"],
    ):
        main()
    apply_cmd = " ".join(mock_run.call_args_list[1].args[0])
    assert "--kubeconfig=/tmp/kc" in apply_cmd
    patch_cmd = " ".join(mock_run.call_args_list[2].args[0])
    assert "--kubeconfig=/tmp/kc" in patch_cmd


@mock.patch("fleet.tasks.configure_spoke_default_cert.subprocess.run")
def test_hub_secret_read_fails(mock_run):
    mock_run.return_value = subprocess.CompletedProcess(
        [], returncode=1, stdout="", stderr="not found"
    )
    with mock.patch(
        "sys.argv",
        ["prog", "--cluster-name", "test-cluster", "--spoke-kubeconfig", "/tmp/kc"],
    ):
        with pytest.raises(SystemExit, match="1"):
            main()


@mock.patch("fleet.tasks.configure_spoke_default_cert.subprocess.run")
def test_spoke_secret_apply_fails(mock_run):
    mock_run.side_effect = [
        subprocess.CompletedProcess(
            [],
            returncode=0,
            stdout='{"tls.crt":"Y2VydA==","tls.key":"a2V5"}',
            stderr="",
        ),
        subprocess.CompletedProcess([], returncode=1, stdout="", stderr="forbidden"),
    ]
    with mock.patch(
        "sys.argv",
        ["prog", "--cluster-name", "test-cluster", "--spoke-kubeconfig", "/tmp/kc"],
    ):
        with pytest.raises(SystemExit, match="1"):
            main()


@mock.patch("fleet.tasks.configure_spoke_default_cert.subprocess.run")
def test_spoke_ingresscontroller_patch_fails(mock_run):
    mock_run.side_effect = [
        subprocess.CompletedProcess(
            [],
            returncode=0,
            stdout='{"tls.crt":"Y2VydA==","tls.key":"a2V5"}',
            stderr="",
        ),
        subprocess.CompletedProcess([], returncode=0, stdout="ok", stderr=""),
        subprocess.CompletedProcess([], returncode=1, stdout="", stderr="error"),
    ]
    with mock.patch(
        "sys.argv",
        ["prog", "--cluster-name", "test-cluster", "--spoke-kubeconfig", "/tmp/kc"],
    ):
        with pytest.raises(SystemExit, match="1"):
            main()


@mock.patch("fleet.tasks.configure_spoke_default_cert.subprocess.run")
def test_secret_yaml_content(mock_run):
    mock_run.side_effect = [
        subprocess.CompletedProcess(
            [],
            returncode=0,
            stdout='{"tls.crt":"Y2VydA==","tls.key":"a2V5"}',
            stderr="",
        ),
        subprocess.CompletedProcess([], returncode=0, stdout="ok", stderr=""),
        subprocess.CompletedProcess([], returncode=0, stdout="ok", stderr=""),
    ]
    with mock.patch(
        "sys.argv",
        ["prog", "--cluster-name", "test-cluster", "--spoke-kubeconfig", "/tmp/kc"],
    ):
        main()
    apply_call = mock_run.call_args_list[1]
    stdin_yaml = apply_call.kwargs.get("input", "")
    assert "test-cluster-leaf-cert" in stdin_yaml
    assert "namespace: openshift-ingress" in stdin_yaml
    assert "kubernetes.io/tls" in stdin_yaml
    assert "tls.crt: Y2VydA==" in stdin_yaml
    assert "tls.key: a2V5" in stdin_yaml


@mock.patch("fleet.tasks.configure_spoke_default_cert.subprocess.run")
def test_patch_uses_merge_type(mock_run):
    mock_run.side_effect = [
        subprocess.CompletedProcess(
            [],
            returncode=0,
            stdout='{"tls.crt":"Y2VydA==","tls.key":"a2V5"}',
            stderr="",
        ),
        subprocess.CompletedProcess([], returncode=0, stdout="ok", stderr=""),
        subprocess.CompletedProcess([], returncode=0, stdout="ok", stderr=""),
    ]
    with mock.patch(
        "sys.argv",
        ["prog", "--cluster-name", "test-cluster", "--spoke-kubeconfig", "/tmp/kc"],
    ):
        main()
    patch_cmd = mock_run.call_args_list[2].args[0]
    assert "patch" in patch_cmd
    assert "--type=merge" in patch_cmd
    assert "openshift-ingress-operator" in " ".join(patch_cmd)


@mock.patch("fleet.tasks.configure_spoke_default_cert.subprocess.run")
def test_patch_json_contains_default_cert(mock_run):
    mock_run.side_effect = [
        subprocess.CompletedProcess(
            [],
            returncode=0,
            stdout='{"tls.crt":"Y2VydA==","tls.key":"a2V5"}',
            stderr="",
        ),
        subprocess.CompletedProcess([], returncode=0, stdout="ok", stderr=""),
        subprocess.CompletedProcess([], returncode=0, stdout="ok", stderr=""),
    ]
    with mock.patch(
        "sys.argv",
        ["prog", "--cluster-name", "my-cluster", "--spoke-kubeconfig", "/tmp/kc"],
    ):
        main()
    patch_cmd = mock_run.call_args_list[2].args[0]
    patch_str = " ".join(patch_cmd)
    assert "my-cluster-leaf-cert" in patch_str
    assert "defaultCertificate" in patch_str


@mock.patch("fleet.tasks.configure_spoke_default_cert.subprocess.run")
def test_cluster_name_parameterized(mock_run):
    mock_run.side_effect = [
        subprocess.CompletedProcess(
            [],
            returncode=0,
            stdout='{"tls.crt":"Y2VydA==","tls.key":"a2V5"}',
            stderr="",
        ),
        subprocess.CompletedProcess([], returncode=0, stdout="ok", stderr=""),
        subprocess.CompletedProcess([], returncode=0, stdout="ok", stderr=""),
    ]
    with mock.patch(
        "sys.argv",
        ["prog", "--cluster-name", "abc-123", "--spoke-kubeconfig", "/tmp/kc"],
    ):
        main()
    hub_cmd = " ".join(mock_run.call_args_list[0].args[0])
    assert "abc-123-leaf-cert" in hub_cmd
    apply_yaml = mock_run.call_args_list[1].kwargs.get("input", "")
    assert "abc-123-leaf-cert" in apply_yaml
    patch_str = " ".join(mock_run.call_args_list[2].args[0])
    assert "abc-123-leaf-cert" in patch_str
