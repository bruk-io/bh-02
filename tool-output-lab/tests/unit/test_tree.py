"""The trees envelopes are made of: outlines by indentation, a document's headings, XML by element."""

from compressors.tree import heading_tree, indent_tree, looks_like_outline, looks_like_xml, xml_tree


def _snapshot(sections: int, items: int) -> str:
    """A Playwright-style accessibility snapshot: nested `- role "name" [ref=..]` lines."""
    lines = ["- generic [ref=e1]:", "  - banner [ref=e2]:", '    - link "Home" [ref=e3]']
    ref = 4
    for s in range(sections):
        lines.append(f'  - region "Section {s}" [ref=e{ref}]:')
        ref += 1
        for i in range(items):
            lines.append(f"    - listitem [ref=e{ref}]:")
            lines.append(f'      - link "Item {s}.{i}" [ref=e{ref + 1}]')
            lines.append(f"        - /url: /items/{s}/{i}")
            ref += 2
    return "\n".join(lines)


def test_indentation_nests_children_under_their_parent():
    roots = indent_tree(["a", "  b", "    c", "  d", "e"])
    assert [(r.first, r.last) for r in roots] == [(0, 3), (4, 4)]
    assert [(c.first, c.last) for c in roots[0].children] == [(1, 2), (3, 3)]
    assert looks_like_outline(_snapshot(4, 20).splitlines())


def test_headings_nest_their_sections_and_the_preamble_is_a_node():
    lines = ["intro", "# A", "text", "## A.1", "more", "# B", "end"]
    roots = heading_tree(lines)
    assert [(r.first, r.last) for r in roots] == [(0, 0), (1, 4), (5, 6)]
    assert [(c.first, c.last) for c in roots[1].children] == [(3, 4)]
    assert [(n.first, n.last) for n in heading_tree(["x", "", "y"])] == [(0, 0), (2, 2)]  # no heading


def test_packed_xml_is_pretty_printed_one_element_a_line():
    frames = "".join(
        f'<frame id="1:{i}" name="Card {i}">'
        + "".join(f'<text id="2:{i}{j}" name="t{j}"/>' for j in range(8))
        + "</frame>"
        for i in range(40)
    )
    raw = f'<?xml version="1.0"?><canvas id="0:1" name="Page">{frames}</canvas>'
    tree = xml_tree(raw)
    assert looks_like_xml(raw) and tree is not None and tree.pretty
    assert len(tree.lines) > 300 and len(tree.roots[0].children) == 40


def test_html_and_broken_xml_are_not_xml():
    assert not looks_like_xml("<!doctype html><html></html>")
    assert xml_tree("<a><b></a>") is None


def test_xml_with_a_bare_ampersand_is_read_leniently_and_kept_as_it_is():
    entries = "".join(f'\n\t<entry code="X-{i}" name="Place {i}"/>' for i in range(300))
    amp = '\n\t<entry code="X-AMP" name="Enewetak & Ujelang"/>'
    raw = f'<?xml version="1.0"?>\n<entries>{entries}{amp}\n</entries>'
    tree = xml_tree(raw)
    assert tree is not None and not tree.pretty and tree.lines[-2] == amp.strip("\n")
