import json
from unittest import mock

import pytest

from fleet.tasks.read_cluster_metadata import main


@mock.patch(
    "fleet.tasks.read_cluster_metadata.sys.argv",
    ["prog", "--cluster-dir", "/nonexistent"],
)
def test_missing_dir_exits_1():
    with pytest.raises(SystemExit, match="1"):
        main()


def test_metadata_file_exists(tmp_path, capsys):
    cluster_dir = tmp_path / "provision" / "c1"
    cluster_dir.mkdir(parents=True)
    (cluster_dir / "metadata.yaml").write_text("htpasswd-provider-name: PartnerIDP\n")
    with mock.patch("sys.argv", ["prog", "--cluster-dir", str(cluster_dir)]):
        main()
    out = json.loads(capsys.readouterr().out.strip())
    assert out["htpasswd-provider-name"] == "PartnerIDP"


def test_metadata_file_missing_outputs_empty_json(tmp_path, capsys):
    cluster_dir = tmp_path / "provision" / "c1"
    cluster_dir.mkdir(parents=True)
    with mock.patch("sys.argv", ["prog", "--cluster-dir", str(cluster_dir)]):
        main()
    out = json.loads(capsys.readouterr().out.strip())
    assert out == {}


def test_metadata_file_empty_outputs_empty_json(tmp_path, capsys):
    cluster_dir = tmp_path / "provision" / "c1"
    cluster_dir.mkdir(parents=True)
    (cluster_dir / "metadata.yaml").write_text("")
    with mock.patch("sys.argv", ["prog", "--cluster-dir", str(cluster_dir)]):
        main()
    out = json.loads(capsys.readouterr().out.strip())
    assert out == {}


def test_multiple_keys(tmp_path, capsys):
    cluster_dir = tmp_path / "provision" / "c1"
    cluster_dir.mkdir(parents=True)
    (cluster_dir / "metadata.yaml").write_text(
        "htpasswd-provider-name: MyIDP\nsome-other-key: value123\n"
    )
    with mock.patch("sys.argv", ["prog", "--cluster-dir", str(cluster_dir)]):
        main()
    out = json.loads(capsys.readouterr().out.strip())
    assert out["htpasswd-provider-name"] == "MyIDP"
    assert out["some-other-key"] == "value123"
