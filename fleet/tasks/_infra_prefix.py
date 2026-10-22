"""Vendored infra_prefix from fleet-cluster-scaffold (scaffold.providers.aws_policies).

The scaffold is a private repo not published to any package index. This 3-line function
is vendored here with parity tests (tests/unit/test_infra_prefix.py) rather than coupling
the fleet image build to the scaffold's release cycle.
"""

import re

_INFRA_BASE_MAX = 21


def infra_prefix(cluster_name: str) -> str:
    base = re.sub(r"[^A-Za-z0-9-]", "-", cluster_name)
    base = re.sub(r"-{2,}", "-", base)
    return base[:_INFRA_BASE_MAX].rstrip("-")
