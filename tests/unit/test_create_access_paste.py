from unittest import mock

import pytest

from fleet.tasks.create_access_paste import generate_password, main, render_markdown


def test_generate_password_matches_pwgen_constraints():
    password = generate_password()
    assert len(password) == 32
    assert any(char.isupper() for char in password)
    assert any(char.isdigit() for char in password)
    assert not any(char in "0OIl1" for char in password)


def test_render_markdown_contains_access_details():
    markdown = render_markdown(
        cluster_name="example",
        base_domain="example.com",
        kubeadmin_password="cluster-password",
        kubeconfig="apiVersion: v1\n",
    )
    assert "https://console-openshift-console.apps.example.example.com" in markdown
    assert "USERNAME: kubeadmin" in markdown
    assert "PASSWORD: cluster-password" in markdown
    assert "```yaml" in markdown
    assert "apiVersion: v1" in markdown


@mock.patch("fleet.tasks.create_access_paste.subprocess.run")
def test_main_creates_paste_and_hub_secret(mock_run, tmp_path):
    kubeconfig = tmp_path / "kubeconfig"
    kubeconfig.write_text("apiVersion: v1\n")

    mock_run.side_effect = [
        mock.Mock(returncode=0, stdout="admin-password-secret"),
        mock.Mock(returncode=0, stdout="Y2x1c3Rlci1wYXNzd29yZA=="),
        mock.Mock(
            returncode=0,
            stdout='{"paste_url":"https://paste.example/abc#key","delete_token":"delete-token"}\n',
        ),
        mock.Mock(returncode=0, stdout="", stderr=""),
    ]

    with mock.patch(
        "sys.argv",
        [
            "prog",
            "--cluster-name",
            "example",
            "--base-domain",
            "example.com",
            "--kubeconfig-file",
            str(kubeconfig),
            "--privatebin-url",
            "https://pastes.example.com",
        ],
    ):
        main()

    assert mock_run.call_count == 4
    privatebin_call = mock_run.call_args_list[2]
    assert privatebin_call.args[0][0] == "privatebin"
    assert "--expire" in privatebin_call.args[0]
    assert "1week" in privatebin_call.args[0]

    secret_call = mock_run.call_args_list[3]
    secret_yaml = secret_call.kwargs["input"]
    assert "example-access-paste" in secret_yaml
    assert "https://paste.example/abc#key" in secret_yaml


@mock.patch("fleet.tasks.create_access_paste.subprocess.run")
def test_main_fails_when_admin_password_secret_ref_is_missing(mock_run, tmp_path):
    kubeconfig = tmp_path / "kubeconfig"
    kubeconfig.write_text("apiVersion: v1\n")

    mock_run.side_effect = [
        mock.Mock(returncode=1, stdout="", stderr="not found"),
    ]

    with mock.patch(
        "sys.argv",
        [
            "prog",
            "--cluster-name",
            "example",
            "--base-domain",
            "example.com",
            "--kubeconfig-file",
            str(kubeconfig),
            "--privatebin-url",
            "https://pastes.example.com",
        ],
    ):
        with pytest.raises(SystemExit, match="1"):
            main()


@mock.patch("fleet.tasks.create_access_paste.subprocess.run")
def test_main_fails_when_privatebin_create_fails(mock_run, tmp_path):
    kubeconfig = tmp_path / "kubeconfig"
    kubeconfig.write_text("apiVersion: v1\n")

    mock_run.side_effect = [
        mock.Mock(returncode=0, stdout="admin-password-secret"),
        mock.Mock(returncode=0, stdout="Y2x1c3Rlci1wYXNzd29yZA=="),
        mock.Mock(returncode=1, stdout="", stderr="create failed"),
    ]

    with mock.patch(
        "sys.argv",
        [
            "prog",
            "--cluster-name",
            "example",
            "--base-domain",
            "example.com",
            "--kubeconfig-file",
            str(kubeconfig),
            "--privatebin-url",
            "https://pastes.example.com",
        ],
    ):
        with pytest.raises(SystemExit, match="1"):
            main()


@mock.patch("fleet.tasks.create_access_paste.subprocess.run")
def test_main_fails_when_kubeadmin_password_secret_is_unreadable(mock_run, tmp_path):
    kubeconfig = tmp_path / "kubeconfig"
    kubeconfig.write_text("apiVersion: v1\n")
    mock_run.side_effect = [
        mock.Mock(returncode=0, stdout="admin-password-secret"),
        mock.Mock(returncode=1, stdout="", stderr="forbidden"),
    ]

    with mock.patch(
        "sys.argv",
        [
            "prog",
            "--cluster-name",
            "example",
            "--base-domain",
            "example.com",
            "--kubeconfig-file",
            str(kubeconfig),
            "--privatebin-url",
            "https://pastes.example.com",
        ],
    ):
        with pytest.raises(SystemExit, match="1"):
            main()


@mock.patch("fleet.tasks.create_access_paste.subprocess.run")
def test_main_fails_when_kubeadmin_password_is_invalid_base64(mock_run, tmp_path):
    kubeconfig = tmp_path / "kubeconfig"
    kubeconfig.write_text("apiVersion: v1\n")
    mock_run.side_effect = [
        mock.Mock(returncode=0, stdout="admin-password-secret"),
        mock.Mock(returncode=0, stdout="not-base64", stderr=""),
    ]

    with mock.patch(
        "sys.argv",
        [
            "prog",
            "--cluster-name",
            "example",
            "--base-domain",
            "example.com",
            "--kubeconfig-file",
            str(kubeconfig),
            "--privatebin-url",
            "https://pastes.example.com",
        ],
    ):
        with pytest.raises(SystemExit, match="1"):
            main()


@mock.patch("fleet.tasks.create_access_paste.subprocess.run")
def test_main_fails_when_privatebin_returns_invalid_json(mock_run, tmp_path):
    kubeconfig = tmp_path / "kubeconfig"
    kubeconfig.write_text("apiVersion: v1\n")
    mock_run.side_effect = [
        mock.Mock(returncode=0, stdout="admin-password-secret"),
        mock.Mock(returncode=0, stdout="Y2x1c3Rlci1wYXNzd29yZA==", stderr=""),
        mock.Mock(returncode=0, stdout="not-json\n", stderr=""),
    ]

    with mock.patch(
        "sys.argv",
        [
            "prog",
            "--cluster-name",
            "example",
            "--base-domain",
            "example.com",
            "--kubeconfig-file",
            str(kubeconfig),
            "--privatebin-url",
            "https://pastes.example.com",
        ],
    ):
        with pytest.raises(SystemExit, match="1"):
            main()


@mock.patch("fleet.tasks.create_access_paste.subprocess.run")
def test_main_fails_when_privatebin_response_omits_paste_url(mock_run, tmp_path):
    kubeconfig = tmp_path / "kubeconfig"
    kubeconfig.write_text("apiVersion: v1\n")
    mock_run.side_effect = [
        mock.Mock(returncode=0, stdout="admin-password-secret"),
        mock.Mock(returncode=0, stdout="Y2x1c3Rlci1wYXNzd29yZA==", stderr=""),
        mock.Mock(returncode=0, stdout="{}\n", stderr=""),
    ]

    with mock.patch(
        "sys.argv",
        [
            "prog",
            "--cluster-name",
            "example",
            "--base-domain",
            "example.com",
            "--kubeconfig-file",
            str(kubeconfig),
            "--privatebin-url",
            "https://pastes.example.com",
        ],
    ):
        with pytest.raises(SystemExit, match="1"):
            main()


@mock.patch("fleet.tasks.create_access_paste.subprocess.run")
def test_main_fails_when_paste_secret_cannot_be_saved(mock_run, tmp_path):
    kubeconfig = tmp_path / "kubeconfig"
    kubeconfig.write_text("apiVersion: v1\n")
    mock_run.side_effect = [
        mock.Mock(returncode=0, stdout="admin-password-secret"),
        mock.Mock(returncode=0, stdout="Y2x1c3Rlci1wYXNzd29yZA==", stderr=""),
        mock.Mock(
            returncode=0,
            stdout='{"paste_url":"https://paste.example/abc#key","delete_token":"delete-token"}\n',
            stderr="",
        ),
        mock.Mock(returncode=1, stdout="", stderr="forbidden"),
    ]

    with mock.patch(
        "sys.argv",
        [
            "prog",
            "--cluster-name",
            "example",
            "--base-domain",
            "example.com",
            "--kubeconfig-file",
            str(kubeconfig),
            "--privatebin-url",
            "https://pastes.example.com",
        ],
    ):
        with pytest.raises(SystemExit, match="1"):
            main()


@mock.patch("fleet.tasks.create_access_paste.subprocess.run")
def test_main_fails_when_kubeconfig_file_is_missing(mock_run, tmp_path):
    kubeconfig = tmp_path / "missing-kubeconfig"
    mock_run.side_effect = [
        mock.Mock(returncode=0, stdout="admin-password-secret"),
        mock.Mock(returncode=0, stdout="Y2x1c3Rlci1wYXNzd29yZA==", stderr=""),
    ]

    with mock.patch(
        "sys.argv",
        [
            "prog",
            "--cluster-name",
            "example",
            "--base-domain",
            "example.com",
            "--kubeconfig-file",
            str(kubeconfig),
            "--privatebin-url",
            "https://pastes.example.com",
        ],
    ):
        with pytest.raises(SystemExit, match="1"):
            main()


@mock.patch("fleet.tasks.create_access_paste.subprocess.run")
def test_main_does_not_log_secrets(mock_run, tmp_path, capsys):
    kubeconfig = tmp_path / "kubeconfig"
    kubeconfig.write_text("apiVersion: v1\n")

    mock_run.side_effect = [
        mock.Mock(returncode=0, stdout="admin-password-secret"),
        mock.Mock(returncode=0, stdout="Y2x1c3Rlci1wYXNzd29yZA=="),
        mock.Mock(
            returncode=0,
            stdout='{"paste_url":"https://paste.example/abc#key","delete_token":"delete-token"}\n',
        ),
        mock.Mock(returncode=0, stdout="", stderr=""),
    ]

    with mock.patch(
        "sys.argv",
        [
            "prog",
            "--cluster-name",
            "example",
            "--base-domain",
            "example.com",
            "--kubeconfig-file",
            str(kubeconfig),
            "--privatebin-url",
            "https://pastes.example.com",
        ],
    ):
        main()

    captured = capsys.readouterr()
    combined_output = captured.out + captured.err
    assert "cluster-password" not in combined_output
    assert "apiVersion: v1" not in combined_output
