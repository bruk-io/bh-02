"""Unit tests for `brig.mech.bwrap`: the linux mechanism's pure render.

Every test here is host-independent and runs on every platform, which is
the point: `Bwrap.compile` is a pure function of `(spec, ctx)`, so the
whole argv can be pinned as a GOLDEN on a darwin laptop with no `bwrap`
binary anywhere on it. What cannot be checked this way -- that the argv
actually confines anything -- is `tests/integration/test_bwrap_fs.py`'s and
`tests/e2e/test_strict_linux_journey.py`'s, and those skip by name off
linux.

Every `CompileCtx` below is built by hand with the LITERAL string
`"linux"`, never `sys.platform`, and with literal `resolved_paths` /
`path_exists` mappings, never a real filesystem: a render that needed one
would have stopped being pure (SPEC.md §6's own discriminating question --
"can a mechanism's render golden run with no filesystem?").
"""

from __future__ import annotations

import re

import pytest

import brig.stack
from brig.core import (
    Axis,
    Channel,
    ChannelKind,
    FsPolicy,
    Grade,
    NetworkPolicy,
    ReadModel,
    Spec,
)
from brig.mech import CompileCtx
from brig.mech.bwrap import (
    DEFAULT_BWRAP_PATH,
    Bwrap,
    ChannelInsideWriteDeny,
    NetworkUnsupported,
    PlatformUnsupported,
    ReadModelUnsupported,
    UnknownPathExistence,
    UnknownPathKind,
    UnresolvedPath,
    bwrap,
)
from brig.mech.env_scrub import env_scrub
from brig.mech.rlimits import rlimits
from brig.run.launcher import _derive_wrap_prefix
from brig.stack import Stack

_JAIL_DIR = "/run/brig/jail0"


def _ctx(
    *,
    resolved: dict[str, str] | None = None,
    exists: dict[str, bool] | None = None,
    platform: str = "linux",
) -> CompileCtx:
    return CompileCtx(
        jail_dir=_JAIL_DIR,
        platform=platform,
        resolved_paths=resolved or {},
        path_exists=exists or {},
    )


def _identity_resolved(*paths: str) -> dict[str, str]:
    """`resolved_paths` for a spec whose paths contain no symlink -- the
    common case, written out rather than defaulted so the render's lookup
    is always exercised (a missing key is a refusal, never a fallback)."""
    return {path: path for path in paths}


#: The one spec every golden below is taken against: an allowlist read
#: model, one write root, two carve-outs (one that exists, one that does
#: not -- the two `write_denies` forms), and one LISTEN channel.
_WORKSPACE = "/srv/ws"
_HOOKS = "/srv/ws/.git/hooks"
_ENVRC = "/srv/ws/.envrc"
_ENDPOINT = "/run/brig/jail0/agent.sock"

_SPEC = Spec(
    fs=FsPolicy(
        read_model=ReadModel.ALLOW_LIST,
        read_allows=("/bin", "/usr"),
        write_allows=(_WORKSPACE,),
        write_denies=(_HOOKS, _ENVRC),
    ),
    channels=(Channel(name="agent", kind=ChannelKind.LISTEN, endpoint=_ENDPOINT),),
)
_SPEC_RESOLVED = _identity_resolved("/bin", "/usr", _WORKSPACE, _HOOKS, _ENVRC, _ENDPOINT)
_SPEC_EXISTS = {
    "/bin": True,
    "/usr": True,
    _WORKSPACE: True,
    _HOOKS: True,
    _ENVRC: False,
    _ENDPOINT: False,
}


def _spec_ctx() -> CompileCtx:
    return _ctx(resolved=_SPEC_RESOLVED, exists=_SPEC_EXISTS)


# --------------------------------------------------------------------------
# Axes: pinned as data, so a later widening is a visible diff.
# --------------------------------------------------------------------------


@pytest.mark.unit
def test_axes_is_exactly_fs_read_fs_write_network() -> None:
    """The three axes the SPEC.md §6 roster row's "fs (allowlist-capable),
    network (netns)" names, and nothing else. `channel_exclusivity` is
    explicitly NOT claimed, for the reason decision-118 gives for seatbelt:
    binding a channel's directory is WORK this mechanism does, not the axis
    about declared channels and enumerated shared media being the only ways
    in and out, which a mount namespace does not establish."""
    assert bwrap.axes == frozenset({Axis.FS_READ, Axis.FS_WRITE, Axis.NETWORK})
    assert Axis.CHANNEL_EXCLUSIVITY not in bwrap.axes
    assert Axis.LIMITS not in bwrap.axes
    assert Axis.ENV not in bwrap.axes


# --------------------------------------------------------------------------
# The golden argv, and the mount order it encodes.
# --------------------------------------------------------------------------


@pytest.mark.unit
def test_golden_argv_for_the_reference_spec() -> None:
    """The whole compiled command line, pinned element by element.

    This is the file's centre of gravity: every ordering claim the module
    docstring makes is visible here as a position, so a reordering that
    reads harmlessly in a diff cannot pass. Read it against the seven
    stages in `brig/mech/bwrap.py`'s own docstring."""
    step = bwrap.compile(_SPEC, _spec_ctx())

    assert step.wrap(("/bin/true", "arg")) == (
        DEFAULT_BWRAP_PATH,
        "--unshare-all",
        # Stage 2: the jail's own furniture, before anything spec-derived.
        "--proc",
        "/proc",
        "--dev",
        "/dev",
        # Stage 3: the readable tree (allowlist), in the Spec's own sorted
        # order -- `FsPolicy.__post_init__` already sorted it.
        "--ro-bind",
        "/bin",
        "/bin",
        "--ro-bind",
        "/usr",
        "/usr",
        # Stage 4: the declared LISTEN channel's own DIRECTORY, read-write,
        # BEFORE the write roots -- decision-163. It is the one mount whose
        # path policy did not choose, so it is the one that may contain
        # them; last, it stacked over the carve-outs and unmade them.
        "--bind",
        "/run/brig/jail0",
        "/run/brig/jail0",
        # Stage 5: the writable roots, over the read-only tree and the
        # channel directory.
        "--bind",
        _WORKSPACE,
        _WORKSPACE,
        # Stage 6: the carve-outs, AFTER stage 5 -- deny-over-allow by
        # mount order. `.envrc` does not exist, so it is the tmpfs form;
        # `.git/hooks` does, so it is the read-only bind form.
        "--tmpfs",
        _ENVRC,
        "--remount-ro",
        _ENVRC,
        "--ro-bind",
        _HOOKS,
        _HOOKS,
        "--",
        "/bin/true",
        "arg",
    )


@pytest.mark.unit
def test_write_denies_are_emitted_after_every_write_allow() -> None:
    """SPEC.md §5's deny-over-allow precedence, expressed here as the one
    thing that makes it true under bwrap: position. Asserted on INDEX, not
    on membership, so moving the `write_denies` loop above the
    `write_allows` loop fails here as well as in the golden above."""
    argv = bwrap.compile(_SPEC, _spec_ctx()).wrap(())

    allow_at = argv.index(_WORKSPACE)
    assert argv.index(_ENVRC) > allow_at
    assert argv.index(_HOOKS) > allow_at


@pytest.mark.unit
def test_the_channel_directory_is_bound_before_the_write_roots() -> None:
    """decision-163. The channel directory is the one mount whose path
    policy does not choose, so it is the one that can turn out to CONTAIN a
    write root or a carve-out -- a jail dir holding the workspace is the
    ordinary shape. Bound LAST (as it was until 2026-09-08) it stacked
    read-write over the carve-outs inside it and silently unmade them;
    bound here it can only be stacked ON.

    Asserted on INDEX, not membership: moving the channel loop back below
    the write roots fails here as well as in the golden above. The pairing
    that would reverse the channel in the other direction -- an endpoint
    UNDER a `write_denies` subpath -- is refused outright rather than
    ordered around; see the refusal test."""
    argv = bwrap.compile(_SPEC, _spec_ctx()).wrap(())

    channel_at = argv.index("/run/brig/jail0")
    assert channel_at < argv.index(_WORKSPACE)
    assert channel_at < argv.index(_HOOKS)
    assert channel_at < argv.index(_ENVRC)


@pytest.mark.unit
def test_a_carve_out_inside_the_channel_directory_still_wins() -> None:
    """The defect decision-163 closed, as its own regression: a jail
    directory that HOLDS the workspace. The carve-out must be the LAST word
    on its own path, not a mount the channel bind stacks over."""
    jail_dir = "/run/brig/jail9"
    workspace = f"{jail_dir}/ws"
    hooks = f"{workspace}/.git/hooks"
    endpoint = f"{jail_dir}/agent.sock"
    spec = Spec(
        fs=FsPolicy(
            read_model=ReadModel.ALLOW_LIST,
            read_allows=("/usr",),
            write_allows=(workspace,),
            write_denies=(hooks,),
        ),
        channels=(Channel(name="agent", kind=ChannelKind.LISTEN, endpoint=endpoint),),
    )
    ctx = _ctx(
        resolved=_identity_resolved("/usr", workspace, hooks, endpoint),
        exists={"/usr": True, workspace: True, hooks: True, endpoint: False},
    )

    argv = bwrap.compile(spec, ctx).wrap(())

    assert argv.index(jail_dir) < argv.index(workspace) < argv.index(hooks)


@pytest.mark.unit
def test_two_channels_in_one_directory_bind_that_directory_once() -> None:
    """Deduped on the DESTINATION directory: two channels beside each other
    in the jail dir are one mount, not two identical ones."""
    endpoint_b = "/run/brig/jail0/second.sock"
    spec = Spec(
        fs=FsPolicy(read_model=ReadModel.ALLOW_LIST, read_allows=("/usr",)),
        channels=(
            Channel(name="a", kind=ChannelKind.LISTEN, endpoint=_ENDPOINT),
            Channel(name="b", kind=ChannelKind.LISTEN, endpoint=endpoint_b),
        ),
    )
    ctx = _ctx(
        resolved=_identity_resolved("/usr", _ENDPOINT, endpoint_b),
        exists={"/usr": True, _ENDPOINT: False, endpoint_b: False},
    )

    argv = bwrap.compile(spec, ctx).wrap(())

    assert argv.count("/run/brig/jail0") == 2  # one `--bind SRC DEST` pair


@pytest.mark.unit
def test_a_symlinked_path_mounts_the_resolved_source_at_the_spec_s_own_path() -> None:
    """The SRC/DEST split, which is load-bearing in both directions: the
    SOURCE is the realpath'd form (so the mount carries the tree the path
    actually points at) and the DESTINATION is the path the `Spec` wrote
    (so `/bin/sh` still resolves inside a jail on a merged-`/usr` host,
    where `/bin` is a symlink to `usr/bin`)."""
    spec = Spec(fs=FsPolicy(read_model=ReadModel.ALLOW_LIST, read_allows=("/bin",)))
    ctx = _ctx(resolved={"/bin": "/usr/bin"}, exists={"/bin": True})

    argv = bwrap.compile(spec, ctx).wrap(())

    assert argv[argv.index("--ro-bind") :][:3] == ("--ro-bind", "/usr/bin", "/bin")


@pytest.mark.unit
def test_wrap_is_a_pure_argv_prefix_verified_by_derive_wrap_prefix() -> None:
    """`handle.exec` (SPEC.md §9) reproduces a stack's confinement on a
    sibling by prepending the derived prefix, and refuses outright when the
    wrap is not one. Every probe runs through `exec`, so this is not a
    stylistic property. Checked with the launcher's own real
    `_derive_wrap_prefix` rather than a restatement of it."""
    argv = ("/bin/sh", "-c", "echo hi")
    wrapped = bwrap.compile(_SPEC, _spec_ctx()).wrap(argv)

    prefix = _derive_wrap_prefix(wrapped, argv)

    assert prefix is not None
    assert prefix + argv == wrapped
    assert prefix[-1] == "--"


@pytest.mark.unit
def test_the_bwrap_binary_is_absolute_and_overridable() -> None:
    """Absolute by default (a bare name resolves through whatever `PATH`
    the launching process carries -- authority no `Spec` granted), and a
    constructor argument because unlike `sandbox-exec` this binary is not
    shipped by the OS."""
    assert DEFAULT_BWRAP_PATH.startswith("/")

    argv = Bwrap("/opt/bin/bwrap").compile(_SPEC, _spec_ctx()).wrap(())

    assert argv[0] == "/opt/bin/bwrap"


# --------------------------------------------------------------------------
# The refusals: six, each naming its own subject (SPEC.md §2 law 2).
# --------------------------------------------------------------------------


@pytest.mark.unit
def test_a_non_linux_platform_is_refused_by_name() -> None:
    with pytest.raises(PlatformUnsupported, match="darwin"):
        bwrap.compile(_SPEC, _ctx(resolved=_SPEC_RESOLVED, exists=_SPEC_EXISTS, platform="darwin"))


@pytest.mark.unit
def test_a_denylist_spec_is_refused_rather_than_translated() -> None:
    """SPEC.md §5: the two read models are declared, not layered. bwrap is
    the allowlist half; compiling a denylist through it would mean masking
    each denied path with a mount, and a mount cannot mask a path that is
    not there yet."""
    spec = Spec(fs=FsPolicy(read_model=ReadModel.DENY_LIST, read_denies=("/home/u/.ssh",)))

    with pytest.raises(ReadModelUnsupported, match="DENY_LIST"):
        bwrap.compile(spec, _ctx())


@pytest.mark.unit
def test_granted_domains_are_refused_because_a_netns_is_deny_all() -> None:
    spec = Spec(
        fs=FsPolicy(read_model=ReadModel.ALLOW_LIST),
        network=NetworkPolicy(allowed_domains=("api.example.com",)),
    )

    with pytest.raises(NetworkUnsupported, match=re.escape("api.example.com")):
        bwrap.compile(spec, _ctx())


@pytest.mark.unit
def test_a_path_missing_from_resolved_paths_is_refused_naming_it() -> None:
    """Never the lexical fallback (decision-115): a rule written against an
    unresolved path is the silent no-op this arrangement exists to
    prevent."""
    spec = Spec(fs=FsPolicy(read_model=ReadModel.ALLOW_LIST, read_allows=("/opt/tools",)))

    with pytest.raises(UnresolvedPath, match="/opt/tools"):
        bwrap.compile(spec, _ctx(exists={"/opt/tools": True}))


@pytest.mark.unit
def test_a_write_deny_missing_from_path_exists_is_refused_naming_it() -> None:
    """decision-159's own refusal. The render cannot choose between the
    bind form and the tmpfs form without knowing, and a guess is how a
    carve-out silently stops holding."""
    spec = Spec(
        fs=FsPolicy(
            read_model=ReadModel.ALLOW_LIST,
            write_allows=(_WORKSPACE,),
            write_denies=(_ENVRC,),
        )
    )
    ctx = _ctx(resolved=_identity_resolved(_WORKSPACE, _ENVRC), exists={_WORKSPACE: True})

    with pytest.raises(UnknownPathExistence, match=re.escape(".envrc")):
        bwrap.compile(spec, ctx)


@pytest.mark.unit
def test_a_channel_endpoint_under_a_write_deny_is_refused() -> None:
    """Compiling the pair would put the socket under a read-only carve-out
    (the carve-outs are stage 6, the channel directory stage 4); compiling
    it the other way round would hand the jail a socket path it can never
    create. Refused by name, both paths named -- the same refusal seatbelt
    makes on its own side."""
    endpoint = "/srv/ws/.git/hooks/agent.sock"
    spec = Spec(
        fs=FsPolicy(
            read_model=ReadModel.ALLOW_LIST,
            write_allows=(_WORKSPACE,),
            write_denies=(_HOOKS,),
        ),
        channels=(Channel(name="agent", kind=ChannelKind.LISTEN, endpoint=endpoint),),
    )
    ctx = _ctx(
        resolved=_identity_resolved(_WORKSPACE, _HOOKS, endpoint),
        exists={_WORKSPACE: True, _HOOKS: True, endpoint: False},
    )

    with pytest.raises(ChannelInsideWriteDeny) as refusal:
        bwrap.compile(spec, ctx)

    assert endpoint in str(refusal.value)
    assert _HOOKS in str(refusal.value)


@pytest.mark.unit
def test_a_write_deny_of_the_whole_tree_swallows_every_channel() -> None:
    """The degenerate carve-out: `write_denies` naming the root. Every
    resolved path lies under `/`, so the channel refusal fires -- which is
    the honest answer (a spec that denies writing anywhere cannot also
    grant a socket) rather than a jail whose channel silently never
    binds."""
    spec = Spec(
        fs=FsPolicy(
            read_model=ReadModel.ALLOW_LIST,
            write_allows=(_WORKSPACE,),
            write_denies=("/",),
        ),
        channels=(Channel(name="agent", kind=ChannelKind.LISTEN, endpoint=_ENDPOINT),),
    )
    ctx = _ctx(
        resolved=_identity_resolved(_WORKSPACE, "/", _ENDPOINT),
        exists={_WORKSPACE: True, "/": True, _ENDPOINT: False},
    )

    with pytest.raises(ChannelInsideWriteDeny):
        bwrap.compile(spec, ctx)


# --------------------------------------------------------------------------
# Grades and denial signatures.
# --------------------------------------------------------------------------


@pytest.mark.unit
def test_the_three_grades_are_enforced_and_their_details_carry_the_load() -> None:
    """The grade details are load-bearing text, not prose: `allowlist`
    names the read model a reader of a report must not mistake for
    seatbelt's denylist, `write_denies` names the carve-out policy, and
    `unshare` names the whole of the network claim."""
    grades = bwrap.compile(_SPEC, _spec_ctx()).grades

    assert grades[Axis.FS_READ].grade is Grade.ENFORCED
    assert "allowlist" in grades[Axis.FS_READ].detail
    assert grades[Axis.FS_WRITE].grade is Grade.ENFORCED
    assert "write_denies" in grades[Axis.FS_WRITE].detail
    assert grades[Axis.NETWORK].grade is Grade.ENFORCED
    assert "unshare" in grades[Axis.NETWORK].detail
    assert set(grades) == {Axis.FS_READ, Axis.FS_WRITE, Axis.NETWORK}


@pytest.mark.unit
def test_the_fs_write_detail_names_the_channel_directory_it_makes_writable() -> None:
    """The one path that is writable and is in no `write_allows` entry.
    Naming it only in a module docstring would put it where a report reader
    never looks (decision-143's own lesson about `env_scrub`'s detail)."""
    detail = bwrap.compile(_SPEC, _spec_ctx()).grades[Axis.FS_WRITE].detail

    assert "directory" in detail.lower()
    assert "channel" in detail.lower()


@pytest.mark.unit
def test_denial_signatures_match_real_denials_and_not_generic_failures() -> None:
    """Both directions, per the unit-tier rule. The two patterns are the
    kernel's own words for this mechanism's two denials; a signature that
    also matched "No such file or directory" would turn an allowlist's
    honest absence into a false `PASS` in the probe engine."""
    signatures = bwrap.compile(_SPEC, _spec_ctx()).denial_signatures

    assert len(signatures) == 2
    erofs, enetunreach = signatures

    assert erofs.search("sh: 1: cannot create /srv/ws/.envrc: Read-only file system")
    assert enetunreach.search("OSError: [Errno 101] Network is unreachable")

    for pattern in signatures:
        assert pattern.search("sh: 1: nope: command not found") is None
        assert pattern.search("cat: /etc/shadow: No such file or directory") is None
        assert pattern.search("Operation not permitted") is None


@pytest.mark.unit
def test_the_step_stages_nothing_starts_nothing_and_requires_nothing() -> None:
    """The whole mechanism is an argv prefix: no staged profile (unlike
    seatbelt), no helper process (unlike connect_proxy), no launch feature,
    and no sensor -- what it knows at compile time is its own argv, which
    the `Handle` already carries verbatim (decision-152's own reason for
    deleting copies)."""
    step = bwrap.compile(_SPEC, _spec_ctx())

    assert step.staged == ()
    assert step.helpers == ()
    assert step.requires == frozenset()
    assert dict(step.env) == {}
    assert step.events is None


# --------------------------------------------------------------------------
# The compatibility-matrix rows this mechanism needs.
# --------------------------------------------------------------------------


@pytest.mark.unit
def test_bwrap_s_matrix_rows_order_the_pairs_that_compose() -> None:
    """`rlimits` outermost of `bwrap`, `bwrap` outermost of `env_scrub` --
    read off the matrix, with each rationale required to name its own
    reason rather than be an empty string the `MatrixEntry` constructor
    would have caught anyway."""
    matrix = dict(brig.stack.COMPATIBILITY_MATRIX)

    with_rlimits = matrix[frozenset({"bwrap", "rlimits"})]
    assert with_rlimits.outer == "rlimits"
    assert "outermost" in with_rlimits.rationale

    with_env_scrub = matrix[frozenset({"bwrap", "env_scrub"})]
    assert with_env_scrub.outer == "bwrap"
    assert "INSIDE" in with_env_scrub.rationale


@pytest.mark.unit
def test_the_two_unreachable_bwrap_rows_say_so_in_their_rationale() -> None:
    """`{bwrap, seatbelt}` and `{bwrap, connect_proxy}` are in the matrix
    only because it must be total -- both pairs claim an axis twice, so
    `Stack.compile`'s claim step refuses them before the matrix is read.
    The rationale has to say that, or a later reader takes the row for a
    plan."""
    matrix = dict(brig.stack.COMPATIBILITY_MATRIX)

    for other in ("seatbelt", "connect_proxy"):
        entry = matrix[frozenset({"bwrap", other})]
        assert "UNREACHABLE" in entry.rationale
        assert "AxisClaimConflict" in entry.rationale


@pytest.mark.unit
def test_a_stack_of_bwrap_and_seatbelt_is_refused_on_claims_not_on_the_matrix() -> None:
    """The claim above, executed rather than asserted: the refusal really
    does come from step 1, so the unreachable row is never consulted."""
    from brig.mech.seatbelt import seatbelt
    from brig.stack import AxisClaimConflict

    with pytest.raises(AxisClaimConflict):
        Stack([bwrap, seatbelt]).compile(_SPEC, ctx=_spec_ctx())


@pytest.mark.unit
def test_the_three_mechanism_linux_stack_composes_rlimits_bwrap_env_scrub() -> None:
    """Outermost to innermost, read off the composed argv rather than off
    the list order -- and constructed SCRAMBLED here so a fallback to list
    order would be caught rather than hidden."""
    argv = Stack([env_scrub, bwrap, rlimits]).compile(_SPEC, ctx=_spec_ctx()).wrap(("/bin/true",))

    trampoline_at = argv.index("brig.mech.trampoline")
    bwrap_at = argv.index(DEFAULT_BWRAP_PATH)
    shell_at = argv.index("/bin/sh")

    assert trampoline_at < bwrap_at < shell_at


# --------------------------------------------------------------------------
# Read carve-outs inside the allowlist (decision-164).
# --------------------------------------------------------------------------

_SECRET = "/srv/ws/local.env"
_STATE = "/srv/ws/state"
_ABSENT = "/srv/ws/later.env"
_ELSEWHERE = "/home/me/.ssh"

_CARVE_OUT_SPEC = Spec(
    fs=FsPolicy(
        read_model=ReadModel.ALLOW_LIST,
        read_allows=("/usr",),
        write_allows=(_WORKSPACE,),
        read_denies=(_SECRET, _STATE, _ABSENT, _ELSEWHERE),
    ),
    channels=(Channel(name="agent", kind=ChannelKind.LISTEN, endpoint=_ENDPOINT),),
)


def _carve_out_ctx(*, exists: dict[str, bool], is_dir: dict[str, bool]) -> CompileCtx:
    paths = ("/usr", _WORKSPACE, _ENDPOINT, _SECRET, _STATE, _ABSENT, _ELSEWHERE)
    return CompileCtx(
        jail_dir=_JAIL_DIR,
        platform="linux",
        resolved_paths=_identity_resolved(*paths),
        path_exists={"/usr": True, _WORKSPACE: True, _ENDPOINT: False, **exists},
        path_is_dir=is_dir,
    )


@pytest.mark.unit
def test_a_read_carve_out_inside_a_root_is_masked_last_by_its_kind() -> None:
    """An existing file is bound to the null device, an existing directory
    becomes an empty mode-0000 read-only tmpfs, both AFTER the write root they
    sit in (so nothing stacks over them). One outside every root is inert: it
    is absent from the jail already."""
    ctx = _carve_out_ctx(
        exists={_SECRET: True, _STATE: True, _ABSENT: True, _ELSEWHERE: True},
        is_dir={_SECRET: False, _STATE: True, _ABSENT: False},
    )
    step = bwrap.compile(_CARVE_OUT_SPEC, ctx)
    argv = step.wrap(("w",))
    write_root_at = argv.index("--bind", argv.index("/run/brig/jail0") + 1)
    assert argv[write_root_at : write_root_at + 3] == ("--bind", _WORKSPACE, _WORKSPACE)
    assert argv[write_root_at + 3 :] == (
        "--ro-bind", "/dev/null", _ABSENT,
        "--ro-bind", "/dev/null", _SECRET,
        "--perms", "0000", "--tmpfs", _STATE, "--remount-ro", _STATE,
        "--", "w",
    )  # fmt: skip
    assert _ELSEWHERE not in argv
    assert step.grades[Axis.FS_READ].grade is Grade.ENFORCED


@pytest.mark.unit
def test_an_absent_read_carve_out_inside_a_root_is_not_mounted_and_is_graded() -> None:
    """A mask needs a mount point, and bwrap creates one on the HOST: a
    `local.env/` directory where a credential file should go. So an absent
    carve-out is left alone, and `fs_read` says so by name."""
    ctx = _carve_out_ctx(
        exists={_SECRET: False, _STATE: False, _ABSENT: False, _ELSEWHERE: False},
        is_dir={},  # nothing is masked, so no kind is needed
    )
    step = bwrap.compile(_CARVE_OUT_SPEC, ctx)
    assert not {_SECRET, _STATE, _ABSENT, _ELSEWHERE} & set(step.wrap(("w",)))
    graded = step.grades[Axis.FS_READ]
    assert graded.grade is Grade.BEST_EFFORT
    assert _SECRET in graded.detail and _ABSENT in graded.detail
    assert _ELSEWHERE not in graded.detail  # outside every root: absence is the enforcement


@pytest.mark.unit
def test_a_read_carve_out_that_holds_a_root_is_masked_too() -> None:
    """Deny over allow in the other direction: a carve-out that is an
    ANCESTOR of a mounted root hides it."""
    inner = f"{_STATE}/inner"
    spec = Spec(
        fs=FsPolicy(read_model=ReadModel.ALLOW_LIST, read_allows=(inner,), read_denies=(_STATE,))
    )
    ctx = CompileCtx(
        jail_dir=_JAIL_DIR,
        platform="linux",
        resolved_paths=_identity_resolved(inner, _STATE),
        path_exists={inner: True, _STATE: True},
        path_is_dir={_STATE: True},
    )
    argv = bwrap.compile(spec, ctx).wrap(("w",))
    assert argv[-8:] == ("--perms", "0000", "--tmpfs", _STATE, "--remount-ro", _STATE, "--", "w")


@pytest.mark.unit
def test_a_carve_out_to_mask_with_no_kind_is_a_refusal_naming_it() -> None:
    ctx = _carve_out_ctx(
        exists={_SECRET: True, _STATE: False, _ABSENT: False, _ELSEWHERE: False}, is_dir={}
    )
    with pytest.raises(UnknownPathKind, match=re.escape(repr(_SECRET))):
        bwrap.compile(_CARVE_OUT_SPEC, ctx)
