"""Checks that the links of the refreshed documents resolve, including heading anchors."""

import pytest

from tests.validation._markdown import ROOT, headings, links

# Documents that have been checked against the repository. Add a document
# here when it is refreshed.
DOCUMENTS = ["README.md", "docs/architecture.md", "docs/user-guide.md"]


@pytest.mark.parametrize("document", DOCUMENTS)
def test_links_and_anchors_resolve(document):
    source = ROOT / document
    targets = links(source)
    assert targets

    for target in targets:
        path, _, anchor = target.partition("#")
        file = source.parent / path if path else source
        assert file.exists(), f"{document} links to the missing path {path}"
        if anchor and file.suffix == ".md":
            assert anchor in headings(file), f"{document}: no heading for {target}"
