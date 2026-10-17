"""Unit tests for `brig.mech.oci`: the container mechanism's pure render (decision-202).

`Oci.compile` is a pure function of `(spec, ctx)`, so the whole `docker create` flag list is pinned
as a golden on any machine with no Docker on it. What cannot be checked this way -- that the flags
confine anything -- is `tests/integration/test_oci_flags_in_effect.py`'s, which skips by name
without a daemon. Every `CompileCtx` is built by hand with the literal platform `"linux"` and
literal path facts, never a real filesystem.
"""

from __future__ import annotations

import dataclasses
from typing import Any

import pytest

from brig.core import (
    Axis,
    Channel,
    ChannelKind,
    EnvMode,
    EnvPolicy,
    FsPolicy,
    Grade,
    Limits,
    NetworkPolicy,
    ReadModel,
    Spec,
)
from brig.core.runtime import EnvNotRepresentable, RuntimeKind
from brig.mech import CompileCtx, Oci, Step
from brig.mech.oci import (
    ENV_FILE_NAME,
    IDLE_COMMAND,
    CarveOutAboveRoot,
    ChannelsUnsupported,
    ContextMissing,
    EnvPassUnsupported,
    NetworkUnsupported,
    PathNotMountable,
    PlatformUnsupported,
    ReadModelUnsupported,
    UnknownUser,
)

pytestmark = pytest.mark.unit

_JAIL_DIR = "/run/brig/jail0"
_EUID = 1234
_WS = "/srv/ws"


def _ctx(
    *,
    exists: dict[str, bool] | None = None,
    is_dir: dict[str, bool] | None = None,
    resolved: dict[str, str] | None = None,
    paths: tuple[str, ...] = (),
    euid: int | None = _EUID,
    platform: str = "linux",
) -> CompileCtx:
    """A context where every path in `paths` resolves to itself, unless `resolved` says
    otherwise, and exists as a directory unless `exists` or `is_dir` say it does not."""
    return CompileCtx(
        jail_dir=_JAIL_DIR,
        platform=platform,
        resolved_paths={**{path: path for path in paths}, **(resolved or {})},
        path_exists={**{path: True for path in paths}, **(exists or {})},
        path_is_dir={**{path: True for path in paths}, **(is_dir or {})},
        euid=euid,
    )


def _s(**parts: Any) -> Spec:
    """A Spec on the allowlist read model, which is the only one `oci` compiles."""
    return Spec(fs=FsPolicy(read_model=ReadModel.ALLOW_LIST), **parts)


def _spec(**fs: object) -> Spec:
    return Spec(fs=FsPolicy(read_model=ReadModel.ALLOW_LIST, **fs))  # type: ignore[arg-type]


def _flags(spec: Spec, ctx: CompileCtx) -> tuple[str, ...]:
    step = Oci("img:1").compile(spec, ctx)
    assert step.container is not None
    return step.container.flags


#: The flags every container gets, whatever the Spec: the first ten, then the env file.
_BASE = (
    "--init",
    "--user",
    str(_EUID),
    "--network",
    "none",
    "--cap-drop",
    "ALL",
    "--security-opt",
    "no-new-privileges",
    "--read-only",
    "--env-file",
    f"{_JAIL_DIR}/{ENV_FILE_NAME}",
)


# --- the plan and the golden ---------------------------------------------------------------


def test_an_empty_spec_compiles_to_the_base_flags_and_nothing_else() -> None:
    step = Oci("img:1").compile(_s(), _ctx())
    assert step.container is not None
    assert step.container.flags == _BASE
    assert (step.container.image, step.container.command) == ("img:1", IDLE_COMMAND)
    assert step.container.env_file == f"{_JAIL_DIR}/oci.env"
    assert (step.container.env_forward, step.container.env_set) == ((), ())


def test_the_whole_flag_list_for_a_spec_with_every_mount_kind_is_this() -> None:
    """The golden: read allow, write root, the pin between the root and a carve-out, a carve-out
    that exists and one that does not, a masked file and a masked directory, a cpu limit."""
    git, hooks, envrc = f"{_WS}/.git", f"{_WS}/.git/hooks", f"{_WS}/.envrc"
    creds, secrets = f"{_WS}/creds.txt", f"{_WS}/secrets"
    spec = Spec(
        fs=FsPolicy(
            read_model=ReadModel.ALLOW_LIST,
            read_allows=("/data",),
            write_allows=(_WS,),
            write_denies=(hooks, envrc),
            read_denies=(creds, secrets),
        ),
        limits=Limits(cpu_seconds=7),
    )
    ctx = _ctx(
        paths=("/data", _WS, git, hooks, envrc, creds, secrets),
        exists={envrc: False},
        is_dir={hooks: True, creds: False, secrets: True, envrc: False},
    )
    assert _flags(spec, ctx) == (
        *_BASE,
        "--ulimit",
        "cpu=7:8",
        "--mount",
        "type=bind,src=/data,dst=/data,readonly",
        "--mount",
        f"type=bind,src={_WS},dst={_WS}",
        "--mount",
        f"type=bind,src={git},dst={git}",
        "--mount",
        f"type=tmpfs,dst={envrc},tmpfs-mode=0555,readonly",
        "--mount",
        f"type=bind,src={hooks},dst={hooks},readonly",
        "--mount",
        f"type=bind,src=/dev/null,dst={creds},readonly",
        "--mount",
        f"type=tmpfs,dst={secrets},tmpfs-mode=0001,readonly",
    )


def test_the_environment_is_never_on_the_command_line() -> None:
    """Law 9: a `set` value and a forwarded name travel in the file the plan renders, and no flag
    carries them -- not `-e`, not `--env`, not the value."""
    spec = _s(env=EnvPolicy(allow_names=("TOKEN",), set=(("SECRET", "hunter2 and more"),)))
    step = Oci("img:1").compile(spec, _ctx())
    assert step.container is not None
    flags = step.container.flags
    assert not {"-e", "--env"} & set(flags)
    assert not [flag for flag in flags if "hunter2" in flag or "TOKEN" in flag]
    assert flags.count("--env-file") == 1
    assert (step.container.env_forward, step.container.env_set) == (
        ("TOKEN",),
        (("SECRET", "hunter2 and more"),),
    )
    assert dict(step.env) == {}


def test_the_user_is_the_embedders_uid_and_never_guessed() -> None:
    assert _flags(_s(), _ctx(euid=0))[_BASE.index("--user") + 1] == "0"
    assert _flags(_s(), _ctx(euid=4711))[_BASE.index("--user") + 1] == "4711"
    with pytest.raises(UnknownUser, match="never guesses root"):
        Oci("img:1").compile(_s(), _ctx(euid=None))


def test_a_cpu_limit_has_a_second_of_headroom_and_zero_is_no_flag() -> None:
    assert _flags(_s(limits=Limits(cpu_seconds=3)), _ctx())[-2:] == ("--ulimit", "cpu=3:4")
    assert "--ulimit" not in _flags(_s(limits=Limits(memory_bytes=10**9)), _ctx())


def test_mounts_name_the_resolved_source_and_the_specs_own_destination() -> None:
    spec = _spec(read_allows=("/data",), write_allows=("/work",))
    ctx = _ctx(resolved={"/data": "/mnt/real/data", "/work": "/mnt/real/work"})
    ctx = dataclasses.replace(ctx, path_exists={}, path_is_dir={})
    flags = _flags(spec, ctx)
    assert "type=bind,src=/mnt/real/data,dst=/data,readonly" in flags
    assert "type=bind,src=/mnt/real/work,dst=/work" in flags


def test_the_pins_are_the_existing_directories_between_a_root_and_a_carve_out() -> None:
    """decision-168: each existing directory between the write root and a carve-out is bound over
    itself, shallowest first; one that does not exist is not (nothing to bind)."""
    deep = f"{_WS}/a/b/c.txt"
    spec = _spec(write_allows=(_WS,), write_denies=(deep,))
    pinned = {f"{_WS}/a": True, f"{_WS}/a/b": False}
    ctx = _ctx(
        paths=(_WS, f"{_WS}/a", f"{_WS}/a/b", deep),
        exists={f"{_WS}/a/b": False, deep: False},
        is_dir={deep: False, **pinned},
    )
    flags = _flags(spec, ctx)
    assert f"type=bind,src={_WS}/a,dst={_WS}/a" in flags
    assert not [flag for flag in flags if f"dst={_WS}/a/b," in flag and "bind" in flag]
    assert f"type=tmpfs,dst={deep},tmpfs-mode=0555,readonly" in flags


def test_a_write_carve_out_no_writable_tree_reaches_is_not_mounted() -> None:
    """decision-165: one outside every write root is unwritable already, and mounting it would be
    a READ grant."""
    spec = _spec(read_allows=("/data",), write_allows=(_WS,), write_denies=("/data/x", "/else"))
    flags = _flags(spec, _ctx(paths=("/data", _WS, "/data/x", "/else")))
    assert not [flag for flag in flags if "dst=/data/x" in flag or "dst=/else" in flag]


def test_a_read_carve_out_outside_every_mounted_root_is_inert() -> None:
    spec = _spec(write_allows=(_WS,), read_denies=("/etc/shadow",))
    flags = _flags(spec, _ctx(paths=(_WS, "/etc/shadow")))
    assert not [flag for flag in flags if "shadow" in flag]


def test_an_absent_read_carve_out_inside_a_root_is_left_alone_and_named_in_the_grade() -> None:
    spec = _spec(write_allows=(_WS,), read_denies=(f"{_WS}/local.env",))
    ctx = _ctx(paths=(_WS, f"{_WS}/local.env"), exists={f"{_WS}/local.env": False})
    step = Oci("img:1").compile(spec, ctx)
    assert step.container is not None
    assert not [flag for flag in step.container.flags if "local.env" in flag]
    assert f"{_WS}/local.env" in step.grades[Axis.FS_READ].detail
    assert "Not masked" in step.grades[Axis.FS_READ].detail


@pytest.mark.parametrize("kind", ["write_denies", "read_denies"])
def test_a_carve_out_above_a_root_is_refused_because_docker_mounts_the_shallower_first(
    kind: str,
) -> None:
    spec = _spec(write_allows=(f"{_WS}/sub",), **{kind: (_WS,)})
    with pytest.raises(CarveOutAboveRoot, match="laid over it"):
        Oci("img:1").compile(spec, _ctx(paths=(_WS, f"{_WS}/sub")))


@pytest.mark.parametrize("path", ["/a,b", '/a"b', "/a\nb"])
def test_a_path_mount_cannot_carry_is_refused(path: str) -> None:
    spec = _spec(write_allows=(path,))
    with pytest.raises(PathNotMountable, match="CSV"):
        Oci("img:1").compile(spec, _ctx(paths=(path,)))


@pytest.mark.parametrize(
    ("field", "message"),
    [("resolved_paths", "no resolved form"), ("path_exists", "no answer for path")],
)
def test_a_path_fact_the_context_lacks_is_a_refusal_naming_the_path(
    field: str, message: str
) -> None:
    spec = _spec(write_allows=(_WS,), write_denies=(f"{_WS}/x",))
    ctx = dataclasses.replace(_ctx(paths=(_WS, f"{_WS}/x")), **{field: {_WS: _WS}})
    with pytest.raises(ContextMissing, match=message):
        Oci("img:1").compile(spec, ctx)


# --- the refusals --------------------------------------------------------------------------


def test_each_thing_a_container_cannot_deliver_is_refused_by_name() -> None:
    refusals: list[tuple[Spec, CompileCtx, type[Exception], str]] = [
        (_s(), _ctx(platform="darwin"), PlatformUnsupported, "'darwin'"),
        (_s(), _ctx(platform=""), PlatformUnsupported, "''"),
        (_s(), _ctx(euid=None), UnknownUser, "ctx.euid"),
        (_s(env=EnvPolicy(mode=EnvMode.PASS)), _ctx(), EnvPassUnsupported, "SCRUB"),
        (
            _s(network=NetworkPolicy(allowed_domains=("example.com",))),
            _ctx(),
            NetworkUnsupported,
            "example.com",
        ),
        (
            _s(channels=(Channel(name="ctl", kind=ChannelKind.LISTEN),)),
            _ctx(),
            ChannelsUnsupported,
            "ctl",
        ),
        (Spec(fs=FsPolicy()), _ctx(), ReadModelUnsupported, "DENY_LIST"),
    ]
    for spec, ctx, error, text in refusals:
        with pytest.raises(error, match=text):
            Oci("img:1").compile(spec, ctx)


@pytest.mark.parametrize("image", ["", "-v", "a b", "a\tb"])
def test_an_image_name_that_is_not_one_is_refused_at_construction(image: str) -> None:
    with pytest.raises(ValueError, match="not an image name"):
        Oci(image)


@pytest.mark.parametrize(
    ("policy", "message"),
    [
        (EnvPolicy(allow_names=("A=B",)), "allow_names"),
        (EnvPolicy(allow_names=("1X",)), "allow_names"),
        (EnvPolicy(set=(("OK", "a\nb"),)), "newline"),
        (EnvPolicy(set=(("OK", "a\rb"),)), "carriage return"),
        (EnvPolicy(set=(("BAD NAME", "v"),)), "BAD NAME"),
    ],
)
def test_an_env_name_or_value_an_env_file_cannot_carry_is_refused_without_the_value(
    policy: EnvPolicy, message: str
) -> None:
    with pytest.raises(EnvNotRepresentable, match=message) as caught:
        Oci("img:1").compile(_s(env=policy), _ctx())
    assert "a\nb" not in str(caught.value)


# --- the env file the plan renders ---------------------------------------------------------


def _plan_for(policy: EnvPolicy):  # noqa: ANN202
    step = Oci("img:1").compile(_s(env=policy), _ctx())
    assert step.container is not None
    return step.container


def test_the_env_file_forwards_what_is_set_and_non_empty_then_the_set_pairs() -> None:
    plan = _plan_for(
        EnvPolicy(
            allow_names=("HOME", "EMPTY", "GONE", "TOKEN"), set=(("TOKEN", "pinned"), ("K", "v"))
        )
    )
    text = plan.env_file_text({"HOME": "/root", "EMPTY": "", "OTHER": "no", "TOKEN": "host"})
    assert text == "HOME=/root\nTOKEN=pinned\nK=v\n"


def test_the_env_file_holds_a_value_verbatim() -> None:
    value = 'a b "quoted" $HOME #hash =eq  trailing  é€'
    plan = _plan_for(EnvPolicy(allow_names=("V",)))
    assert plan.env_file_text({"V": value}) == f"V={value}\n"


def test_nothing_of_the_host_environment_but_the_allowed_names_is_in_the_file() -> None:
    plan = _plan_for(EnvPolicy(allow_names=("KEEP",)))
    text = plan.env_file_text({"KEEP": "1", "SECRET_TOKEN": "s3", "PATH": "/x"})
    assert text == "KEEP=1\n"
    assert _plan_for(EnvPolicy()).env_file_text({"SECRET_TOKEN": "s3"}) == ""


def test_a_forwarded_value_an_env_file_cannot_carry_is_refused_naming_only_the_variable() -> None:
    plan = _plan_for(EnvPolicy(allow_names=("TOKEN",)))
    with pytest.raises(EnvNotRepresentable, match="TOKEN") as caught:
        plan.env_file_text({"TOKEN": "line one\nline two"})
    assert "line one" not in str(caught.value)


# --- the step ------------------------------------------------------------------------------


def test_the_mechanism_names_the_oci_runtime_and_claims_five_axes() -> None:
    mechanism = Oci("img:1")
    assert mechanism.name == "oci" and mechanism.runtime is RuntimeKind.OCI
    assert mechanism.axes == {Axis.FS_READ, Axis.FS_WRITE, Axis.NETWORK, Axis.ENV, Axis.LIMITS}


def test_the_step_wraps_nothing_and_carries_no_helper_staged_file_or_sensor() -> None:
    step = Oci("img:1").compile(_s(), _ctx())
    assert isinstance(step, Step)
    assert step.wrap(("a", "b")) == ("a", "b")
    assert (step.env, step.staged, step.helpers, step.requires, step.events, step.supervisor) == (
        {},
        (),
        (),
        frozenset(),
        None,
        None,
    )


def test_the_grades_are_what_the_flags_deliver() -> None:
    grades = Oci("img:1").compile(_s(), _ctx()).grades
    assert set(grades) == {Axis.FS_READ, Axis.FS_WRITE, Axis.NETWORK, Axis.ENV}
    assert grades[Axis.NETWORK].grade is Grade.ENFORCED and "none" in grades[Axis.NETWORK].detail
    assert grades[Axis.FS_WRITE].grade is Grade.ENFORCED
    assert "write_denies" in grades[Axis.FS_WRITE].detail
    assert grades[Axis.ENV].grade is Grade.ENFORCED
    assert "docker inspect" in grades[Axis.ENV].detail
    # The gap is the image, so never `enforced`, and the detail says so.
    assert grades[Axis.FS_READ].grade is Grade.BEST_EFFORT
    assert "IMAGE" in grades[Axis.FS_READ].detail and "allowlist" in grades[Axis.FS_READ].detail


def test_limits_are_claimed_only_when_a_cpu_limit_gives_the_mechanism_work() -> None:
    """decision-092: with nothing to enforce there is nothing to grade; and with only the limits
    `--ulimit cpu` does not reach, nothing is enforced either."""
    assert Axis.LIMITS not in Oci("img:1").compile(_s(), _ctx()).grades
    assert (
        Axis.LIMITS
        not in Oci("img:1").compile(_s(limits=Limits(max_tasks=5, wall_seconds=9)), _ctx()).grades
    )
    graded = Oci("img:1").compile(_s(limits=Limits(cpu_seconds=1)), _ctx()).grades[Axis.LIMITS]
    assert graded.grade is Grade.BEST_EFFORT
    assert "uncovered: memory, tasks, wall, output" in graded.detail


def test_the_denial_signatures_are_the_two_a_container_produces() -> None:
    patterns = {p.pattern for p in Oci("img:1").compile(_s(), _ctx()).denial_signatures}
    assert patterns == {"Read-only file system", "Network is unreachable"}
