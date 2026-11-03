import json

import pytest

from compressors.cli import fold_text, main


def _src() -> str:
    body = "\n".join(f"        x{i} = {i}" for i in range(400))
    head = 'class A:\n    """A class."""\n    def big(self):\n'
    return f"{head}{body}\n\n    def small(self):\n        return 1\n"


def test_text_that_fits_is_printed_unchanged():
    assert fold_text("x = 1\n", budget=200, path="a.py").text == "x = 1\n"


def test_code_is_folded_by_its_extension_with_real_line_numbers():
    out = fold_text(_src(), budget=200, path="a.py").text
    head, *rest = out.splitlines()
    assert head.startswith("[fold: code (python), ~")
    assert "1\tclass A:" in rest[0]
    assert "3\t    def big(self):" in rest
    assert any("folded (399 lines)" in line for line in rest)  # the body, folded below its header
    assert "405\t    def small(self):" in rest
    assert len(out) / 4 <= 200


def test_code_from_stdin_needs_a_language_and_folds_with_one():
    with pytest.raises(ValueError, match="--lang"):
        fold_text(_src(), budget=200, fmt="code")
    assert "code (python)" in fold_text(_src(), budget=200, lang="python").text


def test_json_from_stdin_is_detected_and_the_query_keeps_an_item_in_view():
    raw = json.dumps([{"id": f"u{i:04d}", "role": "viewer"} for i in range(500)])
    plain = fold_text(raw, budget=300).text
    asked = fold_text(raw, budget=300, query="u0321").text
    assert plain.startswith("[fold: json,") and "u0321" not in plain
    assert "u0321" in asked


def test_packed_xml_says_its_line_numbers_refer_to_a_pretty_copy():
    raw = "<a>" + "".join(f'<b id="{i}"><c/><c/><c/><c/></b>' for i in range(300)) + "</a>"
    r = fold_text(raw, budget=300)
    assert "pretty-printed copy" in r.text.splitlines()[0]
    assert r.source is not None and len(r.source.splitlines()) > 300


def test_xml_already_one_element_per_line_refers_to_the_input_even_with_a_final_newline():
    raw = "<a>\n" + "".join(f'  <b id="{i}"><c/></b>\n' for i in range(400)) + "</a>\n"
    r = fold_text(raw, budget=300)
    assert r.branch == "xml" and r.source is None
    assert "line numbers refer to the input" in r.text.splitlines()[0]


def test_the_result_names_what_folded_it():
    assert fold_text("x = 1\n", budget=200).branch is None
    assert fold_text(json.dumps(list(range(2000))), budget=100).branch == "json"
    code = fold_text(_src(), budget=200, path="a.py")
    assert (code.branch, code.language) == ("code", "python")
    cut = fold_text("x" * 50_000, budget=100)
    assert cut.branch == "text" and cut.text.startswith("[fold: text,")


def test_forcing_a_format_the_text_cannot_take_says_so():
    with pytest.raises(ValueError, match="does not parse as JSON"):
        fold_text("not json " * 2000, budget=100, fmt="json")


def test_the_cli_reads_a_file_and_writes_the_pretty_copy(tmp_path, capsys):
    xml = tmp_path / "page.xml"
    xml.write_text("<a>" + "".join(f'<b id="{i}"><c/><c/><c/><c/></b>' for i in range(300)) + "</a>")
    pretty = tmp_path / "pretty.xml"
    assert main([str(xml), "--budget", "300", "--save", str(pretty)]) == 0
    assert "[fold: xml" in capsys.readouterr().out
    assert len(pretty.read_text().splitlines()) > 300
    assert main([str(tmp_path / "missing.txt")]) == 1


def _line(text: str, n: int) -> str:
    """Line n (1-based) as sed -n 'np' counts it: newline-separated only."""
    return text.split("\n")[n - 1].rstrip("\r")


def test_line_numbers_count_newlines_only_as_sed_and_read_do():
    import re

    src = "import os\n\x0c\n# page two\n" + "".join(
        f"def func_{i}(a):\n    x = a + {i}\n    y = x * 2\n    z = y - 1\n    return z\n\n"
        for i in range(150)
    )
    out = fold_text(src, budget=300, path="ff.py", quiet=True).text
    for n, shown in re.findall(r"(?m)^(\d+)\t(.*?)(?:  \[\.\.\. lines .*)?$", out):
        assert shown == _line(src, int(n)), n


def test_a_progress_line_with_carriage_returns_stays_one_line():
    import re

    lines = [f"2026-11-03T10:00:{i % 60:02d}Z INFO step {i} ok" for i in range(300)]
    lines[100] = "Downloading 10%\r 50%\r 100%"
    lines[200] = "2026-11-03T10:03:20Z ERROR upload failed"
    raw = "\n".join(lines)
    out = fold_text(raw, budget=300, quiet=True).text
    last = max(int(b) for _, b in re.findall(r"lines (\d+)-(\d+)", out))
    assert last <= len(lines)
    assert "ERROR upload failed" in out


def test_crlf_input_folds_exactly_like_lf():
    src = "".join(f"def f{i}(a):\n    x = a\n    y = x\n    return y\n\n" for i in range(300))
    crlf = fold_text(src.replace("\n", "\r\n"), budget=300, path="a.py", quiet=True).text
    assert (
        crlf == fold_text(src, budget=300, path="a.py", quiet=True).text
    )  # the header's size differs, not the fold


def test_query_reaches_code_and_opens_the_definition_that_holds_it():
    import random

    rng = random.Random(5)
    words = ["alpha", "bravo", "cargo", "delta", "ember", "fable", "grove", "haven", "ivory", "jolly"]
    calls = [f"{rng.choice(words)}_{rng.choice(words)}_{rng.choice(words)}" for _ in range(400)]
    calls[237] = "webhook_client"  # every body differs, so only the query can pick this one out
    src = "".join(
        f"def handler_{i}(req):\n    x = {c}()\n    y = parse(x)\n    return y\n\n"
        for i, c in enumerate(calls)
    )
    assert "webhook_client" not in fold_text(src, budget=300, path="h.py", quiet=True).text
    assert "webhook_client" in fold_text(src, budget=300, path="h.py", query="webhook", quiet=True).text


def test_a_query_matching_a_few_of_thirty_siblings_still_shows_them():
    offices = []
    for i in range(30):
        city = "Kyoto" if i in (11, 19) else f"City{i}"
        offices += [
            f"- office {i}:",
            f"  - city: {city}",
            "  - staff: 12",
            "  - phone: 555-0100",
            "  - open: yes",
        ]
    out = fold_text("\n".join(offices), budget=150, query="Kyoto", quiet=True).text
    assert out.count("Kyoto") == 2


def test_a_query_that_names_every_key_keeps_none_of_them_specially():
    import json

    raw = json.dumps({f"node-{i}": {"cpu": i % 7} for i in range(5000)})
    out = fold_text(raw, budget=2000, query="node", quiet=True).text
    assert len(out) / 4 <= 2200


def test_matching_many_items_against_many_terms_is_quick():
    import json
    import time

    items = [{"id": i, "name": f"item {i}", "note": "alpha beta gamma delta " * 3} for i in range(20000)]
    start = time.perf_counter()
    fold_text(json.dumps(items), budget=2000, query=" ".join(f"term{j}" for j in range(40)), quiet=True)
    assert time.perf_counter() - start < 8
