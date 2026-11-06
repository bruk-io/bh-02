"""The seal's files: the key kept outside the repository, its committed digest, and the ledger."""

import stat

import pytest

from scenarios.seal import (
    ENV,
    SealError,
    begin_run,
    build,
    init,
    load_key,
    read_ledger,
    sealed_seeds,
    version,
)


@pytest.fixture
def paths(tmp_path):
    return (
        tmp_path / "config" / "seal.key",
        tmp_path / "repo" / "seal.json",
        tmp_path / "repo" / "ledger.jsonl",
    )


def _made(paths):
    key_file, commitment_file, ledger = paths
    commitment_file.parent.mkdir(parents=True)
    init(key_file, commitment_file, ledger)
    return load_key({}, key_file, commitment_file)


def test_init_keeps_the_key_readable_by_its_owner_only_and_commits_only_its_digest(paths):
    key_file, commitment_file, _ = paths
    key = _made(paths)
    assert stat.S_IMODE(key_file.stat().st_mode) == 0o600
    assert key.hex() not in commitment_file.read_text()


def test_a_second_init_is_refused_so_a_committed_key_is_not_lost_by_accident(paths):
    _made(paths)
    with pytest.raises(SealError, match="committed already"):
        init(*paths)


def test_a_key_that_is_not_the_committed_one_is_refused(paths):
    key_file, commitment_file, _ = paths
    _made(paths)
    with pytest.raises(SealError, match="not the committed one"):
        load_key({ENV: "00" * 32}, key_file, commitment_file)


def test_the_key_can_come_from_the_environment(paths):
    key_file, commitment_file, _ = paths
    key = _made(paths)
    key_file.unlink()
    assert load_key({ENV: key.hex()}, key_file, commitment_file) == key


def test_runs_take_set_after_set_and_every_build_and_run_leaves_a_line(paths):
    _, _, ledger = paths
    key = _made(paths)
    built = build(key, "code", 0, 3, ledger)
    first = begin_run(key, "code", 3, ledger, ("v1", ()))
    second = begin_run(key, "code", 3, ledger, ("v2", ()))
    assert first == (0, built) and second == (1, sealed_seeds(key, "code", 1, 3))
    assert [(e.event, e.set_no, e.version) for e in read_ledger(ledger)] == [
        ("keyed", -1, ""),
        ("built", 0, ""),
        ("run", 0, "v1"),
        ("run", 1, "v2"),
    ]


def test_a_key_a_run_has_used_cannot_be_replaced(paths):
    _, _, ledger = paths
    key = _made(paths)
    begin_run(key, "code", 1, ledger, ("v1", ()))
    with pytest.raises(SealError, match="keep that key"):
        init(*paths, rekey=True)


def test_an_unused_key_can_be_replaced_and_the_ledger_says_so(paths):
    key_file, commitment_file, ledger = paths
    old = _made(paths)
    init(*paths, rekey=True)
    assert load_key({}, key_file, commitment_file) != old
    assert read_ledger(ledger)[-1].note.startswith("replaces ")


def test_the_version_names_the_committed_envelope_code():
    ver, dirty = version()
    assert len(ver) == 16 and isinstance(dirty, tuple)
