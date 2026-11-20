"""Lay out docs/diagrams/value-flow.svg.

Usage:
    python docs/diagrams/layout_value_flow.py           # write the SVG
    python docs/diagrams/layout_value_flow.py --check   # exit 1 if it differs

The content source is value-flow.mermaid. drawing.py holds the drawing
helpers and supplies the shared <style> and <defs> blocks.
"""

import argparse
from pathlib import Path

from drawing import DIAGRAMS, Drawing, emit, shared_head

SVG = DIAGRAMS / "value-flow.svg"

H = 1054

# Three card columns with a 96 px channel between them.
C = (40, 466, 892)
CW, CH = 330, 98
MID = [x + CW // 2 for x in C]  # x of the centre of each column

ROW_PUSH = 296  # push event, EventListener, TriggerBinding
ROW_TT = 450  # TriggerTemplate
ROW_PIPE = 642  # the three pipelines
ROW_VAL = 834  # ConfigMap, metadata.yaml, tier label
TRIGGER_Y, PIPE_Y, VAL_Y = 270, 616, 808  # top edge of the three frames
CHAN_TT, CHAN_PIPE, CHAN_VAL = 422, 590, 782  # channels above the lower rows

DESC = (
    "How a value reaches a pipeline task. Trigger: a push event carries the repository "
    "URL, the commit SHA and the files each commit adds. It reaches the EventListener as "
    "a webhook. A CEL overlay of the EventListener writes extensions.cluster_name from the "
    "first added path. The TriggerBinding reads the extensions and the event body: "
    "cluster-name = $(extensions.cluster_name), git-revision = $(body.after). It passes "
    "them as params to the TriggerTemplate, which writes the params of the PipelineRun "
    "from $(tt.params.NAME). The PipelineRun of pre-provision gets cluster-name, "
    "git-repo-url and git-revision. "
    "Pipelines: the last task of pre-provision, trigger-provision, creates the PipelineRun "
    "of provision with 3 params: cluster-name, git-repo-url and git-revision. The last task of provision, trigger-post-provision, "
    "creates the PipelineRun of post-provision with 9 params. In post-provision the tasks "
    "read $(params.NAME), and when conditions read tier, openshift-cluster and "
    "ai-accelerator. "
    "Values that tasks read: the ConfigMap fleet-pipeline-config holds values for every "
    "cluster; load-config turns each key into a result in every pipeline. metadata.yaml "
    "holds values for one cluster; read-cluster-metadata turns each key into a result. "
    "pre-provision reads aws-credentials-mode from it and provision reads all results. "
    "The ManagedCluster label tier is turned into a result by read-cluster-tier in "
    "provision. "
    "Constraints: Tekton passes no value implicitly; every hop names the value it passes. "
    "A pipeline reads the result of a task as $(tasks.TASK.results.NAME). A pipeline "
    "parameter that differs from the built-in default of load-config wins over the "
    "ConfigMap. A post-provision run started through the EventListener gets cluster-name, "
    "tier and dns-zones only."
)


def render(head: str) -> str:
    """Return the SVG text; head is the <style>...</defs> block."""
    d = Drawing()
    d.begin(
        H,
        "Value flow",
        DESC,
        head,
        "Where the values of a pipeline run come from, and the object that passes each "
        "one on.",
    )

    d.constraints(
        [
            (
                "Rule",
                "m b",
                "Tekton passes no value implicitly; every hop names the value it passes",
            ),
            (
                "Results",
                "c s",
                "a pipeline reads the result of a task as $(tasks.TASK.results.NAME)",
            ),
            (
                "Override",
                "m b",
                "a pipeline parameter that differs from the built-in default of load-config "
                "wins over the ConfigMap",
            ),
            (
                "Limit",
                "m b",
                "a post-provision run started through the EventListener gets cluster-name, "
                "tier and dns-zones only",
            ),
        ],
        160,
    )

    # Each pill sits where no edge or label crosses the top edge of its frame.
    d.section("Frames")
    d.frame(False, 24, TRIGGER_Y, 1214, 294, 40, "TRIGGER")
    d.frame(False, 24, PIPE_Y, 1214, 140, 560, "PIPELINES")
    d.frame(False, 24, VAL_Y, 1214, 140, 830, "VALUES THAT TASKS READ")

    d.section("Cards: trigger")
    d.card(
        "gate",
        C[0],
        ROW_PUSH,
        CW,
        CH,
        "Push event",
        [("m s", "repository URL, commit SHA,"), ("m s", "files each commit adds")],
    )
    d.card(
        "src",
        C[1],
        ROW_PUSH,
        CW,
        CH,
        "EventListener",
        [
            ("m s", "CEL overlay writes extensions.cluster_name"),
            ("m s", "from the first added path"),
        ],
    )
    d.card(
        "src",
        C[2],
        ROW_PUSH,
        CW,
        CH,
        "TriggerBinding",
        [
            ("c s", "cluster-name = $(extensions.cluster_name)"),
            ("c s", "git-revision = $(body.after)"),
        ],
    )
    d.card(
        "src",
        C[0],
        ROW_TT,
        CW,
        CH,
        "TriggerTemplate",
        [
            ("m s", "writes the params of the PipelineRun"),
            ("c s", "from $(tt.params.NAME)"),
        ],
    )

    d.section("Cards: pipelines")
    d.card(
        "core",
        C[0],
        ROW_PIPE,
        CW,
        CH,
        "pre-provision",
        [
            ("m s", "last task: trigger-provision creates the"),
            ("m s", "PipelineRun of provision with 3 params"),
        ],
    )
    d.card(
        "core",
        C[1],
        ROW_PIPE,
        CW,
        CH,
        "provision",
        [
            ("m s", "last task: trigger-post-provision creates the"),
            ("m s", "PipelineRun of post-provision with 9 params"),
        ],
    )
    d.card(
        "core",
        C[2],
        ROW_PIPE,
        CW,
        CH,
        "post-provision",
        [
            ("m s", "tasks read $(params.NAME); when conditions read"),
            ("m s", "tier, openshift-cluster and ai-accelerator"),
        ],
    )

    d.section("Cards: values that tasks read")
    d.card(
        "store",
        C[0],
        ROW_VAL,
        CW,
        CH,
        "ConfigMap fleet-pipeline-config",
        [
            ("m s", "values for every cluster; load-config"),
            ("m s", "turns each key into a result"),
        ],
    )
    d.card(
        "store",
        C[1],
        ROW_VAL,
        CW,
        CH,
        "metadata.yaml",
        [
            ("m s", "values for one cluster; read-cluster-metadata"),
            ("m s", "turns each key into a result"),
        ],
    )
    d.card(
        "store",
        C[2],
        ROW_VAL,
        CW,
        CH,
        "ManagedCluster label tier",
        [("m s", "read-cluster-tier turns it"), ("m s", "into a result")],
    )

    # Every path ends 2 px before its target so the arrow tip touches the border.
    d.section("Edges: trigger")
    mid = ROW_PUSH + CH // 2
    d.edge("flow", f"M{C[0] + CW} {mid} H{C[1] - 2}")
    d.label(418, mid - 7, "webhook", anchor="middle")
    d.edge("flow", f"M{C[1] + CW} {mid} H{C[2] - 2}")
    d.label(844, mid - 7, "extensions", anchor="middle")
    d.edge("flow", f"M{MID[2]} {ROW_PUSH + CH} V{CHAN_TT} H{MID[0]} V{ROW_TT - 2}")
    d.label(MID[0] + 8, CHAN_TT + 15, "params")
    d.edge("flow", f"M{MID[0]} {ROW_TT + CH} V{ROW_PIPE - 2}")
    d.label(
        MID[0] + 8,
        CHAN_PIPE + 15,
        "PipelineRun: cluster-name, git-repo-url, git-revision",
    )

    d.section("Edges: pipeline to pipeline")
    mid = ROW_PIPE + CH // 2
    d.edge("flow", f"M{C[0] + CW} {mid} H{C[1] - 2}")
    d.label(418, mid - 7, "PipelineRun", anchor="middle")
    d.edge("flow", f"M{C[1] + CW} {mid} H{C[2] - 2}")
    d.label(844, mid - 7, "PipelineRun", anchor="middle")

    # The ConfigMap edge ends on the frame of the pipelines: every pipeline
    # runs load-config. The two horizontal lines share the channel and do not meet.
    d.section("Edges: values to pipelines")
    bottom = ROW_PIPE + CH
    d.edge("flow", f"M120 {ROW_VAL} V{PIPE_Y + 140 + 2}")
    d.label(128, CHAN_VAL + 15, "load-config")
    d.edge("flow", f"M560 {ROW_VAL} V{CHAN_VAL} H{MID[0]} V{bottom + 2}")
    d.label(300, CHAN_VAL - 7, "aws-credentials-mode")
    d.edge("flow", f"M{MID[1]} {ROW_VAL} V{bottom + 2}")
    d.label(MID[1] + 8, CHAN_VAL + 15, "results")
    d.edge("flow", f"M{MID[2]} {ROW_VAL} V{CHAN_VAL} H700 V{bottom + 2}")
    d.label(860, CHAN_VAL - 7, "tier")

    d.legend(
        H,
        [(40, "flow", "passes values")],
        [
            (200, "gate", "event"),
            (300, "src", "trigger objects"),
            (460, "core", "pipelines"),
            (590, "store", "values that tasks read"),
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
