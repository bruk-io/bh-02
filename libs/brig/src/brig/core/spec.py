"""Spec and its policy dataclasses: frozen, validated, self-normalizing pure
data. See SPEC.md section 5.

A Spec is canonical the moment it is built: path tuples, domains, names and
pair tuples are normalized in __post_init__, so "equal up to normalization"
is plain `==` and nothing downstream ever renormalizes. The two ALLOW tuples
are canonicalized one step further, to an antichain -- an entry another entry
already covers is dropped, because an allow entry is a subtree (SPEC.md
section 5, decision-160). Construction raises
`ValueError` on a negative/non-integer limit, a duplicate channel name, an
empty path/name/endpoint, `read_allows` populated under DENY_LIST (its
inactive model; `read_denies` is active under both, decision-164), or
`EnvPolicy(mode=PASS, allow_names=(...))` -- PASS's `allow_names` is inert,
and populating it is refused rather than silently ignored (SPEC.md section 5,
decision-064).

core is pure: no I/O, no clock, no randomness, no subprocess.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Final

SPEC_VERSION: Final = 1


class ReadModel(Enum):
    DENY_LIST = "deny_list"
    ALLOW_LIST = "allow_list"


class EnvMode(Enum):
    SCRUB = "scrub"
    PASS = "pass"


class ChannelKind(Enum):
    """The one declared inbound kind: the jail LISTENs and the trusted side
    dials (SPEC.md §10.1). There is no `DIAL` kind, and `MAILBOX` was
    deleted by decision-153 (2026-09-08) -- see SPEC.md §10.

    A one-member enum rather than no field at all: the field is what lets a
    second kind arrive without a `SPEC_VERSION` bump, and `Channel.kind` is
    already in every serialized `Spec` and `Handle`."""

    LISTEN = "listen"


_LIMIT_FIELDS = ("wall_seconds", "cpu_seconds", "memory_bytes", "max_tasks", "max_output_bytes")


def _normalize_paths(paths: tuple[str, ...]) -> tuple[str, ...]:
    """Strip a trailing '/' (except a bare '/'), drop empties, dedupe, sort."""
    cleaned: set[str] = set()
    for raw in paths:
        stripped = raw if raw == "/" else raw.rstrip("/")
        if stripped:
            cleaned.add(stripped)
    return tuple(sorted(cleaned))


def _path_covers(parent: str, child: str) -> bool:
    """True when `parent` confers `child`: the same path, or an ancestor of it.

    An allow entry is a SUBTREE (SPEC.md section 5, decision-160): seatbelt
    compiles it to `(subpath ...)` and bwrap to a bind-mounted tree, so `/w`
    reaches `/w/sub` whether or not `/w/sub` is spelled out. Both arguments are
    already normalized paths (no trailing '/', except the bare root), so the
    boundary test is a plain prefix with the separator re-attached: '/w' covers
    '/w/sub' but not '/wide'.
    """
    if parent == child:
        return True
    prefix = parent if parent.endswith("/") else parent + "/"
    return child.startswith(prefix)


def _normalize_allows(paths: tuple[str, ...]) -> tuple[str, ...]:
    """`_normalize_paths`, then drop every entry another entry already covers.

    An allow tuple is canonicalized to an ANTICHAIN (SPEC.md section 5,
    decision-160): `("/w", "/w/sub")` spells one reach, and it builds as
    `("/w",)`. Without this the reach-containment clause below would stop being
    antisymmetric -- `("/w",)` and `("/w", "/w/sub")` would be subsets of each
    other while comparing unequal.
    """
    normalized = _normalize_paths(paths)
    return tuple(
        path
        for path in normalized
        if not any(other != path and _path_covers(other, path) for other in normalized)
    )


def _allows_reach_within(child: tuple[str, ...], parent: tuple[str, ...]) -> bool:
    """Every child allow is at or under some parent allow (SPEC.md section 5,
    decision-160). The set-containment this replaced refused `/w/sub` onto a
    parent allowing `/w`."""
    return all(any(_path_covers(p, c) for p in parent) for c in child)


def _allows_meet(a: tuple[str, ...], b: tuple[str, ...]) -> tuple[str, ...]:
    """The pointwise intersection of the two trees (SPEC.md section 5,
    decision-160): of each nested pair the inner entry survives, a disjoint
    pair contributes nothing. `FsPolicy.__post_init__` canonicalizes the
    result, so a duplicate carried in from an operand does not survive."""
    kept = [c for c in a if any(_path_covers(p, c) for p in b)]
    kept += [c for c in b if any(_path_covers(p, c) for p in a)]
    return tuple(kept)


def _normalize_domains(domains: tuple[str, ...]) -> tuple[str, ...]:
    """Lowercase, strip a trailing '.', dedupe, sort."""
    cleaned: set[str] = set()
    for raw in domains:
        lowered = raw.lower()
        if lowered.endswith("."):
            lowered = lowered[:-1]
        cleaned.add(lowered)
    return tuple(sorted(cleaned))


def _normalize_names(names: tuple[str, ...]) -> tuple[str, ...]:
    """Dedupe, sort."""
    return tuple(sorted(set(names)))


def _normalize_pairs(pairs: tuple[tuple[str, str], ...]) -> tuple[tuple[str, str], ...]:
    """Dedupe by first element, LAST occurrence wins, sort by first element."""
    merged: dict[str, str] = {}
    for key, value in pairs:
        merged[key] = value
    return tuple(sorted(merged.items()))


@dataclass(frozen=True, slots=True)
class FsPolicy:
    write_allows: tuple[str, ...] = ()
    write_denies: tuple[str, ...] = ()
    read_model: ReadModel = ReadModel.DENY_LIST
    read_denies: tuple[str, ...] = ()
    read_allows: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "write_allows", _normalize_allows(self.write_allows))
        object.__setattr__(self, "write_denies", _normalize_paths(self.write_denies))
        object.__setattr__(self, "read_denies", _normalize_paths(self.read_denies))
        object.__setattr__(self, "read_allows", _normalize_allows(self.read_allows))

        if self.read_model is ReadModel.DENY_LIST and self.read_allows:
            raise ValueError(
                "FsPolicy.read_allows must be empty when read_model is DENY_LIST, "
                f"got {self.read_allows!r}"
            )
        # `read_denies` is active under BOTH models (decision-164): under
        # DENY_LIST it is the whole read policy, under ALLOW_LIST it is the
        # carve-outs subtracted from the allowed tree -- deny-over-allow, the
        # read twin of `write_denies`. So there is no inactive-field refusal
        # for it; `read_allows` under DENY_LIST keeps one, because a denylist
        # has nothing for an allow entry to mean.


@dataclass(frozen=True, slots=True)
class NetworkPolicy:
    allowed_domains: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "allowed_domains", _normalize_domains(self.allowed_domains))


@dataclass(frozen=True, slots=True)
class Limits:
    wall_seconds: int = 0
    cpu_seconds: int = 0
    memory_bytes: int = 0
    max_tasks: int = 0
    max_output_bytes: int = 0

    def __post_init__(self) -> None:
        for name in _LIMIT_FIELDS:
            value = getattr(self, name)
            if type(value) is not int or value < 0:
                raise ValueError(f"Limits.{name} must be a non-negative int, got {value!r}")


@dataclass(frozen=True, slots=True)
class EnvPolicy:
    mode: EnvMode = EnvMode.SCRUB
    allow_names: tuple[str, ...] = ()
    set: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "allow_names", _normalize_names(self.allow_names))
        object.__setattr__(self, "set", _normalize_pairs(self.set))

        if self.mode is EnvMode.PASS and self.allow_names:
            raise ValueError(
                f"EnvPolicy.allow_names must be empty when mode is PASS, got {self.allow_names!r}"
            )


@dataclass(frozen=True, slots=True)
class Channel:
    name: str
    kind: ChannelKind
    endpoint: str

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("Channel.name must be non-empty")
        if not self.endpoint:
            raise ValueError("Channel.endpoint must be non-empty")


@dataclass(frozen=True, slots=True)
class Provisioning:
    files: tuple[tuple[str, str], ...] = ()
    closures: tuple[str, ...] = ()
    env: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "files", _normalize_pairs(self.files))
        object.__setattr__(self, "closures", _normalize_names(self.closures))
        object.__setattr__(self, "env", _normalize_pairs(self.env))

        for path, _digest in self.files:
            if path == "":
                raise ValueError("Provisioning.files contains an entry with an empty path")


@dataclass(frozen=True, slots=True)
class Spec:
    fs: FsPolicy = field(default_factory=FsPolicy)
    network: NetworkPolicy = field(default_factory=NetworkPolicy)
    limits: Limits = field(default_factory=Limits)
    env: EnvPolicy = field(default_factory=EnvPolicy)
    channels: tuple[Channel, ...] = ()
    shared_media: tuple[str, ...] = ()
    provisioning: Provisioning = field(default_factory=Provisioning)

    def __post_init__(self) -> None:
        object.__setattr__(self, "shared_media", _normalize_paths(self.shared_media))
        object.__setattr__(self, "channels", tuple(sorted(self.channels, key=lambda c: c.name)))

        seen: set[str] = set()
        for channel in self.channels:
            if channel.name in seen:
                raise ValueError(f"Spec.channels contains duplicate channel name {channel.name!r}")
            seen.add(channel.name)

    def is_subset_of(self, other: Spec) -> bool:
        return (
            _write_allows_shrink(self, other)
            and _denies_grow(self, other)
            and _domains_shrink(self, other)
            and _limits_tighten(self, other)
            and _env_shrink(self, other)
            and _channels_shrink(self, other)
        )

    def narrowed_to(self, other: Spec) -> Spec:
        """The pointwise meet of self and other: the greatest lower bound --
        the most permissive Spec that is still a subset of both operands,
        never the vacuously strongest one.

        The two ALLOW axes meet as trees, not as sets of strings (SPEC.md
        section 5, decision-160): of each nested pair of entries the inner
        one survives, a disjoint pair contributes nothing. So narrowing a
        spec that allows `/w` onto a child asking for `/w/sub` yields
        `/w/sub`, without `/w/sub` having to be spelled out in the parent.
        Denies are still unioned as plain sets, which is a correct lower
        bound whatever the nesting.

        Raises IncomparableSpecs when self.fs.read_model != other.fs.read_model,
        or when self and other declare the same channel NAME with a different
        kind or endpoint. self.env.set and self.provisioning are carried
        through unchanged from self (the receiver).

        The env meet, three cases exactly: PASS is the identity (meet(PASS,
        X) is X, in either operand position); SCRUB absorbs PASS (the meet
        of a PASS operand with a SCRUB operand is that SCRUB operand, its
        allow-names carried through unchanged); two SCRUB policies meet by
        allow-name intersection.
        """
        if self.fs.read_model is not other.fs.read_model:
            raise IncomparableSpecs(
                f"read models differ: {self.fs.read_model!r} vs {other.fs.read_model!r}"
            )

        other_channels_by_name = {c.name: c for c in other.channels}
        for channel in self.channels:
            conflict = other_channels_by_name.get(channel.name)
            # Only the endpoint is compared: `LISTEN` is the only
            # `ChannelKind` there is since decision-153, so a kind
            # comparison beside this one is a branch nothing can reach.
            if conflict is not None and conflict.endpoint != channel.endpoint:
                raise IncomparableSpecs(
                    f"channel {channel.name!r} bound differently in each operand: "
                    f"{channel!r} vs {conflict!r}"
                )

        new_fs = FsPolicy(
            write_allows=_allows_meet(self.fs.write_allows, other.fs.write_allows),
            write_denies=tuple(set(self.fs.write_denies) | set(other.fs.write_denies)),
            read_model=self.fs.read_model,
            read_denies=tuple(set(self.fs.read_denies) | set(other.fs.read_denies)),
            read_allows=(
                _allows_meet(self.fs.read_allows, other.fs.read_allows)
                if self.fs.read_model is ReadModel.ALLOW_LIST
                else ()
            ),
        )
        new_network = NetworkPolicy(
            allowed_domains=tuple(
                set(self.network.allowed_domains) & set(other.network.allowed_domains)
            )
        )
        new_limits = Limits(
            **{
                name: _limit_min(getattr(self.limits, name), getattr(other.limits, name))
                for name in _LIMIT_FIELDS
            }
        )
        new_env = EnvPolicy(
            mode=(
                EnvMode.SCRUB if EnvMode.SCRUB in (self.env.mode, other.env.mode) else EnvMode.PASS
            ),
            allow_names=(
                tuple(set(self.env.allow_names) & set(other.env.allow_names))
                if self.env.mode is EnvMode.SCRUB and other.env.mode is EnvMode.SCRUB
                else self.env.allow_names
                if self.env.mode is EnvMode.SCRUB
                else other.env.allow_names
                if other.env.mode is EnvMode.SCRUB
                else ()
            ),
            set=self.env.set,
        )
        new_channels = tuple(c for c in self.channels if c.name in other_channels_by_name)
        new_shared_media = tuple(set(self.shared_media) & set(other.shared_media))

        return Spec(
            fs=new_fs,
            network=new_network,
            limits=new_limits,
            env=new_env,
            channels=new_channels,
            shared_media=new_shared_media,
            provisioning=self.provisioning,
        )

    def to_dict(self) -> dict[str, Any]:
        """Versioned, JSON-native dict. See SPEC.md section 5's
        serialization clause and task-007's Deliverable for the pinned
        format: top-level keys exactly `version`, `fs`, `network`,
        `limits`, `env`, `channels`, `shared_media`, `provisioning`; enums
        as their `.value` string; pair tuples as two-element lists;
        `channels` as a list of `{name, kind, endpoint}` dicts. No tuples,
        no enum objects, no sets survive into the result.
        """
        return {
            "version": SPEC_VERSION,
            "fs": {
                "write_allows": list(self.fs.write_allows),
                "write_denies": list(self.fs.write_denies),
                "read_model": self.fs.read_model.value,
                "read_denies": list(self.fs.read_denies),
                "read_allows": list(self.fs.read_allows),
            },
            "network": {
                "allowed_domains": list(self.network.allowed_domains),
            },
            "limits": {name: getattr(self.limits, name) for name in _LIMIT_FIELDS},
            "env": {
                "mode": self.env.mode.value,
                "allow_names": list(self.env.allow_names),
                "set": [[k, v] for k, v in self.env.set],
            },
            "channels": [
                {"name": c.name, "kind": c.kind.value, "endpoint": c.endpoint}
                for c in self.channels
            ],
            "shared_media": list(self.shared_media),
            "provisioning": {
                "files": [[path, digest] for path, digest in self.provisioning.files],
                "closures": list(self.provisioning.closures),
                "env": [[k, v] for k, v in self.provisioning.env],
            },
        }

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> Spec:
        """Inverse of `to_dict`. Raises `ValueError` for a missing
        `version`, an unknown key at any level, or an enum value string
        that names no member; raises `UnsupportedSpecVersion` (itself a
        `ValueError`) when `version` is present but not `SPEC_VERSION`.
        Each message names the offending key or value.

        A key missing below the top level (e.g. no `fs`, or `fs` present
        but missing `read_denies`) falls through to that field's normal
        dataclass default rather than raising -- `version` is the one key
        this method requires, per the Deliverable's four listed failure
        modes.

        The result is built through the ordinary `Spec`/`FsPolicy`/...
        constructors, so task-003's normalization and validation run on
        the way in: a hand-edited dict that violates a validation rule
        (e.g. DENY_LIST with a non-empty read_allows) raises from
        construction, not a from_dict-specific check, and so cannot
        smuggle in an illegal Spec.
        """
        if "version" not in d:
            raise ValueError("Spec.from_dict: missing required key 'version'")
        version = d["version"]
        if version != SPEC_VERSION:
            raise UnsupportedSpecVersion(
                f"Spec.from_dict: unsupported version {version!r}, expected {SPEC_VERSION!r}"
            )
        _check_keys(d, _TOP_LEVEL_KEYS, "top level")

        fs_d = d.get("fs", {})
        _check_keys(fs_d, _FS_KEYS, "fs")
        fs = FsPolicy(
            write_allows=tuple(fs_d.get("write_allows", ())),
            write_denies=tuple(fs_d.get("write_denies", ())),
            read_model=_enum_from_str(
                ReadModel, fs_d.get("read_model", ReadModel.DENY_LIST.value), "fs.read_model"
            ),
            read_denies=tuple(fs_d.get("read_denies", ())),
            read_allows=tuple(fs_d.get("read_allows", ())),
        )

        network_d = d.get("network", {})
        _check_keys(network_d, _NETWORK_KEYS, "network")
        network = NetworkPolicy(allowed_domains=tuple(network_d.get("allowed_domains", ())))

        limits_d = d.get("limits", {})
        _check_keys(limits_d, _LIMITS_KEYS, "limits")
        limits = Limits(**{name: limits_d.get(name, 0) for name in _LIMIT_FIELDS})

        env_d = d.get("env", {})
        _check_keys(env_d, _ENV_KEYS, "env")
        env = EnvPolicy(
            mode=_enum_from_str(EnvMode, env_d.get("mode", EnvMode.SCRUB.value), "env.mode"),
            allow_names=tuple(env_d.get("allow_names", ())),
            set=tuple(tuple(pair) for pair in env_d.get("set", ())),
        )

        channels_raw = d.get("channels", ())
        parsed_channels: list[Channel] = []
        for entry in channels_raw:
            _check_keys(entry, _CHANNEL_KEYS, "channels[]")
            parsed_channels.append(
                Channel(
                    name=entry["name"],
                    kind=_enum_from_str(ChannelKind, entry["kind"], "channels[].kind"),
                    endpoint=entry["endpoint"],
                )
            )

        provisioning_d = d.get("provisioning", {})
        _check_keys(provisioning_d, _PROVISIONING_KEYS, "provisioning")
        provisioning = Provisioning(
            files=tuple(tuple(pair) for pair in provisioning_d.get("files", ())),
            closures=tuple(provisioning_d.get("closures", ())),
            env=tuple(tuple(pair) for pair in provisioning_d.get("env", ())),
        )

        return cls(
            fs=fs,
            network=network,
            limits=limits,
            env=env,
            channels=tuple(parsed_channels),
            shared_media=tuple(d.get("shared_media", ())),
            provisioning=provisioning,
        )


class UnsupportedSpecVersion(ValueError):
    """Raised by Spec.from_dict when `version` is present but does not
    equal SPEC_VERSION. There is exactly one supported version; refusing
    any other is the whole contract (see task-007's Out of scope)."""


_TOP_LEVEL_KEYS: Final = frozenset(
    {"version", "fs", "network", "limits", "env", "channels", "shared_media", "provisioning"}
)
_FS_KEYS: Final = frozenset(
    {"write_allows", "write_denies", "read_model", "read_denies", "read_allows"}
)
_NETWORK_KEYS: Final = frozenset({"allowed_domains"})
_LIMITS_KEYS: Final = frozenset(_LIMIT_FIELDS)
_ENV_KEYS: Final = frozenset({"mode", "allow_names", "set"})
_CHANNEL_KEYS: Final = frozenset({"name", "kind", "endpoint"})
_PROVISIONING_KEYS: Final = frozenset({"files", "closures", "env"})


def _check_keys(d: Mapping[str, Any], allowed: frozenset[str], where: str) -> None:
    unknown = set(d) - allowed
    if unknown:
        raise ValueError(f"Spec.from_dict: unknown key(s) {sorted(unknown)!r} in {where}")


def _enum_from_str[E: Enum](enum_cls: type[E], raw: Any, where: str) -> E:
    try:
        return enum_cls(raw)
    except ValueError:
        raise ValueError(
            f"Spec.from_dict: {raw!r} is not a valid {enum_cls.__name__} value in {where}"
        ) from None


class IncomparableSpecs(ValueError):
    """Raised by Spec.narrowed_to when the two operands have no meet: their
    read models differ, or they bind the same channel name to a different
    kind or endpoint."""


def _write_allows_shrink(child: Spec, parent: Spec) -> bool:
    return _allows_reach_within(child.fs.write_allows, parent.fs.write_allows)


def _denies_grow(child: Spec, parent: Spec) -> bool:
    if child.fs.read_model is not parent.fs.read_model:
        return False
    if not set(child.fs.write_denies) >= set(parent.fs.write_denies):
        return False
    if not set(child.fs.read_denies) >= set(parent.fs.read_denies):
        return False
    if child.fs.read_model is ReadModel.DENY_LIST:
        return True
    return _allows_reach_within(child.fs.read_allows, parent.fs.read_allows)


def _domains_shrink(child: Spec, parent: Spec) -> bool:
    return set(child.network.allowed_domains) <= set(parent.network.allowed_domains)


def _limit_field_tightens(parent_value: int, child_value: int) -> bool:
    """0 means uncapped (+infinity). child tightens onto parent iff parent
    is uncapped, or child is capped and no higher than parent."""
    if parent_value == 0:
        return True
    return child_value != 0 and child_value <= parent_value


def _limit_min(a: int, b: int) -> int:
    """Pointwise minimum with 0 read as +infinity."""
    if a == 0:
        return b
    if b == 0:
        return a
    return min(a, b)


def _limits_tighten(child: Spec, parent: Spec) -> bool:
    return all(
        _limit_field_tightens(getattr(parent.limits, name), getattr(child.limits, name))
        for name in _LIMIT_FIELDS
    )


def _env_shrink(child: Spec, parent: Spec) -> bool:
    """SPEC.md section 5's PASS-is-top bullet, three cases exactly: a PASS
    parent's reach is the top element of the comparison, so it admits any
    child; a SCRUB parent can never confer PASS; two SCRUB policies compare
    by allow-name subset. `allow_names` is inert under PASS (enforced at
    EnvPolicy construction), so it is never consulted when either operand
    is PASS."""
    if parent.env.mode is EnvMode.PASS:
        return True
    if child.env.mode is EnvMode.PASS:
        return False
    return set(child.env.allow_names) <= set(parent.env.allow_names)


def _channels_shrink(child: Spec, parent: Spec) -> bool:
    parent_by_name = {c.name: c for c in parent.channels}
    for channel in child.channels:
        if parent_by_name.get(channel.name) != channel:
            return False
    return set(child.shared_media) <= set(parent.shared_media)
