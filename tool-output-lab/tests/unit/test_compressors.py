"""The router and its folds: JSON, logs, plain text, HTML; and resolving a folded JSON path."""

import json
import re

import pytest

from compressors.common import query_terms
from compressors.html import html_to_text
from compressors.recovery import RecoveryError, resolve
from compressors.route import detect, fold


def _pods(n: int, **overrides_at: dict) -> list[dict]:
    pods = [
        {"name": f"pod-{i:04d}", "phase": "Running", "ready": True, "deleted": False, "restarts": i % 3}
        for i in range(n)
    ]
    for idx, fields in overrides_at.items():
        pods[int(idx.removeprefix("at"))].update(fields)
    return pods


def _text(raw: str, budget: int, args: dict | None = None, use_query: bool = True) -> str:
    terms = query_terms(args or {}) if use_query else frozenset()
    folded = fold(raw, budget_tokens=budget, terms=terms)
    return raw if folded is None else folded.body


def _json(raw: str, budget: int, args: dict | None = None) -> object:
    return json.loads(_text(raw, budget, args))


def _log(n: int) -> list[str]:
    paths = ["/api/items", "/api/users", "/health", "/api/orders", "/static/app.js"]
    return [
        f"2026-11-03T10:{i // 60 % 60:02d}:{i % 60:02d}Z INFO GET {paths[i * 7 % 5]} 200" for i in range(n)
    ]


def test_small_results_pass_through_untouched():
    assert fold("hello\n" * 10, budget_tokens=2000) is None


def test_a_long_array_stays_an_array_and_shows_head_tail_and_markers():
    raw = json.dumps({"pods": _pods(500)})
    folded = fold(raw, budget_tokens=500)
    assert folded is not None and folded.branch == "json"
    pods = json.loads(folded.body)["pods"]
    assert isinstance(pods, list)
    assert pods[0]["name"] == "pod-0000" and pods[-1]["name"] == "pod-0499"
    assert any("_folded" in p and "$.pods[2:499]" in p["_folded"] for p in pods)
    assert len(folded.body) / 4 < len(raw) / 40


def test_the_summary_counts_values_of_low_cardinality_fields():
    raw = json.dumps(_pods(500, at7={"phase": "Failed"}))
    marker = next(p for p in _json(raw, 500) if "_all_items" in p)
    assert marker["_all_items"]["value_counts"]["phase"] == {'"Running"': 499, '"Failed"': 1}


def test_a_rare_value_is_promoted_in_place_with_its_reason():
    text = _text(json.dumps(_pods(500, at312={"phase": "CrashLoopBackOff"})), 500)
    assert "pod-0312" in text and "CrashLoopBackOff" in text and "$[312]" in text


def test_an_error_key_only_one_item_has_is_promoted():
    assert "pod-0250" in _text(json.dumps(_pods(500, at250={"error": "OOMKilled"})), 500)


def test_a_false_boolean_everyone_shares_promotes_nothing():
    assert not any("_next_item_shown_because" in p for p in _json(json.dumps(_pods(500)), 500))


def test_a_value_matching_the_query_is_promoted_only_when_the_query_is_used():
    raw, args = json.dumps(_pods(500)), {"name": "pod-0377"}
    assert "pod-0377" in _text(raw, 500, args)
    assert "pod-0377" not in _text(raw, 500, args, use_query=False)


def test_jsonl_is_folded_as_one_array():
    raw = "\n".join(json.dumps(p) for p in _pods(300, at100={"phase": "Evicted"}))
    folded = fold(raw, budget_tokens=300)
    assert folded is not None and folded.branch == "jsonl"
    assert folded.body.startswith("JSONL shown as one array of 300 records; index i is line i+1;")
    assert "pod-0100" in folded.body


def test_jsonl_with_blank_lines_does_not_claim_index_i_is_line_i_plus_1():
    rows = [json.dumps(p) for p in _pods(300, at150={"phase": "Failed"})]
    folded = fold("\n" + "\n\n".join(rows) + "\n", budget_tokens=300)
    assert folded is not None and folded.branch == "jsonl"
    assert "blank lines are skipped, so index i is not line i+1" in folded.body.splitlines()[0]
    assert "$[150]" in folded.body  # the path still names the record, for jq -s


def test_a_jsonl_record_may_hold_characters_that_splitlines_splits_on():
    rows = [json.dumps({"name": f"pod-{i:04d}", "note": "a\u2028b"}, ensure_ascii=False) for i in range(300)]
    folded = fold("\n".join(rows), budget_tokens=300)
    assert folded is not None and folded.branch == "jsonl"


def test_a_folded_json_path_resolves_to_what_it_names():
    value = {"pods": _pods(500)}
    assert resolve(value, "$.pods[40]")["name"] == "pod-0040"
    assert [p["name"] for p in resolve(value, "$.pods[10:12]")] == ["pod-0010", "pod-0011"]
    with pytest.raises(RecoveryError, match="its keys are: pods"):
        resolve(value, "$.items")


def test_a_repeated_line_pattern_collapses_to_one_line_and_a_count():
    raw = "\n".join(f"2026-11-03T10:00:{i % 60:02d}Z INFO heartbeat ok seq={i}" for i in range(1000))
    text = _text(raw, 200)
    assert "repeated 999 more times, lines 2-1000" in text and len(text) / 4 < 100


def test_an_error_line_in_the_middle_is_kept_with_its_window():
    lines = _log(2000)
    lines[1000] = "2026-11-03T10:16:40Z ERROR payment failed order=needle-42"
    tight = _text("\n".join(lines), 500)
    assert "needle-42" in tight and len(tight) / 4 <= 500  # the line survives inside the budget
    roomy = _text("\n".join(lines), 2000)
    assert lines[997] in roomy and lines[1003] in roomy  # with room, its window too


def test_gap_markers_name_the_lines_they_hide():
    lines = _log(2000)
    shown = _text("\n".join(lines), 500).split("\n")
    for a, b in re.findall(r"lines (\d+)-(\d+) omitted", "\n".join(shown)):
        assert lines[int(a) - 2] in shown and lines[int(a) - 1] not in shown  # shown, then hidden
        assert int(b) == len(lines) or lines[int(b)] in shown


def test_long_text_with_few_lines_is_cut_by_characters():
    folded = fold("x" * 50_000, budget_tokens=500)
    assert folded is not None and folded.branch == "text" and "omitted" in folded.body


def test_html_keeps_headings_and_text_and_drops_scripts_and_chrome():
    raw = (
        "<html><head><title>T</title><script>var secret = 1;</script></head><body>"
        "<nav><ul><li>Home<li>About</ul></nav>"
        "<h2>Retries</h2><p>We retry <a href='/docs/429'>on 429</a>.</p><footer>(c) corp</footer>"
        "<p>After the footer</p></body></html>"
    )
    text = html_to_text(raw)
    assert "## Retries" in text and "on 429 (/docs/429)" in text
    assert "secret" not in text and "Home" not in text and "corp" not in text
    assert "After the footer" in text


def test_detect():
    assert detect('{"a": 1}') == "json"
    assert detect("<!doctype html><html><body>hi</body></html>") == "html"
    assert detect("\n".join(_log(100))) == "lines"
    assert detect("word " * 5000) == "text"


def test_folding_that_saves_little_passes_through():
    raw = json.dumps([{f"k{j}": j for j in range(7)} for _ in range(2)])  # two short items: nothing to fold
    assert fold(raw, budget_tokens=10) is None


def test_the_last_line_of_a_stack_trace_counts_as_an_error():
    lines = _log(2000)
    lines[1000] = "ValueError: order total is negative (needle-7)"
    assert "needle-7" in _text("\n".join(lines), 500)


def test_a_query_term_most_items_share_promotes_nothing():
    raw = json.dumps([{"repo": "bh-02", "owner": "bruk-io", "sha": f"{i:040x}"} for i in range(60)])
    items = _json(raw, 200, {"owner": "bruk-io", "repo": "bh-02"})
    assert not any("_next_item_shown_because" in p for p in items)


def test_forcing_a_branch_that_does_not_exist_names_the_ones_that_do():
    with pytest.raises(ValueError, match="json, xml, html, outline, lines, text"):
        fold("x" * 50_000, budget_tokens=100, force="yaml")


def _jsx_diff() -> str:
    hunks = "".join(
        f' export function Row{i}() {{\n-  return <div className="row"><span>{i}</span></div>;\n'
        f'+  return <div className="row"><span>{i + 1}</span></div>;\n }}\n'
        for i in range(60)
    )
    head = "diff --git a/src/App.jsx b/src/App.jsx\n--- a/src/App.jsx\n+++ b/src/App.jsx\n"
    return f"{head}@@ -1,40 +1,40 @@\n{hunks}"


def test_text_that_only_contains_tags_is_not_html():
    badges = "".join(f'<a href="https://ci/{i}"><img src="https://badge/{i}.svg"></a>\n' for i in range(25))
    readme = "# Project\n\n" + badges + "".join(f"Paragraph {i} of prose.\n" for i in range(200))
    html_diff = (
        "diff --git a/index.html b/index.html\n@@ -1,5 +1,5 @@\n <!doctype html>\n <html>\n"
        + "".join(f"-<p>old {i}</p>\n+<p>new {i}</p>\n" for i in range(100))
    )
    assert [detect(t) for t in (_jsx_diff(), readme, html_diff)] == ["lines"] * 3
    assert "<span>59</span>" in _text(_jsx_diff(), 300)  # the code around the tags is kept


def test_pages_and_fragments_are_still_html():
    page = "<!DOCTYPE html>\n<html><body>" + "".join(f"<div><p>para {i}</p></div>\n" for i in range(100))
    cards = "".join(
        f'<div class="card">\n  <span>item {i}</span>\n  Text for item {i}\n</div>\n' for i in range(100)
    )
    packed = "<div>" + "".join(f"<p>para <b>{i}</b> text<br></p>" for i in range(300)) + "</div>"
    assert [detect(t) for t in (page, cards, packed)] == ["html"] * 3
