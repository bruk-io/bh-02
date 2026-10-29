"""`scripts/cache-efficiency` over hand-written session directories: the hit rate of a steady
conversation, a break sorted as an expiry or as one inside the cache's lifetime (with what changed the
prefix named), sub-agents apart, steps without usable usage left out, and nothing written."""

import datetime
import json
import os
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

_SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "cache-efficiency"
_START = datetime.datetime(2026, 10, 29, 10, 0, tzinfo=datetime.UTC)

type Entry = dict[str, Any]


def _stamp(seconds: float) -> str:
    return (_START + datetime.timedelta(seconds=seconds)).isoformat().replace("+00:00", "Z")


def step(
    start: float,
    *,
    total: int,
    read: int,
    written: int = 0,
    took: float = 5.0,
    model: str = "m1",
    cost: float = 0.01,
    settings: Mapping[str, Any] | None = None,
    usage: Mapping[str, Any] | None = None,
) -> Entry:
    """An assistant entry whose step began `start` seconds after 10:00 and took `took`."""
    record: dict[str, Any] = {
        "at": _stamp(start),
        "took": took,
        "model": model,
        "usage": usage
        if usage is not None
        else {
            "input_tokens": total,
            "output_tokens": 10,
            "cache_read_input_tokens": read,
            "cache_creation_input_tokens": written,
            "cost_usd": cost,
        },
    }
    if settings is not None:
        record["settings"] = dict(settings)
    return {"role": "assistant", "content": "", "step": record}


def _write(path: Path, entries: Sequence[Entry]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(e) + "\n" for e in entries))


def _run(sessions: Path, *args: str) -> dict[str, Any]:
    ran = subprocess.run(
        [sys.executable, str(_SCRIPT), "--sessions", str(sessions), "--json", *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(ran.stdout)


def _one(sessions: Path, entries: Sequence[Entry], *args: str, runs: Sequence[float] = ()) -> dict[str, Any]:
    """Run the script over one session with `entries` as its transcript; return its session figures."""
    _write(sessions / "s1" / "transcript.jsonl", entries)
    if runs:
        _write(sessions / "s1" / "rows.jsonl", [{"at": _stamp(r), "kind": "run"} for r in runs])
    return _run(sessions, *args)["sessions"][0]


SETTINGS = {"model": "e/m1", "provider": "claude-code"}


def test_a_steady_conversation_has_no_break_and_its_hit_rate(tmp_path: Path) -> None:
    entries = [
        step(0, total=1000, read=0, written=1000, settings=SETTINGS),
        step(10, total=1100, read=1000, written=100),
        step(20, total=1300, read=1100, written=200),
    ]
    found = _one(tmp_path, entries)
    assert found["steps"] == 3
    assert found["breaks"] == {"expiry": 0, "inside": 0}
    assert found["input_tokens"] == 3400
    assert found["cache_read_input_tokens"] == 2100
    assert found["cache_creation_input_tokens"] == 1300
    assert found["hit_rate"] == 2100 / 3400
    assert found["write_share"] == 1300 / 3400
    assert round(found["cost_usd"], 6) == 0.03


def test_the_first_step_of_a_conversation_cannot_break(tmp_path: Path) -> None:
    found = _one(tmp_path, [step(0, total=5000, read=0, written=5000)])
    assert found["breaks"] == {"expiry": 0, "inside": 0}


def test_a_long_gap_is_an_expiry(tmp_path: Path) -> None:
    entries = [step(0, total=1000, read=0, written=1000), step(1000, total=1100, read=0, written=1100)]
    found = _one(tmp_path, entries)
    assert found["breaks"] == {"expiry": 1, "inside": 0}
    (broke,) = found["break_list"]
    assert broke["kind"] == "expiry"
    assert broke["gap_seconds"] == 995  # from the end of the first step (5s) to the second
    assert broke["cause"] is None


def test_the_lifetime_is_a_flag(tmp_path: Path) -> None:
    entries = [step(0, total=1000, read=0, written=1000), step(1000, total=1100, read=0, written=1100)]
    found = _one(tmp_path, entries, "--ttl", "3600")
    assert found["breaks"] == {"expiry": 0, "inside": 1}


def test_a_read_just_under_the_threshold_breaks_and_one_over_does_not(tmp_path: Path) -> None:
    entries = [
        step(0, total=1000, read=0, written=1000),
        step(10, total=1000, read=950, written=50),  # over 90% of 1000
        step(20, total=1000, read=800, written=200),  # under 90% of 1000
    ]
    found = _one(tmp_path, entries)
    assert found["breaks"] == {"expiry": 0, "inside": 1}
    assert found["break_list"][0]["cause"] == "none found (the provider?)"


def test_a_system_edit_before_a_short_gap_break_is_its_cause(tmp_path: Path) -> None:
    entries = [
        {"role": "system", "content": "prompt"},
        step(0, total=1000, read=0, written=1000),
        {"role": "system", "edits": [{"at": 1, "drop": 0, "add": ["more"]}]},
        step(10, total=1100, read=0, written=1100),
    ]
    (broke,) = _one(tmp_path, entries)["break_list"]
    assert broke["kind"] == "inside"
    assert broke["cause"] == "system prompt edited"


def test_a_tools_entry_is_the_nearest_cause_over_an_older_edit(tmp_path: Path) -> None:
    entries = [
        step(0, total=1000, read=0, written=1000),
        {"role": "system", "edits": [{"at": 1, "drop": 0, "add": ["more"]}]},
        {"role": "tools", "added": [{"name": "grep"}]},
        step(10, total=1100, read=0, written=1100),
    ]
    (broke,) = _one(tmp_path, entries)["break_list"]
    assert broke["cause"] == "tools entry (added grep)"


def test_a_seed_in_a_compacted_session_is_the_cause(tmp_path: Path) -> None:
    old = [
        {"role": "system", "content": "prompt"},
        step(0, total=50000, read=0, written=50000),
        step(10, total=50500, read=50000, written=500),
    ]
    new = [
        {"role": "system", "content": "prompt"},
        {"role": "user", "content": "summary", "seed": {"keep": "all"}},
        step(30, total=3000, read=0, written=3000),
    ]
    _write(tmp_path / "s1" / "transcript.jsonl.bak", old)
    _write(tmp_path / "s1" / "transcript.jsonl", new)
    found = _run(tmp_path)["sessions"][0]
    assert found["steps"] == 3
    (broke,) = found["break_list"]
    assert broke["kind"] == "inside"
    assert broke["cause"] == "seed (/compact)"


def test_the_first_step_after_a_clear_is_a_new_conversation(tmp_path: Path) -> None:
    _write(tmp_path / "s1" / "transcript.jsonl.bak", [step(0, total=9000, read=0, written=9000)])
    _write(tmp_path / "s1" / "transcript.jsonl", [step(30, total=1000, read=0, written=1000)])
    assert _run(tmp_path)["sessions"][0]["breaks"] == {"expiry": 0, "inside": 0}


def test_a_settings_change_is_a_model_switch(tmp_path: Path) -> None:
    other = {"model": "e/m2", "provider": "claude-code"}
    entries = [
        step(0, total=1000, read=0, written=1000, settings=SETTINGS),
        step(10, total=1100, read=0, written=1100, settings=other, model="m2"),
    ]
    (broke,) = _one(tmp_path, entries)["break_list"]
    assert broke["cause"] == "settings changed (model e/m1 -> e/m2)"


def test_a_run_start_between_two_steps_is_a_resume(tmp_path: Path) -> None:
    entries = [step(0, total=1000, read=0, written=1000), step(60, total=1100, read=0, written=1100)]
    (broke,) = _one(tmp_path, entries, runs=[-5, 30])["break_list"]
    assert broke["kind"] == "inside"
    assert broke["cause"].startswith("resume")


def test_a_run_start_outside_the_two_steps_is_not_a_resume(tmp_path: Path) -> None:
    entries = [step(0, total=1000, read=0, written=1000), step(60, total=1100, read=0, written=1100)]
    (broke,) = _one(tmp_path, entries, runs=[-5])["break_list"]
    assert broke["cause"] == "none found (the provider?)"


def test_sub_agents_are_reported_apart_from_their_parent(tmp_path: Path) -> None:
    _write(
        tmp_path / "s1" / "transcript.jsonl",
        [step(0, total=1000, read=0, written=1000), step(10, total=1100, read=1000, written=100)],
    )
    _write(
        tmp_path / "s1" / "agents" / "scout" / "transcript.jsonl",
        [
            step(2, total=400, read=0, written=400, model="m2"),
            step(12, total=500, read=0, written=500, model="m2"),
        ],
    )
    data = _run(tmp_path)
    own, sub = data["sessions"]
    assert (own["agent"], own["steps"], own["breaks"]["inside"]) == (None, 2, 0)
    assert (sub["agent"], sub["steps"], sub["breaks"]["inside"]) == ("scout", 2, 1)
    assert [(m["model"], m["sub_agents"], m["steps"]) for m in data["models"]] == [
        ("m1", False, 2),
        ("m2", True, 2),
    ]


def test_missing_and_partial_usage_is_left_out_and_counted(tmp_path: Path) -> None:
    bare = step(10, total=0, read=0)
    del bare["step"]["usage"]
    partial = step(20, total=1100, read=1000, usage={"input_tokens": 1100, "partial": True})
    entries = [
        step(0, total=1000, read=0, written=1000),
        bare,
        partial,
        step(30, total=1200, read=0, written=1200),  # follows a left-out step: not judged
    ]
    found = _one(tmp_path, entries)
    assert found["steps"] == 2
    assert found["left_out"] == 2
    assert found["input_tokens"] == 2200
    assert found["breaks"] == {"expiry": 0, "inside": 0}


def test_json_has_every_figure_and_per_model_totals(tmp_path: Path) -> None:
    entries = [
        step(0, total=1000, read=0, written=1000),
        step(10, total=1100, read=0, written=1100, model="m2"),
    ]
    _write(tmp_path / "s1" / "transcript.jsonl", entries)
    data = _run(tmp_path)
    assert data["ttl_seconds"] == 300
    assert data["threshold"] == 0.9
    figures = {
        "steps",
        "left_out",
        "input_tokens",
        "cache_read_input_tokens",
        "cache_creation_input_tokens",
        "output_tokens",
        "hit_rate",
        "write_share",
        "breaks",
        "cost_usd",
        "cost_per_step",
    }
    assert figures <= data["sessions"][0].keys()
    assert all(figures <= m.keys() for m in data["models"])
    assert {m["model"]: m["breaks"]["inside"] for m in data["models"]} == {"m1": 0, "m2": 1}
    assert data["breaks"][0]["model"] == "m2"
    assert {"at", "gap_seconds", "kind", "cause", "cache_read_input_tokens"} <= data["breaks"][0].keys()


def test_the_text_report_lists_the_latest_breaks(tmp_path: Path) -> None:
    _write(
        tmp_path / "s1" / "transcript.jsonl",
        [step(0, total=1000, read=0, written=1000), step(10, total=1100, read=0, written=1100)],
    )
    ran = subprocess.run(
        [sys.executable, str(_SCRIPT), "--sessions", str(tmp_path)],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "per session" in ran.stdout
    assert "per model" in ran.stdout
    assert "cache breaks, the latest:" in ran.stdout
    assert "inside: none found (the provider?)" in ran.stdout


def _listing(root: Path) -> dict[str, tuple[int, int]]:
    return {
        str(p.relative_to(root)): (p.stat().st_mtime_ns, p.stat().st_size) for p in sorted(root.rglob("*"))
    }


def test_the_script_writes_nothing_into_a_session(tmp_path: Path) -> None:
    session = tmp_path / "s1"
    _write(
        session / "transcript.jsonl",
        [step(0, total=1000, read=0, written=1000), step(10, total=1100, read=0)],
    )
    _write(session / "transcript.jsonl.bak", [step(0, total=10, read=0)])
    _write(session / "agents" / "a" / "transcript.jsonl", [step(0, total=10, read=0)])
    _write(session / "rows.jsonl", [{"at": _stamp(0), "kind": "run"}])
    for path in [*session.rglob("*")]:
        os.utime(path, (1_000_000, 1_000_000))
    before = _listing(tmp_path)
    _run(tmp_path)
    subprocess.run(
        [sys.executable, str(_SCRIPT), "--sessions", str(tmp_path)], check=True, capture_output=True
    )
    assert _listing(tmp_path) == before
