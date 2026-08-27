import json
import subprocess
from unittest import mock

import pytest

from fleet.tasks.apply_ai_workloads import (
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


# --- Helper tests (same helpers as virt, but must be covered) ---


@mock.patch("fleet.tasks.apply_ai_workloads.run_with_retry")
def test_apply_manifest_success(mock_retry):
    mock_retry.return_value = _ok(stdout="resource created")
    assert apply_manifest("test.yaml", "kubeconfig") is True


@mock.patch("fleet.tasks.apply_ai_workloads.run_with_retry")
def test_apply_manifest_failure(mock_retry):
    mock_retry.return_value = _fail()
    assert apply_manifest("test.yaml", "kubeconfig") is False


@mock.patch("fleet.tasks.apply_ai_workloads.time.sleep")
@mock.patch("fleet.tasks.apply_ai_workloads.run_with_retry")
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
    assert wait_for_csv("test-ns", "nfd", "kubeconfig") is True


@mock.patch("fleet.tasks.apply_ai_workloads.time.sleep")
@mock.patch("fleet.tasks.apply_ai_workloads.run_with_retry")
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
    assert wait_for_csv("test-ns", "nfd", "kubeconfig") is False


@mock.patch("fleet.tasks.apply_ai_workloads.time.sleep")
@mock.patch("fleet.tasks.apply_ai_workloads.time.time")
@mock.patch("fleet.tasks.apply_ai_workloads.run_with_retry")
def test_wait_for_csv_timeout(mock_retry, mock_time, mock_sleep):
    mock_time.side_effect = [0, 610]
    mock_retry.return_value = _fail()
    assert wait_for_csv("test-ns", "nfd", "kubeconfig", timeout=600) is False


@mock.patch("fleet.tasks.apply_ai_workloads.time.sleep")
@mock.patch("fleet.tasks.apply_ai_workloads.run_with_retry")
def test_wait_for_csv_not_found(mock_retry, mock_sleep):
    csv_response = {"items": []}
    mock_retry.return_value = _ok(stdout=json.dumps(csv_response))
    with mock.patch(
        "fleet.tasks.apply_ai_workloads.time.time", side_effect=[0, 5, 610]
    ):
        assert wait_for_csv("test-ns", "nfd", "kubeconfig", timeout=600) is False


@mock.patch("fleet.tasks.apply_ai_workloads.time.sleep")
@mock.patch("fleet.tasks.apply_ai_workloads.run_with_retry")
def test_wait_for_csv_json_parse_error(mock_retry, mock_sleep):
    mock_retry.side_effect = [
        _ok(stdout="invalid json"),
        _ok(stdout='{"items": []}'),
    ]
    with mock.patch(
        "fleet.tasks.apply_ai_workloads.time.time", side_effect=[0, 5, 610]
    ):
        assert wait_for_csv("test-ns", "nfd", "kubeconfig", timeout=600) is False


@mock.patch("fleet.tasks.apply_ai_workloads.time.sleep")
@mock.patch("fleet.tasks.apply_ai_workloads.run_with_retry")
def test_wait_for_csv_retry_on_command_failure(mock_retry, mock_sleep):
    mock_retry.side_effect = [
        _fail(stderr="connection refused"),
        _ok(stdout='{"items": []}'),
    ]
    with mock.patch(
        "fleet.tasks.apply_ai_workloads.time.time", side_effect=[0, 5, 610]
    ):
        assert wait_for_csv("test-ns", "nfd", "kubeconfig", timeout=600) is False
    mock_sleep.assert_called_with(10)


@mock.patch("fleet.tasks.apply_ai_workloads.time.sleep")
@mock.patch("fleet.tasks.apply_ai_workloads.run_with_retry")
def test_wait_for_condition_success(mock_retry, mock_sleep):
    condition_response = {
        "status": {"conditions": [{"type": "Available", "status": "True"}]}
    }
    mock_retry.return_value = _ok(stdout=json.dumps(condition_response))
    assert (
        wait_for_condition("NFD", "nfd-instance", "test-ns", "Available", "kubeconfig")
        is True
    )


@mock.patch("fleet.tasks.apply_ai_workloads.time.sleep")
@mock.patch("fleet.tasks.apply_ai_workloads.time.time")
@mock.patch("fleet.tasks.apply_ai_workloads.run_with_retry")
def test_wait_for_condition_false_status(mock_retry, mock_time, mock_sleep):
    condition_response = {
        "status": {
            "conditions": [
                {
                    "type": "Available",
                    "status": "False",
                    "reason": "NotReady",
                    "message": "not ready",
                }
            ]
        }
    }
    mock_retry.return_value = _ok(stdout=json.dumps(condition_response))
    mock_time.side_effect = [0, 10, 310]
    assert (
        wait_for_condition(
            "NFD", "nfd-instance", "test-ns", "Available", "kubeconfig", timeout=300
        )
        is False
    )


@mock.patch("fleet.tasks.apply_ai_workloads.time.sleep")
@mock.patch("fleet.tasks.apply_ai_workloads.run_with_retry")
def test_wait_for_condition_resource_not_found(mock_retry, mock_sleep):
    mock_retry.side_effect = [_fail(), _ok(stdout='{"status": {"conditions": []}}')]
    with mock.patch(
        "fleet.tasks.apply_ai_workloads.time.time", side_effect=[0, 5, 310]
    ):
        assert (
            wait_for_condition(
                "NFD", "nfd-instance", "test-ns", "Available", "kubeconfig", timeout=300
            )
            is False
        )


@mock.patch("fleet.tasks.apply_ai_workloads.time.sleep")
@mock.patch("fleet.tasks.apply_ai_workloads.time.time")
@mock.patch("fleet.tasks.apply_ai_workloads.run_with_retry")
def test_wait_for_condition_timeout(mock_retry, mock_time, mock_sleep):
    mock_time.side_effect = [0, 310]
    mock_retry.return_value = _ok(stdout='{"status": {"conditions": []}}')
    assert (
        wait_for_condition(
            "NFD", "nfd-instance", "test-ns", "Available", "kubeconfig", timeout=300
        )
        is False
    )


@mock.patch("fleet.tasks.apply_ai_workloads.time.sleep")
@mock.patch("fleet.tasks.apply_ai_workloads.run_with_retry")
def test_wait_for_condition_json_parse_error(mock_retry, mock_sleep):
    mock_retry.side_effect = [
        _ok(stdout="invalid json"),
        _ok(stdout='{"status": {"conditions": []}}'),
    ]
    with mock.patch(
        "fleet.tasks.apply_ai_workloads.time.time", side_effect=[0, 5, 310]
    ):
        assert (
            wait_for_condition(
                "NFD", "nfd-instance", "test-ns", "Available", "kubeconfig", timeout=300
            )
            is False
        )


# --- main() tests: v3 default ---


_BASE_ARGV = [
    "apply-ai-workloads",
    "--cluster-name",
    "test-cluster",
    "--source-dir",
    "/tmp/test",
    "--spoke-kubeconfig",
    "kubeconfig",
]


@mock.patch("fleet.tasks.apply_ai_workloads.apply_manifest")
@mock.patch("fleet.tasks.apply_ai_workloads.wait_for_csv")
@mock.patch("fleet.tasks.apply_ai_workloads.wait_for_condition")
def test_main_v3_default_success(mock_wait_condition, mock_wait_csv, mock_apply):
    mock_apply.return_value = True
    mock_wait_csv.return_value = True
    mock_wait_condition.return_value = True

    with mock.patch("sys.argv", _BASE_ARGV):
        main()

    apply_calls = [c.args[0] for c in mock_apply.call_args_list]

    # Common operators
    assert "/tmp/test/nfd-subscription.yaml" in apply_calls
    assert "/tmp/test/nfd-operand.yaml" in apply_calls
    assert "/tmp/test/nvidia-gpu-subscription.yaml" in apply_calls
    assert "/tmp/test/nvidia-gpu-cluster-policy.yaml" in apply_calls
    assert "/tmp/test/serverless-subscription.yaml" in apply_calls
    assert "/tmp/test/authorino-subscription.yaml" in apply_calls

    # v3-specific operators
    assert "/tmp/test/v3/cert-manager-subscription.yaml" in apply_calls
    assert "/tmp/test/v3/jobset-subscription.yaml" in apply_calls
    assert "/tmp/test/v3/jobset-operand.yaml" in apply_calls
    assert "/tmp/test/v3/servicemesh-subscription.yaml" in apply_calls

    # v3 OpenShift AI subscription
    assert "/tmp/test/v3/openshift-ai-subscription.yaml" in apply_calls

    # v2 files should NOT be present
    v2_calls = [c for c in apply_calls if "/v2/" in c]
    assert v2_calls == []


# --- main() tests: explicit v2 ---


@mock.patch("fleet.tasks.apply_ai_workloads.apply_manifest")
@mock.patch("fleet.tasks.apply_ai_workloads.wait_for_csv")
@mock.patch("fleet.tasks.apply_ai_workloads.wait_for_condition")
def test_main_v2_success(mock_wait_condition, mock_wait_csv, mock_apply):
    mock_apply.return_value = True
    mock_wait_csv.return_value = True
    mock_wait_condition.return_value = True

    with mock.patch("sys.argv", [*_BASE_ARGV, "--openshift-ai-version", "v2"]):
        main()

    apply_calls = [c.args[0] for c in mock_apply.call_args_list]

    # Common operators
    assert "/tmp/test/nfd-subscription.yaml" in apply_calls
    assert "/tmp/test/nfd-operand.yaml" in apply_calls
    assert "/tmp/test/nvidia-gpu-subscription.yaml" in apply_calls
    assert "/tmp/test/nvidia-gpu-cluster-policy.yaml" in apply_calls
    assert "/tmp/test/serverless-subscription.yaml" in apply_calls
    assert "/tmp/test/authorino-subscription.yaml" in apply_calls

    # v2-specific operators
    assert "/tmp/test/v2/servicemesh-v2-subscription.yaml" in apply_calls

    # v2 OpenShift AI subscription
    assert "/tmp/test/v2/openshift-ai-subscription.yaml" in apply_calls

    # v3 files should NOT be present
    v3_calls = [c for c in apply_calls if "/v3/" in c]
    assert v3_calls == []


@mock.patch("fleet.tasks.apply_ai_workloads.apply_manifest")
@mock.patch("fleet.tasks.apply_ai_workloads.wait_for_csv")
@mock.patch("fleet.tasks.apply_ai_workloads.wait_for_condition")
def test_main_explicit_v3_success(mock_wait_condition, mock_wait_csv, mock_apply):
    mock_apply.return_value = True
    mock_wait_csv.return_value = True
    mock_wait_condition.return_value = True

    with mock.patch("sys.argv", [*_BASE_ARGV, "--openshift-ai-version", "v3"]):
        main()

    apply_calls = [c.args[0] for c in mock_apply.call_args_list]
    assert "/tmp/test/v3/openshift-ai-subscription.yaml" in apply_calls


# --- Failure path tests ---


@mock.patch("fleet.tasks.apply_ai_workloads.apply_manifest")
def test_main_nfd_subscription_fails(mock_apply):
    mock_apply.return_value = False

    with mock.patch("sys.argv", _BASE_ARGV):
        with pytest.raises(SystemExit) as exc:
            main()
    assert exc.value.code == 1


@mock.patch("fleet.tasks.apply_ai_workloads.apply_manifest")
@mock.patch("fleet.tasks.apply_ai_workloads.wait_for_csv")
def test_main_nfd_csv_wait_fails(mock_wait_csv, mock_apply):
    mock_apply.return_value = True
    mock_wait_csv.return_value = False

    with mock.patch("sys.argv", _BASE_ARGV):
        with pytest.raises(SystemExit) as exc:
            main()
    assert exc.value.code == 1


@mock.patch("fleet.tasks.apply_ai_workloads.apply_manifest")
@mock.patch("fleet.tasks.apply_ai_workloads.wait_for_csv")
@mock.patch("fleet.tasks.apply_ai_workloads.wait_for_condition")
def test_main_nfd_operand_apply_fails(mock_wait_condition, mock_wait_csv, mock_apply):
    mock_apply.side_effect = [True, False]
    mock_wait_csv.return_value = True

    with mock.patch("sys.argv", _BASE_ARGV):
        with pytest.raises(SystemExit) as exc:
            main()
    assert exc.value.code == 1


@mock.patch("fleet.tasks.apply_ai_workloads.apply_manifest")
@mock.patch("fleet.tasks.apply_ai_workloads.wait_for_csv")
@mock.patch("fleet.tasks.apply_ai_workloads.wait_for_condition")
def test_main_nfd_condition_wait_fails(mock_wait_condition, mock_wait_csv, mock_apply):
    mock_apply.return_value = True
    mock_wait_csv.return_value = True
    mock_wait_condition.return_value = False

    with mock.patch("sys.argv", _BASE_ARGV):
        with pytest.raises(SystemExit) as exc:
            main()
    assert exc.value.code == 1


@mock.patch("fleet.tasks.apply_ai_workloads.apply_manifest")
@mock.patch("fleet.tasks.apply_ai_workloads.wait_for_csv")
@mock.patch("fleet.tasks.apply_ai_workloads.wait_for_condition")
def test_main_gpu_subscription_fails(mock_wait_condition, mock_wait_csv, mock_apply):
    mock_apply.side_effect = [True, True, False]  # NFD sub, NFD operand, GPU sub fails
    mock_wait_csv.return_value = True
    mock_wait_condition.return_value = True

    with mock.patch("sys.argv", _BASE_ARGV):
        with pytest.raises(SystemExit) as exc:
            main()
    assert exc.value.code == 1


@mock.patch("fleet.tasks.apply_ai_workloads.apply_manifest")
@mock.patch("fleet.tasks.apply_ai_workloads.wait_for_csv")
@mock.patch("fleet.tasks.apply_ai_workloads.wait_for_condition")
def test_main_gpu_csv_fails(mock_wait_condition, mock_wait_csv, mock_apply):
    mock_apply.return_value = True
    mock_wait_csv.side_effect = [True, False]  # NFD CSV ok, GPU CSV fails
    mock_wait_condition.return_value = True

    with mock.patch("sys.argv", _BASE_ARGV):
        with pytest.raises(SystemExit) as exc:
            main()
    assert exc.value.code == 1


@mock.patch("fleet.tasks.apply_ai_workloads.apply_manifest")
@mock.patch("fleet.tasks.apply_ai_workloads.wait_for_csv")
@mock.patch("fleet.tasks.apply_ai_workloads.wait_for_condition")
def test_main_gpu_cluster_policy_fails(mock_wait_condition, mock_wait_csv, mock_apply):
    # NFD sub, NFD operand, GPU sub, GPU cluster policy fails
    mock_apply.side_effect = [True, True, True, False]
    mock_wait_csv.return_value = True
    mock_wait_condition.return_value = True

    with mock.patch("sys.argv", _BASE_ARGV):
        with pytest.raises(SystemExit) as exc:
            main()
    assert exc.value.code == 1


@mock.patch("fleet.tasks.apply_ai_workloads.apply_manifest")
@mock.patch("fleet.tasks.apply_ai_workloads.wait_for_csv")
@mock.patch("fleet.tasks.apply_ai_workloads.wait_for_condition")
def test_main_gpu_condition_fails(mock_wait_condition, mock_wait_csv, mock_apply):
    mock_apply.return_value = True
    mock_wait_csv.return_value = True
    mock_wait_condition.side_effect = [True, False]  # NFD ok, GPU condition fails

    with mock.patch("sys.argv", _BASE_ARGV):
        with pytest.raises(SystemExit) as exc:
            main()
    assert exc.value.code == 1


@mock.patch("fleet.tasks.apply_ai_workloads.apply_manifest")
@mock.patch("fleet.tasks.apply_ai_workloads.wait_for_csv")
@mock.patch("fleet.tasks.apply_ai_workloads.wait_for_condition")
def test_main_serverless_subscription_fails(
    mock_wait_condition, mock_wait_csv, mock_apply
):
    # NFD sub, NFD operand, GPU sub, GPU policy, Serverless fails
    mock_apply.side_effect = [True, True, True, True, False]
    mock_wait_csv.return_value = True
    mock_wait_condition.return_value = True

    with mock.patch("sys.argv", _BASE_ARGV):
        with pytest.raises(SystemExit) as exc:
            main()
    assert exc.value.code == 1


@mock.patch("fleet.tasks.apply_ai_workloads.apply_manifest")
@mock.patch("fleet.tasks.apply_ai_workloads.wait_for_csv")
@mock.patch("fleet.tasks.apply_ai_workloads.wait_for_condition")
def test_main_serverless_csv_fails(mock_wait_condition, mock_wait_csv, mock_apply):
    mock_apply.return_value = True
    # NFD CSV, GPU CSV, Serverless CSV fails
    mock_wait_csv.side_effect = [True, True, False]
    mock_wait_condition.return_value = True

    with mock.patch("sys.argv", _BASE_ARGV):
        with pytest.raises(SystemExit) as exc:
            main()
    assert exc.value.code == 1


@mock.patch("fleet.tasks.apply_ai_workloads.apply_manifest")
@mock.patch("fleet.tasks.apply_ai_workloads.wait_for_csv")
@mock.patch("fleet.tasks.apply_ai_workloads.wait_for_condition")
def test_main_authorino_subscription_fails(
    mock_wait_condition, mock_wait_csv, mock_apply
):
    # NFD sub, NFD operand, GPU sub, GPU policy, Serverless, Authorino fails
    mock_apply.side_effect = [True, True, True, True, True, False]
    mock_wait_csv.return_value = True
    mock_wait_condition.return_value = True

    with mock.patch("sys.argv", _BASE_ARGV):
        with pytest.raises(SystemExit) as exc:
            main()
    assert exc.value.code == 1


@mock.patch("fleet.tasks.apply_ai_workloads.apply_manifest")
@mock.patch("fleet.tasks.apply_ai_workloads.wait_for_csv")
@mock.patch("fleet.tasks.apply_ai_workloads.wait_for_condition")
def test_main_authorino_csv_fails(mock_wait_condition, mock_wait_csv, mock_apply):
    mock_apply.return_value = True
    # NFD, GPU, Serverless, Authorino CSV fails
    mock_wait_csv.side_effect = [True, True, True, False]
    mock_wait_condition.return_value = True

    with mock.patch("sys.argv", _BASE_ARGV):
        with pytest.raises(SystemExit) as exc:
            main()
    assert exc.value.code == 1


# --- v2 version-specific failure tests ---


@mock.patch("fleet.tasks.apply_ai_workloads.apply_manifest")
@mock.patch("fleet.tasks.apply_ai_workloads.wait_for_csv")
@mock.patch("fleet.tasks.apply_ai_workloads.wait_for_condition")
def test_main_v2_servicemesh_subscription_fails(
    mock_wait_condition, mock_wait_csv, mock_apply
):
    # Common: NFD sub, NFD operand, GPU sub, GPU policy, Serverless, Authorino
    # v2-specific: ServiceMesh v2 fails
    mock_apply.side_effect = [True, True, True, True, True, True, False]
    mock_wait_csv.return_value = True
    mock_wait_condition.return_value = True

    with mock.patch("sys.argv", [*_BASE_ARGV, "--openshift-ai-version", "v2"]):
        with pytest.raises(SystemExit) as exc:
            main()
    assert exc.value.code == 1


@mock.patch("fleet.tasks.apply_ai_workloads.apply_manifest")
@mock.patch("fleet.tasks.apply_ai_workloads.wait_for_csv")
@mock.patch("fleet.tasks.apply_ai_workloads.wait_for_condition")
def test_main_v2_servicemesh_csv_fails(mock_wait_condition, mock_wait_csv, mock_apply):
    mock_apply.return_value = True
    # NFD, GPU, Serverless, Authorino CSVs ok, ServiceMesh v2 CSV fails
    mock_wait_csv.side_effect = [True, True, True, True, False]
    mock_wait_condition.return_value = True

    with mock.patch("sys.argv", [*_BASE_ARGV, "--openshift-ai-version", "v2"]):
        with pytest.raises(SystemExit) as exc:
            main()
    assert exc.value.code == 1


@mock.patch("fleet.tasks.apply_ai_workloads.apply_manifest")
@mock.patch("fleet.tasks.apply_ai_workloads.wait_for_csv")
@mock.patch("fleet.tasks.apply_ai_workloads.wait_for_condition")
def test_main_v2_openshift_ai_subscription_fails(
    mock_wait_condition, mock_wait_csv, mock_apply
):
    # All common + v2 ServiceMesh ok, OpenShift AI subscription fails
    mock_apply.side_effect = [True, True, True, True, True, True, True, False]
    mock_wait_csv.return_value = True
    mock_wait_condition.return_value = True

    with mock.patch("sys.argv", [*_BASE_ARGV, "--openshift-ai-version", "v2"]):
        with pytest.raises(SystemExit) as exc:
            main()
    assert exc.value.code == 1


# --- v3 version-specific failure tests ---


@mock.patch("fleet.tasks.apply_ai_workloads.apply_manifest")
@mock.patch("fleet.tasks.apply_ai_workloads.wait_for_csv")
@mock.patch("fleet.tasks.apply_ai_workloads.wait_for_condition")
def test_main_v2_openshift_ai_csv_fails(mock_wait_condition, mock_wait_csv, mock_apply):
    mock_apply.return_value = True
    # NFD, GPU, Serverless, Authorino, ServiceMesh v2 ok; OpenShift AI CSV fails
    mock_wait_csv.side_effect = [True, True, True, True, True, False]
    mock_wait_condition.return_value = True

    with mock.patch("sys.argv", [*_BASE_ARGV, "--openshift-ai-version", "v2"]):
        with pytest.raises(SystemExit) as exc:
            main()
    assert exc.value.code == 1


@mock.patch("fleet.tasks.apply_ai_workloads.apply_manifest")
@mock.patch("fleet.tasks.apply_ai_workloads.wait_for_csv")
@mock.patch("fleet.tasks.apply_ai_workloads.wait_for_condition")
def test_main_v3_certmanager_subscription_fails(
    mock_wait_condition, mock_wait_csv, mock_apply
):
    # Common ok, v3 cert-manager fails
    mock_apply.side_effect = [True, True, True, True, True, True, False]
    mock_wait_csv.return_value = True
    mock_wait_condition.return_value = True

    with mock.patch("sys.argv", [*_BASE_ARGV, "--openshift-ai-version", "v3"]):
        with pytest.raises(SystemExit) as exc:
            main()
    assert exc.value.code == 1


@mock.patch("fleet.tasks.apply_ai_workloads.apply_manifest")
@mock.patch("fleet.tasks.apply_ai_workloads.wait_for_csv")
@mock.patch("fleet.tasks.apply_ai_workloads.wait_for_condition")
def test_main_v3_certmanager_csv_fails(mock_wait_condition, mock_wait_csv, mock_apply):
    mock_apply.return_value = True
    # NFD, GPU, Serverless, Authorino ok; cert-manager CSV fails
    mock_wait_csv.side_effect = [True, True, True, True, False]
    mock_wait_condition.return_value = True

    with mock.patch("sys.argv", [*_BASE_ARGV, "--openshift-ai-version", "v3"]):
        with pytest.raises(SystemExit) as exc:
            main()
    assert exc.value.code == 1


@mock.patch("fleet.tasks.apply_ai_workloads.apply_manifest")
@mock.patch("fleet.tasks.apply_ai_workloads.wait_for_csv")
@mock.patch("fleet.tasks.apply_ai_workloads.wait_for_condition")
def test_main_v3_jobset_subscription_fails(
    mock_wait_condition, mock_wait_csv, mock_apply
):
    # Common ok, v3 cert-manager ok, jobset fails
    mock_apply.side_effect = [True, True, True, True, True, True, True, False]
    mock_wait_csv.return_value = True
    mock_wait_condition.return_value = True

    with mock.patch("sys.argv", [*_BASE_ARGV, "--openshift-ai-version", "v3"]):
        with pytest.raises(SystemExit) as exc:
            main()
    assert exc.value.code == 1


@mock.patch("fleet.tasks.apply_ai_workloads.apply_manifest")
@mock.patch("fleet.tasks.apply_ai_workloads.wait_for_csv")
@mock.patch("fleet.tasks.apply_ai_workloads.wait_for_condition")
def test_main_v3_jobset_csv_fails(mock_wait_condition, mock_wait_csv, mock_apply):
    mock_apply.return_value = True
    # NFD, GPU, Serverless, Authorino, cert-manager ok; jobset CSV fails
    mock_wait_csv.side_effect = [True, True, True, True, True, False]
    mock_wait_condition.return_value = True

    with mock.patch("sys.argv", [*_BASE_ARGV, "--openshift-ai-version", "v3"]):
        with pytest.raises(SystemExit) as exc:
            main()
    assert exc.value.code == 1


@mock.patch("fleet.tasks.apply_ai_workloads.apply_manifest")
@mock.patch("fleet.tasks.apply_ai_workloads.wait_for_csv")
@mock.patch("fleet.tasks.apply_ai_workloads.wait_for_condition")
def test_main_v3_jobset_operand_apply_fails(
    mock_wait_condition, mock_wait_csv, mock_apply
):
    # Common ok, v3 cert-manager ok, jobset sub ok, jobset operand apply fails
    mock_apply.side_effect = [True, True, True, True, True, True, True, True, False]
    mock_wait_csv.return_value = True
    mock_wait_condition.return_value = True

    with mock.patch("sys.argv", [*_BASE_ARGV, "--openshift-ai-version", "v3"]):
        with pytest.raises(SystemExit) as exc:
            main()
    assert exc.value.code == 1


@mock.patch("fleet.tasks.apply_ai_workloads.apply_manifest")
@mock.patch("fleet.tasks.apply_ai_workloads.wait_for_csv")
@mock.patch("fleet.tasks.apply_ai_workloads.wait_for_condition")
def test_main_v3_jobset_operand_condition_fails(
    mock_wait_condition, mock_wait_csv, mock_apply
):
    mock_apply.return_value = True
    mock_wait_csv.return_value = True
    # NFD operand, GPU policy ok; jobset operand condition fails
    mock_wait_condition.side_effect = [True, True, False]

    with mock.patch("sys.argv", [*_BASE_ARGV, "--openshift-ai-version", "v3"]):
        with pytest.raises(SystemExit) as exc:
            main()
    assert exc.value.code == 1


@mock.patch("fleet.tasks.apply_ai_workloads.apply_manifest")
@mock.patch("fleet.tasks.apply_ai_workloads.wait_for_csv")
@mock.patch("fleet.tasks.apply_ai_workloads.wait_for_condition")
def test_main_v3_servicemesh_subscription_fails(
    mock_wait_condition, mock_wait_csv, mock_apply
):
    # Common ok, v3 cert-manager ok, jobset + operand ok, servicemesh v3 fails
    mock_apply.side_effect = [
        True,
        True,
        True,
        True,
        True,
        True,
        True,
        True,
        True,
        False,
    ]
    mock_wait_csv.return_value = True
    mock_wait_condition.return_value = True

    with mock.patch("sys.argv", [*_BASE_ARGV, "--openshift-ai-version", "v3"]):
        with pytest.raises(SystemExit) as exc:
            main()
    assert exc.value.code == 1


@mock.patch("fleet.tasks.apply_ai_workloads.apply_manifest")
@mock.patch("fleet.tasks.apply_ai_workloads.wait_for_csv")
@mock.patch("fleet.tasks.apply_ai_workloads.wait_for_condition")
def test_main_v3_servicemesh_csv_fails(mock_wait_condition, mock_wait_csv, mock_apply):
    mock_apply.return_value = True
    # NFD, GPU, Serverless, Authorino, cert-manager, jobset ok; servicemesh CSV fails
    mock_wait_csv.side_effect = [True, True, True, True, True, True, False]
    mock_wait_condition.return_value = True

    with mock.patch("sys.argv", [*_BASE_ARGV, "--openshift-ai-version", "v3"]):
        with pytest.raises(SystemExit) as exc:
            main()
    assert exc.value.code == 1


@mock.patch("fleet.tasks.apply_ai_workloads.apply_manifest")
@mock.patch("fleet.tasks.apply_ai_workloads.wait_for_csv")
@mock.patch("fleet.tasks.apply_ai_workloads.wait_for_condition")
def test_main_v3_openshift_ai_csv_fails(mock_wait_condition, mock_wait_csv, mock_apply):
    mock_apply.return_value = True
    # All v3 operator CSVs ok, OpenShift AI CSV fails
    mock_wait_csv.side_effect = [True, True, True, True, True, True, True, False]
    mock_wait_condition.return_value = True

    with mock.patch("sys.argv", [*_BASE_ARGV, "--openshift-ai-version", "v3"]):
        with pytest.raises(SystemExit) as exc:
            main()
    assert exc.value.code == 1


@mock.patch("fleet.tasks.apply_ai_workloads.apply_manifest")
@mock.patch("fleet.tasks.apply_ai_workloads.wait_for_csv")
@mock.patch("fleet.tasks.apply_ai_workloads.wait_for_condition")
def test_main_v3_openshift_ai_subscription_fails(
    mock_wait_condition, mock_wait_csv, mock_apply
):
    # All common + v3 operators + operands ok, OpenShift AI subscription fails
    mock_apply.side_effect = [
        True,
        True,
        True,
        True,
        True,
        True,
        True,
        True,
        True,
        True,
        False,
    ]
    mock_wait_csv.return_value = True
    mock_wait_condition.return_value = True

    with mock.patch("sys.argv", [*_BASE_ARGV, "--openshift-ai-version", "v3"]):
        with pytest.raises(SystemExit) as exc:
            main()
    assert exc.value.code == 1
