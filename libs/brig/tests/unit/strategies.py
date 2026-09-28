"""Hypothesis strategies for `brig.core.spec`, plus the six narrowing and
widening operations task-006 tests the subset algebra against.

This is a test-support module, not library code: nothing under `brig/` may
import it (CLAUDE.md's layer boundaries don't even have a lane for tests to
be imported from). Task-006's central property is that the pointwise-meet
operation, applied to a spec and any other, always yields something the
subset-comparison method accepts as reaching no further than the spec;
task-007's is a dict-serialization round-trip. Both are falsifiable only if
`narrow`/`widen` here are defined *independently* of the algebra and
serialization methods they go on to test -- this file must never import,
call, or name any of them (see task-005's Deliverable and AC #2's grep
control). Each operation is a DATA operation on the tuples the drawn `Spec`
already holds: drop or add an entry, flip an enum, move a scalar -- then
reconstruct the (frozen, self-validating) dataclass so task-003's
construction rules are re-run for free.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Container, Iterable
from typing import Any, Final, cast

from hypothesis import strategies as st

from brig.core.spec import (
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
)

DrawFn = st.DrawFn
# The real `st.DrawFn` is a Protocol that also demands a `__signature__`
# attribute, which `st.DataObject.draw` (a bound method -- how narrow/widen
# get exercised directly in test_strategies.py) does not carry. `Draw` is
# the looser, purely-structural type these standalone (non-@composite)
# functions actually need: "something I can call with a strategy".
Draw = Callable[[st.SearchStrategy[Any]], Any]

DIMENSIONS: Final[tuple[str, ...]] = (
    "write_allows",
    "denies",
    "domains",
    "limits",
    "env",
    "channels",
)

# ---------------------------------------------------------------------------
# Component strategies
# ---------------------------------------------------------------------------

_PATH_SEGMENT_CHARS = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
_DOMAIN_LABEL_CHARS = "abcdefghijklmnopqrstuvwxyz0123456789"
_NAME_CHARS = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
_ENV_NAME_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ_0123456789"
_DIGEST_CHARS = "0123456789abcdef"


def _path_segment() -> st.SearchStrategy[str]:
    return st.text(alphabet=_PATH_SEGMENT_CHARS, min_size=1, max_size=12)


def paths() -> st.SearchStrategy[str]:
    """Relative and absolute POSIX-ish paths.

    Segments never contain '/', so what this emits is already stable under
    `brig.core.spec._normalize_paths` (no trailing-slash noise, nothing
    that strips to empty) -- freshness checks in narrow/widen can compare a
    raw draw against a Spec's already-normalized tuples directly.
    """

    def _build(is_absolute: bool, segments: list[str]) -> str:
        joined = "/".join(segments)
        return f"/{joined}" if is_absolute else joined

    varied = st.builds(_build, st.booleans(), st.lists(_path_segment(), min_size=1, max_size=4))
    return st.one_of(varied, st.just("/"))


def domains() -> st.SearchStrategy[str]:
    """Dotted labels, already lowercase so normalization is a no-op here
    too (see `paths` docstring for why that matters for narrow/widen)."""
    labels = st.lists(
        st.text(alphabet=_DOMAIN_LABEL_CHARS, min_size=1, max_size=8), min_size=2, max_size=4
    )
    return labels.map(".".join)


def env_names() -> st.SearchStrategy[str]:
    return st.text(alphabet=_ENV_NAME_CHARS, min_size=1, max_size=12).filter(
        lambda s: not s[0].isdigit()
    )


def _name(min_size: int = 1, max_size: int = 12) -> st.SearchStrategy[str]:
    return st.text(alphabet=_NAME_CHARS, min_size=min_size, max_size=max_size)


def _digest() -> st.SearchStrategy[str]:
    return st.text(alphabet=_DIGEST_CHARS, min_size=8, max_size=64)


def _limit_field_value() -> st.SearchStrategy[int]:
    return st.integers(min_value=0, max_value=10_000)


def limits() -> st.SearchStrategy[Limits]:
    """Mixes 0 (uncapped) and positive independently per field."""
    return st.builds(
        Limits,
        wall_seconds=_limit_field_value(),
        cpu_seconds=_limit_field_value(),
        memory_bytes=_limit_field_value(),
        max_tasks=_limit_field_value(),
        max_output_bytes=_limit_field_value(),
    )


@st.composite
def fs_policies(draw: DrawFn) -> FsPolicy:
    """Both ReadModels. `read_allows` is populated only under ALLOW_LIST
    (task-003's rule for the inactive field); `read_denies` under both, since
    decision-164 made it ALLOW_LIST's carve-outs."""
    write_allows = draw(st.lists(paths(), max_size=5, unique=True))
    write_denies = draw(st.lists(paths(), max_size=5, unique=True))
    read_model = draw(st.sampled_from(ReadModel))
    read_denies = draw(st.lists(paths(), max_size=5, unique=True))
    read_allows: list[str] = []
    if read_model is ReadModel.ALLOW_LIST:
        read_allows = draw(st.lists(paths(), max_size=5, unique=True))
    return FsPolicy(
        write_allows=tuple(write_allows),
        write_denies=tuple(write_denies),
        read_model=read_model,
        read_denies=tuple(read_denies),
        read_allows=tuple(read_allows),
    )


@st.composite
def network_policies(draw: DrawFn) -> NetworkPolicy:
    allowed = draw(st.lists(domains(), max_size=5, unique=True))
    return NetworkPolicy(allowed_domains=tuple(allowed))


@st.composite
def env_policies(draw: DrawFn) -> EnvPolicy:
    """`allow_names` is drawn only under SCRUB. Under PASS it is inert and
    construction now refuses a non-empty value there (task-033, decision-064)
    -- drawing it unconditionally would make every PASS-mode example a
    construction error instead of a property failure."""
    mode = draw(st.sampled_from(EnvMode))
    allow_names: list[str] = []
    if mode is EnvMode.SCRUB:
        allow_names = draw(st.lists(env_names(), max_size=5, unique=True))
    set_pairs = draw(st.lists(st.tuples(env_names(), st.text(max_size=10)), max_size=5))
    return EnvPolicy(mode=mode, allow_names=tuple(allow_names), set=tuple(set_pairs))


@st.composite
def channels(draw: DrawFn) -> Channel:
    name = draw(_name())
    kind = draw(st.sampled_from(ChannelKind))
    endpoint = draw(_name())
    return Channel(name=name, kind=kind, endpoint=endpoint)


@st.composite
def provisionings(draw: DrawFn) -> Provisioning:
    files = draw(st.lists(st.tuples(paths(), _digest()), max_size=5))
    closures = draw(st.lists(paths(), max_size=5, unique=True))
    env = draw(st.lists(st.tuples(env_names(), st.text(max_size=10)), max_size=5))
    return Provisioning(files=tuple(files), closures=tuple(closures), env=tuple(env))


@st.composite
def specs(draw: DrawFn) -> Spec:
    fs = draw(fs_policies())
    network = draw(network_policies())
    lim = draw(limits())
    env = draw(env_policies())
    drawn_channels = draw(st.lists(channels(), max_size=4, unique_by=lambda c: c.name))
    shared_media = draw(st.lists(paths(), max_size=4, unique=True))
    provisioning = draw(provisionings())
    return Spec(
        fs=fs,
        network=network,
        limits=lim,
        env=env,
        channels=tuple(drawn_channels),
        shared_media=tuple(shared_media),
        provisioning=provisioning,
    )


def _fresh[T](draw: Draw, strategy: st.SearchStrategy[T], existing: Container[T]) -> T:
    """Draw a value from `strategy` guaranteed not already in `existing`."""
    return cast(T, draw(strategy.filter(lambda value: value not in existing)))


def _covered(path: str, existing: Iterable[str]) -> bool:
    """True when some entry in `existing` is `path` or an ancestor of it.

    Deliberately a local three-line rule, not an import from the module under
    test: this file must define its data operations independently of the
    algebra it exercises (see this module's docstring). It exists because an
    allow tuple is an antichain of SUBTREES (SPEC.md section 5, decision-160)
    -- adding `/w/sub` beside an existing `/w` widens nothing and is dropped
    at construction, so a widening op that drew it would return an unchanged
    spec and quietly stop being a widening.
    """
    return any(entry == path or path.startswith(entry.rstrip("/") + "/") for entry in existing)


def _fresh_allow(draw: Draw, existing: tuple[str, ...]) -> str:
    """Draw a path that genuinely widens an allow tuple: neither already
    present nor under an entry that is."""
    return cast(str, draw(paths().filter(lambda value: not _covered(value, existing))))


# ---------------------------------------------------------------------------
# The six narrowing dimensions (SPEC.md section 5's "six clauses, exactly").
# Each `narrow`/`widen` is data-only: drop/add a tuple entry, flip an enum,
# move a scalar, then reconstruct the frozen dataclass. `None` means the
# drawn spec has nothing left to move along that dimension.
# ---------------------------------------------------------------------------


def _narrow_write_allows(spec: Spec, draw: Draw) -> Spec | None:
    allows = spec.fs.write_allows
    if not allows:
        return None
    dropped = draw(st.sampled_from(allows))
    new_fs = dataclasses.replace(spec.fs, write_allows=tuple(p for p in allows if p != dropped))
    return dataclasses.replace(spec, fs=new_fs)


def _widen_write_allows(spec: Spec, draw: Draw) -> Spec | None:
    fresh = _fresh_allow(draw, spec.fs.write_allows)
    new_fs = dataclasses.replace(spec.fs, write_allows=(*spec.fs.write_allows, fresh))
    return dataclasses.replace(spec, fs=new_fs)


def _narrow_denies(spec: Spec, draw: Draw) -> Spec | None:
    fs = spec.fs
    fresh_write_deny = _fresh(draw, paths(), fs.write_denies)
    new_write_denies = (*fs.write_denies, fresh_write_deny)

    # A read deny grows under either model (decision-164: under ALLOW_LIST it
    # is a carve-out); under ALLOW_LIST an allow may shrink besides.
    fresh_read_deny = _fresh(draw, paths(), fs.read_denies)
    new_read_denies = (*fs.read_denies, fresh_read_deny)
    new_read_allows = fs.read_allows
    if fs.read_model is ReadModel.ALLOW_LIST and fs.read_allows:
        dropped = draw(st.sampled_from(fs.read_allows))
        new_read_allows = tuple(p for p in fs.read_allows if p != dropped)

    new_fs = dataclasses.replace(
        fs,
        write_denies=new_write_denies,
        read_denies=new_read_denies,
        read_allows=new_read_allows,
    )
    return dataclasses.replace(spec, fs=new_fs)


def _widen_denies(spec: Spec, draw: Draw) -> Spec | None:
    fs = spec.fs
    changed = False
    new_write_denies = fs.write_denies
    if fs.write_denies:
        dropped = draw(st.sampled_from(fs.write_denies))
        new_write_denies = tuple(p for p in fs.write_denies if p != dropped)
        changed = True

    new_read_denies = fs.read_denies
    new_read_allows = fs.read_allows
    if fs.read_denies:  # a carve-out under ALLOW_LIST, the policy under DENY_LIST
        dropped = draw(st.sampled_from(fs.read_denies))
        new_read_denies = tuple(p for p in fs.read_denies if p != dropped)
        changed = True
    if fs.read_model is ReadModel.ALLOW_LIST:
        fresh = _fresh_allow(draw, fs.read_allows)
        new_read_allows = (*fs.read_allows, fresh)
        changed = True

    if not changed:
        return None

    new_fs = dataclasses.replace(
        fs,
        write_denies=new_write_denies,
        read_denies=new_read_denies,
        read_allows=new_read_allows,
    )
    return dataclasses.replace(spec, fs=new_fs)


def _narrow_domains(spec: Spec, draw: Draw) -> Spec | None:
    allowed = spec.network.allowed_domains
    if not allowed:
        return None
    dropped = draw(st.sampled_from(allowed))
    new_network = dataclasses.replace(
        spec.network, allowed_domains=tuple(d for d in allowed if d != dropped)
    )
    return dataclasses.replace(spec, network=new_network)


def _widen_domains(spec: Spec, draw: Draw) -> Spec | None:
    fresh = _fresh(draw, domains(), spec.network.allowed_domains)
    new_network = dataclasses.replace(
        spec.network, allowed_domains=(*spec.network.allowed_domains, fresh)
    )
    return dataclasses.replace(spec, network=new_network)


def _limit_values(lim: Limits) -> tuple[tuple[str, int], ...]:
    return (
        ("wall_seconds", lim.wall_seconds),
        ("cpu_seconds", lim.cpu_seconds),
        ("memory_bytes", lim.memory_bytes),
        ("max_tasks", lim.max_tasks),
        ("max_output_bytes", lim.max_output_bytes),
    )


def _narrow_limits(spec: Spec, draw: Draw) -> Spec | None:
    for name, current in draw(st.permutations(_limit_values(spec.limits))):
        if current == 0:
            new_value = draw(st.integers(min_value=1, max_value=10_000))
            new_limits = dataclasses.replace(spec.limits, **{name: new_value})
            return dataclasses.replace(spec, limits=new_limits)
        if current >= 2:
            new_value = draw(st.integers(min_value=1, max_value=current - 1))
            new_limits = dataclasses.replace(spec.limits, **{name: new_value})
            return dataclasses.replace(spec, limits=new_limits)
    return None


def _widen_limits(spec: Spec, draw: Draw) -> Spec | None:
    for name, current in draw(st.permutations(_limit_values(spec.limits))):
        if current > 0:
            if draw(st.booleans()):
                new_value = draw(st.integers(min_value=current + 1, max_value=current + 10_000))
            else:
                new_value = 0
            new_limits = dataclasses.replace(spec.limits, **{name: new_value})
            return dataclasses.replace(spec, limits=new_limits)
    return None


def _narrow_env(spec: Spec, draw: Draw) -> Spec | None:
    env = spec.env
    options: list[str] = []
    if env.allow_names:
        options.append("drop")
    if env.mode is EnvMode.PASS:
        options.append("toggle")
    if not options:
        return None
    if draw(st.sampled_from(options)) == "drop":
        dropped = draw(st.sampled_from(env.allow_names))
        new_env = dataclasses.replace(
            env, allow_names=tuple(n for n in env.allow_names if n != dropped)
        )
    else:
        new_env = dataclasses.replace(env, mode=EnvMode.SCRUB)
    return dataclasses.replace(spec, env=new_env)


def _widen_env(spec: Spec, draw: Draw) -> Spec | None:
    env = spec.env
    if env.mode is EnvMode.PASS:
        # PASS is the top element of the env axis (SPEC.md section 5) --
        # nothing is wider than a policy that already confers everything.
        return None
    options = ["add", "toggle"]
    if draw(st.sampled_from(options)) == "add":
        fresh = _fresh(draw, env_names(), env.allow_names)
        new_env = dataclasses.replace(env, allow_names=(*env.allow_names, fresh))
    else:
        # Toggling to PASS must also clear allow_names: it is the inactive
        # field under PASS and construction now refuses a non-empty value
        # there (task-033, decision-064).
        new_env = dataclasses.replace(env, mode=EnvMode.PASS, allow_names=())
    return dataclasses.replace(spec, env=new_env)


def _narrow_channels(spec: Spec, draw: Draw) -> Spec | None:
    options: list[str] = []
    if spec.channels:
        options.append("drop_channel")
    if spec.shared_media:
        options.append("drop_shared")
    if not options:
        return None
    if draw(st.sampled_from(options)) == "drop_channel":
        dropped = draw(st.sampled_from(spec.channels))
        new_channels = tuple(c for c in spec.channels if c.name != dropped.name)
        return dataclasses.replace(spec, channels=new_channels)
    dropped_media = draw(st.sampled_from(spec.shared_media))
    new_shared = tuple(p for p in spec.shared_media if p != dropped_media)
    return dataclasses.replace(spec, shared_media=new_shared)


def _widen_channels(spec: Spec, draw: Draw) -> Spec | None:
    if draw(st.sampled_from(("add_channel", "add_shared"))) == "add_channel":
        existing_names = {c.name for c in spec.channels}
        fresh_name = _fresh(draw, _name(), existing_names)
        kind = draw(st.sampled_from(ChannelKind))
        endpoint = draw(_name())
        new_channel = Channel(name=fresh_name, kind=kind, endpoint=endpoint)
        return dataclasses.replace(spec, channels=(*spec.channels, new_channel))
    fresh_media = _fresh(draw, paths(), spec.shared_media)
    return dataclasses.replace(spec, shared_media=(*spec.shared_media, fresh_media))


_NARROW: Final[dict[str, Callable[[Spec, Draw], Spec | None]]] = {
    "write_allows": _narrow_write_allows,
    "denies": _narrow_denies,
    "domains": _narrow_domains,
    "limits": _narrow_limits,
    "env": _narrow_env,
    "channels": _narrow_channels,
}

_WIDEN: Final[dict[str, Callable[[Spec, Draw], Spec | None]]] = {
    "write_allows": _widen_write_allows,
    "denies": _widen_denies,
    "domains": _widen_domains,
    "limits": _widen_limits,
    "env": _widen_env,
    "channels": _widen_channels,
}


def narrow(spec: Spec, dimension: str, draw: Draw) -> Spec | None:
    """Narrow `spec` along one dimension in `DIMENSIONS`.

    `None` means the dimension has nothing left to drop on this spec (it is
    already maximally restrictive along that axis) -- callers use
    `hypothesis.assume`.
    """
    try:
        op = _NARROW[dimension]
    except KeyError:
        raise ValueError(f"unknown dimension {dimension!r}, expected one of {DIMENSIONS}") from None
    return op(spec, draw)


def widen(spec: Spec, dimension: str, draw: Draw) -> Spec | None:
    """Widen `spec` along one dimension in `DIMENSIONS`.

    `None` means the dimension has nothing left to add on this spec (it is
    already maximally permissive along that axis) -- callers use
    `hypothesis.assume`.
    """
    try:
        op = _WIDEN[dimension]
    except KeyError:
        raise ValueError(f"unknown dimension {dimension!r}, expected one of {DIMENSIONS}") from None
    return op(spec, draw)


# ---------------------------------------------------------------------------
# Paired composites for task-006. Each narrow/widen op is None exactly when
# the drawn Spec has nothing left to move along that dimension (see the six
# op pairs above for the precise conditions). Rather than drawing a whole
# spec blind and retrying when we get unlucky, choose the dimension first
# and patch *only* the small piece of the spec that would otherwise make
# that dimension a no-op -- one extra small draw, at most, never a second
# full spec() draw. This makes every (spec, dimension) pair below provably
# total: narrow/widen is asserted non-None rather than retried or skipped,
# so a future change that makes a dimension silently unmovable again fails
# loudly here instead of vanishing into a retry loop or an `assume`.
# ---------------------------------------------------------------------------


def _ensure_narrowable(spec: Spec, dim: str, draw: Draw) -> Spec:
    """Patch the minimum needed so `narrow(spec, dim, draw)` cannot be None.

    `denies` never returns None (see `_narrow_denies`) and `limits` returns
    None only when every field is exactly 1 -- both handled without needing
    a full-spec redraw.
    """
    if dim == "write_allows" and not spec.fs.write_allows:
        new_fs = dataclasses.replace(spec.fs, write_allows=(draw(paths()),))
        return dataclasses.replace(spec, fs=new_fs)
    if dim == "domains" and not spec.network.allowed_domains:
        new_network = dataclasses.replace(spec.network, allowed_domains=(draw(domains()),))
        return dataclasses.replace(spec, network=new_network)
    if dim == "limits" and all(value == 1 for _, value in _limit_values(spec.limits)):
        new_limits = dataclasses.replace(spec.limits, wall_seconds=0)
        return dataclasses.replace(spec, limits=new_limits)
    if dim == "env" and not spec.env.allow_names and spec.env.mode is not EnvMode.PASS:
        new_env = dataclasses.replace(spec.env, allow_names=(draw(env_names()),))
        return dataclasses.replace(spec, env=new_env)
    if dim == "channels" and not spec.channels and not spec.shared_media:
        return dataclasses.replace(spec, shared_media=(draw(paths()),))
    return spec


def _ensure_widenable(spec: Spec, dim: str, draw: Draw) -> Spec:
    """Patch the minimum needed so `widen(spec, dim, draw)` cannot be None.

    `write_allows`, `domains`, and `channels` never return None (see the
    corresponding `_widen_*` functions) -- `denies` (DENY_LIST model with
    both denial lists empty), `limits` (every field exactly 0), and `env`
    (already PASS -- the top of that axis, SPEC.md section 5) can, and all
    three are cheap to patch directly.
    """
    if dim == "denies":
        fs = spec.fs
        if fs.read_model is ReadModel.DENY_LIST and not fs.write_denies and not fs.read_denies:
            new_fs = dataclasses.replace(fs, write_denies=(draw(paths()),))
            return dataclasses.replace(spec, fs=new_fs)
        return spec
    if dim == "limits" and all(value == 0 for _, value in _limit_values(spec.limits)):
        new_limits = dataclasses.replace(spec.limits, wall_seconds=1)
        return dataclasses.replace(spec, limits=new_limits)
    if dim == "env" and spec.env.mode is EnvMode.PASS:
        new_env = dataclasses.replace(spec.env, mode=EnvMode.SCRUB)
        return dataclasses.replace(spec, env=new_env)
    return spec


@st.composite
def spec_and_narrowed(draw: DrawFn, dimension: str | None = None) -> tuple[Spec, Spec]:
    dim = dimension if dimension is not None else draw(st.sampled_from(DIMENSIONS))
    spec = _ensure_narrowable(draw(specs()), dim, draw)
    narrowed = narrow(spec, dim, draw)
    assert narrowed is not None, (
        f"narrow(..., {dim!r}, ...) returned None after _ensure_narrowable patched the spec "
        "-- the totality invariant above no longer holds"
    )
    return spec, narrowed


@st.composite
def spec_and_widened(draw: DrawFn, dimension: str | None = None) -> tuple[Spec, Spec]:
    dim = dimension if dimension is not None else draw(st.sampled_from(DIMENSIONS))
    spec = _ensure_widenable(draw(specs()), dim, draw)
    widened = widen(spec, dim, draw)
    assert widened is not None, (
        f"widen(..., {dim!r}, ...) returned None after _ensure_widenable patched the spec "
        "-- the totality invariant above no longer holds"
    )
    return spec, widened
