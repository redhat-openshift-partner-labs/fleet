import json
import subprocess
from unittest import mock

import pytest

from fleet.tasks.apply_virt_workloads import (
    apply_manifest,
    main,
    wait_for_condition,
    wait_for_csv,
)


def _ok(**overrides):
    defaults = {"args": [], "returncode": 0, "stdout": "success", "stderr": ""}
    defaults.update(overrides)
    return subprocess.CompletedProcess(**defaults)


def _fail(**overrides):
    defaults = {"args": [], "returncode": 1, "stdout": "", "stderr": "error"}
    defaults.update(overrides)
    return subprocess.CompletedProcess(**defaults)


@mock.patch("fleet.tasks.apply_virt_workloads.run_with_retry")
def test_apply_manifest_success(mock_retry):
    mock_retry.return_value = _ok(stdout="namespace/nfd created")

    result = apply_manifest("test.yaml", "kubeconfig")

    assert result is True
    mock_retry.assert_called_once_with(
        ["oc", "apply", "-f", "test.yaml", "--kubeconfig=kubeconfig"],
        capture_output=True,
        text=True,
    )


@mock.patch("fleet.tasks.apply_virt_workloads.run_with_retry")
def test_apply_manifest_failure(mock_retry):
    mock_retry.return_value = _fail(stderr="failed to apply")

    result = apply_manifest("test.yaml", "kubeconfig")

    assert result is False


@mock.patch("fleet.tasks.apply_virt_workloads.time.sleep")
@mock.patch("fleet.tasks.apply_virt_workloads.run_with_retry")
def test_wait_for_csv_success(mock_retry, mock_sleep):
    csv_response = {
        "items": [
            {
                "metadata": {"name": "nfd-operator.v4.10.0"},
                "status": {"phase": "Succeeded"},
            }
        ]
    }
    mock_retry.return_value = _ok(stdout=json.dumps(csv_response))

    result = wait_for_csv("test-ns", "nfd", "kubeconfig")

    assert result is True
    mock_retry.assert_called_with(
        [
            "oc",
            "get",
            "csv",
            "-n",
            "test-ns",
            "-o",
            "json",
            "--kubeconfig=kubeconfig",
        ],
        capture_output=True,
        text=True,
    )


@mock.patch("fleet.tasks.apply_virt_workloads.time.sleep")
@mock.patch("fleet.tasks.apply_virt_workloads.run_with_retry")
def test_wait_for_csv_failure(mock_retry, mock_sleep):
    csv_response = {
        "items": [
            {
                "metadata": {"name": "nfd-operator.v4.10.0"},
                "status": {"phase": "Failed"},
            }
        ]
    }
    mock_retry.return_value = _ok(stdout=json.dumps(csv_response))

    result = wait_for_csv("test-ns", "nfd", "kubeconfig")

    assert result is False


@mock.patch("fleet.tasks.apply_virt_workloads.time.sleep")
@mock.patch("fleet.tasks.apply_virt_workloads.time.time")
@mock.patch("fleet.tasks.apply_virt_workloads.run_with_retry")
def test_wait_for_csv_timeout(mock_retry, mock_time, mock_sleep):
    # Mock time progression to trigger timeout
    mock_time.side_effect = [0, 610]  # Start time, timeout time
    mock_retry.return_value = _fail()

    result = wait_for_csv("test-ns", "nfd", "kubeconfig", timeout=600)

    assert result is False


@mock.patch("fleet.tasks.apply_virt_workloads.time.sleep")
@mock.patch("fleet.tasks.apply_virt_workloads.run_with_retry")
def test_wait_for_csv_not_found(mock_retry, mock_sleep):
    csv_response = {"items": []}
    mock_retry.side_effect = [
        _ok(stdout=json.dumps(csv_response)),
        _ok(stdout=json.dumps(csv_response)),
    ]

    with mock.patch(
        "fleet.tasks.apply_virt_workloads.time.time", side_effect=[0, 5, 610]
    ):
        result = wait_for_csv("test-ns", "nfd", "kubeconfig", timeout=600)

    assert result is False


@mock.patch("fleet.tasks.apply_virt_workloads.time.sleep")
@mock.patch("fleet.tasks.apply_virt_workloads.run_with_retry")
def test_wait_for_csv_json_parse_error(mock_retry, mock_sleep):
    mock_retry.side_effect = [
        _ok(stdout="invalid json"),
        _ok(stdout='{"items": []}'),
    ]

    with mock.patch(
        "fleet.tasks.apply_virt_workloads.time.time", side_effect=[0, 5, 610]
    ):
        result = wait_for_csv("test-ns", "nfd", "kubeconfig", timeout=600)

    assert result is False


@mock.patch("fleet.tasks.apply_virt_workloads.time.sleep")
@mock.patch("fleet.tasks.apply_virt_workloads.run_with_retry")
def test_wait_for_condition_success(mock_retry, mock_sleep):
    condition_response = {
        "status": {
            "conditions": [{"type": "Available", "status": "True", "reason": "Ready"}]
        }
    }
    mock_retry.return_value = _ok(stdout=json.dumps(condition_response))

    result = wait_for_condition(
        "NFD", "nfd-instance", "test-ns", "Available", "kubeconfig"
    )

    assert result is True


@mock.patch("fleet.tasks.apply_virt_workloads.time.sleep")
@mock.patch("fleet.tasks.apply_virt_workloads.time.time")
@mock.patch("fleet.tasks.apply_virt_workloads.run_with_retry")
def test_wait_for_condition_false_status(mock_retry, mock_time, mock_sleep):
    condition_response = {
        "status": {
            "conditions": [
                {
                    "type": "Available",
                    "status": "False",
                    "reason": "NotReady",
                    "message": "Operator not ready",
                }
            ]
        }
    }
    mock_retry.return_value = _ok(stdout=json.dumps(condition_response))
    # Mock timeout after 2 iterations
    mock_time.side_effect = [0, 10, 310]  # Start, check, timeout

    result = wait_for_condition(
        "NFD", "nfd-instance", "test-ns", "Available", "kubeconfig", timeout=300
    )

    assert result is False  # Should timeout and return False


@mock.patch("fleet.tasks.apply_virt_workloads.time.sleep")
@mock.patch("fleet.tasks.apply_virt_workloads.run_with_retry")
def test_wait_for_condition_resource_not_found(mock_retry, mock_sleep):
    mock_retry.side_effect = [_fail(), _ok(stdout='{"status": {"conditions": []}}')]

    with mock.patch(
        "fleet.tasks.apply_virt_workloads.time.time", side_effect=[0, 5, 310]
    ):
        result = wait_for_condition(
            "NFD", "nfd-instance", "test-ns", "Available", "kubeconfig", timeout=300
        )

    assert result is False


@mock.patch("fleet.tasks.apply_virt_workloads.time.sleep")
@mock.patch("fleet.tasks.apply_virt_workloads.time.time")
@mock.patch("fleet.tasks.apply_virt_workloads.run_with_retry")
def test_wait_for_condition_timeout(mock_retry, mock_time, mock_sleep):
    mock_time.side_effect = [0, 310]  # Start time, timeout time
    mock_retry.return_value = _ok(stdout='{"status": {"conditions": []}}')

    result = wait_for_condition(
        "NFD", "nfd-instance", "test-ns", "Available", "kubeconfig", timeout=300
    )

    assert result is False


@mock.patch("fleet.tasks.apply_virt_workloads.apply_manifest")
@mock.patch("fleet.tasks.apply_virt_workloads.wait_for_csv")
@mock.patch("fleet.tasks.apply_virt_workloads.wait_for_condition")
def test_main_success(mock_wait_condition, mock_wait_csv, mock_apply):
    mock_apply.return_value = True
    mock_wait_csv.return_value = True
    mock_wait_condition.return_value = True

    with mock.patch(
        "sys.argv",
        [
            "apply-virt-workloads",
            "--cluster-name",
            "test-cluster",
            "--source-dir",
            "/tmp/test",
            "--spoke-kubeconfig",
            "kubeconfig",
        ],
    ):
        main()

    # Verify NFD operator installation
    assert mock_apply.call_args_list[0] == mock.call(
        "/tmp/test/nfd-subscription.yaml", "kubeconfig"
    )
    assert mock_wait_csv.call_args_list[0] == mock.call(
        "openshift-nfd", "nfd", "kubeconfig", timeout=600
    )

    # Verify NFD operand creation
    assert mock_apply.call_args_list[1] == mock.call(
        "/tmp/test/nfd-operand.yaml", "kubeconfig"
    )
    assert mock_wait_condition.call_args_list[0] == mock.call(
        "NodeFeatureDiscovery",
        "nfd-instance",
        "openshift-nfd",
        "Available",
        "kubeconfig",
    )

    # Verify CNV operator installation
    assert mock_apply.call_args_list[2] == mock.call(
        "/tmp/test/cnv-subscription.yaml", "kubeconfig"
    )
    assert mock_wait_csv.call_args_list[1] == mock.call(
        "openshift-cnv", "kubevirt-hyperconverged", "kubeconfig", timeout=900
    )

    # Verify CNV operand creation
    assert mock_apply.call_args_list[3] == mock.call(
        "/tmp/test/hyperconverged.yaml", "kubeconfig"
    )
    assert mock_wait_condition.call_args_list[1] == mock.call(
        "HyperConverged",
        "kubevirt-hyperconverged",
        "openshift-cnv",
        "Available",
        "kubeconfig",
    )


@mock.patch("fleet.tasks.apply_virt_workloads.apply_manifest")
def test_main_nfd_subscription_fails(mock_apply):
    mock_apply.return_value = False

    with mock.patch(
        "sys.argv",
        [
            "apply-virt-workloads",
            "--cluster-name",
            "test-cluster",
            "--source-dir",
            "/tmp/test",
            "--spoke-kubeconfig",
            "kubeconfig",
        ],
    ):
        with pytest.raises(SystemExit) as exc:
            main()

    assert exc.value.code == 1


@mock.patch("fleet.tasks.apply_virt_workloads.apply_manifest")
@mock.patch("fleet.tasks.apply_virt_workloads.wait_for_csv")
def test_main_nfd_csv_wait_fails(mock_wait_csv, mock_apply):
    mock_apply.return_value = True
    mock_wait_csv.return_value = False

    with mock.patch(
        "sys.argv",
        [
            "apply-virt-workloads",
            "--cluster-name",
            "test-cluster",
            "--source-dir",
            "/tmp/test",
            "--spoke-kubeconfig",
            "kubeconfig",
        ],
    ):
        with pytest.raises(SystemExit) as exc:
            main()

    assert exc.value.code == 1


@mock.patch("fleet.tasks.apply_virt_workloads.apply_manifest")
@mock.patch("fleet.tasks.apply_virt_workloads.wait_for_csv")
@mock.patch("fleet.tasks.apply_virt_workloads.wait_for_condition")
def test_main_cnv_condition_wait_fails(mock_wait_condition, mock_wait_csv, mock_apply):
    mock_apply.return_value = True
    mock_wait_csv.return_value = True
    mock_wait_condition.side_effect = [True, False]  # NFD succeeds, CNV fails

    with mock.patch(
        "sys.argv",
        [
            "apply-virt-workloads",
            "--cluster-name",
            "test-cluster",
            "--source-dir",
            "/tmp/test",
            "--spoke-kubeconfig",
            "kubeconfig",
        ],
    ):
        with pytest.raises(SystemExit) as exc:
            main()

    assert exc.value.code == 1


@mock.patch("fleet.tasks.apply_virt_workloads.apply_manifest")
@mock.patch("fleet.tasks.apply_virt_workloads.wait_for_csv")
def test_main_nfd_operand_apply_fails(mock_wait_csv, mock_apply):
    mock_apply.side_effect = [True, False]  # NFD subscription succeeds, operand fails
    mock_wait_csv.return_value = True

    with mock.patch(
        "sys.argv",
        [
            "apply-virt-workloads",
            "--cluster-name",
            "test-cluster",
            "--source-dir",
            "/tmp/test",
            "--spoke-kubeconfig",
            "kubeconfig",
        ],
    ):
        with pytest.raises(SystemExit) as exc:
            main()

    assert exc.value.code == 1


@mock.patch("fleet.tasks.apply_virt_workloads.apply_manifest")
@mock.patch("fleet.tasks.apply_virt_workloads.wait_for_csv")
@mock.patch("fleet.tasks.apply_virt_workloads.wait_for_condition")
def test_main_nfd_condition_wait_fails(mock_wait_condition, mock_wait_csv, mock_apply):
    mock_apply.return_value = True
    mock_wait_csv.return_value = True
    mock_wait_condition.return_value = False  # NFD condition fails

    with mock.patch(
        "sys.argv",
        [
            "apply-virt-workloads",
            "--cluster-name",
            "test-cluster",
            "--source-dir",
            "/tmp/test",
            "--spoke-kubeconfig",
            "kubeconfig",
        ],
    ):
        with pytest.raises(SystemExit) as exc:
            main()

    assert exc.value.code == 1


@mock.patch("fleet.tasks.apply_virt_workloads.apply_manifest")
@mock.patch("fleet.tasks.apply_virt_workloads.wait_for_csv")
@mock.patch("fleet.tasks.apply_virt_workloads.wait_for_condition")
def test_main_cnv_subscription_apply_fails(
    mock_wait_condition, mock_wait_csv, mock_apply
):
    mock_apply.side_effect = [True, True, False]  # NFD works, CNV subscription fails
    mock_wait_csv.return_value = True
    mock_wait_condition.return_value = True

    with mock.patch(
        "sys.argv",
        [
            "apply-virt-workloads",
            "--cluster-name",
            "test-cluster",
            "--source-dir",
            "/tmp/test",
            "--spoke-kubeconfig",
            "kubeconfig",
        ],
    ):
        with pytest.raises(SystemExit) as exc:
            main()

    assert exc.value.code == 1


@mock.patch("fleet.tasks.apply_virt_workloads.apply_manifest")
@mock.patch("fleet.tasks.apply_virt_workloads.wait_for_csv")
@mock.patch("fleet.tasks.apply_virt_workloads.wait_for_condition")
def test_main_cnv_csv_wait_fails(mock_wait_condition, mock_wait_csv, mock_apply):
    mock_apply.return_value = True
    mock_wait_csv.side_effect = [True, False]  # NFD CSV succeeds, CNV CSV fails
    mock_wait_condition.return_value = True

    with mock.patch(
        "sys.argv",
        [
            "apply-virt-workloads",
            "--cluster-name",
            "test-cluster",
            "--source-dir",
            "/tmp/test",
            "--spoke-kubeconfig",
            "kubeconfig",
        ],
    ):
        with pytest.raises(SystemExit) as exc:
            main()

    assert exc.value.code == 1


@mock.patch("fleet.tasks.apply_virt_workloads.apply_manifest")
@mock.patch("fleet.tasks.apply_virt_workloads.wait_for_csv")
@mock.patch("fleet.tasks.apply_virt_workloads.wait_for_condition")
def test_main_hyperconverged_apply_fails(
    mock_wait_condition, mock_wait_csv, mock_apply
):
    mock_apply.side_effect = [
        True,
        True,
        True,
        False,
    ]  # Everything works except final step
    mock_wait_csv.return_value = True
    mock_wait_condition.return_value = True

    with mock.patch(
        "sys.argv",
        [
            "apply-virt-workloads",
            "--cluster-name",
            "test-cluster",
            "--source-dir",
            "/tmp/test",
            "--spoke-kubeconfig",
            "kubeconfig",
        ],
    ):
        with pytest.raises(SystemExit) as exc:
            main()

    assert exc.value.code == 1


@mock.patch("fleet.tasks.apply_virt_workloads.time.sleep")
@mock.patch("fleet.tasks.apply_virt_workloads.run_with_retry")
def test_wait_for_csv_retry_on_command_failure(mock_retry, mock_sleep):
    mock_retry.side_effect = [
        _fail(stderr="connection refused"),
        _ok(stdout='{"items": []}'),
    ]

    with mock.patch(
        "fleet.tasks.apply_virt_workloads.time.time", side_effect=[0, 5, 610]
    ):
        result = wait_for_csv("test-ns", "nfd", "kubeconfig", timeout=600)

    assert result is False
    # Verify sleep was called after command failure
    mock_sleep.assert_called_with(10)


@mock.patch("fleet.tasks.apply_virt_workloads.time.sleep")
@mock.patch("fleet.tasks.apply_virt_workloads.run_with_retry")
def test_wait_for_condition_json_parse_error(mock_retry, mock_sleep):
    mock_retry.side_effect = [
        _ok(stdout="invalid json that cannot be parsed"),
        _ok(stdout='{"status": {"conditions": []}}'),
    ]

    with mock.patch(
        "fleet.tasks.apply_virt_workloads.time.time", side_effect=[0, 5, 310]
    ):
        result = wait_for_condition(
            "NFD", "nfd-instance", "test-ns", "Available", "kubeconfig", timeout=300
        )

    assert result is False
