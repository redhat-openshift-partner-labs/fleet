"""Catalog checks for operators before their subscriptions are applied."""

import json

from fleet._retry import run_with_retry


def check_operator_catalog(
    package_name: str,
    channel: str,
    source: str,
    kubeconfig: str,
) -> tuple[bool, str]:
    """Check that an operator package is available from the expected catalog."""
    result = run_with_retry(
        [
            "oc",
            "get",
            "packagemanifest",
            package_name,
            "-n",
            "openshift-marketplace",
            "-o",
            "json",
            f"--kubeconfig={kubeconfig}",
        ],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        return False, f"failed to query {package_name}: {result.stderr.strip()}"

    try:
        manifest = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        return False, f"failed to parse {package_name} PackageManifest: {exc}"

    status = manifest.get("status", {})
    catalog_source = status.get("catalogSource", "unknown")
    catalog_source_namespace = status.get("catalogSourceNamespace", "unknown")

    if catalog_source != source:
        return (
            False,
            f"{package_name} is available from {catalog_source}, expected {source}",
        )

    if catalog_source_namespace != "openshift-marketplace":
        return (
            False,
            f"{package_name} is available from {catalog_source_namespace}, "
            "expected openshift-marketplace",
        )

    channels = status.get("channels", [])
    matching_channel = next(
        (entry for entry in channels if entry.get("name") == channel), None
    )
    if matching_channel is None:
        return False, f"{package_name} does not provide channel {channel}"

    if not matching_channel.get("currentCSV"):
        return (
            False,
            f"{package_name} channel {channel} has no current ClusterServiceVersion",
        )

    return True, f"{package_name} {channel} is available from {source}"
