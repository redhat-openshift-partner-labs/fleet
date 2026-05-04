from unittest import mock

import subprocess

import pytest

from fleet.tasks.create_test_vcluster import main


@mock.patch("builtins.open", mock.mock_open())
@mock.patch("fleet.tasks.create_test_vcluster.subprocess.run")
@mock.patch("os.makedirs")
@mock.patch("fleet.tasks.create_test_vcluster.time.sleep")
def test_create_and_extract_success(_mock_sleep, _mock_makedirs, mock_run):
    mock_run.side_effect = [
        subprocess.CompletedProcess([], returncode=0, stdout="", stderr=""),
        subprocess.CompletedProcess(
            [], returncode=0, stdout="a3ViZWNvbmZpZy1kYXRh", stderr=""
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
            "/extra.yaml",
        ],
    ):
        main()
    assert mock_run.call_count == 2
    create_call = mock_run.call_args_list[0].args[0]
    assert "vcluster" == create_call[0]
    assert "create" == create_call[1]
    assert create_call.count("-f") == 1
    assert "/extra.yaml" in create_call
    extract_call = mock_run.call_args_list[1].args[0]
    assert "oc" == extract_call[0]
    assert "vc-test-vc" in extract_call


@mock.patch("builtins.open", mock.mock_open())
@mock.patch("fleet.tasks.create_test_vcluster.subprocess.run")
@mock.patch("os.makedirs")
def test_create_fails(_mock_makedirs, mock_run):
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


@mock.patch("builtins.open", mock.mock_open())
@mock.patch("fleet.tasks.create_test_vcluster.subprocess.run")
@mock.patch("os.makedirs")
@mock.patch("fleet.tasks.create_test_vcluster.time.sleep")
def test_extract_kubeconfig_fails(_mock_sleep, _mock_makedirs, mock_run):
    mock_run.side_effect = [
        subprocess.CompletedProcess([], returncode=0, stdout="", stderr=""),
        subprocess.CompletedProcess([], returncode=1, stdout="", stderr="not found"),
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
@mock.patch("os.makedirs")
@mock.patch("fleet.tasks.create_test_vcluster.time.sleep")
def test_no_extra_values_file(_mock_sleep, _mock_makedirs, mock_run):
    mock_run.side_effect = [
        subprocess.CompletedProcess([], returncode=0, stdout="", stderr=""),
        subprocess.CompletedProcess(
            [], returncode=0, stdout="a3ViZWNvbmZpZy1kYXRh", stderr=""
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
    assert create_call.count("-f") == 1


@mock.patch("builtins.open", mock.mock_open())
@mock.patch("fleet.tasks.create_test_vcluster.subprocess.run")
@mock.patch("os.makedirs")
@mock.patch("fleet.tasks.create_test_vcluster.time.sleep")
def test_generated_values_contain_cluster_params(_mock_sleep, _mock_makedirs, mock_run):
    mock_run.side_effect = [
        subprocess.CompletedProcess([], returncode=0, stdout="", stderr=""),
        subprocess.CompletedProcess(
            [], returncode=0, stdout="a3ViZWNvbmZpZy1kYXRh", stderr=""
        ),
    ]
    with mock.patch(
        "sys.argv",
        [
            "prog",
            "--cluster-name",
            "my-vc",
            "--namespace",
            "my-ns",
            "--output-dir",
            "/out",
        ],
    ):
        main()
    handle = open  # noqa: SIM115
    written = handle().write.call_args_list
    values_content = written[0].args[0]
    assert "my-vc.my-ns.svc.cluster.local" in values_content
    assert "vc-my-vc" in values_content
    assert "namespace: my-ns" in values_content


@mock.patch("builtins.open", mock.mock_open())
@mock.patch("fleet.tasks.create_test_vcluster.subprocess.run")
@mock.patch("os.makedirs")
@mock.patch("fleet.tasks.create_test_vcluster.time.sleep")
def test_kubeconfig_is_base64_decoded(_mock_sleep, _mock_makedirs, mock_run):
    mock_run.side_effect = [
        subprocess.CompletedProcess([], returncode=0, stdout="", stderr=""),
        subprocess.CompletedProcess(
            [], returncode=0, stdout="aGVsbG8gd29ybGQ=", stderr=""
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
    handle = open  # noqa: SIM115
    written = handle().write.call_args_list
    kubeconfig_content = written[1].args[0]
    assert kubeconfig_content == "hello world"


@mock.patch("builtins.open", mock.mock_open())
@mock.patch("fleet.tasks.create_test_vcluster.subprocess.run")
@mock.patch("os.makedirs")
@mock.patch("fleet.tasks.create_test_vcluster.time.sleep")
def test_extra_sans_appear_in_generated_values(_mock_sleep, _mock_makedirs, mock_run):
    mock_run.side_effect = [
        subprocess.CompletedProcess([], returncode=0, stdout="", stderr=""),
        subprocess.CompletedProcess(
            [], returncode=0, stdout="a3ViZWNvbmZpZy1kYXRh", stderr=""
        ),
    ]
    with mock.patch(
        "sys.argv",
        [
            "prog",
            "--cluster-name",
            "my-vc",
            "--namespace",
            "my-ns",
            "--output-dir",
            "/out",
            "--extra-sans",
            "foo.example.com",
            "bar.example.com",
        ],
    ):
        main()
    handle = open  # noqa: SIM115
    written = handle().write.call_args_list
    values_content = written[0].args[0]
    assert "my-vc.my-ns.svc.cluster.local" in values_content
    assert "foo.example.com" in values_content
    assert "bar.example.com" in values_content


def test_generate_values_default_san_always_present():
    from fleet.tasks.create_test_vcluster import _generate_values

    result = _generate_values("vc1", "ns1", extra_sans=["custom.san.io"])
    assert "vc1.ns1.svc.cluster.local" in result
    assert "custom.san.io" in result


def test_generate_values_export_kubeconfig_with_route_san():
    from fleet.tasks.create_test_vcluster import _generate_values

    result = _generate_values("vc1", "ns1", route_san="vc.apps.example.com")
    assert "server: https://vc.apps.example.com:443" in result
    assert "vc1.ns1.svc.cluster.local" in result


def test_generate_values_no_export_kubeconfig_without_route_san():
    from fleet.tasks.create_test_vcluster import _generate_values

    result = _generate_values("vc1", "ns1")
    assert "exportKubeConfig" not in result


@mock.patch("builtins.open", mock.mock_open())
@mock.patch("fleet.tasks.create_test_vcluster.subprocess.run")
@mock.patch("os.makedirs")
@mock.patch("fleet.tasks.create_test_vcluster.time.sleep")
def test_passthrough_route_created_with_route_san(
    _mock_sleep, _mock_makedirs, mock_run
):
    mock_run.side_effect = [
        subprocess.CompletedProcess([], returncode=0, stdout="", stderr=""),
        subprocess.CompletedProcess(
            [], returncode=0, stdout="a3ViZWNvbmZpZy1kYXRh", stderr=""
        ),
        subprocess.CompletedProcess([], returncode=0, stdout="", stderr=""),
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
            "--route-san",
            "vc.apps.example.com",
        ],
    ):
        main()
    assert mock_run.call_count == 3
    route_call = mock_run.call_args_list[2].args[0]
    assert route_call == [
        "oc",
        "create",
        "route",
        "passthrough",
        "test-vc",
        "--service=test-vc",
        "--hostname=vc.apps.example.com",
        "-n",
        "test-ns",
    ]
    handle = open  # noqa: SIM115
    written = handle().write.call_args_list
    values_content = written[0].args[0]
    assert "server: https://vc.apps.example.com:443" in values_content


@mock.patch("builtins.open", mock.mock_open())
@mock.patch("fleet.tasks.create_test_vcluster.subprocess.run")
@mock.patch("os.makedirs")
@mock.patch("fleet.tasks.create_test_vcluster.time.sleep")
def test_route_san_added_to_extra_sans_in_values(_mock_sleep, _mock_makedirs, mock_run):
    mock_run.side_effect = [
        subprocess.CompletedProcess([], returncode=0, stdout="", stderr=""),
        subprocess.CompletedProcess(
            [], returncode=0, stdout="a3ViZWNvbmZpZy1kYXRh", stderr=""
        ),
        subprocess.CompletedProcess([], returncode=0, stdout="", stderr=""),
    ]
    with mock.patch(
        "sys.argv",
        [
            "prog",
            "--cluster-name",
            "my-vc",
            "--namespace",
            "my-ns",
            "--output-dir",
            "/out",
            "--route-san",
            "vc.apps.example.com",
        ],
    ):
        main()
    handle = open  # noqa: SIM115
    written = handle().write.call_args_list
    values_content = written[0].args[0]
    assert "vc.apps.example.com" in values_content
    assert "my-vc.my-ns.svc.cluster.local" in values_content
    assert "server: https://vc.apps.example.com:443" in values_content


@mock.patch("builtins.open", mock.mock_open())
@mock.patch("fleet.tasks.create_test_vcluster.subprocess.run")
@mock.patch("os.makedirs")
@mock.patch("fleet.tasks.create_test_vcluster.time.sleep")
def test_no_route_without_route_san(_mock_sleep, _mock_makedirs, mock_run):
    mock_run.side_effect = [
        subprocess.CompletedProcess([], returncode=0, stdout="", stderr=""),
        subprocess.CompletedProcess(
            [], returncode=0, stdout="a3ViZWNvbmZpZy1kYXRh", stderr=""
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
    assert mock_run.call_count == 2


@mock.patch("builtins.open", mock.mock_open())
@mock.patch("fleet.tasks.create_test_vcluster.subprocess.run")
@mock.patch("os.makedirs")
@mock.patch("fleet.tasks.create_test_vcluster.time.sleep")
def test_route_creation_fails(_mock_sleep, _mock_makedirs, mock_run):
    mock_run.side_effect = [
        subprocess.CompletedProcess([], returncode=0, stdout="", stderr=""),
        subprocess.CompletedProcess(
            [], returncode=0, stdout="a3ViZWNvbmZpZy1kYXRh", stderr=""
        ),
        subprocess.CompletedProcess(
            [], returncode=1, stdout="", stderr="already exists"
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
            "--route-san",
            "vc.apps.example.com",
        ],
    ):
        with pytest.raises(SystemExit, match="1"):
            main()
