import json
import re

from compressors.html import html_to_text
from compressors.recovery import recover
from compressors.route import compress, detect


def _pods(n: int, **overrides_at: dict) -> list[dict]:
    pods = [
        {"name": f"pod-{i:04d}", "phase": "Running", "ready": True, "deleted": False, "restarts": i % 3}
        for i in range(n)
    ]
    for idx, fields in overrides_at.items():
        pods[int(idx.removeprefix("at"))].update(fields)
    return pods


def _folded_json(c) -> object:
    return json.loads(c.text.split("\n", 1)[1])


def test_small_results_pass_through_untouched():
    c = compress("Bash", {}, "hello\n" * 10)
    assert c.branch == "passthrough"
    assert c.text == "hello\n" * 10
    assert c.call_id is None


def test_a_long_array_stays_an_array_and_shows_head_tail_and_markers():
    raw = json.dumps({"pods": _pods(500)})
    c = compress("get_pods", {}, raw, budget_tokens=500)
    assert c.branch == "json"
    pods = _folded_json(c)["pods"]
    assert isinstance(pods, list)
    assert pods[0]["name"] == "pod-0000"
    assert pods[-1]["name"] == "pod-0499"
    assert any("_folded" in p and "$.pods[2:499]" in p["_folded"] for p in pods)
    assert c.out_tokens < c.raw_tokens / 10


def test_the_summary_counts_values_of_low_cardinality_fields():
    raw = json.dumps(_pods(500, at7={"phase": "Failed"}))
    marker = next(p for p in _folded_json(compress("t", {}, raw, budget_tokens=500)) if "_all_items" in p)
    assert marker["_all_items"]["value_counts"]["phase"] == {'"Running"': 499, '"Failed"': 1}


def test_a_rare_value_is_promoted_in_place_with_its_reason():
    raw = json.dumps(_pods(500, at312={"phase": "CrashLoopBackOff"}))
    c = compress("t", {}, raw, budget_tokens=500)
    assert "pod-0312" in c.text
    assert "CrashLoopBackOff" in c.text
    assert "$[312]" in c.text


def test_an_error_key_only_one_item_has_is_promoted():
    raw = json.dumps(_pods(500, at250={"error": "OOMKilled"}))
    assert "pod-0250" in compress("t", {}, raw, budget_tokens=500).text


def test_a_false_boolean_everyone_shares_promotes_nothing():
    raw = json.dumps(_pods(500))
    pods = _folded_json(compress("t", {}, raw, budget_tokens=500))
    assert not any("_next_item_shown_because" in p for p in pods)


def test_a_value_matching_the_query_is_promoted_only_when_the_query_is_used():
    raw = json.dumps(_pods(500))
    args = {"name": "pod-0377"}
    assert "pod-0377" in compress("t", args, raw, budget_tokens=500).text
    assert "pod-0377" not in compress("t", args, raw, budget_tokens=500, use_query=False).text


def test_jsonl_is_folded_as_one_array():
    raw = "\n".join(json.dumps(p) for p in _pods(300, at100={"phase": "Evicted"}))
    c = compress("t", {}, raw, budget_tokens=300)
    assert c.branch == "json"
    assert "JSONL" in c.text
    assert "pod-0100" in c.text


def test_recovery_reads_a_folded_slice_by_path():
    raw = json.dumps({"pods": _pods(500)})
    assert json.loads(recover(raw, "$.pods[40]"))["name"] == "pod-0040"
    assert [p["name"] for p in json.loads(recover(raw, "$.pods[10:12]"))] == ["pod-0010", "pod-0011"]


def test_recovery_says_what_keys_exist_when_a_key_is_wrong():
    out = recover(json.dumps({"pods": []}), "$.items")
    assert out.startswith("recover:")
    assert "pods" in out


def test_recovery_greps_json():
    raw = json.dumps({"pods": _pods(50, at20={"phase": "Evicted"})})
    assert "$.pods[20]" in recover(raw, "grep:evicted")


def _log(n: int) -> list[str]:
    paths = ["/api/items", "/api/users", "/health", "/api/orders", "/static/app.js"]
    return [
        f"2026-11-03T10:{i // 60 % 60:02d}:{i % 60:02d}Z INFO GET {paths[i * 7 % 5]} 200" for i in range(n)
    ]


def test_a_repeated_line_pattern_collapses_to_one_line_and_a_count():
    raw = "\n".join(f"2026-11-03T10:00:{i % 60:02d}Z INFO heartbeat ok seq={i}" for i in range(1000))
    c = compress("Bash", {}, raw, budget_tokens=200)
    assert c.branch == "lines"
    assert "repeated 999 more times, lines 2-1000" in c.text
    assert c.out_tokens < 100


def test_an_error_line_in_the_middle_is_kept_with_its_window():
    lines = _log(2000)
    lines[1000] = "2026-11-03T10:16:40Z ERROR payment failed order=needle-42"
    c = compress("Bash", {}, "\n".join(lines), budget_tokens=500)
    assert "needle-42" in c.text
    assert lines[997] in c.text and lines[1003] in c.text


def test_gap_markers_name_the_lines_recovery_returns():
    raw = "\n".join(_log(2000))
    c = compress("Bash", {}, raw, budget_tokens=500)
    first, last = map(int, re.search(r"lines (\d+)-(\d+) omitted", c.text).groups())
    out = recover(raw, f"lines:{first}-{first + 1}").splitlines()
    assert out == [f"{first}: {raw.splitlines()[first - 1]}", f"{first + 1}: {raw.splitlines()[first]}"]
    assert last > first


def test_long_text_with_few_lines_is_cut_by_characters():
    raw = "x" * 50_000
    c = compress("WebFetch", {}, raw, budget_tokens=500)
    assert c.branch == "text"
    assert "omitted" in c.text
    assert recover(raw, "chars:100-110") == "x" * 10


def test_html_keeps_headings_and_text_and_drops_scripts_and_chrome():
    raw = (
        "<html><head><title>T</title><script>var secret = 1;</script></head><body>"
        "<nav><ul><li>Home<li>About</ul></nav>"
        "<h2>Retries</h2><p>We retry <a href='/docs/429'>on 429</a>.</p><footer>(c) corp</footer>"
        "<p>After the footer</p></body></html>"
    )
    text = html_to_text(raw)
    assert "## Retries" in text
    assert "on 429 (/docs/429)" in text
    assert "secret" not in text and "Home" not in text and "corp" not in text
    assert "After the footer" in text


def test_detect():
    assert detect('{"a": 1}') == "json"
    assert detect("<!doctype html><html><body>hi</body></html>") == "html"
    assert detect("\n".join(_log(100))) == "lines"
    assert detect("word " * 5000) == "text"


def test_folding_that_saves_little_passes_through():
    raw = json.dumps([{"k": "v" * 50} for _ in range(5)] * 1)  # five items: nothing to fold
    c = compress("t", {}, raw, budget_tokens=10)
    assert c.branch == "passthrough"


def test_the_last_line_of_a_stack_trace_counts_as_an_error():
    lines = _log(2000)
    lines[1000] = "ValueError: order total is negative (needle-7)"
    assert "needle-7" in compress("Bash", {}, "\n".join(lines), budget_tokens=500).text
