"""Environment variable resolution for fleet pipeline tasks.

Every argparse argument gets a two-level env var lookup:
  1. Tool-specific: FLEET_{TASK}_{ARG}
  2. Generic fallback: FLEET_{ARG}

Resolution order: CLI arg > tool-specific env > generic env > error (if required).

Usage (each task):
    from fleet.tasks._env import resolve_batch
    resolve_batch(args, "my-task", required=["cluster_name", "base_domain"])
"""

import argparse
import os
import sys

from fleet.tasks._log import error


def env_var_name(task: str, arg: str) -> str:
    t = task.replace("-", "_").upper()
    a = arg.replace("-", "_").upper()
    return f"FLEET_{t}_{a}"


def generic_env_var_name(arg: str) -> str:
    a = arg.replace("-", "_").upper()
    return f"FLEET_{a}"


def _env_lookup(arg_name: str, task_name: str) -> str | None:
    specific = os.environ.get(env_var_name(task_name, arg_name), "")
    if specific:
        return specific
    generic = os.environ.get(generic_env_var_name(arg_name), "")
    if generic:
        return generic
    return None


def check_configmap_env() -> None:
    if not os.environ.get("FLEET_CONFIGMAP_LOADED"):
        error(
            "ConfigMap 'fleet-pipeline-defaults' not loaded. "
            "Ensure it is deployed in the openshift-pipelines namespace "
            "and injected via podTemplate.envFrom."
        )
        sys.exit(1)


def resolve(arg_value: str | None, arg_name: str, task_name: str) -> str | None:
    if arg_value:
        return arg_value
    return _env_lookup(arg_name, task_name)


def resolve_required(arg_value: str | None, arg_name: str, task_name: str) -> str:
    result = resolve(arg_value, arg_name, task_name)
    if not result:
        error(
            f"Required parameter '--{arg_name}' not provided and "
            f"env vars {env_var_name(task_name, arg_name)} / "
            f"{generic_env_var_name(arg_name)} not set."
        )
        sys.exit(1)
    return result


def resolve_bool(arg_value: bool, arg_name: str, task_name: str) -> bool:
    if arg_value:
        return True
    env = _env_lookup(arg_name, task_name)
    if env is not None:
        return env.lower() == "true"
    return False


def resolve_list(
    arg_value: list[str] | None, arg_name: str, task_name: str
) -> list[str]:
    if arg_value:
        return arg_value
    env = _env_lookup(arg_name, task_name)
    if env is not None:
        return [item.strip() for item in env.split(",") if item.strip()]
    return []


def _field_to_arg(field: str) -> str:
    return field.replace("_", "-")


def resolve_batch(  # pylint: disable=too-many-arguments
    args: argparse.Namespace,
    task_name: str,
    *,
    required: list[str] | None = None,
    optional: list[str] | None = None,
    bool_flags: list[str] | None = None,
    list_args: list[str] | None = None,
    check_configmap: bool = True,
) -> None:
    if check_configmap:
        check_configmap_env()
    for field in required or []:
        setattr(
            args,
            field,
            resolve_required(getattr(args, field), _field_to_arg(field), task_name),
        )
    for field in optional or []:
        setattr(
            args,
            field,
            resolve(getattr(args, field), _field_to_arg(field), task_name),
        )
    for field in bool_flags or []:
        setattr(
            args,
            field,
            resolve_bool(getattr(args, field), _field_to_arg(field), task_name),
        )
    for field in list_args or []:
        setattr(
            args,
            field,
            resolve_list(getattr(args, field), _field_to_arg(field), task_name),
        )
