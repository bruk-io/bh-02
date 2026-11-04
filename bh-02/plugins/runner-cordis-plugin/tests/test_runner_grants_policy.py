"""Grants in the policy (decision-0012 items 1, 5 and 10): what `spec_for` and `to_brig` make of
them, and that the floor is asked first, with the path resolved. Pure but for the temp directory a
link is made in."""

from collections.abc import Mapping, Sequence
from pathlib import Path

from runner_cordis_plugin import BrigConfig, Brigged, Policy, allowlisted, spec_for, to_brig
from runner_cordis_plugin.grants import NO_GRANTS, Grant, Grants, Kind
from runner_cordis_plugin.policy import GUIDANCE, SELF_MODIFYING


def _policy(
    tmp_path: Path,
    grants: Grants = NO_GRANTS,
    *,
    secrets: Sequence[str] = (),
    layers: Sequence[str] = (),
    key_envs: Mapping[str, Sequence[str]] | None = None,
) -> Policy:
    project = tmp_path / "project"
    project.mkdir(exist_ok=True)
    return spec_for(
        root=str(project),
        scratch=str(tmp_path / "scratch"),
        home=str(tmp_path / "home"),
        config=BrigConfig(),
        layers=layers,
        host=(),
        secrets=secrets,
        grants=grants,
        key_envs=key_envs,
    )


def _brigged(policy: Policy, grants: Grants = NO_GRANTS) -> Brigged:
    return to_brig(policy, grants=grants, environ={}, stdout="/l/out", stderr="/l/err")


def test_nothing_granted_is_nothing_added(tmp_path: Path) -> None:
    policy = _policy(tmp_path)
    assert policy.readable == () and policy.refused == ()
    assert policy.writable == (str(tmp_path / "project"), str(tmp_path / "scratch"))
    assert "AWS_PROFILE" not in policy.env_allow
    assert _brigged(policy).egress.allow == ()  # the policy is always there, with nothing in it


def test_a_granted_read_write_env_and_destination_are_in_the_policy_and_nothing_else_is(
    tmp_path: Path,
) -> None:
    reading, writing = tmp_path / "data", tmp_path / "out"
    reading.mkdir()
    writing.mkdir()
    grants = Grants(
        (
            Grant(Kind.READ, str(reading)),
            Grant(Kind.WRITE, str(writing)),
            Grant(Kind.ENV, "AWS_PROFILE"),
            Grant(Kind.NET, "example.com", 443),
        )
    )
    policy = _policy(tmp_path, grants)
    brigged = _brigged(allowlisted(policy, ("/usr",)), grants)
    assert str(reading) in brigged.fs.readable and str(reading) not in brigged.fs.writable
    assert str(writing) in brigged.fs.writable
    assert "AWS_PROFILE" in brigged.env_policy.allowed
    assert [(d.host, d.port) for d in brigged.egress.allow] == [("example.com", 443)]
    # and what was not granted is not there
    other = tmp_path / "other"
    other.mkdir()
    assert all(str(other) not in tree for tree in (*brigged.fs.readable, *brigged.fs.writable))
    assert "GITHUB_TOKEN" not in brigged.env_policy.allowed
    assert policy.refused == ()


def test_a_grant_on_a_floor_path_is_refused_and_never_reaches_brig(tmp_path: Path) -> None:
    secret, layer, key = tmp_path / "sessions", tmp_path / "mine.toml", tmp_path / "home" / ".ssh"
    for path in (secret, key):
        path.mkdir(parents=True)
    layer.write_text("")
    grants = Grants(
        (
            Grant(Kind.READ, str(secret)),
            Grant(Kind.READ, str(key / "id")),
            Grant(Kind.WRITE, str(layer)),
            Grant(Kind.ENV, "HTTPS_PROXY"),
            Grant(Kind.ENV, "WORK_KEY"),
        )
    )
    policy = _policy(
        tmp_path,
        grants,
        secrets=(str(secret),),
        layers=(str(layer),),
        key_envs={"WORK_KEY": ("work",)},
    )
    assert len(policy.refused) == 5 and all("never granted" in why for why in policy.refused)
    brigged = _brigged(allowlisted(policy, ("/usr",)), grants)
    assert policy.readable == () and str(layer) not in brigged.fs.writable
    assert not {"HTTPS_PROXY", "WORK_KEY"} & set(brigged.env_policy.allowed)


def test_a_link_to_a_floor_path_is_refused_as_the_path_it_leads_to(tmp_path: Path) -> None:
    secret = tmp_path / "sessions"
    secret.mkdir()
    link = tmp_path / "innocent"
    link.symlink_to(secret)
    grants = Grants((Grant(Kind.READ, str(link)), Grant(Kind.WRITE, str(link / "sub"))))
    policy = _policy(tmp_path, grants, secrets=(str(secret),))
    assert len(policy.refused) == 2
    assert policy.readable == () and all(str(secret) in why for why in policy.refused)
    assert str(link) not in policy.writable and str(secret) not in policy.writable


def test_a_floor_path_given_as_a_link_is_compared_resolved_too(tmp_path: Path) -> None:
    real, alias = tmp_path / "real", tmp_path / "alias"
    real.mkdir()
    alias.symlink_to(real)
    policy = _policy(tmp_path, Grants((Grant(Kind.READ, str(real)),)), secrets=(str(alias),))
    assert policy.readable == () and len(policy.refused) == 1


def test_a_read_grant_where_nothing_is_there_is_left_out_with_the_reason(tmp_path: Path) -> None:
    policy = _policy(tmp_path, Grants((Grant(Kind.READ, str(tmp_path / "gone")),)))
    assert policy.readable == () and "nothing at" in policy.refused[0]


def test_the_guidance_files_are_writable_by_default_and_the_rest_need_an_exact_write_grant(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    (project / ".git" / "hooks").mkdir(parents=True)
    root = str(project)
    plain = _policy(tmp_path)
    assert not {f"{root}/{name}" for name in GUIDANCE} & set(plain.write_denies)
    assert {f"{root}/{name}" for name in SELF_MODIFYING} <= set(plain.write_denies)
    hooks = Grants((Grant(Kind.WRITE, f"{root}/.git/hooks"), Grant(Kind.WRITE, f"{root}/.envrc")))
    granted = _policy(tmp_path, hooks)
    assert f"{root}/.git/hooks" not in granted.write_denies and f"{root}/.envrc" not in granted.write_denies
    assert {f"{root}/.git/config", f"{root}/.bashrc"} <= set(granted.write_denies)  # only those exact paths
    parent = _policy(tmp_path, Grants((Grant(Kind.WRITE, f"{root}/.git"),)))
    assert f"{root}/.git/hooks" in parent.write_denies  # a parent lifts nothing


def test_a_granted_directory_beyond_the_project_keeps_the_self_modification_list(
    tmp_path: Path,
) -> None:
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    policy = _policy(tmp_path, Grants((Grant(Kind.WRITE, str(elsewhere)),)))
    assert str(elsewhere) in policy.writable
    assert f"{elsewhere}/.bashrc" in policy.write_denies and f"{elsewhere}/.git/hooks" in policy.write_denies


def test_a_write_grant_where_nothing_is_there_outside_the_project_is_left_out_with_the_reason(
    tmp_path: Path,
) -> None:
    # An always-grant on a folder since removed (a worktree): brig refuses a writable root that is
    # absent, so keeping it would fail every start.
    gone = tmp_path / "gone"
    policy = _policy(tmp_path, Grants((Grant(Kind.WRITE, str(gone)),)))
    assert str(gone) not in policy.writable and not any(d.startswith(str(gone)) for d in policy.write_denies)
    assert len(policy.refused) == 1 and "nothing there to write into" in policy.refused[0]
    assert all(Path(w).exists() for w in policy.writable if w != str(tmp_path / "scratch"))


def test_a_write_grant_on_an_absent_self_modifying_path_in_the_project_still_lifts_its_deny(
    tmp_path: Path,
) -> None:
    root = str(tmp_path / "project")
    policy = _policy(tmp_path, Grants((Grant(Kind.WRITE, f"{root}/.envrc"),)))
    assert f"{root}/.envrc" not in policy.write_denies  # the jail may make it
    assert policy.writable == (root, str(tmp_path / "scratch"))  # inside the project: no absent root
    assert policy.refused == ()


def test_a_write_grant_under_a_hidden_path_is_left_out_with_the_reason(tmp_path: Path) -> None:
    project = tmp_path / "project"
    (project / "private" / "inner").mkdir(parents=True)
    granted = str(project / "private" / "inner")
    policy = spec_for(
        root=str(project),
        scratch=str(tmp_path / "scratch"),
        home=str(tmp_path / "home"),
        config=BrigConfig(hide=("private",)),
        layers=(),
        host=(),
        secrets=(),
        grants=Grants((Grant(Kind.WRITE, granted),)),
    )
    assert granted not in policy.writable  # brig refuses a mask that hides a root
    assert len(policy.refused) == 1 and "the layer hides it" in policy.refused[0]
