"""Lay out docs/diagrams/architecture.svg.

Usage:
    python docs/diagrams/layout_architecture.py           # write the SVG
    python docs/diagrams/layout_architecture.py --check   # exit 1 if it differs

The content source is architecture.mermaid. drawing.py holds the drawing
helpers and supplies the shared <style> and <defs> blocks.
"""

import argparse
from pathlib import Path

from drawing import DIAGRAMS, Drawing, emit, shared_head

SVG = DIAGRAMS / "architecture.svg"

H = 1612

# Hub and spoke grid: four card columns with a 58 px line channel between them.
C = (84, 358, 632, 906)  # card x per column
CW = 216  # card width
XG = 46  # left channel: Git to the ArgoCD Application
XA, XB, XC, XD = 1154, 1170, 1186, 1202  # right channel: post-provision to the spoke

GIT_Y, GIT_CARD_Y = 238, 264
GIT_CARD_BOTTOM = GIT_CARD_Y + 118
GIT_BOTTOM = GIT_Y + 162
BAND = GIT_BOTTOM + 34  # label baseline between the Git and hub frames
HUB_Y, HUB_BOTTOM = 456, 1174
TEK_Y, TEK_BOTTOM = 490, 802
EL_Y = 516
EL_BOTTOM = EL_Y + 80
PIPE_Y = 672
PIPE_BOTTOM = PIPE_Y + 114
ROW_D = 880  # Crossplane, Hive and ACM, cert-manager
ROW_E = 1024  # Keycloak
ROW_F = 1070  # ArgoCD Application
SPOKE_Y, SPOKE_CARD_Y = 1364, 1390

DESC = (
    "Git is the source of truth. The fleet-clusters repository holds provision/NAME/ with "
    "the cluster overlays and metadata.yaml, and deprovision/NAME-archive sentinel files. "
    "The fleet repository holds tekton/ and workloads/TIER/ (pipelines, tasks, triggers and "
    "tier overlays) and hub-config/ and bootstrap/ (hub operators and their configuration). "
    "The hub cluster is trusted. ArgoCD syncs Git to the Application fleet-hub-config. "
    "Tekton is the workflow engine. A push to fleet-clusters reaches the EventListener "
    "fleet-cluster-lifecycle through a webhook. A push that adds provision/NAME/ starts the "
    "pre-provision pipeline, a push that adds deprovision/NAME-archive starts the "
    "deprovision pipeline, and a request whose body holds action: post-provision starts the "
    "post-provision pipeline. The pipelines clone Git with the git-clone task. "
    "The pre-provision pipeline creates the namespace, SSH key, pull secret and IAM "
    "credentials and checks the inputs: it applies IAM CRs to Crossplane, which holds the "
    "IAM users, roles and policies of each cluster, waits for the keys, and starts the "
    "provision pipeline. The provision pipeline applies the cluster CRs to Hive and ACM "
    "(ClusterDeployment, ManagedCluster with the tier label), waits for the install and the "
    "ACM join, and starts the post-provision pipeline. Hive installs the cluster. "
    "The post-provision pipeline creates a ClusterIssuer and a Certificate in cert-manager, "
    "which holds one ClusterIssuer per cluster for Let's Encrypt DNS-01 through Route53, "
    "registers an OIDC client per cluster in Keycloak, and writes to the spoke: the leaf "
    "certificate and key, the OAuth CR and provider Secrets, the cluster-admins group and "
    "binding, and the kustomize overlays of the tier. "
    "The deprovision pipeline deletes the cluster CRs, waits for the uninstall, deletes the "
    "IAM CRs, and posts a deployment status to fleet-clusters. "
    "The spoke is third-party accessible. It holds the ingress certificate (leaf "
    "certificate and key, no CA key), OAuth with htpasswd and OpenID providers, RBAC with "
    "the cluster-admins group, and the tier workloads (base, virt, ai, coco). "
    "Constraints: Tekton, ArgoCD, ACM, Hive, Crossplane, cert-manager and Keycloak run on "
    "the hub. The spoke receives only artifacts derived on the hub. Triggers are pushes to "
    "main of fleet-clusters; [skip-provision] or [skip-deprovision] in the commit message "
    "skips the run."
)


def render(head: str) -> str:
    """Return the SVG text; head is the <style>...</defs> block."""
    d = Drawing()
    d.begin(
        H,
        "Architecture",
        DESC,
        head,
        "A push to fleet-clusters starts Tekton pipelines on the hub; the pipelines drive "
        "Crossplane, Hive, cert-manager, Keycloak and the spoke.",
    )

    d.constraints(
        [
            (
                "Hub",
                "m b",
                "Tekton, ArgoCD, ACM, Hive, Crossplane, cert-manager and Keycloak run on the hub",
            ),
            (
                "Spoke",
                "m b",
                "third-party accessible; it receives only artifacts derived on the hub",
            ),
            (
                "Triggers",
                "m b",
                "pushes to main of fleet-clusters; [skip-provision] or [skip-deprovision] "
                "in the commit message skips the run",
            ),
        ],
        160,
    )

    # Each pill sits where no edge crosses the top edge of its frame.
    d.section("Frames")
    d.frame(False, 24, GIT_Y, 1214, 162, 40, "GIT · SOURCE OF TRUTH")
    d.frame(False, 24, HUB_Y, 1214, HUB_BOTTOM - HUB_Y, 560, "HUB CLUSTER · TRUSTED")
    d.frame(False, 24, SPOKE_Y, 1214, 142, 496, "SPOKE · THIRD-PARTY ACCESSIBLE")
    d.frame(True, 68, TEK_Y, 1070, TEK_BOTTOM - TEK_Y, 600, "TEKTON · WORKFLOW ENGINE")

    d.section("Cards: Git")
    d.card(
        "store",
        40,
        GIT_CARD_Y,
        366,
        118,
        "fleet-clusters",
        [
            ("c s", "provision/NAME/ · deprovision/NAME-archive"),
            ("t b", "cluster overlays · metadata.yaml"),
        ],
    )
    d.card(
        "store",
        448,
        GIT_CARD_Y,
        366,
        118,
        "fleet: pipelines and workloads",
        [
            ("c s", "tekton/ · workloads/TIER/"),
            ("t b", "pipelines, tasks, triggers, tier overlays"),
        ],
    )
    d.card(
        "store",
        856,
        GIT_CARD_Y,
        366,
        118,
        "fleet: hub configuration",
        [
            ("c s", "hub-config/ · bootstrap/"),
            ("t b", "hub operators and their configuration"),
        ],
    )

    d.section("Cards: Tekton")
    d.card(
        "gate",
        C[1],
        EL_Y,
        C[3] + CW - C[1],
        80,
        "EventListener",
        [("c s", "fleet-cluster-lifecycle")],
    )
    d.card(
        "src",
        C[0],
        PIPE_Y,
        CW,
        114,
        "deprovision",
        [("m s", "deletes the cluster and"), ("m s", "its hub artifacts")],
    )
    d.card(
        "src",
        C[1],
        PIPE_Y,
        CW,
        114,
        "pre-provision",
        [
            ("m s", "namespace, SSH key, pull secret,"),
            ("m s", "IAM credentials, input checks"),
        ],
    )
    d.card(
        "src",
        C[2],
        PIPE_Y,
        CW,
        114,
        "provision",
        [("m s", "applies cluster CRs, waits for"), ("m s", "install and ACM join")],
    )
    d.card(
        "src",
        C[3],
        PIPE_Y,
        CW,
        114,
        "post-provision",
        [("m s", "OAuth, TLS, RBAC, tier"), ("m s", "workloads, access details")],
    )

    d.section("Cards: hub services")
    d.card(
        "src",
        C[1],
        ROW_D,
        CW,
        100,
        "Crossplane",
        [("t b", "IAM users, roles and"), ("t b", "policies per cluster")],
    )
    d.card(
        "core",
        C[2],
        ROW_D,
        CW,
        100,
        "Hive and ACM",
        [("c s", "ClusterDeployment"), ("c s", "ManagedCluster · tier label")],
    )
    d.card(
        "src",
        C[3],
        ROW_D,
        CW,
        100,
        "cert-manager",
        [
            ("t b", "ClusterIssuer per cluster"),
            ("m s", "Let's Encrypt DNS-01, Route53"),
        ],
    )
    d.card(
        "src",
        C[3],
        ROW_E,
        CW,
        100,
        "Keycloak",
        [("t b", "OIDC client per cluster")],
    )
    d.card(
        "src",
        C[0],
        ROW_F,
        CW,
        80,
        "ArgoCD Application",
        [("c s", "fleet-hub-config")],
    )

    d.section("Cards: Spoke")
    d.card(
        "store",
        C[0],
        SPOKE_CARD_Y,
        CW,
        100,
        "Ingress certificate",
        [("t b", "leaf certificate and key"), ("m s", "no CA key")],
    )
    d.card(
        "core",
        C[1],
        SPOKE_CARD_Y,
        CW,
        100,
        "OAuth",
        [("t b", "htpasswd and OpenID providers")],
    )
    d.card(
        "core",
        C[2],
        SPOKE_CARD_Y,
        CW,
        100,
        "RBAC",
        [("c s", "cluster-admins"), ("t b", "group")],
    )
    d.card(
        "out",
        C[3],
        SPOKE_CARD_Y,
        CW,
        100,
        "Tier workloads",
        [("t b", "base · virt · ai · coco")],
    )

    # Every path ends 2 px before its target so the arrow tip touches the border.
    d.section("Edges: Git and hub")
    d.edge("flow", f"M{XG} {GIT_BOTTOM} V{ROW_F + 40} H{C[0] - 2}")
    d.label(XG + 8, BAND, "ArgoCD sync")
    d.edge("flow", f"M160 {PIPE_Y} V{GIT_CARD_BOTTOM + 2}")
    d.label(168, BAND, "deployment status")
    d.edge("flow", f"M390 {GIT_CARD_BOTTOM} V{EL_Y - 2}")
    d.label(398, BAND, "push webhook")
    d.edge("flow", f"M980 {GIT_BOTTOM} V{TEK_Y - 2}")
    d.label(988, BAND, "cloned by git-clone")

    d.section("Edges: EventListener to pipelines, pipeline chain")
    d.edge("flow", f"M{C[1]} {EL_Y + 40} H230 V{PIPE_Y - 2}")
    d.label(238, 630, "push adds", "deprovision/NAME-archive")
    d.edge("flow", f"M466 {EL_BOTTOM} V{PIPE_Y - 2}")
    d.label(474, 630, "push adds", "provision/NAME/")
    d.edge("flow", f"M1014 {EL_BOTTOM} V{PIPE_Y - 2}")
    d.label(1006, 630, "request body", "action: post-provision", anchor="end")
    d.edge("flow", f"M{C[1] + CW} {PIPE_Y + 57} H{C[2] - 2}")
    d.label(603, PIPE_Y + 50, "starts", anchor="middle")
    d.edge("flow", f"M{C[2] + CW} {PIPE_Y + 57} H{C[3] - 2}")
    d.label(877, PIPE_Y + 50, "starts", anchor="middle")

    d.section("Edges: pre-provision, provision")
    d.edge("flow", f"M420 {PIPE_BOTTOM} V{ROW_D - 2}")
    d.label(412, 846, "applies IAM CRs", anchor="end")
    d.edge("ctl", f"M500 {PIPE_BOTTOM} V{ROW_D - 2}")
    d.label(508, 846, "waits for keys")
    d.edge("flow", f"M694 {PIPE_BOTTOM} V{ROW_D - 2}")
    d.label(686, 846, "applies CRs", anchor="end")
    d.edge("ctl", f"M774 {PIPE_BOTTOM} V{ROW_D - 2}")
    d.label(782, 838, "waits for install", "and ACM join")

    # The Keycloak line passes cert-manager through the channel left of column 4.
    d.section("Edges: post-provision to hub services")
    d.edge("flow", f"M1014 {PIPE_BOTTOM} V{ROW_D - 2}")
    d.label(1022, 838, "ClusterIssuer,", "Certificate")
    d.edge("flow", f"M930 {PIPE_BOTTOM} V864 H877 V{ROW_E + 50} H{C[3] - 2}")
    d.label(885, 1006, "registers OIDC client")

    # The two Hive lines run below Crossplane. The lower line takes the right
    # vertical and the lower entry so the two do not cross.
    d.section("Edges: deprovision")
    d.edge("flow", f"M220 {PIPE_BOTTOM} V{ROW_D + 50} H{C[1] - 2}")
    d.label(228, ROW_D + 43, "deletes IAM CRs")
    d.edge("flow", f"M160 {PIPE_BOTTOM} V1004 H594 V{ROW_D + 30} H{C[2] - 2}")
    d.label(240, 997, "deletes cluster CRs")
    d.edge("ctl", f"M120 {PIPE_BOTTOM} V1032 H612 V{ROW_D + 70} H{C[2] - 2}")
    d.label(240, 1025, "waits for uninstall")

    # Hive to Spoke ends on the frame edge, left of the first spoke card.
    d.section("Edges: Hive to spoke")
    d.edge("flow", f"M740 {ROW_D + 100} V1200 H54 V{SPOKE_Y - 2}")
    d.label(62, 1290, "installs the cluster")

    # Post-provision leaves the card's right side; the topmost exit takes the
    # outermost channel line so the four lines do not cross.
    d.section("Edges: post-provision to spoke")
    right = C[3] + CW
    d.edge("flow", f"M{right} {PIPE_Y + 90} H{XA} V1226 H250 V{SPOKE_CARD_Y - 2}")
    d.label(258, 1330, "leaf certificate", "and key")
    d.edge("flow", f"M{right} {PIPE_Y + 68} H{XB} V1252 H478 V{SPOKE_CARD_Y - 2}")
    d.label(486, 1330, "OAuth CR,", "provider Secrets")
    d.edge("flow", f"M{right} {PIPE_Y + 46} H{XC} V1278 H784 V{SPOKE_CARD_Y - 2}")
    d.label(792, 1330, "group and", "binding")
    d.edge("flow", f"M{right} {PIPE_Y + 24} H{XD} V1304 H1040 V{SPOKE_CARD_Y - 2}")
    d.label(1048, 1330, "kustomize", "overlays")

    d.legend(
        H,
        [(40, "flow", "applies, starts, writes"), (222, "ctl", "waits")],
        [
            (390, "gate", "event entry"),
            (512, "src", "pipelines and operators"),
            (708, "core", "cluster control"),
            (857, "store", "git and key material"),
            (1035, "out", "workloads"),
        ],
    )
    return d.end()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check", action="store_true", help="exit 1 if the SVG differs; write nothing"
    )
    args = parser.parse_args()
    emit(SVG, render(shared_head()), args.check, Path(__file__).name)


if __name__ == "__main__":
    main()
