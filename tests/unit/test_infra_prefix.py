"""Parity tests for the vendored infra_prefix against scaffold test vectors."""

from fleet.tasks._infra_prefix import infra_prefix


def test_passthrough():
    assert infra_prefix("10f25620-vscopeocpv") == "10f25620-vscopeocpv"


def test_truncation():
    assert infra_prefix("a" * 30) == "a" * 21


def test_trailing_dash_stripped():
    assert infra_prefix("abcdefghijklmnopqrst-uvw") == "abcdefghijklmnopqrst"


def test_collapsed_dashes():
    assert infra_prefix("a--b") == "a-b"


def test_non_alnum_replaced():
    assert infra_prefix("hello_world.foo") == "hello-world-foo"


def test_combined_normalise_and_truncate():
    name = "partner__acme--openshift...cluster-1"
    result = infra_prefix(name)
    assert "-_" not in result and ".." not in result and "--" not in result
    assert len(result) <= 21
    assert not result.endswith("-")
