"""Catalog checks for operators before their subscriptions are applied."""

import json
from typing import Any

from fleet._retry import run_with_retry


def _select_package_manifest(
    response: dict[str, Any], package_name: str, source: str
) -> tuple[dict[str, Any] | None, str | None]:
    package_manifests = [
        manifest
        for manifest in response.get("items", [])
        if manifest.get("status", {}).get("packageName") == package_name
    ]
    if not package_manifests:
        return None, f"{package_name} is not available from any catalog"

    manifest = next(
        (
            manifest
            for manifest in package_manifests
            if manifest.get("status", {}).get("catalogSource") == source
        ),
        None,
    )
    if manifest is None:
        sources = ", ".join(
            sorted(
                {
                    manifest.get("status", {}).get("catalogSource", "unknown")
                    for manifest in package_manifests
                }
            )
        )
        return None, f"{package_name} is available from {sources}, expected {source}"

    return manifest, None


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
        response = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        return False, f"failed to parse {package_name} PackageManifest: {exc}"

    manifest, selection_error = _select_package_manifest(response, package_name, source)
    if manifest is None:
        return False, selection_error or "failed to select a PackageManifest"

    status = manifest.get("status", {})
    catalog_source_namespace = status.get("catalogSourceNamespace", "unknown")

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


def channel_related_images(
    package_name: str, channel: str, source: str, kubeconfig: str
) -> list[str]:
    """currentCSVDesc.relatedImages of the channel; ValueError with the reason when unavailable."""
    result = run_with_retry(
        [
            "oc",
            "get",
            "packagemanifest",
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
        raise ValueError(f"failed to query {package_name}: {result.stderr.strip()}")

    try:
        response = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"failed to parse {package_name} PackageManifest: {exc}"
        ) from exc

    manifest, selection_error = _select_package_manifest(response, package_name, source)
    if manifest is None:
        raise ValueError(selection_error)

    channels = manifest.get("status", {}).get("channels", [])
    matching_channel = next(
        (entry for entry in channels if entry.get("name") == channel), None
    )
    if matching_channel is None:
        raise ValueError(f"{package_name} does not provide channel {channel}")

    # The catalog lists the pull specs of the channel's current CSV.
    images = (matching_channel.get("currentCSVDesc") or {}).get("relatedImages")
    if not images:
        raise ValueError(f"{package_name} channel {channel} lists no related images")

    return [str(image) for image in images]
