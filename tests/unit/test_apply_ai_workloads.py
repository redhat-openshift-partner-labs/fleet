from unittest import mock
import subprocess
import pytest

from fleet.tasks.apply_ai_workloads import main, wait_for_csv_ready, wait_for_nfd_ready, wait_for_datasciencecluster_ready


def _ok(**overrides):
    defaults = {"args": [], "returncode": 0, "stdout": "yaml-output", "stderr": ""}
    defaults.update(overrides)
    return subprocess.CompletedProcess(**defaults)


def _fail(**overrides):
    defaults = {"args": [], "returncode": 1, "stdout": "", "stderr": "error"}
    defaults.update(overrides)
    return subprocess.CompletedProcess(**defaults)


@mock.patch("fleet.tasks.apply_ai_workloads.run_with_retry")
def test_apply_success(mock_retry):
    """Test successful application of AI workloads with all readiness checks."""
    # Mock sequence: kustomize build, oc apply, then all readiness checks
    mock_retry.side_effect = [
        _ok(stdout="apiVersion: v1\nkind: List\nitems: []"),  # kustomize build
        _ok(stdout="configured"),   # oc apply
        _ok(stdout="Succeeded"),   # NFD CSV ready
        _ok(stdout="True"),        # NFD operand ready
        _ok(stdout="Succeeded"),   # GPU Operator CSV ready
        _ok(stdout="Succeeded"),   # OpenShift AI CSV ready
        _ok(stdout="True"),        # DataScienceCluster ready
    ]

    with mock.patch(
        "sys.argv",
        [
            "prog",
            "--cluster-name",
            "test-cluster",
            "--source-dir",
            "/workspace/source/workloads/ai",
            "--spoke-kubeconfig",
            "/workspace/kubeconfig",
        ],
    ):
        main()

    assert mock_retry.call_count == 7
    # Verify kustomize build command
    kustomize_call = mock_retry.call_args_list[0]
    assert "kustomize" in " ".join(kustomize_call.args[0])
    assert "/workspace/source/workloads/ai" in kustomize_call.args[0]

    # Verify oc apply command
    apply_call = mock_retry.call_args_list[1]
    assert "--kubeconfig=/workspace/kubeconfig" in apply_call.args[0]


@mock.patch("fleet.tasks.apply_ai_workloads.run_with_retry")
def test_kustomize_build_fails(mock_retry):
    """Test failure when kustomize build fails."""
    mock_retry.return_value = _fail(stderr="error building kustomization")

    with mock.patch(
        "sys.argv",
        [
            "prog",
            "--cluster-name",
            "test-cluster",
            "--source-dir",
            "/workspace/source/workloads/ai",
            "--spoke-kubeconfig",
            "/workspace/kubeconfig",
        ],
    ):
        with pytest.raises(SystemExit, match="1"):
            main()


@mock.patch("fleet.tasks.apply_ai_workloads.run_with_retry")
def test_apply_fails(mock_retry):
    """Test failure when oc apply fails."""
    mock_retry.side_effect = [
        _ok(stdout="apiVersion: v1\nkind: List"),  # kustomize build succeeds
        _fail(stderr="forbidden"),                # oc apply fails
    ]

    with mock.patch(
        "sys.argv",
        [
            "prog",
            "--cluster-name",
            "test-cluster",
            "--source-dir",
            "/workspace/source/workloads/ai",
            "--spoke-kubeconfig",
            "/workspace/kubeconfig",
        ],
    ):
        with pytest.raises(SystemExit, match="1"):
            main()


@mock.patch("fleet.tasks.apply_ai_workloads.run_with_retry")
def test_nfd_csv_wait_timeout(mock_retry):
    """Test timeout when NFD CSV never becomes ready."""
    mock_retry.side_effect = [
        _ok(stdout="apiVersion: v1\nkind: List"),  # kustomize build
        _ok(stdout="configured"),                 # oc apply
        _ok(stdout="Installing"),                 # NFD CSV not ready
    ]

    with mock.patch(
        "sys.argv",
        [
            "prog",
            "--cluster-name",
            "test-cluster",
            "--source-dir",
            "/workspace/source/workloads/ai",
            "--spoke-kubeconfig",
            "/workspace/kubeconfig",
        ],
    ):
        with mock.patch("fleet.tasks.apply_ai_workloads.wait_for_csv_ready") as mock_wait:
            mock_wait.return_value = False
            with pytest.raises(SystemExit, match="1"):
                main()


@mock.patch("fleet.tasks.apply_ai_workloads.run_with_retry")
@mock.patch("time.sleep")  # Mock sleep to speed up tests
def test_wait_for_csv_ready_success(mock_sleep, mock_retry):
    """Test successful CSV readiness check."""
    mock_retry.return_value = _ok(stdout="Succeeded")

    result = wait_for_csv_ready("test-csv", "test-namespace", "/kubeconfig", 600)
    assert result is True

    # Verify correct oc command was called
    mock_retry.assert_called_once()
    call_args = mock_retry.call_args.args[0]
    assert "oc" in call_args
    assert "get" in call_args
    assert "csv" in call_args
    assert "test-csv" in call_args
    assert "-n" in call_args
    assert "test-namespace" in call_args


@mock.patch("fleet.tasks.apply_ai_workloads.run_with_retry")
@mock.patch("time.sleep")
@mock.patch("time.time")
def test_wait_for_csv_ready_timeout(mock_time, mock_sleep, mock_retry):
    """Test CSV readiness check timeout."""
    # Mock time to simulate timeout
    mock_time.side_effect = [0, 700]  # Start at 0, then jump past timeout
    mock_retry.return_value = _ok(stdout="Installing")

    result = wait_for_csv_ready("test-csv", "test-namespace", "/kubeconfig", 600)
    assert result is False


@mock.patch("fleet.tasks.apply_ai_workloads.run_with_retry")
@mock.patch("time.sleep")
def test_wait_for_nfd_ready_success(mock_sleep, mock_retry):
    """Test successful NFD operand readiness check."""
    mock_retry.return_value = _ok(stdout="True")

    result = wait_for_nfd_ready("/kubeconfig", 300)
    assert result is True

    # Verify correct oc command
    call_args = mock_retry.call_args.args[0]
    assert "oc" in call_args
    assert "get" in call_args
    assert "nodefeaturesdiscovery" in call_args
    assert "nfd-instance" in call_args


@mock.patch("fleet.tasks.apply_ai_workloads.run_with_retry")
@mock.patch("time.sleep")
def test_wait_for_datasciencecluster_ready_success(mock_sleep, mock_retry):
    """Test successful DataScienceCluster readiness check."""
    mock_retry.return_value = _ok(stdout="True")

    result = wait_for_datasciencecluster_ready("/kubeconfig", 600)
    assert result is True

    # Verify correct oc command
    call_args = mock_retry.call_args.args[0]
    assert "oc" in call_args
    assert "get" in call_args
    assert "datasciencecluster" in call_args
    assert "default-dsc" in call_args


@mock.patch("fleet.tasks.apply_ai_workloads.run_with_retry")
@mock.patch("time.sleep")
@mock.patch("time.time")
def test_wait_for_nfd_ready_timeout(mock_time, mock_sleep, mock_retry):
    """Test NFD operand readiness timeout."""
    mock_time.side_effect = [0, 350]  # Jump past timeout
    mock_retry.return_value = _ok(stdout="False")

    result = wait_for_nfd_ready("/kubeconfig", 300)
    assert result is False


@mock.patch("fleet.tasks.apply_ai_workloads.run_with_retry")
def test_wait_for_csv_not_found_initially(mock_retry):
    """Test CSV readiness when CSV doesn't exist initially."""
    mock_retry.side_effect = [
        _fail(stderr="NotFound"),  # CSV doesn't exist yet
        _ok(stdout="Succeeded"),   # CSV exists and ready on second check
    ]

    with mock.patch("time.sleep"):
        with mock.patch("time.time", side_effect=[0, 5, 10]):
            result = wait_for_csv_ready("test-csv", "test-namespace", "/kubeconfig", 600)

    assert result is True
    assert mock_retry.call_count == 2


@mock.patch("fleet.tasks.apply_ai_workloads.apply_manifests_and_wait")
def test_uses_correct_source_dir(mock_apply):
    """Test that the correct source directory is passed to apply function."""
    mock_apply.return_value = True

    with mock.patch(
        "sys.argv",
        [
            "prog",
            "--cluster-name",
            "test-cluster",
            "--source-dir",
            "/custom/workloads/path",
            "--spoke-kubeconfig",
            "/workspace/kubeconfig",
        ],
    ):
        main()

    mock_apply.assert_called_once_with("/custom/workloads/path", "/workspace/kubeconfig")


@mock.patch("fleet.tasks.apply_ai_workloads.run_with_retry")
def test_gpu_operator_csv_failure_stops_execution(mock_retry):
    """Test that GPU Operator CSV failure stops the execution."""
    mock_retry.side_effect = [
        _ok(stdout="apiVersion: v1\nkind: List"),  # kustomize build
        _ok(stdout="configured"),                 # oc apply
        _ok(stdout="Succeeded"),                  # NFD CSV ready
        _ok(stdout="True"),                       # NFD operand ready
        _ok(stdout="Failed"),                     # GPU Operator CSV failed
    ]

    with mock.patch(
        "sys.argv",
        [
            "prog",
            "--cluster-name",
            "test-cluster",
            "--source-dir",
            "/workspace/source/workloads/ai",
            "--spoke-kubeconfig",
            "/workspace/kubeconfig",
        ],
    ):
        with mock.patch("fleet.tasks.apply_ai_workloads.wait_for_csv_ready") as mock_wait:
            # First call (NFD) succeeds, second call (GPU Operator) fails
            mock_wait.side_effect = [True, True, False]
            with pytest.raises(SystemExit, match="1"):
                main()


@mock.patch("fleet.tasks.apply_ai_workloads.run_with_retry")
@mock.patch("time.sleep")
@mock.patch("time.time")
def test_wait_for_datasciencecluster_timeout(mock_time, mock_sleep, mock_retry):
    """Test DataScienceCluster readiness timeout."""
    mock_time.side_effect = [0, 700]  # Jump past timeout
    mock_retry.return_value = _ok(stdout="False")

    result = wait_for_datasciencecluster_ready("/kubeconfig", 600)
    assert result is False


@mock.patch("fleet.tasks.apply_ai_workloads.run_with_retry")
def test_openshift_ai_csv_failure(mock_retry):
    """Test OpenShift AI CSV failure scenario."""
    mock_retry.side_effect = [
        _ok(stdout="apiVersion: v1\nkind: List"),  # kustomize build
        _ok(stdout="configured"),                 # oc apply
    ]

    with mock.patch(
        "sys.argv",
        [
            "prog",
            "--cluster-name",
            "test-cluster",
            "--source-dir",
            "/workspace/source/workloads/ai",
            "--spoke-kubeconfig",
            "/workspace/kubeconfig",
        ],
    ):
        with mock.patch("fleet.tasks.apply_ai_workloads.wait_for_csv_ready") as mock_wait_csv:
            with mock.patch("fleet.tasks.apply_ai_workloads.wait_for_nfd_ready") as mock_wait_nfd:
                # NFD steps succeed, OpenShift AI CSV fails
                mock_wait_csv.side_effect = [True, True, False]  # NFD, GPU Op, OAI
                mock_wait_nfd.return_value = True
                with pytest.raises(SystemExit, match="1"):
                    main()


@mock.patch("fleet.tasks.apply_ai_workloads.run_with_retry")
def test_datasciencecluster_failure(mock_retry):
    """Test DataScienceCluster creation failure."""
    mock_retry.side_effect = [
        _ok(stdout="apiVersion: v1\nkind: List"),  # kustomize build
        _ok(stdout="configured"),                 # oc apply
    ]

    with mock.patch(
        "sys.argv",
        [
            "prog",
            "--cluster-name",
            "test-cluster",
            "--source-dir",
            "/workspace/source/workloads/ai",
            "--spoke-kubeconfig",
            "/workspace/kubeconfig",
        ],
    ):
        with mock.patch("fleet.tasks.apply_ai_workloads.wait_for_csv_ready") as mock_wait_csv:
            with mock.patch("fleet.tasks.apply_ai_workloads.wait_for_nfd_ready") as mock_wait_nfd:
                with mock.patch("fleet.tasks.apply_ai_workloads.wait_for_datasciencecluster_ready") as mock_wait_dsc:
                    # All CSVs succeed, DSC fails
                    mock_wait_csv.return_value = True
                    mock_wait_nfd.return_value = True
                    mock_wait_dsc.return_value = False
                    with pytest.raises(SystemExit, match="1"):
                        main()