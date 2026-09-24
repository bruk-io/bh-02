"""Spec and its six policy dataclasses: frozen, validated, self-normalizing.

SPEC.md section 5. See task-003 for the normalization/validation tables this
tests against.
"""

from dataclasses import FrozenInstanceError

import pytest

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

# ---------------------------------------------------------------------------
# AC #2: Spec() constructs with no arguments; every field carries its
# documented empty/zero default.
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_spec_constructs_with_no_arguments_and_documented_defaults() -> None:
    spec = Spec()

    assert spec.fs == FsPolicy()
    assert spec.network == NetworkPolicy()
    assert spec.limits == Limits()
    assert spec.env == EnvPolicy()
    assert spec.channels == ()
    assert spec.shared_media == ()
    assert spec.provisioning == Provisioning()


@pytest.mark.unit
def test_fs_policy_defaults() -> None:
    fs = FsPolicy()
    assert fs.write_allows == ()
    assert fs.write_denies == ()
    assert fs.read_model is ReadModel.DENY_LIST
    assert fs.read_denies == ()
    assert fs.read_allows == ()


@pytest.mark.unit
def test_network_policy_default_is_empty_deny_all() -> None:
    assert NetworkPolicy().allowed_domains == ()


@pytest.mark.unit
def test_limits_default_is_all_zero_uncapped() -> None:
    limits = Limits()
    assert limits.wall_seconds == 0
    assert limits.cpu_seconds == 0
    assert limits.memory_bytes == 0
    assert limits.max_tasks == 0
    assert limits.max_output_bytes == 0


@pytest.mark.unit
def test_env_policy_default_is_scrub_and_empty() -> None:
    env = EnvPolicy()
    assert env.mode is EnvMode.SCRUB
    assert env.allow_names == ()
    assert env.set == ()


@pytest.mark.unit
def test_provisioning_default_is_empty() -> None:
    prov = Provisioning()
    assert prov.files == ()
    assert prov.closures == ()
    assert prov.env == ()


# ---------------------------------------------------------------------------
# AC #3: normalization is idempotent and order-insensitive for every
# path-tuple field.
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_write_allows_normalization_is_order_and_noise_insensitive() -> None:
    a = FsPolicy(write_allows=("/a/", "/b", "/a", "//"))
    b = FsPolicy(write_allows=("/b/", "/a"))
    assert a.write_allows == b.write_allows == ("/a", "/b")
    assert a == b


@pytest.mark.unit
def test_write_denies_normalization_is_order_and_noise_insensitive() -> None:
    a = FsPolicy(write_denies=("/x/y/", "/x", "/x/y"))
    b = FsPolicy(write_denies=("/x", "/x/y/"))
    assert a.write_denies == b.write_denies == ("/x", "/x/y")
    assert a == b


@pytest.mark.unit
def test_read_denies_normalization_is_order_and_noise_insensitive() -> None:
    a = FsPolicy(read_denies=("/c/", "/a", "/c"))
    b = FsPolicy(read_denies=("/a", "/c/"))
    assert a.read_denies == b.read_denies == ("/a", "/c")
    assert a == b


@pytest.mark.unit
def test_read_allows_normalization_is_order_and_noise_insensitive() -> None:
    a = FsPolicy(read_model=ReadModel.ALLOW_LIST, read_allows=("/z/", "/y", "/z"))
    b = FsPolicy(read_model=ReadModel.ALLOW_LIST, read_allows=("/y", "/z/"))
    assert a.read_allows == b.read_allows == ("/y", "/z")
    assert a == b


@pytest.mark.unit
def test_shared_media_normalization_is_order_and_noise_insensitive() -> None:
    a = Spec(shared_media=("/m/", "/n", "/m"))
    b = Spec(shared_media=("/n", "/m/"))
    assert a.shared_media == b.shared_media == ("/m", "/n")
    assert a == b


@pytest.mark.unit
def test_bare_root_survives_path_normalization() -> None:
    assert FsPolicy(write_allows=("/",)).write_allows == ("/",)


@pytest.mark.unit
def test_write_allows_normalization_is_idempotent() -> None:
    once = FsPolicy(write_allows=("/a/", "/b//", "/a"))
    twice = FsPolicy(write_allows=once.write_allows)
    assert once.write_allows == twice.write_allows


@pytest.mark.unit
def test_write_denies_normalization_is_idempotent() -> None:
    once = FsPolicy(write_denies=("/a/", "/b//", "/a"))
    twice = FsPolicy(write_denies=once.write_denies)
    assert once.write_denies == twice.write_denies


@pytest.mark.unit
def test_read_denies_normalization_is_idempotent() -> None:
    once = FsPolicy(read_denies=("/a/", "/b//", "/a"))
    twice = FsPolicy(read_denies=once.read_denies)
    assert once.read_denies == twice.read_denies


@pytest.mark.unit
def test_fs_policy_read_allows_normalization_is_idempotent() -> None:
    once = FsPolicy(read_model=ReadModel.ALLOW_LIST, read_allows=("/a/", "/b//", "/a"))
    twice = FsPolicy(read_model=ReadModel.ALLOW_LIST, read_allows=once.read_allows)
    assert once.read_allows == twice.read_allows


@pytest.mark.unit
def test_spec_shared_media_normalization_is_idempotent() -> None:
    once = Spec(shared_media=("/a/", "/b//", "/a"))
    twice = Spec(shared_media=once.shared_media)
    assert once.shared_media == twice.shared_media


@pytest.mark.unit
def test_allowed_domains_normalization_lowercases_strips_dot_dedupes_sorts() -> None:
    a = NetworkPolicy(allowed_domains=("Example.com.", "b.com", "example.com"))
    b = NetworkPolicy(allowed_domains=("b.com", "EXAMPLE.COM."))
    assert a.allowed_domains == b.allowed_domains == ("b.com", "example.com")


@pytest.mark.unit
def test_allow_names_normalization_dedupes_and_sorts() -> None:
    a = EnvPolicy(allow_names=("PATH", "HOME", "PATH"))
    b = EnvPolicy(allow_names=("HOME", "PATH"))
    assert a.allow_names == b.allow_names == ("HOME", "PATH")


@pytest.mark.unit
def test_closures_normalization_dedupes_and_sorts() -> None:
    a = Provisioning(closures=("/nix/store/b", "/nix/store/a", "/nix/store/b"))
    b = Provisioning(closures=("/nix/store/a", "/nix/store/b"))
    assert a.closures == b.closures == ("/nix/store/a", "/nix/store/b")


@pytest.mark.unit
def test_channels_are_sorted_by_name() -> None:
    spec = Spec(
        channels=(
            Channel(name="z", kind=ChannelKind.LISTEN, endpoint="e1"),
            Channel(name="a", kind=ChannelKind.LISTEN, endpoint="e2"),
        )
    )
    assert [c.name for c in spec.channels] == ["a", "z"]


# ---------------------------------------------------------------------------
# AC #4: pair-tuple last-wins dedupe.
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_env_policy_set_last_occurrence_wins() -> None:
    assert EnvPolicy(set=(("A", "1"), ("A", "2"))).set == (("A", "2"),)


@pytest.mark.unit
def test_provisioning_files_last_occurrence_wins_and_sorts() -> None:
    prov = Provisioning(files=(("/p", "digest1"), ("/a", "digest0"), ("/p", "digest2")))
    assert prov.files == (("/a", "digest0"), ("/p", "digest2"))


@pytest.mark.unit
def test_provisioning_env_last_occurrence_wins() -> None:
    prov = Provisioning(env=(("K", "old"), ("K", "new")))
    assert prov.env == (("K", "new"),)


# ---------------------------------------------------------------------------
# AC #5: one pytest.raises(ValueError) test per numbered validation rule.
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_rule1_negative_limit_raises() -> None:
    with pytest.raises(ValueError) as excinfo:
        Limits(wall_seconds=-1)
    assert "Limits.wall_seconds" in str(excinfo.value)


@pytest.mark.unit
def test_rule1_bool_limit_is_rejected_as_not_an_int() -> None:
    with pytest.raises(ValueError) as excinfo:
        Limits(max_tasks=True)
    assert "Limits.max_tasks" in str(excinfo.value)


@pytest.mark.unit
def test_rule2_deny_list_with_read_allows_raises() -> None:
    with pytest.raises(ValueError) as excinfo:
        FsPolicy(read_model=ReadModel.DENY_LIST, read_allows=("/a",))
    assert "FsPolicy.read_allows" in str(excinfo.value)


@pytest.mark.unit
def test_rule3_allow_list_with_read_denies_raises() -> None:
    with pytest.raises(ValueError) as excinfo:
        FsPolicy(read_model=ReadModel.ALLOW_LIST, read_denies=("/a",))
    assert "FsPolicy.read_denies" in str(excinfo.value)


@pytest.mark.unit
def test_rule4_duplicate_channel_name_raises() -> None:
    with pytest.raises(ValueError) as excinfo:
        Spec(
            channels=(
                Channel(name="c1", kind=ChannelKind.LISTEN, endpoint="e1"),
                Channel(name="c1", kind=ChannelKind.LISTEN, endpoint="e2"),
            )
        )
    assert "Spec.channels" in str(excinfo.value)


@pytest.mark.unit
def test_rule5_empty_path_in_provisioning_files_raises() -> None:
    with pytest.raises(ValueError) as excinfo:
        Provisioning(files=(("", "digest"),))
    assert "Provisioning.files" in str(excinfo.value)


@pytest.mark.unit
def test_rule6_empty_channel_name_raises() -> None:
    with pytest.raises(ValueError) as excinfo:
        Channel(name="", kind=ChannelKind.LISTEN, endpoint="e1")
    assert "Channel.name" in str(excinfo.value)


@pytest.mark.unit
def test_rule6_empty_channel_endpoint_raises() -> None:
    with pytest.raises(ValueError) as excinfo:
        Channel(name="c1", kind=ChannelKind.LISTEN, endpoint="")
    assert "Channel.endpoint" in str(excinfo.value)


# ---------------------------------------------------------------------------
# AC #6: every dataclass is frozen.
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_spec_is_frozen() -> None:
    spec = Spec()
    with pytest.raises(FrozenInstanceError):
        spec.channels = ()  # type: ignore[misc]


@pytest.mark.unit
def test_fs_policy_is_frozen() -> None:
    fs = FsPolicy()
    with pytest.raises(FrozenInstanceError):
        fs.read_model = ReadModel.ALLOW_LIST  # type: ignore[misc]


@pytest.mark.unit
def test_network_policy_is_frozen() -> None:
    net = NetworkPolicy()
    with pytest.raises(FrozenInstanceError):
        net.allowed_domains = ()  # type: ignore[misc]


@pytest.mark.unit
def test_limits_is_frozen() -> None:
    limits = Limits()
    with pytest.raises(FrozenInstanceError):
        limits.wall_seconds = 1  # type: ignore[misc]


@pytest.mark.unit
def test_env_policy_is_frozen() -> None:
    env = EnvPolicy()
    with pytest.raises(FrozenInstanceError):
        env.mode = EnvMode.PASS  # type: ignore[misc]


@pytest.mark.unit
def test_channel_is_frozen() -> None:
    channel = Channel(name="c1", kind=ChannelKind.LISTEN, endpoint="e1")
    with pytest.raises(FrozenInstanceError):
        channel.name = "c2"  # type: ignore[misc]


@pytest.mark.unit
def test_provisioning_is_frozen() -> None:
    prov = Provisioning()
    with pytest.raises(FrozenInstanceError):
        prov.closures = ()  # type: ignore[misc]
