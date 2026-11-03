import re

from compressors.tree import (
    fold_outline,
    fold_tree,
    fold_xml,
    indent_tree,
    looks_like_outline,
    looks_like_xml,
)


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


def test_a_big_outline_folds_to_the_budget_and_keeps_the_top_levels():
    raw = _snapshot(sections=20, items=30)
    assert looks_like_outline(raw.splitlines())
    fold = fold_outline(raw, budget_tokens=600)
    assert len(fold.text) / 4 <= 700
    for s in range(20):
        assert f'region "Section {s}"' in fold.text
    assert "folded" in fold.text


def test_fold_markers_name_the_exact_lines_they_hide():
    raw = _snapshot(sections=5, items=20)
    lines = raw.splitlines()
    fold = fold_outline(raw, budget_tokens=200)
    for a, b in re.findall(r"lines (\d+)-(\d+) folded", fold.text):
        hidden = lines[int(a) - 1 : int(b)]
        assert hidden and not any(h in fold.text.splitlines() for h in hidden if h.strip())


def test_with_room_everything_shows():
    raw = _snapshot(sections=2, items=3)
    assert fold_outline(raw, budget_tokens=100_000).text == raw


def test_numbered_lines_carry_their_source_line_numbers():
    lines = ["def f():", "    a = 1", "    b = 2", "    c = 3", "    return a", "x = 1"]
    from compressors.tree import Node

    text, opened, folded = fold_tree(lines, (Node(0, 0, 4),), budget_tokens=1)
    assert text.splitlines() == ["1\tdef f():  [... lines 2-5 folded (4 lines)]", "6\tx = 1"]
    assert (opened, folded) == (0, 1)


def test_packed_xml_is_pretty_printed_and_folded_by_element():
    frames = "".join(
        f'<frame id="1:{i}" name="Card {i}">'
        + "".join(f'<text id="2:{i}{j}" name="t{j}"/>' for j in range(8))
        + "</frame>"
        for i in range(40)
    )
    raw = f'<?xml version="1.0"?><canvas id="0:1" name="Page">{frames}</canvas>'
    assert looks_like_xml(raw)
    fold = fold_xml(raw, budget_tokens=500)
    assert fold is not None
    assert len(fold.source.splitlines()) > 300  # one element per line now
    assert 'name="Card 39"' in fold.text and 'name="Card 0"' in fold.text
    assert "folded" in fold.text
    assert len(fold.text) / 4 <= 600


def test_html_and_broken_xml_are_not_xml():
    assert not looks_like_xml("<!doctype html><html></html>")
    assert fold_xml("<a><b></a>", budget_tokens=100) is None


def test_a_sibling_that_stands_out_is_shown_inside_a_partly_open_list():
    lines = ["- list [ref=e1]:"]
    for i in range(200):
        flag = " [disabled]" if i == 117 else ""
        lines.append(f'  - button "Pay invoice {i}" [ref=e{i + 2}]{flag}:')
        lines.append(f"    - img [ref=e{i + 900}]")
        lines.append(f"    - text: Invoice {i}")
        lines.append("    - text: due soon")
    fold = fold_outline("\n".join(lines), budget_tokens=800)
    assert "siblings)" in fold.text
    assert 'button "Pay invoice 117" [ref=e119] [disabled]' in fold.text
    assert 'button "Pay invoice 150"' not in fold.text


def test_a_stand_out_opens_first_even_when_its_list_opens_in_full():
    lines = ["- list [ref=e1]:"]
    for i in range(50):
        flag = " [disabled]" if i == 0 else ""
        lines += [f"  - listitem [ref=e{i + 2}]:", f"    - text: Invoice {i}", "    - text: due soon"]
        lines.append(f'    - button "Pay invoice {i}" [ref=e{i + 900}]{flag}')
    fold = fold_outline("\n".join(lines), budget_tokens=600)
    assert 'button "Pay invoice 0" [ref=e900] [disabled]' in fold.text


def test_xml_with_a_bare_ampersand_is_read_leniently_and_shown_as_it_is():
    entries = "".join(f'\n\t<entry code="X-{i}" name="Place {i}"/>' for i in range(300))
    amp = '\n\t<entry code="X-AMP" name="Enewetak & Ujelang"/>'
    raw = f'<?xml version="1.0"?>\n<entries>{entries}{amp}\n</entries>'
    fold = fold_xml(raw, budget_tokens=300)
    assert fold is not None and fold.source == raw
    assert "Enewetak & Ujelang" in fold_xml(raw, budget_tokens=100_000).text


def test_long_xml_comments_and_the_doctype_fold_like_elements():
    from compressors.tree import xml_tree

    comment = "\n".join(f"comment line {i}" for i in range(40))
    doctype = "\n".join(f"<!ENTITY e{i} 'x'>" for i in range(20))
    raw = (
        f'<?xml version="1.0"?>\n<!--\n{comment}\n-->\n<!DOCTYPE root [\n{doctype}\n]>\n<root>\n<a/>\n</root>'
    )
    lines, roots = xml_tree(raw)
    spans = [(n.first + 1, n.last + 1) for n in roots]
    assert spans == [(2, 43), (44, 65), (66, 68)]
    fold = fold_xml(raw, budget_tokens=60)
    assert "comment line 20" not in fold.text and "<root>" in fold.text


def test_a_stand_out_is_found_among_siblings_with_alphanumeric_ids():
    import random

    rng = random.Random(3)
    lines = ["- list [ref=e1]:"]
    for i in range(150):
        inv = f"INV-{rng.getrandbits(28):07x}"
        flag = " [disabled]" if i == 75 else ""
        lines += [f"  - listitem [ref=e{rng.randint(10, 99999)}]:", f"    - text: Invoice {inv}"]
        lines.append(f'    - button "Pay {inv}" [ref=e{rng.randint(10, 99999)}]{flag}')
    assert "[disabled]" in fold_outline("\n".join(lines), budget_tokens=500).text


def test_stand_outs_past_the_cap_are_counted_in_the_marker_that_hides_them():
    lines = ["- list:"]
    for i in range(300):
        flag = " [disabled]" if i % 20 == 7 else ""  # 15 stand-outs, the cap is 10
        lines += [
            f"  - item {i}:",
            f"    - text: row {i}",
            f'    - button "Pay {i}"{flag}',
            "    - text: due",
        ]
    text = fold_outline("\n".join(lines), budget_tokens=900).text
    shown = text.count("[disabled]")
    more = sum(int(n) for n in __import__("re").findall(r"; (\d+) of them stand out too", text))
    assert shown + more == 15 and more > 0
