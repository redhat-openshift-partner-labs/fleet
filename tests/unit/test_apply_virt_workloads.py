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

_ARGV = [
    "apply-virt-workloads",
    "--cluster-name",
    "test-cluster",
    "--source-dir",
    "/tmp/test",
    "--spoke-kubeconfig",
    "kubeconfig",
]


def _run_main() -> None:
    with mock.patch("sys.argv", _ARGV):
        main()


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
@mock.patch("fleet.tasks.apply_virt_workloads.check_operator_catalog")
def test_main_success_with_nfd(
    mock_check_catalog, mock_wait_condition, mock_wait_csv, mock_apply
):
    mock_apply.return_value = True
    mock_wait_csv.return_value = True
    mock_wait_condition.return_value = True
    mock_check_catalog.return_value = (True, "available")

    _run_main()

    assert mock_check_catalog.call_args_list == [
        mock.call(
            "kubevirt-hyperconverged", "stable", "redhat-operators", "kubeconfig"
        ),
        mock.call("nfd", "stable", "redhat-operators", "kubeconfig"),
    ]

    # Verify CNV operator installation
    assert mock_apply.call_args_list[0] == mock.call(
        "/tmp/test/cnv-subscription.yaml", "kubeconfig"
    )
    assert mock_wait_csv.call_args_list[0] == mock.call(
        "openshift-cnv", "kubevirt-hyperconverged", "kubeconfig", timeout=900
    )

    # Verify CNV operand creation
    assert mock_apply.call_args_list[1] == mock.call(
        "/tmp/test/hyperconverged.yaml", "kubeconfig"
    )
    assert mock_wait_condition.call_args_list[0] == mock.call(
        "HyperConverged",
        "kubevirt-hyperconverged",
        "openshift-cnv",
        "Available",
        "kubeconfig",
    )

    # Verify optional NFD installation after CNV is healthy
    assert mock_apply.call_args_list[2] == mock.call(
        "/tmp/test/nfd-subscription.yaml", "kubeconfig"
    )
    assert mock_wait_csv.call_args_list[1] == mock.call(
        "openshift-nfd", "nfd", "kubeconfig", timeout=600
    )
    assert mock_apply.call_args_list[3] == mock.call(
        "/tmp/test/nfd-operand.yaml", "kubeconfig"
    )
    assert mock_wait_condition.call_args_list[1] == mock.call(
        "NodeFeatureDiscovery",
        "nfd-instance",
        "openshift-nfd",
        "Available",
        "kubeconfig",
    )


@mock.patch("fleet.tasks.apply_virt_workloads.apply_manifest")
@mock.patch("fleet.tasks.apply_virt_workloads.wait_for_csv")
@mock.patch("fleet.tasks.apply_virt_workloads.wait_for_condition")
@mock.patch("fleet.tasks.apply_virt_workloads.check_operator_catalog")
def test_main_success_without_nfd(
    mock_check_catalog, mock_wait_condition, mock_wait_csv, mock_apply
):
    mock_apply.return_value = True
    mock_wait_csv.return_value = True
    mock_wait_condition.return_value = True
    mock_check_catalog.side_effect = [
        (True, "CNV available"),
        (False, "nfd unavailable"),
    ]

    _run_main()

    assert mock_apply.call_args_list == [
        mock.call("/tmp/test/cnv-subscription.yaml", "kubeconfig"),
        mock.call("/tmp/test/hyperconverged.yaml", "kubeconfig"),
    ]
    assert mock_wait_csv.call_args_list == [
        mock.call("openshift-cnv", "kubevirt-hyperconverged", "kubeconfig", timeout=900)
    ]
    assert mock_wait_condition.call_args_list == [
        mock.call(
            "HyperConverged",
            "kubevirt-hyperconverged",
            "openshift-cnv",
            "Available",
            "kubeconfig",
        )
    ]


@mock.patch("fleet.tasks.apply_virt_workloads.apply_manifest")
@mock.patch("fleet.tasks.apply_virt_workloads.check_operator_catalog")
def test_main_cnv_unavailable_fails_before_apply(mock_check_catalog, mock_apply):
    mock_check_catalog.return_value = (False, "CNV unavailable")

    with pytest.raises(SystemExit) as exc:
        _run_main()

    assert exc.value.code == 1
    mock_apply.assert_not_called()


@mock.patch("fleet.tasks.apply_virt_workloads.apply_manifest")
@mock.patch("fleet.tasks.apply_virt_workloads.wait_for_csv")
@mock.patch("fleet.tasks.apply_virt_workloads.wait_for_condition")
@mock.patch("fleet.tasks.apply_virt_workloads.check_operator_catalog")
def test_main_nfd_subscription_failure_does_not_block_cnv(
    mock_check_catalog, mock_wait_condition, mock_wait_csv, mock_apply
):
    mock_apply.side_effect = [True, True, False]
    mock_wait_csv.return_value = True
    mock_wait_condition.return_value = True
    mock_check_catalog.return_value = (True, "available")

    _run_main()

    assert mock_apply.call_args_list[-1] == mock.call(
        "/tmp/test/nfd-subscription.yaml", "kubeconfig"
    )


@pytest.mark.parametrize(
    ("apply_values", "wait_csv_values"),
    [
        ([True, True, True], [True, False]),
        ([True, True, True, False], [True, True]),
    ],
    ids=["csv", "operand"],
)
@mock.patch("fleet.tasks.apply_virt_workloads.apply_manifest")
@mock.patch("fleet.tasks.apply_virt_workloads.wait_for_csv")
@mock.patch("fleet.tasks.apply_virt_workloads.wait_for_condition")
@mock.patch("fleet.tasks.apply_virt_workloads.check_operator_catalog")
def test_main_nfd_installation_failure_does_not_block_cnv(
    mock_check_catalog,
    mock_wait_condition,
    mock_wait_csv,
    mock_apply,
    apply_values,
    wait_csv_values,
):
    mock_apply.side_effect = apply_values
    mock_wait_csv.side_effect = wait_csv_values
    mock_wait_condition.return_value = True
    mock_check_catalog.return_value = (True, "available")

    _run_main()


@pytest.mark.parametrize(
    "failure_case",
    [
        ([True, True], True, False),
        ([False], True, True),
        ([True], False, True),
        ([True, False], True, True),
    ],
    ids=["condition", "subscription", "csv", "operand"],
)
@mock.patch("fleet.tasks.apply_virt_workloads.apply_manifest")
@mock.patch("fleet.tasks.apply_virt_workloads.wait_for_csv")
@mock.patch("fleet.tasks.apply_virt_workloads.wait_for_condition")
@mock.patch("fleet.tasks.apply_virt_workloads.check_operator_catalog")
def test_main_cnv_failure_exits(
    mock_check_catalog,
    mock_wait_condition,
    mock_wait_csv,
    mock_apply,
    failure_case,
):
    apply_values, wait_csv_value, wait_condition_value = failure_case
    mock_apply.side_effect = apply_values
    mock_wait_csv.return_value = wait_csv_value
    mock_wait_condition.return_value = wait_condition_value
    mock_check_catalog.side_effect = [
        (True, "CNV available"),
        (False, "nfd unavailable"),
    ]

    with pytest.raises(SystemExit) as exc:
        _run_main()

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
