from compressors.common import split_lines
from compressors.config import CHOICES
from compressors.envelope import Role
from compressors.envelope_tree import ANOMALIES, NAVS, SAMPLES, SHAPES, envelope
from compressors.route import lines_envelope
from compressors.tree import indent_tree, xml_tree
from evals.envelope_check import text_problems


def _snapshot(n: int = 60, disabled: tuple[int, ...] = (9, 41)) -> str:
    lines = ["- main [ref=e1]:", '  - heading "Invoices" [level=1] [ref=e2]', "  - list [ref=e3]:"]
    for i in range(n):
        flag = " [disabled]" if i in disabled else ""
        lines += [
            f"    - listitem [ref=e{100 + i}]:",
            f"      - text: Invoice INV-{i:04d}",
            f'      - button "Pay INV-{i:04d}" [ref=e{900 + i}]{flag}',
        ]
    return "\n".join(lines) + "\n"


def _outline(raw: str, terms: frozenset[str] = frozenset(), budget: int = 2000, view: str = "sample"):
    lines = tuple(split_lines(raw))
    return envelope(lines, indent_tree(list(lines)), terms, budget, view=view)


def test_a_run_of_like_items_is_counted_and_the_items_that_differ_are_listed():
    raw = _snapshot()
    env = _outline(raw, view="schema")
    text = env.text()
    assert "3:   - list [ref=e3]:" in text and "60 items like: - listitem [ref=<*>]:" in text
    assert "anomalies: 2 of 60 items in 1 run, all listed" in text
    assert "2 lines like: - button <*> [ref=<*>] [disabled]  (in 2 of 60 items)" in text
    assert "31:     - listitem [ref=e109]:" in text  # the item, by its first line
    assert "grep -nF '] [disabled]' FILE  (the 2 lines like it)" in text
    assert text_problems(raw, env, run_tools=False) == []


def test_a_rare_value_in_an_attribute_marks_its_item():
    cards = "".join(
        f'<frame id="1:{i}" name="Card {i}" width="{160 if i == 33 else 320}">'
        f'<text id="2:{i}" name="Title"/></frame>'
        for i in range(50)
    )
    tree = xml_tree(f'<canvas id="0:1" name="Grid">{cards}</canvas>')
    assert tree is not None and tree.pretty
    lines = tuple(tree.lines)
    env = envelope(lines, tree.roots, frozenset(), 2000)
    text = env.text()
    assert '<*>3 is "160" in 1 line like: <frame id=<*> name=<*> width=<*>>  (in 1 of 50 items)' in text
    assert text_problems("\n".join(lines), env, run_tools=False) == []


def test_the_query_shows_its_items_whole_and_each_once():
    raw = _snapshot()
    samples = _outline(raw, frozenset({"inv-0025"}), view="schema").level(Role.SAMPLES)
    assert samples.head == "2 lines match the query"
    assert [line.split(":")[0] for line in samples.body] == ["79", "80", "81"]  # its item, whole


def test_a_tree_with_no_run_is_its_outline():
    raw = "".join(f"- section {chr(65 + i)}:\n  - para about {chr(65 + i)}\n" for i in range(4)) * 1
    env = _outline(raw)
    assert (
        env.level(Role.ANOMALIES).head.startswith("none found by its rules")
        and "1: - section A:" in env.text()
    )


def test_each_tree_part_knob_names_exactly_the_producers_there_are():
    assert set(CHOICES["tree_envelope.shape"]) == {"", *SHAPES}
    assert set(CHOICES["tree_envelope.anomalies"]) == {"", *ANOMALIES}
    assert set(CHOICES["tree_envelope.samples"]) == {"", *SAMPLES}
    assert set(CHOICES["tree_envelope.nav"]) == {"", *NAVS}


def test_a_page_is_its_headings_and_the_query_shows_its_section():
    sections = "".join(
        f"<h2>Part {i}</h2>"
        + "".join(f"<p>Paragraph {j} of part {i}, on topic {i * 10 + j}.</p>" for j in range(8))
        for i in range(30)
    )
    raw = f"<!doctype html><html><body><h1>Guide</h1>{sections}</body></html>"
    env, source = lines_envelope(raw, "html", frozenset({"part 17"}), 400)
    text = env.text()
    assert "1: # Guide" in text and "## Part 0" in text
    assert "## Part 17" in text and "Paragraph 3 of part 17" in text  # the section the query names
    assert text_problems(source, env, run_tools=False) == []


def test_code_is_its_definitions_a_class_with_all_its_methods():
    words = [
        a + b for a in ("red", "blue", "gold", "jade", "rust", "teal", "plum") for b in ("fox", "owl", "elk")
    ]
    methods = "".join(f"    def {w}(self):\n        return self.{w}\n\n" for w in words[:12])
    helpers = "".join(f"def {w}_helper():\n    if True:\n        return '{w}'\n\n" for w in words * 2)
    src = f"class Server:\n{methods}\n{helpers}"
    env, source = lines_envelope(src, "code", frozenset(), 2000, language="python")
    text = env.text()
    assert env.level(Role.ANOMALIES).head.startswith(
        "none found by its rules"
    )  # definitions with their own names are no run
    assert "1: class Server:" in text and all(f"def {w}(self):" in text for w in words[:12])
    assert text_problems(source, env, run_tools=False) == []


def test_a_zero_amount_among_positive_ones_marks_its_item_and_shows_it_whole():
    lines = ["- list:"]
    for i in range(40):
        amount = "0.00" if i == 17 else f"{20 + (i * 37) % 800}.{i % 100:02d}"
        lines += [
            f"  - item {i}:",
            f"    - text: Invoice INV-{i:04d}",
            f"    - text: ${amount} due 1{i % 9} Nov",
        ]
    raw = "\n".join(lines) + "\n"
    src = tuple(split_lines(raw))
    env = envelope(src, indent_tree(list(src)), frozenset(), 2000, view="schema")
    text = env.text()
    assert (
        "is 0 in 1 line like: - text: $<*>.<*> due <*> Nov  (in 1 of 40 items; a number far from the rest)"
        in text
    )
    assert "54:     - text: Invoice INV-0017" in text  # the short item whole: its name is in view
    assert text_problems(raw, env, run_tools=False) == []
