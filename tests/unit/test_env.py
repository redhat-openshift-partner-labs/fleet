import os

import pytest

from fleet.tasks._env import (
    check_configmap_env,
    env_var_name,
    generic_env_var_name,
    resolve,
    resolve_batch,
    resolve_bool,
    resolve_list,
    resolve_required,
)

# --- env_var_name ---


def test_env_var_name_basic():
    assert env_var_name("register-keycloak-client", "keycloak-url") == (
        "FLEET_REGISTER_KEYCLOAK_CLIENT_KEYCLOAK_URL"
    )


def test_env_var_name_single_word():
    assert env_var_name("validate", "cluster-name") == "FLEET_VALIDATE_CLUSTER_NAME"


# --- generic_env_var_name ---


def test_generic_env_var_name():
    assert generic_env_var_name("keycloak-url") == "FLEET_KEYCLOAK_URL"


def test_generic_env_var_name_single_word():
    assert generic_env_var_name("timeout") == "FLEET_TIMEOUT"


# --- resolve ---


def test_resolve_cli_arg_provided():
    assert resolve("value", "arg", "task") == "value"


def test_resolve_cli_arg_empty_string_falls_through(monkeypatch):
    monkeypatch.setenv("FLEET_TASK_ARG", "from-env")
    assert resolve("", "arg", "task") == "from-env"


def test_resolve_cli_arg_none_falls_through(monkeypatch):
    monkeypatch.setenv("FLEET_TASK_ARG", "from-env")
    assert resolve(None, "arg", "task") == "from-env"


def test_resolve_specific_env_var(monkeypatch):
    monkeypatch.setenv("FLEET_MY_TASK_MY_ARG", "specific")
    assert resolve(None, "my-arg", "my-task") == "specific"


def test_resolve_generic_env_var(monkeypatch):
    monkeypatch.setenv("FLEET_MY_ARG", "generic")
    assert resolve(None, "my-arg", "my-task") == "generic"


def test_resolve_specific_wins_over_generic(monkeypatch):
    monkeypatch.setenv("FLEET_MY_TASK_MY_ARG", "specific")
    monkeypatch.setenv("FLEET_MY_ARG", "generic")
    assert resolve(None, "my-arg", "my-task") == "specific"


def test_resolve_nothing_set():
    assert resolve(None, "missing-arg", "missing-task") is None


def test_resolve_empty_env_var_treated_as_missing(monkeypatch):
    monkeypatch.setenv("FLEET_TASK_ARG", "")
    assert resolve(None, "arg", "task") is None


# --- resolve_required ---


def test_resolve_required_returns_value():
    assert resolve_required("val", "arg", "task") == "val"


def test_resolve_required_from_env(monkeypatch):
    monkeypatch.setenv("FLEET_ARG", "env-val")
    assert resolve_required(None, "arg", "task") == "env-val"


def test_resolve_required_exits_when_missing():
    with pytest.raises(SystemExit, match="1"):
        resolve_required(None, "missing-arg", "missing-task")


# --- resolve_bool ---


def test_resolve_bool_cli_true():
    assert resolve_bool(True, "flag", "task") is True


def test_resolve_bool_cli_false():
    assert resolve_bool(False, "flag", "task") is False


def test_resolve_bool_env_true(monkeypatch):
    monkeypatch.setenv("FLEET_FLAG", "true")
    assert resolve_bool(False, "flag", "task") is True


def test_resolve_bool_env_false(monkeypatch):
    monkeypatch.setenv("FLEET_FLAG", "false")
    assert resolve_bool(False, "flag", "task") is False


def test_resolve_bool_no_env_defaults_false():
    assert resolve_bool(False, "flag", "task") is False


def test_resolve_bool_specific_env_wins(monkeypatch):
    monkeypatch.setenv("FLEET_MY_TASK_INSECURE", "true")
    monkeypatch.setenv("FLEET_INSECURE", "false")
    assert resolve_bool(False, "insecure", "my-task") is True


# --- resolve_list ---


def test_resolve_list_cli_provided():
    assert resolve_list(["a", "b"], "sans", "task") == ["a", "b"]


def test_resolve_list_env_comma_separated(monkeypatch):
    monkeypatch.setenv("FLEET_EXTRA_SANS", "a.com,b.com,c.com")
    assert resolve_list(None, "extra-sans", "task") == ["a.com", "b.com", "c.com"]


def test_resolve_list_env_empty_returns_empty(monkeypatch):
    monkeypatch.setenv("FLEET_EXTRA_SANS", "")
    assert resolve_list(None, "extra-sans", "task") == []


def test_resolve_list_nothing_returns_empty():
    assert resolve_list(None, "extra-sans", "task") == []


def test_resolve_list_empty_cli_list_falls_through(monkeypatch):
    monkeypatch.setenv("FLEET_EXTRA_SANS", "a.com")
    assert resolve_list([], "extra-sans", "task") == ["a.com"]


# --- check_configmap_env ---


def test_check_configmap_env_present(monkeypatch):
    monkeypatch.setenv("FLEET_CONFIGMAP_LOADED", "true")
    check_configmap_env()


def test_check_configmap_env_missing():
    os.environ.pop("FLEET_CONFIGMAP_LOADED", None)
    with pytest.raises(SystemExit, match="1"):
        check_configmap_env()


# --- resolve_batch ---


def _make_ns(**kwargs):
    """Build an argparse.Namespace with given attributes."""
    import argparse

    return argparse.Namespace(**kwargs)


def test_resolve_batch_required_from_cli(monkeypatch):
    monkeypatch.setenv("FLEET_CONFIGMAP_LOADED", "true")
    ns = _make_ns(cluster_name="prod", base_domain="example.com")
    resolve_batch(ns, "my-task", required=["cluster_name", "base_domain"])
    assert ns.cluster_name == "prod"
    assert ns.base_domain == "example.com"


def test_resolve_batch_required_from_env(monkeypatch):
    monkeypatch.setenv("FLEET_CONFIGMAP_LOADED", "true")
    monkeypatch.setenv("FLEET_MY_TASK_CLUSTER_NAME", "env-cluster")
    ns = _make_ns(cluster_name=None)
    resolve_batch(ns, "my-task", required=["cluster_name"])
    assert ns.cluster_name == "env-cluster"


def test_resolve_batch_required_exits_when_missing(monkeypatch):
    monkeypatch.setenv("FLEET_CONFIGMAP_LOADED", "true")
    ns = _make_ns(cluster_name=None)
    with pytest.raises(SystemExit, match="1"):
        resolve_batch(ns, "my-task", required=["cluster_name"])


def test_resolve_batch_optional_from_cli(monkeypatch):
    monkeypatch.setenv("FLEET_CONFIGMAP_LOADED", "true")
    ns = _make_ns(values_file="/tmp/vals.yaml")
    resolve_batch(ns, "my-task", optional=["values_file"])
    assert ns.values_file == "/tmp/vals.yaml"


def test_resolve_batch_optional_missing_is_none(monkeypatch):
    monkeypatch.setenv("FLEET_CONFIGMAP_LOADED", "true")
    ns = _make_ns(values_file=None)
    resolve_batch(ns, "my-task", optional=["values_file"])
    assert ns.values_file is None


def test_resolve_batch_bool_flags(monkeypatch):
    monkeypatch.setenv("FLEET_CONFIGMAP_LOADED", "true")
    ns = _make_ns(insecure=False)
    monkeypatch.setenv("FLEET_MY_TASK_INSECURE", "true")
    resolve_batch(ns, "my-task", bool_flags=["insecure"])
    assert ns.insecure is True


def test_resolve_batch_bool_flags_cli_true(monkeypatch):
    monkeypatch.setenv("FLEET_CONFIGMAP_LOADED", "true")
    ns = _make_ns(insecure=True)
    resolve_batch(ns, "my-task", bool_flags=["insecure"])
    assert ns.insecure is True


def test_resolve_batch_list_args_from_env(monkeypatch):
    monkeypatch.setenv("FLEET_CONFIGMAP_LOADED", "true")
    monkeypatch.setenv("FLEET_MY_TASK_EXTRA_SANS", "a.com,b.com")
    ns = _make_ns(extra_sans=None)
    resolve_batch(ns, "my-task", list_args=["extra_sans"])
    assert ns.extra_sans == ["a.com", "b.com"]


def test_resolve_batch_list_args_from_cli(monkeypatch):
    monkeypatch.setenv("FLEET_CONFIGMAP_LOADED", "true")
    ns = _make_ns(extra_sans=["x.com"])
    resolve_batch(ns, "my-task", list_args=["extra_sans"])
    assert ns.extra_sans == ["x.com"]


def test_resolve_batch_check_configmap_true_by_default():
    os.environ.pop("FLEET_CONFIGMAP_LOADED", None)
    ns = _make_ns(cluster_name="x")
    with pytest.raises(SystemExit, match="1"):
        resolve_batch(ns, "my-task", required=["cluster_name"])


def test_resolve_batch_check_configmap_false(monkeypatch):
    os.environ.pop("FLEET_CONFIGMAP_LOADED", None)
    ns = _make_ns(cluster_name="x")
    resolve_batch(ns, "my-task", required=["cluster_name"], check_configmap=False)
    assert ns.cluster_name == "x"


def test_resolve_batch_field_to_arg_conversion(monkeypatch):
    monkeypatch.setenv("FLEET_CONFIGMAP_LOADED", "true")
    monkeypatch.setenv("FLEET_MY_TASK_KEYCLOAK_ADMIN_SECRET", "sec")
    ns = _make_ns(keycloak_admin_secret=None)
    resolve_batch(ns, "my-task", required=["keycloak_admin_secret"])
    assert ns.keycloak_admin_secret == "sec"


def test_resolve_batch_mixed_categories(monkeypatch):
    monkeypatch.setenv("FLEET_CONFIGMAP_LOADED", "true")
    monkeypatch.setenv("FLEET_MY_TASK_INSECURE", "true")
    monkeypatch.setenv("FLEET_MY_TASK_EXTRA_SANS", "a.com")
    ns = _make_ns(
        cluster_name="prod",
        values_file=None,
        insecure=False,
        extra_sans=None,
    )
    resolve_batch(
        ns,
        "my-task",
        required=["cluster_name"],
        optional=["values_file"],
        bool_flags=["insecure"],
        list_args=["extra_sans"],
    )
    assert ns.cluster_name == "prod"
    assert ns.values_file is None
    assert ns.insecure is True
    assert ns.extra_sans == ["a.com"]


def test_resolve_batch_no_args_is_noop(monkeypatch):
    monkeypatch.setenv("FLEET_CONFIGMAP_LOADED", "true")
    ns = _make_ns()
    resolve_batch(ns, "my-task")
