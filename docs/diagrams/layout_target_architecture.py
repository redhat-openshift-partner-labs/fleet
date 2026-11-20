"""Lay out docs/diagrams/target-architecture.svg.

Usage:
    python docs/diagrams/layout_target_architecture.py           # write the SVG
    python docs/diagrams/layout_target_architecture.py --check   # exit 1 if it differs

The content source is target-architecture.mermaid. drawing.py holds the
drawing helpers and supplies the shared <style> and <defs> blocks.
"""

import argparse
from pathlib import Path

from drawing import DIAGRAMS, Drawing, emit, shared_head

SVG = DIAGRAMS / "target-architecture.svg"

H = 1658

# Hub grid: three card columns, one line channel on each side.
C1, C2, C3 = 84, 529, 866  # card x per column
CW12, CW3 = 263, 256  # card widths
F1, F2, F3 = 68, 513, 850  # nested frame x per column
FW12, FW3 = 295, 288  # nested frame widths
XG = 46  # left channel: Git to the hub-config Application
XP, X1, X2, X3 = 1154, 1170, 1186, 1202  # right channel: post-provision lines
XA, XH = 379, 497  # verticals between columns 1 and 2

GIT_Y, GIT_CARD_Y = 206, 232
HUB_Y, HUB_BOTTOM = 424, 1306
TEK_Y, EL_Y, PIPE_Y = 458, 484, 640
ROW_D_F, ROW_D = 868, 894  # Crossplane, Hive, cert-manager
ROW_E_F, ROW_E = 1040, 1066  # ApplicationSet, Placement
ROW_F = 1192  # hub-config Application
SPOKE_Y, SPOKE_CARD_Y = 1420, 1446

GIT_BOTTOM = GIT_Y + 162
EL_BOTTOM = EL_Y + 80
PIPE_BOTTOM = PIPE_Y + 96
Q_RIGHT = C3 + CW3

DESC = (
    "Git is the source of truth. It holds hub-config (ACM, Tekton, cert-manager), "
    "the fleet-clusters repository with provision/NAME/ (ClusterDeployment, MachinePool, "
    "install-config, tier label), tekton/pipelines (provision, post-provision, deprovision), "
    "and workloads/TIER (day-2 manifests). "
    "The hub cluster is trusted. Inside it, Tekton is the workflow engine: an EventListener "
    "receives the git webhook on commit and triggers the provision and post-provision "
    "pipelines by path and the deprovision pipeline on a deletion PR. Git is also read by "
    "the provision pipeline during the run, and ArgoCD syncs Git to the hub-config "
    "Application, which delivers Tekton, ACM and cert-manager. ArgoCD is used for manifest "
    "delivery only. "
    "The provision pipeline applies Crossplane CRs for AWS IAM user generation, which "
    "produces per-cluster credentials and generates AWS creds for the Hive controller. "
    "The provision pipeline applies cluster CRs to Hive and waits for ready. Hive provisions "
    "the spoke through the cloud API. "
    "The post-provision pipeline, for tiers base, virt, ai and coco, requests a cert on the "
    "hub from cert-manager (ClusterIssuer internal-ca) in the hub-only secret authority, "
    "derives and pushes the leaf cert and key only to the spoke, applies tier manifests "
    "through the spoke kubeconfig, configures the IDP, and labels the spoke "
    "bootstrapped=true on the Placement / ManagedCluster in ACM / Hive. The Placement feeds "
    "the ACM cluster generator of the ApplicationSet, which delivers day-2 workloads to the "
    "spoke. "
    "The deprovision pipeline deletes the cluster CRs, waits for the uninstall, and cleans "
    "the hub-side artifacts in cert-manager. "
    "The spoke is third-party accessible. It holds the leaf cert and key with no CA "
    "material, baseline operators by tier (CNV, GPU and OAI, sandboxed containers, base), "
    "the IDP config with no hub client secret, and day-2 workloads delivered by the ArgoCD "
    "ApplicationSet. "
    "Constraints: Tekton, ArgoCD and ACM run on the hub; the spoke is third-party accessible."
)


def render(head: str) -> str:
    """Return the SVG text; head is the <style>...</defs> block."""
    d = Drawing()
    d.begin(
        H,
        "Target architecture",
        DESC,
        head,
        "Git changes trigger Tekton pipelines on the hub; the pipelines drive Crossplane, "
        "Hive, cert-manager and the spoke.",
    )

    d.constraints(
        [
            ("Hub", "m b", "Tekton + ArgoCD + ACM run on the hub"),
            ("Spoke", "m b", "third-party accessible"),
        ],
        160,
    )

    # Each pill sits where no edge crosses the top edge of its frame.
    d.section("Frames")
    d.frame(False, 24, GIT_Y, 1214, 162, 40, "GIT · SOURCE OF TRUTH")
    d.frame(False, 24, HUB_Y, 1214, HUB_BOTTOM - HUB_Y, 930, "HUB CLUSTER · TRUSTED")
    d.frame(False, 24, SPOKE_Y, 1214, 142, 850, "SPOKE · THIRD-PARTY ACCESSIBLE")
    d.frame(True, F1, TEK_Y, 1070, 294, 882, "TEKTON · WORKFLOW ENGINE")
    d.frame(True, F1, ROW_D_F, FW12, 138, 180, "CROSSPLANE")
    d.frame(True, F2, ROW_D_F, FW12, 314, 578, "ACM / HIVE")
    d.frame(True, F3, ROW_D_F, FW3, 138, 858, "HUB-ONLY SECRET AUTHORITY")
    d.frame(True, F1, ROW_E_F, FW12, 248, 76, "ARGOCD · MANIFEST DELIVERY ONLY")

    d.section("Cards: Git")
    d.card(
        "store",
        40,
        GIT_CARD_Y,
        264,
        118,
        "hub-config/",
        [("t b", "ACM · Tekton · cert-manager")],
    )
    d.card(
        "store",
        346,
        GIT_CARD_Y,
        264,
        118,
        "fleet-clusters",
        [
            ("c s", "provision/NAME/"),
            ("t b", "ClusterDeployment · MachinePool"),
            ("t b", "install-config · tier label"),
        ],
    )
    d.card(
        "store",
        652,
        GIT_CARD_Y,
        264,
        118,
        "tekton/pipelines/",
        [("t b", "provision · post-provision"), ("t b", "deprovision")],
    )
    d.card(
        "store",
        958,
        GIT_CARD_Y,
        264,
        118,
        "workloads/TIER/",
        [("t b", "day-2 manifests")],
    )

    d.section("Cards: Tekton")
    d.card("gate", C2, EL_Y, CW12, 80, "EventListener", [("t b", "git webhook")])
    d.card(
        "src",
        C1,
        PIPE_Y,
        CW12,
        96,
        "Provision pipeline",
        [
            ("m s", "applies Crossplane and cluster CRs"),
            ("m s", "waits for Hive to be ready"),
        ],
    )
    d.card(
        "src",
        C2,
        PIPE_Y,
        CW12,
        96,
        "Deprovision pipeline",
        [
            ("m s", "deletes cluster CRs, waits for uninstall"),
            ("m s", "cleans hub-side artifacts"),
        ],
    )
    d.card(
        "src",
        C3,
        PIPE_Y,
        CW3,
        96,
        "Post-provision pipeline",
        [("t b", "tier: base / virt / ai / coco")],
    )

    d.section("Cards: Crossplane, ACM / Hive, secret authority")
    d.card(
        "src",
        C1,
        ROW_D,
        CW12,
        96,
        "AWS IAM user generation",
        [("t b", "per-cluster credentials")],
    )
    d.card(
        "core",
        C2,
        ROW_D,
        CW12,
        96,
        "Hive controller",
        [("t b", "provisions via cloud API")],
    )
    d.card(
        "src",
        C3,
        ROW_D,
        CW3,
        96,
        "cert-manager",
        [("c s", "ClusterIssuer: internal-ca")],
    )

    d.section("Cards: ArgoCD, Placement")
    d.card(
        "src",
        C1,
        ROW_E,
        CW12,
        100,
        "ApplicationSet",
        [("t b", "ACM cluster generator"), ("t b", "day-2 workload delivery")],
    )
    d.card(
        "core",
        C2,
        ROW_E,
        CW12,
        100,
        "Placement / ManagedCluster",
        [("t b", "tier label"), ("c s", "bootstrapped=true")],
    )
    d.card(
        "src",
        C1,
        ROW_F,
        CW12,
        80,
        "Application: hub-config",
        [("t b", "delivers Tekton, ACM, cert-manager")],
    )

    d.section("Cards: Spoke")
    d.card(
        "out",
        40,
        SPOKE_CARD_Y,
        264,
        100,
        "Day-2 workloads",
        [("t b", "via ArgoCD ApplicationSet")],
    )
    d.card(
        "store",
        346,
        SPOKE_CARD_Y,
        264,
        100,
        "Leaf cert + key only",
        [("t b", "no CA material")],
    )
    d.card(
        "src",
        652,
        SPOKE_CARD_Y,
        264,
        100,
        "Baseline operators",
        [("t b", "by tier: CNV · GPU+OAI ·"), ("t b", "sandboxed containers · base")],
    )
    d.card(
        "core",
        958,
        SPOKE_CARD_Y,
        264,
        100,
        "IDP config",
        [("t b", "no hub client secret")],
    )

    # Every path ends 2 px before its target so the arrow tip touches the border.
    d.section("Edges: Git to hub")
    d.edge("flow", f"M{XG} {GIT_BOTTOM} V{ROW_F + 40} H{C1 - 2}")
    d.label(XG + 8, 402, "ArgoCD sync")
    d.edge("flow", f"M150 {GIT_BOTTOM} V{PIPE_Y - 2}")
    d.label(158, 402, "repo read during pipeline")
    d.edge("flow", f"M660 {GIT_BOTTOM} V{EL_Y - 2}")
    d.label(668, 402, "webhook on commit")

    d.section("Edges: EventListener to pipelines")
    d.edge("flow", f"M600 {EL_BOTTOM} V600 H300 V{PIPE_Y - 2}")
    d.label(310, 593, "trigger by path")
    d.edge("flow", f"M660 {EL_BOTTOM} V{PIPE_Y - 2}")
    d.label(668, 624, "trigger on deletion PR")
    d.edge("flow", f"M720 {EL_BOTTOM} V600 H994 V{PIPE_Y - 2}")
    d.label(840, 593, "trigger by path")

    d.section("Edges: provision pipeline")
    d.edge("flow", f"M120 {PIPE_BOTTOM} V{ROW_D - 2}")
    d.label(128, 834, "applies Crossplane CRs")
    d.edge("flow", f"M330 {PIPE_BOTTOM} V780 H563 V{ROW_D - 2}")
    d.label(340, 773, "applies CRs")
    d.edge("ctl", f"M290 {PIPE_BOTTOM} V812 H545 V{ROW_D - 2}")
    d.label(300, 805, "waits for ready")
    d.edge("flow", f"M{C1 + CW12} {ROW_D + 48} H{C2 - 2}")
    d.label(382, ROW_D + 41, "generates AWS creds")

    d.section("Edges: deprovision pipeline")
    d.edge("flow", f"M700 {PIPE_BOTTOM} V{ROW_D - 2}")
    d.label(692, 826, "1. delete", "cluster CRs", anchor="end")
    d.edge("ctl", f"M740 {PIPE_BOTTOM} V{ROW_D - 2}")
    d.label(748, 826, "2. wait for", "uninstall")
    d.edge("flow", f"M775 {PIPE_BOTTOM} V784 H829 V{ROW_D + 48} H{C3 - 2}")
    d.label(783, 777, "3. clean hub-side artifacts")

    # Post-provision leaves the card's right side; the topmost exit takes the
    # outermost channel line so the four lines do not cross.
    d.section("Edges: post-provision pipeline")
    d.edge("flow", f"M1104 {PIPE_BOTTOM} V{ROW_D - 2}")
    d.label(1096, 826, "requests cert on hub", anchor="end")
    d.edge("flow", f"M{Q_RIGHT} 718 H{XP} V{ROW_E + 50} H{C2 + CW12 + 2}")
    d.label(830, ROW_E + 43, "labels spoke bootstrapped=true")
    d.edge("flow", f"M{Q_RIGHT} 698 H{X1} V1336 H560 V{SPOKE_CARD_Y - 2}")
    d.label(568, 1366, "derives + pushes", "leaf cert + key ONLY")
    d.edge("flow", f"M{Q_RIGHT} 678 H{X2} V1362 H784 V{SPOKE_CARD_Y - 2}")
    d.label(792, 1386, "applies tier manifests", "via spoke kubeconfig")
    d.edge("flow", f"M{Q_RIGHT} 658 H{X3} V{SPOKE_CARD_Y - 2}")
    d.label(X3 - 8, 1400, "configures IDP", anchor="end")

    # Hive to Spoke ends on the frame edge, between two spoke cards.
    d.section("Edges: ACM / Hive, ArgoCD to spoke")
    d.edge("ctl", f"M{C2} {ROW_E + 30} H{C1 + CW12 + 2}")
    d.label(388, ROW_E + 23, "cluster generator")
    d.edge("flow", f"M{C2} {ROW_D + 76} H{XH} V1358 H325 V{SPOKE_Y - 2}")
    d.label(333, 1394, "cloud API")
    d.edge("flow", f"M{C1 + CW12} {ROW_E + 76} H{XA} V1336 H172 V{SPOKE_CARD_Y - 2}")
    d.label(182, 1329, "delivers workloads")

    d.legend(
        H,
        [(40, "flow", "applies / triggers"), (222, "ctl", "waits / watches")],
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
