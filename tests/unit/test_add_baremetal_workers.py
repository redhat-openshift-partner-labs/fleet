import json
import subprocess
from unittest import mock

import pytest

from fleet.tasks.add_baremetal_workers import (
    create_baremetal_machinepool,
    get_cluster_region_and_zones,
    main,
    wait_for_machinepool_ready,
)


def _ok(**overrides):
    defaults = {"args": [], "returncode": 0, "stdout": "success", "stderr": ""}
    defaults.update(overrides)
    return subprocess.CompletedProcess(**defaults)


def _fail(**overrides):
    defaults = {"args": [], "returncode": 1, "stdout": "", "stderr": "error"}
    defaults.update(overrides)
    return subprocess.CompletedProcess(**defaults)


@mock.patch("fleet.tasks.add_baremetal_workers.run_with_retry")
def test_get_cluster_region_and_zones_success(mock_retry):
    cluster_deployment_response = {
        "spec": {"platform": {"aws": {"region": "us-east-2"}}}
    }
    machinepool_response = {
        "spec": {
            "platform": {"aws": {"zones": ["us-east-2a", "us-east-2b", "us-east-2c"]}}
        }
    }

    mock_retry.side_effect = [
        _ok(stdout=json.dumps(cluster_deployment_response)),
        _ok(stdout=json.dumps(machinepool_response)),
    ]

    result = get_cluster_region_and_zones("test-cluster")

    assert result == {
        "region": "us-east-2",
        "zones": ["us-east-2a", "us-east-2b", "us-east-2c"],
    }


@mock.patch("fleet.tasks.add_baremetal_workers.run_with_retry")
def test_get_cluster_region_and_zones_clusterdeployment_fails(mock_retry):
    mock_retry.return_value = _fail(stderr="ClusterDeployment not found")

    result = get_cluster_region_and_zones("test-cluster")

    assert result is None


@mock.patch("fleet.tasks.add_baremetal_workers.run_with_retry")
def test_get_cluster_region_and_zones_invalid_json(mock_retry):
    mock_retry.return_value = _ok(stdout="invalid json")

    result = get_cluster_region_and_zones("test-cluster")

    assert result is None


@mock.patch("fleet.tasks.add_baremetal_workers.run_with_retry")
def test_get_cluster_region_and_zones_missing_keys(mock_retry):
    cluster_deployment_response = {"spec": {"platform": {}}}  # Missing aws key

    mock_retry.return_value = _ok(stdout=json.dumps(cluster_deployment_response))

    result = get_cluster_region_and_zones("test-cluster")

    assert result is None


@mock.patch("fleet.tasks.add_baremetal_workers.run_with_retry")
def test_get_cluster_region_and_zones_machinepool_fallback(mock_retry):
    cluster_deployment_response = {
        "spec": {"platform": {"aws": {"region": "us-west-1"}}}
    }

    mock_retry.side_effect = [
        _ok(stdout=json.dumps(cluster_deployment_response)),
        _fail(),  # MachinePool get fails
    ]

    result = get_cluster_region_and_zones("test-cluster")

    assert result == {
        "region": "us-west-1",
        "zones": ["us-west-1a", "us-west-1b", "us-west-1c"],  # Default fallback
    }


@mock.patch("fleet.tasks.add_baremetal_workers.run_with_retry")
def test_get_cluster_region_and_zones_machinepool_invalid_json(mock_retry):
    cluster_deployment_response = {
        "spec": {"platform": {"aws": {"region": "us-west-1"}}}
    }

    mock_retry.side_effect = [
        _ok(stdout=json.dumps(cluster_deployment_response)),
        _ok(stdout="invalid machinepool json"),
    ]

    result = get_cluster_region_and_zones("test-cluster")

    assert result == {
        "region": "us-west-1",
        "zones": ["us-west-1a", "us-west-1b", "us-west-1c"],  # Default fallback
    }


@mock.patch("fleet.tasks.add_baremetal_workers.run_with_retry")
def test_create_baremetal_machinepool_success(mock_retry):
    mock_retry.return_value = _ok(
        stdout="machinepool.hive.openshift.io/test-cluster-baremetal created"
    )

    region_info = {"region": "us-east-2", "zones": ["us-east-2a", "us-east-2b"]}
    result = create_baremetal_machinepool("test-cluster", region_info)

    assert result is True

    # Verify the call was made with stdin input
    args, kwargs = mock_retry.call_args
    assert args[0] == ["oc", "apply", "-f", "-"]
    assert kwargs["capture_output"] is True
    assert kwargs["text"] is True
    assert "input" in kwargs

    # Verify the JSON input contains expected MachinePool spec
    json_input = json.loads(kwargs["input"])
    assert json_input["kind"] == "MachinePool"
    assert json_input["metadata"]["name"] == "test-cluster-baremetal"
    assert json_input["spec"]["platform"]["aws"]["zones"] == [
        "us-east-2a",
        "us-east-2b",
    ]


@mock.patch("fleet.tasks.add_baremetal_workers.json.dumps")
def test_create_baremetal_machinepool_json_serialization_fails(mock_json_dumps):
    mock_json_dumps.side_effect = TypeError(
        "Object of type set is not JSON serializable"
    )

    region_info = {"region": "us-east-2", "zones": ["us-east-2a"]}
    result = create_baremetal_machinepool("test-cluster", region_info)

    assert result is False


@mock.patch("fleet.tasks.add_baremetal_workers.run_with_retry")
def test_create_baremetal_machinepool_apply_fails(mock_retry):
    mock_retry.return_value = _fail(stderr="Failed to create MachinePool")

    region_info = {"region": "us-east-2", "zones": ["us-east-2a"]}
    result = create_baremetal_machinepool("test-cluster", region_info)

    assert result is False


@mock.patch("fleet.tasks.add_baremetal_workers.time.sleep")
@mock.patch("fleet.tasks.add_baremetal_workers.run_with_retry")
def test_wait_for_machinepool_ready_success(mock_retry, mock_sleep):
    machinepool_response = {
        "spec": {"replicas": 1},
        "status": {"replicas": 1, "machineSets": [{"readyReplicas": 1}]},
    }
    mock_retry.return_value = _ok(stdout=json.dumps(machinepool_response))

    result = wait_for_machinepool_ready("test-cluster")

    assert result is True


@mock.patch("fleet.tasks.add_baremetal_workers.time.sleep")
@mock.patch("fleet.tasks.add_baremetal_workers.run_with_retry")
def test_wait_for_machinepool_ready_not_ready(mock_retry, mock_sleep):
    machinepool_response = {
        "spec": {"replicas": 1},
        "status": {"replicas": 0, "machineSets": [{"readyReplicas": 0}]},
    }

    mock_retry.side_effect = [
        _ok(stdout=json.dumps(machinepool_response)),
        _ok(stdout=json.dumps(machinepool_response)),
    ]

    with mock.patch(
        "fleet.tasks.add_baremetal_workers.time.time", side_effect=[0, 30, 1210]
    ):
        result = wait_for_machinepool_ready("test-cluster", timeout=1200)

    assert result is False


@mock.patch("fleet.tasks.add_baremetal_workers.time.sleep")
@mock.patch("fleet.tasks.add_baremetal_workers.run_with_retry")
def test_wait_for_machinepool_ready_failed_condition(mock_retry, mock_sleep):
    machinepool_response = {
        "spec": {"replicas": 1},
        "status": {
            "replicas": 0,
            "readyReplicas": 0,
            "conditions": [
                {
                    "type": "Failed",
                    "status": "True",
                    "message": "Instance launch failed",
                }
            ],
        },
    }
    mock_retry.return_value = _ok(stdout=json.dumps(machinepool_response))

    result = wait_for_machinepool_ready("test-cluster")

    assert result is False


@mock.patch("fleet.tasks.add_baremetal_workers.time.sleep")
@mock.patch("fleet.tasks.add_baremetal_workers.run_with_retry")
def test_wait_for_machinepool_ready_get_fails(mock_retry, mock_sleep):
    mock_retry.side_effect = [_fail(), _fail()]

    with mock.patch(
        "fleet.tasks.add_baremetal_workers.time.time", side_effect=[0, 30, 1210]
    ):
        result = wait_for_machinepool_ready("test-cluster", timeout=1200)

    assert result is False


@mock.patch("fleet.tasks.add_baremetal_workers.time.sleep")
@mock.patch("fleet.tasks.add_baremetal_workers.run_with_retry")
def test_wait_for_machinepool_ready_json_parse_error(mock_retry, mock_sleep):
    mock_retry.side_effect = [_ok(stdout="invalid json"), _ok(stdout="invalid json")]

    with mock.patch(
        "fleet.tasks.add_baremetal_workers.time.time", side_effect=[0, 30, 1210]
    ):
        result = wait_for_machinepool_ready("test-cluster", timeout=1200)

    assert result is False


@mock.patch("fleet.tasks.add_baremetal_workers.time.sleep")
@mock.patch("fleet.tasks.add_baremetal_workers.time.time")
@mock.patch("fleet.tasks.add_baremetal_workers.run_with_retry")
def test_wait_for_machinepool_ready_timeout(mock_retry, mock_time, mock_sleep):
    mock_time.side_effect = [0, 1210]  # Start time, timeout time
    mock_retry.return_value = _ok(stdout='{"spec": {"replicas": 1}, "status": {}}')

    result = wait_for_machinepool_ready("test-cluster", timeout=1200)

    assert result is False


@mock.patch("fleet.tasks.add_baremetal_workers.get_cluster_region_and_zones")
@mock.patch("fleet.tasks.add_baremetal_workers.create_baremetal_machinepool")
@mock.patch("fleet.tasks.add_baremetal_workers.wait_for_machinepool_ready")
def test_main_success(mock_wait_ready, mock_create_mp, mock_get_regions):
    mock_get_regions.return_value = {
        "region": "us-east-2",
        "zones": ["us-east-2a", "us-east-2b"],
    }
    mock_create_mp.return_value = True
    mock_wait_ready.return_value = True

    with mock.patch(
        "sys.argv",
        [
            "add-baremetal-workers",
            "--cluster-name",
            "test-cluster",
        ],
    ):
        main()

    mock_get_regions.assert_called_once_with("test-cluster")
    mock_create_mp.assert_called_once_with(
        "test-cluster", {"region": "us-east-2", "zones": ["us-east-2a", "us-east-2b"]}
    )
    mock_wait_ready.assert_called_once_with("test-cluster")


@mock.patch("fleet.tasks.add_baremetal_workers.get_cluster_region_and_zones")
def test_main_get_regions_fails(mock_get_regions):
    mock_get_regions.return_value = None

    with mock.patch(
        "sys.argv",
        [
            "add-baremetal-workers",
            "--cluster-name",
            "test-cluster",
        ],
    ):
        with pytest.raises(SystemExit) as exc:
            main()

    assert exc.value.code == 1


@mock.patch("fleet.tasks.add_baremetal_workers.get_cluster_region_and_zones")
@mock.patch("fleet.tasks.add_baremetal_workers.create_baremetal_machinepool")
def test_main_create_machinepool_fails(mock_create_mp, mock_get_regions):
    mock_get_regions.return_value = {
        "region": "us-east-2",
        "zones": ["us-east-2a"],
    }
    mock_create_mp.return_value = False

    with mock.patch(
        "sys.argv",
        [
            "add-baremetal-workers",
            "--cluster-name",
            "test-cluster",
        ],
    ):
        with pytest.raises(SystemExit) as exc:
            main()

    assert exc.value.code == 1


@mock.patch("fleet.tasks.add_baremetal_workers.get_cluster_region_and_zones")
@mock.patch("fleet.tasks.add_baremetal_workers.create_baremetal_machinepool")
@mock.patch("fleet.tasks.add_baremetal_workers.wait_for_machinepool_ready")
def test_main_wait_for_ready_fails(mock_wait_ready, mock_create_mp, mock_get_regions):
    mock_get_regions.return_value = {
        "region": "us-east-2",
        "zones": ["us-east-2a"],
    }
    mock_create_mp.return_value = True
    mock_wait_ready.return_value = False

    with mock.patch(
        "sys.argv",
        [
            "add-baremetal-workers",
            "--cluster-name",
            "test-cluster",
        ],
    ):
        with pytest.raises(SystemExit) as exc:
            main()

    assert exc.value.code == 1
