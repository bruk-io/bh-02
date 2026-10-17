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
from brig.mech import CompileCtx, Step
from brig.mech.bwrap import (
    DEFAULT_BWRAP_PATH,
    DEFAULT_INTERPRETER,
    Bwrap,
    ChannelInsideWriteDeny,
    NetworkUnsupported,
    PlatformUnsupported,
    ReadModelUnsupported,
    UnknownPathExistence,
    UnknownPathKind,
    UnresolvedPath,
    pins,
)
from brig.mech.env_scrub import env_scrub
from brig.mech.rlimits import rlimits
from brig.run.host import _derive_wrap_prefix
from brig.stack import Stack

_JAIL_DIR = "/run/brig/jail0"


class _BwrapWhoseInterpreterIsMounted(Bwrap):
    """`Bwrap` whose supervisor interpreter (decision-190) is under the first path the `Spec`
    mounts, so a test about where a mount lands in the argv does not need `/usr` in its `Spec`.
    The tests of the interpreter itself build `Bwrap` directly."""

    def compile(self, spec: Spec, ctx: CompileCtx) -> Step:
        roots = (*spec.fs.read_allows, *spec.fs.write_allows)
        interpreter = f"{roots[0].rstrip('/')}/python3" if roots else DEFAULT_INTERPRETER
        return Bwrap(self._bwrap_path, interpreter).compile(spec, ctx)


bwrap = _BwrapWhoseInterpreterIsMounted()


def _ctx(
    *,
    resolved: dict[str, str] | None = None,
    exists: dict[str, bool] | None = None,
    platform: str = "linux",
    is_dir: dict[str, bool] | None = None,
) -> CompileCtx:
    return CompileCtx(
        jail_dir=_JAIL_DIR,
        platform=platform,
        resolved_paths=resolved or {},
        path_exists=exists or {},
        path_is_dir=is_dir or {},
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
_GIT = "/srv/ws/.git"
_HOOKS = "/srv/ws/.git/hooks"
_ENVRC = "/srv/ws/.envrc"

_SPEC = Spec(
    fs=FsPolicy(
        read_model=ReadModel.ALLOW_LIST,
        read_allows=("/bin", "/usr"),
        write_allows=(_WORKSPACE,),
        write_denies=(_HOOKS, _ENVRC),
    ),
    channels=(Channel(name="ctl", kind=ChannelKind.LISTEN),),
)
_SPEC_RESOLVED = _identity_resolved("/bin", "/usr", _WORKSPACE, _GIT, _HOOKS, _ENVRC)
_SPEC_EXISTS = {
    "/bin": True,
    "/usr": True,
    _WORKSPACE: True,
    _GIT: True,
    _HOOKS: True,
    _ENVRC: False,
}


def _spec_ctx() -> CompileCtx:
    return _ctx(resolved=_SPEC_RESOLVED, exists=_SPEC_EXISTS, is_dir={_GIT: True})


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
# The /proc/sys cover is for a workload that can be the host's uid 0 (decision-194).
# --------------------------------------------------------------------------

_COVER = ("--ro-bind", "/proc/sys", "/proc/sys")


def _with_euid(euid: int | None) -> tuple[str, ...]:
    ctx = _spec_ctx()
    ctx = CompileCtx(
        jail_dir=ctx.jail_dir,
        platform=ctx.platform,
        resolved_paths=ctx.resolved_paths,
        path_exists=ctx.path_exists,
        path_is_dir=ctx.path_is_dir,
        euid=euid,
    )
    return bwrap.compile(_SPEC, ctx).wrap(("w",))


def _contains(argv: tuple[str, ...], run: tuple[str, ...]) -> bool:
    return any(argv[i : i + len(run)] == run for i in range(len(argv)))


@pytest.mark.unit
@pytest.mark.parametrize("euid", [None, 0], ids=["unknown", "root"])
def test_the_proc_sys_cover_is_emitted_for_root_and_for_a_user_nobody_named(
    euid: int | None,
) -> None:
    """decision-177's guard, kept where it guards: a workload that is the host's uid 0, and an
    unknown user, which is never guessed weaker."""
    assert _contains(_with_euid(euid), _COVER)


@pytest.mark.unit
@pytest.mark.parametrize("euid", [1, 1000, 30033])
def test_the_proc_sys_cover_is_left_off_for_a_user_known_not_to_be_root(euid: int) -> None:
    """decision-194: a cover over `/proc/sys` hides a non-empty directory, which the kernel
    will not let a nested mount namespace's fresh `/proc` stand beside, and guards nothing for
    a user whose sysctl writes the mode bits already refuse. The rest of stage 1 and 2 is
    unchanged: the capabilities are dropped and the proc is the jail's own."""
    argv = _with_euid(euid)
    assert not _contains(argv, ("/proc/sys", "/proc/sys"))
    assert _contains(
        argv, ("--cap-drop", "ALL", "--chdir", "/", "--proc", "/proc", "--dev", "/dev")
    )
    # And the same spec as root is the same argv with the cover added, nothing else moved.
    covered = _with_euid(0)
    cut = covered.index("/proc/sys") - 1
    assert covered[:cut] + covered[cut + 3 :] == argv


@pytest.mark.unit
def test_a_compile_context_carries_the_user_and_says_unknown_by_default() -> None:
    assert _ctx().euid is None
    assert CompileCtx(jail_dir=_JAIL_DIR, platform="linux", euid=1234).euid == 1234


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
        # The command is the pid namespace's init: brig's supervisor, whose argv is the
        # one after `--` (decision-190).
        "--as-pid-1",
        # No capability for the workload, whoever runs bwrap (decision-177).
        "--cap-drop",
        "ALL",
        # A working directory the jail can't write: stage 8 makes `/` read-only.
        "--chdir",
        "/",
        # Stage 2: the jail's own furniture, before anything spec-derived;
        # its sysctls read-only (decision-177).
        "--proc",
        "/proc",
        "--ro-bind",
        "/proc/sys",
        "/proc/sys",
        "--dev",
        "/dev",
        # ... and `/dev/shm` a tmpfs of its own, writable (decision-198): the one
        # writable path under `/dev`, which stage 8 leaves alone.
        "--perms",
        "1777",
        "--tmpfs",
        "/dev/shm",
        # Stage 3: the readable tree (allowlist), in the Spec's own sorted
        # order -- `FsPolicy.__post_init__` already sorted it.
        "--ro-bind",
        "/bin",
        "/bin",
        "--ro-bind",
        "/usr",
        "/usr",
        # Stage 4: the runtime's channel directory (decision-184), read-write,
        # once for the jail since the Spec declares a channel, at its own
        # path, and every channel's one grant (decision-186). BEFORE the
        # write roots -- decision-163: it is the one mount whose path policy
        # did not choose, so it is the one that may contain them; last, it
        # stacked over the carve-outs and unmade them.
        "--bind",
        f"{_JAIL_DIR}/chan",
        f"{_JAIL_DIR}/chan",
        # Stage 5: the writable roots, over the read-only tree and the
        # channel directory.
        "--bind",
        _WORKSPACE,
        _WORKSPACE,
        # Stage 5a: the pins -- decision-168. `.git` is between the write
        # root and the `.git/hooks` carve-out, so it is bound over itself:
        # a mount point the workload can't rename away to make a new one.
        "--bind",
        _GIT,
        _GIT,
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
        # Stage 7a: the supervisor's program, read from descriptor 0 and bound read-only
        # after every mount, so none covers it (decision-190).
        "--perms",
        "0444",
        "--ro-bind-data",
        "0",
        "/.brig-supervisor.py",
        # Stage 8: the jail's own tmpfses, read-only, last: `/dev` (decision-198),
        # then the root (decision-166), where until it was a write outside every
        # write root landed in it.
        "--remount-ro",
        "/dev",
        "--remount-ro",
        "/",
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
    that would reverse the channel in the other direction -- the channel
    directory UNDER a `write_denies` subpath -- is refused outright rather
    than ordered around; see the refusal test."""
    argv = bwrap.compile(_SPEC, _spec_ctx()).wrap(())

    channel_at = argv.index(f"{_JAIL_DIR}/chan")
    assert channel_at < argv.index(_WORKSPACE)
    assert channel_at < argv.index(_HOOKS)
    assert channel_at < argv.index(_ENVRC)


@pytest.mark.unit
def test_a_carve_out_inside_the_channel_directory_still_wins() -> None:
    """The defect decision-163 closed, as its own regression: a channel
    directory that HOLDS the workspace. The carve-out must be the LAST word
    on its own path, not a mount the channel bind stacks over."""
    chan_dir = f"{_JAIL_DIR}/chan"
    workspace = f"{chan_dir}/ws"
    hooks = f"{workspace}/.git/hooks"
    spec = Spec(
        fs=FsPolicy(
            read_model=ReadModel.ALLOW_LIST,
            read_allows=("/usr",),
            write_allows=(workspace,),
            write_denies=(hooks,),
        ),
        channels=(Channel(name="ctl", kind=ChannelKind.LISTEN),),
    )
    git = f"{workspace}/.git"
    ctx = _ctx(
        resolved=_identity_resolved("/usr", workspace, git, hooks),
        exists={"/usr": True, workspace: True, git: True, hooks: True},
        is_dir={git: True},
    )

    argv = bwrap.compile(spec, ctx).wrap(())

    assert argv.index(chan_dir) < argv.index(workspace) < argv.index(hooks)


@pytest.mark.unit
def test_two_channels_bind_the_channel_directory_once() -> None:
    """Two channels are one grant: the runtime's channel directory, where
    each start's socket is reserved, is one mount, not two identical ones
    (decision-186)."""
    spec = Spec(
        fs=FsPolicy(read_model=ReadModel.ALLOW_LIST, read_allows=("/usr",)),
        channels=(
            Channel(name="a", kind=ChannelKind.LISTEN),
            Channel(name="b", kind=ChannelKind.LISTEN),
        ),
    )
    ctx = _ctx(resolved=_identity_resolved("/usr"), exists={"/usr": True})

    argv = bwrap.compile(spec, ctx).wrap(())

    assert argv.count(f"{_JAIL_DIR}/chan") == 2  # one `--bind SRC DEST` pair


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

    assert ("--ro-bind", "/usr/bin", "/bin") in zip(argv, argv[1:], argv[2:], strict=False)


@pytest.mark.unit
def test_wrap_is_a_pure_argv_prefix_verified_by_derive_wrap_prefix() -> None:
    """`jail.start` (SPEC.md §9) reproduces a stack's confinement on a
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
def test_a_channel_directory_under_a_write_deny_is_refused() -> None:
    """Compiling the pair would put every socket under a read-only carve-out
    (the carve-outs are stage 6, the channel directory stage 4); compiling
    it the other way round would hand the jail a channel directory it can
    never bind in. Refused by name, both paths named -- the same refusal
    seatbelt makes on its own side. Since decision-186 the channel directory
    is the one place a socket can be, so it is the one refused; a carve-out
    elsewhere (the control) refuses nothing."""
    workspace = _JAIL_DIR
    spec = Spec(
        fs=FsPolicy(
            read_model=ReadModel.ALLOW_LIST,
            write_allows=(workspace,),
            write_denies=(f"{_JAIL_DIR}/chan",),
        ),
        channels=(Channel(name="ctl", kind=ChannelKind.LISTEN),),
    )
    ctx = _ctx(
        resolved=_identity_resolved(workspace, f"{_JAIL_DIR}/chan"),
        exists={workspace: True, f"{_JAIL_DIR}/chan": True},
    )

    with pytest.raises(ChannelInsideWriteDeny) as refusal:
        bwrap.compile(spec, ctx)

    assert f"{_JAIL_DIR}/chan" in str(refusal.value)
    assert "write_denies" in str(refusal.value)
    # The control: the reference spec's carve-outs are elsewhere, and it compiles.
    bwrap.compile(_SPEC, _spec_ctx())


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
        channels=(Channel(name="ctl", kind=ChannelKind.LISTEN),),
    )
    ctx = _ctx(
        resolved=_identity_resolved(_WORKSPACE, "/"),
        exists={_WORKSPACE: True, "/": True},
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
    the `Jail` already carries verbatim (decision-152's own reason for
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

    trampoline_at = argv.index("brig.trampoline")
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
    channels=(Channel(name="ctl", kind=ChannelKind.LISTEN),),
)


def _carve_out_ctx(*, exists: dict[str, bool], is_dir: dict[str, bool]) -> CompileCtx:
    paths = ("/usr", _WORKSPACE, _SECRET, _STATE, _ABSENT, _ELSEWHERE)
    return CompileCtx(
        jail_dir=_JAIL_DIR,
        platform="linux",
        resolved_paths=_identity_resolved(*paths),
        path_exists={"/usr": True, _WORKSPACE: True, **exists},
        path_is_dir=is_dir or {},
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
    write_root_at = argv.index("--bind", argv.index(f"{_JAIL_DIR}/chan") + 2)
    assert argv[write_root_at : write_root_at + 3] == ("--bind", _WORKSPACE, _WORKSPACE)
    assert argv[write_root_at + 3 :] == (
        "--ro-bind", "/dev/null", _ABSENT,
        "--ro-bind", "/dev/null", _SECRET,
        "--perms", "0000", "--tmpfs", _STATE, "--remount-ro", _STATE,
        "--perms", "0444", "--ro-bind-data", "0", "/.brig-supervisor.py",
        "--remount-ro", "/dev",
        "--remount-ro", "/",
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
    assert argv[-17:-11] == ("--perms", "0000", "--tmpfs", _STATE, "--remount-ro", _STATE)


@pytest.mark.unit
def test_a_carve_out_to_mask_with_no_kind_is_a_refusal_naming_it() -> None:
    ctx = _carve_out_ctx(
        exists={_SECRET: True, _STATE: False, _ABSENT: False, _ELSEWHERE: False}, is_dir={}
    )
    with pytest.raises(UnknownPathKind, match=re.escape(repr(_SECRET))):
        bwrap.compile(_CARVE_OUT_SPEC, ctx)


@pytest.mark.unit
def test_a_write_carve_out_no_writable_tree_reaches_is_not_mounted() -> None:
    """decision-165: a `write_denies` entry outside every write root and
    channel directory is unwritable already, and binding it would put a path
    into the jail the allowlist left out -- a READ grant made by a deny. So
    it compiles to nothing; one inside the workspace still mounts."""
    layer = "/home/me/.local/state/app/sessions/1/session.toml"
    spec = Spec(
        fs=FsPolicy(
            read_model=ReadModel.ALLOW_LIST,
            read_allows=("/usr",),
            write_allows=(_WORKSPACE,),
            write_denies=(layer, _HOOKS),
        ),
        channels=(Channel(name="ctl", kind=ChannelKind.LISTEN),),
    )
    ctx = _ctx(
        resolved=_identity_resolved("/usr", _WORKSPACE, layer, _GIT, _HOOKS),
        exists={_GIT: True, _HOOKS: True},  # the outside one is never asked about
        is_dir={_GIT: True},
    )
    argv = bwrap.compile(spec, ctx).wrap(("w",))
    assert layer not in argv
    assert argv[-14:-11] == ("--ro-bind", _HOOKS, _HOOKS)


@pytest.mark.unit
def test_pins_are_the_directories_between_a_write_root_and_each_carve_out() -> None:
    """decision-168, lexically: shallowest first, once each, none for a
    carve-out directly in a root or outside every root."""
    assert pins(
        ("/w",), ("/w/.git/config", "/w/.git/hooks", "/w/a/b/c.toml", "/w/.envrc", "/x/y/z")
    ) == (
        "/w/.git",
        "/w/a",
        "/w/a/b",
    )


@pytest.mark.unit
def test_an_absent_directory_between_a_root_and_a_carve_out_is_not_pinned() -> None:
    """bwrap makes the mount point's missing parents itself; only one that
    exists is bound over itself, and a pin with no existence answer is
    refused, never guessed."""
    spec = Spec(
        fs=FsPolicy(
            read_model=ReadModel.ALLOW_LIST,
            read_allows=("/usr",),
            write_allows=(_WORKSPACE,),
            write_denies=(_HOOKS,),
        ),
    )
    resolved = _identity_resolved("/usr", _WORKSPACE, _GIT, _HOOKS)
    absent = _ctx(resolved=resolved, exists={_GIT: False, _HOOKS: False}, is_dir={_GIT: False})
    assert _GIT not in bwrap.compile(spec, absent).wrap(())
    with pytest.raises(UnknownPathExistence, match=re.escape(_GIT)):
        bwrap.compile(spec, _ctx(resolved=resolved, exists={_HOOKS: True}))


# --------------------------------------------------------------------------
# The seal (decision-173): no write root grants the jail directory.
# --------------------------------------------------------------------------

#: A write root ABOVE the jail directory, the shape an embedder run from `/tmp`
#: has: a workspace carve-out (pinned outside the jail directory), the channel
#: directory inside it, a carve-out in its scratch and one in the sealed part.
_ABOVE = "/run/brig"
_ABOVE_HOOKS = f"{_ABOVE}/ws/.git/hooks"
_SEALED_DENY = f"{_JAIL_DIR}/logs/x"
_SCRATCH_DENY = f"{_JAIL_DIR}/tmp/a/.envrc"
_ABOVE_PINS = (
    _JAIL_DIR,
    f"{_ABOVE}/ws",
    f"{_JAIL_DIR}/logs",
    f"{_JAIL_DIR}/tmp",
    f"{_ABOVE}/ws/.git",
    f"{_JAIL_DIR}/tmp/a",
)


def _above_spec() -> Spec:
    return Spec(
        fs=FsPolicy(
            read_model=ReadModel.ALLOW_LIST,
            read_allows=("/usr",),
            write_allows=(_ABOVE,),
            write_denies=(_ABOVE_HOOKS, _SEALED_DENY, _SCRATCH_DENY),
        ),
        channels=(Channel(name="ctl", kind=ChannelKind.LISTEN),),
    )


def _above_ctx() -> CompileCtx:
    paths = ("/usr", _ABOVE, _ABOVE_HOOKS, _SEALED_DENY, _SCRATCH_DENY, *_ABOVE_PINS)
    return _ctx(
        resolved=_identity_resolved(*paths),
        exists={**dict.fromkeys(paths, True), _SCRATCH_DENY: False},
        is_dir=dict.fromkeys(_ABOVE_PINS, True),
    )


@pytest.mark.unit
def test_a_write_root_above_the_jail_directory_is_sealed_out_of_it() -> None:
    """decision-173, the whole argv. After the write root and the pins
    outside the jail directory: the jail directory read-only, its scratch
    writable again (`--bind-try`), the channel directory inside it bound
    again, then only the pins inside the scratch. The pins at the jail
    directory and in `logs/` are not bound (either would undo the seal),
    and the carve-out in the sealed part is not mounted (its tmpfs could not
    be made there, and nothing could write it anyway)."""
    argv = bwrap.compile(_above_spec(), _above_ctx()).wrap(("w",))
    assert argv == (
        DEFAULT_BWRAP_PATH,
        "--unshare-all",
        "--as-pid-1",
        "--cap-drop",
        "ALL",
        "--chdir",
        "/",
        "--proc",
        "/proc",
        "--ro-bind",
        "/proc/sys",
        "/proc/sys",
        "--dev",
        "/dev",
        "--perms",
        "1777",
        "--tmpfs",
        "/dev/shm",
        "--ro-bind",
        "/usr",
        "/usr",
        # The runtime's channel directory (decision-184), stage 4.
        "--bind",
        f"{_JAIL_DIR}/chan",
        f"{_JAIL_DIR}/chan",
        "--bind",
        _ABOVE,
        _ABOVE,
        "--bind",
        f"{_ABOVE}/ws",
        f"{_ABOVE}/ws",
        "--bind",
        f"{_ABOVE}/ws/.git",
        f"{_ABOVE}/ws/.git",
        "--ro-bind",
        _JAIL_DIR,
        _JAIL_DIR,
        "--bind-try",
        f"{_JAIL_DIR}/tmp",
        f"{_JAIL_DIR}/tmp",
        # ... and bound again after the seal, which hides it (decision-184).
        "--bind",
        f"{_JAIL_DIR}/chan",
        f"{_JAIL_DIR}/chan",
        "--bind",
        f"{_JAIL_DIR}/tmp",
        f"{_JAIL_DIR}/tmp",
        "--bind",
        f"{_JAIL_DIR}/tmp/a",
        f"{_JAIL_DIR}/tmp/a",
        "--tmpfs",
        _SCRATCH_DENY,
        "--remount-ro",
        _SCRATCH_DENY,
        "--ro-bind",
        _ABOVE_HOOKS,
        _ABOVE_HOOKS,
        # The supervisor's program, after every mount (decision-190).
        "--perms",
        "0444",
        "--ro-bind-data",
        "0",
        "/.brig-supervisor.py",
        "--remount-ro",
        "/dev",
        "--remount-ro",
        "/",
        "--",
        "w",
    )


@pytest.mark.unit
def test_the_seal_is_shown_where_each_writable_tree_puts_the_jail_directory() -> None:
    """A write root spelled through a link mounts the jail directory at the
    spec's spelling, so that is where it is sealed; `/run` reaches it at its own
    path. The source is always the resolved jail directory."""
    for root, resolved_root, dest in (("/r", _ABOVE, "/r/jail0"), ("/run", "/run", _JAIL_DIR)):
        spec = Spec(fs=FsPolicy(read_model=ReadModel.ALLOW_LIST, write_allows=(root,)))
        argv = bwrap.compile(spec, _ctx(resolved={root: resolved_root})).wrap(())
        seal = ("--ro-bind", _JAIL_DIR, dest, "--bind-try", f"{_JAIL_DIR}/tmp", f"{dest}/tmp")
        assert argv[-16:-10] == seal, argv


@pytest.mark.unit
def test_no_seal_without_a_writable_tree_above_the_jail_directory() -> None:
    """The control: the reference spec's write root is beside the jail
    directory and its channel directory is inside it, so nothing is sealed
    and the golden above holds unchanged. A write root strictly
    inside the jail directory reaches none of its control state either."""
    assert "--bind-try" not in bwrap.compile(_SPEC, _spec_ctx()).wrap(())
    inside = f"{_JAIL_DIR}/ws"
    spec = Spec(fs=FsPolicy(read_model=ReadModel.ALLOW_LIST, write_allows=(inside,)))
    argv = bwrap.compile(spec, _ctx(resolved={inside: inside})).wrap(())
    assert _JAIL_DIR not in argv
    assert "--bind-try" not in argv


def _channel_only_spec() -> Spec:
    return Spec(
        fs=FsPolicy(read_model=ReadModel.ALLOW_LIST, read_allows=("/usr",)),
        channels=(Channel(name="ctl", kind=ChannelKind.LISTEN),),
    )


def _binds(argv: tuple[str, ...]) -> list[tuple[str, str]]:
    """Every read-write `--bind SRC DEST` pair in `argv`, `--bind-try` too."""
    return [
        (argv[i + 1], argv[i + 2]) for i, arg in enumerate(argv) if arg in ("--bind", "--bind-try")
    ]


def _at_or_under(path: str, root: str) -> bool:
    return path == root or path.startswith(root + "/")


@pytest.mark.unit
@pytest.mark.parametrize("sealed", [True, False], ids=["write root above", "no write root above"])
def test_a_channel_never_makes_the_jail_directory_writable(sealed: bool) -> None:
    """decision-174, restated by decision-186: a channel's one grant is the
    runtime's channel directory, a subdirectory brig names, so no channel can
    make the jail directory itself writable. Inside the jail directory only
    the channel directory and the scratch (and pins inside the scratch) are
    ever bound read-write, whether or not a write root above it is there too;
    and the channel directory is (the control: the grant is made)."""
    spec = _above_spec() if sealed else _channel_only_spec()
    ctx = _above_ctx() if sealed else _ctx(resolved=_identity_resolved("/usr"))
    binds = _binds(bwrap.compile(spec, ctx).wrap(()))
    chan, scratch = f"{_JAIL_DIR}/chan", f"{_JAIL_DIR}/tmp"
    inside = {path for pair in binds for path in pair if _at_or_under(path, _JAIL_DIR)}
    assert (chan, chan) in binds
    assert _JAIL_DIR not in inside, binds
    assert all(_at_or_under(path, chan) or _at_or_under(path, scratch) for path in inside), binds


@pytest.mark.unit
def test_a_channel_is_granted_the_channel_directory_and_nothing_else() -> None:
    """decision-186: with no write root, the one read-write mount a channel
    adds is the channel directory at its own path; a spec without a channel
    has none (the control)."""
    ctx = _ctx(resolved=_identity_resolved("/usr"))
    chan = f"{_JAIL_DIR}/chan"
    assert _binds(bwrap.compile(_channel_only_spec(), ctx).wrap(())) == [(chan, chan)]
    no_channel = Spec(fs=FsPolicy(read_model=ReadModel.ALLOW_LIST, read_allows=("/usr",)))
    assert _binds(bwrap.compile(no_channel, ctx).wrap(())) == []


@pytest.mark.unit
@pytest.mark.parametrize("sealed", [True, False], ids=["write root above", "no write root above"])
def test_no_channel_grant_reaches_the_records(sealed: bool) -> None:
    """decision-181, restated by decision-186: the records teardown signals by
    live under `<jail_dir>/procs`, a sibling of the channel directory, so no
    read-write mount a channel brings is at, under or above them (an
    ancestor bound writable would reach them too). The integration twin
    (`test_bwrap_records_refused.py`) writes at them through a real jail."""
    spec = _above_spec() if sealed else _channel_only_spec()
    ctx = _above_ctx() if sealed else _ctx(resolved=_identity_resolved("/usr"))
    records = f"{_JAIL_DIR}/procs"
    binds = _binds(bwrap.compile(spec, ctx).wrap(()))
    reaching = [
        (source, dest)
        for source, dest in binds
        if _at_or_under(source, _JAIL_DIR) or _at_or_under(dest, _JAIL_DIR)
        if _at_or_under(dest, records) or _at_or_under(records, dest)
    ]
    assert reaching == [], binds
    assert (f"{_JAIL_DIR}/chan", f"{_JAIL_DIR}/chan") in binds
