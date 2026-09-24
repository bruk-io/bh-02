"""Unit tests for `brig.mech.seatbelt.profile`: the pure `Spec -> SBPL text`
render (task-058). Golden by literal comparison (decision-018), ordering as
an assertion independent of the golden, an AST purity scan proving the
golden has no filesystem dependency, the three named refusals, the
`jail_dir` lexical guard with its discriminating control, and the
`network-bind` conditionality asserted by exact count in both directions.

task-058's own AC #8 mutation check (move the write_denies emission loop
above the write_allows loop in `brig/mech/seatbelt/profile.py`) is a
scratch-copy exercise against THIS file's ordering and golden tests,
recorded in the task's Evidence notes rather than shipped as code here --
mutating the source under test is not something a permanent test performs
on itself.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from brig.core import Channel, ChannelKind, FsPolicy, ReadModel, Spec
from brig.mech.seatbelt.profile import (
    ChannelInsideWriteDeny,
    ReadModelUnsupported,
    UnresolvedPath,
    render_sbpl,
)

_PROFILE_PATH = (
    Path(__file__).resolve().parents[2] / "src" / "brig" / "mech" / "seatbelt" / "profile.py"
)

# --------------------------------------------------------------------------
# AC #2: the golden fixture -- one Spec carrying a workspace (write_allow),
# one write_deny, one read_deny, one LISTEN channel. Every raw Spec path
# below is deliberately the darwin-symlinked SHORTHAND ("/tmp/...") while
# `_GOLDEN_RESOLVED` maps each to its "/private/tmp/..." resolved form --
# so the golden also proves the render emits the RESOLVED text, never the
# raw Spec path (a render that accidentally used the raw path would still
# produce *a* profile, just not one that matches this fixture).
# --------------------------------------------------------------------------

_GOLDEN_JAIL_DIR = "/private/tmp/bg1"

_GOLDEN_SPEC = Spec(
    fs=FsPolicy(
        write_allows=("/tmp/bg1/workspace",),
        write_denies=("/tmp/bg1/workspace/.git/hooks",),
        read_denies=("/Users/dev/.ssh",),
    ),
    channels=(Channel(name="control", kind=ChannelKind.LISTEN, endpoint="/tmp/bg1/control.sock"),),
)

_GOLDEN_RESOLVED = {
    "/tmp/bg1/workspace": "/private/tmp/bg1/workspace",
    "/tmp/bg1/workspace/.git/hooks": "/private/tmp/bg1/workspace/.git/hooks",
    "/Users/dev/.ssh": "/Users/dev/.ssh",
    "/tmp/bg1/control.sock": "/private/tmp/bg1/control.sock",
}

_EXPECTED_GOLDEN_PROFILE = """\
(version 1)
(deny default)
(import "system.sb")
(allow process-exec*)
(allow process-fork)
(allow signal (target self))
(allow file-read* (subpath "/"))
(deny file-read* (subpath "/Users/dev/.ssh"))
(deny file-write* (subpath "/"))
(allow file-write* (subpath "/private/tmp/bg1/workspace"))
(deny file-write* (subpath "/private/tmp/bg1/workspace/.git/hooks"))
(allow file-write* (literal "/private/tmp/bg1/control.sock"))
(allow network-bind)
(deny network* (with no-log))
"""


@pytest.mark.unit
def test_golden_full_profile_literal_comparison() -> None:
    """AC #2 (decision-018): the WHOLE rendered string compared with `==`
    against a here-doc expected profile -- not a substring scan, not a
    line-subset check."""
    rendered = render_sbpl(_GOLDEN_SPEC, resolved=_GOLDEN_RESOLVED, jail_dir=_GOLDEN_JAIL_DIR)
    assert rendered == _EXPECTED_GOLDEN_PROFILE


# --------------------------------------------------------------------------
# AC #3: ordering, independent of the golden's string equality -- a
# dedicated Spec with TWO write_allows and TWO write_denies, so "spec
# order" and the deny-over-allow precedence are both exercised on more
# than one entry each.
# --------------------------------------------------------------------------

_ORDER_JAIL_DIR = "/private/tmp/order"
_ORDER_SPEC = Spec(
    fs=FsPolicy(
        write_allows=("/private/tmp/order/a", "/private/tmp/order/b"),
        write_denies=("/private/tmp/order/a/.git/hooks", "/private/tmp/order/b/.envrc"),
    ),
)
_ORDER_RESOLVED = {
    "/private/tmp/order/a": "/private/tmp/order/a",
    "/private/tmp/order/b": "/private/tmp/order/b",
    "/private/tmp/order/a/.git/hooks": "/private/tmp/order/a/.git/hooks",
    "/private/tmp/order/b/.envrc": "/private/tmp/order/b/.envrc",
}


@pytest.mark.unit
def test_ordering_write_deny_after_write_allow_and_import_before_every_rule() -> None:
    """AC #3, both halves:

    1. The smallest line index among the per-entry write-DENY subpath
       rules is greater than the largest line index among the per-entry
       write-ALLOW subpath rules -- deny-over-allow precedence. Scoped to
       PER-ENTRY rules: the whole-tree `(deny file-write* (subpath "/"))`
       default line is excluded by name, because it sits BEFORE
       write_allows and a naive "starts with '(deny file-write*'" match
       would make this assertion false on a CORRECT render.
    2. The `(import "system.sb")` line has a smaller index than every
       RULE line -- excluding `(deny default)` by name, since this
       module's own docstring states that line deliberately precedes the
       import (the darwin SIGABRT dialect fact), and excluding
       `(version 1)`, a format header rather than a policy rule.
    """
    rendered = render_sbpl(_ORDER_SPEC, resolved=_ORDER_RESOLVED, jail_dir=_ORDER_JAIL_DIR)
    lines = rendered.splitlines()

    import_idx = next(i for i, line in enumerate(lines) if line == '(import "system.sb")')

    rule_idxs = [
        i
        for i, line in enumerate(lines)
        if (line.startswith("(allow ") or line.startswith("(deny ")) and line != "(deny default)"
    ]
    assert rule_idxs, "expected at least one policy rule line"
    assert import_idx < min(rule_idxs)

    allow_write_idxs = [
        i for i, line in enumerate(lines) if line.startswith("(allow file-write* (subpath ")
    ]
    deny_write_idxs = [
        i
        for i, line in enumerate(lines)
        if line.startswith("(deny file-write* (subpath ")
        and line != '(deny file-write* (subpath "/"))'
    ]
    assert len(allow_write_idxs) == 2
    assert len(deny_write_idxs) == 2
    assert min(deny_write_idxs) > max(allow_write_idxs)


# --------------------------------------------------------------------------
# AC #4: purity. Same ast-parsed, top-level-only technique as
# tests/unit/test_mech_events_purity.py, over profile.py alone, against
# this task's own named banned set (deliberately a DIFFERENT set than that
# file's -- this task's AC #5 names os, os.path, pathlib, subprocess,
# shutil, sys explicitly).
# --------------------------------------------------------------------------

_BANNED_IMPORT_NAMES = frozenset({"os", "os.path", "pathlib", "subprocess", "shutil", "sys"})


def _top_level_imported_modules(source: str) -> set[str]:
    tree = ast.parse(source)
    modules: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            modules.add(node.module)
    return modules


@pytest.mark.unit
def test_profile_module_import_set_excludes_filesystem_and_process_modules() -> None:
    """AC #4: an AST scan of brig/mech/seatbelt/profile.py's top-level
    imports contains none of os, os.path, pathlib, subprocess, shutil,
    sys -- so the golden test above has no filesystem dependency at all."""
    actual = _top_level_imported_modules(_PROFILE_PATH.read_text())
    overlap = actual & _BANNED_IMPORT_NAMES
    assert not overlap, (
        f"brig/mech/seatbelt/profile.py top-level-imports banned module(s): {overlap}"
    )


# --------------------------------------------------------------------------
# AC #5: refusals, each naming its subject.
# --------------------------------------------------------------------------


@pytest.mark.unit
def test_refuses_allow_list_read_model_naming_the_model() -> None:
    spec = Spec(fs=FsPolicy(read_model=ReadModel.ALLOW_LIST))
    with pytest.raises(ReadModelUnsupported, match=r"ReadModel\.ALLOW_LIST"):
        render_sbpl(spec, resolved={}, jail_dir="/private/tmp/x")


@pytest.mark.unit
def test_refuses_unresolved_write_allow_naming_that_path() -> None:
    spec = Spec(fs=FsPolicy(write_allows=("/private/tmp/x/workspace",)))
    with pytest.raises(UnresolvedPath, match=re.escape("/private/tmp/x/workspace")):
        render_sbpl(spec, resolved={}, jail_dir="/private/tmp/x")


@pytest.mark.unit
def test_refuses_channel_inside_write_deny_naming_both_paths() -> None:
    spec = Spec(
        fs=FsPolicy(
            write_allows=("/private/tmp/x/workspace",),
            write_denies=("/private/tmp/x/workspace/.git",),
        ),
        channels=(
            Channel(
                name="control",
                kind=ChannelKind.LISTEN,
                endpoint="/private/tmp/x/workspace/.git/control.sock",
            ),
        ),
    )
    resolved = {
        "/private/tmp/x/workspace": "/private/tmp/x/workspace",
        "/private/tmp/x/workspace/.git": "/private/tmp/x/workspace/.git",
        "/private/tmp/x/workspace/.git/control.sock": (
            "/private/tmp/x/workspace/.git/control.sock"
        ),
    }
    with pytest.raises(ChannelInsideWriteDeny) as exc_info:
        render_sbpl(spec, resolved=resolved, jail_dir="/private/tmp/x")
    message = str(exc_info.value)
    resolved_endpoint = "/private/tmp/x/workspace/.git/control.sock"
    deny_root = "/private/tmp/x/workspace/.git"
    # deny_root is a literal substring of resolved_endpoint in this fixture
    # (that's the point being tested), so a plain `path in message` check on
    # deny_root is vacuous -- it would still pass a mutant that dropped
    # deny_root from the message entirely, since resolved_endpoint's own text
    # contains it. repr() disambiguates: repr(deny_root) closes its quote
    # immediately after ".git", so it is NOT a substring of
    # repr(resolved_endpoint), where ".git" is followed by "/control.sock"
    # before the closing quote. Each assertion below is independently
    # falsifiable by a mutant that drops that one path from the message.
    assert repr(deny_root) not in repr(resolved_endpoint)
    assert repr(resolved_endpoint) in message
    assert repr(deny_root) in message


# --------------------------------------------------------------------------
# AC #6: the jail_dir invariant -- a LEXICAL guard, plus its control.
# --------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize("root", ["/tmp", "/var", "/etc"])
def test_refuses_jail_dir_with_a_symlinked_root_leading_component(root: str) -> None:
    """CompileCtx's docstring states the caller supplies a realpath'd
    jail_dir; this render refuses (UnresolvedPath) when jail_dir's leading
    component is one of darwin's known symlinked roots -- a LEXICAL guard,
    not a realpath comparison (a pure render cannot lstat). No filesystem
    read on either side of this assertion."""
    with pytest.raises(UnresolvedPath, match=re.escape(root)):
        render_sbpl(Spec(), resolved={}, jail_dir=f"{root}/bg1")


@pytest.mark.unit
def test_control_a_private_tmp_jail_dir_does_not_refuse() -> None:
    """The discriminating control for the guard above: `/private/tmp/bg1`
    is the RESOLVED form of `/tmp/bg1` and must NOT trip the lexical
    guard -- proving the guard discriminates the documented trap shape
    rather than refusing everything textually containing "tmp". No
    filesystem read on either side."""
    rendered = render_sbpl(Spec(), resolved={}, jail_dir="/private/tmp/bg1")
    assert rendered.startswith("(version 1)\n")


# --------------------------------------------------------------------------
# AC #7: network-bind conditionality, asserted by exact count in both
# directions. The third case -- a MAILBOX-only control proving the
# conditionality was keyed on LISTEN specifically rather than on "any
# channel at all" -- went with `MAILBOX` itself (decision-153): `LISTEN`
# is the only `ChannelKind` there is, so "declares a LISTEN channel" and
# "declares a channel" are the same condition and there is no third case.
# --------------------------------------------------------------------------


@pytest.mark.unit
def test_network_bind_renders_exactly_once_with_one_listen_channel() -> None:
    spec = Spec(
        channels=(Channel(name="c", kind=ChannelKind.LISTEN, endpoint="/private/tmp/x/c.sock"),)
    )
    resolved = {"/private/tmp/x/c.sock": "/private/tmp/x/c.sock"}
    rendered = render_sbpl(spec, resolved=resolved, jail_dir="/private/tmp/x")
    assert rendered.splitlines().count("(allow network-bind)") == 1


@pytest.mark.unit
def test_network_bind_renders_exactly_zero_times_with_no_channels() -> None:
    rendered = render_sbpl(Spec(), resolved={}, jail_dir="/private/tmp/x")
    assert rendered.splitlines().count("(allow network-bind)") == 0
