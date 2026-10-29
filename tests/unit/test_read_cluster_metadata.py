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


def test_metadata_non_object_exits_1(tmp_path):
    cluster_dir = tmp_path / "provision" / "c1"
    cluster_dir.mkdir(parents=True)
    (cluster_dir / "metadata.yaml").write_text("- item\n")
    with mock.patch("sys.argv", ["prog", "--cluster-dir", str(cluster_dir)]):
        with pytest.raises(SystemExit, match="1"):
            main()


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


def test_ai_accelerator_none(tmp_path, capsys):
    cluster_dir = tmp_path / "provision" / "c1"
    cluster_dir.mkdir(parents=True)
    (cluster_dir / "metadata.yaml").write_text("ai-accelerator: none\n")
    with mock.patch("sys.argv", ["prog", "--cluster-dir", str(cluster_dir)]):
        main()
    out = json.loads(capsys.readouterr().out.strip())
    assert out["ai-accelerator"] == "none"


def test_ai_accelerator_nvidia_gpu(tmp_path, capsys):
    cluster_dir = tmp_path / "provision" / "c1"
    cluster_dir.mkdir(parents=True)
    (cluster_dir / "metadata.yaml").write_text("ai-accelerator: nvidia-gpu\n")
    with mock.patch("sys.argv", ["prog", "--cluster-dir", str(cluster_dir)]):
        main()
    out = json.loads(capsys.readouterr().out.strip())
    assert out["ai-accelerator"] == "nvidia-gpu"


def test_ai_accelerator_invalid_exits_1(tmp_path):
    cluster_dir = tmp_path / "provision" / "c1"
    cluster_dir.mkdir(parents=True)
    (cluster_dir / "metadata.yaml").write_text("ai-accelerator: tpu\n")
    with mock.patch("sys.argv", ["prog", "--cluster-dir", str(cluster_dir)]):
        with pytest.raises(SystemExit, match="1"):
            main()


def test_timezone_and_schedule_are_output(tmp_path, capsys):
    cluster_dir = tmp_path / "provision" / "c1"
    cluster_dir.mkdir(parents=True)
    (cluster_dir / "metadata.yaml").write_text(
        'timezone: America/Chicago\nschedule: "00 08 * * 1-5"\n'
    )
    with mock.patch("sys.argv", ["prog", "--cluster-dir", str(cluster_dir)]):
        main()
    out = json.loads(capsys.readouterr().out.strip())
    assert out["timezone"] == "America/Chicago"
    assert out["schedule"] == "00 08 * * 1-5"


def test_invalid_timezone_exits_1(tmp_path):
    cluster_dir = tmp_path / "provision" / "c1"
    cluster_dir.mkdir(parents=True)
    (cluster_dir / "metadata.yaml").write_text("timezone: Not/AZone\n")
    with mock.patch("sys.argv", ["prog", "--cluster-dir", str(cluster_dir)]):
        with pytest.raises(SystemExit, match="1"):
            main()


def test_schedule_with_wrong_field_count_exits_1(tmp_path):
    cluster_dir = tmp_path / "provision" / "c1"
    cluster_dir.mkdir(parents=True)
    (cluster_dir / "metadata.yaml").write_text('schedule: "00 08 * *"\n')
    with mock.patch("sys.argv", ["prog", "--cluster-dir", str(cluster_dir)]):
        with pytest.raises(SystemExit, match="1"):
            main()


def test_schedule_with_out_of_range_value_exits_1(tmp_path):
    cluster_dir = tmp_path / "provision" / "c1"
    cluster_dir.mkdir(parents=True)
    (cluster_dir / "metadata.yaml").write_text('schedule: "60 08 * * 1-5"\n')
    with mock.patch("sys.argv", ["prog", "--cluster-dir", str(cluster_dir)]):
        with pytest.raises(SystemExit, match="1"):
            main()
