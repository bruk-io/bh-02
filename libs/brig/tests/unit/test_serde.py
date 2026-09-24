"""Spec serialization: `to_dict`/`from_dict`, versioned, round-trip stable.

SPEC.md section 5's serialization clause; task-007's deliverable. See
`brig/core/spec.py` for the pinned dict format (top-level keys, enum-as-
string, pair tuples as two-element lists) and the four `from_dict` failure
modes (missing version, wrong version, unknown key, bogus enum string).
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from hypothesis import given

from brig.core.spec import (
    SPEC_VERSION,
    Channel,
    ChannelKind,
    EnvMode,
    EnvPolicy,
    FsPolicy,
    Limits,
    NetworkPolicy,
    Provisioning,
    ReadModel,
    Spec,
    UnsupportedSpecVersion,
)
from tests.unit.strategies import specs

# ---------------------------------------------------------------------------
# A fully-populated Spec (every field non-empty, a channel present) used as
# the fixture for the non-vacuity pin (AC #4) and the enum-string pin
# (AC #6) -- a Spec built from defaults would leave every enum at its
# default member, which is exactly the case a hardcoded string literal in
# to_dict would still pass.
# ---------------------------------------------------------------------------


def _populated_spec() -> Spec:
    return Spec(
        fs=FsPolicy(
            write_allows=("/a",),
            write_denies=("/b",),
            read_model=ReadModel.ALLOW_LIST,
            read_denies=(),
            read_allows=("/c",),
        ),
        network=NetworkPolicy(allowed_domains=("example.com",)),
        limits=Limits(
            wall_seconds=1, cpu_seconds=2, memory_bytes=3, max_tasks=4, max_output_bytes=5
        ),
        # mode=SCRUB (not PASS): task-033/decision-064 made allow_names
        # inert-and-refused under PASS, so a populated allow_names and a
        # non-default mode can no longer both appear on one EnvPolicy --
        # keeping allow_names non-empty here matters to this fixture's
        # every-leaf-populated purpose; mode's own non-default reachability
        # is pinned separately in test_to_dict_enums_serialize_as_value_strings_*.
        env=EnvPolicy(mode=EnvMode.SCRUB, allow_names=("PATH",), set=(("KEY", "value"),)),
        channels=(Channel(name="ch1", kind=ChannelKind.LISTEN, endpoint="ep1"),),
        shared_media=("/shared",),
        provisioning=Provisioning(
            files=(("/f", "deadbeef"),), closures=("clo",), env=(("E", "v"),)
        ),
    )


def _walk_json_native(value: Any) -> None:
    """Recursively assert `value` contains only JSON-native Python types:
    dict, list, str, int, bool, None -- never a tuple, an Enum member, or a
    set. `json.dumps` alone does not catch a stray tuple (it serializes a
    tuple as a JSON array with no complaint), so this walk is the actual
    proof that AC #3's "no tuples, no enum objects, no sets" holds.
    """
    if isinstance(value, dict):
        for k, v in value.items():
            assert type(k) is str
            _walk_json_native(v)
    elif isinstance(value, list):
        for item in value:
            _walk_json_native(item)
    else:
        assert type(value) in (str, int, bool, type(None)), (
            f"non-JSON-native value {value!r} of type {type(value)!r}"
        )


# ---------------------------------------------------------------------------
# AC #2: round-trip property via to_dict/from_dict directly.
# ---------------------------------------------------------------------------


@pytest.mark.unit
@given(s=specs())
def test_ec1_dict_round_trip(s: Spec) -> None:
    assert Spec.from_dict(s.to_dict()) == s


# ---------------------------------------------------------------------------
# AC #3: JSON round-trip property. json.dumps/loads is necessary but not
# sufficient to prove JSON-nativeness (it happily serializes a tuple as a
# list, so a stray tuple in to_dict's output would sail through this
# property unnoticed) -- the `_walk_json_native` pass below is what actually
# proves no tuples/enums/sets survive into the dict, and
# `json.loads(json.dumps(d)) == d` is what would catch a tuple (a tuple and
# the list json.loads produces from it are never ==).
# ---------------------------------------------------------------------------


@pytest.mark.unit
@given(s=specs())
def test_ec1_json_round_trip(s: Spec) -> None:
    d = s.to_dict()
    _walk_json_native(d)
    reloaded = json.loads(json.dumps(d))
    assert reloaded == d  # would fail if `d` held a tuple json.dumps silently flattened
    assert Spec.from_dict(reloaded) == s


@pytest.mark.unit
def test_to_dict_json_dumps_alone_would_not_catch_a_tuple() -> None:
    """Documents the trap AC #3 warns about: json.dumps serializes a tuple
    exactly like a list, with no error and no distinguishing output."""
    assert json.dumps((1, 2)) == json.dumps([1, 2])


# ---------------------------------------------------------------------------
# AC #4: non-vacuity pin. Exact key sets, hardcoded (not derived from
# dataclasses.fields, which would make this vacuous against the same class
# of bug it exists to catch), at the top level and inside every nested
# policy dict, including a channel entry.
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_to_dict_exact_key_sets() -> None:
    d = _populated_spec().to_dict()

    assert d["version"] == SPEC_VERSION
    assert set(d.keys()) == {
        "version",
        "fs",
        "network",
        "limits",
        "env",
        "channels",
        "shared_media",
        "provisioning",
    }
    assert set(d["fs"].keys()) == {
        "write_allows",
        "write_denies",
        "read_model",
        "read_denies",
        "read_allows",
    }
    assert set(d["network"].keys()) == {"allowed_domains"}
    assert set(d["limits"].keys()) == {
        "wall_seconds",
        "cpu_seconds",
        "memory_bytes",
        "max_tasks",
        "max_output_bytes",
    }
    assert set(d["env"].keys()) == {"mode", "allow_names", "set"}
    assert set(d["provisioning"].keys()) == {"files", "closures", "env"}

    assert len(d["channels"]) == 1
    assert set(d["channels"][0].keys()) == {"name", "kind", "endpoint"}


# ---------------------------------------------------------------------------
# AC #6: enums serialize as their .value string, never the member name and
# never an int. Both the non-default members (deny_list/scrub/listen are
# the *default* ReadModel/EnvMode members and ChannelKind.LISTEN specifically
# -- a hardcoded literal would pass those alone) and their opposite members
# are pinned, so a to_dict that hardcodes a string literal instead of
# reading `.value` cannot pass both halves.
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_to_dict_enums_serialize_as_value_strings_default_members() -> None:
    spec = Spec(
        fs=FsPolicy(read_model=ReadModel.DENY_LIST),
        env=EnvPolicy(mode=EnvMode.SCRUB),
        channels=(Channel(name="ch", kind=ChannelKind.LISTEN, endpoint="ep"),),
    )
    d = spec.to_dict()

    assert d["fs"]["read_model"] == "deny_list"
    assert isinstance(d["fs"]["read_model"], str)
    assert d["env"]["mode"] == "scrub"
    assert isinstance(d["env"]["mode"], str)
    assert d["channels"][0]["kind"] == "listen"
    assert isinstance(d["channels"][0]["kind"], str)


@pytest.mark.unit
def test_to_dict_enums_serialize_as_value_strings_other_members() -> None:
    spec = Spec(
        fs=FsPolicy(read_model=ReadModel.ALLOW_LIST),
        env=EnvPolicy(mode=EnvMode.PASS),
        channels=(Channel(name="ch", kind=ChannelKind.LISTEN, endpoint="ep"),),
    )
    d = spec.to_dict()

    assert d["fs"]["read_model"] == "allow_list"
    assert isinstance(d["fs"]["read_model"], str)
    assert d["env"]["mode"] == "pass"
    assert isinstance(d["env"]["mode"], str)
    # `ChannelKind` has one member since decision-153, so there is no
    # "other member" of it left to exercise -- the value-string assertion
    # still belongs here beside the other two enums.
    assert d["channels"][0]["kind"] == "listen"
    assert isinstance(d["channels"][0]["kind"], str)


# ---------------------------------------------------------------------------
# AC #7: from_dict's four failure modes, each with its own type and each
# naming the offender in its message.
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_from_dict_missing_version_raises_plain_value_error() -> None:
    d = Spec().to_dict()
    del d["version"]

    with pytest.raises(ValueError, match=r"missing required key 'version'") as exc_info:
        Spec.from_dict(d)

    # UnsupportedSpecVersion subclasses ValueError, so pin the exact type:
    # a from_dict that raised UnsupportedSpecVersion here for the wrong
    # reason would still pass a bare pytest.raises(ValueError).
    assert type(exc_info.value) is ValueError


@pytest.mark.unit
def test_from_dict_wrong_version_raises_unsupported_spec_version() -> None:
    d = Spec().to_dict()
    d["version"] = 2

    with pytest.raises(UnsupportedSpecVersion, match=r"unsupported version 2, expected 1"):
        Spec.from_dict(d)


@pytest.mark.unit
def test_from_dict_unknown_top_level_key_raises_value_error_naming_it() -> None:
    d = Spec().to_dict()
    d["bogus_top_level_key"] = "x"

    with pytest.raises(ValueError, match="bogus_top_level_key"):
        Spec.from_dict(d)


@pytest.mark.unit
def test_from_dict_unknown_nested_key_raises_value_error_naming_it() -> None:
    d = Spec().to_dict()
    d["fs"]["bogus_nested_key"] = "x"

    with pytest.raises(ValueError, match="bogus_nested_key"):
        Spec.from_dict(d)


@pytest.mark.unit
def test_from_dict_unknown_key_in_channel_entry_raises_value_error_naming_it() -> None:
    d = _populated_spec().to_dict()
    d["channels"][0]["bogus_channel_key"] = "x"

    with pytest.raises(ValueError, match="bogus_channel_key"):
        Spec.from_dict(d)


@pytest.mark.unit
def test_from_dict_bogus_enum_value_raises_value_error_naming_it() -> None:
    d = Spec().to_dict()
    d["fs"]["read_model"] = "not_a_real_read_model"

    with pytest.raises(ValueError, match="not_a_real_read_model"):
        Spec.from_dict(d)


@pytest.mark.unit
def test_from_dict_bogus_env_mode_value_raises_value_error_naming_it() -> None:
    d = Spec().to_dict()
    d["env"]["mode"] = "not_a_real_env_mode"

    with pytest.raises(ValueError, match="not_a_real_env_mode"):
        Spec.from_dict(d)


@pytest.mark.unit
def test_from_dict_bogus_channel_kind_value_raises_value_error_naming_it() -> None:
    d = _populated_spec().to_dict()
    d["channels"][0]["kind"] = "not_a_real_channel_kind"

    with pytest.raises(ValueError, match="not_a_real_channel_kind"):
        Spec.from_dict(d)


# ---------------------------------------------------------------------------
# AC #8: from_dict re-validates. A hand-built dict that violates a
# task-003 construction rule (DENY_LIST with a non-empty read_allows) must
# raise ValueError from the normal Spec/FsPolicy construction path, not
# merely from from_dict's own key/enum checking -- the `match=` pins the
# actual FsPolicy.__post_init__ message so a differently-worded ValueError
# raised by from_dict's own bookkeeping could not pass this test by
# accident.
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_from_dict_revalidates_illegal_spec_via_normal_construction() -> None:
    d = Spec().to_dict()
    d["fs"]["read_model"] = "deny_list"
    d["fs"]["read_allows"] = ["/should/not/be/allowed/under/deny_list"]

    with pytest.raises(ValueError, match=r"read_allows must be empty when read_model is DENY_LIST"):
        Spec.from_dict(d)
