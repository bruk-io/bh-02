"""What the frame says, as plain values: usage totals, the model field, the palette's entries."""

from dataclasses import dataclass, field
from typing import Any

from tui_cordis_plugin import frame


def test_usage_sums_turn_by_turn_and_shows_cost_once_there_is_one() -> None:
    total = frame.add_usage(frame.Usage(), {"input_tokens": 900, "output_tokens": 40})
    assert frame.usage_text(total) == "900 in · 40 out"
    total = frame.add_usage(total, {"input_tokens": 12_000, "output_tokens": 60, "cost_usd": 0.02})
    total = frame.add_usage(total, {"input_tokens": 100, "output_tokens": 0, "cost_usd": 0.01})
    assert total == frame.Usage(13_000, 100, 0.03)
    assert frame.usage_text(total) == "13k in · 100 out · $0.0300"
    assert frame.usage_text(frame.Usage(2_500_000, 3)) == "2.5M in · 3 out"


def test_usage_says_how_much_input_came_from_the_prompt_cache_once_some_did() -> None:
    total = frame.add_usage(frame.Usage(), {"input_tokens": 6381, "output_tokens": 4, "cost_usd": 0.008})
    total = frame.add_usage(
        total, {"input_tokens": 6393, "output_tokens": 5, "cost_usd": 0.0007, "cache_read_input_tokens": 6378}
    )
    assert total.cached_tokens == 6378
    assert frame.usage_forms(total) == ("13k in · 6,378 cached · 9 out · $0.0087", "12k/9 $0.01")


def test_usage_s_short_form_keeps_each_count_in_a_few_cells_and_the_cost_in_cents() -> None:
    assert frame.usage_forms(frame.Usage(12_345, 678, 0.1234)) == (
        "12k in · 678 out · $0.1234",
        "12k/678 $0.12",
    )
    assert frame.usage_forms(frame.Usage(1234, 5))[1] == "1.2k/5"
    assert frame.usage_forms(frame.Usage(2_500_000, 10_500))[1] == "2.5M/10k"


@dataclass
class _Entry:
    id: str
    config: dict[str, Any] = field(default_factory=dict)


def test_the_model_is_what_the_models_value_says_the_model_row_names() -> None:
    assert frame.model_text({"name": "qwen3", "provider": "openai"}) == ("qwen3", "openai")
    assert frame.model_text({"name": "typo", "provider": ""}) == ("typo", "")  # no model there is
    assert frame.model_text({}) == ("none", "")
    assert frame.model_forms(("qwen3", "openai"), "up") == ("qwen3 (openai)", "qwen3")
    assert frame.model_forms(("typo", ""), "up") == ("typo",)


def test_the_model_field_says_starting_from_the_row_s_unloading_until_it_is_active() -> None:
    """A `/model` replacement: unloading, the old fiber inactive, the new one's reload, and
    (for the Claude stack's `/clear`) a second reload as the loop comes back, then active."""
    phase = frame.phase_of("active")
    sonnet = ("sonnet", "claude-code")
    assert frame.model_forms(sonnet, phase) == ("sonnet (claude-code)", "sonnet")
    seen = []
    for kind in ("unloading", "unbind", "inactive", "reload", "unloading", "reload", "bind", "active"):
        phase = frame.phase_after(kind, phase)
        seen.append(frame.model_forms(sonnet, phase)[0])
    assert seen == [*["sonnet (claude-code, starting…)"] * 7, "sonnet (claude-code)"]
    assert frame.model_forms(sonnet, frame.phase_after("reload", "up"))[1] == "sonnet…"  # narrow
    assert frame.model_forms(sonnet, frame.phase_after("failed", "starting")) == (
        "sonnet (claude-code, failed)",
        "sonnet ✗",
    )
    assert frame.model_forms(("typo", ""), "starting") == ("typo (starting…)", "typo…")


def test_the_model_field_stops_saying_starting_once_the_row_is_down_for_good() -> None:
    """A layer edit that removes or disables the row: unloading, then inactive with the row
    no longer listed. The program shutting down: cancelled."""
    assert frame.phase_after("inactive", "starting", listed=False) == "up"
    assert frame.phase_after("inactive", "starting", listed=True) == "starting"  # a replacement
    assert frame.phase_after("cancelled", "starting") == "up"


def test_a_row_is_listed_while_the_layers_name_it_enabled() -> None:
    @dataclass
    class Entry:
        id: str
        disabled: bool = False

    assert frame.listed([Entry("loop")], "loop")
    assert not frame.listed([Entry("loop", disabled=True)], "loop")
    assert not frame.listed([Entry("kernel")], "loop")


def test_the_first_push_reads_the_row_s_phase_from_the_loader_s_status() -> None:
    assert [frame.phase_of(s) for s in ("loading", "unloading", "inactive")] == ["starting"] * 3
    assert frame.phase_of("active, work failed: RuntimeError()") == "up"
    assert frame.phase_of("failed: ValueError()") == frame.phase_of("unresolved: no plugin") == "failed"
    assert frame.phase_of(None) == frame.phase_of("disabled") == "up"  # nothing to wait for


def test_a_row_is_starting_from_its_unloading_until_it_is_active_or_down_for_good() -> None:
    starting: frozenset[str] = frozenset()
    for kind, row in [("unloading", "loop"), ("unloading", "chat"), ("inactive", "chat"), ("bind", "x")]:
        starting = frame.starting_after(starting, kind, row)
    assert starting == {"loop"}  # the chat row is down, not coming up: it follows the model
    assert frame.starting_after(starting, "reload", "kernel") == {"loop", "kernel"}
    assert frame.starting_after(starting, "active", "loop") == frozenset()
    assert frame.starting_after(starting, "failed-inactive", "loop") == frozenset()


def test_no_line_waits_on_a_row_heard_coming_up_binding_no_key() -> None:
    """`status` binds no key, so no line waits on it, not even while it first comes up;
    `kernel` binds one, and a kernel heard binding (even one whose reload came before the ui
    listened) is waited on when it comes up again."""
    keyless = frame.Keyless()
    for kind, row in [("bind", "kernel"), ("active", "kernel"), ("reload", "status")]:
        keyless = frame.keyless_after(keyless, kind, row)
    assert keyless.unwaited == {"status"}  # its first setup: nothing bound yet
    keyless = frame.keyless_after(keyless, "active", "status")
    assert keyless.unwaited == keyless.rows == {"status"}
    for kind, row in [("reload", "kernel"), ("reload", "status")]:  # a /clear
        keyless = frame.keyless_after(keyless, kind, row)
    assert keyless.unwaited == {"status"}  # the kernel is waited on from its reload
    keyless = frame.keyless_after(keyless, "active", "early")  # came up unheard
    assert "early" not in keyless.unwaited
    changed = frame.keyless_after(frame.keyless_after(keyless, "bind", "status"), "active", "status")
    assert "status" not in changed.unwaited  # a row that now binds a key is waited on


def test_a_held_row_is_held_through_its_restart_until_it_is_up() -> None:
    """A row announced as restarting is expected, begins at its unloading, is expected again
    at the `inactive` inside a restart (its new fiber comes next), and is let go once it is up
    or down for good; an event of a row not held changes nothing."""
    held = frame.Held(expected=frozenset({"loop", "kernel"}))
    held = frame.held_after(held, "unloading", "loop")
    assert held == frame.Held(frozenset({"kernel"}), frozenset({"loop"}))
    held = frame.held_after(held, "inactive", "loop")
    assert held == frame.Held(frozenset({"kernel", "loop"}))  # not let go: the new one comes
    for kind in ("reload", "active"):
        held = frame.held_after(held, kind, "loop")
    assert held == frame.Held(frozenset({"kernel"})) and held.rows == {"kernel"}
    assert frame.held_after(held, "reload", "status") == held  # not held: not taken on
    assert frame.held_after(held, "failed", "kernel").rows == frozenset()


def test_the_palette_offers_every_command_then_help_and_exit_once_each() -> None:
    specs = [
        {"name": "rows", "help": "the rows", "usage": ""},
        {"name": "model", "help": "switch model", "usage": "[NAME]"},
        {"name": "help", "help": "a second help", "usage": ""},
    ]
    entries = frame.palette_entries(specs)
    assert [e.call for e in entries] == ["/rows", "/model", "/help", "/exit"]
    assert [e.takes_arguments for e in entries] == [False, True, False, False]
    assert entries[2].help == "a second help"  # the first offer of a name wins


def test_a_command_s_choices_are_entries_of_their_own_read_each_time() -> None:
    offered = [{"args": "haiku", "help": "switch to haiku"}, {"args": "", "help": "no args: skipped"}]

    def broken() -> list[dict[str, str]]:
        raise ValueError("the models file is not TOML")

    specs = [
        {"name": "model", "help": "list or switch", "usage": "[NAME]", "choices": lambda: offered},
        {"name": "other", "help": "x", "usage": "", "choices": broken},
    ]
    entries = frame.palette_entries(specs)
    assert [e.call for e in entries] == ["/model", "/model haiku", "/other", "/help", "/exit"]
    assert entries[1].help == "switch to haiku" and not entries[1].takes_arguments  # runs at once
    offered.append({"args": "opus", "help": "switch to opus"})  # a model added since
    assert "/model opus" in [e.call for e in frame.palette_entries(specs)]


def test_a_turn_stopped_before_its_output_was_counted_makes_the_totals_lower_bounds() -> None:
    read = {"type": "usage", "input_tokens": 900, "output_tokens": 0, "cost_usd": 0.001, "partial": True}
    rest = {"type": "usage", "input_tokens": 0, "output_tokens": 40, "cost_usd": 0.0002}
    whole = frame.total_usage([read, rest, {"type": "turn_end"}])  # the count came: exact
    assert whole.uncounted == 0 and frame.usage_text(whole) == "900 in · 40 out · $0.0012"
    stopped = frame.total_usage([read, rest, {"type": "turn_end"}, read, {"type": "turn_end"}])
    assert stopped.uncounted == 1
    assert frame.usage_forms(stopped) == ("1,800 in · 40+ out · $0.0022+", "1.8k/40+ $0.00+")
    carried = frame.add_usage(frame.Usage(), {"type": "carried", "input_tokens": 5, "uncounted": 2})
    assert carried.uncounted == 2  # a trimmed history keeps it
