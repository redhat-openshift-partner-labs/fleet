"""Create a PrivateBin paste containing spoke cluster access details.

CLI: fleet-create-access-paste --cluster-name NAME --base-domain DOMAIN
    --kubeconfig-file PATH --privatebin-url URL
Reads the kubeadmin password from Hive, renders a Markdown paste, uploads it
through PrivateBin, and stores the paste URL and password in a Hub Secret.
"""

import argparse
import base64
import json
import secrets
import subprocess
import sys
import tempfile
from pathlib import Path

from fleet.tasks._log import configure, error, info


def generate_password(length: int = 32) -> str:
    """Generate a password equivalent to `pwgen 32 1 -Bcn`."""
    lowercase = "abcdefghjkmnpqrstuvwxyz"
    uppercase = "ABCDEFGHJKMNPQRSTUVWXYZ"
    digits = "23456789"
    allowed = lowercase + uppercase + digits

    while True:
        password = "".join(secrets.choice(allowed) for _ in range(length))
        if any(char in uppercase for char in password) and any(
            char in digits for char in password
        ):
            return password


def render_markdown(
    cluster_name: str,
    base_domain: str,
    kubeadmin_password: str,
    kubeconfig: str,
) -> str:
    """Render the PrivateBin Markdown payload."""
    console_url = f"https://console-openshift-console.apps.{cluster_name}.{base_domain}"
    return (
        "## CONSOLE  \n"
        f"URL: {console_url}  \n"
        "USERNAME: kubeadmin  \n"
        f"PASSWORD: {kubeadmin_password}  \n"
        "\n"
        "## KUBECONFIG  \n"
        "```yaml\n"
        f"{kubeconfig}"
        "```\n"
    )


def _run(command: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(command, capture_output=True, text=True, **kwargs)


def _read_kubeadmin_password(cluster_name: str) -> str:
    secret_ref = _run(
        [
            "oc",
            "get",
            "clusterdeployment",
            cluster_name,
            "-n",
            cluster_name,
            "-o",
            "jsonpath={.spec.clusterMetadata.adminPasswordSecretRef.name}",
        ]
    )
    if secret_ref.returncode != 0 or not secret_ref.stdout.strip():
        error(f"Failed to read kubeadmin password secret reference for {cluster_name}")
        sys.exit(1)

    secret_name = secret_ref.stdout.strip()
    password_result = _run(
        [
            "oc",
            "get",
            "secret",
            secret_name,
            "-n",
            cluster_name,
            "-o",
            "jsonpath={.data.password}",
        ]
    )
    if password_result.returncode != 0 or not password_result.stdout.strip():
        error("Failed to read kubeadmin password from Hub Secret")
        sys.exit(1)

    try:
        return base64.b64decode(password_result.stdout.strip(), validate=True).decode(
            "utf-8"
        )
    except (ValueError, UnicodeDecodeError):
        error("Kubeadmin password is not valid base64-encoded UTF-8")
        sys.exit(1)


def _create_privatebin_paste(
    content: str,
    paste_password: str,
    privatebin_url: str,
    expire: str,
) -> dict:
    with tempfile.TemporaryDirectory(prefix="fleet-access-paste-") as temp_dir:
        paste_path = Path(temp_dir) / "access.md"
        config_path = Path(temp_dir) / "privatebin.json"
        paste_path.write_text(content, encoding="utf-8")
        config_path.write_text(
            json.dumps(
                {
                    "bin": [{"host": privatebin_url, "name": ""}],
                    "expire": expire,
                    "formatter": "markdown",
                    "gzip": True,
                }
            ),
            encoding="utf-8",
        )

        result = _run(
            [
                "privatebin",
                "--config",
                str(config_path),
                "create",
                "--filename",
                str(paste_path),
                "--password",
                paste_password,
                "--expire",
                expire,
                "--formatter",
                "markdown",
                "--gzip",
                "--output",
                "json",
            ]
        )

    if result.returncode != 0:
        error(f"Failed to create PrivateBin paste: {result.stderr.strip()}")
        sys.exit(1)

    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        error("PrivateBin returned invalid JSON")
        sys.exit(1)


def _save_paste_secret(
    cluster_name: str,
    paste_url: str,
    paste_password: str,
    namespace: str,
) -> None:
    secret_yaml = (
        "apiVersion: v1\n"
        "kind: Secret\n"
        "metadata:\n"
        f"  name: {cluster_name}-access-paste\n"
        f"  namespace: {namespace}\n"
        "type: Opaque\n"
        "stringData:\n"
        f"  url: {paste_url}\n"
        f"  password: {paste_password}\n"
    )
    result = _run(["oc", "apply", "-f", "-"], input=secret_yaml)
    if result.returncode != 0:
        error("Failed to save PrivateBin paste Secret")
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cluster-name", required=True)
    parser.add_argument("--base-domain", required=True)
    parser.add_argument("--kubeconfig-file", required=True)
    parser.add_argument("--privatebin-url", required=True)
    parser.add_argument("--expire", default="1week")
    parser.add_argument("--namespace", default="openshift-pipelines")
    args = parser.parse_args()

    configure("create-access-paste")

    info("=== Creating cluster access paste ===")
    info(f"  cluster-name={args.cluster_name}")
    info(f"  base-domain={args.base_domain}")
    info(f"  privatebin-url={args.privatebin_url}")
    info(f"  expire={args.expire}")
    info(f"  namespace={args.namespace}")

    kubeadmin_password = _read_kubeadmin_password(args.cluster_name)
    info("  -> kubeadmin password read")

    try:
        kubeconfig = Path(args.kubeconfig_file).read_text(encoding="utf-8")
    except OSError:
        error(f"Kubeconfig file not found: {args.kubeconfig_file}")
        sys.exit(1)
    info(f"  -> kubeconfig read ({len(kubeconfig)} bytes)")

    paste_password = generate_password()
    markdown = render_markdown(
        args.cluster_name,
        args.base_domain,
        kubeadmin_password,
        kubeconfig,
    )
    info(f"  -> Markdown rendered ({len(markdown)} bytes)")

    paste = _create_privatebin_paste(
        markdown,
        paste_password,
        args.privatebin_url,
        args.expire,
    )
    paste_url = paste.get("paste_url")
    if not paste_url:
        error("PrivateBin response did not include paste_url")
        sys.exit(1)
    info("  -> PrivateBin paste created")

    _save_paste_secret(
        args.cluster_name,
        paste_url,
        paste_password,
        args.namespace,
    )
    info(f"Access paste saved to Secret {args.cluster_name}-access-paste")
