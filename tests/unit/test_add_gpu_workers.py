from unittest import mock
import subprocess
import json
import pytest

from fleet.tasks.add_gpu_workers import main, get_cluster_region_and_zones, create_gpu_machinepool, wait_for_machinepool_ready


def _ok(**overrides):
    defaults = {"args": [], "returncode": 0, "stdout": "success", "stderr": ""}
    defaults.update(overrides)
    return subprocess.CompletedProcess(**defaults)


def _fail(**overrides):
    defaults = {"args": [], "returncode": 1, "stdout": "", "stderr": "error"}
    defaults.update(overrides)
    return subprocess.CompletedProcess(**defaults)


@mock.patch("fleet.tasks.add_gpu_workers.run_with_retry")
def test_get_cluster_region_and_zones_success(mock_retry):
    """Test successful retrieval of cluster region and availability zones."""
    cluster_deployment = {
        "spec": {
            "platform": {
                "aws": {
                    "region": "us-east-1"
                }
            }
        }
    }

    zones = ["us-east-1a", "us-east-1b", "us-east-1c"]

    mock_retry.side_effect = [
        _ok(stdout=json.dumps(cluster_deployment)),  # ClusterDeployment
        _ok(stdout=json.dumps(zones))                # MachinePool zones
    ]

    region, returned_zones = get_cluster_region_and_zones("test-cluster", "/kubeconfig")

    assert region == "us-east-1"
    assert returned_zones == zones
    assert mock_retry.call_count == 2


@mock.patch("fleet.tasks.add_gpu_workers.run_with_retry")
def test_get_cluster_region_non_aws_platform(mock_retry):
    """Test error when cluster is not on AWS platform."""
    cluster_deployment = {
        "spec": {
            "platform": {
                "azure": {
                    "region": "eastus"
                }
            }
        }
    }

    mock_retry.return_value = _ok(stdout=json.dumps(cluster_deployment))

    with pytest.raises(SystemExit, match="1"):
        get_cluster_region_and_zones("test-cluster", "/kubeconfig")


@mock.patch("fleet.tasks.add_gpu_workers.run_with_retry")
def test_get_cluster_region_clusterdeployment_not_found(mock_retry):
    """Test error when ClusterDeployment is not found."""
    mock_retry.return_value = _fail(stderr="ClusterDeployment not found")

    with pytest.raises(SystemExit, match="1"):
        get_cluster_region_and_zones("test-cluster", "/kubeconfig")


@mock.patch("fleet.tasks.add_gpu_workers.run_with_retry")
def test_create_gpu_machinepool_success(mock_retry):
    """Test successful GPU MachinePool creation."""
    mock_retry.return_value = _ok(stdout="machinepool.hive.openshift.io/test-cluster-gpu created")

    result = create_gpu_machinepool("test-cluster", "us-east-1", ["us-east-1a"], "/kubeconfig")

    assert result is True
    mock_retry.assert_called_once()

    # Verify the MachinePool spec was passed correctly
    call_args = mock_retry.call_args
    machinepool_json = call_args.kwargs['input']
    machinepool_spec = json.loads(machinepool_json)

    assert machinepool_spec['metadata']['name'] == "test-cluster-gpu"
    assert machinepool_spec['spec']['platform']['aws']['type'] == "g5.4xlarge"
    assert machinepool_spec['spec']['replicas'] == 1
    assert "nvidia.com/gpu" in [taint['key'] for taint in machinepool_spec['spec']['taints']]


@mock.patch("fleet.tasks.add_gpu_workers.run_with_retry")
def test_create_gpu_machinepool_failure(mock_retry):
    """Test GPU MachinePool creation failure."""
    mock_retry.return_value = _fail(stderr="Failed to create MachinePool")

    result = create_gpu_machinepool("test-cluster", "us-east-1", ["us-east-1a"], "/kubeconfig")

    assert result is False


@mock.patch("fleet.tasks.add_gpu_workers.run_with_retry")
@mock.patch("time.sleep")  # Mock sleep to speed up tests
def test_wait_for_machinepool_ready_success(mock_sleep, mock_retry):
    """Test successful MachinePool readiness check."""
    machinepool_status = {
        "status": {
            "replicas": 1,
            "readyReplicas": 1
        }
    }

    mock_retry.return_value = _ok(stdout=json.dumps(machinepool_status))

    result = wait_for_machinepool_ready("test-cluster", "/kubeconfig", 300)
    assert result is True


@mock.patch("fleet.tasks.add_gpu_workers.run_with_retry")
@mock.patch("time.sleep")
@mock.patch("time.time")
def test_wait_for_machinepool_ready_timeout(mock_time, mock_sleep, mock_retry):
    """Test MachinePool readiness timeout."""
    machinepool_status = {
        "status": {
            "replicas": 1,
            "readyReplicas": 0
        }
    }

    mock_time.side_effect = [0, 2500]  # Jump past timeout
    mock_retry.return_value = _ok(stdout=json.dumps(machinepool_status))

    result = wait_for_machinepool_ready("test-cluster", "/kubeconfig", 2400)
    assert result is False


@mock.patch("fleet.tasks.add_gpu_workers.run_with_retry")
@mock.patch("time.sleep")
def test_wait_for_machinepool_not_found_initially(mock_sleep, mock_retry):
    """Test MachinePool readiness when MachinePool doesn't exist initially."""
    machinepool_status = {
        "status": {
            "replicas": 1,
            "readyReplicas": 1
        }
    }

    mock_retry.side_effect = [
        _fail(stderr="NotFound"),            # MachinePool doesn't exist yet
        _ok(stdout=json.dumps(machinepool_status))  # MachinePool exists and ready
    ]

    with mock.patch("time.time", side_effect=[0, 30, 60]):
        result = wait_for_machinepool_ready("test-cluster", "/kubeconfig", 300)

    assert result is True
    assert mock_retry.call_count == 2


@mock.patch("fleet.tasks.add_gpu_workers.get_cluster_region_and_zones")
@mock.patch("fleet.tasks.add_gpu_workers.create_gpu_machinepool")
@mock.patch("fleet.tasks.add_gpu_workers.wait_for_machinepool_ready")
def test_main_success(mock_wait, mock_create, mock_get_region):
    """Test successful main execution."""
    mock_get_region.return_value = ("us-east-1", ["us-east-1a", "us-east-1b"])
    mock_create.return_value = True
    mock_wait.return_value = True

    with mock.patch(
        "sys.argv",
        [
            "prog",
            "--cluster-name",
            "test-cluster",
            "--spoke-kubeconfig",
            "/workspace/kubeconfig",
        ],
    ):
        main()

    mock_get_region.assert_called_once_with("test-cluster", "/workspace/kubeconfig")
    mock_create.assert_called_once_with("test-cluster", "us-east-1", ["us-east-1a", "us-east-1b"], "/workspace/kubeconfig")
    mock_wait.assert_called_once_with("test-cluster", "/workspace/kubeconfig", 2400)


@mock.patch("fleet.tasks.add_gpu_workers.get_cluster_region_and_zones")
@mock.patch("fleet.tasks.add_gpu_workers.create_gpu_machinepool")
def test_main_create_machinepool_failure(mock_create, mock_get_region):
    """Test main execution when MachinePool creation fails."""
    mock_get_region.return_value = ("us-east-1", ["us-east-1a"])
    mock_create.return_value = False

    with mock.patch(
        "sys.argv",
        [
            "prog",
            "--cluster-name",
            "test-cluster",
            "--spoke-kubeconfig",
            "/workspace/kubeconfig",
        ],
    ):
        with pytest.raises(SystemExit, match="1"):
            main()


@mock.patch("fleet.tasks.add_gpu_workers.get_cluster_region_and_zones")
@mock.patch("fleet.tasks.add_gpu_workers.create_gpu_machinepool")
@mock.patch("fleet.tasks.add_gpu_workers.wait_for_machinepool_ready")
def test_main_wait_timeout_failure(mock_wait, mock_create, mock_get_region):
    """Test main execution when MachinePool provisioning times out."""
    mock_get_region.return_value = ("us-east-1", ["us-east-1a"])
    mock_create.return_value = True
    mock_wait.return_value = False

    with mock.patch(
        "sys.argv",
        [
            "prog",
            "--cluster-name",
            "test-cluster",
            "--spoke-kubeconfig",
            "/workspace/kubeconfig",
        ],
    ):
        with pytest.raises(SystemExit, match="1"):
            main()


@mock.patch("fleet.tasks.add_gpu_workers.run_with_retry")
def test_machinepool_spec_validation(mock_retry):
    """Test that GPU MachinePool spec contains all required fields."""
    mock_retry.return_value = _ok()

    create_gpu_machinepool("test-cluster", "us-west-2", ["us-west-2a", "us-west-2b"], "/kubeconfig")

    call_args = mock_retry.call_args
    machinepool_json = call_args.kwargs['input']
    spec = json.loads(machinepool_json)

    # Verify key specifications
    assert spec['metadata']['labels']['fleet.openshift.com/tier'] == "ai"
    assert spec['spec']['platform']['aws']['type'] == "g5.4xlarge"
    assert spec['spec']['platform']['aws']['rootVolume']['size'] == 256
    assert spec['spec']['platform']['aws']['rootVolume']['type'] == "gp3"
    assert spec['spec']['platform']['aws']['rootVolume']['iops'] == 4000
    assert spec['spec']['replicas'] == 1
    assert "node-role.kubernetes.io/gpu" in spec['spec']['labels']
    assert spec['spec']['platform']['aws']['zones'] == ["us-west-2a", "us-west-2b"]


@mock.patch("fleet.tasks.add_gpu_workers.run_with_retry")
def test_machinepool_gpu_taints(mock_retry):
    """Test that GPU MachinePool has correct taints for GPU workloads."""
    mock_retry.return_value = _ok()

    create_gpu_machinepool("test-cluster", "us-east-1", ["us-east-1a"], "/kubeconfig")

    call_args = mock_retry.call_args
    machinepool_json = call_args.kwargs['input']
    spec = json.loads(machinepool_json)

    # Verify GPU taint
    taints = spec['spec']['taints']
    assert len(taints) == 1
    gpu_taint = taints[0]
    assert gpu_taint['key'] == "nvidia.com/gpu"
    assert gpu_taint['value'] == "true"
    assert gpu_taint['effect'] == "NoSchedule"