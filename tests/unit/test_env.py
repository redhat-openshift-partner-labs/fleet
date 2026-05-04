import os

import pytest

from fleet.tasks._env import (
    check_configmap_env,
    env_var_name,
    generic_env_var_name,
    resolve,
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
