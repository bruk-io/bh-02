"""The findings page against the lab: its examples are what the hook makes today, and it builds whole
(it reads results/FINDINGS.md and the eval tasks on this host, so these are functional tests)."""

import re

from pages import examples
from pages.findings import SOURCE, blocks, page

_TEXT = SOURCE.read_text()


def _code_blocks() -> list[str]:
    return ["\n".join(b[1:]) for b in blocks(_TEXT) if b[0] == "```"]


def test_the_page_shows_the_envelopes_the_hook_makes_now():
    """When the code changes what an envelope says, the page must change with it: run
    pages/examples.py's functions and paste their text into results/FINDINGS.md."""
    shown = _code_blocks()
    banner, envelope = examples.invoices().split("\n", 1)
    none_found = next(ln for ln in examples.calm().splitlines() if ln.startswith("anomalies:"))
    for made in (banner, envelope, none_found, examples.log(), examples.snapshot()):
        assert made in shown, f"FINDINGS.md no longer shows this envelope as the code makes it:\n{made[:200]}"


def test_the_page_builds_and_every_link_within_it_lands():
    html = page(_TEXT, {"envelope-flow": "<figure></figure>"}, "today")
    ids = set(re.findall(r'id="([^"]+)"', html))
    links = set(re.findall(r'href="#([^"]+)"', html))
    assert links and links <= ids, f"links to no heading: {sorted(links - ids)}"
